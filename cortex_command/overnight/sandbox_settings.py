"""Per-spawn sandbox-settings construction for overnight orchestrator and dispatch.

This module is the single shared library layer beneath both spawn sites
(``cortex_command/overnight/runner.py`` and ``cortex_command/pipeline/dispatch.py``)
that constructs the documented ``sandbox.filesystem.{denyWrite,allowWrite}`` JSON
shape, manages per-spawn tempfile lifecycle, emits the Linux-platform warning,
and records the ``CORTEX_SANDBOX_SOFT_FAIL`` event under an exclusive file lock.

Both spawn sites consume this layer's outputs as JSON dicts that are written to
per-spawn tempfiles and passed via ``--settings <tempfile>`` (orchestrator) or
``ClaudeAgentOptions(settings=str(tempfile_path))`` (dispatch).

This file establishes the public surface (constants + builder signatures) only.
Builder bodies are implemented in subsequent tasks; signatures raise
``NotImplementedError`` so downstream callers can wire against the surface
while bodies are filled in.
"""

from __future__ import annotations

import atexit
import fcntl
import json
import os
import stat
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, TextIO

from cortex_command.common import atomic_write


# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

SOFT_FAIL_ENV_VAR = "CORTEX_SANDBOX_SOFT_FAIL"
"""Environment variable name for the kill-switch that downgrades
``sandbox.failIfUnavailable`` from ``true`` to ``false``. Read at each
settings-builder invocation per spec Req 4."""

SETTINGS_TEMPFILE_PREFIX = "cortex-sandbox-"
"""Prefix for per-spawn settings tempfiles created via ``tempfile.mkstemp``."""

SETTINGS_TEMPFILE_SUFFIX = ".json"
"""Suffix for per-spawn settings tempfiles."""

SETTINGS_DIRNAME = "sandbox-settings"
"""Subdirectory name under ``<session_dir>/`` where per-spawn settings tempfiles
live. Per spec Req 11, tempfiles live alongside other session-scoped state
rather than in system ``/tmp/``."""

GIT_DENY_SUFFIXES = (
    ".git/refs/heads/main",
    ".git/refs/heads/master",
    ".git/HEAD",
    ".git/packed-refs",
)
"""Per-repo git-state-mutation paths added to the orchestrator deny-set per spec
Req 3. Static enumeration covers ``main`` / ``master`` default branches; custom
default branches (``develop``, ``trunk``, etc.) are NOT covered by V1 and are
documented as a limitation in the spec Non-Requirements."""

OUT_OF_WORKTREE_ALLOW_WRITERS: tuple[str, ...] = (
    "~/.cache/uv/",
    "$TMPDIR/",
    "~/.claude/sessions/",
    "~/.cache/cortex/",
    "~/.cache/cortex-command/",
    "~/.local/share/overnight-sessions/",
)
"""Risk-targeted out-of-worktree writers added to the per-feature dispatch
``allowWrite`` list per spec Req 10. Each entry corresponds to a documented
cortex writer:

- ``~/.cache/uv/``: SDK package install during retry-resolve flows.
- ``$TMPDIR/``: Python tempfile output (locked into dispatched-agent env to
  prevent unset-fallback to ``/tmp/``).
- ``~/.claude/sessions/``: SDK session JSON files.
- ``~/.cache/cortex/``: backlog telemetry breadcrumb log
  (``cortex_command/backlog/_telemetry.py:27``).
- ``~/.cache/cortex-command/``: scheduled-launches sidecar + lock
  (``cortex_command/overnight/scheduler/sidecar.py:3``).
- ``~/.local/share/overnight-sessions/``: install-guard + dashboard
  active-session pointer (``cortex_command/install_guard.py:55``,
  ``cortex_command/dashboard/poller.py:109``).
"""

LINUX_WARNING = (
    "WARNING: cortex sandbox enforcement is macOS-Seatbelt-only; "
    "Linux/bwrap behavior is undefined per parent epic #162. "
    "Sandbox configuration may not enforce as documented."
)
"""One-line stderr warning emitted at first builder invocation when
``sys.platform != "darwin"`` per spec Req 18. Observability-only; does NOT
crash or exit. Linux invocation is undefined behavior with stderr advisory."""


# ---------------------------------------------------------------------------
# Builder signatures (bodies implemented in Tasks 2 and 3)
# ---------------------------------------------------------------------------


def build_orchestrator_deny_paths(
    home_repo: Path,
    integration_worktrees: dict[str, str],
) -> list[str]:
    """Build the orchestrator deny-set: per-repo git-state-mutation paths.

    For ``home_repo`` and each repo key in ``integration_worktrees``, emit four
    entries by joining the repo path with each ``GIT_DENY_SUFFIXES`` value.
    Per spec Req 3, this is static enumeration — no dynamic
    ``git symbolic-ref`` resolution.

    Args:
        home_repo: Absolute path to the home cortex repo.
        integration_worktrees: Mapping of cross-repo absolute paths (keys) to
            integration-worktree paths (values), per
            ``cortex_command/overnight/state.py:228-230``.

    Returns:
        List of absolute deny-paths. Length is ``4 * (1 + len(integration_worktrees))``.
    """
    repo_paths: list[str] = [str(home_repo)]
    for repo_key in integration_worktrees.keys():
        if repo_key not in repo_paths:
            repo_paths.append(repo_key)

    deny_paths: list[str] = []
    for repo_path in repo_paths:
        for suffix in GIT_DENY_SUFFIXES:
            deny_paths.append(str(Path(repo_path) / suffix))
    return deny_paths


