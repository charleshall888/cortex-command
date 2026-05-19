"""Tests for feature_cards.html PR-url rendering via feature_pr field.

Tests cover:
  - feature with pr.json populated: renders <a href="...">PR #N</a> anchor
  - feature without pr.json: no PR anchor in rendered HTML
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from cortex_command.dashboard.app import templates
from cortex_command.dashboard.data import parse_feature_pr_artifact
from cortex_command.dashboard.poller import DashboardState


def _make_overnight_fixture(slug: str) -> dict:
    """Return a minimal overnight-state dict for a single feature slug."""
    return {
        "session_id": "test-pr-session",
        "current_round": 1,
        "phase": "running",
        "started_at": "2026-01-01T00:00:00+00:00",
        "features": {
            slug: {
                "status": "merged",
                "started_at": "2026-01-01T00:00:00+00:00",
            }
        },
        "round_history": [],
    }


def _render(state: DashboardState) -> str:
    """Render feature_cards.html directly with the given state."""
    return templates.env.get_template("feature_cards.html").render(state=state)


class TestFeatureCardsPrUrl(unittest.TestCase):
    """feature_cards.html renders PR anchor when feature_pr[slug] is populated."""

    def test_pr_anchor_rendered_when_pr_json_present(self):
        """When feature_pr[slug] is set, the card renders an <a> with the PR URL and number."""
        slug = "test-feature-with-pr"
        pr_data = {
            "number": 42,
            "url": "https://github.com/example/repo/pull/42",
            "head_branch": "test-feature-with-pr",
            "opened_at": "2026-01-01T00:00:00+00:00",
            "repo": "example/repo",
        }

        with tempfile.TemporaryDirectory() as tmp:
            lifecycle_dir = Path(tmp) / "cortex" / "lifecycle"
            feature_dir = lifecycle_dir / slug
            feature_dir.mkdir(parents=True)
            (feature_dir / "pr.json").write_text(
                json.dumps(pr_data), encoding="utf-8"
            )

            parsed = parse_feature_pr_artifact(lifecycle_dir, slug)
            self.assertIsNotNone(parsed, "parse_feature_pr_artifact should return dict")

            state = DashboardState()
            state.overnight = _make_overnight_fixture(slug)
            state.feature_pr[slug] = parsed

        html = _render(state)

        self.assertIn('href="https://github.com/example/repo/pull/42"', html)
        self.assertIn("PR #42", html)

    def test_no_pr_anchor_when_pr_json_absent(self):
        """When no pr.json exists for a feature, no PR anchor appears in the rendered card."""
        slug = "test-feature-no-pr"

        with tempfile.TemporaryDirectory() as tmp:
            lifecycle_dir = Path(tmp) / "cortex" / "lifecycle"
            feature_dir = lifecycle_dir / slug
            feature_dir.mkdir(parents=True)
            # intentionally do NOT write pr.json

            parsed = parse_feature_pr_artifact(lifecycle_dir, slug)
            self.assertIsNone(parsed, "parse_feature_pr_artifact should return None when absent")

        state = DashboardState()
        state.overnight = _make_overnight_fixture(slug)
        # feature_pr[slug] is intentionally absent

        html = _render(state)

        self.assertNotIn("github.com/example/repo/pull", html)
        self.assertNotIn("PR #", html)


if __name__ == "__main__":
    unittest.main()
