"""Integration tests for Jinja2 template rendering.

Tests construct DashboardState with synthetic data, render base.html directly
via the Jinja2 environment (bypassing HTTP), and assert expected strings appear
in the rendered HTML.

Covers:
  - session panel with overnight data shows session_id
  - pipeline panel shows feature name and status badge
  - feature cards show "—" for None plan_progress
  - round history table shows round number
  - absent overnight renders "No active session."
  - absent pipeline renders "No active pipeline."
  - round_history empty list renders "No completed rounds yet."
"""

from __future__ import annotations

import unittest

from cortex_command.dashboard.app import templates
from cortex_command.dashboard.poller import DashboardState


def _make_overnight_fixture() -> dict:
    """Return a minimal overnight-state dict for rendering tests."""
    return {
        "session_id": "test-session-001",
        "current_round": 2,
        "phase": "running",
        "started_at": "2026-02-26T10:00:00+00:00",
        "features": {
            "feat-alpha": {
                "status": "merged",
                "started_at": "2026-02-26T10:00:00+00:00",
            },
            "feat-beta": {
                "status": "pending",
                "started_at": "2026-02-26T10:00:00+00:00",
            },
        },
        "round_history": [],
    }


def _make_feature_states_fixture() -> dict:
    """Return a minimal feature_states dict for rendering tests."""
    return {
        "feat-alpha": {
            "current_phase": "complete",
            "phase_transitions": [{"from": "research", "to": "complete", "ts": "2026-02-26T11:00:00+00:00"}],
            "rework_cycles": 0,
            "plan_progress": (3, 5),
        },
        "feat-beta": {
            "current_phase": None,
            "phase_transitions": [],
            "rework_cycles": 0,
            "plan_progress": None,
        },
    }


def _render(state: DashboardState) -> str:
    """Render base.html with the given state, returning the HTML string."""
    return templates.env.get_template("base.html").render(state=state)


class TestSessionPanel(unittest.TestCase):
    """Tests for session_panel.html inclusion."""

    def test_shows_session_id_when_overnight_present(self):
        state = DashboardState()
        state.overnight = _make_overnight_fixture()
        state.feature_states = _make_feature_states_fixture()
        html = _render(state)
        self.assertIn("test-session-001", html)

    def test_shows_current_round(self):
        state = DashboardState()
        state.overnight = _make_overnight_fixture()
        state.feature_states = _make_feature_states_fixture()
        html = _render(state)
        self.assertIn("Round 2", html)

    def test_shows_no_active_session_when_overnight_absent(self):
        state = DashboardState()
        # state.overnight is None by default
        html = _render(state)
        self.assertIn("No active session", html)

    def test_merged_badge_appears_when_feature_merged(self):
        state = DashboardState()
        state.overnight = _make_overnight_fixture()
        state.feature_states = _make_feature_states_fixture()
        html = _render(state)
        self.assertIn("merged", html)


class TestPipelinePanel(unittest.TestCase):
    """Tests for pipeline_panel.html inclusion."""

    def test_shows_feature_name_when_pipeline_present(self):
        state = DashboardState()
        state.pipeline = {
            "phase": "executing",
            "features": [{"name": "my-pipeline-feature", "status": "implementing"}],
        }
        html = _render(state)
        self.assertIn("my-pipeline-feature", html)

    def test_shows_no_active_pipeline_when_absent(self):
        state = DashboardState()
        # state.pipeline is None by default
        html = _render(state)
        self.assertIn("No active pipeline.", html)

    def test_shows_phase(self):
        state = DashboardState()
        state.pipeline = {
            "phase": "executing",
            "features": [{"name": "feat", "status": "implementing"}],
        }
        html = _render(state)
        self.assertIn("executing", html)


