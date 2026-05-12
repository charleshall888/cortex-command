"""Tests for the synthesizer defer-count circuit breaker (Task 7 wiring).

Three test cases (per ``lifecycle/.../plan.md`` Task 10):

  1. ``test_threshold_fires_at_three_defers``
     Direct unit test on the ``_count_synthesizer_deferred`` helper:
     three ``plan_synthesis_deferred`` events with the same session_id
     yields a count of 3.

  2. ``test_threshold_does_not_fire_at_two_defers``
     Symmetric negative case: two events yields a count of 2 (below
     the threshold of ``CIRCUIT_BREAKER_THRESHOLD = 3``).

  3. ``test_circuit_breaker_marks_features_paused``
     Integrated round-loop test: drive ``runner.run`` with three
     pre-existing ``plan_synthesis_deferred`` events and a state
     fixture carrying a critical-tier pending feature; mock
     ``_spawn_orchestrator`` (and supporting subprocess plumbing) so
     no real subprocess is spawned. Assert (a) the events log gains
     a ``synthesizer_circuit_breaker_fired`` entry, (b) the session
     phase is ``paused`` with ``paused_reason == 'synthesizer_circuit_breaker'``,
     and (c) the critical-tier feature's status is ``paused``.

The ``_FakeBatchConfig``/``MagicMock`` pattern mirrors
``cortex_command/pipeline/tests/test_repair_agent.py:30-43``.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cortex_command.overnight import events
from cortex_command.overnight import state as state_module
from cortex_command.overnight.constants import CIRCUIT_BREAKER_THRESHOLD
from cortex_command.overnight.runner import _count_synthesizer_deferred


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_SESSION_ID = "overnight-2026-05-04-circuit-breaker"


def _write_deferred_events(
    events_path: Path,
    session_id: str,
    count: int,
    *,
    extra_session_noise: int = 0,
) -> None:
    """Append ``count`` PLAN_SYNTHESIS_DEFERRED entries for ``session_id``.

    When ``extra_session_noise > 0``, also append that many entries with
    a different session id so the helper's defensive session_id filter
    is exercised.
    """
    lines: list[str] = []
    base_round = 1
    for i in range(count):
        lines.append(
            json.dumps(
                {
                    "v": 1,
                    "ts": f"2026-05-04T00:{i:02d}:00+00:00",
                    "event": events.PLAN_SYNTHESIS_DEFERRED,
                    "session_id": session_id,
                    "round": base_round + i,
                    "details": {"reason": "low_confidence"},
                }
            )
        )
    for j in range(extra_session_noise):
        lines.append(
            json.dumps(
                {
                    "v": 1,
                    "ts": f"2026-05-04T01:{j:02d}:00+00:00",
                    "event": events.PLAN_SYNTHESIS_DEFERRED,
                    "session_id": f"other-session-{j}",
                    "round": 1,
                }
            )
        )
    events_path.parent.mkdir(parents=True, exist_ok=True)
    with open(events_path, "a", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")


# ---------------------------------------------------------------------------
# (1) Helper-direct: threshold fires at three defers
# ---------------------------------------------------------------------------

def test_threshold_fires_at_three_defers(tmp_path: Path) -> None:
    """Three matching events → ``_count_synthesizer_deferred`` returns 3."""
    events_path = tmp_path / "overnight-events.log"
    _write_deferred_events(events_path, _SESSION_ID, count=3)

    result = _count_synthesizer_deferred(events_path, _SESSION_ID)

    assert result == 3, f"expected count=3, got {result}"
    # And 3 meets the documented threshold.
    assert result >= CIRCUIT_BREAKER_THRESHOLD, (
        f"expected count >= CIRCUIT_BREAKER_THRESHOLD "
        f"({CIRCUIT_BREAKER_THRESHOLD}), got {result}"
    )


def test_threshold_filters_other_session_noise(tmp_path: Path) -> None:
    """Helper's defensive session_id filter excludes other-session entries.

    Three matching + two from a different session_id should still
    return 3, not 5. This guards against archived entries from a
    re-used path leaking into the count.
    """
    events_path = tmp_path / "overnight-events.log"
    _write_deferred_events(
        events_path, _SESSION_ID, count=3, extra_session_noise=2
    )

    result = _count_synthesizer_deferred(events_path, _SESSION_ID)

    assert result == 3, f"expected count=3 (noise filtered), got {result}"


# ---------------------------------------------------------------------------
# (2) Helper-direct: threshold does not fire at two defers
# ---------------------------------------------------------------------------

def test_threshold_does_not_fire_at_two_defers(tmp_path: Path) -> None:
    """Two matching events → ``_count_synthesizer_deferred`` returns 2."""
    events_path = tmp_path / "overnight-events.log"
    _write_deferred_events(events_path, _SESSION_ID, count=2)

    result = _count_synthesizer_deferred(events_path, _SESSION_ID)

    assert result == 2, f"expected count=2, got {result}"
    # And 2 is strictly below the documented threshold.
    assert result < CIRCUIT_BREAKER_THRESHOLD, (
        f"expected count < CIRCUIT_BREAKER_THRESHOLD "
        f"({CIRCUIT_BREAKER_THRESHOLD}), got {result}"
    )


# ---------------------------------------------------------------------------
# (3) Integrated: round-loop entry point fires the breaker
# ---------------------------------------------------------------------------

def _build_session_state(
    session_dir: Path,
    state_path: Path,
    events_path: Path,
    *,
    critical_feature_name: str,
) -> state_module.OvernightState:
    """Build + persist a session state with one critical-tier pending feature."""
    state = state_module.OvernightState(
        session_id=_SESSION_ID,
        plan_ref=str(session_dir / "overnight-plan.md"),
        current_round=1,
        phase="executing",
        features={
            critical_feature_name: state_module.OvernightFeatureStatus(
                status="pending",
            ),
        },
    )
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_module.save_state(state, state_path)
    # Touch the plan file so any path-checks find an existing artifact.
    plan_path = Path(state.plan_ref)
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text("# overnight plan\n", encoding="utf-8")
    return state


def test_circuit_breaker_marks_features_paused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Three deferred events + one round-loop iteration trips the breaker.

    Asserts:
      (a) ``events.log`` contains ``synthesizer_circuit_breaker_fired``,
      (b) state phase is ``paused`` with reason
          ``synthesizer_circuit_breaker``,
      (c) the critical-tier feature's status is ``paused``.

    Heavy mocking: ``_start_session``, ``_spawn_orchestrator``,
    ``_poll_subprocess``, ``_post_loop``, signal-handler installers and
    auth pre-flight are all stubbed so the round body is a no-op apart
    from the synthesizer-defer-count check.
    """
    from cortex_command.overnight import runner as runner_module

    session_dir = tmp_path / "cortex" / "lifecycle" / "sessions" / _SESSION_ID
    session_dir.mkdir(parents=True, exist_ok=True)
    state_path = session_dir / "overnight-state.json"
    events_path = session_dir / "overnight-events.log"
    repo_path = tmp_path / "repo"
    repo_path.mkdir(parents=True, exist_ok=True)

    critical_feature = "critical-feature-xyz"
    state = _build_session_state(
        session_dir=session_dir,
        state_path=state_path,
        events_path=events_path,
        critical_feature_name=critical_feature,
    )
    plan_path = Path(state.plan_ref)

    # Pre-seed the events log with three plan_synthesis_deferred entries
    # so the breaker fires on the first round-loop iteration.
    _write_deferred_events(events_path, _SESSION_ID, count=3)

    # --- Mocks ----------------------------------------------------------
    # _start_session — bypass interrupt recovery and PID/active-session
    # plumbing.
    def _fake_start_session(
        state_path: Path,
        session_dir: Path,
        repo_path: Path,
        events_path: Path,
        coord,
    ):
        loaded = state_module.load_state(state_path)
        return loaded, {"pid": 0}, "2026-05-04T00:00:00+00:00"

    monkeypatch.setattr(runner_module, "_start_session", _fake_start_session)

    # Signal-handler installers — neutralize so test doesn't mutate
    # global signal state.
    monkeypatch.setattr(
        runner_module, "install_signal_handlers", lambda _coord: {}
    )
    monkeypatch.setattr(
        runner_module, "_install_sigterm_tree_walker", lambda _prior: None
    )
    monkeypatch.setattr(
        runner_module, "restore_signal_handlers", lambda _prior: None
    )

    # Auth pre-flight — runner already wraps this in try/except, but
    # keep the test offline.
    monkeypatch.setattr(
        runner_module.auth,
        "ensure_sdk_auth",
        lambda event_log_path=None: {},
    )

    # _spawn_orchestrator — return a stub Popen + watchdog tuple. The
    # round-loop polls this via _poll_subprocess (also mocked) and
    # treats the result as a successful exit, then checks for a
    # batch-plan file (which we never create), so the orchestrator-no-
    # plan path runs and the breaker check fires.
    fake_proc = MagicMock()
    fake_proc.stdout = MagicMock()
    fake_proc.stdout.closed = True
    fake_proc.poll = MagicMock(return_value=0)
    fake_wctx = MagicMock()
    fake_wctx.stall_flag = MagicMock()
    fake_wctx.stall_flag.is_set = MagicMock(return_value=False)
    fake_watchdog = MagicMock()
    monkeypatch.setattr(
        runner_module,
        "_spawn_orchestrator",
        lambda **kw: (fake_proc, fake_wctx, fake_watchdog),
    )
    monkeypatch.setattr(
        runner_module, "_poll_subprocess", lambda proc, coord: 0
    )

    # Telemetry helper is fire-and-forget; no need to exercise it.
    monkeypatch.setattr(
        runner_module,
        "_emit_orchestrator_round_telemetry",
        lambda *a, **kw: None,
    )

    # _post_loop runs after a clean exit and would attempt PR creation,
    # morning-report generation, etc. Stub it out — the breaker-driven
    # assertions are about state persisted BEFORE _post_loop runs.
    monkeypatch.setattr(runner_module, "_post_loop", lambda **kw: None)

    # read_criticality is called per pending feature when the breaker
    # fires. Force "critical" so the feature qualifies for the paused
    # transition.
    monkeypatch.setattr(
        runner_module,
        "read_criticality",
        lambda name: "critical" if name == critical_feature else "medium",
    )

    # Clean any stray LIFECYCLE_SESSION_ID and force ours so log_event
    # tags entries with our session.
    monkeypatch.setenv("LIFECYCLE_SESSION_ID", _SESSION_ID)

    # --- Invoke ---------------------------------------------------------
    exit_code = runner_module.run(
        state_path=state_path,
        session_dir=session_dir,
        repo_path=repo_path,
        plan_path=plan_path,
        events_path=events_path,
        time_limit_seconds=None,
        max_rounds=1,
        tier="critical",
        dry_run=False,
    )

    # --- Assertions -----------------------------------------------------
    # Clean-exit path returns 0 (post_loop is stubbed).
    assert exit_code == 0, f"expected exit code 0, got {exit_code}"

    # (a) events.log carries a synthesizer_circuit_breaker_fired entry.
    logged = events.read_events(events_path)
    fired = [
        e
        for e in logged
        if e.get("event") == events.SYNTHESIZER_CIRCUIT_BREAKER_FIRED
    ]
    assert len(fired) >= 1, (
        f"expected at least one SYNTHESIZER_CIRCUIT_BREAKER_FIRED entry; "
        f"got events={[e.get('event') for e in logged]}"
    )
    fired_entry = fired[-1]
    assert fired_entry.get("details", {}).get("session_id") == _SESSION_ID
    assert (
        fired_entry.get("details", {}).get("deferred_count")
        >= CIRCUIT_BREAKER_THRESHOLD
    )

    # (b) state phase is paused with the specific reason.
    final_state = state_module.load_state(state_path)
    assert final_state.phase == "paused", (
        f"expected phase='paused', got {final_state.phase!r}"
    )
    assert final_state.paused_reason == "synthesizer_circuit_breaker", (
        f"expected paused_reason='synthesizer_circuit_breaker', "
        f"got {final_state.paused_reason!r}"
    )

    # (c) the critical-tier feature is now paused with the matching
    #     error tag.
    fs = final_state.features[critical_feature]
    assert fs.status == "paused", (
        f"expected critical feature status='paused', got {fs.status!r}"
    )
    assert fs.error == "synthesizer_circuit_breaker", (
        f"expected feature error='synthesizer_circuit_breaker', "
        f"got {fs.error!r}"
    )
