"""Task 14: runner-level heartbeat across all executing sub-phases.

Today ``HEARTBEAT`` is emitted only by ``_heartbeat_loop`` inside
``run_batch`` (the batch_runner subprocess). During the planning sub-phase
— between ``ROUND_START`` and the batch_runner spawn — the runner only
polls via ``_poll_subprocess`` (no events), so ``overnight-events.log`` can
be silent >30 min during healthy plan generation. That blind window makes
event-log staleness an *invalid* liveness signal in the planning phase,
which would break Task 15's wedged-runner staleness predicate.

This task adds a runner-owned heartbeat
(:class:`runner.RunnerHeartbeatThread`) that emits ``HEARTBEAT`` on a fixed
cadence (:data:`runner.RUNNER_HEARTBEAT_INTERVAL_SECONDS`) across the entire
planning→batch span, advancing the last-event timestamp in every
``executing`` sub-phase.

Why not drive the full ``runner.run`` in-process: ``_start_session``
records ``start_time = datetime.now()`` and ``ipc.verify_runner_pid``
requires that to match this process's ``create_time`` within ±2s, which
never holds for the long-lived pytest process. So these tests drive the
heartbeat-emit mechanism directly — one emit / one thread tick against a
temp events log — and assert the last-event ts advances via
``status._read_last_event_ts``. A source/AST wiring guard asserts ``run``
actually starts the thread, so removing the wiring regresses the suite.
"""

from __future__ import annotations

import ast
import inspect
import threading
import time
from pathlib import Path

from cortex_command.overnight import events, runner, status
from cortex_command.overnight.runner_primitives import RunnerCoordination


def _read_last_ts(events_path: Path):
    """Resolve the last-event timestamp the staleness predicate would read."""
    return status._read_last_event_ts(events_path)


def _make_coord() -> RunnerCoordination:
    return RunnerCoordination(
        shutdown_event=threading.Event(),
        state_lock=threading.Lock(),
        kill_lock=threading.Lock(),
        received_signals=[],
    )


def test_runner_heartbeat_reuses_registered_event_literal() -> None:
    """The emit reuses ``events.HEARTBEAT`` — no new event literal/registry.

    Task 14 explicitly forbids inventing a new event name (that would
    require registry changes out of scope). The constant must be the
    already-registered ``"heartbeat"`` so ``log_event``'s ``EVENT_TYPES``
    membership check passes.
    """
    assert events.HEARTBEAT == "heartbeat"
    assert events.HEARTBEAT in events.EVENT_TYPES


def test_single_emit_writes_a_heartbeat_advancing_last_event_ts(
    tmp_path: Path,
) -> None:
    """A single runner-level emit advances the last-event timestamp.

    Simulates the planning-phase window: a fresh events log with no batch
    heartbeat. After one runner-level emit, ``status._read_last_event_ts``
    (the exact source Task 15's staleness predicate keys on) returns a
    parseable timestamp — proving the runner heartbeat makes event-log
    staleness a valid liveness signal during planning.
    """
    events_path = tmp_path / "overnight-events.log"
    assert _read_last_ts(events_path) is None  # silent log up front

    runner._emit_runner_heartbeat(
        events_path,
        session_id="overnight-2026-06-18-plan",
        round_num=1,
    )

    last_ts = _read_last_ts(events_path)
    assert last_ts is not None

    # The emitted record is a registered HEARTBEAT carrying the runner
    # source marker (distinguishing it from the batch_runner's emit).
    logged = events.read_events(events_path)
    assert len(logged) == 1
    assert logged[0]["event"] == events.HEARTBEAT
    assert logged[0]["details"]["source"] == "runner"
    assert logged[0]["details"]["session_id"] == "overnight-2026-06-18-plan"


def test_emit_advances_ts_beyond_a_prior_stale_event(tmp_path: Path) -> None:
    """A later heartbeat advances the last-event ts past an earlier one.

    Models the staleness signal directly: seed a heartbeat (the "stale"
    last event), capture its ts, then emit a second runner-level heartbeat
    and assert the last-event ts strictly advances. This is the property
    Task 15's predicate depends on — without the runner heartbeat the ts
    would not advance during the planning sub-phase.
    """
    events_path = tmp_path / "overnight-events.log"

    runner._emit_runner_heartbeat(events_path, "sess", 1)
    first_ts = _read_last_ts(events_path)
    assert first_ts is not None

    # Ensure the wall clock advances so the second ISO-8601 ts is strictly
    # later (ISO timestamps have microsecond resolution; a tiny sleep is
    # ample and keeps the assertion robust).
    time.sleep(0.01)

    runner._emit_runner_heartbeat(events_path, "sess", 1)
    second_ts = _read_last_ts(events_path)
    assert second_ts is not None
    assert second_ts > first_ts


def test_thread_tick_emits_a_heartbeat_within_the_cadence(
    tmp_path: Path,
) -> None:
    """One thread cadence tick emits a heartbeat advancing the last-event ts.

    Drives the daemon thread itself with a tiny interval so a single tick
    fires quickly, then asserts the last-event ts advanced — the
    end-to-end mechanism (thread → emit → log) without the infeasible full
    ``run`` drive. ``stop()`` reaps the thread promptly.
    """
    events_path = tmp_path / "overnight-events.log"
    coord = _make_coord()

    hb = runner.RunnerHeartbeatThread(
        coord=coord,
        events_path=events_path,
        session_id="sess",
        round_num=2,
        interval_seconds=0.05,
    )
    hb.start()
    try:
        # Wait until at least one beat lands (bounded so a hang fails fast).
        deadline = time.monotonic() + 5.0
        while _read_last_ts(events_path) is None:
            if time.monotonic() >= deadline:
                break
            time.sleep(0.02)
    finally:
        hb.stop()
        hb.join(timeout=2.0)

    assert not hb.is_alive()
    last_ts = _read_last_ts(events_path)
    assert last_ts is not None
    logged = events.read_events(events_path)
    assert all(e["event"] == events.HEARTBEAT for e in logged)
    assert logged[-1]["round"] == 2


