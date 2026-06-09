"""Real-git harness coverage for R3 (SHA-anchored revert on non-APPROVED review).

This module builds a real git repository (not a mock of ``subprocess.run``) so
the rollback's effect on the integration branch's *tree* is observable — the
spec's R3b/R3c acceptance explicitly rules out mock-only tree assertions.

It exercises two properties the dead, HEAD-anchored ``revert_merge`` could not
satisfy:

(b) ``test_deferred_review_reverts_feature_merge_with_intervening_merge`` —
    after a deferred review, the integration branch's tree no longer contains
    the feature's changes AND a revert commit exists. Crucially it **stacks an
    unrelated intervening merge on top of the target feature's merge before
    reverting**, so a ``git revert -m 1 HEAD`` would revert the wrong (latest)
    merge and leave the feature's code in place. This is what discriminates the
    SHA-anchored fix from the dead HEAD-anchored code.

(c) ``test_revert_conflict_aborts_and_escalates_blocking_deferral`` — a later
    commit touching the same lines makes the revert conflict; the harness
    asserts ``git revert --abort`` ran (no half-applied revert / clean tree)
    AND a ``SEVERITY_BLOCKING`` deferral was escalated.

The ``_git`` helper follows the established subprocess pattern in
``tests/test_integration_branch.py`` / ``tests/test_git_sync_rebase.py``
(repeatable identity via ``GIT_*`` env, gpgsign disabled).
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, MagicMock, patch

from cortex_command.overnight.deferral import SEVERITY_BLOCKING
from cortex_command.overnight.outcome_router import OutcomeContext, apply_feature_result
from cortex_command.overnight.report import ReportData, render_deferred_questions
from cortex_command.overnight.state import OvernightFeatureStatus, OvernightState
from cortex_command.overnight.types import CircuitBreakerState, FeatureResult
from cortex_command.pipeline.merge import revert_merge


# ---------------------------------------------------------------------------
# Real-git harness
# ---------------------------------------------------------------------------


def _git(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    """Run git with a repeatable identity inside a fixture repo."""
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
        "GIT_CONFIG_COUNT": "2",
        "GIT_CONFIG_KEY_0": "commit.gpgsign",
        "GIT_CONFIG_VALUE_0": "false",
        "GIT_CONFIG_KEY_1": "tag.gpgsign",
        "GIT_CONFIG_VALUE_1": "false",
    }
    env.pop("GIT_DIR", None)
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=check,
        capture_output=True,
        text=True,
        env=env,
    )


class RealGitWorktree:
    """A throwaway git repo with helpers for building real merges and reverts.

    Supports the operations R3's real-git acceptance needs: creating real
    ``--no-ff`` merges of feature branches into ``main``, stacking an unrelated
    intervening merge on top of a target merge, reverting by SHA, and
    inspecting branch-tree state (file presence/content, working-tree
    cleanliness, revert-commit existence).
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        _git("init", "-b", "main", ".", cwd=root)
        # Disable inherited git hooks (the repo's commit-msg validator would
        # reject the auto-generated ``Revert "..."`` message produced by the
        # in-code ``revert_merge`` subprocess, which runs git WITHOUT the
        # GIT_* identity env this harness sets). Persisting it in the repo
        # config makes every git invocation skip hooks, including the
        # production code path under test.
        _git("config", "core.hooksPath", "/dev/null", cwd=root)
        # Disable commit signing in the repo config so the in-code
        # ``revert_merge`` subprocess (which does not carry this harness's
        # GIT_CONFIG gpgsign-disabling env) does not try to GPG-sign the
        # revert commit and fail under a globally-enabled commit.gpgsign.
        _git("config", "commit.gpgsign", "false", cwd=root)
        _git("config", "tag.gpgsign", "false", cwd=root)
        _git("config", "user.name", "Test", cwd=root)
        _git("config", "user.email", "test@example.com", cwd=root)
        (root / "README.md").write_text("base\n")
        _git("add", "README.md", cwd=root)
        _git("commit", "-m", "Initial commit", cwd=root)

    # --- construction helpers ---

    def feature_branch(self, name: str, files: dict[str, str]) -> str:
        """Create a ``pipeline/{name}`` branch off main that writes *files*.

        Returns the fully-qualified branch name. Leaves the repo on ``main``.
        """
        branch = f"pipeline/{name}"
        _git("checkout", "-b", branch, "main", cwd=self.root)
        for rel, content in files.items():
            (self.root / rel).write_text(content)
            _git("add", rel, cwd=self.root)
        _git("commit", "-m", f"{name}: changes", cwd=self.root)
        _git("checkout", "main", cwd=self.root)
        return branch

    def merge_no_ff(self, branch: str) -> str:
        """``git merge --no-ff <branch>`` into main; return the merge SHA."""
        _git("checkout", "main", cwd=self.root)
        _git("merge", "--no-ff", branch, "-m", f"Merge {branch} into main", cwd=self.root)
        return self.head()

    def append_commit(self, rel: str, content: str, message: str) -> str:
        """Append *content* to *rel* on main and commit; return its SHA."""
        _git("checkout", "main", cwd=self.root)
        path = self.root / rel
        existing = path.read_text() if path.exists() else ""
        path.write_text(existing + content)
        _git("add", rel, cwd=self.root)
        _git("commit", "-m", message, cwd=self.root)
        return self.head()

    # --- inspection helpers ---

    def head(self) -> str:
        return _git("rev-parse", "HEAD", cwd=self.root).stdout.strip()

    def file_on_main(self, rel: str) -> str | None:
        """Return the content of *rel* as it exists on main's tree, or None."""
        res = _git("show", f"main:{rel}", cwd=self.root, check=False)
        return res.stdout if res.returncode == 0 else None

    def working_tree_clean(self) -> bool:
        return _git("status", "--porcelain", cwd=self.root).stdout.strip() == ""

    def revert_in_progress(self) -> bool:
        return (self.root / ".git" / "REVERT_HEAD").exists()

    def log_subjects(self, n: int = 20) -> list[str]:
        out = _git("log", f"-{n}", "--format=%s", cwd=self.root).stdout
        return [ln for ln in out.splitlines() if ln]


