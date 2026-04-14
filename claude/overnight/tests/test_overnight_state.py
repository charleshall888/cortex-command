#!/usr/bin/env python3
"""Tests for OvernightFeatureStatus recovery_attempts and recovery_depth fields.

Verifies four requirements:
(a) default values, (b) save/load round-trip, (c) interrupt reset preservation,
(d) negative value validation.
"""

import json
import tempfile
import pytest
from pathlib import Path

from claude.overnight.state import OvernightFeatureStatus, OvernightState
from claude.overnight.state import save_state, load_state, save_batch_result
from claude.overnight.orchestrator import BatchResult
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


# ---------------------------------------------------------------------------
# Test (f): save_batch_result round-trip with extra_fields
# ---------------------------------------------------------------------------

def test_save_batch_result_fields_and_extra_fields() -> None:
    """save_batch_result writes JSON containing all BatchResult fields and extra_fields."""
    with tempfile.TemporaryDirectory() as tmp:
        result_path = Path(tmp) / "batch-1-results.json"

        batch = BatchResult(
            batch_id=1,
            features_merged=["feat-a"],
            features_paused=[{"name": "feat-b", "error": "timeout"}],
            features_deferred=[{"name": "feat-c", "question_count": 2}],
            features_failed=[{"name": "feat-d", "error": "crash"}],
            circuit_breaker_fired=False,
            global_abort_signal=False,
            abort_reason=None,
            key_files_changed={"feat-a": ["src/main.py"]},
        )

        extra = {"throttle_stats": {"total": 0, "delays": []}}
        save_batch_result(batch, result_path, extra_fields=extra)

        data = json.loads(result_path.read_text(encoding="utf-8"))

        # All BatchResult dataclass fields must be present
        if data["batch_id"] != 1:
            pytest.fail(f"expected batch_id=1, got {data['batch_id']!r}")
            return
        if data["features_merged"] != ["feat-a"]:
            pytest.fail(f"expected features_merged=['feat-a'], got {data['features_merged']!r}")
            return
        if len(data["features_paused"]) != 1:
            pytest.fail(f"expected 1 paused feature, got {len(data['features_paused'])}")
            return
        if len(data["features_deferred"]) != 1:
            pytest.fail(f"expected 1 deferred feature, got {len(data['features_deferred'])}")
            return
        if len(data["features_failed"]) != 1:
            pytest.fail(f"expected 1 failed feature, got {len(data['features_failed'])}")
            return
        if data["circuit_breaker_fired"] is not False:
            pytest.fail(f"expected circuit_breaker_fired=False, got {data['circuit_breaker_fired']!r}")
            return
        if data["global_abort_signal"] is not False:
            pytest.fail(f"expected global_abort_signal=False, got {data['global_abort_signal']!r}")
            return
        if data["key_files_changed"] != {"feat-a": ["src/main.py"]}:
            pytest.fail(f"unexpected key_files_changed: {data['key_files_changed']!r}")
            return

        # extra_fields must be merged into the top-level JSON
        if "throttle_stats" not in data:
            pytest.fail("throttle_stats missing from written JSON")
            return
        if data["throttle_stats"] != {"total": 0, "delays": []}:
            pytest.fail(f"unexpected throttle_stats: {data['throttle_stats']!r}")
            return
