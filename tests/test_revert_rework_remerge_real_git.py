"""Real-git harness coverage for R4 (rework-path rollback reverts the *live*
re-merge SHA, querying branch state to avoid a failed double-revert).

The rework loop (``review_dispatch.dispatch_review``) creates a SECOND merge
commit when a cycle-1 ``CHANGES_REQUESTED`` triggers a fix + re-merge. If
cycle-2 then defers, the rollback in ``outcome_router.apply_feature_result``
must revert the *re-merge's* live SHA (threaded onto ``ReviewResult.merge_sha``
in R2) — NOT the stale original first-merge SHA — and must tolerate the case
where ``merge_feature`` already inline-reverted that re-merge on a post-merge
test failure (it logs ``merge_revert_error`` and returns ``success=False``
without ``check=True``). Reverting an already-reverted merge exits non-zero
with a clean tree; ``revert_merge`` queries branch state (``REVERT_HEAD``) to
treat that as a no-op success rather than a spurious conflict that would
escalate a bogus blocking deferral.

This module reuses the real-git harness Task 3 built in
``tests/test_revert_merge_real_git.py`` (``RealGitWorktree`` / ``_git`` /
``_make_real_ctx``) rather than rebuilding a parallel fixture. It builds real
``--no-ff`` merges (a first merge then a re-merge of the same feature branch)
so the rollback's effect on the integration branch's *tree* is observable, as
the spec's R4 acceptance requires.
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from cortex_command.overnight.outcome_router import apply_feature_result
from cortex_command.overnight.types import FeatureResult
from cortex_command.pipeline.merge import revert_merge

from tests.test_revert_merge_real_git import RealGitWorktree, _git, _make_real_ctx


def _remerge_feature_branch(wt: RealGitWorktree, branch: str, rel: str, content: str) -> str:
    """Model a cycle-1 rework re-merge of *branch* into main.

    Adds the rework "fix" commit to the already-merged feature branch — the
    fix the cycle-1 reviewer asked for, which introduces the file *rel* — then
    performs a second ``--no-ff`` merge into main. This is exactly the SECOND
    merge commit ``dispatch_review``'s rework loop produces via
    ``merge_feature``: ``git merge --no-ff`` of an already-merged branch brings
    only the new (post-first-merge) commits, so the re-merge's payload is the
    rework fix that introduces *rel*. Returns the re-merge SHA.

    Because *rel* is introduced by the re-merge (not the first merge),
    ``git revert -m 1 <re_sha>`` removes it — whereas reverting the stale
    first-merge SHA would leave it in place. That is the discriminator the R4
    rollback must get right.
    """
    _git("checkout", branch, cwd=wt.root)
    (wt.root / rel).write_text(content)
    _git("add", rel, cwd=wt.root)
    _git("commit", "-m", f"{branch}: rework fix", cwd=wt.root)
    re_sha = wt.merge_no_ff(branch)
    return re_sha


class TestRevertReworkRemergeRealGit(unittest.IsolatedAsyncioTestCase):
    async def test_cycle2_defer_reverts_live_remerge_not_stale_first_merge(self):
        """R4: a cycle-1 re-merge then a cycle-2 defer reverts the re-merge's
        LIVE SHA, leaving no feature code on the integration branch.

        The rework fix (the cycle-1 reviewer's requested change) introduces
        ``x_feature.txt`` and is carried onto main by the re-merge — so
        reverting the re-merge SHA removes it, whereas reverting the stale
        first-merge SHA would leave it in place. This asserts the rollback
        targets the re-merge SHA threaded onto ``ReviewResult.merge_sha``.
        """
        with TemporaryDirectory() as td:
            repo = Path(td) / "repo"
            repo.mkdir()
            session_dir = Path(td) / "session"
            session_dir.mkdir()
            wt = RealGitWorktree(repo)

            # First merge of feat-x carries a scaffold (pre-review state).
            x_branch = wt.feature_branch("feat-x", {"scaffold.txt": "scaffold\n"})
            first_merge_sha = wt.merge_no_ff(x_branch)
            self.assertIsNone(
                wt.file_on_main("x_feature.txt"),
                "the feature file must be introduced by the re-merge, not the "
                "first merge, so the SHA discriminator is meaningful",
            )

            # Cycle-1 rework re-merge introduces the feature file x_feature.txt.
            remerge_sha = _remerge_feature_branch(
                wt, x_branch, "x_feature.txt", "X content\n"
            )
            self.assertNotEqual(remerge_sha, first_merge_sha)

            # Sanity: the feature file is now on main (via the re-merge).
            self.assertEqual(wt.file_on_main("x_feature.txt"), "X content\n")

            ctx = _make_real_ctx(repo, session_dir)
            ctx.worktree_branches["feat-x"] = x_branch

            # The router's primary merge_feature returns the FIRST merge SHA;
            # dispatch_review's rework loop threads the LIVE re-merge SHA.
            merge_result = MagicMock(
                success=True, error=None, conflict=False, test_result=None,
                merge_sha=first_merge_sha,
            )
            review_result = MagicMock(
                deferred=True, verdict="CHANGES_REQUESTED", cycle=2,
                merge_sha=remerge_sha,
            )

            with (
                patch(
                    "cortex_command.overnight.outcome_router._get_changed_files",
                    return_value=["x_feature.txt"],
                ),
                patch(
                    "cortex_command.overnight.outcome_router.merge_feature",
                    return_value=merge_result,
                ),
                patch(
                    "cortex_command.overnight.outcome_router.requires_review",
                    return_value=True,
                ),
                patch(
                    "cortex_command.overnight.outcome_router.dispatch_review",
                    new=AsyncMock(return_value=review_result),
                ),
                patch("cortex_command.overnight.outcome_router.read_tier", return_value="L"),
                patch(
                    "cortex_command.overnight.outcome_router.read_criticality",
                    return_value="high",
                ),
                patch("cortex_command.overnight.outcome_router._write_back_to_backlog"),
                patch("cortex_command.overnight.outcome_router.overnight_log_event"),
                patch("cortex_command.overnight.outcome_router.cleanup_worktree"),
            ):
                await apply_feature_result(
                    "feat-x",
                    FeatureResult(name="feat-x", status="completed"),
                    ctx,
                )

            # No feature code remains on the integration branch: reverting the
            # live re-merge SHA removes x_feature.txt. Reverting the stale
            # first-merge SHA would have left it (the first merge never touched
            # it), so this discriminates the SHA choice.
            self.assertIsNone(
                wt.file_on_main("x_feature.txt"),
                "reverting the live re-merge SHA should remove feat-x's feature "
                "code; reverting the stale first-merge SHA would leave it",
            )
            # A revert commit of the RE-MERGE exists, and tree is clean (no
            # failed double-revert / half-applied state).
            self.assertTrue(
                any(s.startswith('Revert "Merge') for s in wt.log_subjects()),
                f"expected a revert commit; log subjects: {wt.log_subjects()}",
            )
            self.assertTrue(wt.working_tree_clean())
            self.assertFalse(wt.revert_in_progress())
            self.assertIn(
                "feat-x", [d["name"] for d in ctx.batch_result.features_deferred]
            )

    async def test_cycle2_defer_already_reverted_remerge_no_double_revert(self):
        """R4: when ``merge_feature`` already inline-reverted the re-merge on a
        post-merge test failure, the cycle-2 defer rollback queries branch
        state and does NOT attempt (or fail) a double-revert.

        Concretely: the re-merge SHA is reverted *before* the router's rollback
        runs (modeling ``merge_feature``'s test-failure inline revert). The
        rollback's ``revert_merge`` of that same SHA exits non-zero with a clean
        tree and no ``REVERT_HEAD``; it must report success-by-no-op, NOT abort
        and escalate a spurious 'do NOT re-run' blocking deferral.
        """
        with TemporaryDirectory() as td:
            repo = Path(td) / "repo"
            repo.mkdir()
            session_dir = Path(td) / "session"
            session_dir.mkdir()
            wt = RealGitWorktree(repo)

            x_branch = wt.feature_branch("feat-x", {"scaffold.txt": "scaffold\n"})
            first_merge_sha = wt.merge_no_ff(x_branch)
            remerge_sha = _remerge_feature_branch(
                wt, x_branch, "x_feature.txt", "X content\n"
            )
            self.assertEqual(wt.file_on_main("x_feature.txt"), "X content\n")

            # Model merge_feature's inline test-failure revert of the re-merge:
            # the re-merge is already netted out before the router rolls back.
            _git("checkout", "main", cwd=repo)
            _git("revert", "-m", "1", "--no-edit", remerge_sha, cwd=repo)
            self.assertIsNone(wt.file_on_main("x_feature.txt"))
            head_after_inline_revert = wt.head()

            captured_deferrals: list = []

            def _capture_write_deferral(deferral, deferred_dir=None):
                captured_deferrals.append(deferral)

            ctx = _make_real_ctx(repo, session_dir)
            ctx.worktree_branches["feat-x"] = x_branch

            merge_result = MagicMock(
                success=True, error=None, conflict=False, test_result=None,
                merge_sha=first_merge_sha,
            )
            review_result = MagicMock(
                deferred=True, verdict="CHANGES_REQUESTED", cycle=2,
                merge_sha=remerge_sha,
            )

            with (
                patch(
                    "cortex_command.overnight.outcome_router._get_changed_files",
                    return_value=["x_feature.txt"],
                ),
                patch(
                    "cortex_command.overnight.outcome_router.merge_feature",
                    return_value=merge_result,
                ),
                patch(
                    "cortex_command.overnight.outcome_router.requires_review",
                    return_value=True,
                ),
                patch(
                    "cortex_command.overnight.outcome_router.dispatch_review",
                    new=AsyncMock(return_value=review_result),
                ),
                patch(
                    "cortex_command.overnight.outcome_router.write_deferral",
                    side_effect=_capture_write_deferral,
                ),
                patch("cortex_command.overnight.outcome_router.read_tier", return_value="L"),
                patch(
                    "cortex_command.overnight.outcome_router.read_criticality",
                    return_value="high",
                ),
                patch("cortex_command.overnight.outcome_router._write_back_to_backlog"),
                patch("cortex_command.overnight.outcome_router.overnight_log_event"),
                patch("cortex_command.overnight.outcome_router.cleanup_worktree"),
            ):
                await apply_feature_result(
                    "feat-x",
                    FeatureResult(name="feat-x", status="completed"),
                    ctx,
                )

            # No failed double-revert: tree clean, no half-applied revert, and
            # HEAD is unchanged from the inline revert (the no-op added nothing).
            self.assertTrue(wt.working_tree_clean())
            self.assertFalse(wt.revert_in_progress())
            self.assertEqual(wt.head(), head_after_inline_revert)
            # Feature code stays gone (it was already reverted inline).
            self.assertIsNone(wt.file_on_main("x_feature.txt"))
            # No spurious 'do NOT re-run' conflict deferral was escalated — the
            # already-reverted no-op is NOT the dependent-conflict R-edge.
            self.assertEqual(
                captured_deferrals, [],
                "an already-reverted re-merge must not escalate a blocking "
                f"conflict deferral; got: {captured_deferrals}",
            )
            self.assertIn(
                "feat-x", [d["name"] for d in ctx.batch_result.features_deferred]
            )

    def test_revert_merge_unit_already_reverted_is_noop_success(self):
        """Direct unit check of the rewritten ``revert_merge`` already-reverted
        branch: reverting a merge that was already reverted returns
        ``success=True, already_reverted=True`` without aborting or escalating.
        """
        with TemporaryDirectory() as td:
            repo = Path(td) / "repo"
            repo.mkdir()
            wt = RealGitWorktree(repo)
            branch = wt.feature_branch("feat-r", {"r.txt": "R\n"})
            r_sha = wt.merge_no_ff(branch)

            # Pre-revert the merge (as merge_feature's inline revert would).
            _git("revert", "-m", "1", "--no-edit", r_sha, cwd=repo)
            self.assertIsNone(wt.file_on_main("r.txt"))
            head_before = wt.head()

            result = revert_merge(r_sha, repo_path=repo, feature="feat-r")

            self.assertTrue(result.success)
            self.assertTrue(result.already_reverted)
            self.assertFalse(result.aborted)
            # No new commit, no half-applied revert, clean tree.
            self.assertEqual(wt.head(), head_before)
            self.assertFalse(wt.revert_in_progress())
            self.assertTrue(wt.working_tree_clean())


if __name__ == "__main__":
    unittest.main()
