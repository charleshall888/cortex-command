"""Crash-loop resume guard tests (spec §R9, Task 11).

``cortex overnight start`` resume must refuse to auto-resume a session that
out-of-process crash recovery paused (``paused_reason ==
"orchestrator_crash"``) once its ``crash_recovery_attempts`` counter exceeds
the crash-loop bound (default 1), unless ``--force`` is passed — because the
#308 trigger class (e.g. a pre-commit gate blocking every commit) is
deterministic and a blind auto-resume would crash, get recovered, and crash
again. A clean pause (``budget_exhausted``/``signal``) is unaffected.

Two coverage axes (spec §R9 acceptance + the Task-11 ordering acceptance):

  * the guard DECISION — :func:`runner._crash_loop_resume_declined` declines a
    crash-paused, over-bound session with the sidecar present, proceeds with
    ``--force``, and never touches a clean ``budget_exhausted`` pause; and
  * the LOCK ORDERING — :func:`runner._start_session` runs the guard read (the
    ``recovery-complete.json`` sidecar + the counter) UNDER the takeover lock
    and BEFORE :func:`interrupt.handle_interrupted_features` mutates feature
    status, so a declined resume leaves the ``running`` feature un-reset.

The guard decision is tested directly (per the task note: the full ``run()``
drive is flaky against the ``verify_runner_pid`` ±2 s ``create_time`` check;
the decline path returns before any pid claim, so driving ``_start_session``
to the decline is safe — but the pure decision function is the primary anchor).
"""

from __future__ import annotations

import json
from pathlib import Path

from cortex_command.overnight import interrupt as interrupt_mod
from cortex_command.overnight import runner
from cortex_command.overnight.recovery import RECOVERY_COMPLETE_SIDECAR
from cortex_command.overnight.runner import (
    CRASH_RECOVERY_RESUME_BOUND,
    RunnerCoordination,
    _crash_loop_resume_declined,
    _start_session,
)
from cortex_command.overnight.state import (
    OvernightFeatureStatus,
    OvernightState,
    load_state,
    save_state,
)

SESSION_ID = "overnight-2026-06-17-crashloop"


def _build_session(
    tmp_path: Path,
    *,
    paused_reason: str | None,
    crash_recovery_attempts: int,
    write_sidecar: bool,
    feature_status: str = "pending",
) -> Path:
    """Lay out a paused session dir on disk and return its ``session_dir``.

    Builds ``{tmp_path}/cortex/lifecycle/sessions/{SESSION_ID}/`` with an
    ``overnight-state.json`` at ``phase == "paused"`` carrying the given
    ``paused_reason`` + ``crash_recovery_attempts`` and one feature at
    ``feature_status``. Optionally writes the ``recovery-complete.json``
    sidecar (the race-authoritative recovery-ran marker the guard reads).
    """
    session_dir = tmp_path / "cortex" / "lifecycle" / "sessions" / SESSION_ID
    session_dir.mkdir(parents=True, exist_ok=True)

    state = OvernightState(
        session_id=SESSION_ID,
        plan_ref="cortex/lifecycle/overnight-plan.md",
        phase="paused",
        paused_from="executing",
        paused_reason=paused_reason,
        crash_recovery_attempts=crash_recovery_attempts,
        features={
            "feature-a": OvernightFeatureStatus(
                status=feature_status,
                started_at="2026-06-17T00:00:00+00:00"
                if feature_status == "running"
                else None,
            )
        },
    )
    save_state(state, session_dir / "overnight-state.json")

    if write_sidecar:
        (session_dir / RECOVERY_COMPLETE_SIDECAR).write_text(
            json.dumps(
                {
                    "session_id": SESSION_ID,
                    "trigger": "guardian",
                    "paused_reason": "orchestrator_crash",
                    "recovered_at": "2026-06-17T01:00:00+00:00",
                }
            ),
            encoding="utf-8",
        )

    return session_dir