# ---------------------------------------------------------------------------
# OutcomeContext factory wired to a real integration repo
# ---------------------------------------------------------------------------


def _make_real_ctx(repo: Path, session_dir: Path) -> OutcomeContext:
    """Build an OutcomeContext whose home integration worktree is *repo*.

    ``repo_path_map[name] = None`` + ``home_worktree_path = repo`` makes
    ``_merge_target_repo_path`` resolve to the real fixture repo, so the live
    ``revert_merge`` call in ``apply_feature_result`` runs against real git.
    """
    batch_result = MagicMock()
    batch_result.features_merged = []
    batch_result.features_paused = []
    batch_result.features_deferred = []
    batch_result.features_failed = []
    batch_result.key_files_changed = {}
    batch_result.circuit_breaker_fired = False
    batch_result.global_abort_signal = False
    batch_result.abort_reason = None

    config = MagicMock()
    config.batch_id = 1
    config.base_branch = "main"
    config.test_command = None
    config.session_dir = session_dir
    config.overnight_events_path = session_dir / "overnight.log"
    config.pipeline_events_path = session_dir / "pipeline.log"
    config.overnight_state_path = session_dir / "state.json"

    return OutcomeContext(
        batch_result=batch_result,
        lock=asyncio.Lock(),
        cb_state=CircuitBreakerState(consecutive_pauses=0),
        recovery_attempts_map={},
        worktree_paths={},
        worktree_branches={},
        repo_path_map={},
        integration_worktrees={},
        integration_branches={},
        session_id="s-real",
        backlog_ids={},
        feature_names=["feat-x"],
        config=config,
        home_worktree_path=repo,
    )


