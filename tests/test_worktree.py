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

from cortex_command.pipeline.worktree import (
    _resolve_branch_name,
    create_worktree,
    resolve_worktree_root,
)


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

            # Isolate $TMPDIR so branch (c)'s default doesn't collide with
            # parallel/previous test runs sharing the system tmpdir.
            isolated_tmpdir = tmppath / "tmp"
            isolated_tmpdir.mkdir()

            with patch("cortex_command.pipeline.worktree._repo_root", return_value=tmppath), \
                    patch.dict(os.environ, {"TMPDIR": str(isolated_tmpdir)}):
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

            # Isolate $TMPDIR so branch (c)'s default doesn't collide with
            # parallel/previous test runs sharing the system tmpdir.
            isolated_tmpdir = tmppath / "tmp"
            isolated_tmpdir.mkdir()

            with patch("cortex_command.pipeline.worktree._repo_root", return_value=tmppath), \
                    patch.dict(os.environ, {"TMPDIR": str(isolated_tmpdir)}):
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

            # Branch (c) now resolves to <repo>/.claude/worktrees/<feature>.
            # Pre-create the target worktree dir as a NON-EMPTY non-worktree
            # directory. The non-empty requirement is load-bearing: git
            # accepts an empty existing directory as a valid worktree target,
            # so an empty dir would not trigger the failure path.
            target_dir = (tmppath / ".claude" / "worktrees" / "orphan-test").resolve()
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
# Uses pytest monkeypatch to isolate env vars; branch (c) uses _repo_root.
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

    def test_branch_c_default_repo_relative(self, monkeypatch, tmp_path):
        """Branch (c): default <repo>/.claude/worktrees/<feature> when no env var."""
        monkeypatch.delenv("CORTEX_WORKTREE_ROOT", raising=False)
        repo = tmp_path / "repo"
        repo.mkdir()

        with patch(
            "cortex_command.pipeline.worktree._repo_root",
            return_value=repo,
        ):
            result = resolve_worktree_root("my-feat", session_id=None)

        assert result == (repo / ".claude" / "worktrees" / "my-feat").resolve()

    def test_branch_d_cross_repo_tmpdir(self, monkeypatch, tmp_path):
        """Branch (d): cross-repo path uses $TMPDIR when session_id is provided."""
        monkeypatch.delenv("CORTEX_WORKTREE_ROOT", raising=False)
        monkeypatch.setenv("TMPDIR", str(tmp_path))

        result = resolve_worktree_root("feat", session_id="sess-42")

        assert result == tmp_path / "overnight-worktrees" / "sess-42" / "feat"

    def test_branch_a_wins_over_c_d(self, monkeypatch, tmp_path):
        """Branch (a) takes priority over all other branches."""
        monkeypatch.setenv("CORTEX_WORKTREE_ROOT", str(tmp_path / "override"))
        monkeypatch.delenv("TMPDIR", raising=False)

        with patch(
            "cortex_command.pipeline.worktree._repo_root",
            return_value=tmp_path / "repo",
        ):
            result = resolve_worktree_root("feat", session_id="sess-1")

        assert result == tmp_path / "override" / "feat"

    def test_branch_d_wins_over_c_when_session_id_set(self, monkeypatch, tmp_path):
        """Branch (d) takes priority over (c) when session_id is provided and no env var."""
        monkeypatch.delenv("CORTEX_WORKTREE_ROOT", raising=False)
        monkeypatch.setenv("TMPDIR", str(tmp_path / "tmp"))

        with patch(
            "cortex_command.pipeline.worktree._repo_root",
            return_value=tmp_path / "repo",
        ):
            result = resolve_worktree_root("feat", session_id="sess-1")

        assert result == (tmp_path / "tmp") / "overnight-worktrees" / "sess-1" / "feat"


# ---------------------------------------------------------------------------
# New dedicated regression tests for R1, R2, R3, R4 (Phase 1 verification).
# Tests are named per their verify-rN slug so pytest collection can confirm
# their presence via --collect-only.
# ---------------------------------------------------------------------------


