"""Stdlib-only background-install healer for the cortex-core plugin.

Ported from ``plugins/cortex-overnight/install_core.py`` (see ADR-0026).
This module is invoked by the SessionStart-async hook
``hooks/cortex-cli-background-install.sh`` (canonical source, mirrored into
``plugins/cortex-core/hooks/`` by ``just build-plugin``) via a bare system
``python3`` heredoc that does::

    sys.path.insert(0, CLAUDE_PLUGIN_ROOT)
    import install_core
    install_core.run_install_in_background()

Because that loader gives the module only ``CLAUDE_PLUGIN_ROOT`` on
``sys.path`` — NOT the wheel's ``cortex_command`` package — this module MUST
be stdlib-only. No ``cortex_command.*``, no ``mcp``, ``pydantic``,
``fastmcp``, or ``packaging`` imports.

Scope note (ADR-0026 / spec R8): this healer only *initiates* an async
reinstall of the cortex-command wheel when the installed version drifts
behind the pin. It does NOT guarantee the wheel matches by the time any
lifecycle verb runs this session. The correctness boundary remains the
per-verb protocol detect-and-halt (spec R7/R11; Tasks 13/19), NOT this
healer.

Deliberate divergences from the cortex-overnight port (documented in
ADR-0026):

* No in-flight-session guard. The overnight guard tracks *runner* sessions
  (``~/.local/share/overnight-sessions/active-session.json``); it has no
  awareness of interactive Claude Code sessions, so porting it would give
  false assurance. Concurrent initiation is instead made benign by the
  install flock plus ``uv tool install --reinstall`` idempotency, and the
  correctness boundary is explicitly the per-verb check, not any guard.
* No NDJSON forensics log. The overnight module's ``last-error.log`` audit
  trail is consumed by its companion version-sync hook (R25); cortex-core
  has no such companion. Failures instead write a ``session-install-failed``
  sentinel (skip predicate 3) so the next session throttles, and
  ``run_install_in_background`` returns a structured outcome for callers and
  tests.
* Four skip predicates only (``CORTEX_AUTO_INSTALL=0``, probe failure,
  failure sentinel, install-in-progress marker) — the overnight
  ``CORTEX_DEV_MODE``/dirty-tree/non-main-branch predicates are not ported.
"""

from __future__ import annotations

import errno
import fcntl
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# CLI version pin
# ---------------------------------------------------------------------------

#: The git tag this plugin heals the installed wheel toward, and the
#: print-root JSON schema major it expects. Mirrors
#: ``plugins/cortex-overnight/cli_pin.py``; the two plugin pins are bumped
#: together at release. Inlined here (rather than a sibling ``cli_pin.py``)
#: because cortex-core has no ``server.py`` that also needs to import it, so
#: a single in-module constant is the leaner home. Tests monkeypatch this
#: symbol to drive the drift comparison.
CLI_PIN = ("v2.37.0", "2.0")


# ---------------------------------------------------------------------------
# Confused-deputy guard (mirrors server.py:_enforce_plugin_root)
# ---------------------------------------------------------------------------


def _enforce_plugin_root() -> None:
    """Refuse to run unless this file lives under ``$CLAUDE_PLUGIN_ROOT``.

    Confused-deputy mitigation: an attacker who can override
    ``CLAUDE_PLUGIN_ROOT`` must not be able to point the bare-``python3``
    loader at arbitrary Python. On mismatch (or absent env var), raise
    ``SystemExit(1)``; the hook's bash trampoline suppresses it and exits 0.

    Called at the top of :func:`run_install_in_background` rather than at
    import time so unit tests can import the module and exercise the
    predicate helpers directly.
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


# ---------------------------------------------------------------------------
# Stdlib version-tuple helper (no ``packaging`` import)
# ---------------------------------------------------------------------------


def version_tuple(v: Optional[str]) -> tuple[int, ...]:
    """Convert ``vX.Y.Z`` (or ``X.Y.Z``) to an int tuple, PEP 440 prefix.

    Bare-semver only: non-numeric segments truncate. The cortex-command
    release process emits bare ``vX.Y.Z`` tags; a non-semver suffix is a
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
# Constants
# ---------------------------------------------------------------------------

