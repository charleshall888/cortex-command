"""Telemetry helper for cortex-* backlog entry points.

Mirrors the byte-for-byte JSONL output of ``bin/cortex-log-invocation``
so post-migration records remain comparable to pre-migration records.
Fail-open contract: every error returns silently and writes a
breadcrumb to ``~/.cache/cortex/log-invocation-errors.log``. Five
breadcrumb categories match the bash shim: ``no_session_id``,
``no_repo_root``, ``session_dir_missing``, ``write_denied``,
``other``.

Spec R12 requires byte-equivalence, not implementation reuse — see
spec Non-Requirement #7. The bash shim and this helper remain
physically separate; the byte-equivalence assertion is enforced by
``cortex_command/backlog/tests/test_telemetry_byte_equivalence.py``.
"""

from __future__ import annotations

import datetime as _dt
import json as _json
import os as _os
import subprocess as _subprocess
import sys as _sys
from pathlib import Path as _Path


_BREADCRUMB_PATH = _Path.home() / ".cache" / "cortex" / "log-invocation-errors.log"


def _now_iso_utc() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_breadcrumb(category: str, snippet: str = "") -> None:
    """Append a one-line breadcrumb to the error log; swallow all failures."""
    try:
        _BREADCRUMB_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_BREADCRUMB_PATH, "a", encoding="utf-8") as f:
            f.write(f"{_now_iso_utc()} {category} {snippet}\n")
    except Exception:
        pass


def _resolve_repo_root() -> str:
    """Return git toplevel; empty string on any failure (matches bash).

    Consults ``CORTEX_REPO_ROOT`` first with a ``.git``-marker validation
    that mirrors the bash shim's ``[ -d "$root/.git" ] || [ -f "$root/.git" ]``
    guard. The Python predicate is pinned to ``marker.is_dir() or
    marker.is_file()`` — agrees with bash on regular files, directories,
    and broken symlinks. Falls back to ``git rev-parse --show-toplevel``
    on absent or invalid env (Spec #198 Task 2).
    """
    env_root = _os.environ.get("CORTEX_REPO_ROOT")
    if env_root:
        marker = _Path(env_root) / ".git"
        if marker.is_dir() or marker.is_file():
            return env_root
    try:
        result = _subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return ""
        return result.stdout.strip()
    except Exception:
        return ""


def log_invocation(script_name: str) -> None:
    """Emit one JSONL record for a cortex-* entry-point invocation.

    Byte-equivalent to ``bin/cortex-log-invocation`` per spec R12. The
    record schema is exactly four fields in this order:
    ``ts``, ``script``, ``argv_count``, ``session_id``. The output uses
    ``json.dumps(separators=(',', ':'), ensure_ascii=False)`` plus a
    trailing ``\\n`` so the bytes match what the bash shim's
    ``printf '{"ts":"%s","script":"%s","argv_count":%d,"session_id":"%s"}\\n'``
    produces for the same inputs.

    Wraps every code path in try/except — any failure produces a
    breadcrumb and returns silently (matches the bash shim's
    ``trap 'exit 0' EXIT``).

    Args:
        script_name: The user-visible command name (e.g.
            ``cortex-update-item``), NOT the Python module name.
    """
    try:
        session_id = _os.environ.get("LIFECYCLE_SESSION_ID")
        if not session_id:
            _write_breadcrumb("no_session_id", "")
            return

        repo_root = _resolve_repo_root()
        if not repo_root:
            _write_breadcrumb("no_repo_root", "")
            return

        session_dir = _Path(repo_root) / "cortex" / "lifecycle" / "sessions" / session_id
        try:
            session_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        if not session_dir.is_dir():
            _write_breadcrumb("session_dir_missing", str(session_dir))
            return

        # Bash skips records when script_name or session_id contains
        # `"` or `\`. Mirror that to preserve byte-equivalence — bash
        # printf would emit broken JSON, while json.dumps would emit
        # escaped JSON. Skipping in both implementations is the only
        # behavior that stays equivalent.
        if any(c in script_name or c in session_id for c in ('"', "\\")):
            _write_breadcrumb("other", str(session_dir))
            return

        argv_count = len(_sys.argv) - 1
        if argv_count < 0:
            argv_count = 0

        record = {
            "ts": _now_iso_utc(),
            "script": script_name,
            "argv_count": argv_count,
            "session_id": session_id,
        }
        line = _json.dumps(record, separators=(",", ":"), ensure_ascii=False) + "\n"

        log_file = session_dir / "bin-invocations.jsonl"
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            _write_breadcrumb("write_denied", str(log_file))
            return
    except Exception:
        _write_breadcrumb("other", "")
        return