def build_dispatch_allow_paths(
    worktree_path: Path,
    integration_base_path: Path | None,
) -> list[str]:
    """Build the per-feature dispatch allow-list.

    Returns the worktree path, the optional integration-base path, and the six
    expanded ``OUT_OF_WORKTREE_ALLOW_WRITERS`` entries (with ``~`` and
    ``$TMPDIR`` resolved).

    Args:
        worktree_path: Absolute path to the per-feature worktree.
        integration_base_path: Cross-repo integration-base path, or ``None`` for
            home-repo dispatches.

    Returns:
        List of absolute allow-paths.
    """
    allow_paths: list[str] = [str(worktree_path), str(worktree_path.resolve())]

    if integration_base_path is not None:
        allow_paths.append(str(integration_base_path))
        allow_paths.append(str(integration_base_path.resolve()))

    tmpdir_value = os.environ.get("TMPDIR", "/tmp")
    for entry in OUT_OF_WORKTREE_ALLOW_WRITERS:
        expanded = entry.replace("$TMPDIR", tmpdir_value)
        expanded = os.path.expanduser(expanded)
        allow_paths.append(expanded)

    return allow_paths


def build_sandbox_settings_dict(
    deny_paths: list[str],
    allow_paths: list[str],
    soft_fail: bool,
) -> dict:
    """Build the canonical per-spawn sandbox-settings JSON dict.

    Single canonical builder used by both the orchestrator spawn (Req 2) and
    per-feature dispatch (Req 5). Emits the documented
    ``sandbox.filesystem.{denyWrite,allowWrite}`` JSON shape.

    Args:
        deny_paths: Absolute paths added to ``sandbox.filesystem.denyWrite``.
        allow_paths: Absolute paths added to ``sandbox.filesystem.allowWrite``.
        soft_fail: When ``True``, sets ``sandbox.failIfUnavailable: false``
            (kill-switch active per Req 4); when ``False``, sets
            ``sandbox.failIfUnavailable: true``.

    Returns:
        Dict with the spec Req 2 / Req 5 shape, ready for JSON serialization.
    """
    return {
        "sandbox": {
            "enabled": True,
            "failIfUnavailable": not soft_fail,
            "allowUnsandboxedCommands": False,
            "enableWeakerNestedSandbox": False,
            "enableWeakerNetworkIsolation": False,
            "filesystem": {
                "denyWrite": deny_paths,
                "allowWrite": allow_paths,
            },
        }
    }


def read_soft_fail_env() -> bool:
    """Read the ``CORTEX_SANDBOX_SOFT_FAIL`` env var at call time per Req 4.

    Re-read at every settings-builder invocation (orchestrator-spawn time AND
    each per-dispatch invocation); mid-session toggling affects only NEW
    spawns, not the orchestrator's own per-spawn settings JSON which is built
    once at orchestrator-spawn time.

    Returns:
        ``True`` if the env var is set to a truthy value; ``False`` otherwise.
    """
    value = os.environ.get(SOFT_FAIL_ENV_VAR, "")
    return value.strip().lower() in ("1", "true", "yes", "on")


def write_settings_tempfile(session_dir: Path, settings: dict) -> Path:
    """Write per-spawn settings JSON to a tempfile under ``<session_dir>/sandbox-settings/``.

    Uses ``cortex_command.common.atomic_write`` for the durable write, with
    mode ``0o600``, prefix ``cortex-sandbox-``, suffix ``.json`` per spec
    Req 1 and Req 11.

    Args:
        session_dir: The overnight session directory (per
            ``cortex_command/overnight/state.py`` session-scoping).
        settings: The dict produced by ``build_sandbox_settings_dict``.

    Returns:
        Absolute path to the created tempfile.
    """
    settings_dir = session_dir / SETTINGS_DIRNAME
    settings_dir.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(
        prefix=SETTINGS_TEMPFILE_PREFIX,
        suffix=SETTINGS_TEMPFILE_SUFFIX,
        dir=str(settings_dir),
    )
    # Close the FD immediately; we will write via atomic_write to honor the
    # tempfile + os.replace pattern from cortex_command/common.py:498-522.
    os.close(fd)

    tempfile_path = Path(tmp_path)
    atomic_write(tempfile_path, json.dumps(settings, indent=2))
    os.chmod(tempfile_path, stat.S_IRUSR | stat.S_IWUSR)  # 0o600

    return tempfile_path


