"""Out-of-process overnight-runner supervision (spec §Phase 1).

Every existing liveness/recovery primitive (the in-process
``WatchdogThread``, signal-driven ``_cleanup``, the descendant-tree
reaper) lives *inside* the runner process and fires only from its control
flow or a delivered signal. When the runner itself dies hard
(SIGKILL/OOM) or its event loop wedges, nothing out-of-process detects it
and the session stays stuck in ``phase: executing`` with no live runner,
no morning report, and orphaned workers — the failure class behind #308.

This module is the out-of-process supervision layer that sits *above* the
file-based state/ipc/report primitives. It grows in later tasks to add the
recovery core, the orphan reaper, and the wedged-runner staleness
predicate; this first piece is the false-positive-free *detection*
predicate.

Detection predicate (spec §R1, Phase 1)
---------------------------------------
:func:`needs_recovery_pid_death` is a pure, read-only predicate that flags
a session for recovery iff its on-disk ``phase`` is ``"executing"`` AND
the recorded session-leader ``runner.pid`` is no longer alive
(``ipc.verify_runner_pid`` is ``False``). This is the symmetric
*mid-round-loop* counterpart to :func:`fail_markers._advisory_is_stale`'s
*pre-round-loop* escalation — minus the age term, because a dead runner's
pid is dead immediately. The signal cannot false-positive on healthy work:
a live runner's pid is always alive. It deliberately does NOT key on
event-log staleness — that is the alive-but-wedged Phase 2 signal, which
is unsafe until the planning-phase heartbeat blind window is closed.

This module performs no writes.
"""

from __future__ import annotations

from pathlib import Path

from cortex_command.overnight import status
from cortex_command.overnight.fail_markers import _session_phase


def needs_recovery_pid_death(session_dir: Path) -> bool:
    """Return ``True`` iff a session needs pid-death recovery (spec §R1).

    Flags the session iff BOTH:

      1. its on-disk ``phase`` (``overnight-state.json``'s ``phase``
         field, read via :func:`fail_markers._session_phase`) is
         ``"executing"``, AND
      2. its recorded session-leader ``runner.pid`` is not alive —
         :func:`status._is_runner_pid_live` is ``False`` (the file is
         absent, the payload is malformed, or the recorded process is
         gone; ``verify_runner_pid`` matches ``create_time`` ±2s so PID
         reuse is defended).

    This cannot false-positive on healthy work: a live runner's pid is
    always alive, so an ``executing`` session with a live pid returns
    ``False``. A session in any other phase (``paused``/``complete``/
    ``planning``/``starting``/missing) returns ``False`` regardless of pid
    liveness. It does NOT key on event-log staleness — that alive-but-
    wedged signal is Phase 2.

    Purely read-only: this function never writes state.
    """
    if _session_phase(session_dir) != "executing":
        return False
    return not status._is_runner_pid_live(session_dir)