# ---------------------------------------------------------------------------
# Guard decision (spec §R9 acceptance)
# ---------------------------------------------------------------------------

def test_declines_over_bound_crash_pause_without_force(tmp_path: Path) -> None:
    """Over-bound crash pause + sidecar declines auto-resume without --force."""
    session_dir = _build_session(
        tmp_path,
        paused_reason="orchestrator_crash",
        crash_recovery_attempts=CRASH_RECOVERY_RESUME_BOUND + 1,
        write_sidecar=True,
    )
    state = load_state(session_dir / "overnight-state.json")

    decline = _crash_loop_resume_declined(session_dir, state, force=False)

    assert decline is not None, "over-bound crash pause must decline auto-resume"
    assert "crash_recovery_attempts" in decline
    assert "--force" in decline


def test_proceeds_over_bound_crash_pause_with_force(tmp_path: Path) -> None:
    """--force bypasses the guard for an over-bound crash pause."""
    session_dir = _build_session(
        tmp_path,
        paused_reason="orchestrator_crash",
        crash_recovery_attempts=CRASH_RECOVERY_RESUME_BOUND + 1,
        write_sidecar=True,
    )
    state = load_state(session_dir / "overnight-state.json")

    decline = _crash_loop_resume_declined(session_dir, state, force=True)

    assert decline is None, "--force must proceed even past the bound"


def test_budget_exhausted_pause_resumes_regardless(tmp_path: Path) -> None:
    """A clean budget_exhausted pause is never declined, even over-bound.

    The guard keys on ``paused_reason == "orchestrator_crash"``; a clean
    pause must resume normally regardless of the counter (and regardless of a
    stray sidecar, which a clean pause would never write).
    """
    session_dir = _build_session(
        tmp_path,
        paused_reason="budget_exhausted",
        crash_recovery_attempts=CRASH_RECOVERY_RESUME_BOUND + 5,
        write_sidecar=True,
    )
    state = load_state(session_dir / "overnight-state.json")

    decline = _crash_loop_resume_declined(session_dir, state, force=False)

    assert decline is None, "budget_exhausted pause must resume regardless"


def test_crash_pause_at_bound_resumes(tmp_path: Path) -> None:
    """At the bound (not over it), a crash pause still auto-resumes.

    The bound is a strict ``>`` threshold: a single recovered attempt
    (counter == bound) is allowed to resume; only an over-bound counter
    (the deterministic crash-loop signal) declines.
    """
    session_dir = _build_session(
        tmp_path,
        paused_reason="orchestrator_crash",
        crash_recovery_attempts=CRASH_RECOVERY_RESUME_BOUND,
        write_sidecar=True,
    )
    state = load_state(session_dir / "overnight-state.json")

    decline = _crash_loop_resume_declined(session_dir, state, force=False)

    assert decline is None, "a crash pause at (not over) the bound must resume"


def test_crash_pause_over_bound_without_sidecar_resumes(tmp_path: Path) -> None:
    """No recovery-complete sidecar -> recovery did not actually run -> resume.

    The sidecar is the race-authoritative "recovery ran on this session"
    marker. Without it the over-bound counter alone is not the decline signal
    (a counter could survive from an unrelated path), so the guard proceeds.
    """
    session_dir = _build_session(
        tmp_path,
        paused_reason="orchestrator_crash",
        crash_recovery_attempts=CRASH_RECOVERY_RESUME_BOUND + 1,
        write_sidecar=False,
    )
    state = load_state(session_dir / "overnight-state.json")

    decline = _crash_loop_resume_declined(session_dir, state, force=False)

    assert decline is None, "no sidecar means recovery did not run -> resume"


# ---------------------------------------------------------------------------
# Lock ordering: guard reads the sidecar BEFORE handle_interrupted_features
# mutates state (Task 11 acceptance — spec Overview "Recovery↔resume ordering")
# ---------------------------------------------------------------------------

