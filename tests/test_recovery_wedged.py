"""Tests for the wedged-runner (alive-but-hung) recovery path (spec §R12).

Phase 2 extends out-of-process recovery from the hard-dead case (pid gone,
:func:`recovery.needs_recovery_pid_death`) to the alive-but-WEDGED case: the
runner process is alive (``verify_runner_pid`` reads alive) but its event loop
is hung, so ``overnight-events.log`` has gone stale past a safe threshold.

This module asserts the four verification criteria for Task 15:

  (a) ``WEDGED_STALENESS_SECONDS > STALL_TIMEOUT_SECONDS`` — the threshold is
      strictly greater than the in-process watchdog's wall-clock timer so the
      runner's own ``WatchdogThread`` gets first crack at a graceful self-heal.
  (b) executing + alive-pid + heartbeat age ``WEDGED_STALENESS_SECONDS + 60``
      → :func:`needs_recovery_wedged` True; age ``WEDGED_STALENESS_SECONDS - 60``
      → False.
  (c) the wedged-recovery path issues ``SIGKILL`` to the recorded pid BEFORE
      the ``state.transition`` call (the still-alive wedged runner could
      otherwise overwrite ``paused``→``executing``) — verified by monkeypatching
      ``os.kill`` + ``state.transition`` and asserting call order.
  (d) the guardian scan recovers a synthesized wedged (alive-pid +
      stale-heartbeat) session via the unified :func:`recovery.needs_recovery`
      gate.

The pid fixtures mirror ``tests/test_recovery_predicate.py`` /
``tests/test_recovery_core.py``; the reaper is monkeypatched so no real
processes are touched and ``SKIP_NOTIFICATIONS=1`` suppresses the report-path
notify shell-out.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psutil

from cortex_command.overnight import guardian, recovery
from cortex_command.overnight.recovery import (
    WEDGED_STALENESS_SECONDS,
    ReapOutcome,
    needs_recovery,
    needs_recovery_wedged,
    recover_session,
)
from cortex_command.overnight.runner import STALL_TIMEOUT_SECONDS
from cortex_command.overnight.state import (
    OvernightFeatureStatus,
    OvernightState,
    load_state,
    save_state,
)

SESSION_ID = "overnight-2026-04-24-wedged"


def _alive_pid_payload(pid: int, session_id: str = SESSION_ID) -> dict:
    """Return a well-formed ``runner.pid`` payload for a live ``pid``.

    A ``start_time`` matching ``pid``'s ``create_time`` verifies as live via
    :func:`ipc.verify_runner_pid` (±2s create_time match).
    """
    epoch = psutil.Process(pid).create_time()
    return {
        "schema_version": 1,
        "magic": "cortex-runner-v1",
        "pid": pid,
        "pgid": os.getpgrp(),
        "start_time": datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat(),
        "session_id": session_id,
    }


def _write_runner_pid(session_dir: Path, payload: dict) -> None:
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "runner.pid").write_text(json.dumps(payload))


def _sessions_root(root: Path) -> Path:
    return root / "cortex" / "lifecycle" / "sessions"


def _write_heartbeat(lifecycle_root: Path, age_seconds: float) -> None:
    """Append a single HEARTBEAT event whose ``ts`` is ``age_seconds`` in the past.

    Mirrors the runner-level heartbeat (Task 14) shape that
    :func:`status._read_last_event_ts` reads off ``overnight-events.log``: a
    JSONL line with an ``event`` key and a parseable ISO ``ts``.
    """
    lifecycle_root.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    entry = {
        "v": 1,
        "ts": ts.isoformat(),
        "event": "HEARTBEAT",
        "session_id": SESSION_ID,
        "round": 1,
        "details": {"session_id": SESSION_ID, "source": "runner"},
    }
    log_path = lifecycle_root / "overnight-events.log"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def _synthesize_wedged(
    root: Path,
    *,
    session_id: str = SESSION_ID,
    age_seconds: float,
    alive_pid: int | None = None,
) -> Path:
    """Build a wedged session: ``executing`` + alive-pid + stale heartbeat.

    Lays out ``{root}/cortex/lifecycle/sessions/{session_id}/`` with an
    ``executing`` state, a live ``runner.pid`` (defaults to this process so
    ``verify_runner_pid`` reads alive), and an ``overnight-events.log`` whose
    last HEARTBEAT is ``age_seconds`` old. Returns the session dir.
    """
    pid = alive_pid if alive_pid is not None else os.getpid()
    session_dir = _sessions_root(root) / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    state = OvernightState(
        session_id=session_id,
        plan_ref="cortex/lifecycle/overnight-plan.md",
        phase="executing",
        features={"feature-a": OvernightFeatureStatus(status="running")},
    )
    save_state(state, session_dir / "overnight-state.json")
    _write_runner_pid(session_dir, _alive_pid_payload(pid, session_id))
    # The events log lives at lifecycle_root == session_dir.parent.parent.
    _write_heartbeat(session_dir.parent.parent, age_seconds)
    return session_dir


# ---------------------------------------------------------------------------
# (a) threshold relationship
# ---------------------------------------------------------------------------


def test_wedged_threshold_strictly_greater_than_stall_timeout() -> None:
    """WEDGED_STALENESS_SECONDS must be strictly > STALL_TIMEOUT_SECONDS.

    The strict-greater margin lets the in-process watchdog (which fires at
    STALL_TIMEOUT_SECONDS) attempt its own graceful self-heal before the
    out-of-process guardian SIGKILLs the wedged runner.
    """
    assert WEDGED_STALENESS_SECONDS > STALL_TIMEOUT_SECONDS


# ---------------------------------------------------------------------------
# (b) staleness-predicate boundary
# ---------------------------------------------------------------------------


def test_wedged_predicate_true_when_heartbeat_older_than_threshold(tmp_path):
    """executing + alive-pid + heartbeat older than the threshold → True."""
    session_dir = _synthesize_wedged(
        tmp_path, age_seconds=WEDGED_STALENESS_SECONDS + 60
    )
    assert needs_recovery_wedged(session_dir) is True
    # The unified gate also fires.
    assert needs_recovery(session_dir) is True


def test_wedged_predicate_false_when_heartbeat_younger_than_threshold(tmp_path):
    """executing + alive-pid + heartbeat younger than the threshold → False.

    A healthy-but-slow round whose heartbeat is fresh must never be flagged —
    that is what the strict-greater margin protects.
    """
    session_dir = _synthesize_wedged(
        tmp_path, age_seconds=WEDGED_STALENESS_SECONDS - 60
    )
    assert needs_recovery_wedged(session_dir) is False
    # And the unified gate is also clean (pid is alive, so no pid-death either).
    assert needs_recovery(session_dir) is False


def test_wedged_predicate_false_when_no_heartbeat(tmp_path):
    """executing + alive-pid + NO parseable last-event → False.

    Staleness is asserted only against a real timestamp; an absent log on an
    alive runner is treated as not-stale, never inferred as a wedge.
    """
    session_dir = _sessions_root(tmp_path) / SESSION_ID
    session_dir.mkdir(parents=True, exist_ok=True)
    state = OvernightState(
        session_id=SESSION_ID,
        plan_ref="cortex/lifecycle/overnight-plan.md",
        phase="executing",
    )
    save_state(state, session_dir / "overnight-state.json")
    _write_runner_pid(session_dir, _alive_pid_payload(os.getpid()))
    # No overnight-events.log written.
    assert needs_recovery_wedged(session_dir) is False


# ---------------------------------------------------------------------------
# (c) SIGKILL-before-transition ordering
# ---------------------------------------------------------------------------


def test_wedged_recovery_sigkills_before_transition(tmp_path, monkeypatch):
    """The wedged path issues SIGKILL to the recorded pid BEFORE transition.

    A still-alive wedged runner could overwrite ``paused``→``executing`` (the
    takeover lock does not serialize ``save_state`` cross-process), so recovery
    MUST kill it first. Monkeypatches ``os.kill`` and ``state.transition`` to a
    shared call log and asserts the kill (of the recorded pid) precedes the
    transition.
    """
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("SKIP_NOTIFICATIONS", "1")
    monkeypatch.setattr(
        recovery, "reap_session_orphans", lambda *a, **k: ReapOutcome()
    )

    session_dir = _synthesize_wedged(
        tmp_path, age_seconds=WEDGED_STALENESS_SECONDS + 60
    )
    recorded_pid = os.getpid()

    calls: list[tuple] = []

    def _fake_kill(pid, sig):
        calls.append(("kill", pid, sig))

    def _fake_transition(state, target):
        calls.append(("transition", target))
        # Mimic the real transition's side effect so downstream steps proceed.
        state.paused_from = state.phase
        state.phase = target

    # os.kill is referenced as ``os.kill`` inside recovery (module-level os).
    monkeypatch.setattr(recovery.os, "kill", _fake_kill)
    monkeypatch.setattr(recovery.state_mod, "transition", _fake_transition)

    result = recover_session(session_dir, trigger="manual")
    assert result.action == "recovered"

    # Exactly one kill, of the recorded pid, with SIGKILL, BEFORE the transition.
    kill_calls = [c for c in calls if c[0] == "kill"]
    transition_calls = [c for c in calls if c[0] == "transition"]
    assert kill_calls, "expected a SIGKILL on the wedged runner"
    assert transition_calls, "expected a transition call"

    import signal as _signal

    assert kill_calls[0] == ("kill", recorded_pid, _signal.SIGKILL)
    first_kill_idx = calls.index(kill_calls[0])
    first_transition_idx = calls.index(transition_calls[0])
    assert first_kill_idx < first_transition_idx, (
        "SIGKILL must precede the state transition"
    )


def test_pid_death_recovery_does_not_sigkill(tmp_path, monkeypatch):
    """The pid-death path must NOT issue a SIGKILL (no live runner to kill).

    Regression guard for the additive change: only the wedged branch kills.
    """
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("SKIP_NOTIFICATIONS", "1")
    monkeypatch.setattr(
        recovery, "reap_session_orphans", lambda *a, **k: ReapOutcome()
    )

    # Dead-pid session: spawn-and-wait a child so its pid reads dead.
    proc = psutil.Popen(["true"])
    proc.wait()
    dead_pid = proc.pid

    session_dir = _sessions_root(tmp_path) / SESSION_ID
    session_dir.mkdir(parents=True, exist_ok=True)
    state = OvernightState(
        session_id=SESSION_ID,
        plan_ref="cortex/lifecycle/overnight-plan.md",
        phase="executing",
        features={"feature-a": OvernightFeatureStatus(status="running")},
    )
    save_state(state, session_dir / "overnight-state.json")
    _write_runner_pid(
        session_dir,
        {
            "schema_version": 1,
            "magic": "cortex-runner-v1",
            "pid": dead_pid,
            "pgid": os.getpgrp(),
            "start_time": datetime(
                2026, 4, 24, 12, 0, 0, tzinfo=timezone.utc
            ).isoformat(),
            "session_id": SESSION_ID,
        },
    )

    kills: list = []
    monkeypatch.setattr(recovery.os, "kill", lambda *a, **k: kills.append(a))

    result = recover_session(session_dir, trigger="manual")
    assert result.action == "recovered"
    assert kills == [], "pid-death recovery must not SIGKILL anything"
    final = load_state(session_dir / "overnight-state.json")
    assert final.phase == "paused"
    assert final.paused_reason == "orchestrator_crash"


# ---------------------------------------------------------------------------
# (d) guardian scan via the unified gate
# ---------------------------------------------------------------------------


def test_guardian_scan_recovers_wedged_via_unified_gate(tmp_path, monkeypatch):
    """The guardian scan recovers a synthesized wedged session.

    Builds an ``executing`` + alive-pid + stale-heartbeat session and asserts
    the scan (which now gates on the unified ``needs_recovery``) recovers it.
    The wedged runner is this test process, so ``os.kill`` is monkeypatched to
    a no-op recorder — no real kill — and the reaper is stubbed.
    """
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("SKIP_NOTIFICATIONS", "1")
    monkeypatch.setattr(
        recovery, "reap_session_orphans", lambda *a, **k: ReapOutcome()
    )
    kills: list = []
    monkeypatch.setattr(recovery.os, "kill", lambda *a, **k: kills.append(a))

    session_dir = _synthesize_wedged(
        tmp_path, age_seconds=WEDGED_STALENESS_SECONDS + 60
    )

    state_root = tmp_path / "cortex" / "lifecycle"
    results = guardian.scan_and_recover(state_root)

    by_id = {r.session_id: r for r in results}
    assert SESSION_ID in by_id
    assert by_id[SESSION_ID].action == "recovered"
    assert by_id[SESSION_ID].trigger == "guardian"

    # The wedged runner was SIGKILLed before the transition (guardian path).
    assert kills, "guardian wedged recovery must SIGKILL the wedged runner"

    final = load_state(session_dir / "overnight-state.json")
    assert final.phase == "paused"
    assert final.paused_reason == "orchestrator_crash"
    assert not (session_dir / "runner.pid").exists()
