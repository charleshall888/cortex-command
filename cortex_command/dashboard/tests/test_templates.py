"""Integration tests for Jinja2 template rendering.

Tests construct DashboardState with synthetic data and render templates directly
via the Jinja2 environment (bypassing HTTP), then assert expected strings appear
in the rendered HTML.

Since the 2026-05-18 htmx redesign, base.html ships only empty section shells and
loads each panel's real content at runtime via ``hx-get="/partials/..."``. Panel
content tests therefore render the matching partial directly (mirroring the
``/partials/*`` route handler's template + context), while structural tests still
render base.html to assert the section shells exist.

Covers:
  - session panel with overnight data shows session_id and "round · N"
  - pipeline panel shows feature name and status badge
  - feature cards show task ratio "N / M tasks" and feature slugs
  - round history table shows the round id span and merged count
  - absent overnight renders "no active session"
  - absent pipeline renders "no pipeline · refinement queue empty"
  - round_history empty list renders "no rounds cleared yet"
"""

from __future__ import annotations

import types
import unittest

from cortex_command.dashboard.app import templates
from cortex_command.dashboard.poller import DashboardState


def _fake_request(path: str = "/") -> types.SimpleNamespace:
    """Minimal stand-in for the Starlette Request the app injects via request-first
    TemplateResponse. base.html reads only ``request.url.path`` (for nav highlighting),
    so a namespace exposing ``.url.path`` is sufficient for direct-render tests."""
    return types.SimpleNamespace(url=types.SimpleNamespace(path=path))


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
    return templates.env.get_template("base.html").render(state=state, request=_fake_request())


def _render_partial(name: str, **context: object) -> str:
    """Render a panel partial directly, mirroring how the matching ``/partials/*``
    route handler renders it.

    Since the 2026-05-18 htmx redesign, base.html only ships empty section shells
    and loads each panel's real content at runtime via ``hx-get="/partials/..."``.
    Direct-render tests therefore target the partial, not base.html. ``request`` is
    always supplied to match the handlers' context contract (the handlers pass it
    unconditionally even though these partial bodies don't read it)."""
    return templates.env.get_template(name).render(request=_fake_request(), **context)


class TestSessionPanel(unittest.TestCase):
    """Tests for session_panel.html inclusion."""

    def test_shows_session_id_when_overnight_present(self):
        state = DashboardState()
        state.overnight = _make_overnight_fixture()
        state.feature_states = _make_feature_states_fixture()
        html = _render_partial("session_panel.html", state=state, last_session=None)
        self.assertIn("test-session-001", html)

    def test_shows_current_round(self):
        state = DashboardState()
        state.overnight = _make_overnight_fixture()
        state.feature_states = _make_feature_states_fixture()
        html = _render_partial("session_panel.html", state=state, last_session=None)
        # Redesign emits the round as the "round · N" stream-line token rather than
        # the pre-redesign "Round N" heading.
        self.assertIn("round · 2", html)

    def test_shows_no_active_session_when_overnight_absent(self):
        state = DashboardState()
        # state.overnight is None by default
        html = _render_partial("session_panel.html", state=state, last_session=None)
        # Redesign empty-state copy is lowercase with no trailing period.
        self.assertIn("no active session", html)

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
        html = _render_partial("pipeline_panel.html", state=state)
        # Redesign empty-state copy replaced "No active pipeline." with this string.
        self.assertIn("no pipeline · refinement queue empty", html)

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
        html = _render_partial("feature_cards.html", state=state)
        # Redesign renders the plan ratio spaced as "N / M tasks" (was "N/M tasks").
        self.assertIn("3 / 5 tasks", html)

    def test_shows_feature_slug(self):
        state = DashboardState()
        state.overnight = _make_overnight_fixture()
        state.feature_states = _make_feature_states_fixture()
        html = _render_partial("feature_cards.html", state=state)
        self.assertIn("feat-alpha", html)
        self.assertIn("feat-beta", html)

    def test_shows_no_features_active_when_overnight_absent(self):
        state = DashboardState()
        html = _render_partial("feature_cards.html", state=state)
        # Redesign empty-state copy replaced "No features active." with this string.
        self.assertIn("no features in play · awaiting next round", html)


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
        html = _render_partial("round_history.html", state=state)
        # Redesign renders the round number as an "R{n}" id span, not a bare "<td>1</td>".
        self.assertIn('<span class="round-id">R1</span>', html)

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
        html = _render_partial("round_history.html", state=state)
        # Redesign renders the merged count inside a round-cell span ("2 · <slugs>"),
        # not a bare "<td>2</td>".
        self.assertIn('class="round-cell round-cell--good">2 · ', html)

    def test_shows_no_completed_rounds_when_history_empty(self):
        state = DashboardState()
        overnight = _make_overnight_fixture()
        overnight["round_history"] = []
        state.overnight = overnight
        state.feature_states = _make_feature_states_fixture()
        html = _render_partial("round_history.html", state=state)
        # Redesign empty-state copy replaced "No completed rounds yet." with this string.
        self.assertIn("no rounds cleared yet", html)

    def test_shows_no_completed_rounds_when_overnight_absent(self):
        state = DashboardState()
        html = _render_partial("round_history.html", state=state)
        # Redesign empty-state copy replaced "No completed rounds yet." with this string.
        self.assertIn("no rounds cleared yet", html)


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


