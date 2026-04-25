"""Pre-install in-flight guard (R28).

This module aborts the ``cortex`` CLI entry point when a live overnight
runner is mid-session, so a concurrent ``uv tool install --reinstall
cortex-command`` cannot clobber the running package on disk mid-run.

The guard is invoked from :mod:`cortex_command.__init__` but must only
fire on *entry-point CLI invocations*; ``__init__.py`` also runs during
pytest collection, dashboard boot, runner-spawned children, and IDE
introspection, any of which would be broken by a blind abort. Five
carve-outs (first-match-wins) short-circuit the check:

1. ``"pytest" in sys.modules`` OR ``"PYTEST_CURRENT_TEST" in os.environ``
   — skip during pytest collection/run.
2. ``os.environ.get("CORTEX_RUNNER_CHILD") == "1"`` — skip in
   subprocesses spawned by the runner (orchestrator, batch_runner).
3. ``"uvicorn" in sys.argv[0]`` OR the dashboard module is the
   import-initiator — skip FastAPI boot so the dashboard can observe
   in-flight sessions.
4. ``CORTEX_ALLOW_INSTALL_DURING_RUN=1`` — explicit user opt-out.
5. Argparse pre-parse of ``sys.argv[1:]``: the cancel-bypass.
   ``overnight cancel <session_id> --force`` (any valid argparse
   ordering of positional/flag) returns immediately so the user can
   always clear a stale pointer even while the guard thinks a run is
   active.

A further guard narrowing is the **liveness check**: even with an
``active-session.json`` whose ``phase != "complete"``, the guard reads
the named session's ``runner.pid`` and calls
:func:`cortex_command.overnight.ipc.verify_runner_pid`. If the PID is
dead/missing/magic-mismatch, the active-session pointer is treated as
stale — the guard returns and emits a stderr warning recommending
``cortex overnight cancel <id> --force`` to clear the stale state. This
reuses the self-heal pattern at ``cli_handler.py:382-397`` so a crashed
runner cannot permanently lock out reinstalls.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Mirror of ``cortex_command.overnight.ipc.ACTIVE_SESSION_PATH``. We
# duplicate the path derivation rather than importing ``ipc`` because
# ``ipc`` transitively imports ``psutil`` at module load — and the guard
# runs from system-python invocations (e.g. ``python3
# backlog/update_item.py``) where ``psutil`` is not on sys.path. Pulling
# in ``ipc`` unconditionally turned the guard into a hard ImportError
# for every system-python entry point. The ``ipc`` import is now
# deferred to the live-runner branch where ``verify_runner_pid`` is
# actually called.
_ACTIVE_SESSION_PATH = (
    Path.home() / ".local" / "share" / "overnight-sessions" / "active-session.json"
)


class InstallInFlightError(SystemExit):
    """Raised when the guard fires — exits the process with code 1."""

    def __init__(self, message: str) -> None:
        # Write the user-facing message to stderr, then SystemExit(1).
        print(message, file=sys.stderr, flush=True)
        super().__init__(1)


# ---------------------------------------------------------------------------
# Cancel-bypass pre-parse
# ---------------------------------------------------------------------------

def _build_cancel_bypass_parser() -> argparse.ArgumentParser:
    """Build a minimal argparse parser that recognises only the
    ``cancel <session_id> --force`` form (after the ``overnight``
    subcommand token has been stripped by :func:`_is_cancel_force_invocation`).

    This is *not* the full ``cortex`` CLI parser; we deliberately keep
    it narrow so any other invocation silently falls through to the
    real check. The ``add_help=False`` + ``parse_known_args`` combo
    suppresses argparse's normal stderr/exit behaviour on unknown
    tokens so the guard can run in error-quiet mode against arbitrary
    ``sys.argv`` shapes (python -m forms, extra flags, etc.).
    """
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    subparsers = parser.add_subparsers(dest="verb")
    cancel = subparsers.add_parser("cancel", add_help=False)
    cancel.add_argument("session_id", nargs="?", default=None)
    cancel.add_argument("--force", action="store_true", default=False)
    cancel.add_argument("--session-dir", dest="session_dir", default=None)
    return parser


def _is_cancel_force_invocation(argv: list[str]) -> bool:
    """Return True when ``argv`` encodes ``overnight cancel ... --force``.

    Robust to all valid argparse orderings (``cancel <id> --force``,
    ``cancel --force <id>``, etc.) and to invocation forms like
    ``python -m cortex_command.cli ...`` because we first locate the
    ``overnight`` token in ``argv`` and parse only the tokens that
    follow. This side-steps argparse's strictness about what the
    top-level subparser's `choices` should be when the real argv is
    threaded through ``python -m`` or similar.
    """
    # Locate the ``overnight`` verb. All valid cancel-force invocations
    # have this token somewhere in argv; everything before it is
    # interpreter/launcher noise we can drop.
    try:
        idx = argv.index("overnight")
    except ValueError:
        return False

    tail = argv[idx + 1 :]
    if not tail:
        return False

    parser = _build_cancel_bypass_parser()
    try:
        ns, _unknown = parser.parse_known_args(tail)
    except SystemExit:
        return False
    except Exception:
        return False
    return (
        getattr(ns, "verb", None) == "cancel"
        and bool(getattr(ns, "force", False))
    )


# ---------------------------------------------------------------------------
# Dashboard import-initiator detection
# ---------------------------------------------------------------------------

def _is_dashboard_initiator() -> bool:
    """Return True when the dashboard (FastAPI/uvicorn) is booting.

    Two signals are checked:

    * ``sys.argv[0]`` contains ``uvicorn`` — covers the direct
      ``uvicorn cortex_command.dashboard.app:app`` launch.
    * The ``cortex_command.dashboard`` module is present on any frame
      of the current import stack — covers ``python -m
      cortex_command.dashboard`` and indirect imports of the dashboard
      entry point that might occur before argv reflects the reality.
    """
    argv0 = sys.argv[0] if sys.argv else ""
    if "uvicorn" in argv0:
        return True

    # If the dashboard module has already been imported, treat that as
    # the import-initiator. This is conservative — if anything else has
    # imported dashboard first, we still skip the guard — but dashboards
    # are the main rightful in-flight observer and this is the safer
    # default.
    if "cortex_command.dashboard" in sys.modules:
        return True
    if "cortex_command.dashboard.app" in sys.modules:
        return True

    return False


# ---------------------------------------------------------------------------
# Main guard entry point
# ---------------------------------------------------------------------------

def _check_in_flight_install_core() -> None:
    """Core guard logic.

    Separated from :func:`check_in_flight_install` so the guard's own
    tests can exercise every non-pytest carve-out and the main path
    from within a live pytest process, where the pytest carve-out
    would otherwise short-circuit immediately. Production code always
    calls :func:`check_in_flight_install` (which runs the pytest
    carve-out first).

    Carve-outs evaluated in order: (b) runner-child, (c) dashboard,
    (d) explicit opt-out, (e) cancel-force bypass. Then the main
    active-session + liveness check.
    """
    # (b) runner-child carve-out — subprocess inherited the env var from
    # a parent runner process. The runner sets this on every spawn of
    # batch_runner / orchestrator / smoke_test; see runner.py.
    if os.environ.get("CORTEX_RUNNER_CHILD") == "1":
        return

    # (c) dashboard carve-out — FastAPI/uvicorn boot must be able to
    # observe in-flight sessions.
    if _is_dashboard_initiator():
        return

    # (d) explicit user opt-out. Documented in the fail message:
    # PASS INLINE, do not `export` in the shell, because exporting
    # inherits into spawned children and silently re-disables R28
    # across the whole shell session.
    if os.environ.get("CORTEX_ALLOW_INSTALL_DURING_RUN") == "1":
        return

    # (e) cancel-bypass — a user mid-run must always be able to run
    # ``cortex overnight cancel <id> --force`` to clear a pointer.
    if _is_cancel_force_invocation(sys.argv[1:]):
        return

    # -------------------------------------------------------------------
    # Main check: read the active-session pointer directly. Defer the
    # ``ipc`` import (which pulls in psutil) until we actually need
    # ``verify_runner_pid`` — that way system-python invocations with
    # no overnight session in flight don't trip on a missing psutil.
    # -------------------------------------------------------------------
    if not _ACTIVE_SESSION_PATH.exists():
        return

    try:
        active = json.loads(_ACTIVE_SESSION_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return  # Unreadable / malformed — treat as absent.

    if not isinstance(active, dict):
        return

    phase = active.get("phase")
    if phase == "complete":
        return

    # Liveness check: even if phase != "complete", the active-session
    # pointer may be stale after a runner crash. Read the named session's
    # runner.pid and verify the recorded process is alive with the right
    # magic/start_time. If not, treat the pointer as stale — the guard
    # returns and recommends `cortex overnight cancel <id> --force` to
    # clear the stale state. (Same self-heal pattern as
    # cli_handler.py:382-397.)
    session_dir_str = active.get("session_dir")
    session_id = active.get("session_id", "<unknown>")
    if not isinstance(session_dir_str, str):
        return  # Malformed pointer — treat as stale.

    session_dir = Path(session_dir_str)
    runner_pid_path = session_dir / "runner.pid"
    if not runner_pid_path.exists():
        # Pointer references a session whose runner.pid is gone — stale.
        print(
            f"warning: stale active-session pointer for {session_id!r} "
            f"(runner.pid missing). Run "
            f"`cortex overnight cancel {session_id} --force` to clear.",
            file=sys.stderr,
            flush=True,
        )
        return

    try:
        pid_data = json.loads(runner_pid_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pid_data = None

    # Only now do we need psutil — defer the ``ipc`` import here so
    # absent / malformed paths don't pay it.
    from cortex_command.overnight import ipc

    if pid_data is None or not ipc.verify_runner_pid(pid_data):
        # Runner is dead/missing but pointer lingers. Warn and allow.
        print(
            f"warning: stale active-session pointer for {session_id!r} "
            f"(runner not alive). Run "
            f"`cortex overnight cancel {session_id} --force` to clear.",
            file=sys.stderr,
            flush=True,
        )
        return

    # Real, live in-flight runner — abort.
    raise InstallInFlightError(
        f"cortex: overnight session {session_id!r} is in-flight "
        f"(phase={phase!r}). Refusing to run to avoid clobbering the "
        f"running package mid-session.\n"
        f"\n"
        f"Options:\n"
        f"  - wait for the session to finish; OR\n"
        f"  - `cortex overnight cancel {session_id} --force` to stop it; OR\n"
        f"  - re-run prefixed with CORTEX_ALLOW_INSTALL_DURING_RUN=1 "
        f"(pass INLINE; do NOT `export` it — exported env vars are "
        f"inherited by spawned children and silently re-disable R28 "
        f"across the whole shell session).\n"
    )


def check_in_flight_install() -> None:
    """Abort if an overnight session is live and this looks like install-time.

    Carve-outs evaluated top-to-bottom; first match returns immediately.
    Called from ``cortex_command/__init__.py`` so every entry-point
    invocation funnels through — but the carve-outs are what make this
    safe to call unconditionally at import time.

    Order: (a) pytest, (b) runner-child, (c) dashboard, (d) explicit
    opt-out, (e) cancel-force bypass. Then the main active-session +
    liveness check.
    """
    # (a) pytest carve-out — must be first because pytest collection
    # imports the package transitively for every test module, and a
    # misfire here would break the entire test suite at collection.
    if "pytest" in sys.modules or "PYTEST_CURRENT_TEST" in os.environ:
        return

    _check_in_flight_install_core()
