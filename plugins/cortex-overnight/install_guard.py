"""Vendored sibling of cortex_command.install_guard.check_in_flight_install_core.

GENERATED FILE — DO NOT EDIT.

Regenerate via ``just sync-install-guard``. The canonical source-of-truth
is ``cortex_command/install_guard.py``. The ``.githooks/pre-commit`` parity
gate enforces byte-identity of the ``check_in_flight_install_core``
function source between this file and the canonical via
``just sync-install-guard --check``.

This sibling exists so the cortex-overnight plugin's PEP 723 venv
(stdlib + mcp + pydantic, no psutil) can honor R28's in-flight install
guard. Callers in this venv supply their own pid-verifier callable
(e.g., os.kill(pid, 0) + ``ps -p <pid> -o lstart=`` parse for macOS
recycled-pid semantics) instead of psutil-backed verification.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Callable, Optional


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