class TestVerifyR1BranchCRepoRelative:
    """R1: branch (c) default returns <repo>/.claude/worktrees/<feature>."""

    def test_branch_c_default_returns_repo_relative(self, monkeypatch, tmp_path):
        """verify-r1: <repo>/.claude/worktrees/<feature> is the new default."""
        monkeypatch.delenv("CORTEX_WORKTREE_ROOT", raising=False)
        repo = tmp_path / "repo"
        repo.mkdir()

        with patch(
            "cortex_command.pipeline.worktree._repo_root",
            return_value=repo,
        ):
            result = resolve_worktree_root("verify-r1", session_id=None)

        assert result == (repo / ".claude" / "worktrees" / "verify-r1").resolve()


class TestVerifyR2BranchCPathResolved:
    """R2: branch (c) canonicalizes via Path.resolve() so symlinks collapse."""

    def test_branch_c_path_is_resolved(self, monkeypatch, tmp_path):
        """verify-r2: a symlinked repo_root is canonicalized to its real target."""
        monkeypatch.delenv("CORTEX_WORKTREE_ROOT", raising=False)

        real_repo = tmp_path / "real-repo"
        real_repo.mkdir()
        symlink_repo = tmp_path / "repo-symlink"
        symlink_repo.symlink_to(real_repo)

        with patch(
            "cortex_command.pipeline.worktree._repo_root",
            return_value=symlink_repo,
        ):
            result = resolve_worktree_root("verify-r2", session_id=None)

        # The result must use the resolved (canonical) form of repo_root,
        # not the symlink path itself.
        assert str(result) == str((real_repo / ".claude" / "worktrees" / "verify-r2").resolve())
        # And explicitly NOT the symlink form.
        assert not str(result).startswith(str(symlink_repo) + "/")

    def test_branch_c_path_no_symlink_unchanged(self, monkeypatch, tmp_path):
        """verify-r2 negative control: non-symlink repo_root result is unchanged."""
        monkeypatch.delenv("CORTEX_WORKTREE_ROOT", raising=False)
        repo = tmp_path / "repo"
        repo.mkdir()

        with patch(
            "cortex_command.pipeline.worktree._repo_root",
            return_value=repo,
        ):
            result = resolve_worktree_root("verify-r2-neg", session_id=None)

        assert result == (repo / ".claude" / "worktrees" / "verify-r2-neg").resolve()


class TestVerifyR4CleanupWorktreeRoutesThroughResolver:
    """R4: cleanup_worktree()'s fallback routes through resolve_worktree_root()."""

    def test_cleanup_worktree_routes_through_resolver(self, monkeypatch, tmp_path):
        """verify-r4: cleanup_worktree() with no explicit path calls the resolver."""
        from cortex_command.pipeline import worktree as wt_mod

        sentinel = tmp_path / "sentinel-resolver-path"
        sentinel.mkdir()

        calls: list[tuple] = []

        def fake_resolver(feature, session_id=None, repo_root=None):
            calls.append((feature, session_id, repo_root))
            return sentinel

        # Stub out subprocess.run entirely so cleanup_worktree exercises the
        # resolver call without touching real git state.
        def fake_run(cmd, *args, **kwargs):
            return CompletedProcess(args=cmd, returncode=1, stdout="", stderr="")

        monkeypatch.setattr(wt_mod, "resolve_worktree_root", fake_resolver)
        monkeypatch.setattr(wt_mod, "_repo_root", lambda: tmp_path)
        monkeypatch.setattr(wt_mod.subprocess, "run", fake_run)

        wt_mod.cleanup_worktree("verify-r4", branch="pipeline/verify-r4")

        # The resolver was invoked exactly once with the right arguments.
        assert calls == [("verify-r4", None, tmp_path)]

    def test_cleanup_worktree_explicit_path_bypasses_resolver(self, monkeypatch, tmp_path):
        """verify-r4: explicit worktree_path bypasses the resolver entirely."""
        from cortex_command.pipeline import worktree as wt_mod

        calls: list[tuple] = []

        def fake_resolver(feature, session_id=None, repo_root=None):
            calls.append((feature, session_id, repo_root))
            return tmp_path / "should-not-be-used"

        def fake_run(cmd, *args, **kwargs):
            return CompletedProcess(args=cmd, returncode=1, stdout="", stderr="")

        monkeypatch.setattr(wt_mod, "resolve_worktree_root", fake_resolver)
        monkeypatch.setattr(wt_mod, "_repo_root", lambda: tmp_path)
        monkeypatch.setattr(wt_mod.subprocess, "run", fake_run)

        explicit = tmp_path / "explicit-path"
        wt_mod.cleanup_worktree("verify-r4-neg", branch="pipeline/verify-r4-neg", worktree_path=explicit)

        # When worktree_path is given, the resolver MUST NOT be consulted.
        assert calls == []


