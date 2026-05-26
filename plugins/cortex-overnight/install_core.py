"""Stdlib-only install runner factored out of ``server.py`` (spec R9).

This module is the sibling of ``server.py`` that holds the install-path
helpers (``_run_install_and_verify`` and its support functions). It is
intentionally stdlib-only so the new SessionStart-async hook
(``hooks/cortex-cli-background-install.sh``, added in Phase 3) can
invoke the install path without loading ``server.py`` — which depends
on third-party packages (``mcp``, ``fastmcp``, ``pydantic``,
``packaging``) that the bare-stdlib hook Python cannot resolve.

Imports MUST be stdlib + the sibling ``install_guard`` and ``cli_pin``
modules only — no ``cortex_command.*``, no ``packaging``, no ``mcp``,
no ``pydantic``, no ``fastmcp`` (spec R13). Version comparison in this
module uses the stdlib ``version_tuple()`` helper below; ``packaging``
must not be imported here.

The ``_enforce_plugin_root`` function is **duplicated** (not imported)
from ``server.py`` per spec R10 — importing it would create a circular
import once Task 8 rewires ``server.py`` to import from ``install_core``.
A pre-commit byte-identity guard (Task 9) keeps the two copies in
sync.

The ``cli_pin`` import is deferred to function bodies so this module
loads cleanly during Phase 2 even before Phase 1's ``cli_pin.py`` is
in place. Once Phase 1 lands, callers see no behavior difference; the
deferred import is the same lazy-load pattern used for ``packaging``
in the legacy ``server.py:824`` site.
"""

from __future__ import annotations

import datetime as _datetime
import errno
import fcntl
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional


def _enforce_plugin_root() -> None:
    """R17 — confused-deputy mitigation.

    Verify, at startup, that this file lives under the resolved
    ``${CLAUDE_PLUGIN_ROOT}``. On mismatch (or absent env var), refuse
    to start: print ``"plugin path mismatch"`` to stderr and exit
    non-zero. This prevents an attacker who can override
    ``CLAUDE_PLUGIN_ROOT`` from pointing uv run at arbitrary Python.
    """

    plugin_root_env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if not plugin_root_env:
        print(
            "plugin path mismatch (CLAUDE_PLUGIN_ROOT not set)",
            file=sys.stderr,
        )
        sys.exit(1)

    file_path = Path(__file__).resolve()
    plugin_root = Path(plugin_root_env).resolve()

    if not file_path.is_relative_to(plugin_root):
        print(
            f"plugin path mismatch (file={file_path} root={plugin_root})",
            file=sys.stderr,
        )
        sys.exit(1)


# Fail-fast: enforce the confused-deputy invariant at import time,
# mirroring ``server.py:84``. The byte-identity parity guard added in
# Task 9 ensures this stays in sync with server.py's copy.
_enforce_plugin_root()


# ---------------------------------------------------------------------------
# Stdlib version-tuple helper (replaces packaging.Version in moved code)
# ---------------------------------------------------------------------------


def version_tuple(v: Optional[str]) -> tuple[int, ...]:
    """Convert ``vX.Y.Z`` (or ``X.Y.Z``) to an int tuple.

    PEP 440 prefix split only — no ``packaging`` import. Non-numeric
    segments truncate. Mirrors the shape used by the existing bash
    hook helper at
    ``plugins/cortex-overnight/hooks/cortex-cli-version-sync.sh:155-165``.

    Bare-semver only (per spec Technical Constraints): non-semver
    suffixes (``.post``, ``.dev``, ``+local``, ``rcN``) are not
    semantically ordered. The cortex-command release process emits
    bare semver tags (``vX.Y.Z``); a non-semver suffix is a
    release-process bug, not a runtime case this helper must handle.
    """
    v = (v or "").lstrip("v")
    parts: list[int] = []
    for seg in v.split("."):
        try:
            parts.append(int(seg))
        except ValueError:
            break
    return tuple(parts)


