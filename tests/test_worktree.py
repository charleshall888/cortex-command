"""Unit tests for worktree.py .venv symlink behavior.

Tests three scenarios:
1. .venv present in repo root -> symlink created in worktree
2. .venv absent from repo root -> no error, no symlink
3. Cross-repo worktree -> no symlink even when .venv exists
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

import pytest

from cortex_command.pipeline.worktree import create_worktree, resolve_worktree_root


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

            with patch("cortex_command.pipeline.worktree._repo_root", return_value=tmppath):
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

            with patch("cortex_command.pipeline.worktree._repo_root", return_value=tmppath):
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


class TestWorktreeCreateFailure(unittest.TestCase):
    """Tests for create_worktree failure-path behavior.

    Covers:
    - Orphan branch cleanup on failed `git worktree add -b` (Requirement 1)
    - Stderr surfaced in raised exception message (Requirement 2)
    - Exception type is ValueError, not CalledProcessError (Requirement 3)
    - Cleanup failure silently swallowed (Requirement 4)
    """

    def test_failure_cleans_up_orphan_branch_and_raises_valueerror_with_stderr(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            branch = _init_git_repo(tmppath)

            # Pre-create the target worktree dir as a NON-EMPTY non-worktree
            # directory. The non-empty requirement is load-bearing: git
            # accepts an empty existing directory as a valid worktree target,
            # so an empty dir would not trigger the failure path.
            target_dir = tmppath / ".claude" / "worktrees" / "orphan-test"
            target_dir.mkdir(parents=True)
            (target_dir / "sentinel.txt").write_text("block")

            with patch("cortex_command.pipeline.worktree._repo_root", return_value=tmppath):
                with self.assertRaises(ValueError) as ctx:
                    create_worktree("orphan-test", base_branch=branch)

            exc = ctx.exception
            self.assertIsInstance(exc, ValueError)
            self.assertNotIsInstance(exc, subprocess.CalledProcessError)

            match = re.match(r"^worktree_creation_failed: (.+)", str(exc))
            self.assertIsNotNone(
                match,
                f"Expected message to match 'worktree_creation_failed: .+', got: {str(exc)!r}",
            )
            # The captured group is non-empty (git stderr text for the
            # "fatal: ... already exists" error).
            self.assertTrue(match.group(1).strip())

            # Assert that the orphan branch was cleaned up: no branches
            # matching pipeline/orphan-test* remain.
            branch_list = subprocess.run(
                ["git", "branch", "--list", "pipeline/orphan-test*"],
                capture_output=True,
                text=True,
                cwd=str(tmppath),
            )
            self.assertEqual(branch_list.returncode, 0)
            self.assertEqual(branch_list.stdout, "")

    def test_failure_with_empty_stderr_yields_no_stderr_sentinel(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            def fake_run(cmd, *args, **kwargs):
                # Command-matching dispatcher. `cmd` is a list.
                if not isinstance(cmd, list):
                    # Defensive: treat any non-list invocation as a pass-
                    # through success.
                    return CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

                # `git rev-parse --verify refs/heads/...` used by
                # `_branch_exists`. Pretend the branch does NOT exist so
                # `_resolve_branch_name` returns `pipeline/{feature}` on the
                # first try.
                if cmd[:3] == ["git", "rev-parse", "--verify"]:
                    return CompletedProcess(args=cmd, returncode=1, stdout="", stderr="")

                # `git worktree add` — the failing call under test. Return
                # exit 128 with empty stderr to exercise the "(no stderr)"
                # sentinel branch.
                if cmd[:3] == ["git", "worktree", "add"]:
                    return CompletedProcess(args=cmd, returncode=128, stdout="", stderr="")

                # `git branch -D <branch>` — cleanup call. Succeed silently.
                if cmd[:3] == ["git", "branch", "-D"]:
                    return CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

                # Fallback: return success.
                return CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

            with patch("cortex_command.pipeline.worktree._repo_root", return_value=tmppath), \
                    patch("cortex_command.pipeline.worktree.subprocess.run", side_effect=fake_run):
                with self.assertRaises(ValueError) as ctx:
                    create_worktree("empty-stderr-test", base_branch="main")

            self.assertEqual(
                str(ctx.exception),
                "worktree_creation_failed: (no stderr)",
            )

    def test_cleanup_failure_silently_swallowed_original_raised_unchanged(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            def fake_run(cmd, *args, **kwargs):
                if not isinstance(cmd, list):
                    return CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

                # `_branch_exists` lookup — pretend branch does not exist.
                if cmd[:3] == ["git", "rev-parse", "--verify"]:
                    return CompletedProcess(args=cmd, returncode=1, stdout="", stderr="")

                # `git worktree add` — fail with a specific stderr.
                if cmd[:3] == ["git", "worktree", "add"]:
                    return CompletedProcess(
                        args=cmd, returncode=128, stdout="", stderr="fatal: simulated"
                    )

                # `git branch -D <branch>` — cleanup ALSO fails. This must
                # be silently swallowed; the original error should still
                # surface unchanged.
                if cmd[:3] == ["git", "branch", "-D"]:
                    return CompletedProcess(
                        args=cmd,
                        returncode=1,
                        stdout="",
                        stderr="error: branch deletion failed",
                    )

                return CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

            with patch("cortex_command.pipeline.worktree._repo_root", return_value=tmppath), \
                    patch("cortex_command.pipeline.worktree.subprocess.run", side_effect=fake_run):
                with self.assertRaises(ValueError) as ctx:
                    create_worktree("cleanup-fail-test", base_branch="main")

            self.assertEqual(
                str(ctx.exception),
                "worktree_creation_failed: fatal: simulated",
            )


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------------
# Tests for resolve_worktree_root() — one test per resolution branch (R6).
# Uses pytest monkeypatch to isolate env vars and patch settings.local.json.
# ---------------------------------------------------------------------------

class TestResolveWorktreeRoot:
    """Tests for resolve_worktree_root() covering each resolution branch."""

    def test_branch_a_cortex_worktree_root_env_var(self, monkeypatch, tmp_path):
        """Branch (a): CORTEX_WORKTREE_ROOT env var takes precedence."""
        custom_root = str(tmp_path / "custom-roots")
        monkeypatch.setenv("CORTEX_WORKTREE_ROOT", custom_root)
        # Unset TMPDIR so the $TMPDIR expansion is deterministic
        monkeypatch.delenv("TMPDIR", raising=False)

        result = resolve_worktree_root("my-feature", session_id=None)

        assert result == tmp_path / "custom-roots" / "my-feature"

    def test_branch_a_tmpdir_expansion_in_env_var(self, monkeypatch, tmp_path):
        """Branch (a): $TMPDIR inside CORTEX_WORKTREE_ROOT is expanded."""
        monkeypatch.setenv("TMPDIR", str(tmp_path))
        monkeypatch.setenv("CORTEX_WORKTREE_ROOT", "$TMPDIR/worktrees")

        result = resolve_worktree_root("feat", session_id="sess-1")

        assert result == tmp_path / "worktrees" / "feat"

    def test_branch_b_registered_path_from_settings(self, monkeypatch, tmp_path):
        """Branch (b): registered path from settings.local.json used when env var absent."""
        monkeypatch.delenv("CORTEX_WORKTREE_ROOT", raising=False)

        # Write a fake settings.local.json with a worktrees/ entry.
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        registered_root = tmp_path / "sandbox-worktrees"
        settings = {
            "sandbox": {
                "filesystem": {
                    "allowWrite": [
                        str(tmp_path / "cortex"),
                        str(registered_root) + "/worktrees/",
                    ]
                }
            }
        }
        (claude_dir / "settings.local.json").write_text(json.dumps(settings))

        with patch(
            "cortex_command.pipeline.worktree.Path.home",
            return_value=tmp_path,
        ):
            result = resolve_worktree_root("feat", session_id=None)

        # The first entry containing "worktrees/" is the registered root;
        # feature is appended.
        assert result == Path(str(registered_root) + "/worktrees/") / "feat"

    def test_branch_c_default_same_repo(self, monkeypatch, tmp_path):
        """Branch (c): default same-repo path when no env var and no registered path."""
        monkeypatch.delenv("CORTEX_WORKTREE_ROOT", raising=False)

        with patch(
            "cortex_command.pipeline.worktree._registered_worktree_root",
            return_value=None,
        ), patch(
            "cortex_command.pipeline.worktree._repo_root",
            return_value=tmp_path,
        ):
            result = resolve_worktree_root("my-feat", session_id=None)

        assert result == tmp_path / ".claude" / "worktrees" / "my-feat"

    def test_branch_d_cross_repo_tmpdir(self, monkeypatch, tmp_path):
        """Branch (d): cross-repo path uses $TMPDIR when session_id is provided."""
        monkeypatch.delenv("CORTEX_WORKTREE_ROOT", raising=False)
        monkeypatch.setenv("TMPDIR", str(tmp_path))

        with patch(
            "cortex_command.pipeline.worktree._registered_worktree_root",
            return_value=None,
        ):
            result = resolve_worktree_root("feat", session_id="sess-42")

        assert result == tmp_path / "overnight-worktrees" / "sess-42" / "feat"

    def test_branch_a_wins_over_b_c_d(self, monkeypatch, tmp_path):
        """Branch (a) takes priority over all other branches."""
        monkeypatch.setenv("CORTEX_WORKTREE_ROOT", str(tmp_path / "override"))
        monkeypatch.delenv("TMPDIR", raising=False)

        registered_root = tmp_path / "registered" / "worktrees/"
        with patch(
            "cortex_command.pipeline.worktree._registered_worktree_root",
            return_value=registered_root,
        ), patch(
            "cortex_command.pipeline.worktree._repo_root",
            return_value=tmp_path / "repo",
        ):
            result = resolve_worktree_root("feat", session_id="sess-1")

        assert result == tmp_path / "override" / "feat"

    def test_branch_b_wins_over_c_d(self, monkeypatch, tmp_path):
        """Branch (b) takes priority over (c) and (d) when env var is unset."""
        monkeypatch.delenv("CORTEX_WORKTREE_ROOT", raising=False)
        monkeypatch.setenv("TMPDIR", str(tmp_path / "tmp"))

        registered_root = tmp_path / "registered-worktrees"
        with patch(
            "cortex_command.pipeline.worktree._registered_worktree_root",
            return_value=registered_root,
        ), patch(
            "cortex_command.pipeline.worktree._repo_root",
            return_value=tmp_path / "repo",
        ):
            result = resolve_worktree_root("feat", session_id="sess-1")

        assert result == registered_root / "feat"

    def test_no_settings_file_falls_through_to_c(self, monkeypatch, tmp_path):
        """When settings.local.json is absent, branch (b) returns None and (c) is used."""
        monkeypatch.delenv("CORTEX_WORKTREE_ROOT", raising=False)

        with patch(
            "cortex_command.pipeline.worktree.Path.home",
            return_value=tmp_path,  # No .claude/settings.local.json here
        ), patch(
            "cortex_command.pipeline.worktree._repo_root",
            return_value=tmp_path / "repo",
        ):
            result = resolve_worktree_root("feat", session_id=None)

        assert result == tmp_path / "repo" / ".claude" / "worktrees" / "feat"

    def test_settings_without_worktrees_marker_falls_through(self, monkeypatch, tmp_path):
        """Settings entries without 'worktrees/' marker don't match branch (b)."""
        monkeypatch.delenv("CORTEX_WORKTREE_ROOT", raising=False)

        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings = {
            "sandbox": {
                "filesystem": {
                    "allowWrite": [
                        str(tmp_path / "cortex"),
                        str(tmp_path / "other-path"),
                    ]
                }
            }
        }
        (claude_dir / "settings.local.json").write_text(json.dumps(settings))

        with patch(
            "cortex_command.pipeline.worktree.Path.home",
            return_value=tmp_path,
        ), patch(
            "cortex_command.pipeline.worktree._repo_root",
            return_value=tmp_path / "repo",
        ):
            result = resolve_worktree_root("feat", session_id=None)

        assert result == tmp_path / "repo" / ".claude" / "worktrees" / "feat"
