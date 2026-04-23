"""Unit tests for review_dispatch.py: parse_verdict().

Tests cover:
  - Valid JSON verdict block extraction from review.md
  - Malformed JSON returns ERROR result
  - Missing file returns ERROR result
  - Multiple JSON blocks returns the first match
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from claude.pipeline.review_dispatch import parse_verdict


class TestParseVerdict:
    """Tests for parse_verdict()."""

    def test_valid_verdict_block(self, tmp_path: Path):
        """Extracts a well-formed JSON verdict block from review.md."""
        review_path = tmp_path / "review.md"
        verdict_data = {
            "verdict": "APPROVED",
            "cycle": 1,
            "issues": [],
        }
        review_path.write_text(
            "# Review\n\nSome commentary.\n\n"
            f"```json\n{json.dumps(verdict_data, indent=2)}\n```\n",
            encoding="utf-8",
        )

        result = parse_verdict(review_path)
        assert result["verdict"] == "APPROVED"
        assert result["cycle"] == 1
        assert result["issues"] == []

    def test_changes_requested_verdict(self, tmp_path: Path):
        """Extracts a CHANGES_REQUESTED verdict correctly."""
        review_path = tmp_path / "review.md"
        verdict_data = {
            "verdict": "CHANGES_REQUESTED",
            "cycle": 2,
            "issues": ["Missing tests", "Unused import"],
        }
        review_path.write_text(
            "# Review\n\n"
            f"```json\n{json.dumps(verdict_data)}\n```\n",
            encoding="utf-8",
        )

        result = parse_verdict(review_path)
        assert result["verdict"] == "CHANGES_REQUESTED"
        assert result["cycle"] == 2
        assert result["issues"] == ["Missing tests", "Unused import"]

    def test_malformed_json_returns_error(self, tmp_path: Path):
        """Malformed JSON inside a code block returns the ERROR result."""
        review_path = tmp_path / "review.md"
        review_path.write_text(
            "# Review\n\n```json\n{not valid json}\n```\n",
            encoding="utf-8",
        )

        result = parse_verdict(review_path)
        assert result["verdict"] == "ERROR"
        assert result["cycle"] == 0
        assert result["issues"] == []

    def test_missing_file_returns_error(self, tmp_path: Path):
        """Non-existent review.md returns the ERROR result."""
        review_path = tmp_path / "nonexistent" / "review.md"

        result = parse_verdict(review_path)
        assert result["verdict"] == "ERROR"
        assert result["cycle"] == 0
        assert result["issues"] == []

    def test_no_json_block_returns_error(self, tmp_path: Path):
        """Review file without a JSON code block returns the ERROR result."""
        review_path = tmp_path / "review.md"
        review_path.write_text(
            "# Review\n\nThis review has no JSON block.\n",
            encoding="utf-8",
        )

        result = parse_verdict(review_path)
        assert result["verdict"] == "ERROR"
        assert result["cycle"] == 0
        assert result["issues"] == []

    def test_empty_file_returns_error(self, tmp_path: Path):
        """Empty review.md returns the ERROR result."""
        review_path = tmp_path / "review.md"
        review_path.write_text("", encoding="utf-8")

        result = parse_verdict(review_path)
        assert result["verdict"] == "ERROR"
        assert result["cycle"] == 0
        assert result["issues"] == []

    def test_verdict_with_surrounding_text(self, tmp_path: Path):
        """JSON block surrounded by prose is still extracted correctly."""
        review_path = tmp_path / "review.md"
        verdict_data = {
            "verdict": "REJECTED",
            "cycle": 1,
            "issues": ["Fundamental design flaw"],
        }
        review_path.write_text(
            "# Code Review\n\n"
            "The implementation has issues.\n\n"
            f"```json\n{json.dumps(verdict_data)}\n```\n\n"
            "Please address the above.\n",
            encoding="utf-8",
        )

        result = parse_verdict(review_path)
        assert result["verdict"] == "REJECTED"
        assert result["cycle"] == 1
        assert result["issues"] == ["Fundamental design flaw"]
