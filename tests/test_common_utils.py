"""Unit tests for claude.common utility functions: read_tier and requires_review.

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

from claude.common import read_tier, requires_review


# ---------------------------------------------------------------------------
# read_tier
# ---------------------------------------------------------------------------


class TestReadTier:
    """Tests for read_tier()."""

    def test_returns_tier_from_events_log(self, tmp_path: Path):
        """Reads the tier field from a well-formed events.log."""
        feature = "test-feature"
        feature_dir = tmp_path / feature
        feature_dir.mkdir()
        events_log = feature_dir / "events.log"
        events_log.write_text(
            json.dumps({"event": "plan_parsed", "tier": "complex"}) + "\n",
            encoding="utf-8",
        )

        result = read_tier(feature, lifecycle_base=tmp_path)
        assert result == "complex"

    def test_returns_last_tier_when_multiple(self, tmp_path: Path):
        """When multiple lines have a tier field, returns the last one."""
        feature = "test-feature"
        feature_dir = tmp_path / feature
        feature_dir.mkdir()
        events_log = feature_dir / "events.log"
        lines = [
            json.dumps({"event": "plan_parsed", "tier": "simple"}),
            json.dumps({"event": "something_else", "note": "no tier here"}),
            json.dumps({"event": "complexity_override", "tier": "complex"}),
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

    def test_complexity_override_event_updates_tier(self, tmp_path: Path):
        """A complexity_override event with a tier field overrides earlier values."""
        feature = "test-feature"
        feature_dir = tmp_path / feature
        feature_dir.mkdir()
        events_log = feature_dir / "events.log"
        lines = [
            json.dumps({"event": "plan_parsed", "tier": "simple"}),
            json.dumps({"event": "complexity_override", "tier": "complex"}),
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
            json.dumps({"event": "plan_parsed", "tier": "complex"}),
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