def cleanup_stale_tempfiles(session_dir: Path, runner_start_ts: float) -> None:
    """Startup-scan: remove stale ``cortex-sandbox-*.json`` tempfiles.

    Handles SIGKILL / OOM / kernel-panic crash paths that bypass
    ``atexit`` cleanup. Removes any ``<session_dir>/sandbox-settings/cortex-sandbox-*.json``
    file whose mtime is older than ``runner_start_ts`` per spec Req 11. Pattern
    follows ``dashboard/app.py:237`` PID-file precedent.

    Args:
        session_dir: The overnight session directory.
        runner_start_ts: Unix timestamp captured at runner-init; tempfiles
            older than this are stale and removed.
    """
    settings_dir = session_dir / SETTINGS_DIRNAME
    if not settings_dir.exists():
        return

    pattern = f"{SETTINGS_TEMPFILE_PREFIX}*{SETTINGS_TEMPFILE_SUFFIX}"
    for stale in settings_dir.glob(pattern):
        try:
            mtime = stale.stat().st_mtime
        except OSError:
            continue
        if mtime < runner_start_ts:
            try:
                stale.unlink()
            except OSError:
                # Best-effort cleanup; ignore races and permission errors so
                # startup never crashes on stale-tempfile cleanup.
                pass


def register_atexit_cleanup(tempfile_path: Path) -> Callable[[], None]:
    """Register an ``atexit`` callback that removes ``tempfile_path`` on clean shutdown.

    Returns the registered callback so tests can invoke it directly without
    calling ``atexit._run_exitfuncs()`` (which would drain ALL process-level
    handlers including pytest-cov coverage finalizer + dashboard PID-file
    cleanup at ``dashboard/app.py:237``).

    Args:
        tempfile_path: Absolute path to the tempfile to remove on exit.

    Returns:
        The callback that was registered. Tests can call this directly to
        simulate clean shutdown without process-wide handler drainage.
    """
    target = Path(tempfile_path)

    def _cleanup() -> None:
        try:
            target.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            # Best-effort: never raise during interpreter shutdown.
            pass

    atexit.register(_cleanup)
    return _cleanup


# Module-level guard for one-shot Linux-warning emission. Initial state is
# ``False``; flipped to ``True`` on first emission. ``reset_linux_warning_latch``
# is a test-only helper that flips this back to its initial state so the
# ``test_linux_warning_emitted`` and ``test_macos_no_warning`` tests can run in
# any order without ordering coupling.
_LINUX_WARNING_EMITTED: bool = False


def reset_linux_warning_latch() -> None:
    """Test-only helper: reset the module-level Linux-warning emission flag.

    The Linux warning is emitted at most once per process via a module-level
    guard. This helper resets the guard so ``test_linux_warning_emitted`` and
    ``test_macos_no_warning`` can run in any order without ordering coupling.

    Not for production use.
    """
    global _LINUX_WARNING_EMITTED
    _LINUX_WARNING_EMITTED = False


def emit_linux_warning_if_needed(stream: TextIO = sys.stderr) -> None:
    """Emit ``LINUX_WARNING`` to stderr at most once per process when on Linux.

    Per spec Req 18, fires when ``sys.platform != "darwin"``. Observability-only;
    does NOT crash or exit. The orchestrator continues and the spec's other
    Reqs (settings tempfile, deny-set construction) execute as written.

    Args:
        stream: The text stream to write to (defaults to ``sys.stderr``;
            parameterized for test capture).
    """
    global _LINUX_WARNING_EMITTED
    if _LINUX_WARNING_EMITTED:
        return
    if sys.platform == "darwin":
        return
    print(LINUX_WARNING, file=stream)
    _LINUX_WARNING_EMITTED = True


def record_soft_fail_event(session_dir: Path) -> None:
    """Record a ``sandbox_soft_fail_active`` event in the session events.log.

    Writes the event under ``fcntl.LOCK_EX`` to prevent the
    read-then-conditional-write TOCTOU race under concurrent dispatch. Idempotent:
    if the event is already present, no second entry is written.

    Used by the morning-report builder (per spec Req 20) to emit the
    unconditional header line when the kill-switch was active at any point
    during the session.

    Args:
        session_dir: The overnight session directory containing ``events.log``.
    """
    session_dir.mkdir(parents=True, exist_ok=True)
    events_path = session_dir / "events.log"

    # Open for read+write+create (no truncation) so we can hold an exclusive
    # lock across the read-then-conditional-write. ``cortex_command.overnight.events.log_event``
    # does NOT take a lock, so we implement the lock locally per the task spec.
    fd = os.open(events_path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            # Read existing events to check for the idempotency sentinel.
            existing = b""
            chunk = os.read(fd, 65536)
            while chunk:
                existing += chunk
                chunk = os.read(fd, 65536)
            if b"sandbox_soft_fail_active" in existing:
                return

            entry = {
                "v": 1,
                "ts": datetime.now(timezone.utc).isoformat(),
                "event": "sandbox_soft_fail_active",
                "session_id": os.environ.get("LIFECYCLE_SESSION_ID", "manual"),
            }
            line = (json.dumps(entry) + "\n").encode("utf-8")
            # Append at end of file. Seek to end before writing to be explicit;
            # we hold LOCK_EX so no concurrent writer can interleave.
            os.lseek(fd, 0, os.SEEK_END)
            os.write(fd, line)
            os.fsync(fd)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
