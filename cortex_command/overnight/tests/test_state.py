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

from cortex_command.overnight.state import OvernightState, load_state, save_state


class TestIntegrationBranchesPersistence(unittest.TestCase):
    """Tests for integration_branches serialization and backward compatibility."""

    def test_integration_branches_roundtrip(self):
        """OvernightState.integration_branches survives a save_state/load_state cycle."""
        expected = {"repo_a": "overnight/abc"}
        state = OvernightState(
            session_id="overnight-2026-01-01-0000",
            plan_ref="lifecycle/overnight-plan.md",
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
            "plan_ref": "lifecycle/overnight-plan.md",
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
            plan_ref="lifecycle/overnight-plan.md",
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
            "plan_ref": "lifecycle/overnight-plan.md",
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


if __name__ == "__main__":
    unittest.main()
