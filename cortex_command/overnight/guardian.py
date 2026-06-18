"""Out-of-process guardian scan entrypoint (spec §R6, Phase 1).

The persistent host-level launchd guardian (its launchd plumbing lands in a
later task) periodically scans *all* ``executing`` overnight sessions and
recovers any whose runner has died — the out-of-process detector for the
case the in-process ``WatchdogThread`` structurally cannot handle (a runner
that died hard or wedged cannot supervise its own host's death).

This module is the scan entrypoint that guardian invokes. It holds **no
recovery logic of its own**: it enumerates session dirs under the state
root, applies the unified :func:`recovery.needs_recovery` predicate (the
disjunction of the pid-death and alive-but-wedged signals), and calls the
existing :func:`recovery.recover_session` (``trigger="guardian"``) for each
session that needs it. Healthy sessions are left untouched.

Per-session failure isolation (spec §R6, the load-bearing invariant here)
--------------------------------------------------------------------------
A single persistent agent scans ALL sessions, so one poison session must
not starve its co-resident stuck sessions. Each session's
predicate+recover is wrapped in its own ``try``/``except``: an exception on
one session — a malformed ``overnight-state.json``, an un-swallowed
``AccessDenied`` from the reaper, or a
:class:`ipc.ConcurrentRunnerLockTimeoutError` surfacing out of
:func:`recovery.recover_session`'s 5s takeover-lock budget — is recorded as
that session's :class:`RecoveryResult` (``action == "error"``) and the scan
continues to the remaining sessions. The scan is cheap, idempotent (each
session is already guarded by the takeover lock + the
``recovery-complete.json`` sidecar), and continue-on-error per session.
"""

from __future__ import annotations

import sys
from pathlib import Path

from cortex_command.overnight import recovery
from cortex_command.overnight.recovery import RecoveryResult


def _session_dirs(state_root: Path) -> list[Path]:
    """Return the per-session dirs under ``state_root`` (``sessions/*/``).

    Mirrors the ``report``/``status`` enumeration shape
    (``cortex/lifecycle/sessions/*/``) — globs ``sessions/*`` and keeps only
    real directories holding an ``overnight-state.json``, skipping symlink
    entries (e.g. the ``latest-overnight`` pointer) so a linked target is not
    double-scanned. A missing ``sessions/`` subdir yields an empty list.
    """
    sessions_root = state_root / "sessions"
    if not sessions_root.is_dir():
        return []
    dirs: list[Path] = []
    for entry in sorted(sessions_root.glob("*")):
        if entry.is_symlink():
            continue
        if not entry.is_dir():
            continue
        if not (entry / "overnight-state.json").exists():
            continue
        dirs.append(entry)
    return dirs


def scan_and_recover(state_root: Path) -> list[RecoveryResult]:
    """Scan all ``executing`` sessions under ``state_root`` and recover the dead.

    This is the guardian's scan entrypoint (spec §R6) and is also reachable
    by an operator via ``cortex overnight guardian scan``. It holds no
    recovery logic of its own: for each enumerated session dir it applies the
    unified :func:`recovery.needs_recovery` predicate (pid-death OR
    alive-but-wedged) and, when the predicate fires, invokes
    :func:`recovery.recover_session` with ``trigger="guardian"``. Healthy
    sessions (live pid with a fresh heartbeat, or any phase other than
    ``executing``) are left untouched and produce no result entry.

    **Per-session failure isolation.** Each session's predicate+recover runs
    in its own ``try``/``except`` so a single poison session cannot abort the
    scan. An exception on one session is captured as that session's
    :class:`RecoveryResult` with ``action == "error"`` and the scan proceeds
    to the next session. This guarantees a stuck session is recovered whether
    it is enumerated before or after a poison session.

    Args:
        state_root: The lifecycle state root holding a ``sessions/``
            subdirectory (``cortex/lifecycle``). Each candidate session is
            ``state_root/sessions/{session_id}``.

    Returns:
        A list of :class:`RecoveryResult` — one per session that needed
        recovery (``action`` ``"recovered"``/``"noop"``) or that raised
        during its predicate+recover (``action == "error"``). Healthy
        sessions that did not need recovery contribute no entry.
    """
    results: list[RecoveryResult] = []
    for session_dir in _session_dirs(state_root):
        try:
            if not recovery.needs_recovery(session_dir):
                continue
            results.append(recovery.recover_session(session_dir, trigger="guardian"))
        except Exception as exc:  # noqa: BLE001 — per-session isolation is the contract
            # One poison session (malformed state, un-swallowed AccessDenied,
            # or a lock-timeout surfacing out of recover_session) must not
            # starve co-resident stuck sessions: record the failure and keep
            # scanning. session_id is best-effort — derive it from the dir name
            # since the state load may be the thing that failed. The failure
            # text is attached as an ``error`` attribute on the result (the
            # error/skipped entry the spec allows); ``RecoveryResult`` has no
            # ``error`` field of its own, so guardian sets it post-construction
            # rather than reaching into the recovery module's dataclass.
            error_result = RecoveryResult(
                session_id=session_dir.name,
                action="error",
                trigger="guardian",
            )
            error_result.error = f"{type(exc).__name__}: {exc}"
            results.append(error_result)
    return results


