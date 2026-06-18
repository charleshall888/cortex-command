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

import fcntl
import os
import signal
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import psutil

from cortex_command.overnight import events, ipc, report, status
from cortex_command.overnight import state as state_mod
from cortex_command.overnight.fail_markers import _session_phase
from cortex_command.overnight.runner import (
    DESCENDANT_GRACEFUL_SHUTDOWN_SECONDS,
    STALL_TIMEOUT_SECONDS,
)


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
# Wedged-runner staleness predicate (spec §R12, Phase 2)
# ---------------------------------------------------------------------------

#: Event-log staleness threshold (seconds) that flags an *alive-but-wedged*
#: runner for recovery (spec §R12, Task 15). A named module constant — not a
#: bare literal — so the acceptance test can reference it directly and the
#: strict-greater-than relationship to the in-process watchdog's
#: :data:`runner.STALL_TIMEOUT_SECONDS` (``1800s``) is assertable.
#:
#: Pinned at ``2700`` (45 min) — strictly greater than ``STALL_TIMEOUT_SECONDS``
#: by a ``900s`` margin so the runner's own in-process ``WatchdogThread`` gets
#: first crack at a graceful self-heal before the out-of-process guardian
#: SIGKILLs the wedged runner. This margin is what makes the staleness signal
#: safe: a healthy-but-slow round that the in-process watchdog would already
#: have terminated cannot reach this threshold.
WEDGED_STALENESS_SECONDS: float = 2700.0

# Fail loud if the strict-greater-than invariant ever regresses (e.g. someone
# lowers WEDGED_STALENESS_SECONDS or raises STALL_TIMEOUT_SECONDS): the whole
# point of the threshold is to let the in-process watchdog self-heal first.
assert WEDGED_STALENESS_SECONDS > STALL_TIMEOUT_SECONDS, (
    "WEDGED_STALENESS_SECONDS must be strictly greater than "
    "STALL_TIMEOUT_SECONDS so the in-process watchdog self-heals first"
)


def needs_recovery_wedged(session_dir: Path) -> bool:
    """Return ``True`` iff a session needs *wedged-runner* recovery (spec §R12).

    The alive-but-hung counterpart to :func:`needs_recovery_pid_death`. Flags
    the session iff ALL THREE hold:

      1. its on-disk ``phase`` is ``"executing"``, AND
      2. its recorded session-leader ``runner.pid`` reads **ALIVE**
         (:func:`status._is_runner_pid_live` is ``True``) — the runner process
         exists, so the pid-death signal does NOT fire, AND
      3. the last event in ``overnight-events.log`` (the runner-level heartbeat
         advances this in every ``executing`` sub-phase, per Task 14) is older
         than :data:`WEDGED_STALENESS_SECONDS` — the event loop has gone silent
         past the safe threshold.

    The freshness source is :func:`status._read_last_event_ts` over the session
    tree's ``overnight-events.log``; a missing or unparseable last-event
    timestamp is treated as *not stale* (``False``) — staleness is only asserted
    against a real, parseable timestamp, never inferred from an absent one (an
    absent log on an alive runner is more likely a fresh start than a wedge).

    The :data:`WEDGED_STALENESS_SECONDS` threshold is strictly greater than the
    in-process watchdog's ``STALL_TIMEOUT_SECONDS`` so the runner's own
    ``WatchdogThread`` gets first crack at a graceful self-heal — this margin is
    what keeps a healthy-but-slow round from false-positiving.

    Purely read-only: this function never writes state.
    """
    if _session_phase(session_dir) != "executing":
        return False
    if not status._is_runner_pid_live(session_dir):
        # Pid is dead → this is the pid-death case, not the wedged case.
        return False
    last_ts = status._read_last_event_ts(
        _lifecycle_root(session_dir) / "overnight-events.log"
    )
    if last_ts is None:
        # No parseable last-event timestamp: do not infer a wedge from an absent
        # signal — only a real, parseable, stale timestamp flags the wedge.
        return False
    age_seconds = (datetime.now(timezone.utc) - last_ts).total_seconds()
    return age_seconds > WEDGED_STALENESS_SECONDS