# ---------------------------------------------------------------------------
# Install-path constants (factored from server.py per spec R9)
# ---------------------------------------------------------------------------

#: Wait budget (seconds) for acquiring the cross-process install flock
#: at ``${XDG_STATE_HOME}/cortex-command/install.lock``. Spec R4c.
_INSTALL_FLOCK_WAIT_BUDGET_SECONDS = 60.0

#: Polling interval (seconds) used by the non-blocking install-flock
#: acquisition loop. Same trade-off as the R11 update flock.
_INSTALL_FLOCK_POLL_INTERVAL_SECONDS = 0.1

#: Timeout (seconds) for ``uv tool install --reinstall git+<url>@<tag>``.
#: A network-bound first install of the wheel; budget mirrors uv's own
#: default install behaviour for a fresh resolve + download.
_INSTALL_SUBPROCESS_TIMEOUT_SECONDS = 300.0

#: Timeout (seconds) for the post-install ``cortex --print-root --format
#: json`` verification probe. Bounded by argparse + a single state-file
#: read; 10s is generous.
_INSTALL_VERIFY_TIMEOUT_SECONDS = 10.0

#: Window (seconds) during which a recent ``install-failed.<ts>`` sentinel
#: short-circuits a re-attempt. Spec R4d: callers within 60s of a prior
#: failure surface the previous error rather than retrying on partial
#: state. After the window expires the sentinel is ignored and a fresh
#: install attempt is made.
_INSTALL_SENTINEL_WINDOW_SECONDS = 60.0

#: Maximum number of timestamped ``last-install-uv.<ts>.log`` files kept
#: under ``${XDG_STATE_HOME}/cortex-command/``. Older logs are pruned
#: by the install path itself via a single-pass directory scan at
#: install start (spec R11, should-have).
_UV_LOG_RETENTION_COUNT = 5


class CortexInstallFailed(RuntimeError):
    """Raised when first-install fails (subprocess error or verification).

    Carries a structured-failure context the MCP runtime surfaces to the
    Claude Code client. The hook returns silently on success; this
    exception is the only failure surface (apart from the hook being
    skipped via ``CORTEX_AUTO_INSTALL=0``, which falls through to the
    notice-only path that ``_CORTEX_CLI_MISSING_ERROR`` already covers).
    """


# ---------------------------------------------------------------------------
# R14 — NDJSON error log stages + emitter (factored from server.py)
# ---------------------------------------------------------------------------

#: Spec R14 stage values. Validated at append time so a typo in a call
#: site surfaces during development rather than landing as a malformed
#: audit record. Non-install callers in server.py (e.g.,
#: ``_orchestrate_upgrade``, ``_run_verification_probe``) import this
#: allowlist from install_core in Task 8.
_NDJSON_ERROR_STAGES = frozenset(
    {
        "git_ls_remote",
        "cortex_upgrade",
        "verification_probe",
        "flock_timeout",
        "first_install",
        # R4 version-comparison branch stages (Task 11). See
        # ``_ensure_cortex_installed``.
        "version_mismatch_reinstall",
        "version_mismatch_reinstall_parse_failure",
        "version_mismatch_blocked_by_inflight_session",
    }
)


def _last_error_log_path() -> Path:
    """Return ``${XDG_STATE_HOME:-$HOME/.local/state}/cortex-command/last-error.log``.

    Per spec R14 the log lives under XDG state home with a fallback to
    ``$HOME/.local/state``. Resolved fresh on each call so tests can
    redirect ``HOME`` / ``XDG_STATE_HOME`` via ``monkeypatch``.
    """
    xdg_state = os.environ.get("XDG_STATE_HOME")
    if xdg_state:
        base = Path(xdg_state)
    else:
        base = Path(os.environ.get("HOME", str(Path.home()))) / ".local" / "state"
    return base / "cortex-command" / "last-error.log"


