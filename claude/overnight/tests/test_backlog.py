"""Unit tests for _is_pipeline_branch_merged() and filter_ready() check 6.

Four test cases:
  1. All matching branches are merged → item excluded ("pipeline branch already merged into main")
  2. At least one branch has unmerged commits → item eligible
  3. No matching branches → item eligible (fail open)
  4. subprocess.run raises OSError → item eligible (fail open)
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

from claude.overnight.backlog import BacklogItem, _is_pipeline_branch_merged, filter_ready


class TestIsPipelineBranchMerged(unittest.TestCase):
    """Direct tests for _is_pipeline_branch_merged()."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._root = Path(self._tmpdir.name)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _make_run(self, branch_list: str, log_outputs: list[str]) -> MagicMock:
        """Build a mock for subprocess.run that sequences branch-list then log calls."""
        results = []
        # First call: git branch --list
        branch_result = MagicMock()
        branch_result.returncode = 0
        branch_result.stdout = branch_list
        results.append(branch_result)
        # Subsequent calls: git log per branch
        for log_out in log_outputs:
            log_result = MagicMock()
            log_result.returncode = 0
            log_result.stdout = log_out
            results.append(log_result)
        mock = MagicMock(side_effect=results)
        return mock

    def test_all_branches_merged_returns_true(self) -> None:
        """When all pipeline/{slug}* branches have empty git log output, returns True."""
        mock_run = self._make_run(
            branch_list="  pipeline/my-feature\n",
            log_outputs=[""],
        )
        with patch("claude.overnight.backlog.subprocess.run", mock_run):
            result = _is_pipeline_branch_merged("my-feature", self._root)
        self.assertTrue(result)

    def test_unmerged_commits_returns_false(self) -> None:
        """When a branch has unmerged commits, returns False."""
        mock_run = self._make_run(
            branch_list="  pipeline/my-feature\n",
            log_outputs=["abc1234 add some feature\n"],
        )
        with patch("claude.overnight.backlog.subprocess.run", mock_run):
            result = _is_pipeline_branch_merged("my-feature", self._root)
        self.assertFalse(result)

    def test_no_matching_branches_returns_false(self) -> None:
        """When git branch --list returns no branches, returns False (fail open)."""
        mock_run = self._make_run(branch_list="", log_outputs=[])
        with patch("claude.overnight.backlog.subprocess.run", mock_run):
            result = _is_pipeline_branch_merged("my-feature", self._root)
        self.assertFalse(result)

    def test_subprocess_oserror_returns_false(self) -> None:
        """When subprocess.run raises OSError, returns False (fail open)."""
        with patch(
            "claude.overnight.backlog.subprocess.run", side_effect=OSError("no git")
        ):
            result = _is_pipeline_branch_merged("my-feature", self._root)
        self.assertFalse(result)

    def test_empty_slug_returns_false(self) -> None:
        """Empty slug short-circuits immediately without subprocess calls."""
        with patch("claude.overnight.backlog.subprocess.run") as mock_run:
            result = _is_pipeline_branch_merged("", self._root)
        self.assertFalse(result)
        mock_run.assert_not_called()

    def test_multiple_branches_all_merged(self) -> None:
        """Multiple branches all merged → True."""
        mock_run = self._make_run(
            branch_list="  pipeline/feat\n  pipeline/feat-2\n",
            log_outputs=["", ""],
        )
        with patch("claude.overnight.backlog.subprocess.run", mock_run):
            result = _is_pipeline_branch_merged("feat", self._root)
        self.assertTrue(result)

    def test_multiple_branches_one_unmerged(self) -> None:
        """Multiple branches where second has unmerged commits → False."""
        mock_run = self._make_run(
            branch_list="  pipeline/feat\n  pipeline/feat-2\n",
            log_outputs=["", "abc1234 wip\n"],
        )
        with patch("claude.overnight.backlog.subprocess.run", mock_run):
            result = _is_pipeline_branch_merged("feat", self._root)
        self.assertFalse(result)


class TestFilterReadyMergeCheck(unittest.TestCase):
    """Integration test: merged pipeline branch causes ineligibility in filter_ready()."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._root = Path(self._tmpdir.name)
        self._orig_cwd = os.getcwd()
        os.chdir(self._root)

    def tearDown(self) -> None:
        os.chdir(self._orig_cwd)
        self._tmpdir.cleanup()

    def _make_item(self, slug: str) -> BacklogItem:
        lifecycle_dir = self._root / "lifecycle" / slug
        lifecycle_dir.mkdir(parents=True)
        (lifecycle_dir / "research.md").write_text("# Research\n")
        (lifecycle_dir / "spec.md").write_text("# Spec\n")
        return BacklogItem(
            id=1,
            title="My Feature",
            status="in_progress",
            lifecycle_slug=slug,
        )

    def test_merged_branch_item_is_ineligible(self) -> None:
        """Item passes checks 1-5 but fails check 6 when branch is merged."""
        slug = "my-feature"
        item = self._make_item(slug)

        branch_result = MagicMock(returncode=0, stdout="  pipeline/my-feature\n")
        log_result = MagicMock(returncode=0, stdout="")

        with patch(
            "claude.overnight.backlog.subprocess.run",
            side_effect=[branch_result, log_result],
        ):
            readiness = filter_ready([item], project_root=self._root)

        self.assertEqual(len(readiness.eligible), 0)
        self.assertEqual(len(readiness.ineligible), 1)
        reason = readiness.ineligible[0][1]
        self.assertEqual(reason, "pipeline branch already merged into main")

    def test_unmerged_branch_item_is_eligible(self) -> None:
        """Item is eligible when pipeline branch has unmerged commits."""
        slug = "my-feature"
        item = self._make_item(slug)

        branch_result = MagicMock(returncode=0, stdout="  pipeline/my-feature\n")
        log_result = MagicMock(returncode=0, stdout="abc1234 some commit\n")

        with patch(
            "claude.overnight.backlog.subprocess.run",
            side_effect=[branch_result, log_result],
        ):
            readiness = filter_ready([item], project_root=self._root)

        self.assertEqual(len(readiness.eligible), 1)
        self.assertEqual(len(readiness.ineligible), 0)
