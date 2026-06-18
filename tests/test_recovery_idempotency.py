"""Idempotency + concurrency-safety test for the recovery core (spec §R3).

:func:`cortex_command.overnight.recovery.recover_session` runs the whole
detect→recover sequence under :func:`ipc._acquire_takeover_lock` and makes a
second invocation on an already-recovered session a no-op via a layered guard
checked under the lock:

  1. the standalone, race-authoritative :data:`RECOVERY_COMPLETE_SIDECAR`
     sidecar exists → return no-op immediately;
  2. (failing that) the post-lock state re-load reports ``phase in
     ("paused", "complete")`` → short-circuit to no-op (catch-first; never
     relying on ``state.transition`` raising ``ValueError``).

This test synthesizes a stuck-``executing`` + dead-pid session dir on disk
(mirroring ``tests/test_recovery_core.py``), drives it through
:func:`recover_session` once to recover it, then invokes ``recover_session``
again on the SAME session and asserts the spec's §R3 acceptance criterion:

  * the second call makes no further state change (``overnight-state.json``
    mtime + contents stable) and raises no exception;
  * the :data:`RECOVERY_COMPLETE_SIDECAR` exists after the first call and is the
    gate the second call short-circuits on (verified by removing it and
    confirming the second call is then gated only by the ``phase``-guard, which
    is also a no-op).

The orphan reaper (:func:`reap_session_orphans`) is monkeypatched so the test
never touches real processes.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import psutil

from cortex_command.overnight import recovery
from cortex_command.overnight.recovery import (
    ORCHESTRATOR_CRASH_PAUSED_REASON,
    RECOVERY_COMPLETE_SIDECAR,
    ReapOutcome,
    recover_session,
)
from cortex_command.overnight.state import (
    OvernightFeatureStatus,
    OvernightState,
    load_state,
    save_state,
)

SESSION_ID = "overnight-2026-04-24-idempotency"


def _dead_pid() -> int:
    """Return a pid that is (almost certainly) not running."""
    proc = psutil.Popen(["true"])
    proc.wait()
    return proc.pid


def _dead_pid_payload(pid: int) -> dict:
    """Return a well-formed ``runner.pid`` payload for a dead ``pid``."""
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


def _synthesize_stuck_session(root: Path) -> Path:
    """Build a stuck-``executing`` + dead-pid session dir under ``root``."""
    session_dir = root / "cortex" / "lifecycle" / "sessions" / SESSION_ID
    session_dir.mkdir(parents=True, exist_ok=True)

    state = OvernightState(
        session_id=SESSION_ID,
        plan_ref="cortex/lifecycle/overnight-plan.md",
        phase="executing",
        features={"feature-a": OvernightFeatureStatus(status="running")},
    )
    save_state(state, session_dir / "overnight-state.json")

    _write_runner_pid(session_dir, _dead_pid_payload(_dead_pid()))
    return session_dir


def test_recover_session_second_call_is_noop(tmp_path, monkeypatch):
    """A second ``recover_session`` on an already-recovered session is a no-op.

    Asserts the second call (a) makes no further state change — the
    ``overnight-state.json`` mtime and contents are stable — and raises no
    exception, and (b) is gated by the ``recovery-complete.json`` sidecar, which
    exists after the first (recovering) call.
    """
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))
    # report.notify() shells out to ~/.claude/notify.sh, which blocks on `cat`
    # when stdin is non-tty; SKIP_NOTIFICATIONS=1 short-circuits it.
    monkeypatch.setenv("SKIP_NOTIFICATIONS", "1")

    # Reaper must not touch real processes — monkeypatch it to a fixed outcome.
    sentinel_reap = ReapOutcome(matched=[111], terminated=[111])
    monkeypatch.setattr(
        recovery, "reap_session_orphans", lambda *a, **k: sentinel_reap
    )

    session_dir = _synthesize_stuck_session(tmp_path)
    state_path = session_dir / "overnight-state.json"
    sidecar_path = session_dir / RECOVERY_COMPLETE_SIDECAR

    # First call: a real recovery. Drives executing -> paused and writes the
    # race-authoritative completion sidecar as its final step.
    first = recover_session(session_dir, trigger="manual")
    assert first.action == "recovered"

    # The completion sidecar exists after the first call — it is the gate the
    # second call must short-circuit on.
    assert sidecar_path.exists()

    after_first = load_state(state_path)
    assert after_first.phase == "paused"
    assert after_first.paused_reason == ORCHESTRATOR_CRASH_PAUSED_REASON
    assert after_first.crash_recovery_attempts == 1

    # Snapshot the post-recovery state file (mtime + raw bytes) so the second
    # call's no-op-ness is provable.
    mtime_after_first = state_path.stat().st_mtime_ns
    bytes_after_first = state_path.read_bytes()

    # Second call on the SAME session: must be a no-op, raise nothing, and
    # short-circuit on the sidecar (guard (a)) before touching state.
    second = recover_session(session_dir, trigger="manual")
    assert second.action == "noop"

    # No further state change: mtime and raw contents are stable, and the
    # crash-recovery counter did NOT advance (a re-pause would have bumped it).
    assert state_path.stat().st_mtime_ns == mtime_after_first
    assert state_path.read_bytes() == bytes_after_first

    after_second = load_state(state_path)
    assert after_second.phase == "paused"
    assert after_second.paused_reason == ORCHESTRATOR_CRASH_PAUSED_REASON
    assert after_second.crash_recovery_attempts == 1


def test_recover_session_sidecar_is_the_short_circuit_gate(tmp_path, monkeypatch):
    """The ``recovery-complete.json`` sidecar is the layer-(a) short-circuit gate.

    With a fully-recovered (``phase == paused``) session, removing the sidecar
    proves the sidecar — not a ``paused_reason`` flip — is the gate guard (a)
    keys on: the call still short-circuits (now via the layer-(b) phase guard),
    remains a no-op, and raises nothing. This confirms recovery never relies on
    ``state.transition`` raising to detect an illegal re-pause.
    """
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("SKIP_NOTIFICATIONS", "1")

    sentinel_reap = ReapOutcome(matched=[111], terminated=[111])
    monkeypatch.setattr(
        recovery, "reap_session_orphans", lambda *a, **k: sentinel_reap
    )

    session_dir = _synthesize_stuck_session(tmp_path)
    state_path = session_dir / "overnight-state.json"
    sidecar_path = session_dir / RECOVERY_COMPLETE_SIDECAR

    # Recover the session, then delete the completion sidecar.
    recover_session(session_dir, trigger="guardian")
    assert sidecar_path.exists()
    sidecar_path.unlink()
    assert not sidecar_path.exists()

    mtime_before = state_path.stat().st_mtime_ns
    bytes_before = state_path.read_bytes()

    # Sidecar gone, but phase is already "paused" -> layer-(b) phase guard
    # short-circuits to a no-op without raising (never relies on transition
    # raising ValueError on the illegal paused -> paused re-pause).
    result = recover_session(session_dir, trigger="guardian")
    assert result.action == "noop"

    # Still no state mutation.
    assert state_path.stat().st_mtime_ns == mtime_before
    assert state_path.read_bytes() == bytes_before
    after = load_state(state_path)
    assert after.phase == "paused"
    assert after.crash_recovery_attempts == 1
