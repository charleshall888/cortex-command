"""Unit tests for OvernightState persistence (save_state / load_state).

Covers:
  TestIntegrationBranchesPersistence — round-trip serialization of
    integration_branches and backward-compatible loading of old state JSON
    that lacks the integration_branches key.
  TestIntegrationWorktreesPersistence — round-trip serialization of
    integration_worktrees and backward-compatible loading of old state JSON
    that lacks the integration_worktrees key.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from cortex_command.overnight.state import (
    OvernightFeatureStatus,
    OvernightState,
    load_state,
    save_state,
    sweep_blocker_failed_dependents,
)


class TestIntegrationBranchesPersistence(unittest.TestCase):
    """Tests for integration_branches serialization and backward compatibility."""

    def test_integration_branches_roundtrip(self):
        """OvernightState.integration_branches survives a save_state/load_state cycle."""
        expected = {"repo_a": "overnight/abc"}
        state = OvernightState(
            session_id="overnight-2026-01-01-0000",
            plan_ref="cortex/lifecycle/overnight-plan.md",
            phase="executing",
            integration_branches=expected,
        )

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        self.addCleanup(tmp_path.unlink, missing_ok=True)

        save_state(state, tmp_path)
        loaded = load_state(tmp_path)

        self.assertEqual(loaded.integration_branches, expected)

    def test_load_state_defaults_integration_branches_empty(self):
        """Loading a state JSON without integration_branches key returns empty dict."""
        minimal_state = {
            "session_id": "overnight-2025-12-31-2359",
            "plan_ref": "cortex/lifecycle/overnight-plan.md",
            "plan_hash": None,
            "current_round": 1,
            "phase": "executing",
            "features": {},
            "round_history": [],
            "started_at": "2025-12-31T23:59:00+00:00",
            "updated_at": "2025-12-31T23:59:00+00:00",
            "paused_from": None,
            "integration_branch": "overnight/overnight-2025-12-31-2359",
            "worktree_path": None,
            # NOTE: integration_branches key is intentionally absent
        }

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as tmp:
            json.dump(minimal_state, tmp)
            tmp_path = Path(tmp.name)
        self.addCleanup(tmp_path.unlink, missing_ok=True)

        loaded = load_state(tmp_path)

        self.assertEqual(loaded.integration_branches, {})


class TestIntegrationWorktreesPersistence(unittest.TestCase):
    """Tests for integration_worktrees serialization and backward compatibility."""

    def test_integration_worktrees_roundtrip(self):
        """OvernightState.integration_worktrees survives a save_state/load_state cycle."""
        expected = {"/abs/repo": "/tmp/wt"}
        state = OvernightState(
            session_id="overnight-2026-01-01-0000",
            plan_ref="cortex/lifecycle/overnight-plan.md",
            phase="executing",
            integration_worktrees=expected,
        )

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        self.addCleanup(tmp_path.unlink, missing_ok=True)

        save_state(state, tmp_path)
        loaded = load_state(tmp_path)

        self.assertEqual(loaded.integration_worktrees, expected)

    def test_load_state_defaults_integration_worktrees_empty(self):
        """Loading a state JSON without integration_worktrees key returns empty dict."""
        minimal_state = {
            "session_id": "overnight-2025-12-31-2359",
            "plan_ref": "cortex/lifecycle/overnight-plan.md",
            "plan_hash": None,
            "current_round": 1,
            "phase": "executing",
            "features": {},
            "round_history": [],
            "started_at": "2025-12-31T23:59:00+00:00",
            "updated_at": "2025-12-31T23:59:00+00:00",
            "paused_from": None,
            "integration_branch": "overnight/overnight-2025-12-31-2359",
            "worktree_path": None,
            # NOTE: integration_worktrees key is intentionally absent
        }

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as tmp:
            json.dump(minimal_state, tmp)
            tmp_path = Path(tmp.name)
        self.addCleanup(tmp_path.unlink, missing_ok=True)

        loaded = load_state(tmp_path)

        self.assertEqual(loaded.integration_worktrees, {})


class TestSweepBlockerFailedDependents(unittest.TestCase):
    """Tests for the end-of-round dependent-failure sweep helper."""

    @staticmethod
    def _state(features: dict[str, OvernightFeatureStatus]) -> OvernightState:
        return OvernightState(
            session_id="overnight-2026-01-01-0000",
            plan_ref="cortex/lifecycle/overnight-plan.md",
            phase="executing",
            features=features,
        )

    def test_pending_dependent_of_failed_blocker_fails(self):
        """A pending dependent of a failed blocker becomes failed (blocker_failed)."""
        state = self._state({
            "A": OvernightFeatureStatus(status="failed"),
            "B": OvernightFeatureStatus(
                status="pending", intra_session_blocked_by=["A"]
            ),
        })

        sweep_blocker_failed_dependents(state)

        self.assertEqual(state.features["B"].status, "failed")
        self.assertEqual(state.features["B"].error, "blocker_failed")

    def test_transitive_chain_fully_resolves(self):
        """A→B→C: when A fails, both B and C cascade to failed in one sweep."""
        state = self._state({
            "A": OvernightFeatureStatus(status="failed"),
            "B": OvernightFeatureStatus(
                status="pending", intra_session_blocked_by=["A"]
            ),
            "C": OvernightFeatureStatus(
                status="pending", intra_session_blocked_by=["B"]
            ),
        })

        sweep_blocker_failed_dependents(state)

        self.assertEqual(state.features["B"].status, "failed")
        self.assertEqual(state.features["B"].error, "blocker_failed")
        self.assertEqual(state.features["C"].status, "failed")
        self.assertEqual(state.features["C"].error, "blocker_failed")

    def test_paused_blocker_does_not_cascade(self):
        """A paused blocker (recoverable) leaves its dependent untouched."""
        state = self._state({
            "A": OvernightFeatureStatus(status="paused"),
            "B": OvernightFeatureStatus(
                status="pending", intra_session_blocked_by=["A"]
            ),
        })

        sweep_blocker_failed_dependents(state)

        self.assertEqual(state.features["B"].status, "pending")
        self.assertIsNone(state.features["B"].error)

    def test_paused_dependent_of_failed_blocker_is_swept(self):
        """A paused dependent of a failed blocker IS swept to failed.

        Distinct from a paused *blocker*: a paused dependent's blocker will
        never merge this session, so it is not recoverable and must terminate.
        """
        state = self._state({
            "A": OvernightFeatureStatus(status="failed"),
            "B": OvernightFeatureStatus(
                status="paused", intra_session_blocked_by=["A"]
            ),
        })

        sweep_blocker_failed_dependents(state)

        self.assertEqual(state.features["B"].status, "failed")
        self.assertEqual(state.features["B"].error, "blocker_failed")


class TestRecoverableBranchPersistence(unittest.TestCase):
    """Tests for recoverable_branch serialization and backward compatibility."""

    def test_recoverable_branch_roundtrip(self):
        """A non-None recoverable_branch survives a save_state/load_state cycle."""
        state = OvernightState(
            session_id="overnight-2026-01-01-0000",
            plan_ref="cortex/lifecycle/overnight-plan.md",
            phase="executing",
            features={
                "feat-a": OvernightFeatureStatus(
                    status="deferred", recoverable_branch="pipeline/feat-a-2"
                ),
            },
        )

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        self.addCleanup(tmp_path.unlink, missing_ok=True)

        save_state(state, tmp_path)
        loaded = load_state(tmp_path)

        self.assertEqual(
            loaded.features["feat-a"].recoverable_branch, "pipeline/feat-a-2"
        )

    def test_load_state_defaults_recoverable_branch_none(self):
        """A feature dict lacking recoverable_branch loads with the field None."""
        minimal_state = {
            "session_id": "overnight-2025-12-31-2359",
            "plan_ref": "cortex/lifecycle/overnight-plan.md",
            "plan_hash": None,
            "current_round": 1,
            "phase": "executing",
            "features": {
                # NOTE: recoverable_branch key is intentionally absent
                "feat-a": {"status": "deferred", "deferred_questions": 2},
            },
            "round_history": [],
            "started_at": "2025-12-31T23:59:00+00:00",
            "updated_at": "2025-12-31T23:59:00+00:00",
            "paused_from": None,
            "integration_branch": "overnight/overnight-2025-12-31-2359",
            "worktree_path": None,
        }

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as tmp:
            json.dump(minimal_state, tmp)
            tmp_path = Path(tmp.name)
        self.addCleanup(tmp_path.unlink, missing_ok=True)

        loaded = load_state(tmp_path)

        self.assertIsNone(loaded.features["feat-a"].recoverable_branch)


if __name__ == "__main__":
    unittest.main()
