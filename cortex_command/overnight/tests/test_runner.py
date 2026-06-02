"""Unit tests for runner.py plan-commit helper (Task 9 / spec R10).

Covers ``_commit_round_plans_in_worktree`` and its worktree resolver
``_resolve_feature_integration_worktree``:

  TestPlanCommitWorktreeResolution — home-only session: the helper resolves
    the integration worktree from ``state.worktree_path`` and runs ``git``
    with ``cwd`` = that worktree (not the home repo).
  TestPlanCommitStagesPlanPaths — the staged ``git add`` argv names the
    round's ``cortex/lifecycle/{feature}/plan.md`` paths.
  TestPlanCommitLandsOnIntegrationBranch — integration-level confirmation
    (real git repo + worktree) that the commit lands on
    ``overnight/{session_id}`` and not ``main``, and the home-tree copy is
    left in place.
  TestPlanCommitWorktreeAbsent — absent/torn-down worktree fails safe
    (no crash, no git commit).
"""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cortex_command.overnight import runner
from cortex_command.overnight.state import (
    OvernightFeatureStatus,
    OvernightState,
)


def _make_home_only_state(
    *,
    worktree_path: str,
    features: dict[str, OvernightFeatureStatus],
    session_id: str = "overnight-test-0000",
) -> OvernightState:
    """A home-only session: worktree_path set, integration_worktrees empty."""
    return OvernightState(
        session_id=session_id,
        plan_ref="cortex/lifecycle/overnight-plan.md",
        phase="executing",
        features=features,
        worktree_path=worktree_path,
        integration_worktrees={},
    )


def _write_home_plan(home: Path, feature: str, body: str = "# Plan\n") -> Path:
    """Write a home-tree plan.md for *feature* and return its path."""
    plan = home / "cortex" / "lifecycle" / feature / "plan.md"
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text(body)
    return plan