#: Wait budget (seconds) for the cross-process install flock.
_INSTALL_FLOCK_WAIT_BUDGET_SECONDS = 60.0

#: Polling interval (seconds) for the non-blocking flock acquisition loop.
_INSTALL_FLOCK_POLL_INTERVAL_SECONDS = 0.1

#: Timeout (seconds) for the ``cortex --print-root --format json`` probe.
_INSTALL_VERIFY_TIMEOUT_SECONDS = 10.0

#: Window (seconds) during which a recent ``session-install-failed.<ts>``
#: sentinel short-circuits a re-attempt (skip predicate 3). 30 minutes so a
#: persistent failure does not loop on every new session.
_SESSION_INSTALL_SENTINEL_WINDOW_SECONDS = 1800.0

#: Freshness ceiling (seconds) for the ``install.in-progress`` marker (skip
#: predicate 4). A marker older than this is treated as stale (its owning
#: process was SIGKILL/OOM-killed before its ``finally`` ran) and ignored.
_INSTALL_MARKER_STALE_SECONDS = 600.0


# ---------------------------------------------------------------------------
# Skip predicate 1 — CORTEX_AUTO_INSTALL=0
# ---------------------------------------------------------------------------


def is_auto_install_disabled() -> bool:
    """Return ``True`` when ``CORTEX_AUTO_INSTALL=0`` is set (per-user opt-out).

    Resolved fresh on each call so tests can flip the env var via
    ``monkeypatch``.
    """
    return os.environ.get("CORTEX_AUTO_INSTALL") == "0"


# ---------------------------------------------------------------------------
# State-dir helpers
# ---------------------------------------------------------------------------


def _install_state_dir() -> Path:
    """Return ``${XDG_STATE_HOME:-$HOME/.local/state}/cortex-command``.

    Shared with the cortex-overnight install path so both plugins serialize
    on the same install flock and read/write the same marker + sentinels.
    Resolved fresh on each call so tests can redirect ``HOME`` /
    ``XDG_STATE_HOME`` via ``monkeypatch``.
    """
    xdg_state = os.environ.get("XDG_STATE_HOME")
    if xdg_state:
        base = Path(xdg_state)
    else:
        base = Path(os.environ.get("HOME", str(Path.home()))) / ".local" / "state"
    return base / "cortex-command"


def _install_lock_path() -> Path:
    """Return the shared install-lock path under XDG state home."""
    return _install_state_dir() / "install.lock"


def _install_in_progress_marker_path() -> Path:
    """Return ``${XDG_STATE_HOME}/cortex-command/install.in-progress``.

    Zero-byte marker written under the install flock immediately before the
    detached ``uv tool install`` is spawned and unlinked in the ``finally``.
    Its mtime is the freshness signal read by skip predicate 4.
    """
    return _install_state_dir() / "install.in-progress"


# ---------------------------------------------------------------------------
# Skip predicate 3 — recent session-install-failed sentinel
# ---------------------------------------------------------------------------


def _recent_session_install_failed_sentinel() -> Optional[Path]:
    """Return a fresh ``session-install-failed.*`` sentinel path, or ``None``.

    "Fresh" means mtime within
    :data:`_SESSION_INSTALL_SENTINEL_WINDOW_SECONDS` of now. Returns the most
    recent qualifying sentinel so the caller can surface its context.
    """
    state_dir = _install_state_dir()
    if not state_dir.is_dir():
        return None
    cutoff = time.time() - _SESSION_INSTALL_SENTINEL_WINDOW_SECONDS
    candidates: list[tuple[float, Path]] = []
    try:
        for entry in state_dir.iterdir():
            if not entry.name.startswith("session-install-failed."):
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


