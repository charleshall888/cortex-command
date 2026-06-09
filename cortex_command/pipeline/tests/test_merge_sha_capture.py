"""Tests for live merge-SHA capture across the three roll-back-able merge sites.

These tests cover R2 of overnight-review-gate-crashes-to-cycle: each site that
produces a merge that may later need reverting must surface the *live*
integration-branch merge commit so a later rollback can ``git revert -m 1``
that exact SHA under the lock.

The three sites and their result fields:
  - merge.py            -> MergeResult.merge_sha          (primary merge)
  - review_dispatch.py  -> ReviewResult.merge_sha         (cycle-1 rework re-merge)
  - merge_recovery.py   -> MergeRecoveryResult.merge_sha  (post-test-recovery re-merge)

The MergeResult tests use a real git repo (not mocks) so the assertion that the
captured SHA is the actual integration-branch merge commit — a commit with two
parents, equal to ``git rev-parse HEAD`` on the base branch — is observable and
not self-sealing. The ReviewResult / MergeRecoveryResult tests assert the
threading contract (the result carries the underlying MergeResult.merge_sha)
using a real MergeResult value so the SHA propagated is the genuine merge commit.
"""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# conftest.py installs the SDK stub under pytest, but call it directly so
# unittest runs of this module also get the stub before the dispatch import.
from cortex_command.pipeline.tests.conftest import _install_sdk_stub
_install_sdk_stub()

# Pre-load the overnight package before importing review_dispatch so its
# transitive `from cortex_command.overnight.deferral import …` does not
# trigger overnight/__init__.py to circle back through outcome_router →
# review_dispatch while review_dispatch is still mid-import. See the
# identical preamble in test_review_dispatch.py for the dependency chain.
import cortex_command.overnight.deferral  # noqa: F401, E402

from cortex_command.pipeline.merge import (  # noqa: E402
    MergeResult,
    TestResult,
    merge_feature,
)
from cortex_command.pipeline.merge_recovery import (  # noqa: E402
    MergeRecoveryResult,
    recover_test_failure,
)
import cortex_command.pipeline.review_dispatch as review_dispatch  # noqa: E402


# ---------------------------------------------------------------------------
# Real-git harness for MergeResult.merge_sha
# ---------------------------------------------------------------------------

def _git(repo: Path, *args: str) -> str:
    """Run a git command in *repo* and return stripped stdout."""
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        cwd=repo,
        check=True,
    )
    return result.stdout.strip()


def _init_git_identity(repo: Path) -> None:
    """Init a repo on ``main`` with a committer identity and signing disabled.

    Disabling ``commit.gpgsign`` / ``tag.gpgsign`` keeps these throwaway test
    repos independent of the developer's global GPG-signing config (which is
    unavailable in sandboxed CI).
    """
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "commit.gpgsign", "false")
    _git(repo, "config", "tag.gpgsign", "false")


def _commit(repo: Path, message: str) -> None:
    """Commit staged changes, bypassing any installed commit-msg hooks.

    Capitalized subject + ``--no-verify`` keeps these throwaway test commits
    independent of the repo's commit-message validation hook.
    """
    _git(repo, "commit", "-q", "--no-verify", "-m", message)


