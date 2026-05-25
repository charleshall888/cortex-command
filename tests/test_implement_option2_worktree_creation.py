"""Integration test for implement.md option 2: interactive worktree creation.

Verifies that create_worktree(feature="interactive-test-fixture", base_branch="main")
materializes a worktree at <repo>/.claude/worktrees/interactive-test-fixture/ with:
  - branch named interactive/test-fixture
  - .claude/settings.local.json copied from the repo root (when present)
  - .venv as a symlink (when .venv exists in the repo root)

Each test uses a fresh tempdir for the repo so parallel test runs don't collide.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cortex_command.pipeline.worktree import create_worktree


def _init_git_repo(path: Path) -> str:
    """Initialize a git repo with an initial empty commit.

    Returns the default branch name (e.g. 'main' or 'master').
    """
    subprocess.run(
        ["git", "init"],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(path),
    )
    subprocess.run(
        [
            "git",
            "-c", "commit.gpgsign=false",
            "-c", "user.email=test@test.com",
            "-c", "user.name=Test",
            "commit",
            "--allow-empty",
            "-m", "init",
        ],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(path),
    )
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(path),
    )
    return result.stdout.strip()


class TestOption2InteractiveWorktreeCreation(unittest.TestCase):
    """Integration tests for implement.md option 2 worktree creation.

    Each test creates a sandbox-aware temp git repo, calls
    create_worktree(feature="interactive-test-fixture", base_branch=<branch>),
    and asserts the worktree is materialized correctly at the expected path.
    """

    def test_worktree_created_at_expected_repo_relative_path(self):
        """Worktree lands at <repo>/.claude/worktrees/interactive-test-fixture/."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir).resolve()
            base_branch = _init_git_repo(tmppath)

            expected_path = (tmppath / ".claude" / "worktrees" / "interactive-test-fixture").resolve()

            with patch("cortex_command.pipeline.worktree._repo_root", return_value=tmppath):
                info = create_worktree(
                    feature="interactive-test-fixture",
                    base_branch=base_branch,
                )

            self.assertEqual(info.path, expected_path)
            self.assertTrue(info.path.is_dir(), f"Worktree directory missing: {info.path}")

    def test_branch_named_interactive_test_fixture(self):
        """Branch is named interactive/test-fixture (interactive- prefix stripped, / inserted)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir).resolve()
            base_branch = _init_git_repo(tmppath)

            with patch("cortex_command.pipeline.worktree._repo_root", return_value=tmppath):
                info = create_worktree(
                    feature="interactive-test-fixture",
                    base_branch=base_branch,
                )

            self.assertEqual(info.branch, "interactive/test-fixture")

    def test_settings_local_json_copied_to_worktree(self):
        """`.claude/settings.local.json` is copied from the repo into the worktree."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir).resolve()
            base_branch = _init_git_repo(tmppath)

            # Create a .claude/settings.local.json in the repo root.
            claude_dir = tmppath / ".claude"
            claude_dir.mkdir()
            settings_content = json.dumps({"sandbox": {"filesystem": {"allowWrite": []}}})
            (claude_dir / "settings.local.json").write_text(settings_content, encoding="utf-8")

            with patch("cortex_command.pipeline.worktree._repo_root", return_value=tmppath):
                info = create_worktree(
                    feature="interactive-test-fixture",
                    base_branch=base_branch,
                )

            copied_settings = info.path / ".claude" / "settings.local.json"
            self.assertTrue(
                copied_settings.is_file(),
                f".claude/settings.local.json not found at: {copied_settings}",
            )
            # Verify content matches what we wrote.
            self.assertEqual(
                json.loads(copied_settings.read_text(encoding="utf-8")),
                json.loads(settings_content),
            )

    def test_venv_is_symlink_when_venv_present(self):
        """`.venv` inside the worktree is a symlink pointing to the repo's .venv."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir).resolve()
            base_branch = _init_git_repo(tmppath)

            # Create a .venv directory in the repo root.
            (tmppath / ".venv").mkdir()

            with patch("cortex_command.pipeline.worktree._repo_root", return_value=tmppath):
                info = create_worktree(
                    feature="interactive-test-fixture",
                    base_branch=base_branch,
                )

            venv_link = info.path / ".venv"
            self.assertTrue(
                venv_link.is_symlink(),
                f".venv is not a symlink at: {venv_link}",
            )
            self.assertEqual(
                os.readlink(str(venv_link)),
                str(tmppath / ".venv"),
            )

    def test_worktree_info_fields(self):
        """WorktreeInfo returned has the correct feature, branch, path, and exists=True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir).resolve()
            base_branch = _init_git_repo(tmppath)

            expected_path = (tmppath / ".claude" / "worktrees" / "interactive-test-fixture").resolve()

            with patch("cortex_command.pipeline.worktree._repo_root", return_value=tmppath):
                info = create_worktree(
                    feature="interactive-test-fixture",
                    base_branch=base_branch,
                )

            self.assertEqual(info.feature, "interactive-test-fixture")
            self.assertEqual(info.branch, "interactive/test-fixture")
            self.assertEqual(info.path, expected_path)
            self.assertTrue(info.exists)


if __name__ == "__main__":
    unittest.main()