class TestPlanCommitWorktreeResolution(unittest.TestCase):
    """Home-only session resolves the worktree from state.worktree_path."""

    def test_plan_commit_resolver_picks_worktree_path_for_home_feature(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            wt = Path(td) / "worktree"
            wt.mkdir()
            state = _make_home_only_state(
                worktree_path=str(wt),
                features={"feat-a": OvernightFeatureStatus(status="pending")},
            )
            resolved = runner._resolve_feature_integration_worktree(
                state, state.features["feat-a"]
            )
            self.assertEqual(resolved, wt)

    def test_plan_commit_resolver_picks_cross_repo_integration_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cross_repo = Path(td) / "other-repo"
            cross_repo.mkdir()
            cross_wt = Path(td) / "cross-worktree"
            cross_wt.mkdir()
            repo_key = str(cross_repo.expanduser().resolve())
            state = OvernightState(
                session_id="overnight-test-0000",
                plan_ref="cortex/lifecycle/overnight-plan.md",
                phase="executing",
                features={
                    "feat-x": OvernightFeatureStatus(
                        status="pending", repo_path=str(cross_repo)
                    )
                },
                worktree_path=str(Path(td) / "home-worktree"),
                integration_worktrees={repo_key: str(cross_wt)},
            )
            resolved = runner._resolve_feature_integration_worktree(
                state, state.features["feat-x"]
            )
            self.assertEqual(resolved, cross_wt)

    def test_plan_commit_runs_git_with_cwd_equal_to_worktree(self) -> None:
        """For a home-only session the git commands run in state.worktree_path."""
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "home"
            home.mkdir()
            wt = Path(td) / "worktree"
            wt.mkdir()
            _write_home_plan(home, "feat-a")
            state = _make_home_only_state(
                worktree_path=str(wt),
                features={"feat-a": OvernightFeatureStatus(status="pending")},
            )

            captured: list[dict] = []

            def _fake_run(argv, **kwargs):
                captured.append({"argv": argv, "cwd": kwargs.get("cwd")})
                # Make "git diff --cached --quiet" report staged changes so
                # the commit branch is exercised.
                rc = 1 if argv[:3] == ["git", "diff", "--cached"] else 0
                return subprocess.CompletedProcess(argv, rc, stdout="", stderr="")

            with mock.patch.object(runner.subprocess, "run", side_effect=_fake_run):
                runner._commit_round_plans_in_worktree(
                    state=state,
                    home_repo_path=home,
                    session_id="overnight-test-0000",
                    events_path=Path(td) / "events.log",
                )

            self.assertTrue(captured, "expected git subprocess calls")
            # Every git invocation runs with cwd == the resolved worktree,
            # not the home repo.
            for call in captured:
                self.assertEqual(call["cwd"], str(wt))
            self.assertNotIn(str(home), [c["cwd"] for c in captured])


class TestPlanCommitStagesPlanPaths(unittest.TestCase):
    """git add argv names the round's plan.md paths, not just any cwd."""

    def test_plan_commit_git_add_names_feature_plan_paths(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "home"
            home.mkdir()
            wt = Path(td) / "worktree"
            wt.mkdir()
            _write_home_plan(home, "feat-a")
            _write_home_plan(home, "feat-b")
            state = _make_home_only_state(
                worktree_path=str(wt),
                features={
                    "feat-a": OvernightFeatureStatus(status="pending"),
                    "feat-b": OvernightFeatureStatus(status="pending"),
                },
            )

            add_argvs: list[list[str]] = []

            def _fake_run(argv, **kwargs):
                if argv[:2] == ["git", "add"]:
                    add_argvs.append(list(argv))
                rc = 1 if argv[:3] == ["git", "diff", "--cached"] else 0
                return subprocess.CompletedProcess(argv, rc, stdout="", stderr="")

            with mock.patch.object(runner.subprocess, "run", side_effect=_fake_run):
                runner._commit_round_plans_in_worktree(
                    state=state,
                    home_repo_path=home,
                    session_id="overnight-test-0000",
                    events_path=Path(td) / "events.log",
                )

            self.assertTrue(add_argvs, "expected a git add invocation")
            staged = {p for argv in add_argvs for p in argv[2:]}
            self.assertIn("cortex/lifecycle/feat-a/plan.md", staged)
            self.assertIn("cortex/lifecycle/feat-b/plan.md", staged)


class TestPlanCommitLandsOnIntegrationBranch(unittest.TestCase):
    """Real git repo + worktree: commit lands on overnight/{id}, not main."""

    def _git(self, cwd: Path, *args: str) -> str:
        return subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def test_plan_commit_lands_on_integration_branch_home_copy_remains(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "home"
            home.mkdir()
            session_id = "overnight-test-0000"
            branch = f"overnight/{session_id}"

            # Initialize a real home repo on main with an initial commit.
            self._git(home, "init", "-q", "-b", "main")
            self._git(home, "config", "user.email", "t@example.com")
            self._git(home, "config", "user.name", "Test")
            self._git(home, "config", "commit.gpgsign", "false")
            (home / "README.md").write_text("seed\n")
            self._git(home, "add", "README.md")
            self._git(home, "commit", "-q", "-m", "seed")
            main_head_before = self._git(home, "rev-parse", "main")

            # Create the integration worktree on overnight/{session_id}.
            wt = Path(td) / "worktree"
            self._git(home, "worktree", "add", "-q", "-b", branch, str(wt))

            # Orchestrator wrote plan.md into the HOME tree (uncommitted).
            home_plan = _write_home_plan(home, "feat-a", "# Plan A\nbody\n")

            state = _make_home_only_state(
                worktree_path=str(wt),
                features={"feat-a": OvernightFeatureStatus(status="pending")},
                session_id=session_id,
            )

            runner._commit_round_plans_in_worktree(
                state=state,
                home_repo_path=home,
                session_id=session_id,
                events_path=Path(td) / "events.log",
            )

            # The commit landed on the worktree's checked-out branch...
            wt_branch = self._git(wt, "rev-parse", "--abbrev-ref", "HEAD")
            self.assertEqual(wt_branch, branch)
            wt_log = self._git(wt, "log", "-1", "--format=%s")
            self.assertIn(session_id, wt_log)
            # ...and the plan.md is tracked in the worktree branch.
            tracked = self._git(wt, "ls-files", "cortex/lifecycle/feat-a/plan.md")
            self.assertEqual(tracked, "cortex/lifecycle/feat-a/plan.md")

            # main was NOT advanced (no commit on home main).
            main_head_after = self._git(home, "rev-parse", "main")
            self.assertEqual(main_head_before, main_head_after)

            # The home-tree copy is left in place (Task 7 dispatch reads it).
            self.assertTrue(home_plan.is_file())


class TestPlanCommitWorktreeAbsent(unittest.TestCase):
    """Absent/torn-down worktree fails safe — no crash, no git commit."""

    def test_plan_commit_absent_integration_worktree_no_commit_no_crash(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "home"
            home.mkdir()
            _write_home_plan(home, "feat-a")
            missing_wt = Path(td) / "does-not-exist"
            state = _make_home_only_state(
                worktree_path=str(missing_wt),
                features={"feat-a": OvernightFeatureStatus(status="pending")},
            )

            calls: list[list[str]] = []

            def _fake_run(argv, **kwargs):
                calls.append(list(argv))
                return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

            with mock.patch.object(runner.subprocess, "run", side_effect=_fake_run):
                # Must not raise.
                runner._commit_round_plans_in_worktree(
                    state=state,
                    home_repo_path=home,
                    session_id="overnight-test-0000",
                    events_path=Path(td) / "events.log",
                )

            # No git command ran against the missing worktree.
            self.assertEqual(calls, [])

    def test_plan_commit_none_integration_worktree_for_home_feature_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            home = Path(td) / "home"
            home.mkdir()
            _write_home_plan(home, "feat-a")
            # Home-only session with no worktree_path recorded at all.
            state = OvernightState(
                session_id="overnight-test-0000",
                plan_ref="cortex/lifecycle/overnight-plan.md",
                phase="executing",
                features={"feat-a": OvernightFeatureStatus(status="pending")},
                worktree_path=None,
                integration_worktrees={},
            )
            resolved = runner._resolve_feature_integration_worktree(
                state, state.features["feat-a"]
            )
            self.assertIsNone(resolved)


if __name__ == "__main__":
    unittest.main()
