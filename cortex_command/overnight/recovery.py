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

from dataclasses import dataclass, field
from pathlib import Path

import psutil

from cortex_command.overnight import status
from cortex_command.overnight.fail_markers import _session_phase
from cortex_command.overnight.runner import DESCENDANT_GRACEFUL_SHUTDOWN_SECONDS


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


# ---------------------------------------------------------------------------
# Env-match orphan reaper (spec §R5, Phase 1)
# ---------------------------------------------------------------------------

#: The env var the runner sets at its two spawn sites (orchestrator
#: ``runner.py:1247``, batch_runner ``:1458``) and inherits to every
#: descendant. It is the **load-bearing identity discriminator**: only
#: runner-spawned children carry it. ``LIFECYCLE_SESSION_ID`` alone is NOT
#: sufficient — it is also exported into ordinary interactive Claude Code
#: sessions in a cortex repo (SessionStart hook / ``CLAUDE_ENV_FILE``), so an
#: operator's interactive ``claude`` session on the same feature legitimately
#: carries it. Selection keeps the AND of both markers; collapsing it to a
#: session-id-only match would broad-match (and kill) operator sessions.
_RUNNER_CHILD_MARKER = "CORTEX_RUNNER_CHILD"
_SESSION_ID_MARKER = "LIFECYCLE_SESSION_ID"

#: Bound on the enumerate→signal fixpoint loop. A matched worker can fork a
#: fresh child *during* the grace window; re-enumerating after each grace
#: window catches it. The loop terminates early when a pass finds zero
#: matched pids; otherwise it stops at this cap and surfaces any still-matched
#: pids as ``unreaped`` rather than spinning unboundedly.
_REAP_FIXPOINT_MAX_PASSES = 3


@dataclass
class ReapOutcome:
    """Outcome of an env-match orphan reap (spec §R5).

    Counts and pid lists for the processes a reap pass touched:

    * ``matched`` — pids selected by the AND of both env markers across all
      fixpoint passes (deduplicated).
    * ``terminated`` — pids that were SIGTERMed and exited within the grace
      window (graceful shutdown).
    * ``killed`` — pids that survived the grace window and were SIGKILLed.
    * ``unreaped`` — pids that still matched the env markers at the fixpoint
      cap (req: surface, never broad-match) — e.g. an env-matched class the
      reaper could not bring down, or a marker-less worker reached no other
      way (the spec's Open-Decision fallback). Surfaced in the recovery
      report, never escalated to a broad ``claude`` match.
    """

    matched: list[int] = field(default_factory=list)
    terminated: list[int] = field(default_factory=list)
    killed: list[int] = field(default_factory=list)
    unreaped: list[int] = field(default_factory=list)

    @property
    def matched_count(self) -> int:
        return len(self.matched)

    @property
    def terminated_count(self) -> int:
        return len(self.terminated)

    @property
    def killed_count(self) -> int:
        return len(self.killed)

    @property
    def unreaped_count(self) -> int:
        return len(self.unreaped)


def _env_matches_session(proc: psutil.Process, session_id: str) -> bool:
    """Return ``True`` iff ``proc``'s env carries BOTH session markers.

    Selection keeps the AND of ``CORTEX_RUNNER_CHILD == "1"`` and
    ``LIFECYCLE_SESSION_ID == session_id`` (spec §R5). A process whose
    environment cannot be introspected (``process_iter`` set the ``environ``
    attr to ``None`` or accessing it raises ``AccessDenied``/``NoSuchProcess``
    / ``ZombieProcess``) is treated as a non-match and swallowed — never a
    broad match.
    """
    try:
        environ = proc.info.get("environ")
    except (AttributeError, KeyError):
        try:
            environ = proc.environ()
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
            return False
        except Exception:
            return False
    if not environ:
        return False
    return (
        environ.get(_RUNNER_CHILD_MARKER) == "1"
        and environ.get(_SESSION_ID_MARKER) == session_id
    )


def _select_matched(session_id: str) -> list[psutil.Process]:
    """Enumerate processes and return only those env-matched to ``session_id``.

    Enumerates via ``psutil.process_iter(['environ', 'create_time'])`` (the
    attr is set to ``None`` / raises ``AccessDenied`` for processes that can't
    be introspected — those are non-matches, swallowed). Selection is the AND
    of both env markers; it MUST NOT broad-match all ``claude`` processes.
    """
    matched: list[psutil.Process] = []
    try:
        procs = psutil.process_iter(["environ", "create_time"])
    except Exception:
        return matched
    for proc in procs:
        try:
            if _env_matches_session(proc, session_id):
                matched.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
        except Exception:
            continue
    return matched