def _append_error_ndjson(
    *,
    stage: str,
    error: str,
    context: Optional[dict[str, Any]] = None,
) -> None:
    """Append a single-line JSON record to the R14 error log.

    Schema (spec R14):

    .. code-block:: json

        {"ts": "<ISO 8601>", "stage": "<stage>",
         "error": "<message>", "context": {...}}

    Defensive: the helper itself never raises out to the caller. If the
    filesystem write fails (sandbox denial, disk full, etc.), the
    failure is logged to stderr and swallowed — the audit record is
    best-effort, but a failed audit-write must never collapse the
    user's tool call.
    """
    if stage not in _NDJSON_ERROR_STAGES:
        # Defensive: an unknown stage indicates a typo at the call site.
        # Log to stderr (one-liner) and substitute "unknown" so the
        # forensic record still lands rather than getting silently
        # dropped on a strict-validation branch.
        print(
            f"cortex MCP: NDJSON error-log received unknown stage "
            f"{stage!r}; recording as 'unknown'",
            file=sys.stderr,
        )
        stage = "unknown"

    record = {
        "ts": _datetime.datetime.now(_datetime.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "stage": stage,
        "error": error,
        "context": context or {},
    }

    log_path = _last_error_log_path()
    try:
        os.makedirs(log_path.parent, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except OSError as exc:
        # Best-effort: failed audit-write must never break the user's
        # tool call. Surface to stderr so the issue is at least visible.
        print(
            f"cortex MCP: failed to append NDJSON error record "
            f"({exc.__class__.__name__}: {exc}); continuing",
            file=sys.stderr,
        )


# ---------------------------------------------------------------------------
# Install state-dir helpers (factored from server.py)
# ---------------------------------------------------------------------------


def _install_state_dir() -> Path:
    """Return ``${XDG_STATE_HOME:-$HOME/.local/state}/cortex-command``.

    Resolved fresh on each call so tests can redirect ``HOME`` /
    ``XDG_STATE_HOME`` via ``monkeypatch`` (mirrors
    :func:`_last_error_log_path`).
    """
    xdg_state = os.environ.get("XDG_STATE_HOME")
    if xdg_state:
        base = Path(xdg_state)
    else:
        base = Path(os.environ.get("HOME", str(Path.home()))) / ".local" / "state"
    return base / "cortex-command"


def _install_lock_path() -> Path:
    """Return the install-lock path under XDG state home (R4c)."""
    return _install_state_dir() / "install.lock"


def _recent_install_failed_sentinel() -> Optional[Path]:
    """Return a sentinel path if any ``install-failed.*`` is fresh.

    "Fresh" means the file's mtime is within
    :data:`_INSTALL_SENTINEL_WINDOW_SECONDS` of now (R4d). Returns the
    most recent qualifying sentinel so the caller can surface its
    context. Returns ``None`` when the state dir is missing or no
    qualifying sentinel exists.
    """
    state_dir = _install_state_dir()
    if not state_dir.is_dir():
        return None
    cutoff = time.time() - _INSTALL_SENTINEL_WINDOW_SECONDS
    candidates: list[tuple[float, Path]] = []
    try:
        for entry in state_dir.iterdir():
            if not entry.name.startswith("install-failed."):
                continue
            try:
                mtime = entry.stat().st_mtime
            except OSError:
                continue
            if mtime >= cutoff:
                candidates.append((mtime, entry))
    except OSError:
        return None
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def _write_install_failed_sentinel(error: str) -> Path:
    """Create ``${XDG_STATE_HOME}/cortex-command/install-failed.<ts>``.

    The sentinel body is the failure summary so a subsequent reader can
    surface the prior failure context (R4d). Best-effort: directory
    creation and write failures are swallowed and the would-be path is
    still returned, so the caller can include it in the user-facing
    error even when the on-disk write itself failed.
    """
    state_dir = _install_state_dir()
    sentinel_path = state_dir / f"install-failed.{int(time.time())}"
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        sentinel_path.write_text(error, encoding="utf-8")
    except OSError as exc:
        print(
            f"cortex MCP: failed to write install-failed sentinel "
            f"({exc.__class__.__name__}: {exc}); continuing",
            file=sys.stderr,
        )
    return sentinel_path


def _acquire_install_flock(lock_path: Path) -> Optional[int]:
    """Acquire ``fcntl.flock(LOCK_EX)`` on ``lock_path`` with a 60s budget.

    Pattern derived from R11 / ``cortex_command/init/settings_merge.py``:
    non-blocking poll so the wait budget is enforced cooperatively
    without depending on signal delivery (incompatible with the FastMCP
    runtime's signal handlers).

    Returns the open file descriptor on success. Returns ``None`` on
    budget expiry; the caller raises :class:`CortexInstallFailed` after
    logging the timeout.
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600)
    deadline = time.monotonic() + _INSTALL_FLOCK_WAIT_BUDGET_SECONDS
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return fd
            except OSError as exc:
                if exc.errno not in (errno.EWOULDBLOCK, errno.EAGAIN):
                    os.close(fd)
                    raise
            if time.monotonic() >= deadline:
                os.close(fd)
                return None
            time.sleep(_INSTALL_FLOCK_POLL_INTERVAL_SECONDS)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        raise


def _release_install_flock(fd: int) -> None:
    """Release the install flock acquired by :func:`_acquire_install_flock`."""
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _resolve_installed_cortex_path() -> Optional[str]:
    """Return the absolute path of the installed ``cortex`` console script.

    Strategy: shell out to ``uv tool list --show-paths`` and parse the
    ``- cortex (/abs/path)`` line under the ``cortex-command`` package
    block. This closes the PATH-poisoning surface flagged in research
    §H/§I: the post-install verification probe targets the absolute
    path uv just wrote, not whichever ``cortex`` happens to be first on
    PATH after the reinstall.

    Returns ``None`` on parse/probe failure; callers fall back to a
    failure-emitting NDJSON record rather than silently regressing to
    bare-PATH ``cortex``.
    """
    try:
        result = subprocess.run(
            ["uv", "tool", "list", "--show-paths"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None

    if result.returncode != 0:
        return None

    # Match lines like: ``- cortex (/Users/.../bin/cortex)``. The first
    # match is the cortex console script (other entries are
    # ``cortex-*`` siblings — we anchor the script name with a literal
    # space-paren to disambiguate).
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line.startswith("- cortex ("):
            continue
        # Strip ``- cortex (`` prefix and the trailing ``)``.
        path_str = line[len("- cortex (") :]
        if not path_str.endswith(")"):
            continue
        return path_str[:-1]
    return None


# ---------------------------------------------------------------------------
# Timestamped uv-log helpers (spec R11, should-have)
# ---------------------------------------------------------------------------


def _uv_log_path() -> Path:
    """Return a per-install timestamped uv log path.

    ``${XDG_STATE_HOME:-$HOME/.local/state}/cortex-command/last-install-uv.<unix-timestamp>.log``

    Per spec R11: timestamped filenames preserve diagnostic data
    across the 30-min retry boundary (the legacy truncate-on-each-
    invocation approach lost prior failure context). The async hook
    records the path in its NDJSON record's ``uv_log_path`` field so
    consumers can correlate.
    """
    return _install_state_dir() / f"last-install-uv.{int(time.time())}.log"


def _prune_uv_logs(retention: int = _UV_LOG_RETENTION_COUNT) -> None:
    """Keep the N most-recent ``last-install-uv.<ts>.log`` files.

    Single-pass directory scan at install start; older logs are
    unlinked when count > ``retention`` (most-recent-by-mtime are
    kept). Best-effort: any OSError during scan or unlink is swallowed
    silently — log pruning must never block an install.
    """
    state_dir = _install_state_dir()
    if not state_dir.is_dir():
        return
    candidates: list[tuple[float, Path]] = []
    try:
        for entry in state_dir.iterdir():
            name = entry.name
            if not (name.startswith("last-install-uv.") and name.endswith(".log")):
                continue
            try:
                mtime = entry.stat().st_mtime
            except OSError:
                continue
            candidates.append((mtime, entry))
    except OSError:
        return
    if len(candidates) <= retention:
        return
    # Sort newest-first; everything past the retention boundary is stale.
    candidates.sort(reverse=True)
    for _, stale_path in candidates[retention:]:
        try:
            stale_path.unlink()
        except OSError:
            continue


# ---------------------------------------------------------------------------
# Install + verify runner (factored from server.py:581)
# ---------------------------------------------------------------------------


def _run_install_and_verify(*, stage: str) -> None:
    """Run ``uv tool install --reinstall`` + verification probe.

    Shared body for both the first-install branch (``stage=
    "first_install"``) and the version-mismatch branches (``stage=
    "version_mismatch_reinstall"`` and
    ``stage="version_mismatch_reinstall_parse_failure"``). All NDJSON
    records emitted from this helper carry the supplied ``stage`` so
    integration tests can disambiguate which branch fired.

    Acquires the install flock, re-verifies CLI presence under the
    lock (skip on contending process), runs ``uv tool install``, then
    verifies via the absolute-path-pinned ``cortex --print-root
    --format json`` (closes the PATH-poisoning surface).
    """
    # Lazy import: ``cli_pin`` is a sibling stdlib module added in
    # Phase 1. Deferring the import keeps this module loadable in
    # isolation during Phase 2 work and mirrors the lazy-import
    # pattern used in the legacy ``server.py`` install path.
    from cli_pin import CLI_PIN

    # Single-pass prune of stale per-install uv logs (spec R11).
    _prune_uv_logs()
    uv_log_path = _uv_log_path()

    lock_path = _install_lock_path()
    fd = _acquire_install_flock(lock_path)
    if fd is None:
        error = (
            f"timed out waiting "
            f"{int(_INSTALL_FLOCK_WAIT_BUDGET_SECONDS)}s for "
            f"{lock_path}"
        )
        _append_error_ndjson(
            stage=stage,
            error=error,
            context={
                "cli_pin": CLI_PIN[0],
                "exit_code": -1,
                "phase": "flock_timeout",
                "uv_log_path": str(uv_log_path),
            },
        )
        raise CortexInstallFailed(
            f"cortex auto-install: {error}; another MCP session is "
            f"holding the install lock."
        )

    try:
        # Re-verify under the lock: a contending process may have just
        # finished installing matching version. For first-install,
        # bare ``which`` suffices. For version-mismatch we re-enter
        # the outer loop only by retry; this helper does not loop.
        if stage == "first_install" and shutil.which("cortex") is not None:
            return

        install_argv = [
            "uv",
            "tool",
            "install",
            "--reinstall",
            "--refresh-package",
            "cortex-command",
            f"git+https://github.com/charleshall888/cortex-command.git"
            f"@{CLI_PIN[0]}",
        ]
        try:
            install_result = subprocess.run(
                install_argv,
                timeout=_INSTALL_SUBPROCESS_TIMEOUT_SECONDS,
                capture_output=True,
                text=True,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            error = f"{exc.__class__.__name__}: {exc}"
            sentinel_path = _write_install_failed_sentinel(error)
            _append_error_ndjson(
                stage=stage,
                error=error,
                context={
                    "cli_pin": CLI_PIN[0],
                    "exit_code": -1,
                    "phase": "uv_tool_install",
                    "sentinel": str(sentinel_path),
                    "uv_log_path": str(uv_log_path),
                },
            )
            raise CortexInstallFailed(
                f"cortex auto-install (`uv tool install --reinstall "
                f"--refresh-package cortex-command "
                f"git+...@{CLI_PIN[0]}`) failed: {error}"
            ) from exc

        if install_result.returncode != 0:
            error = (
                f"uv tool install exit={install_result.returncode}; "
                f"stderr={install_result.stderr!r}"
            )
            sentinel_path = _write_install_failed_sentinel(error)
            _append_error_ndjson(
                stage=stage,
                error=error,
                context={
                    "cli_pin": CLI_PIN[0],
                    "exit_code": install_result.returncode,
                    "phase": "uv_tool_install",
                    "sentinel": str(sentinel_path),
                    "uv_log_path": str(uv_log_path),
                },
            )
            raise CortexInstallFailed(
                f"cortex auto-install (`uv tool install --reinstall "
                f"--refresh-package cortex-command "
                f"git+...@{CLI_PIN[0]}`) failed: {error}"
            )

        # Resolve the absolute path of the just-installed cortex
        # console script. Falls back to a failure NDJSON record rather
        # than regressing to bare-PATH ``cortex`` (closes the
        # PATH-poisoning surface flagged in research §H/§I).
        cortex_abs_path = _resolve_installed_cortex_path()
        if cortex_abs_path is None:
            error = (
                "post-install verification: could not resolve absolute "
                "cortex path via `uv tool list --show-paths`"
            )
            sentinel_path = _write_install_failed_sentinel(error)
            _append_error_ndjson(
                stage=stage,
                error=error,
                context={
                    "cli_pin": CLI_PIN[0],
                    "exit_code": -1,
                    "phase": "resolve_absolute_path",
                    "sentinel": str(sentinel_path),
                    "uv_log_path": str(uv_log_path),
                },
            )
            raise CortexInstallFailed(error)

        # Post-install verification — `cortex --print-root --format json`,
        # invoked via the absolute path (NOT bare PATH).
        try:
            verify_result = subprocess.run(
                [cortex_abs_path, "--print-root", "--format", "json"],
                timeout=_INSTALL_VERIFY_TIMEOUT_SECONDS,
                capture_output=True,
                text=True,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            error = (
                f"post-install verification "
                f"(`{cortex_abs_path} --print-root --format json`) "
                f"raised: {exc.__class__.__name__}: {exc}"
            )
            sentinel_path = _write_install_failed_sentinel(error)
            _append_error_ndjson(
                stage=stage,
                error=error,
                context={
                    "cli_pin": CLI_PIN[0],
                    "exit_code": -1,
                    "phase": "verify_print_root",
                    "sentinel": str(sentinel_path),
                    "uv_log_path": str(uv_log_path),
                },
            )
            raise CortexInstallFailed(error) from exc

        if verify_result.returncode != 0:
            error = (
                f"post-install verification "
                f"(`{cortex_abs_path} --print-root --format json`) "
                f"exit={verify_result.returncode}; "
                f"stderr={verify_result.stderr!r}"
            )
            sentinel_path = _write_install_failed_sentinel(error)
            _append_error_ndjson(
                stage=stage,
                error=error,
                context={
                    "cli_pin": CLI_PIN[0],
                    "exit_code": verify_result.returncode,
                    "phase": "verify_print_root",
                    "sentinel": str(sentinel_path),
                    "uv_log_path": str(uv_log_path),
                },
            )
            raise CortexInstallFailed(error)

        try:
            json.loads(verify_result.stdout)
        except json.JSONDecodeError as exc:
            error = (
                f"post-install verification "
                f"(`{cortex_abs_path} --print-root --format json`) "
                f"emitted unparseable JSON: {exc}; "
                f"stdout={verify_result.stdout!r}"
            )
            sentinel_path = _write_install_failed_sentinel(error)
            _append_error_ndjson(
                stage=stage,
                error=error,
                context={
                    "cli_pin": CLI_PIN[0],
                    "exit_code": verify_result.returncode,
                    "phase": "verify_print_root_parse",
                    "sentinel": str(sentinel_path),
                    "uv_log_path": str(uv_log_path),
                },
            )
            raise CortexInstallFailed(error) from exc
    finally:
        _release_install_flock(fd)