class TestBacklogPanelBackendGate(unittest.TestCase):
    """backlog_panel.html renders a backend-aware 3-way (R5, R6c)."""

    def test_none_backend_renders_placeholder(self):
        state = DashboardState()
        state.backlog_backend = "none"
        # Populated counts must be IGNORED on the non-local arm.
        state.backlog_counts = {"backlog": 2, "complete": 1}
        html = _render_partial("backlog_panel.html", state=state)
        self.assertIn("backlog tracking disabled", html)
        self.assertNotIn("items tracked", html)
        self.assertNotIn("stack-bar", html)

    def test_external_backend_names_the_backend(self):
        state = DashboardState()
        state.backlog_backend = "github-issues"
        state.backlog_counts = {"backlog": 2}
        html = _render_partial("backlog_panel.html", state=state)
        self.assertIn("tracked externally via", html)
        self.assertIn("github-issues", html)
        self.assertNotIn("stack-bar", html)

    def test_cortex_backlog_populated_arm_unchanged(self):
        # R6c: the default arm's rendered output is byte-for-byte today's.
        state = DashboardState()
        state.backlog_backend = "cortex-backlog"
        state.backlog_counts = {"backlog": 2, "complete": 1}
        html = _render_partial("backlog_panel.html", state=state)
        self.assertIn("3 items tracked", html)
        self.assertIn("stack-bar", html)

    def test_cortex_backlog_empty_arm_unchanged(self):
        state = DashboardState()
        state.backlog_backend = "cortex-backlog"
        state.backlog_counts = {}
        html = _render_partial("backlog_panel.html", state=state)
        self.assertIn("no backlog items found", html)


class TestSiblingTemplateTitleFallback(unittest.TestCase):
    """feature_cards.html / escalations_panel.html slug-fallback under the
    title-clear — the deliberate spec.md:69 behavior change. Pins the two
    sibling consumers of state.backlog_titles cleared by the non-local poller
    arm so the fallback render is guarded, not just verbally acknowledged."""

    def test_feature_cards_falls_back_to_slug_when_titles_cleared(self):
        state = DashboardState()
        state.overnight = _make_overnight_fixture()
        state.feature_states = _make_feature_states_fixture()
        state.backlog_titles = {}  # the non-local arm clears this
        html = _render_partial("feature_cards.html", state=state)
        self.assertIn("feat-alpha", html)  # raw slug shown, no error

    def test_feature_cards_shows_title_when_present(self):
        # Contrast: a populated title IS shown — proves the fallback is
        # title-when-present / slug-when-cleared, not slug-always.
        state = DashboardState()
        state.overnight = _make_overnight_fixture()
        state.feature_states = _make_feature_states_fixture()
        state.backlog_titles = {"feat-alpha": "Alpha Human Title"}
        html = _render_partial("feature_cards.html", state=state)
        self.assertIn("Alpha Human Title", html)

    def test_escalations_panel_falls_back_to_slug_when_titles_cleared(self):
        state = DashboardState()
        state.open_questions_total = 1
        state.overnight = {"features": {"feat-alpha": {"status": "running"}}}
        state.feature_escalations = {
            "feat-alpha": [
                {
                    "question": "Blocked on X?",
                    "escalation_id": "esc-1",
                    "ts": "2026-06-24T10:00:00+00:00",
                }
            ]
        }
        state.backlog_titles = {}  # the non-local arm clears this
        html = _render_partial("escalations_panel.html", state=state)
        self.assertIn("feat-alpha", html)  # raw slug shown, no error


if __name__ == "__main__":
    unittest.main()
