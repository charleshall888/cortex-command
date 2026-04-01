"""Unit tests for worktree.py .venv symlink behavior.

Tests three scenarios:
1. .venv present in repo root -> symlink created in worktree
2. .venv absent from repo root -> no error, no symlink
3. Cross-repo worktree -> no symlink even when .venv exists
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from claude.pipeline.worktree import create_worktree


def _init_git_repo(path: Path) -> str:
    """Initialize a git repo with an initial empty commit.

    Returns the name of the default branch (e.g. 'main' or 'master').
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


class TestWorktreeVenvSymlink(unittest.TestCase):
    """Tests for .venv symlink creation during worktree setup."""

    def test_venv_symlink_created_when_venv_present(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            branch = _init_git_repo(tmppath)

            # Create a .venv directory in the repo root
            (tmppath / ".venv").mkdir()

            with patch("claude.pipeline.worktree._repo_root", return_value=tmppath):
                info = create_worktree("test-feature", base_branch=branch)

            self.assertTrue((info.path / ".venv").is_symlink())
            self.assertEqual(
                os.readlink(info.path / ".venv"),
                str(tmppath / ".venv"),
            )

    def test_venv_symlink_skipped_when_venv_absent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            branch = _init_git_repo(tmppath)

            # No .venv directory created

            with patch("claude.pipeline.worktree._repo_root", return_value=tmppath):
                info = create_worktree("test-feature-2", base_branch=branch)

            self.assertFalse((info.path / ".venv").is_symlink())

    def test_cross_repo_no_venv_symlink(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            branch = _init_git_repo(tmppath)

            # Create a .venv directory in the repo root
            (tmppath / ".venv").mkdir()

            info = create_worktree(
                "test-feature-3",
                base_branch=branch,
                repo_path=tmppath,
                session_id=tmppath.name,
            )

            self.assertFalse((info.path / ".venv").is_symlink())


if __name__ == "__main__":
    unittest.main()
