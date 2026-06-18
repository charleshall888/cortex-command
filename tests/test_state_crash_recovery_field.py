"""Tests for the session-level crash-recovery state field.

Covers lifecycle ``overnight-run-now-runner-left-session`` Task 1 — the
``OvernightState.crash_recovery_attempts`` counter that the out-of-process
recovery core increments and the ``cortex overnight start`` resume guard reads
to refuse crash-looping into a deterministic failure.

Two cases:
    (a) construct + save_state + load_state round-trip preserves a non-zero
        ``crash_recovery_attempts``;
    (b) a hand-written legacy state JSON lacking the key loads with the
        backward-compatible default of ``0``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cortex_command.overnight.state import (
    OvernightState,
    load_state,
    save_state,
)


def test_crash_recovery_attempts_round_trip(tmp_path: Path):
    """save_state then load_state preserves a non-zero crash_recovery_attempts."""
    state_path = tmp_path / "overnight-state.json"
    state = OvernightState(
        session_id="overnight-2026-06-17-2200",
        plan_ref="/tmp/plan.md",
        crash_recovery_attempts=2,
    )

    save_state(state, state_path)
    loaded = load_state(state_path)

    assert loaded.crash_recovery_attempts == 2


def test_crash_recovery_attempts_defaults_to_zero_on_legacy_state(tmp_path: Path):
    """A legacy state file lacking the key loads with crash_recovery_attempts == 0."""
    state_path = tmp_path / "overnight-state.json"
    legacy = {
        "session_id": "overnight-legacy",
        "plan_ref": "/tmp/plan.md",
        "current_round": 1,
        "phase": "executing",
        "features": {},
        "round_history": [],
        "started_at": "2026-06-17T22:00:00+00:00",
        "updated_at": "2026-06-17T22:00:00+00:00",
        # Note: no "crash_recovery_attempts" key.
    }
    state_path.write_text(json.dumps(legacy), encoding="utf-8")

    loaded = load_state(state_path)

    assert loaded.crash_recovery_attempts == 0


def test_crash_recovery_attempts_rejects_negative():
    """A negative crash_recovery_attempts is rejected by __post_init__."""
    with pytest.raises(ValueError, match="crash_recovery_attempts"):
        OvernightState(crash_recovery_attempts=-1)
