"""Pre-install in-flight guard (R28).

This module aborts the ``cortex upgrade`` CLI dispatch path when a live
overnight runner is mid-session, so a concurrent ``uv tool install
--reinstall cortex-command`` cannot clobber the running package on disk
mid-run.

The guard is invoked **only** from the install-mutation dispatch path
(:func:`cortex_command.cli._dispatch_upgrade`), not on package import.
This makes ``import cortex_command`` (and read-only entry points such
as ``cortex overnight status``) safe to execute while a runner is
alive, and it removes the need for blanket import-time carve-outs
(pytest collection, dashboard boot, runner-spawned children, IDE
introspection). Future maintainers introducing a new
install-mutation entry point must call :func:`check_in_flight_install`
explicitly from that handler.

Two carve-outs (first-match-wins) remain on the upgrade path itself:

1. ``CORTEX_ALLOW_INSTALL_DURING_RUN=1`` — explicit user opt-out.
   Pass INLINE; do not ``export`` it, because exporting inherits into
   spawned children and silently re-disables R28 across the whole
   shell session.
2. Argparse pre-parse of ``sys.argv[1:]``: the cancel-bypass.
   ``overnight cancel <session_id> --force`` (any valid argparse
   ordering) returns immediately so the user can always clear a stale
   pointer.

A further guard narrowing is the **liveness check**: even with an
``active-session.json`` whose ``phase != "complete"``, the guard reads
the named session's ``runner.pid`` and calls
:func:`cortex_command.overnight.ipc.verify_runner_pid`. If the PID is
dead/missing/magic-mismatch, the active-session pointer is treated as
stale — the guard returns and emits a stderr warning recommending
``cortex overnight cancel <id> --force``. This reuses the self-heal
pattern at ``cli_handler.py:382-397`` so a crashed runner cannot
permanently lock out reinstalls.

Architecture: the active-session.json read + liveness check logic
lives in :func:`check_in_flight_install_core` — a stdlib-only function
that takes the active-session path, a pid-verifier callable, and a
``now`` callable (defaulting to ``time.time``) as parameters. The
``now`` parameter exists purely to enable deterministic tests. The
core is vendored byte-identically into
``plugins/cortex-overnight/install_guard.py`` (enforced by
``.githooks/pre-commit`` + ``just sync-install-guard``) so the
plugin's PEP 723 venv — which deliberately has no psutil dependency —
can honor R28 by supplying its own pid-verifier callable. The
CLI-specific carve-outs (``CORTEX_ALLOW_INSTALL_DURING_RUN``,
argparse cancel-bypass) live in the wrapper :func:`check_in_flight_install`,
NOT in the core, because those are dispatch-path concerns that do not
apply to MCP-tool-call-gated paths.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Callable, Optional

# Mirror of ``cortex_command.overnight.ipc.ACTIVE_SESSION_PATH``. We
# duplicate the path derivation rather than importing ``ipc`` because
# ``ipc`` transitively imports ``psutil`` at module load — and the guard
# may be called from environments where ``psutil`` is not on sys.path.
# The ``ipc`` import is deferred to the live-runner branch where
# ``verify_runner_pid`` is actually called.
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
# Core guard logic — stdlib-only, vendored to plugins/cortex-overnight/
# ---------------------------------------------------------------------------
# BEGIN sync-install-guard:check_in_flight_install_core
def check_in_flight_install_core(
    active_session_path: Path,
    pid_verifier: Callable[[dict], bool],
    now: Callable[[], float] = time.time,
) -> Optional[str]:
    """Return a reason-string when an in-flight install must be blocked, else None.

    Stdlib-only. The ``pid_verifier`` callable AND the ``now`` callable
    are parameters to preserve the stdlib-only contract: callers in the
    CLI (psutil available) and in the plugin's PEP 723 venv (no psutil)
    each supply an appropriate pid-verifier. ``now`` enables
    deterministic tests.

    Returns:
        ``None`` when the active-session pointer is absent, malformed,
        complete, or stale (with a stderr self-heal warning in the
        stale cases). A non-empty reason-string when a live in-flight
        runner is detected and the caller must abort.

    This function is vendored byte-identically into
    ``plugins/cortex-overnight/install_guard.py`` via
    ``just sync-install-guard``; the ``.githooks/pre-commit`` parity
    gate enforces source identity. Do not edit the vendored sibling
    directly — edit this function and regenerate.

    The ``now`` parameter is unused in the current logic but reserved
    for time-windowed decisions (e.g., stale-pointer TTL). It is part
    of the signature so future additions remain stdlib-only.
    """
    _ = now  # reserved for future use (e.g., stale-pointer TTL)

    if not active_session_path.exists():
        return None

    try:
        active = json.loads(active_session_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None  # Unreadable / malformed — treat as absent.

    if not isinstance(active, dict):
        return None

    phase = active.get("phase")
    if phase == "complete":
        return None

    # Liveness check: even if phase != "complete", the active-session
    # pointer may be stale after a runner crash. Read the named session's
    # runner.pid and call the supplied pid_verifier. If not alive,
    # treat the pointer as stale — return None and emit a stderr
    # warning recommending `cortex overnight cancel <id> --force`.
    session_dir_str = active.get("session_dir")
    session_id = active.get("session_id", "<unknown>")
    if not isinstance(session_dir_str, str):
        return None  # Malformed pointer — treat as stale.

    session_dir = Path(session_dir_str)
    runner_pid_path = session_dir / "runner.pid"
    if not runner_pid_path.exists():
        print(
            f"warning: stale active-session pointer for {session_id!r} "
            f"(runner.pid missing). Run "
            f"`cortex overnight cancel {session_id} --force` to clear.",
            file=sys.stderr,
            flush=True,
        )
        return None

    try:
        pid_data = json.loads(runner_pid_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pid_data = None

    if pid_data is None or not pid_verifier(pid_data):
        # Runner is dead/missing but pointer lingers. Warn and allow.
        print(
            f"warning: stale active-session pointer for {session_id!r} "
            f"(runner not alive). Run "
            f"`cortex overnight cancel {session_id} --force` to clear.",
            file=sys.stderr,
            flush=True,
        )
        return None

    # Real, live in-flight runner — block.
    return (
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
# END sync-install-guard:check_in_flight_install_core


# ---------------------------------------------------------------------------
# CLI-side wrapper: carve-outs + psutil-backed pid_verifier
# ---------------------------------------------------------------------------

def _cli_pid_verifier(pid_data: dict) -> bool:
    """psutil-backed pid verifier — defers the ipc import to keep
    stdlib-only callers (e.g., absent-session paths) from paying it.
    """
    # Defer the ``ipc`` import (which pulls in psutil) until we actually
    # need ``verify_runner_pid``.
    from cortex_command.overnight import ipc
    return ipc.verify_runner_pid(pid_data)


def check_in_flight_install() -> None:
    """Abort if an overnight session is live and this is an install-mutation path.

    Carve-outs evaluated top-to-bottom; first match returns immediately:

    1. ``CORTEX_ALLOW_INSTALL_DURING_RUN=1`` — explicit user opt-out.
    2. ``overnight cancel <id> --force`` cancel-bypass.

    Then delegates to :func:`check_in_flight_install_core` for the
    active-session + liveness check. If the core returns a non-None
    reason-string, raise :class:`InstallInFlightError`.
    """
    # (1) explicit user opt-out. PASS INLINE; do not `export` in the
    # shell, because exporting inherits into spawned children and
    # silently re-disables R28 across the whole shell session.
    if os.environ.get("CORTEX_ALLOW_INSTALL_DURING_RUN") == "1":
        return

    # (2) cancel-bypass — a user mid-run must always be able to run
    # ``cortex overnight cancel <id> --force`` to clear a pointer.
    if _is_cancel_force_invocation(sys.argv[1:]):
        return

    reason = check_in_flight_install_core(
        _ACTIVE_SESSION_PATH,
        pid_verifier=_cli_pid_verifier,
    )
    if reason is not None:
        raise InstallInFlightError(reason)