def _write_session_install_failed_sentinel(error: str) -> Path:
    """Create ``${XDG_STATE_HOME}/cortex-command/session-install-failed.<ts>``.

    Best-effort: directory-creation and write failures are swallowed; the
    would-be path is returned regardless.
    """
    state_dir = _install_state_dir()
    sentinel_path = state_dir / f"session-install-failed.{int(time.time())}"
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        sentinel_path.write_text(error, encoding="utf-8")
    except OSError as exc:
        print(
            f"cortex-core install: failed to write session-install-failed "
            f"sentinel ({exc.__class__.__name__}: {exc}); continuing",
            file=sys.stderr,
        )
    return sentinel_path


# ---------------------------------------------------------------------------
# Skip predicate 4 — install-in-progress marker freshness
# ---------------------------------------------------------------------------


def _install_in_progress() -> bool:
    """Return ``True`` when a fresh ``install.in-progress`` marker exists.

    A concurrent hook (either plugin's) is mid-spawn. A marker older than
    :data:`_INSTALL_MARKER_STALE_SECONDS` is stale and ignored.
    """
    marker_path = _install_in_progress_marker_path()
    try:
        mtime = marker_path.stat().st_mtime
    except OSError:
        return False
    return (time.time() - mtime) < _INSTALL_MARKER_STALE_SECONDS


# ---------------------------------------------------------------------------
# Install flock (shared with the overnight path)
# ---------------------------------------------------------------------------