def needs_recovery(session_dir: Path) -> bool:
    """Return ``True`` iff a session needs recovery (unified gate, spec §R12).

    The disjunction of the two detection signals:
    :func:`needs_recovery_pid_death` (the hard-dead runner) OR
    :func:`needs_recovery_wedged` (the alive-but-hung runner). This is the
    single predicate the guardian scan and the recovery core's step-1
    re-confirm gate on, so wedged sessions are caught alongside pid-dead ones.
    """
    return needs_recovery_pid_death(session_dir) or needs_recovery_wedged(
        session_dir
    )


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


# ---------------------------------------------------------------------------
# Recovery core sequence (spec §R2, Phase 1)
# ---------------------------------------------------------------------------

#: The descriptive ``paused_reason`` a crash-recovery pause sets (spec §R2
#: step 2, Task 1). Single-valued on purpose: the "recovery completed" signal
#: is NOT a second ``paused_reason`` — it is the standalone
#: :data:`RECOVERY_COMPLETE_SIDECAR` file plus the
#: :data:`ORCHESTRATOR_CRASH_RECOVERED_EVENT` event — so a concurrent resume's
#: ``save_state`` rewrite of ``overnight-state.json`` cannot clobber the
#: completion marker.
ORCHESTRATOR_CRASH_PAUSED_REASON = "orchestrator_crash"

#: Filename of the standalone, race-authoritative completion marker written as
#: the final step of a successful recovery (spec §R3, Overview "Recovery↔resume
#: ordering"). A separate file — not a flag inside ``overnight-state.json`` —
#: so a concurrent resume ``save_state`` cannot overwrite it. Task 5 adds the
#: idempotency short-circuit that keys on this file's existence; this task only
#: writes it (step 7).
RECOVERY_COMPLETE_SIDECAR = "recovery-complete.json"

#: The event name emitted to ``overnight-events.log`` when recovery completes
#: (spec §R10). Registered in ``bin/.events-registry.md`` by Task 12; until the
#: matching ``EVENT_TYPES`` constant is added in ``events.py`` the emit is
#: swallowed best-effort (see :func:`recover_session`).
ORCHESTRATOR_CRASH_RECOVERED_EVENT = "orchestrator_crash_recovered"


@dataclass
class RecoveryResult:
    """Outcome of a :func:`recover_session` invocation (spec §R2).

    Fields:

    * ``session_id`` — the recovered session's id (from on-disk state). May be
      ``""`` when state could not be loaded.
    * ``action`` — ``"recovered"`` when the full transition→report→reap→clear
      sequence ran, ``"noop"`` when the predicate did not re-confirm under the
      (Task-5) lock so nothing was mutated.
    * ``trigger`` — the surface that invoked recovery (``"guardian"`` |
      ``"manual"``), threaded into the completion event.
    * ``reap`` — the :class:`ReapOutcome` from the orphan reap, or ``None`` on a
      no-op.
    * ``report_path`` — the session-specific morning report path written, or
      ``None`` if no report was written.
    * ``latest_report_path`` — the latest-copy morning report path, or ``None``.
    """

    session_id: str
    action: str
    trigger: str
    reap: Optional[ReapOutcome] = None
    report_path: Optional[Path] = None
    latest_report_path: Optional[Path] = None


def _lifecycle_root(session_dir: Path) -> Path:
    """Return the lifecycle root implied by a session dir.

    A session dir is ``{lifecycle_root}/sessions/{session_id}`` (see
    :func:`state.session_dir`), so the lifecycle root is two levels up. Used to
    resolve the per-session report + events-log destinations without depending
    on ``CORTEX_REPO_ROOT`` resolution (the session dir is passed in directly).
    """
    return session_dir.parent.parent