def reap_session_orphans(
    session_id: str,
    *,
    graceful_timeout: float = DESCENDANT_GRACEFUL_SHUTDOWN_SECONDS,
    max_passes: int = _REAP_FIXPOINT_MAX_PASSES,
) -> ReapOutcome:
    """Reap a dead session's orphaned workers by env-marker enumeration.

    When the runner dies, its descendants reparent to launchd (PID 1), so
    neither the in-process descendant-tree walk (it walks the *caller's*
    children) nor a recorded-pgid ``killpg`` reaches them — the codebase
    explicitly rejects recorded child-PGIDs
    (:func:`runner._terminate_descendant_tree` docstring). This external
    reaper instead enumerates processes via :mod:`psutil` and selects only
    those whose environment carries BOTH ``CORTEX_RUNNER_CHILD == "1"`` AND
    ``LIFECYCLE_SESSION_ID == session_id`` (the identity anchor), then
    SIGTERM → grace → SIGKILL per matched process. It MUST NOT broad-match
    all ``claude`` processes — that would kill an operator's interactive
    session, which legitimately carries ``LIFECYCLE_SESSION_ID`` (but never
    ``CORTEX_RUNNER_CHILD``).

    **TOCTOU guard**: each pid's ``create_time`` is re-read immediately
    before each signal; if the process vanished or its ``create_time``
    changed (pid reuse) between enumeration and signal, it is skipped. This
    guards only the enumerate→kill window — it does not assert prior session
    membership beyond the env match, which is the identity anchor.

    **Fixpoint loop**: enumerate→signal runs as a bounded fixpoint — after
    the grace window, re-enumerate and repeat until a pass finds zero matched
    pids or ``max_passes`` is hit. This catches a child a matched worker
    forked *during* the grace window. Any pid still env-matched at the cap is
    surfaced as ``unreaped`` (never broad-matched).

    Best-effort: every per-process exception is swallowed so one failure does
    not block the rest. Returns a :class:`ReapOutcome` summarizing the pass.
    """
    outcome = ReapOutcome()
    seen_matched: set[int] = set()

    for _pass in range(max_passes):
        matched_procs = _select_matched(session_id)
        if not matched_procs:
            # Fixpoint reached: no env-matched pid remains.
            outcome.matched = sorted(seen_matched)
            return outcome

        for proc in matched_procs:
            seen_matched.add(proc.pid)

        # Phase 1: SIGTERM each matched proc, re-reading create_time
        # immediately before the signal to guard the enumerate→kill window.
        signalled: list[psutil.Process] = []
        for proc in matched_procs:
            if not _toctou_alive(proc):
                continue
            try:
                proc.terminate()
                signalled.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
            except Exception:
                continue

        # Phase 2: collective wait for graceful exit (up to graceful_timeout).
        try:
            gone, alive = psutil.wait_procs(signalled, timeout=graceful_timeout)
        except Exception:
            gone, alive = [], signalled

        for proc in gone:
            outcome.terminated.append(proc.pid)

        # Phase 3: SIGKILL survivors, re-reading create_time again.
        for proc in alive:
            if not _toctou_alive(proc):
                # Vanished between the wait and the kill — count it as a
                # graceful exit (it is gone, just not via our SIGTERM-wait).
                outcome.terminated.append(proc.pid)
                continue
            try:
                proc.kill()
                outcome.killed.append(proc.pid)
            except psutil.NoSuchProcess:
                outcome.terminated.append(proc.pid)
            except (psutil.AccessDenied, psutil.ZombieProcess):
                continue
            except Exception:
                continue

    # Cap reached without a clean pass: surface any pid that STILL matches the
    # env markers as un-reaped (never broad-matched).
    for proc in _select_matched(session_id):
        outcome.unreaped.append(proc.pid)

    outcome.matched = sorted(seen_matched)
    return outcome


def _toctou_alive(proc: psutil.Process) -> bool:
    """Re-read ``create_time`` and confirm ``proc`` is the same process.

    Guards the enumerate→kill TOCTOU window: returns ``False`` if the process
    vanished between enumeration and the signal, or if its ``create_time``
    changed (the pid was reused for a different process). The enumeration-time
    ``create_time`` is read from ``proc.info`` (populated by
    ``process_iter(['create_time'])``); a live re-read via ``proc.create_time()``
    must match it. Any introspection failure is treated as not-alive (skip),
    never a broad match.
    """
    try:
        enumerated = proc.info.get("create_time")
    except (AttributeError, KeyError):
        enumerated = None
    try:
        live = proc.create_time()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return False
    except Exception:
        return False
    if enumerated is None:
        # No enumeration-time baseline to compare against: the live read
        # succeeded, so the process exists — but without a baseline we cannot
        # rule out reuse. Treat the successful live read as alive.
        return True
    return enumerated == live