# R11: atime-touch guard on create_worktree()'s idempotent return branch.
#
# The guard refreshes the worktree's access time on lifecycle resume so
# macOS's nightly dirhelper purge (3-day atime-based eviction of
# /var/folders/) does not silently delete paused/deferred features. The
# tests below are module-level functions (not class methods) so they match
# the plan.md Task 9 verification selector:
#   pytest tests/test_worktree.py::test_atime_touch_distinguishes_guard_set_from_creation_fresh


def test_atime_touch_distinguishes_guard_set_from_creation_fresh(
    monkeypatch, tmp_path
):
    """Positive: idempotent re-invocation advances the worktree's atime."""
    import time as _time

    monkeypatch.delenv("CORTEX_WORKTREE_ROOT", raising=False)
    monkeypatch.delenv("CORTEX_SKIP_ATIME_TOUCH", raising=False)
    isolated_tmpdir = tmp_path / "tmp"
    isolated_tmpdir.mkdir()
    monkeypatch.setenv("TMPDIR", str(isolated_tmpdir))

    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    branch = _init_git_repo(repo_dir)

    with patch(
        "cortex_command.pipeline.worktree._repo_root", return_value=repo_dir
    ):
        info = create_worktree("atime-guard-positive", base_branch=branch)

        # Set both atime and mtime to a known-old timestamp so we can
        # observe whether the guard moved atime forward.
        old_time = _time.time() - 3600
        os.utime(info.path, (old_time, old_time))

        # Re-invoke create_worktree to exercise the idempotent return.
        create_worktree("atime-guard-positive", base_branch=branch)

    new_atime = os.stat(info.path).st_atime
    assert new_atime > old_time + 60, (
        f"expected guard to advance atime; old_time={old_time}, "
        f"new_atime={new_atime}, delta={new_atime - old_time}"
    )


def test_atime_touch_skipped_with_env_opt_out(monkeypatch, tmp_path):
    """Negative: CORTEX_SKIP_ATIME_TOUCH=1 leaves atime unchanged."""
    import time as _time

    monkeypatch.delenv("CORTEX_WORKTREE_ROOT", raising=False)
    isolated_tmpdir = tmp_path / "tmp"
    isolated_tmpdir.mkdir()
    monkeypatch.setenv("TMPDIR", str(isolated_tmpdir))

    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    branch = _init_git_repo(repo_dir)

    with patch(
        "cortex_command.pipeline.worktree._repo_root", return_value=repo_dir
    ):
        info = create_worktree("atime-guard-negative", base_branch=branch)

        old_time = _time.time() - 3600
        os.utime(info.path, (old_time, old_time))

        # Opt out of the guard before the idempotent re-invocation.
        monkeypatch.setenv("CORTEX_SKIP_ATIME_TOUCH", "1")
        create_worktree("atime-guard-negative", base_branch=branch)

    new_atime = os.stat(info.path).st_atime
    assert abs(new_atime - old_time) <= 5, (
        f"expected atime unchanged with opt-out; old_time={old_time}, "
        f"new_atime={new_atime}, delta={new_atime - old_time}"
    )


