"""Tests for OvernightState.paused_reason field.

Covers:
  (a) default value is None
  (b) save/load round-trip preserves the value
  (c) paused_reason is preserved through handle_interrupted_features()
  (d) old state JSON without paused_reason key loads cleanly (backward compat)
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from cortex_command.overnight.interrupt import handle_interrupted_features
from cortex_command.overnight.state import OvernightFeatureStatus, OvernightState, load_state, save_state


# ---------------------------------------------------------------------------
# (a) Default value
# ---------------------------------------------------------------------------

def test_paused_reason_default_none() -> None:
    """OvernightState() has paused_reason == None by default."""
    state = OvernightState()
    if state.paused_reason is not None:
        pytest.fail(f"expected paused_reason=None, got {state.paused_reason!r}")


# ---------------------------------------------------------------------------
# (b) Round-trip serialization
# ---------------------------------------------------------------------------

def test_paused_reason_round_trip() -> None:
    """paused_reason='budget_exhausted' survives a save_state/load_state cycle."""
    with tempfile.TemporaryDirectory() as tmp:
        state_path = Path(tmp) / "overnight-state.json"

        state = OvernightState(
            session_id="overnight-2026-01-01-0000",
            plan_ref="cortex/lifecycle/overnight-plan.md",
            phase="paused",
            paused_from="executing",
            paused_reason="budget_exhausted",
        )

        save_state(state, state_path)
        loaded = load_state(state_path)

        if loaded.paused_reason != "budget_exhausted":
            pytest.fail(
                f"expected paused_reason='budget_exhausted', got {loaded.paused_reason!r}"
            )


# ---------------------------------------------------------------------------
# (c) Preservation through handle_interrupted_features()
# ---------------------------------------------------------------------------

def test_paused_reason_preserved_through_interrupt() -> None:
    """handle_interrupted_features() does not reset paused_reason."""
    with tempfile.TemporaryDirectory() as tmp:
        state_path = Path(tmp) / "overnight-state.json"

        # No running features — interrupt has nothing to do but must still
        # preserve paused_reason through the load/save cycle.
        state = OvernightState(
            session_id="overnight-2026-01-01-0001",
            plan_ref="cortex/lifecycle/overnight-plan.md",
            phase="paused",
            paused_from="executing",
            paused_reason="stall_timeout",
            features={
                "feature-a": OvernightFeatureStatus(status="pending"),
            },
        )

        save_state(state, state_path)
        handle_interrupted_features(state_path)
        loaded = load_state(state_path)

        if loaded.paused_reason != "stall_timeout":
            pytest.fail(
                f"expected paused_reason='stall_timeout' after interrupt, "
                f"got {loaded.paused_reason!r}"
            )


# ---------------------------------------------------------------------------
# (d) Backward compatibility — missing key in old state JSON
# ---------------------------------------------------------------------------

def test_load_state_missing_paused_reason_defaults_none() -> None:
    """Loading a state JSON without paused_reason key returns paused_reason=None."""
    minimal_state = {
        "session_id": "overnight-2025-12-31-2359",
        "plan_ref": "cortex/lifecycle/overnight-plan.md",
        "plan_hash": None,
        "current_round": 1,
        "phase": "paused",
        "features": {},
        "round_history": [],
        "started_at": "2025-12-31T23:59:00+00:00",
        "updated_at": "2025-12-31T23:59:00+00:00",
        "paused_from": "executing",
        "integration_branch": None,
        "integration_branches": {},
        "worktree_path": None,
        "project_root": None,
        # NOTE: paused_reason key is intentionally absent
    }

    with tempfile.NamedTemporaryFile(
        suffix=".json", delete=False, mode="w"
    ) as tmp:
        json.dump(minimal_state, tmp)
        tmp_path = Path(tmp.name)

    try:
        loaded = load_state(tmp_path)
        if loaded.paused_reason is not None:
            pytest.fail(
                f"expected paused_reason=None for old state without key, "
                f"got {loaded.paused_reason!r}"
            )
    finally:
        tmp_path.unlink(missing_ok=True)
