"""Unit tests for map_results.py — batch result mapping to state and strategy.

Covers:
  TestAllFourStatusMappings — results file with one feature per bucket;
    verifies correct statuses, error fields, and deferred_questions.
  TestMissingResultsFallback — no results file; batch plan features marked
    failed with the expected error message.
  TestFallbackRespectsTerminalStatus — merged feature not overwritten when
    results file is missing.
  TestStrategyRoundHistory — results file with merged feature and
    key_files_changed; verifies strategy.round_history_notes entry.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from cortex_command.overnight.map_results import (
    _handle_missing_results,
    _map_results_to_state,
    _update_strategy,
)
from cortex_command.overnight.state import (
    OvernightFeatureStatus,
    OvernightState,
    RoundSummary,
    load_state,
    save_state,
)
from cortex_command.overnight.strategy import OvernightStrategy, load_strategy, save_strategy


def _make_state(features: dict[str, OvernightFeatureStatus] | None = None) -> OvernightState:
    """Create a minimal OvernightState for testing."""
    return OvernightState(
        session_id="overnight-test-0000",
        plan_ref="lifecycle/test-plan.md",
        phase="executing",
        features=features or {},
    )


def _write_state(state: OvernightState, path: Path) -> None:
    """Save state to *path* (convenience wrapper)."""
    save_state(state, path)


def _write_strategy(strategy: OvernightStrategy, path: Path) -> None:
    """Save strategy to *path* (convenience wrapper)."""
    save_strategy(strategy, path)


def _write_master_plan(plan_path: Path, feature_names: list[str]) -> None:
    """Write a minimal master-plan markdown that parse_master_plan can parse.

    Creates a valid Features table with one row per *feature_names* entry.
    """
    rows = []
    for i, name in enumerate(feature_names, start=1):
        rows.append(f"| {i} | {name} | simple | 1 | summary |")

    plan_text = (
        "# Master Plan: test-plan\n\n"
        "## Features\n\n"
        "| Priority | Name | Complexity | Tasks | Summary |\n"
        "|----------|------|------------|-------|---------|\n"
        + "\n".join(rows)
        + "\n"
    )
    plan_path.write_text(plan_text, encoding="utf-8")


class TestAllFourStatusMappings(unittest.TestCase):
    """Results file present with one feature per status bucket."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._tmp = Path(self._tmpdir.name)
        self._state_path = self._tmp / "overnight-state.json"

        # Create initial state with all four features pending
        state = _make_state(
            features={
                "feat-merged": OvernightFeatureStatus(status="pending"),
                "feat-paused": OvernightFeatureStatus(status="pending"),
                "feat-deferred": OvernightFeatureStatus(status="pending"),
                "feat-failed": OvernightFeatureStatus(status="pending"),
            }
        )
        _write_state(state, self._state_path)

        self._results = {
            "features_merged": ["feat-merged"],
            "features_paused": [
                {"name": "feat-paused", "error": "CI red on integration branch"},
            ],
            "features_deferred": [
                {"name": "feat-deferred", "question_count": 3},
            ],
            "features_failed": [
                {"name": "feat-failed", "error": "timeout after 10 min"},
            ],
        }

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_merged_status_and_no_error(self):
        """Merged feature has status='merged' and error=None."""
        _map_results_to_state(self._results, self._state_path, batch_id=1)
        state = load_state(self._state_path)
        fs = state.features["feat-merged"]
        self.assertEqual(fs.status, "merged")
        self.assertIsNone(fs.error)

    def test_paused_status_and_error(self):
        """Paused feature has status='paused' and the correct error string."""
        _map_results_to_state(self._results, self._state_path, batch_id=1)
        state = load_state(self._state_path)
        fs = state.features["feat-paused"]
        self.assertEqual(fs.status, "paused")
        self.assertEqual(fs.error, "CI red on integration branch")

    def test_deferred_status_and_question_count(self):
        """Deferred feature has status='deferred' and deferred_questions=3."""
        _map_results_to_state(self._results, self._state_path, batch_id=1)
        state = load_state(self._state_path)
        fs = state.features["feat-deferred"]
        self.assertEqual(fs.status, "deferred")
        self.assertEqual(fs.deferred_questions, 3)

    def test_failed_status_and_error(self):
        """Failed feature has status='failed' and the correct error string."""
        _map_results_to_state(self._results, self._state_path, batch_id=1)
        state = load_state(self._state_path)
        fs = state.features["feat-failed"]
        self.assertEqual(fs.status, "failed")
        self.assertEqual(fs.error, "timeout after 10 min")


