#!/usr/bin/env python3
"""Tests for OvernightFeatureStatus recovery_attempts and recovery_depth fields.

Verifies four requirements:
(a) default values, (b) save/load round-trip, (c) interrupt reset preservation,
(d) negative value validation.
"""

import tempfile
import pytest
from pathlib import Path

from claude.overnight.state import OvernightFeatureStatus, OvernightState
from claude.overnight.state import save_state, load_state
from claude.overnight.interrupt import handle_interrupted_features


# ---------------------------------------------------------------------------
# Test (a): default values
# ---------------------------------------------------------------------------

def test_defaults() -> None:
    """OvernightFeatureStatus() has recovery_attempts == 0 and recovery_depth == 0."""
    fs = OvernightFeatureStatus()
    if fs.recovery_attempts != 0:
        pytest.fail(f"expected recovery_attempts=0, got {fs.recovery_attempts!r}")
        return
    if fs.recovery_depth != 0:
        pytest.fail(f"expected recovery_depth=0, got {fs.recovery_depth!r}")
        return


# ---------------------------------------------------------------------------
# Test (b): save/load round-trip
# ---------------------------------------------------------------------------

def test_round_trip() -> None:
    """State with recovery_attempts=1, recovery_depth=1 survives save/load."""
    with tempfile.TemporaryDirectory() as tmp:
        state_path = Path(tmp) / "overnight-state.json"

        state = OvernightState(
            session_id="test-session",
            plan_ref="lifecycle/test/plan.md",
            features={
                "feature-a": OvernightFeatureStatus(
                    recovery_attempts=1,
                    recovery_depth=1,
                ),
            },
        )

        save_state(state, state_path)
        loaded = load_state(state_path)

        fs = loaded.features.get("feature-a")
        if fs is None:
            pytest.fail("feature-a not found after load")
            return
        if fs.recovery_attempts != 1:
            pytest.fail(f"expected recovery_attempts=1, got {fs.recovery_attempts!r}")
            return
        if fs.recovery_depth != 1:
            pytest.fail(f"expected recovery_depth=1, got {fs.recovery_depth!r}")
            return


# ---------------------------------------------------------------------------
# Test (c): interrupt reset preservation
# ---------------------------------------------------------------------------

def test_interrupt_preservation() -> None:
    """handle_interrupted_features preserves recovery_attempts and resets status to pending."""
    with tempfile.TemporaryDirectory() as tmp:
        state_path = Path(tmp) / "overnight-state.json"

        state = OvernightState(
            session_id="test-session-interrupt",
            plan_ref="lifecycle/test/plan.md",
            features={
                "feature-b": OvernightFeatureStatus(
                    status="running",
                    recovery_attempts=1,
                ),
            },
        )

        save_state(state, state_path)
        handle_interrupted_features(state_path)
        loaded = load_state(state_path)

        fs = loaded.features.get("feature-b")
        if fs is None:
            pytest.fail("feature-b not found after interrupt handling")
            return
        if fs.recovery_attempts != 1:
            pytest.fail(f"expected recovery_attempts=1 preserved, got {fs.recovery_attempts!r}")
            return
        if fs.status != "pending":
            pytest.fail(f"expected status='pending' after interrupt, got {fs.status!r}")
            return


# ---------------------------------------------------------------------------
# Test (d): negative value validation
# ---------------------------------------------------------------------------

def test_negative_validation() -> None:
    """OvernightFeatureStatus raises ValueError for negative recovery_attempts and recovery_depth."""
    try:
        OvernightFeatureStatus(recovery_attempts=-1)
        pytest.fail("expected ValueError for recovery_attempts=-1, but no exception was raised")
        return
    except ValueError:
        pass

    try:
        OvernightFeatureStatus(recovery_depth=-1)
        pytest.fail("expected ValueError for recovery_depth=-1, but no exception was raised")
        return
    except ValueError:
        pass


# ---------------------------------------------------------------------------
# Test (e): repo_path round-trip
# ---------------------------------------------------------------------------

def test_repo_path_round_trip() -> None:
    """State with repo_path survives save/load; default is None."""
    # Verify default is None
    default_fs = OvernightFeatureStatus()
    if default_fs.repo_path is not None:
        pytest.fail(f"expected default repo_path=None, got {default_fs.repo_path!r}")
        return

    with tempfile.TemporaryDirectory() as tmp:
        state_path = Path(tmp) / "overnight-state.json"

        state = OvernightState(
            session_id="test-session-repo-path",
            plan_ref="lifecycle/test/plan.md",
            features={
                "feature-c": OvernightFeatureStatus(
                    repo_path="~/Workspaces/other-repo",
                ),
            },
        )

        save_state(state, state_path)
        loaded = load_state(state_path)

        fs = loaded.features.get("feature-c")
        if fs is None:
            pytest.fail("feature-c not found after load")
            return
        if fs.repo_path != "~/Workspaces/other-repo":
            pytest.fail(f"expected repo_path='~/Workspaces/other-repo', got {fs.repo_path!r}")
            return
