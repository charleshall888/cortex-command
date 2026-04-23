"""Coupling test: _classify_no_commit() error strings match _suggest_next_step() patterns.

Ensures the classification strings produced by outcome_router._classify_no_commit
contain substrings that _suggest_next_step in report.py recognises, preventing
silent drift between the two modules.
"""

from __future__ import annotations

import subprocess
from unittest.mock import patch, MagicMock

import pytest

from cortex_command.overnight.outcome_router import _classify_no_commit
from cortex_command.overnight.report import _suggest_next_step

DEFAULT_SUGGESTION = "Review learnings, retry or investigate"


class TestNoCommitClassificationCoupling:
    """Verify _classify_no_commit output couples correctly to _suggest_next_step."""

    def test_stale_branch_classified_and_routed(self):
        """Stale branch (base ahead) contains 'already merged' and gets a
        non-default suggestion."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "5\n"

        with patch("claude.overnight.outcome_router.subprocess.run", return_value=mock_result):
            result = _classify_no_commit("feat-x", "feat-x-branch", "main")

        assert "already merged" in result
        assert _suggest_next_step(result) != DEFAULT_SUGGESTION

    def test_fresh_branch_no_commits_classified_and_routed(self):
        """Fresh branch at base HEAD contains 'no changes produced' and gets a
        non-default suggestion."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "0\n"

        with patch("claude.overnight.outcome_router.subprocess.run", return_value=mock_result):
            result = _classify_no_commit("feat-y", "feat-y-branch", "main")

        assert "no changes produced" in result
        assert _suggest_next_step(result) != DEFAULT_SUGGESTION

    def test_invalid_branch_ref_hits_fallback_and_default_suggestion(self):
        """Invalid branch ref returns fallback containing branch name, and
        _suggest_next_step returns the default suggestion."""
        mock_result = MagicMock()
        mock_result.returncode = 128
        mock_result.stderr = "fatal: Not a valid object name"
        mock_result.stdout = ""

        with patch("claude.overnight.outcome_router.subprocess.run", return_value=mock_result):
            result = _classify_no_commit("feat-z", "feat-z-branch", "main")

        assert result  # non-empty
        assert "feat-z-branch" in result
        assert _suggest_next_step(result) == DEFAULT_SUGGESTION

    def test_subprocess_timeout_returns_fallback(self):
        """TimeoutExpired produces a fallback string containing the branch name."""
        with patch(
            "claude.overnight.outcome_router.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="git", timeout=30),
        ):
            result = _classify_no_commit("feat-t", "feat-t-branch", "main")

        assert result  # non-empty
        assert "feat-t-branch" in result
