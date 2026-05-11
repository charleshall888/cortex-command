"""Unit tests for cortex_command.common utility functions: read_tier and requires_review.

Tests cover:
  - read_tier: existing events.log with tier field, empty file,
    missing file (default "simple"), complexity_override event.
  - requires_review: all 8 cells of the gating matrix
    (2 tiers x 4 criticalities).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cortex_command.common import mark_task_done_in_plan, read_tier, requires_review


# ---------------------------------------------------------------------------
# read_tier
# ---------------------------------------------------------------------------


class TestReadTier:
    """Tests for read_tier()."""

    def test_returns_tier_from_events_log(self, tmp_path: Path):
        """Reads the tier field from a well-formed lifecycle_start event."""
        feature = "test-feature"
        feature_dir = tmp_path / feature
        feature_dir.mkdir()
        events_log = feature_dir / "events.log"
        events_log.write_text(
            json.dumps({"event": "lifecycle_start", "tier": "complex"}) + "\n",
            encoding="utf-8",
        )

        result = read_tier(feature, lifecycle_base=tmp_path)
        assert result == "complex"

    def test_complexity_override_supersedes_lifecycle_start_tier(
        self, tmp_path: Path
    ):
        """complexity_override.to supersedes the earlier lifecycle_start.tier."""
        feature = "test-feature"
        feature_dir = tmp_path / feature
        feature_dir.mkdir()
        events_log = feature_dir / "events.log"
        lines = [
            json.dumps({"event": "lifecycle_start", "tier": "simple"}),
            json.dumps({"event": "something_else", "note": "no tier here"}),
            json.dumps({"event": "complexity_override", "to": "complex"}),
        ]
        events_log.write_text("\n".join(lines) + "\n", encoding="utf-8")

        result = read_tier(feature, lifecycle_base=tmp_path)
        assert result == "complex"

    def test_returns_default_for_empty_file(self, tmp_path: Path):
        """Empty events.log returns the default tier 'simple'."""
        feature = "test-feature"
        feature_dir = tmp_path / feature
        feature_dir.mkdir()
        events_log = feature_dir / "events.log"
        events_log.write_text("", encoding="utf-8")

        result = read_tier(feature, lifecycle_base=tmp_path)
        assert result == "simple"

    def test_returns_default_for_missing_file(self, tmp_path: Path):
        """Missing events.log returns the default tier 'simple'."""
        feature = "test-feature"
        # Don't create the feature directory at all
        result = read_tier(feature, lifecycle_base=tmp_path)
        assert result == "simple"

    def test_complexity_override_to_field_updates_tier(self, tmp_path: Path):
        """complexity_override with `to` field overrides the baseline tier."""
        feature = "test-feature"
        feature_dir = tmp_path / feature
        feature_dir.mkdir()
        events_log = feature_dir / "events.log"
        lines = [
            json.dumps({"event": "lifecycle_start", "tier": "simple"}),
            json.dumps({"event": "complexity_override", "to": "complex"}),
        ]
        events_log.write_text("\n".join(lines) + "\n", encoding="utf-8")

        result = read_tier(feature, lifecycle_base=tmp_path)
        assert result == "complex"

    def test_skips_malformed_json_lines(self, tmp_path: Path):
        """Malformed JSON lines are skipped without error."""
        feature = "test-feature"
        feature_dir = tmp_path / feature
        feature_dir.mkdir()
        events_log = feature_dir / "events.log"
        lines = [
            "not valid json",
            json.dumps({"event": "lifecycle_start", "tier": "complex"}),
            "{bad json too",
        ]
        events_log.write_text("\n".join(lines) + "\n", encoding="utf-8")

        result = read_tier(feature, lifecycle_base=tmp_path)
        assert result == "complex"

    def test_returns_default_when_no_tier_field_present(self, tmp_path: Path):
        """Events without a tier field leave the default 'simple' unchanged."""
        feature = "test-feature"
        feature_dir = tmp_path / feature
        feature_dir.mkdir()
        events_log = feature_dir / "events.log"
        lines = [
            json.dumps({"event": "session_start"}),
            json.dumps({"event": "task_complete", "task": 1}),
        ]
        events_log.write_text("\n".join(lines) + "\n", encoding="utf-8")

        result = read_tier(feature, lifecycle_base=tmp_path)
        assert result == "simple"


# ---------------------------------------------------------------------------
# requires_review — all 8 cells of the gating matrix
# ---------------------------------------------------------------------------


class TestRequiresReview:
    """Tests for requires_review(): 2 tiers x 4 criticalities = 8 cells."""

    # simple tier: only high and critical trigger review

    def test_simple_low_skips_review(self):
        assert requires_review("simple", "low") is False

    def test_simple_medium_skips_review(self):
        assert requires_review("simple", "medium") is False

    def test_simple_high_requires_review(self):
        assert requires_review("simple", "high") is True

    def test_simple_critical_requires_review(self):
        assert requires_review("simple", "critical") is True

    # complex tier: always requires review regardless of criticality

    def test_complex_low_requires_review(self):
        assert requires_review("complex", "low") is True

    def test_complex_medium_requires_review(self):
        assert requires_review("complex", "medium") is True

    def test_complex_high_requires_review(self):
        assert requires_review("complex", "high") is True

    def test_complex_critical_requires_review(self):
        assert requires_review("complex", "critical") is True


# ---------------------------------------------------------------------------
# mark_task_done_in_plan — idempotency over already-marked Status fields (R12)
# ---------------------------------------------------------------------------


class TestMarkTaskDoneInPlanIdempotent:
    """Codify R12: mark_task_done_in_plan is a no-op on already-[X] or [x]
    Status fields (file bytes unchanged) and updates [ ] to [x].
    """

    def test_mark_task_done_in_plan_idempotent_over_existing_marks(
        self, tmp_path: Path
    ):
        """R12: calling on [X] or [x] leaves bytes unchanged; [ ] becomes [x]."""
        # Case 1: already [X] complete — file bytes must be byte-identical.
        plan_upper = tmp_path / "plan_upper.md"
        content_upper = (
            "# Plan\n\n"
            "### Task 1: Do the thing\n"
            "- **Status**: [X] complete\n"
        )
        plan_upper.write_text(content_upper, encoding="utf-8")
        before_upper = plan_upper.read_bytes()
        mark_task_done_in_plan(plan_upper, 1)
        after_upper = plan_upper.read_bytes()
        assert after_upper == before_upper

        # Case 2: already [x] complete — file bytes must be byte-identical.
        plan_lower = tmp_path / "plan_lower.md"
        content_lower = (
            "# Plan\n\n"
            "### Task 1: Do the thing\n"
            "- **Status**: [x] complete\n"
        )
        plan_lower.write_text(content_lower, encoding="utf-8")
        before_lower = plan_lower.read_bytes()
        mark_task_done_in_plan(plan_lower, 1)
        after_lower = plan_lower.read_bytes()
        assert after_lower == before_lower

        # Case 3: [ ] pending — file is updated to [x] complete.
        plan_pending = tmp_path / "plan_pending.md"
        content_pending = (
            "# Plan\n\n"
            "### Task 1: Do the thing\n"
            "- **Status**: [ ] pending\n"
        )
        plan_pending.write_text(content_pending, encoding="utf-8")
        mark_task_done_in_plan(plan_pending, 1)
        updated = plan_pending.read_text(encoding="utf-8")
        assert "- **Status**: [x] pending" in updated
        assert "- **Status**: [ ] pending" not in updated