class TestRevertMergeRealGit(unittest.IsolatedAsyncioTestCase):
    async def test_deferred_review_reverts_feature_merge_with_intervening_merge(self):
        """R3b + intervening-merge discriminator.

        Merge feature X, stack an UNRELATED feature Y merge on top, then drive
        the deferred-review path for X. The SHA-anchored revert must undo X's
        changes (its file is gone from main's tree) while Y's changes survive,
        and a revert commit must exist. A HEAD-anchored revert would revert Y's
        merge instead and leave X's code in place — failing this test.
        """
        with TemporaryDirectory() as td:
            repo = Path(td) / "repo"
            repo.mkdir()
            session_dir = Path(td) / "session"
            session_dir.mkdir()
            wt = RealGitWorktree(repo)

            # Feature X — the one that will be deferred + reverted.
            x_branch = wt.feature_branch("feat-x", {"x_feature.txt": "X content\n"})
            x_merge_sha = wt.merge_no_ff(x_branch)

            # Unrelated intervening feature Y, merged ON TOP of X's merge.
            y_branch = wt.feature_branch("feat-y", {"y_feature.txt": "Y content\n"})
            wt.merge_no_ff(y_branch)

            # Sanity: both features present, HEAD is Y's merge (not X's).
            self.assertEqual(wt.file_on_main("x_feature.txt"), "X content\n")
            self.assertEqual(wt.file_on_main("y_feature.txt"), "Y content\n")
            self.assertNotEqual(wt.head(), x_merge_sha)

            ctx = _make_real_ctx(repo, session_dir)
            ctx.worktree_branches["feat-x"] = x_branch

            merge_result = MagicMock(
                success=True, error=None, conflict=False, test_result=None,
                merge_sha=x_merge_sha,
            )
            review_result = MagicMock(
                deferred=True, verdict="REJECTED", cycle=1, merge_sha=None,
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

            # X's changes are reverted from the integration branch's tree...
            self.assertIsNone(
                wt.file_on_main("x_feature.txt"),
                "feature X's file should be gone after the SHA-anchored revert; "
                "a HEAD-anchored revert would have left it in place",
            )
            # ...while the unrelated intervening feature Y survives.
            self.assertEqual(wt.file_on_main("y_feature.txt"), "Y content\n")
            # A revert commit exists.
            self.assertTrue(
                any(s.startswith('Revert "Merge') for s in wt.log_subjects()),
                f"expected a revert commit; log subjects: {wt.log_subjects()}",
            )
            # Tree is clean (no half-applied state) and the feature was deferred.
            self.assertTrue(wt.working_tree_clean())
            self.assertFalse(wt.revert_in_progress())
            self.assertIn(
                "feat-x", [d["name"] for d in ctx.batch_result.features_deferred]
            )

    async def test_revert_conflict_aborts_and_escalates_blocking_deferral(self):
        """R3c: a revert conflict triggers ``git revert --abort`` (no
        half-applied revert remains) AND escalates a SEVERITY_BLOCKING deferral.

        A later commit rewrites the same lines feature X added, so reverting
        X's merge conflicts.
        """
        with TemporaryDirectory() as td:
            repo = Path(td) / "repo"
            repo.mkdir()
            session_dir = Path(td) / "session"
            session_dir.mkdir()
            wt = RealGitWorktree(repo)

            # Feature X writes shared.txt; merge it.
            x_branch = wt.feature_branch("feat-x", {"shared.txt": "line from X\n"})
            x_merge_sha = wt.merge_no_ff(x_branch)

            # A later commit overwrites the SAME line so reverting X conflicts.
            _git("checkout", "main", cwd=repo)
            (repo / "shared.txt").write_text("line rewritten by a dependent\n")
            _git("add", "shared.txt", cwd=repo)
            _git("commit", "-m", "Dependent rewrites shared.txt", cwd=repo)

            head_before = wt.head()

            ctx = _make_real_ctx(repo, session_dir)
            ctx.worktree_branches["feat-x"] = x_branch

            merge_result = MagicMock(
                success=True, error=None, conflict=False, test_result=None,
                merge_sha=x_merge_sha,
            )
            review_result = MagicMock(
                deferred=True, verdict="REJECTED", cycle=1, merge_sha=None,
            )

            captured_deferrals: list = []

            def _capture_write_deferral(deferral, deferred_dir=None):
                captured_deferrals.append(deferral)

            with (
                patch(
                    "cortex_command.overnight.outcome_router._get_changed_files",
                    return_value=["shared.txt"],
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
                    "cortex_command.overnight.outcome_router._next_escalation_n",
                    return_value=1,
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

            # The revert was aborted: no half-applied revert, tree clean, and
            # HEAD is unchanged (the merge genuinely remains on the branch).
            self.assertFalse(
                wt.revert_in_progress(),
                "git revert --abort should have cleared the half-applied revert",
            )
            self.assertTrue(wt.working_tree_clean())
            self.assertEqual(wt.head(), head_before)
            # X's merge still present (the R-edge: code genuinely remains).
            self.assertEqual(wt.file_on_main("shared.txt"), "line rewritten by a dependent\n")

            # A SEVERITY_BLOCKING deferral was escalated.
            self.assertEqual(len(captured_deferrals), 1)
            self.assertEqual(captured_deferrals[0].severity, SEVERITY_BLOCKING)

    async def test_aborted_revert_surface_names_dependent_and_says_do_not_rerun(self):
        """R6d: a feature whose revert ABORTS on a real conflict produces a
        blocking deferral whose RENDERED morning-report surface (a) carries the
        legacy 'do NOT re-run' annotation (accurate here — the merge genuinely
        remains) and (b) names the dependent feature Y that references the
        reverted code. Drives the conflict via the real-git harness.
        """
        with TemporaryDirectory() as td:
            repo = Path(td) / "repo"
            repo.mkdir()
            session_dir = Path(td) / "session"
            session_dir.mkdir()
            wt = RealGitWorktree(repo)

            # Feature X writes shared.txt; merge it.
            x_branch = wt.feature_branch("feat-x", {"shared.txt": "line from X\n"})
            x_merge_sha = wt.merge_no_ff(x_branch)

            # Dependent feature Y rewrites the SAME line so reverting X conflicts.
            _git("checkout", "main", cwd=repo)
            (repo / "shared.txt").write_text("line rewritten by feat-y\n")
            _git("add", "shared.txt", cwd=repo)
            _git("commit", "-m", "feat-y rewrites shared.txt", cwd=repo)

            ctx = _make_real_ctx(repo, session_dir)
            ctx.worktree_branches["feat-x"] = x_branch
            # Y is an in-batch feature touching the same file → identified as
            # the dependent by the file-set intersection.
            ctx.batch_result.key_files_changed["feat-y"] = ["shared.txt"]

            merge_result = MagicMock(
                success=True, error=None, conflict=False, test_result=None,
                merge_sha=x_merge_sha,
            )
            review_result = MagicMock(
                deferred=True, verdict="REJECTED", cycle=1, merge_sha=None,
            )

            captured_deferrals: list = []

            def _capture_write_deferral(deferral, deferred_dir=None):
                captured_deferrals.append(deferral)

            with (
                patch(
                    "cortex_command.overnight.outcome_router._get_changed_files",
                    return_value=["shared.txt"],
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
                    "cortex_command.overnight.outcome_router._next_escalation_n",
                    return_value=1,
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

            # A blocking conflict deferral was escalated and names Y.
            self.assertEqual(len(captured_deferrals), 1)
            dq = captured_deferrals[0]
            self.assertEqual(dq.severity, SEVERITY_BLOCKING)
            self.assertIn("feat-y", dq.context)

            # Render the deferral through the report: the surface must NOT be
            # reconciled (the revert aborted → no merge_reverted=True signal),
            # so it retains the legacy "do NOT re-run" annotation.
            state = OvernightState(session_id="s-real")
            state.features["feat-x"] = OvernightFeatureStatus(status="deferred")
            data = ReportData()
            data.state = state
            # feature_merged present (the merge landed) + a feature_deferred with
            # merge_reverted False (the abort), as the live router would emit.
            data.events = [
                {"event": "feature_merged", "feature": "feat-x"},
                {
                    "event": "feature_deferred",
                    "feature": "feat-x",
                    "details": {"review_verdict": "REJECTED", "merge_reverted": False},
                },
            ]
            data.deferrals = [dq]

            surface = render_deferred_questions(data)
            self.assertIn("do NOT re-run", surface)
            self.assertIn("on the integration branch", surface)
            # The dependent feature Y is named in the rendered surface (it
            # appears in the deferral question text the renderer echoes).
            self.assertIn("feat-y", surface)

    def test_revert_merge_unit_aborts_on_conflict(self):
        """Direct unit check of the rewritten ``revert_merge`` abort branch over
        a real conflicting revert (no router involvement)."""
        with TemporaryDirectory() as td:
            repo = Path(td) / "repo"
            repo.mkdir()
            wt = RealGitWorktree(repo)
            branch = wt.feature_branch("feat-z", {"shared.txt": "from Z\n"})
            z_sha = wt.merge_no_ff(branch)
            # Rewrite the same line so the revert conflicts.
            (repo / "shared.txt").write_text("rewritten\n")
            _git("add", "shared.txt", cwd=repo)
            _git("commit", "-m", "rewrite", cwd=repo)

            result = revert_merge(z_sha, repo_path=repo, feature="feat-z")
            self.assertFalse(result.success)
            self.assertTrue(result.aborted)
            self.assertFalse(wt.revert_in_progress())
            self.assertTrue(wt.working_tree_clean())

    def test_revert_merge_unit_succeeds_clean(self):
        """Direct unit check of the success branch: a clean SHA-anchored revert
        removes the feature's file and leaves a revert commit."""
        with TemporaryDirectory() as td:
            repo = Path(td) / "repo"
            repo.mkdir()
            wt = RealGitWorktree(repo)
            branch = wt.feature_branch("feat-w", {"w.txt": "W\n"})
            w_sha = wt.merge_no_ff(branch)
            # Intervening unrelated merge on top.
            other = wt.feature_branch("feat-o", {"o.txt": "O\n"})
            wt.merge_no_ff(other)

            result = revert_merge(w_sha, repo_path=repo, feature="feat-w")
            self.assertTrue(result.success)
            self.assertFalse(result.aborted)
            self.assertIsNone(wt.file_on_main("w.txt"))
            self.assertEqual(wt.file_on_main("o.txt"), "O\n")


if __name__ == "__main__":
    unittest.main()