def test_stop_wakes_thread_promptly_on_clean_exit(tmp_path: Path) -> None:
    """``stop()`` wakes the thread immediately rather than blocking a cadence.

    A long cadence (large interval) must not delay a clean-exit ``join``:
    ``stop()`` sets the thread's own stop event so ``wait`` returns at once.
    Guards the clean-path reap in ``run``'s ``finally`` against blocking for
    the full 300s interval.
    """
    events_path = tmp_path / "overnight-events.log"
    coord = _make_coord()

    hb = runner.RunnerHeartbeatThread(
        coord=coord,
        events_path=events_path,
        session_id="sess",
        round_num=1,
        interval_seconds=300.0,  # would block join() if stop() did not wake it
    )
    hb.start()
    hb.stop()
    hb.join(timeout=2.0)
    assert not hb.is_alive()


def test_shutdown_event_stops_the_thread(tmp_path: Path) -> None:
    """A shutdown signal (``coord.shutdown_event``) stops the heartbeat.

    The signal path sets ``coord.shutdown_event`` (not the thread's own
    stop event); the thread must honor it as an exit trigger so the
    heartbeat ceases once shutdown is in progress.
    """
    events_path = tmp_path / "overnight-events.log"
    coord = _make_coord()

    hb = runner.RunnerHeartbeatThread(
        coord=coord,
        events_path=events_path,
        session_id="sess",
        round_num=1,
        interval_seconds=0.05,
    )
    hb.start()
    time.sleep(0.12)  # let at least one tick fire
    coord.shutdown_event.set()
    hb.join(timeout=2.0)
    assert not hb.is_alive()


def test_set_round_updates_subsequent_heartbeat_round(tmp_path: Path) -> None:
    """``set_round`` re-stamps the round carried on later heartbeats.

    The main loop calls ``set_round`` as it advances rounds so planning-span
    beats carry the round currently executing.
    """
    events_path = tmp_path / "overnight-events.log"
    coord = _make_coord()

    hb = runner.RunnerHeartbeatThread(
        coord=coord,
        events_path=events_path,
        session_id="sess",
        round_num=1,
        interval_seconds=0.05,
    )
    hb.set_round(7)
    hb.start()
    try:
        deadline = time.monotonic() + 5.0
        while _read_last_ts(events_path) is None:
            if time.monotonic() >= deadline:
                break
            time.sleep(0.02)
    finally:
        hb.stop()
        hb.join(timeout=2.0)

    logged = events.read_events(events_path)
    assert logged, "expected at least one heartbeat"
    assert logged[-1]["round"] == 7


def test_emit_is_best_effort_and_never_raises(tmp_path: Path) -> None:
    """A log-write failure is swallowed — the heartbeat never crashes run.

    Liveness, not durability, is the point: a transient write error must not
    propagate out of the emit and abort the runner. Pointing the emit at a
    path whose parent is a regular file (so ``mkdir``/open fails) exercises
    the best-effort swallow.
    """
    bad_parent = tmp_path / "not-a-dir"
    bad_parent.write_text("x", encoding="utf-8")
    events_path = bad_parent / "overnight-events.log"

    # Must not raise despite the un-writable path.
    runner._emit_runner_heartbeat(events_path, "sess", 1)


def test_run_is_wired_to_start_the_runner_heartbeat() -> None:
    """``run`` constructs and starts a ``RunnerHeartbeatThread``.

    Wiring guard (mirrors ``test_runner_finally_clears_pid``'s AST approach,
    since ``verify_runner_pid``'s ±2s create_time match makes a faithful
    in-process ``run`` drive infeasible). Removing the thread start — the
    regression this task defends against, reopening the planning-phase blind
    window — fails this test. Also asserts the ``finally`` stops the thread
    so it never outlives the round loop.
    """
    source = inspect.getsource(runner.run)
    tree = ast.parse(source)
    func = tree.body[0]
    assert isinstance(func, ast.FunctionDef)

    constructs_thread = False
    starts_thread = False
    finally_stops_thread = False

    for node in ast.walk(func):
        if isinstance(node, ast.Call):
            callee = node.func
            if isinstance(callee, ast.Name) and callee.id == "RunnerHeartbeatThread":
                constructs_thread = True
            if (
                isinstance(callee, ast.Attribute)
                and callee.attr == "start"
                and isinstance(callee.value, ast.Name)
                and callee.value.id == "heartbeat_thread"
            ):
                starts_thread = True

    for node in ast.walk(func):
        if isinstance(node, ast.Try) and node.finalbody:
            for stmt in node.finalbody:
                for inner in ast.walk(stmt):
                    if (
                        isinstance(inner, ast.Call)
                        and isinstance(inner.func, ast.Attribute)
                        and inner.func.attr == "stop"
                        and isinstance(inner.func.value, ast.Name)
                        and inner.func.value.id == "heartbeat_thread"
                    ):
                        finally_stops_thread = True

    assert constructs_thread, "run() must construct a RunnerHeartbeatThread"
    assert starts_thread, "run() must start the heartbeat thread"
    assert finally_stops_thread, (
        "run()'s finally must stop the heartbeat thread so it never "
        "outlives the round loop"
    )
