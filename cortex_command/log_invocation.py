"""Fail-open JSONL invocation logger for bin/cortex-* scripts.

Python port of the bash ``bin/cortex-log-invocation`` shim. Emits one JSON
line per invocation to
``cortex/lifecycle/sessions/<LIFECYCLE_SESSION_ID>/bin-invocations.jsonl``
under the resolved repo root. The contract is **fail-open**: every error
path exits 0 with a breadcrumb appended to
``~/.cache/cortex/log-invocation-errors.log``. The breadcrumb category set
is preserved verbatim from the bash original:
``no_session_id``, ``no_repo_root``, ``session_dir_missing``,
``write_denied``, ``other``.

Usage: ``cortex-log-invocation <script_path> [argv...]``

JSON emission uses :func:`json.dumps` with ``ensure_ascii=False`` and
``separators=(",", ":")`` so the output matches ``jq -c``'s UTF-8 default
emission (required for the Phase 1 golden-replay parity scaffold to apply
byte-identical assertions to fixtures containing em-dashes, smart quotes,
or names with diacritics).

The function ``main(argv)`` exposes the console-script entry point and
returns an integer exit code; the trap-style ``exit 0`` contract is
enforced by ``main`` returning 0 on every code path.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional


_BREADCRUMB_DIR_ENV = "HOME"
_BREADCRUMB_REL = ".cache/cortex/log-invocation-errors.log"


def _utc_now_iso() -> str:
    """Return the current UTC timestamp in the bash-script's format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _log_breadcrumb(category: str, snippet: str = "") -> None:
    """Append a single breadcrumb line to the cache log.

    Silent on every error — the breadcrumb logger is itself fail-open.
    """
    home = os.environ.get(_BREADCRUMB_DIR_ENV)
    if not home:
        return
    cache_dir = Path(home) / ".cache" / "cortex"
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        line = f"{_utc_now_iso()} {category} {snippet}\n"
        with (cache_dir / "log-invocation-errors.log").open("a", encoding="utf-8") as fh:
            fh.write(line)
    except OSError:
        return


def _resolve_repo_root() -> Optional[Path]:
    """Resolve the repo root using ``CORTEX_REPO_ROOT`` then ``git rev-parse``.

    Returns ``None`` when neither path yields a usable root. Mirrors the
    bash original's logic precisely: trust ``CORTEX_REPO_ROOT`` only when
    it points at a directory containing a ``.git`` entry (file or dir),
    else fall back to ``git rev-parse --show-toplevel``.
    """
    env_root = os.environ.get("CORTEX_REPO_ROOT")
    if env_root:
        candidate = Path(env_root)
        git_marker = candidate / ".git"
        if git_marker.is_dir() or git_marker.is_file():
            return candidate

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    stripped = result.stdout.strip()
    if not stripped:
        return None
    return Path(stripped)


def main(argv: Optional[List[str]] = None) -> int:
    """Fail-open invocation logger.

    Always returns 0. Records a breadcrumb on every non-write code path.
    """
    args = list(sys.argv[1:] if argv is None else argv)

    session_id = os.environ.get("LIFECYCLE_SESSION_ID", "")
    if not session_id:
        _log_breadcrumb("no_session_id", "")
        return 0

    repo_root = _resolve_repo_root()
    if repo_root is None:
        _log_breadcrumb("no_repo_root", "")
        return 0

    session_dir = repo_root / "cortex" / "lifecycle" / "sessions" / session_id
    if not session_dir.is_dir():
        try:
            session_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
    if not session_dir.is_dir():
        _log_breadcrumb("session_dir_missing", str(session_dir))
        return 0

    script_path = args[0] if args else ""
    script_name = script_path.rsplit("/", 1)[-1] if script_path else ""
    argv_count = max(len(args) - 1, 0)

    # Bash original rejects quotes/backslashes in script_name or session_id
    # via a glob case-pattern; preserve the same defensive guard.
    forbidden = ('"', "\\")
    combined = script_name + session_id
    if any(ch in combined for ch in forbidden):
        _log_breadcrumb("other", str(session_dir))
        return 0

    ts = _utc_now_iso()
    record = {
        "ts": ts,
        "script": script_name,
        "argv_count": argv_count,
        "session_id": session_id,
    }
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"

    log_file = session_dir / "bin-invocations.jsonl"
    try:
        with log_file.open("a", encoding="utf-8") as fh:
            fh.write(line)
    except OSError:
        _log_breadcrumb("write_denied", str(log_file))
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