def _acquire_install_flock(lock_path: Path) -> Optional[int]:
    """Acquire ``fcntl.flock(LOCK_EX)`` on ``lock_path`` with a 60s budget.

    Non-blocking poll so the wait budget is enforced cooperatively. Returns
    the open fd on success, or ``None`` on budget expiry.
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


# ---------------------------------------------------------------------------
# Version probe (skip predicate 2)
# ---------------------------------------------------------------------------


def _probe_installed_version() -> Optional[str]:
    """Return the installed cortex version string, or ``None`` on any failure.

    Skip predicate 2: binary absent, non-zero exit, non-JSON stdout, or a
    payload without a string ``version`` all yield ``None`` — drift cannot
    be computed, so the caller silent-skips (mirrors the loop's warn-only
    no-install posture).
    """
    try:
        result = subprocess.run(
            ["cortex", "--print-root", "--format", "json"],
            timeout=_INSTALL_VERIFY_TIMEOUT_SECONDS,
            capture_output=True,
            text=True,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    version = payload.get("version")
    if not isinstance(version, str):
        return None
    return version


# ---------------------------------------------------------------------------
# Initiate path
# ---------------------------------------------------------------------------


def _install_argv() -> list[str]:
    """Return the ``uv tool install --reinstall`` argv pinned to ``CLI_PIN``."""
    return [
        "uv",
        "tool",
        "install",
        "--reinstall",
        "--refresh-package",
        "cortex-command",
        f"git+https://github.com/charleshall888/cortex-command.git@{CLI_PIN[0]}",
    ]


def run_install_in_background(*, dry_run: Optional[bool] = None) -> dict[str, Any]:
    """Initiate a detached background reinstall of the cortex wheel on drift.

    Entry point invoked by ``hooks/cortex-cli-background-install.sh`` at
    SessionStart. Consults four skip predicates in order (each silent-skips),
    compares the installed version against :data:`CLI_PIN`, and on drift
    spawns a detached ``uv tool install --reinstall`` under the install
    flock.

    Skip predicates (spec R8 / ADR-0026), cheapest first:

    1. ``CORTEX_AUTO_INSTALL=0`` — per-user opt-out.
    2. Probe failure — ``cortex --print-root --format json`` absent, non-zero,
       or non-JSON; drift cannot be computed.
    3. Recent ``session-install-failed.<ts>`` sentinel within 30 min.
    4. Fresh ``install.in-progress`` marker — a concurrent initiate is
       mid-spawn.

    ``dry_run`` (or ``CORTEX_INSTALL_DRY_RUN=1`` when the argument is
    ``None``) runs every predicate and the drift comparison but stops short
    of the ``uv`` spawn and marker write, returning the argv it *would* run.
    This is the CI-exercisable initiate path — no real install runs in CI.

    Returns a structured outcome dict ``{"action": <str>, "reason"/... }``.
    The hook ignores the return; tests assert on it. Honest semantics: an
    ``"initiated"`` outcome means the async reinstall was *spawned*, not that
    the wheel already matches — the per-verb check remains the correctness
    boundary.
    """
    _enforce_plugin_root()

    if dry_run is None:
        dry_run = os.environ.get("CORTEX_INSTALL_DRY_RUN") == "1"

    # (1) CORTEX_AUTO_INSTALL=0 — per-user opt-out.
    if is_auto_install_disabled():
        return {"action": "skipped", "reason": "auto_install_disabled"}

    # (2) Probe failure — drift cannot be computed.
    installed_version = _probe_installed_version()
    if installed_version is None:
        return {"action": "skipped", "reason": "probe_failure"}

    # (3) Recent session-install-failed sentinel throttle.
    sentinel = _recent_session_install_failed_sentinel()
    if sentinel is not None:
        return {
            "action": "skipped",
            "reason": "recent_failure_sentinel",
            "sentinel": str(sentinel),
        }

    # (4) Install already in progress (fresh marker).
    if _install_in_progress():
        return {"action": "skipped", "reason": "install_in_progress"}

    # Drift comparison.
    target_version = CLI_PIN[0].lstrip("v")
    if version_tuple(installed_version) == version_tuple(target_version):
        return {
            "action": "noop",
            "reason": "no_drift",
            "installed_version": installed_version,
        }

    argv = _install_argv()

    # Dry-run initiate path — report the action without spawning (CI-safe).
    if dry_run:
        return {
            "action": "initiated",
            "dry_run": True,
            "installed_version": installed_version,
            "target": CLI_PIN[0],
            "argv": argv,
        }

    # Acquire the shared install flock (60s budget).
    lock_path = _install_lock_path()
    fd = _acquire_install_flock(lock_path)
    if fd is None:
        return {"action": "skipped", "reason": "flock_timeout"}

    marker_path = _install_in_progress_marker_path()
    marker_written = False
    spawn_error: Optional[str] = None
    try:
        # Write the zero-byte in-progress marker under the lock.
        try:
            marker_path.parent.mkdir(parents=True, exist_ok=True)
            with open(marker_path, "w", encoding="utf-8"):
                pass
            marker_written = True
        except OSError as exc:
            # Marker write failed; proceed with the spawn anyway — the marker
            # is an advisory signal, not a correctness gate.
            spawn_error = f"marker_write_failed: {exc.__class__.__name__}: {exc}"

        # Spawn the detached install. ``start_new_session=True`` puts the
        # child in its own session so the hook script exits in ~ms while the
        # network-bound install runs on. Output is discarded (no NDJSON
        # companion in cortex-core); failure surfaces via the sentinel below.
        try:
            subprocess.Popen(
                argv,
                start_new_session=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env={**os.environ, "UV_NO_PROGRESS": "1"},
            )
        except OSError as exc:
            spawn_error = f"{exc.__class__.__name__}: {exc}"
            sentinel_path = _write_session_install_failed_sentinel(spawn_error)
            return {
                "action": "failed",
                "reason": "spawn_failure",
                "error": spawn_error,
                "sentinel": str(sentinel_path),
            }
    finally:
        if marker_written:
            try:
                os.unlink(marker_path)
            except OSError:
                pass
        _release_install_flock(fd)

    return {
        "action": "initiated",
        "dry_run": False,
        "installed_version": installed_version,
        "target": CLI_PIN[0],
        "argv": argv,
    }
