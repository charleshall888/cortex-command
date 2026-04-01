"""Tests for initialize_overnight_state() worktree routing across session types.

Covers three session types:
  1. Pure wild-light: all items target a single cross-repo, no MC-local items.
     The cross-repo worktree becomes worktree_path (primary), and the MC
     worktree is stored in integration_worktrees.
  2. MC-only: all items have repo=None. The MC worktree is primary and
     integration_worktrees is empty.
  3. Mixed: some MC-local items, some cross-repo items. The MC worktree
     stays primary.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from claude.overnight.backlog import BacklogItem, Batch, SelectionResult
from claude.overnight.plan import initialize_overnight_state


def _make_selection_with_repos(repos: list[str | None]) -> SelectionResult:
    """Build a SelectionResult with one Batch containing items with given repo values."""
    items = [
        BacklogItem(
            id=i + 1,
            title=f"Item {i + 1}",
            status="backlog",
            priority="medium",
            repo=repo,
            lifecycle_slug=f"item-{i + 1}",
        )
        for i, repo in enumerate(repos)
    ]
    batch = Batch(items=items, batch_context="test context", batch_id=1)
    return SelectionResult(batches=[batch], ineligible=[], summary="test")


def _cross_repo_side_effects(cross_repo_count: int, stale_branch_exists: bool = False):
    """Build a list of subprocess.run side-effect return values.

    Covers the MC worktree setup followed by N cross-repo worktree setups.

    MC sequence:
      1. git worktree prune
      2. git show-ref --verify -> returncode 1 (no stale branch)
      3. git worktree add (check=True)

    Per cross-repo sequence:
      4. git rev-parse origin/HEAD (capture_output) -> "abc123"
      5. git worktree prune (cwd=repo)
      6. git show-ref --verify (cwd=repo) -> returncode 1 (no stale branch)
      7. git worktree add (cwd=repo, check=True)
    """
    effects = []
    # MC setup
    effects.append(MagicMock(returncode=0))  # prune
    effects.append(MagicMock(returncode=1))  # show-ref (no stale branch)
    effects.append(MagicMock(returncode=0))  # worktree add

    for _ in range(cross_repo_count):
        rev_parse_mock = MagicMock(returncode=0)
        rev_parse_mock.stdout = b"abc123\n"
        effects.append(rev_parse_mock)  # rev-parse origin/HEAD
        effects.append(MagicMock(returncode=0))  # prune
        if stale_branch_exists:
            effects.append(MagicMock(returncode=0))  # show-ref (stale exists)
            effects.append(MagicMock(returncode=0))  # branch -D
        else:
            effects.append(MagicMock(returncode=1))  # show-ref (no stale)
        effects.append(MagicMock(returncode=0))  # worktree add

    return effects


class TestWorktreeRouting(unittest.TestCase):
    """Tests for worktree_path routing in initialize_overnight_state()."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._fake_tmpdir = self._tmpdir.name

    def tearDown(self):
        self._tmpdir.cleanup()

    # ------------------------------------------------------------------
    # 1. Pure wild-light: all items target a single cross-repo
    # ------------------------------------------------------------------

    def test_pure_wild_light_routes_to_cross_repo_worktree(self):
        """When all items target a cross-repo, worktree_path is the cross-repo worktree."""
        selection = _make_selection_with_repos([
            "/path/to/wild-light",
            "/path/to/wild-light",
        ])

        effects = _cross_repo_side_effects(cross_repo_count=1)
        mock_run = MagicMock(side_effect=effects)

        cross_repo_resolved = str(Path("/path/to/wild-light").expanduser().resolve())

        env_patch = patch.dict(os.environ, {"TMPDIR": self._fake_tmpdir})
        subprocess_patch = patch("claude.overnight.plan.subprocess.run", mock_run)
        exists_patch = patch("claude.overnight.plan.Path.exists", return_value=False)

        with env_patch, subprocess_patch, exists_patch:
            state = initialize_overnight_state(selection)

        # The cross-repo worktree path should be under TMPDIR with the repo name suffix
        expected_cross_worktree = str(
            Path(self._fake_tmpdir) / "overnight-worktrees"
            / f"{state.session_id}-wild-light"
        )
        self.assertEqual(state.worktree_path, expected_cross_worktree)

    def test_pure_wild_light_stores_mc_worktree_in_integration_worktrees(self):
        """For pure wild-light, project_root is in integration_worktrees (MC worktree preserved)."""
        selection = _make_selection_with_repos([
            "/path/to/wild-light",
            "/path/to/wild-light",
        ])

        effects = _cross_repo_side_effects(cross_repo_count=1)
        mock_run = MagicMock(side_effect=effects)

        env_patch = patch.dict(os.environ, {"TMPDIR": self._fake_tmpdir})
        subprocess_patch = patch("claude.overnight.plan.subprocess.run", mock_run)
        exists_patch = patch("claude.overnight.plan.Path.exists", return_value=False)

        with env_patch, subprocess_patch, exists_patch:
            state = initialize_overnight_state(selection)

        project_root = str(Path.cwd().resolve())
        self.assertIn(project_root, state.integration_worktrees)

        # The MC worktree should be the standard MC worktree path
        expected_mc_worktree = str(
            Path(self._fake_tmpdir) / "overnight-worktrees" / state.session_id
        )
        self.assertEqual(state.integration_worktrees[project_root], expected_mc_worktree)

    # ------------------------------------------------------------------
    # 2. MC-only: all items have repo=None
    # ------------------------------------------------------------------

    def test_mc_only_routes_to_mc_worktree(self):
        """When all items are MC-local, worktree_path is the MC worktree."""
        selection = _make_selection_with_repos([None, None])

        mock_run = MagicMock(return_value=MagicMock(returncode=0))

        env_patch = patch.dict(os.environ, {"TMPDIR": self._fake_tmpdir})
        subprocess_patch = patch("claude.overnight.plan.subprocess.run", mock_run)

        with env_patch, subprocess_patch:
            state = initialize_overnight_state(selection)

        expected_mc_worktree = str(
            Path(self._fake_tmpdir) / "overnight-worktrees" / state.session_id
        )
        self.assertEqual(state.worktree_path, expected_mc_worktree)

    def test_mc_only_has_empty_integration_worktrees(self):
        """MC-only session produces empty integration_worktrees."""
        selection = _make_selection_with_repos([None, None])

        mock_run = MagicMock(return_value=MagicMock(returncode=0))

        env_patch = patch.dict(os.environ, {"TMPDIR": self._fake_tmpdir})
        subprocess_patch = patch("claude.overnight.plan.subprocess.run", mock_run)

        with env_patch, subprocess_patch:
            state = initialize_overnight_state(selection)

        project_root = str(Path.cwd().resolve())
        self.assertNotIn(project_root, state.integration_worktrees)
        self.assertEqual(state.integration_worktrees, {})

    # ------------------------------------------------------------------
    # 3. Mixed: MC-local + cross-repo items -> MC stays primary
    # ------------------------------------------------------------------

    def test_mixed_routes_to_mc_worktree(self):
        """MC + single cross-repo: worktree_path stays MC (not the cross-repo worktree).

        This is the critical regression case: a session with exactly one cross-repo
        target AND MC-local items must NOT trigger pure wild-light routing even though
        len(integration_worktrees) == 1.
        """
        selection = _make_selection_with_repos([
            None,                   # MC-local item
            "/path/to/wild-light",  # cross-repo item (only one)
        ])

        effects = _cross_repo_side_effects(cross_repo_count=1)
        mock_run = MagicMock(side_effect=effects)

        env_patch = patch.dict(os.environ, {"TMPDIR": self._fake_tmpdir})
        subprocess_patch = patch("claude.overnight.plan.subprocess.run", mock_run)
        exists_patch = patch("claude.overnight.plan.Path.exists", return_value=False)

        with env_patch, subprocess_patch, exists_patch:
            state = initialize_overnight_state(selection)

        expected_mc_worktree = str(
            Path(self._fake_tmpdir) / "overnight-worktrees" / state.session_id
        )
        self.assertEqual(state.worktree_path, expected_mc_worktree)


if __name__ == "__main__":
    unittest.main()