# ---------------------------------------------------------------------------
# Persistent guardian install / remove (spec §R6, Task 10)
#
# These wire the scan entrypoint above to its AUTOMATIC trigger: a SINGLE
# host-level launchd LaunchAgent on a ``StartInterval`` cadence that invokes
# ``cortex overnight guardian scan`` every tick. One agent for the whole host
# (NOT per-session) avoids the install/GC-per-session problem. The launchd
# plumbing lives in :mod:`cortex_command.overnight.scheduler.macos`; these
# helpers gate on macOS support and delegate.
# ---------------------------------------------------------------------------


class GuardianUnsupportedError(Exception):
    """Raised when guardian install/remove is attempted off macOS.

    The persistent guardian is a launchd LaunchAgent — macOS-only. The
    manual ``cortex overnight recover`` verb and ``cortex overnight guardian
    scan`` remain available cross-platform; only the persistent installer is
    macOS-bound.
    """


def install_guardian(repo_root: Path) -> Path:
    """Install the single persistent host-level guardian LaunchAgent.

    Renders a ``StartInterval``-cadence plist (fixed host-level label, no
    per-session minting, no launcher shim) whose ``ProgramArguments`` invoke
    ``cortex overnight guardian scan`` against ``repo_root``, then bootstraps
    it via ``launchctl``. Re-install replaces a prior registration (idempotent).

    Args:
        repo_root: The user repo whose ``cortex/lifecycle/sessions/`` the
            installed guardian scans (threaded via ``CORTEX_REPO_ROOT``).

    Returns:
        The path of the written guardian plist.

    Raises:
        GuardianUnsupportedError: when run off macOS.
    """
    if sys.platform != "darwin":
        raise GuardianUnsupportedError(
            "the persistent guardian is a macOS launchd LaunchAgent; "
            "use 'cortex overnight recover' or a scheduled "
            "'cortex overnight guardian scan' on other platforms"
        )
    from cortex_command.overnight.scheduler import macos

    return macos.install_guardian(repo_root=repo_root)


def remove_guardian() -> bool:
    """Bootout and unlink the persistent guardian LaunchAgent.

    A clean no-op when the guardian is not installed (bootout on an
    unregistered label is non-fatal; the plist unlink tolerates an absent
    file).

    Returns:
        ``True`` if the guardian plist was removed, ``False`` if it was
        already absent.

    Raises:
        GuardianUnsupportedError: when run off macOS.
    """
    if sys.platform != "darwin":
        raise GuardianUnsupportedError(
            "the persistent guardian is a macOS launchd LaunchAgent; "
            "there is nothing to remove on other platforms"
        )
    from cortex_command.overnight.scheduler import macos

    return macos.remove_guardian()