# ---------------------------------------------------------------------------
# Tests for _resolve_branch_name() prefix parameter (T6 — interactive support).
# ---------------------------------------------------------------------------


class TestResolveBranchNamePrefix:
    """Tests for the prefix parameter added to _resolve_branch_name()."""

    def test_interactive_prefix_returns_interactive_slug(self, tmp_path):
        """verify-t6: prefix="interactive" yields interactive/{slug} branch name."""
        _init_git_repo(tmp_path)
        result = _resolve_branch_name("test-fixture", repo=tmp_path, prefix="interactive")
        assert result == "interactive/test-fixture"

    def test_default_prefix_is_pipeline(self, tmp_path):
        """Default prefix produces pipeline/{feature} (backward-compatible)."""
        _init_git_repo(tmp_path)
        result = _resolve_branch_name("my-feature", repo=tmp_path)
        assert result == "pipeline/my-feature"

    def test_interactive_prefix_collision_appends_suffix(self, tmp_path):
        """Collision suffix increments correctly for interactive/ prefix."""
        _init_git_repo(tmp_path)
        # Pre-create the branch so the first probe finds a collision.
        subprocess.run(
            ["git", "branch", "interactive/collision-feat"],
            capture_output=True,
            text=True,
            check=True,
            cwd=str(tmp_path),
        )
        result = _resolve_branch_name("collision-feat", repo=tmp_path, prefix="interactive")
        assert result == "interactive/collision-feat-2"


# ---------------------------------------------------------------------------
# .mcp.json propagation invariant (#260): verify that git worktree add into
# <repo>/.claude/worktrees/<feature>/ succeeds and propagates .mcp.json into
# the worktree. The matching deny invariant (writes to .mcp.json blocked) is
# enforced by the Claude Code JS tool layer, not the kernel — a pytest
# subprocess open() will not raise PermissionError. The deny half is
# documented here and observable end-to-end only inside a live Claude Code
# session; this test pins the propagation half plus a best-effort note.
# ---------------------------------------------------------------------------


def test_mcp_json_propagation_and_deny_invariant(tmp_path):
    """Verify .mcp.json propagates into a .claude/worktrees/<feature>/ worktree.

    The deny invariant (sandbox blocks writes to .mcp.json) is enforced by
    the Claude Code JS tool layer, not by Seatbelt at the kernel level. A
    pytest subprocess open() will NOT raise PermissionError. The deny half
    of this invariant is observable end-to-end only inside a live Claude
    Code session; this test pins the propagation half so a regression in
    git worktree add behavior (e.g. .mcp.json suddenly excluded) is caught.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    branch = _init_git_repo(repo)

    # Seed .mcp.json in the repo and commit it so git worktree add propagates
    # the file to the new worktree's checkout.
    mcp_content = '{"mcpServers": {}}\n'
    (repo / ".mcp.json").write_text(mcp_content)
    subprocess.run(
        ["git", "add", ".mcp.json"],
        check=True,
        cwd=str(repo),
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "-c", "commit.gpgsign=false",
            "-c", "user.email=t@t",
            "-c", "user.name=t",
            "commit", "-m", "seed mcp",
        ],
        check=True,
        cwd=str(repo),
        capture_output=True,
    )

    with patch("cortex_command.pipeline.worktree._repo_root", return_value=repo):
        info = create_worktree("probe-mcp", base_branch=branch)

    # Propagation: the worktree contains a copy of .mcp.json with the
    # committed contents.
    worktree_mcp = info.path / ".mcp.json"
    assert worktree_mcp.exists(), (
        f"expected .mcp.json to propagate into worktree at {worktree_mcp}; "
        "regression in git worktree add behavior would break sandbox "
        "trust handoff for the spawned claude session."
    )
    assert worktree_mcp.read_text() == mcp_content
