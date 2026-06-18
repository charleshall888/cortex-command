"""Integration test for the recovery core sequence (spec §R2, Phase 1).

:func:`cortex_command.overnight.recovery.recover_session` is the
writer-authorized recovery core: it drives a pid-dead ``executing`` session
to a clean ``paused`` end-state by re-implementing pause/report/reap/clear
from the pure ``state``/``ipc``/``report`` primitives (never the runner's
in-process-lock helpers).

This test synthesizes a stuck-``executing`` + dead-pid session dir on disk
(mirroring the fixture style in ``tests/test_recovery_predicate.py`` /
``tests/test_recovery_reaper.py`` and the ``_write_state`` / runner.pid-payload
helpers in ``tests/test_runner_resume.py`` / ``tests/test_ipc_verify_runner_pid.py``),
drives it through :func:`recover_session`, and asserts the spec's acceptance
criterion:

  * final ``phase == "paused"``;
  * ``paused_reason == "orchestrator_crash"``;
  * a morning-report file exists;
  * ``runner.pid`` is cleared (``verify_runner_pid`` on the prior payload → False).

The orphan reaper (:func:`reap_session_orphans`) is monkeypatched so the test
never touches real processes.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import psutil

from cortex_command.overnight import ipc, recovery
from cortex_command.overnight.recovery import (
    RECOVERY_COMPLETE_SIDECAR,
    ReapOutcome,
    RecoveryResult,
    recover_session,
)
from cortex_command.overnight.state import (
    OvernightFeatureStatus,
    OvernightState,
    load_state,
    save_state,
)

SESSION_ID = "overnight-2026-04-24-recovery"


def _dead_pid() -> int:
    """Return a pid that is (almost certainly) not running.

    Spawns a trivial child, waits for it to exit, and returns its pid so
    :func:`ipc.verify_runner_pid` reads it as dead.
    """
    proc = psutil.Popen(["true"])
    proc.wait()
    return proc.pid


def _dead_pid_payload(pid: int) -> dict:
    """Return a well-formed ``runner.pid`` payload for a dead ``pid``.

    The schema is valid (correct magic, in-range version) but the recorded
    process is gone, so :func:`ipc.verify_runner_pid` reads it as dead.
    """
    return {
        "schema_version": 1,
        "magic": "cortex-runner-v1",
        "pid": pid,
        "pgid": os.getpgrp(),
        "start_time": datetime(2026, 4, 24, 12, 0, 0, tzinfo=timezone.utc).isoformat(),
        "session_id": SESSION_ID,
    }


def _write_runner_pid(session_dir: Path, payload: dict) -> None:
    """Write a ``runner.pid`` JSON file into ``session_dir``."""
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "runner.pid").write_text(json.dumps(payload))


def _synthesize_stuck_session(root: Path) -> tuple[Path, dict]:
    """Build a stuck-``executing`` + dead-pid session dir under ``root``.

    Lays out ``{root}/cortex/lifecycle/sessions/{SESSION_ID}/`` with an
    ``overnight-state.json`` at ``phase == "executing"`` (one non-terminal
    feature, so the partial report has something to convey) and a ``runner.pid``
    whose recorded process is dead. Returns ``(session_dir, dead_pid_payload)``.
    """
    session_dir = root / "cortex" / "lifecycle" / "sessions" / SESSION_ID
    session_dir.mkdir(parents=True, exist_ok=True)

    state = OvernightState(
        session_id=SESSION_ID,
        plan_ref="cortex/lifecycle/overnight-plan.md",
        phase="executing",
        features={"feature-a": OvernightFeatureStatus(status="running")},
    )
    save_state(state, session_dir / "overnight-state.json")

    payload = _dead_pid_payload(_dead_pid())
    _write_runner_pid(session_dir, payload)

    return session_dir, payload


def test_recover_session_drives_stuck_to_paused(tmp_path, monkeypatch):
    """A stuck-executing + dead-pid session is recovered to a clean paused
    end-state (spec §R2 acceptance).

    Asserts final ``phase == "paused"``, ``paused_reason == "orchestrator_crash"``,
    a morning-report file exists, and ``runner.pid`` is cleared.
    """
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))
    # report.notify() shells out to ~/.claude/notify.sh, which blocks on `cat`
    # when stdin is non-tty; SKIP_NOTIFICATIONS=1 short-circuits it (the
    # established suppression hatch — see tests/test_runner_pr_gating.py).
    monkeypatch.setenv("SKIP_NOTIFICATIONS", "1")

    # Reaper must not touch real processes — monkeypatch it to a fixed outcome.
    sentinel_reap = ReapOutcome(matched=[111], terminated=[111])
    monkeypatch.setattr(
        recovery, "reap_session_orphans", lambda *a, **k: sentinel_reap
    )

    session_dir, prior_payload = _synthesize_stuck_session(tmp_path)

    result = recover_session(session_dir, trigger="manual")

    # The result reflects a real recovery action threading through the reap.
    assert isinstance(result, RecoveryResult)
    assert result.action == "recovered"
    assert result.session_id == SESSION_ID
    assert result.trigger == "manual"
    assert result.reap is sentinel_reap

    # Final state: paused with the crash reason and a bumped counter.
    final = load_state(session_dir / "overnight-state.json")
    assert final.phase == "paused"
    assert final.paused_reason == "orchestrator_crash"
    assert final.paused_from == "executing"
    assert final.crash_recovery_attempts == 1

    # A morning-report file exists (Task 6 enriches its banner later).
    assert (session_dir / "morning-report.md").exists()

    # runner.pid is cleared — verify_runner_pid on the PRIOR payload is False
    # (and the file itself is gone).
    assert not (session_dir / "runner.pid").exists()
    assert ipc.verify_runner_pid(prior_payload) is False

    # The race-authoritative completion sidecar was written as the final step.
    assert (session_dir / RECOVERY_COMPLETE_SIDECAR).exists()


def test_recover_session_noop_when_predicate_false(tmp_path, monkeypatch):
    """When the predicate does not re-confirm, recovery is a no-op.

    A session whose runner pid is live (this process) does not need recovery;
    ``recover_session`` must return ``action == "noop"`` without mutating state.
    """
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))

    # If the reaper is reached on a no-op, fail loudly.
    def _boom(*a, **k):
        raise AssertionError("reaper must not run on a no-op")

    monkeypatch.setattr(recovery, "reap_session_orphans", _boom)

    session_dir = tmp_path / "cortex" / "lifecycle" / "sessions" / SESSION_ID
    session_dir.mkdir(parents=True, exist_ok=True)
    state = OvernightState(
        session_id=SESSION_ID,
        plan_ref="cortex/lifecycle/overnight-plan.md",
        phase="executing",
    )
    save_state(state, session_dir / "overnight-state.json")

    # Live pid (this process) -> predicate False -> no recovery.
    epoch = psutil.Process(os.getpid()).create_time()
    _write_runner_pid(
        session_dir,
        {
            "schema_version": 1,
            "magic": "cortex-runner-v1",
            "pid": os.getpid(),
            "pgid": os.getpgrp(),
            "start_time": datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat(),
            "session_id": SESSION_ID,
        },
    )

    result = recover_session(session_dir, trigger="guardian")

    assert result.action == "noop"
    assert result.session_id == SESSION_ID

    # State is untouched: still executing, no crash reason, runner.pid intact.
    final = load_state(session_dir / "overnight-state.json")
    assert final.phase == "executing"
    assert final.paused_reason is None
    assert final.crash_recovery_attempts == 0
    assert (session_dir / "runner.pid").exists()
    assert not (session_dir / RECOVERY_COMPLETE_SIDECAR).exists()