def test_guard_declines_before_feature_status_reset(
    tmp_path: Path, monkeypatch
) -> None:
    """A declined resume runs the guard read BEFORE the feature-status reset.

    Drives :func:`runner._start_session` against a crash-paused, over-bound
    session whose sidecar is present and which has a ``running`` feature. The
    guard must decline (return ``(None, None, None)``) WITHOUT
    :func:`interrupt.handle_interrupted_features` having run — proved by the
    feature staying ``running`` (a run would have reset it to ``pending``) and
    by a tripwire on ``handle_interrupted_features`` never firing.

    The decline path returns before any ``runner.pid`` claim, so the
    ``verify_runner_pid`` ±2 s ``create_time`` flakiness the task note warns
    about does not apply here.
    """
    session_dir = _build_session(
        tmp_path,
        paused_reason="orchestrator_crash",
        crash_recovery_attempts=CRASH_RECOVERY_RESUME_BOUND + 1,
        write_sidecar=True,
        feature_status="running",
    )
    state_path = session_dir / "overnight-state.json"

    # Tripwire: if the guard's ordering is wrong and
    # handle_interrupted_features runs ahead of the decline, fail loudly.
    def _boom(*_a, **_k):
        raise AssertionError(
            "handle_interrupted_features must NOT run before a declined resume"
        )

    monkeypatch.setattr(interrupt_mod, "handle_interrupted_features", _boom)

    coord = RunnerCoordination()
    state, pid_data, start_time = _start_session(
        state_path=state_path,
        session_dir=session_dir,
        repo_path=tmp_path,
        events_path=session_dir / "overnight-events.log",
        coord=coord,
        force=False,
    )

    # Declined: _start_session signals refusal with the (None, None, None)
    # sentinel the caller maps to a nonzero exit.
    assert state is None
    assert pid_data is None
    assert start_time is None

    # The feature-status reset never ran: feature-a is still running.
    final = load_state(state_path)
    assert final.features["feature-a"].status == "running", (
        "the declined resume must not have reset the running feature"
    )
    # And no runner.pid was claimed on the decline path.
    assert not (session_dir / "runner.pid").exists()


def test_force_runs_interrupt_recovery_past_bound(
    tmp_path: Path, monkeypatch
) -> None:
    """--force bypasses the guard and proceeds to interrupt recovery.

    Symmetric to the decline-ordering test: with ``--force`` the guard does
    not decline, so ``_start_session`` proceeds past the guard to
    ``handle_interrupted_features``. We monkeypatch the rest of the claim path
    to no-ops so the test asserts only the proceed-past-guard ordering without
    driving the flaky full pid-claim.
    """
    session_dir = _build_session(
        tmp_path,
        paused_reason="orchestrator_crash",
        crash_recovery_attempts=CRASH_RECOVERY_RESUME_BOUND + 1,
        write_sidecar=True,
        feature_status="running",
    )
    state_path = session_dir / "overnight-state.json"

    called = {"interrupt": False}

    real_handle = interrupt_mod.handle_interrupted_features

    def _record(path):
        called["interrupt"] = True
        return real_handle(path)

    monkeypatch.setattr(interrupt_mod, "handle_interrupted_features", _record)
    # Stub the pid-claim path so we do not depend on verify_runner_pid timing.
    monkeypatch.setattr(
        runner.ipc, "write_runner_pid", lambda *a, **k: None
    )
    monkeypatch.setattr(
        runner.ipc, "write_active_session", lambda *a, **k: None
    )
    monkeypatch.setattr(
        runner, "_check_concurrent_start", lambda *a, **k: (None, k.get("lock_fd"))
    )

    coord = RunnerCoordination()
    state, pid_data, start_time = _start_session(
        state_path=state_path,
        session_dir=session_dir,
        repo_path=tmp_path,
        events_path=session_dir / "overnight-events.log",
        coord=coord,
        force=True,
    )

    # --force proceeded past the guard: interrupt recovery ran and the
    # session was claimed (non-None return).
    assert called["interrupt"] is True
    assert state is not None
    assert pid_data is not None
    assert start_time is not None