def recover_session(session_dir: Path, *, trigger: str) -> RecoveryResult:
    """Drive a pid-dead ``executing`` session to a clean ``paused`` end-state.

    This is the writer-authorized recovery core (spec §R2/§R3). It re-implements
    pause/report/reap/clear from the pure ``state``/``ipc``/``report``
    primitives — it MUST NOT call the runner's ``_transition_paused`` /
    ``_generate_morning_report``, which require an in-process
    ``RunnerCoordination`` threading lock unavailable out-of-process.

    **Concurrency + idempotency (spec §R3).** The whole detect→recover sequence
    runs under :func:`ipc._acquire_takeover_lock` (a 5s-budget flock, released
    in a ``finally``). A second invocation on an already-recovered session is a
    no-op via a layered guard checked *under the lock*, in order:

      * **(a) sidecar guard** — if the :data:`RECOVERY_COMPLETE_SIDECAR` file
        already exists, return a no-op immediately. This is the sole
        race-authoritative completion marker: a separate file a concurrent
        resume's ``save_state`` rewrite of ``overnight-state.json`` cannot
        clobber (the ``paused_reason`` stays ``"orchestrator_crash"``, never a
        ``"_recovered"`` flip).
      * **(b) phase guard** — re-load state *after* the lock is held and
        short-circuit to a no-op if ``phase in ("paused", "complete")``. This
        catch-first guard is checked before any ``state.transition`` call so we
        never rely on ``transition`` raising ``ValueError`` to detect an
        illegal re-pause.

    With the lock held, performs, in order:

      1. **Re-load state from disk and re-confirm the predicate.** The mutated
         ``state`` object is this post-lock load (a stale pre-lock read could
         slip past both guards). If :func:`needs_recovery_pid_death` is ``False``
         at re-confirm, return a no-op :class:`RecoveryResult` without mutating
         anything.
      2. ``state.transition(state, "paused")`` + set
         ``paused_reason = "orchestrator_crash"`` + increment
         ``crash_recovery_attempts`` + atomic ``save_state``.
      3. ``ipc.update_active_session_phase(session_id, "paused")`` (retain the
         active-session pointer — no clear).
      4. Write the partial morning report (Task 6 enriches its banner).
      5. Reap session-matched orphans (:func:`reap_session_orphans`).
      6. ``ipc.clear_runner_pid(session_dir, expected_session_id=session_id)``
         (CAS — unlinks only on session_id match).
      7. Write the :data:`RECOVERY_COMPLETE_SIDECAR` sidecar atomically as the
         final, race-authoritative completion marker.

    Emits an :data:`ORCHESTRATOR_CRASH_RECOVERED_EVENT` event to
    ``overnight-events.log`` with a ``trigger`` field after the sequence. The
    emit is best-effort: ``events.log_event`` validates the name against
    ``EVENT_TYPES`` and raises ``ValueError`` for an unregistered name, so the
    call is wrapped so a not-yet-registered event never aborts a completed
    recovery (the registration lands in Task 12 / ``EVENT_TYPES``).

    Args:
        session_dir: The session's directory
            (``{lifecycle_root}/sessions/{session_id}``) holding
            ``overnight-state.json`` and ``runner.pid``.
        trigger: The invoking surface — ``"guardian"`` or ``"manual"``.

    Returns:
        A :class:`RecoveryResult` describing what was done.

    Raises:
        ConcurrentRunnerLockTimeoutError: If the takeover lock cannot be
            acquired within its 5s budget (a concurrent recovery/resume holds
            it).
    """
    state_path = session_dir / "overnight-state.json"

    # Acquire the per-session takeover lock so the whole detect→recover sequence
    # runs serialized against a concurrent recovery; released in the finally via
    # flock(LOCK_UN) + os.close (the helper returns a held fd, NOT a context
    # manager). Raises ConcurrentRunnerLockTimeoutError on its 5s budget.
    lock_fd = ipc._acquire_takeover_lock(session_dir)
    try:
        # Idempotency guard (a): the race-authoritative completion sidecar
        # already exists → recovery already ran; second invocation is a no-op.
        # Checked FIRST, under the lock, before any state load or mutation.
        if (session_dir / RECOVERY_COMPLETE_SIDECAR).exists():
            return RecoveryResult(
                session_id="",
                action="noop",
                trigger=trigger,
            )

        # Step 1: re-load state from disk UNDER THE LOCK. The mutated state
        # object MUST be this post-lock load (a stale pre-lock read could slip
        # past the phase guard below and the transition call).
        overnight_state = state_mod.load_state(state_path)
        session_id = overnight_state.session_id

        # Idempotency guard (b): short-circuit if the session is already in a
        # terminal/paused phase. Catch-first — we do NOT rely on
        # state.transition raising ValueError for an illegal re-pause.
        if overnight_state.phase in ("paused", "complete"):
            return RecoveryResult(
                session_id=session_id,
                action="noop",
                trigger=trigger,
            )

        # Re-confirm the UNIFIED predicate under the lock; a session whose
        # runner pid is now alive AND whose heartbeat is fresh (or whose phase
        # is no longer executing) needs no recovery. The unified gate catches
        # both the pid-death case and the alive-but-wedged case.
        if not needs_recovery(session_dir):
            return RecoveryResult(
                session_id=session_id,
                action="noop",
                trigger=trigger,
            )

        # SIGKILL-before-transition (wedged case only, spec §R12). When the
        # runner pid reads ALIVE the firing signal is the wedged-staleness
        # predicate, NOT pid-death — and a still-alive wedged runner could
        # overwrite our ``paused`` back to ``executing`` (the takeover lock does
        # NOT serialize ``save_state`` cross-process). So we MUST SIGKILL the
        # recorded runner BEFORE the transition. The pid's ``create_time`` is
        # re-verified immediately before the kill (``verify_runner_pid``
        # semantics) so a reused pid is never killed.
        if needs_recovery_wedged(session_dir):
            _sigkill_wedged_runner(session_dir)

        # Step 2: transition executing -> paused, record the reason, bump the
        # crash-recovery counter, and persist atomically.
        state_mod.transition(overnight_state, "paused")
        overnight_state.paused_reason = ORCHESTRATOR_CRASH_PAUSED_REASON
        overnight_state.crash_recovery_attempts += 1
        state_mod.save_state(overnight_state, state_path)

        # Step 3: retain the active-session pointer at the new phase (no clear).
        # A no-op if the pointer is absent or names a different session.
        ipc.update_active_session_phase(session_id, "paused")

        # Step 4: write the partial morning report. Both the session-specific
        # and the latest-copy paths are written; pass the lifecycle root
        # explicitly so the write stays anchored to this session dir's tree.
        # (Task 6 enriches the banner via the new orchestrator_crash render
        # branch.)
        lifecycle_root = _lifecycle_root(session_dir)
        project_root = lifecycle_root.parent.parent
        report_path: Optional[Path] = None
        latest_report_path: Optional[Path] = None
        try:
            written = report.generate_and_write_report(
                state_path=state_path,
                events_path=lifecycle_root / "overnight-events.log",
                report_dir=session_dir,
                project_root=project_root,
            )
            report_path = session_dir / "morning-report.md"
            latest_report_path = lifecycle_root / "morning-report.md"
            if written is not None:
                report_path = Path(written)
        except Exception:
            # The report is partial-safe but best-effort: a render failure must
            # not block the transition/reap/clear that already succeeded.
            pass

        # Step 5: reap the dead session's orphaned workers by env-marker match.
        reap = reap_session_orphans(session_id)

        # Step 6: clear the stale runner.pid (CAS — only unlinks on session
        # match).
        ipc.clear_runner_pid(session_dir, expected_session_id=session_id)

        # Step 7: write the recovery-complete sidecar atomically as the final,
        # race-authoritative completion marker (a separate file a concurrent
        # resume save_state cannot overwrite). The reap counts are threaded in
        # so a later report re-render can surface the orphan-reap outcome line
        # (Task 6); recovery's own report at step 4 ran before this write, so
        # that render omits the reap line defensively.
        _write_recovery_complete_sidecar(
            session_dir,
            session_id=session_id,
            trigger=trigger,
            reap=reap,
        )

        # Completion event (best-effort: swallow an unregistered-name ValueError
        # so a not-yet-registered EVENT_TYPES entry never aborts a completed
        # recovery).
        try:
            events.log_event(
                ORCHESTRATOR_CRASH_RECOVERED_EVENT,
                overnight_state.current_round,
                details={
                    "trigger": trigger,
                    "reaped": reap.matched_count,
                    "killed": reap.killed_count,
                    "unreaped": reap.unreaped_count,
                },
                log_path=lifecycle_root / "overnight-events.log",
            )
        except Exception:
            pass

        return RecoveryResult(
            session_id=session_id,
            action="recovered",
            trigger=trigger,
            reap=reap,
            report_path=report_path,
            latest_report_path=latest_report_path,
        )
    finally:
        # Release the takeover lock: unlock then close the held fd (the helper
        # returns a bare fd, not a context manager).
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(lock_fd)


