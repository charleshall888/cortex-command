"""Tests for the guardian scan entrypoint (spec §R6, Phase 1).

:func:`cortex_command.overnight.guardian.scan_and_recover` is the entrypoint
the persistent host-level launchd guardian invokes each tick (and that an
operator can run via ``cortex overnight guardian scan``). It holds no
recovery logic of its own: it enumerates every session under
``state_root/sessions/*/``, applies the false-positive-free
:func:`recovery.needs_recovery_pid_death` predicate, and calls
:func:`recovery.recover_session` (``trigger="guardian"``) for each session
whose runner has died.

The load-bearing invariant proved here is **per-session failure isolation**:
one persistent agent scans ALL sessions, so a single poison session (a
malformed ``overnight-state.json`` that raises inside the predicate+recover
path) must NOT starve its co-resident stuck sessions. The
``_synthesize_*`` helpers mirror the fixture style in
``tests/test_recovery_predicate.py`` / ``tests/test_recovery_core.py``; the
reaper is monkeypatched so the test never touches real processes, and
``SKIP_NOTIFICATIONS=1`` suppresses the report-path notify shell-out.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import psutil
import pytest

from cortex_command.overnight import guardian, recovery
from cortex_command.overnight.recovery import ReapOutcome
from cortex_command.overnight.state import (
    OvernightFeatureStatus,
    OvernightState,
    load_state,
    save_state,
)


def _dead_pid() -> int:
    """Return a pid that is (almost certainly) not running.

    Spawns a trivial child, waits for it to exit, and returns its pid so
    :func:`ipc.verify_runner_pid` reads it as dead.
    """
    proc = psutil.Popen(["true"])
    proc.wait()
    return proc.pid


def _dead_pid_payload(pid: int, session_id: str) -> dict:
    """Return a well-formed ``runner.pid`` payload for a dead ``pid``."""
    return {
        "schema_version": 1,
        "magic": "cortex-runner-v1",
        "pid": pid,
        "pgid": os.getpgrp(),
        "start_time": datetime(2026, 4, 24, 12, 0, 0, tzinfo=timezone.utc).isoformat(),
        "session_id": session_id,
    }


def _alive_pid_payload(pid: int, session_id: str) -> dict:
    """Return a well-formed ``runner.pid`` payload for a live ``pid``."""
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


def _synthesize_stuck(root: Path, session_id: str) -> Path:
    """Build a stuck-``executing`` + dead-pid session (needs recovery)."""
    session_dir = _sessions_root(root) / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    state = OvernightState(
        session_id=session_id,
        plan_ref="cortex/lifecycle/overnight-plan.md",
        phase="executing",
        features={"feature-a": OvernightFeatureStatus(status="running")},
    )
    save_state(state, session_dir / "overnight-state.json")
    _write_runner_pid(session_dir, _dead_pid_payload(_dead_pid(), session_id))
    return session_dir


def _synthesize_healthy(root: Path, session_id: str) -> Path:
    """Build an ``executing`` + live-pid session (must NOT be recovered)."""
    session_dir = _sessions_root(root) / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    state = OvernightState(
        session_id=session_id,
        plan_ref="cortex/lifecycle/overnight-plan.md",
        phase="executing",
    )
    save_state(state, session_dir / "overnight-state.json")
    _write_runner_pid(session_dir, _alive_pid_payload(os.getpid(), session_id))
    return session_dir


def _synthesize_poison(root: Path, session_id: str) -> Path:
    """Build a poison session whose malformed state raises during recovery.

    The ``overnight-state.json`` is valid JSON with ``phase == "executing"``
    (so :func:`fail_markers._session_phase` reads it as ``executing`` and the
    pid-death predicate fires) but is missing the required ``session_id`` /
    ``plan_ref`` / ``current_round`` / ``started_at`` / ``updated_at`` keys
    that :func:`state.load_state` dereferences — so :func:`recover_session`
    raises a ``KeyError`` from inside the per-session try/except. A dead
    ``runner.pid`` makes the predicate select it as a recovery candidate.
    """
    session_dir = _sessions_root(root) / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    # Malformed: phase present (predicate keys on it) but load_state's
    # required keys absent -> recover_session raises.
    (session_dir / "overnight-state.json").write_text(
        json.dumps({"phase": "executing"})
    )
    _write_runner_pid(session_dir, _dead_pid_payload(_dead_pid(), session_id))
    return session_dir


def _patch_reaper(monkeypatch) -> None:
    """Monkeypatch the orphan reaper so the test never touches real processes."""
    monkeypatch.setattr(
        recovery,
        "reap_session_orphans",
        lambda *a, **k: ReapOutcome(),
    )


@pytest.mark.parametrize(
    "stuck_id,poison_id",
    [
        # Poison enumerated BEFORE the stuck session (sorted by dir name).
        ("zzz-stuck", "aaa-poison"),
        # Poison enumerated AFTER the stuck session.
        ("aaa-stuck", "zzz-poison"),
    ],
)
def test_scan_recovers_stuck_isolating_poison(
    tmp_path, monkeypatch, stuck_id, poison_id
):
    """A stuck session is recovered while a healthy one is left alone and a
    poison one is isolated — order-independently (spec §R6 acceptance).

    Builds (a) a stuck-``executing`` + dead-pid session, (b) a healthy
    live-pid session, and (c) a poison session with a malformed
    ``overnight-state.json``. Asserts the stuck one is recovered, the healthy
    and poison ones are not, and the poison session's exception does NOT
    prevent the stuck session's recovery — verified for BOTH enumeration
    orders (poison sorting before AND after the stuck session).
    """
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("SKIP_NOTIFICATIONS", "1")
    _patch_reaper(monkeypatch)

    stuck_dir = _synthesize_stuck(tmp_path, stuck_id)
    healthy_dir = _synthesize_healthy(tmp_path, "mid-healthy")
    poison_dir = _synthesize_poison(tmp_path, poison_id)

    state_root = tmp_path / "cortex" / "lifecycle"
    results = guardian.scan_and_recover(state_root)

    by_id = {r.session_id: r for r in results}

    # The stuck session was recovered regardless of poison enumeration order.
    assert stuck_id in by_id
    assert by_id[stuck_id].action == "recovered"
    assert by_id[stuck_id].trigger == "guardian"
    final = load_state(stuck_dir / "overnight-state.json")
    assert final.phase == "paused"
    assert final.paused_reason == "orchestrator_crash"

    # The poison session produced an isolated error entry, not an abort.
    assert poison_id in by_id
    assert by_id[poison_id].action == "error"
    assert getattr(by_id[poison_id], "error", "")
    # Its malformed state was NOT mutated (recovery never got past load).
    assert json.loads((poison_dir / "overnight-state.json").read_text()) == {
        "phase": "executing"
    }

    # The healthy session was left untouched: no result entry, still executing.
    assert "mid-healthy" not in by_id
    healthy_state = load_state(healthy_dir / "overnight-state.json")
    assert healthy_state.phase == "executing"
    assert healthy_state.paused_reason is None
    assert (healthy_dir / "runner.pid").exists()


def test_scan_empty_when_no_sessions(tmp_path, monkeypatch):
    """A state root with no ``sessions/`` subdir yields an empty scan."""
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))
    state_root = tmp_path / "cortex" / "lifecycle"
    assert guardian.scan_and_recover(state_root) == []


def test_scan_noops_all_healthy(tmp_path, monkeypatch):
    """A scan over only healthy sessions recovers nothing and lists nothing."""
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("SKIP_NOTIFICATIONS", "1")
    _patch_reaper(monkeypatch)

    _synthesize_healthy(tmp_path, "healthy-1")
    _synthesize_healthy(tmp_path, "healthy-2")

    state_root = tmp_path / "cortex" / "lifecycle"
    results = guardian.scan_and_recover(state_root)

    assert results == []