def _init_repo_with_feature_branch(repo: Path, feature: str) -> str:
    """Create a real git repo with a base branch and a divergent feature branch.

    Returns the fully-qualified feature branch name (``pipeline/<feature>``).
    """
    _init_git_identity(repo)

    (repo / "base.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "base.txt")
    _commit(repo, "Base commit")

    branch = f"pipeline/{feature}"
    _git(repo, "checkout", "-q", "-b", branch)
    (repo / "feature.txt").write_text("feature change\n", encoding="utf-8")
    _git(repo, "add", "feature.txt")
    _commit(repo, "Feature commit")

    # Return to main so merge_feature checks it out cleanly.
    _git(repo, "checkout", "-q", "main")
    return branch


class TestMergeResultSha(unittest.TestCase):
    """MergeResult.merge_sha equals the actual integration-branch merge commit."""

    def test_merge_sha_is_the_merge_commit_with_two_parents(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            branch = _init_repo_with_feature_branch(repo, "feat-a")

            result = merge_feature(
                "feat-a",
                base_branch="main",
                test_command=None,
                ci_check=False,
                branch=branch,
                repo_path=repo,
            )

            self.assertTrue(result.success)
            self.assertIsNotNone(result.merge_sha)

            # The captured SHA must equal HEAD on the base branch (the merge
            # commit), not the feature-branch tip.
            head_sha = _git(repo, "rev-parse", "HEAD")
            self.assertEqual(result.merge_sha, head_sha)

            feature_tip = _git(repo, "rev-parse", branch)
            self.assertNotEqual(result.merge_sha, feature_tip)

            # The captured commit is a real merge commit: it has two parents.
            parents = _git(repo, "rev-list", "--parents", "-n", "1", result.merge_sha)
            parent_shas = parents.split()[1:]
            self.assertEqual(len(parent_shas), 2,
                             f"merge_sha is not a two-parent merge commit: {parents}")

    def test_revert_m1_of_captured_sha_is_valid(self):
        """git revert -m 1 <merge_sha> succeeds — confirms it is a merge commit."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            branch = _init_repo_with_feature_branch(repo, "feat-b")

            result = merge_feature(
                "feat-b",
                base_branch="main",
                test_command=None,
                ci_check=False,
                branch=branch,
                repo_path=repo,
            )
            self.assertIsNotNone(result.merge_sha)

            revert = subprocess.run(
                ["git", "revert", "-m", "1", "--no-edit", result.merge_sha],
                capture_output=True,
                text=True,
                cwd=repo,
            )
            self.assertEqual(revert.returncode, 0,
                             f"revert -m 1 failed: {revert.stderr}")
            # After the revert the feature change is gone from the tree.
            self.assertFalse((repo / "feature.txt").exists())

    def test_merge_sha_none_when_test_failure_reverts(self):
        """When the post-merge test gate fails and merge.py reverts, merge_sha is None."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            branch = _init_repo_with_feature_branch(repo, "feat-c")

            result = merge_feature(
                "feat-c",
                base_branch="main",
                test_command="exit 1",  # force a post-merge test failure
                ci_check=False,
                branch=branch,
                repo_path=repo,
            )

            self.assertFalse(result.success)
            self.assertIsNone(result.merge_sha)

    def test_merge_sha_none_on_conflict(self):
        """A merge conflict (no merge landed) leaves merge_sha None."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _init_git_identity(repo)
            (repo / "f.txt").write_text("base\n", encoding="utf-8")
            _git(repo, "add", "f.txt")
            _commit(repo, "Base")

            branch = "pipeline/feat-d"
            _git(repo, "checkout", "-q", "-b", branch)
            (repo / "f.txt").write_text("feature version\n", encoding="utf-8")
            _git(repo, "add", "f.txt")
            _commit(repo, "Feature edit")
            _git(repo, "checkout", "-q", "main")
            # Diverge main on the same file to force a conflict.
            (repo / "f.txt").write_text("main version\n", encoding="utf-8")
            _git(repo, "add", "f.txt")
            _commit(repo, "Main edit")

            result = merge_feature(
                "feat-d",
                base_branch="main",
                test_command=None,
                ci_check=False,
                branch=branch,
                repo_path=repo,
            )

            self.assertFalse(result.success)
            self.assertTrue(result.conflict)
            self.assertIsNone(result.merge_sha)


# ---------------------------------------------------------------------------
# ReviewResult.merge_sha — cycle-1 rework re-merge threading
# ---------------------------------------------------------------------------

class TestReviewResultMergeSha(unittest.IsolatedAsyncioTestCase):
    """ReviewResult.merge_sha carries the cycle-1 re-merge's MergeResult.merge_sha."""

    async def _run_rework(self, cycle2_verdict: str, remerge_sha: str | None):
        """Drive dispatch_review through cycle-1 CHANGES_REQUESTED -> rework -> cycle 2.

        Returns the final ReviewResult.
        """
        with tempfile.TemporaryDirectory() as tmp:
            lifecycle_base = Path(tmp) / "lifecycle"
            (lifecycle_base / "feat").mkdir(parents=True, exist_ok=True)
            spec_path = Path(tmp) / "spec.md"
            spec_path.write_text("spec content\n", encoding="utf-8")
            worktree = Path(tmp) / "worktree"
            worktree.mkdir()

            # parse_verdict returns CHANGES_REQUESTED cycle 1 first, then the
            # cycle-2 verdict on the second call.
            verdicts = [
                {"verdict": "CHANGES_REQUESTED", "cycle": 1, "issues": ["fix x"]},
                {"verdict": cycle2_verdict, "cycle": 2, "issues": []},
            ]

            def _parse_side_effect(_path):
                return verdicts.pop(0)

            # The fix agent and review agents are dispatched via dispatch_task.
            dispatch_mock = AsyncMock(return_value=MagicMock(
                success=True, output="", cost_usd=0.0,
                error_type=None, error_detail=None,
            ))

            # The cycle-1 re-merge returns a MergeResult carrying the live SHA.
            remerge_result = MergeResult(
                success=True,
                feature="feat",
                conflict=False,
                test_result=TestResult(passed=True, output="", return_code=0),
                merge_sha=remerge_sha,
            )

            # SHA circuit-breaker reads HEAD before/after the fix agent; make
            # them differ so rework proceeds to the re-merge.
            sha_values = iter(["before_sha", "after_sha"])

            def _subproc_side_effect(cmd, **kwargs):
                proc = MagicMock()
                proc.returncode = 0
                proc.stdout = next(sha_values, "after_sha") + "\n"
                proc.stderr = ""
                return proc

            with patch.object(review_dispatch, "parse_verdict", side_effect=_parse_side_effect), \
                 patch.object(review_dispatch, "dispatch_task", dispatch_mock), \
                 patch.object(review_dispatch, "merge_feature", return_value=remerge_result), \
                 patch.object(review_dispatch.subprocess, "run", side_effect=_subproc_side_effect):
                # Seed a review.md so the early read of review_md_path works.
                (lifecycle_base / "feat" / "review.md").write_text(
                    "```json\n{}\n```\n", encoding="utf-8",
                )
                result = await review_dispatch.dispatch_review(
                    feature="feat",
                    worktree_path=worktree,
                    branch="pipeline/feat",
                    spec_path=spec_path,
                    complexity="complex",
                    criticality="high",
                    lifecycle_base=lifecycle_base,
                    deferred_dir=Path(tmp) / "deferred",
                    base_branch="main",
                    test_command=None,
                    repo_path=worktree,
                )
            return result

    async def test_approved_cycle2_carries_remerge_sha(self):
        result = await self._run_rework("APPROVED", remerge_sha="remerge123")
        self.assertTrue(result.approved)
        self.assertEqual(result.merge_sha, "remerge123")

    async def test_deferred_cycle2_carries_remerge_sha(self):
        result = await self._run_rework("REJECTED", remerge_sha="remerge456")
        self.assertTrue(result.deferred)
        self.assertEqual(result.merge_sha, "remerge456")

    async def test_no_rework_path_has_none_merge_sha(self):
        """A straight ERROR/REJECTED at cycle 1 (no re-merge) leaves merge_sha None."""
        with tempfile.TemporaryDirectory() as tmp:
            lifecycle_base = Path(tmp) / "lifecycle"
            (lifecycle_base / "feat").mkdir(parents=True, exist_ok=True)
            spec_path = Path(tmp) / "spec.md"
            spec_path.write_text("spec\n", encoding="utf-8")
            worktree = Path(tmp) / "worktree"
            worktree.mkdir()
            (lifecycle_base / "feat" / "review.md").write_text(
                "```json\n{}\n```\n", encoding="utf-8",
            )

            dispatch_mock = AsyncMock(return_value=MagicMock(
                success=True, output="", cost_usd=0.0,
                error_type=None, error_detail=None,
            ))
            with patch.object(
                review_dispatch, "parse_verdict",
                return_value={"verdict": "REJECTED", "cycle": 1, "issues": []},
            ), patch.object(review_dispatch, "dispatch_task", dispatch_mock):
                result = await review_dispatch.dispatch_review(
                    feature="feat",
                    worktree_path=worktree,
                    branch="pipeline/feat",
                    spec_path=spec_path,
                    complexity="complex",
                    criticality="high",
                    lifecycle_base=lifecycle_base,
                    deferred_dir=Path(tmp) / "deferred",
                    base_branch="main",
                    repo_path=worktree,
                )

            self.assertTrue(result.deferred)
            self.assertIsNone(result.merge_sha)


# ---------------------------------------------------------------------------
# MergeRecoveryResult.merge_sha — recovery re-merge threading
# ---------------------------------------------------------------------------

def _make_proc(returncode: int = 0, stdout: str = "", stderr: str = ""):
    proc = MagicMock()
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = stderr
    return proc


def _recovery_subprocess_side_effect(cmd, **kwargs):
    """Side-effect for merge_recovery.subprocess.run (dirty-base + diff checks)."""
    if isinstance(cmd, list):
        if "--show-toplevel" in cmd:
            return _make_proc(returncode=0, stdout="/fake/repo\n")
        if "--porcelain" in cmd:
            return _make_proc(returncode=0, stdout="")
        if "diff" in cmd:
            return _make_proc(returncode=0, stdout="")
    return _make_proc(returncode=0)


_RECOVERY_KWARGS = dict(
    feature="rec-feat",
    base_branch="main",
    test_output="FAILED test_foo",
    branch="pipeline/rec-feat",
    worktree_path=Path("/fake/worktree"),
    test_command="python -m pytest",
    pipeline_log_path=None,
)


class TestMergeRecoveryResultMergeSha(unittest.IsolatedAsyncioTestCase):
    """MergeRecoveryResult.merge_sha carries the recovery re-merge's merge commit."""

    async def test_flaky_success_carries_merge_sha(self):
        """Flaky-guard re-merge success surfaces the integration-branch merge SHA."""
        merge_ok = MergeResult(
            success=True, feature="rec-feat", conflict=False,
            test_result=TestResult(passed=True, output="", return_code=0),
            merge_sha="flaky_merge_sha",
        )
        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "cortex_command.pipeline.merge_recovery.subprocess.run",
                side_effect=_recovery_subprocess_side_effect,
            ), patch(
                "cortex_command.pipeline.merge.merge_feature",
                return_value=merge_ok,
            ):
                result = await recover_test_failure(
                    **{**_RECOVERY_KWARGS, "learnings_dir": Path(tmp)},
                )
        self.assertTrue(result.success)
        self.assertTrue(result.flaky)
        self.assertEqual(result.merge_sha, "flaky_merge_sha")

    async def test_repair_success_carries_merge_sha(self):
        """Repair-cycle re-merge success surfaces the integration-branch merge SHA."""
        merge_calls = {"n": 0}

        def _merge_side_effect(*args, **kwargs):
            merge_calls["n"] += 1
            if merge_calls["n"] == 1:
                # flaky guard fails
                return MergeResult(
                    success=False, feature="rec-feat", conflict=False,
                    test_result=TestResult(passed=False, output="x", return_code=1),
                    error="Tests failed",
                )
            # repair re-merge succeeds, carrying the live merge SHA
            return MergeResult(
                success=True, feature="rec-feat", conflict=False,
                test_result=TestResult(passed=True, output="", return_code=0),
                merge_sha="repair_merge_sha",
            )

        sha_seq = iter(["before", "after"])

        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "cortex_command.pipeline.merge_recovery.subprocess.run",
                side_effect=_recovery_subprocess_side_effect,
            ), patch(
                "cortex_command.pipeline.merge.merge_feature",
                side_effect=_merge_side_effect,
            ), patch(
                "cortex_command.pipeline.merge_recovery._get_branch_sha",
                side_effect=lambda _wt: next(sha_seq, "after"),
            ), patch(
                "cortex_command.pipeline.dispatch.dispatch_task",
                new_callable=AsyncMock,
            ) as mock_dispatch:
                mock_dispatch.return_value = MagicMock(
                    success=True, output="fixed", cost_usd=0.0,
                    error_type=None, error_detail=None,
                )
                result = await recover_test_failure(
                    **{**_RECOVERY_KWARGS, "learnings_dir": Path(tmp)},
                )
        self.assertTrue(result.success)
        self.assertEqual(result.merge_sha, "repair_merge_sha")

    async def test_failure_path_has_none_merge_sha(self):
        """A paused/exhausted recovery (no successful re-merge) leaves merge_sha None."""
        merge_fail = MergeResult(
            success=False, feature="rec-feat", conflict=False,
            test_result=TestResult(passed=False, output="x", return_code=1),
            error="Tests failed",
        )
        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "cortex_command.pipeline.merge_recovery.subprocess.run",
                side_effect=_recovery_subprocess_side_effect,
            ), patch(
                "cortex_command.pipeline.merge.merge_feature",
                return_value=merge_fail,
            ), patch(
                "cortex_command.pipeline.merge_recovery._get_branch_sha",
                return_value="same_sha",  # triggers circuit breaker pause
            ), patch(
                "cortex_command.pipeline.dispatch.dispatch_task",
                new_callable=AsyncMock,
            ) as mock_dispatch:
                mock_dispatch.return_value = MagicMock(
                    success=True, output="no changes", cost_usd=0.0,
                    error_type=None, error_detail=None,
                )
                result = await recover_test_failure(
                    **{**_RECOVERY_KWARGS, "learnings_dir": Path(tmp)},
                )
        self.assertFalse(result.success)
        self.assertIsNone(result.merge_sha)


if __name__ == "__main__":
    unittest.main()