def _sigkill_wedged_runner(session_dir: Path) -> None:
    """SIGKILL the create_time-verified wedged runner recorded in ``runner.pid``.

    Called from :func:`recover_session` for the wedged case ONLY, *before* the
    ``state.transition`` to ``paused`` (spec §R12). The wedged runner's event
    loop is hung but its process is still alive, so it could ``save_state`` over
    our ``paused`` back to ``executing`` — and the takeover lock does NOT
    serialize ``save_state`` cross-process. Killing it first removes that race.

    **TOCTOU guard (pid reuse).** The recorded ``runner.pid`` payload is
    re-verified via :func:`ipc.verify_runner_pid` (magic + schema bound +
    ``create_time`` ±2s) immediately before the ``os.kill`` — so a pid the OS
    has recycled for an unrelated process is never killed. If the payload is
    absent/malformed or no longer verifies (the runner died on its own between
    the predicate and here, or the pid was reused), the kill is skipped.

    Best-effort: any signalling failure (the process exited in the TOCTOU
    window, an ``OSError`` from ``os.kill``) is swallowed — the subsequent
    transition/report/reap/clear sequence proceeds either way, and the reaper
    is a second line of defense for the worker tree.
    """
    pid_data = ipc.read_runner_pid(session_dir)
    if pid_data is None:
        return
    # Re-verify create_time ±2s immediately before the kill so a reused pid is
    # never signalled (verify_runner_pid semantics).
    if not ipc.verify_runner_pid(pid_data):
        return
    pid = pid_data.get("pid")
    if not isinstance(pid, int):
        return
    try:
        os.kill(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        # Vanished in the TOCTOU window, or we lack permission — proceed with
        # the transition regardless; the kill is a best-effort race guard.
        pass


def _write_recovery_complete_sidecar(
    session_dir: Path,
    *,
    session_id: str,
    trigger: str,
    reap: Optional[ReapOutcome] = None,
) -> None:
    """Atomically write the ``recovery-complete.json`` completion sidecar.

    The standalone, race-authoritative completion marker (spec §R3). Written as
    recovery's final step via the shared atomic tempfile+``os.replace`` helper
    so a reader never sees a partial file and a concurrent resume's
    ``save_state`` (which rewrites only ``overnight-state.json``) cannot clobber
    it. Task 5 adds the idempotency short-circuit that keys on this file's
    existence.

    The optional ``reap`` outcome is recorded under a ``"reap"`` key (counts
    only) so a later morning-report re-render can surface the orphan-reap
    outcome line (Task 6). The morning report's dependency on this field is
    optional/defensive — an absent sidecar or absent ``reap`` key just omits
    that one banner line.
    """
    payload: dict = {
        "session_id": session_id,
        "trigger": trigger,
        "paused_reason": ORCHESTRATOR_CRASH_PAUSED_REASON,
        "recovered_at": datetime.now(timezone.utc).isoformat(),
    }
    if reap is not None:
        payload["reap"] = {
            "matched": reap.matched_count,
            "terminated": reap.terminated_count,
            "killed": reap.killed_count,
            "unreaped": reap.unreaped_count,
        }
    ipc._atomic_write_json(session_dir / RECOVERY_COMPLETE_SIDECAR, payload)