class TestMissingResultsFallback(unittest.TestCase):
    """No results file — pending features marked failed with no-results message."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._tmp = Path(self._tmpdir.name)
        self._state_path = self._tmp / "overnight-state.json"
        self._plan_path = self._tmp / "batch-plan-round-1.md"

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_pending_features_marked_failed(self):
        """Two pending features both get status='failed' with the expected message."""
        state = _make_state(
            features={
                "alpha": OvernightFeatureStatus(status="pending"),
                "beta": OvernightFeatureStatus(status="pending"),
            }
        )
        _write_state(state, self._state_path)
        _write_master_plan(self._plan_path, ["alpha", "beta"])

        _handle_missing_results(self._plan_path, self._state_path)

        state = load_state(self._state_path)
        for name in ("alpha", "beta"):
            fs = state.features[name]
            self.assertEqual(fs.status, "failed", f"{name} should be failed")
            self.assertEqual(
                fs.error,
                "batch_runner.py did not produce results file",
                f"{name} should have the no-results error",
            )


class TestFallbackRespectsTerminalStatus(unittest.TestCase):
    """Merged feature not overwritten when results file is missing."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._tmp = Path(self._tmpdir.name)
        self._state_path = self._tmp / "overnight-state.json"
        self._plan_path = self._tmp / "batch-plan-round-2.md"

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_merged_not_overwritten(self):
        """A feature already at 'merged' stays 'merged' after fallback."""
        state = _make_state(
            features={
                "already-merged": OvernightFeatureStatus(status="merged"),
                "still-pending": OvernightFeatureStatus(status="pending"),
            }
        )
        _write_state(state, self._state_path)
        _write_master_plan(
            self._plan_path, ["already-merged", "still-pending"]
        )

        _handle_missing_results(self._plan_path, self._state_path)

        state = load_state(self._state_path)
        self.assertEqual(state.features["already-merged"].status, "merged")
        self.assertEqual(state.features["still-pending"].status, "failed")

    def test_failed_not_overwritten(self):
        """A feature already at 'failed' stays 'failed' (terminal) after fallback."""
        state = _make_state(
            features={
                "prev-failed": OvernightFeatureStatus(
                    status="failed", error="original error"
                ),
            }
        )
        _write_state(state, self._state_path)
        _write_master_plan(self._plan_path, ["prev-failed"])

        _handle_missing_results(self._plan_path, self._state_path)

        state = load_state(self._state_path)
        fs = state.features["prev-failed"]
        self.assertEqual(fs.status, "failed")
        # Original error preserved — not overwritten by fallback message
        self.assertEqual(fs.error, "original error")

    def test_deferred_not_overwritten(self):
        """A feature already at 'deferred' stays 'deferred' (terminal) after fallback."""
        state = _make_state(
            features={
                "prev-deferred": OvernightFeatureStatus(status="deferred"),
            }
        )
        _write_state(state, self._state_path)
        _write_master_plan(self._plan_path, ["prev-deferred"])

        _handle_missing_results(self._plan_path, self._state_path)

        state = load_state(self._state_path)
        self.assertEqual(state.features["prev-deferred"].status, "deferred")