class TestFeatureCards(unittest.TestCase):
    """Tests for feature_cards.html inclusion."""

    def test_shows_dash_for_none_plan_progress(self):
        state = DashboardState()
        state.overnight = _make_overnight_fixture()
        state.feature_states = {
            "feat-alpha": {
                "current_phase": None,
                "phase_transitions": [],
                "rework_cycles": 0,
                "plan_progress": None,
            },
            "feat-beta": {
                "current_phase": None,
                "phase_transitions": [],
                "rework_cycles": 0,
                "plan_progress": None,
            },
        }
        html = _render(state)
        self.assertIn("—", html)

    def test_shows_task_ratio_when_plan_progress_present(self):
        state = DashboardState()
        state.overnight = _make_overnight_fixture()
        state.feature_states = {
            "feat-alpha": {
                "current_phase": "implement",
                "phase_transitions": [],
                "rework_cycles": 0,
                "plan_progress": (3, 5),
            },
            "feat-beta": {
                "current_phase": None,
                "phase_transitions": [],
                "rework_cycles": 0,
                "plan_progress": None,
            },
        }
        html = _render(state)
        self.assertIn("3/5 tasks", html)

    def test_shows_feature_slug(self):
        state = DashboardState()
        state.overnight = _make_overnight_fixture()
        state.feature_states = _make_feature_states_fixture()
        html = _render(state)
        self.assertIn("feat-alpha", html)
        self.assertIn("feat-beta", html)

    def test_shows_no_features_active_when_overnight_absent(self):
        state = DashboardState()
        html = _render(state)
        self.assertIn("No features active.", html)


class TestRoundHistory(unittest.TestCase):
    """Tests for round_history.html inclusion."""

    def test_shows_round_number_in_table(self):
        state = DashboardState()
        overnight = _make_overnight_fixture()
        overnight["round_history"] = [
            {
                "round_number": 1,
                "started_at": "2026-02-26T09:00:00+00:00",
                "completed_at": "2026-02-26T10:00:00+00:00",
                "features_merged": ["feat-alpha"],
                "features_paused": [],
                "features_deferred": [],
            }
        ]
        state.overnight = overnight
        state.feature_states = _make_feature_states_fixture()
        html = _render(state)
        self.assertIn("<td>1</td>", html)

    def test_shows_merged_count(self):
        state = DashboardState()
        overnight = _make_overnight_fixture()
        overnight["round_history"] = [
            {
                "round_number": 1,
                "started_at": "2026-02-26T09:00:00+00:00",
                "completed_at": "2026-02-26T10:00:00+00:00",
                "features_merged": ["feat-alpha", "feat-beta"],
                "features_paused": [],
                "features_deferred": [],
            }
        ]
        state.overnight = overnight
        state.feature_states = _make_feature_states_fixture()
        html = _render(state)
        self.assertIn("<td>2</td>", html)

    def test_shows_no_completed_rounds_when_history_empty(self):
        state = DashboardState()
        overnight = _make_overnight_fixture()
        overnight["round_history"] = []
        state.overnight = overnight
        state.feature_states = _make_feature_states_fixture()
        html = _render(state)
        self.assertIn("No completed rounds yet.", html)

    def test_shows_no_completed_rounds_when_overnight_absent(self):
        state = DashboardState()
        html = _render(state)
        self.assertIn("No completed rounds yet.", html)


class TestStructuralElements(unittest.TestCase):
    """Tests that verify required structural elements are present."""

    def test_round_history_section_exists(self):
        state = DashboardState()
        html = _render(state)
        self.assertIn('id="round-history"', html)

    def test_session_panel_section_exists(self):
        state = DashboardState()
        html = _render(state)
        self.assertIn('id="session-panel"', html)

    def test_pipeline_panel_section_exists(self):
        state = DashboardState()
        html = _render(state)
        self.assertIn('id="pipeline-panel"', html)

    def test_feature_cards_section_exists(self):
        state = DashboardState()
        html = _render(state)
        self.assertIn('id="feature-cards"', html)


if __name__ == "__main__":
    unittest.main()