class TestStrategyRoundHistory(unittest.TestCase):
    """Results with merged feature and key_files_changed updates strategy."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._tmp = Path(self._tmpdir.name)
        self._strategy_path = self._tmp / "overnight-strategy.json"

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_round_history_note_format(self):
        """round_history_notes gets one entry with the expected format."""
        _write_strategy(OvernightStrategy(), self._strategy_path)

        results = {
            "features_merged": ["cool-feature"],
            "features_paused": [],
            "features_deferred": [],
            "features_failed": [],
            "key_files_changed": {
                "cool-feature": ["src/main.py", "src/utils.py"],
            },
        }

        _update_strategy(results, batch_id=2, strategy_path=self._strategy_path)

        strategy = load_strategy(self._strategy_path)
        self.assertEqual(len(strategy.round_history_notes), 1)
        note = strategy.round_history_notes[0]
        self.assertIn("Round 2", note)
        self.assertIn("merged 1 features", note)
        self.assertIn("cool-feature", note)
        self.assertIn("0 paused", note)

    def test_hot_files_accumulated_from_key_files_changed(self):
        """Files touched by merged features appear in hot_files when threshold met."""
        # Pre-seed strategy with existing hot_files so that any file touched
        # by a merged feature will cross the >= 2 threshold.
        initial_strategy = OvernightStrategy(hot_files=["src/main.py"])
        _write_strategy(initial_strategy, self._strategy_path)

        results = {
            "features_merged": ["feat-a"],
            "features_paused": [],
            "features_deferred": [],
            "features_failed": [],
            "key_files_changed": {
                "feat-a": ["src/main.py", "src/new.py"],
            },
        }

        _update_strategy(results, batch_id=1, strategy_path=self._strategy_path)

        strategy = load_strategy(self._strategy_path)
        # src/main.py was already hot + touched by feat-a => stays hot
        self.assertIn("src/main.py", strategy.hot_files)
        # src/new.py was only touched by one feature => not hot
        self.assertNotIn("src/new.py", strategy.hot_files)

    def test_multiple_merged_features_make_shared_file_hot(self):
        """A file touched by two merged features becomes hot from scratch."""
        _write_strategy(OvernightStrategy(), self._strategy_path)

        results = {
            "features_merged": ["feat-x", "feat-y"],
            "features_paused": [],
            "features_deferred": [],
            "features_failed": [],
            "key_files_changed": {
                "feat-x": ["shared.py"],
                "feat-y": ["shared.py", "only-y.py"],
            },
        }

        _update_strategy(results, batch_id=1, strategy_path=self._strategy_path)

        strategy = load_strategy(self._strategy_path)
        self.assertIn("shared.py", strategy.hot_files)
        self.assertNotIn("only-y.py", strategy.hot_files)

    def test_round_history_appends_not_replaces(self):
        """A second call appends a second round history note."""
        initial_strategy = OvernightStrategy(
            round_history_notes=["Round 1: merged 1 features (alpha), 0 paused."]
        )
        _write_strategy(initial_strategy, self._strategy_path)

        results = {
            "features_merged": ["beta"],
            "features_paused": [{"name": "gamma", "error": "flaky"}],
            "features_deferred": [],
            "features_failed": [],
        }

        _update_strategy(results, batch_id=2, strategy_path=self._strategy_path)

        strategy = load_strategy(self._strategy_path)
        self.assertEqual(len(strategy.round_history_notes), 2)
        self.assertIn("Round 1", strategy.round_history_notes[0])
        note2 = strategy.round_history_notes[1]
        self.assertIn("Round 2", note2)
        self.assertIn("1 paused", note2)


class TestRoundHistoryPopulation(unittest.TestCase):
    """_map_results_to_state populates round_history with RoundSummary entries."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._tmp = Path(self._tmpdir.name)
        self._state_path = self._tmp / "overnight-state.json"
        state = _make_state()
        _write_state(state, self._state_path)

    def tearDown(self):
        self._tmpdir.cleanup()

    def _make_results(self, features_merged: list[str]) -> dict:
        return {
            "features_merged": features_merged,
            "features_paused": [],
            "features_deferred": [],
            "features_failed": [],
        }

    def test_features_merged_populated(self):
        """batch_id=2 with two merged features writes one RoundSummary entry."""
        _map_results_to_state(
            self._make_results(["feat-x", "feat-y"]),
            self._state_path,
            batch_id=2,
        )
        state = load_state(self._state_path)
        self.assertEqual(len(state.round_history), 1)
        rs = state.round_history[0]
        self.assertEqual(rs.round_number, 2)
        self.assertEqual(rs.features_merged, ["feat-x", "feat-y"])

    def test_empty_merge_round_written(self):
        """batch_id=1 with no merged features writes one entry with empty list."""
        _map_results_to_state(
            self._make_results([]),
            self._state_path,
            batch_id=1,
        )
        state = load_state(self._state_path)
        self.assertEqual(len(state.round_history), 1)
        rs = state.round_history[0]
        self.assertEqual(rs.round_number, 1)
        self.assertEqual(rs.features_merged, [])

    def test_idempotent_nonempty(self):
        """Calling twice with same batch_id and features leaves exactly one entry."""
        results = self._make_results(["feat-a"])
        _map_results_to_state(results, self._state_path, batch_id=1)
        _map_results_to_state(results, self._state_path, batch_id=1)
        state = load_state(self._state_path)
        self.assertEqual(len(state.round_history), 1)
        self.assertEqual(state.round_history[0].features_merged, ["feat-a"])

    def test_idempotent_different_data(self):
        """Second call with different features for same batch_id is discarded (first-write-wins)."""
        _map_results_to_state(
            self._make_results(["feat-a"]),
            self._state_path,
            batch_id=1,
        )
        _map_results_to_state(
            self._make_results(["feat-b"]),
            self._state_path,
            batch_id=1,
        )
        state = load_state(self._state_path)
        self.assertEqual(len(state.round_history), 1)
        self.assertEqual(state.round_history[0].features_merged, ["feat-a"])

    def test_upsert_replaces_empty(self):
        """Pre-existing RoundSummary with empty list is replaced by non-empty call."""
        # Pre-write state with a round 1 entry that has no merged features
        state = load_state(self._state_path)
        state.round_history.append(RoundSummary(round_number=1, features_merged=[]))
        _write_state(state, self._state_path)

        _map_results_to_state(
            self._make_results(["feat-x"]),
            self._state_path,
            batch_id=1,
        )
        state = load_state(self._state_path)
        self.assertEqual(len(state.round_history), 1)
        self.assertEqual(state.round_history[0].features_merged, ["feat-x"])


if __name__ == "__main__":
    unittest.main()
