"""Unit tests for initialize_overnight_state() and validate_target_repos() in plan.py.

Covers:
  TestInitializeOvernightState — worktree creation, worktree_path field,
    stale-worktree collision handling, and subprocess call patterns.
  TestValidateTargetRepos — repo path validation, tilde expansion, deduplication,
    and error handling.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

from cortex_command.overnight.backlog import BacklogItem, Batch, SelectionResult
from cortex_command.overnight.plan import initialize_overnight_state, validate_target_repos


def _make_selection(*titles: str) -> SelectionResult:
    """Build a minimal SelectionResult with one batch containing the given items."""
    items = [
        BacklogItem(id=i + 1, title=title, status="backlog", priority="medium")
        for i, title in enumerate(titles)
    ]
    batch = Batch(items=items, batch_context="test context", batch_id=1)
    return SelectionResult(batches=[batch], ineligible=[], summary="test")


class TestInitializeOvernightState(unittest.TestCase):
    """Tests for initialize_overnight_state() worktree integration."""

    def setUp(self):
        # Use a deterministic TMPDIR so worktree_path is predictable.
        self._tmpdir = tempfile.TemporaryDirectory()
        self._fake_tmpdir = self._tmpdir.name

    def tearDown(self):
        self._tmpdir.cleanup()

    def _run(self, selection: SelectionResult, plan_content: str | None = None):
        """Call initialize_overnight_state() with TMPDIR patched and subprocess mocked."""
        mock_run = MagicMock(return_value=MagicMock(returncode=0))
        env_patch = patch.dict(os.environ, {"TMPDIR": self._fake_tmpdir})
        subprocess_patch = patch("cortex_command.overnight.plan.subprocess.run", mock_run)
        with env_patch, subprocess_patch:
            state = initialize_overnight_state(selection, plan_content)
        return state, mock_run

    # ------------------------------------------------------------------
    # worktree_path field
    # ------------------------------------------------------------------

    def test_worktree_path_set_under_tmpdir(self):
        """Returned state has worktree_path under $TMPDIR/overnight-worktrees/{session_id}."""
        selection = _make_selection("Feature Alpha")
        state, _ = self._run(selection)

        self.assertIsNotNone(state.worktree_path)
        expected_prefix = str(Path(self._fake_tmpdir) / "overnight-worktrees")
        self.assertTrue(
            state.worktree_path.startswith(expected_prefix),
            f"worktree_path={state.worktree_path!r} should start with {expected_prefix!r}",
        )

    def test_worktree_path_ends_with_session_id(self):
        """worktree_path last component matches state.session_id."""
        selection = _make_selection("Feature Beta")
        state, _ = self._run(selection)

        self.assertIsNotNone(state.worktree_path)
        self.assertEqual(Path(state.worktree_path).name, state.session_id)

    def test_worktree_path_formula(self):
        """worktree_path equals str(Path(TMPDIR) / 'overnight-worktrees' / session_id)."""
        selection = _make_selection("Feature Gamma")
        state, _ = self._run(selection)

        expected = str(
            Path(self._fake_tmpdir) / "overnight-worktrees" / state.session_id
        )
        self.assertEqual(state.worktree_path, expected)

    # ------------------------------------------------------------------
    # subprocess call pattern — git worktree prune + git worktree add
    # ------------------------------------------------------------------

    def test_git_worktree_prune_called(self):
        """subprocess.run is called with ['git', 'worktree', 'prune']."""
        selection = _make_selection("Feature Delta")
        _, mock_run = self._run(selection)

        prune_call = call(
            ["git", "worktree", "prune", "--expire", "now"],
            cwd=Path.cwd().resolve(),
        )
        self.assertIn(prune_call, mock_run.call_args_list)

    def test_git_worktree_add_called_with_correct_args(self):
        """subprocess.run is called with ['git', 'worktree', 'add', <path>, '-b', <branch>]."""
        selection = _make_selection("Feature Epsilon")
        state, mock_run = self._run(selection)

        expected_worktree_add = call(
            [
                "git",
                "worktree",
                "add",
                state.worktree_path,
                "-b",
                f"overnight/{state.session_id}",
            ],
            cwd=Path.cwd().resolve(),
            check=True,
        )
        self.assertIn(expected_worktree_add, mock_run.call_args_list)

    def test_prune_called_before_add(self):
        """git worktree prune is called before git worktree add."""
        selection = _make_selection("Feature Zeta")
        _, mock_run = self._run(selection)

        call_list = mock_run.call_args_list
        cmds = [c.args[0] for c in call_list]

        prune_idx = next(
            (i for i, cmd in enumerate(cmds) if cmd[:3] == ["git", "worktree", "prune"]),
            None,
        )
        add_idx = next(
            (i for i, cmd in enumerate(cmds) if cmd[:3] == ["git", "worktree", "add"]),
            None,
        )
        self.assertIsNotNone(prune_idx, "git worktree prune not found in calls")
        self.assertIsNotNone(add_idx, "git worktree add not found in calls")
        self.assertLess(prune_idx, add_idx, "prune must be called before add")

    def test_git_checkout_b_not_called(self):
        """subprocess.run is never called with 'git checkout -b'."""
        selection = _make_selection("Feature Eta")
        _, mock_run = self._run(selection)

        for c in mock_run.call_args_list:
            cmd = c.args[0] if c.args else []
            self.assertNotEqual(
                cmd[:3],
                ["git", "checkout", "-b"],
                "git checkout -b must not be called",
            )

    # ------------------------------------------------------------------
    # Stale-worktree collision handling
    # ------------------------------------------------------------------

    def test_stale_worktree_directory_is_removed_before_add(self):
        """When worktree_path exists on disk, shutil.rmtree is called, then git worktree add."""
        selection = _make_selection("Feature Theta")

        mock_run = MagicMock(return_value=MagicMock(returncode=0))
        rmtree_mock = MagicMock()

        env_patch = patch.dict(os.environ, {"TMPDIR": self._fake_tmpdir})
        subprocess_patch = patch("cortex_command.overnight.plan.subprocess.run", mock_run)
        # Patch Path.exists to return True (simulate stale directory)
        exists_patch = patch("pathlib.Path.exists", return_value=True)
        rmtree_patch = patch("cortex_command.overnight.plan.shutil.rmtree", rmtree_mock)

        with env_patch, subprocess_patch, exists_patch, rmtree_patch:
            state = initialize_overnight_state(selection)

        # shutil.rmtree should have been called with the worktree path
        rmtree_mock.assert_called_once_with(Path(state.worktree_path), ignore_errors=True)

        # git worktree add should still be called after removal
        add_call_found = any(
            c.args[0][:3] == ["git", "worktree", "add"]
            for c in mock_run.call_args_list
            if c.args
        )
        self.assertTrue(add_call_found, "git worktree add must be called after stale cleanup")

    def test_stale_worktree_collision_succeeds(self):
        """initialize_overnight_state() succeeds (no exception) when worktree dir pre-exists."""
        selection = _make_selection("Feature Iota")

        mock_run = MagicMock(return_value=MagicMock(returncode=0))

        env_patch = patch.dict(os.environ, {"TMPDIR": self._fake_tmpdir})
        subprocess_patch = patch("cortex_command.overnight.plan.subprocess.run", mock_run)
        exists_patch = patch("pathlib.Path.exists", return_value=True)
        rmtree_patch = patch("cortex_command.overnight.plan.shutil.rmtree")

        with env_patch, subprocess_patch, exists_patch, rmtree_patch:
            # Must not raise
            state = initialize_overnight_state(selection)

        self.assertIsNotNone(state.worktree_path)

    def test_no_rmtree_when_directory_absent(self):
        """shutil.rmtree is NOT called when the worktree directory does not exist."""
        selection = _make_selection("Feature Kappa")

        mock_run = MagicMock(return_value=MagicMock(returncode=0))
        rmtree_mock = MagicMock()

        env_patch = patch.dict(os.environ, {"TMPDIR": self._fake_tmpdir})
        subprocess_patch = patch("cortex_command.overnight.plan.subprocess.run", mock_run)
        # Path.exists returns False — directory absent
        exists_patch = patch("pathlib.Path.exists", return_value=False)
        rmtree_patch = patch("cortex_command.overnight.plan.shutil.rmtree", rmtree_mock)

        with env_patch, subprocess_patch, exists_patch, rmtree_patch:
            initialize_overnight_state(selection)

        rmtree_mock.assert_not_called()

    # ------------------------------------------------------------------
    # State field coverage
    # ------------------------------------------------------------------

    def test_integration_branch_matches_session_id(self):
        """integration_branch is 'overnight/{session_id}'."""
        selection = _make_selection("Feature Lambda")
        state, _ = self._run(selection)

        self.assertEqual(state.integration_branch, f"overnight/{state.session_id}")

    def test_features_populated_from_selection(self):
        """All items from the selection appear in state.features."""
        selection = _make_selection("Alpha Feature", "Beta Feature")
        state, _ = self._run(selection)

        self.assertEqual(len(state.features), 2)
        for slug, fs in state.features.items():
            self.assertEqual(fs.status, "pending")

    def test_plan_hash_set_when_content_provided(self):
        """plan_hash is set when plan_content is provided."""
        import hashlib
        selection = _make_selection("Feature Mu")
        plan_content = "# Plan\n\nTask 1\n"
        state, _ = self._run(selection, plan_content=plan_content)

        expected = hashlib.sha256(plan_content.encode("utf-8")).hexdigest()
        self.assertEqual(state.plan_hash, expected)

    def test_plan_hash_none_when_content_absent(self):
        """plan_hash is None when plan_content is not provided."""
        selection = _make_selection("Feature Nu")
        state, _ = self._run(selection, plan_content=None)

        self.assertIsNone(state.plan_hash)

    def test_integration_branches_populated_for_home_repo(self):
        """integration_branches contains the current working directory root path mapped to integration_branch."""
        selection = _make_selection("Feature Omicron")
        state, _ = self._run(selection)

        # The repo root is computed as Path.cwd() from plan.py — the CWD when the test
        # runner is invoked from the home repo is the repository root.
        expected_root = str(Path.cwd().resolve())

        self.assertIn(expected_root, state.integration_branches)
        self.assertEqual(state.integration_branches[expected_root], state.integration_branch)

    def test_integration_branches_includes_cross_repo_target(self):
        """integration_branches contains a key for each unique cross-repo target."""
        selection = _make_selection_with_repos(["/path/to/wild-light"])
        state, _ = self._run(selection)

        expected_key = str(Path("/path/to/wild-light").expanduser().resolve())
        self.assertIn(expected_key, state.integration_branches)
        self.assertEqual(state.integration_branches[expected_key], state.integration_branch)

    def test_integration_branches_deduplicates(self):
        """Two items with the same repo: path produce exactly one entry in integration_branches."""
        selection = _make_selection_with_repos(["/path/to/wild-light", "/path/to/wild-light"])
        state, _ = self._run(selection)

        expected_key = str(Path("/path/to/wild-light").expanduser().resolve())
        # Count occurrences of the cross-repo key — dict keys are unique so just confirm presence
        cross_repo_entries = [k for k in state.integration_branches if k == expected_key]
        self.assertEqual(len(cross_repo_entries), 1)

    def test_integration_branches_key_uses_cwd(self):
        """integration_branches first key uses Path.cwd() — will pass after Task 2.

        Pre-Task 2: FAILS because plan.py uses Path(__file__) to find the
        project root rather than Path.cwd().
        Post-Task 2: PASSES once plan.py is changed to use Path.cwd().

        Wheel-install migration (Task 4): ``_resolve_user_project_root``
        rejects a CWD that lacks ``lifecycle/`` and ``backlog/``. Patching
        ``Path.cwd`` to a bare ``/tmp/fake-repo`` would now hit that
        rejection, so we materialize the fake-repo as a real tmp directory
        with ``lifecycle/`` for the duration of the test.
        """
        fake_repo = Path(self._fake_tmpdir) / "fake-repo"
        (fake_repo / "lifecycle").mkdir(parents=True)
        selection = _make_selection("Feature CWD")
        mock_run = MagicMock(return_value=MagicMock(returncode=0))
        cwd_patch = patch("pathlib.Path.cwd", return_value=fake_repo)
        subprocess_patch = patch("cortex_command.overnight.plan.subprocess.run", mock_run)
        env_patch = patch.dict(os.environ, {"TMPDIR": self._fake_tmpdir})
        with env_patch, subprocess_patch, cwd_patch:
            state = initialize_overnight_state(selection)

        self.assertEqual(next(iter(state.integration_branches)), str(fake_repo.resolve()))

    def test_integration_branches_home_repo_regression(self):
        """integration_branches first key matches Path.cwd().resolve() — regression guard.

        This test does NOT patch Path.cwd(), so it uses the actual project root
        CWD. It passes before Task 2 (where plan.py uses Path(__file__)) because
        when run from the home repo, Path(__file__).parent.parent.parent ==
        Path.cwd().resolve(). It continues to pass after Task 2 once plan.py
        switches to Path.cwd().
        """
        selection = _make_selection("Feature Regression")
        mock_run = MagicMock(return_value=MagicMock(returncode=0))
        subprocess_patch = patch("cortex_command.overnight.plan.subprocess.run", mock_run)
        env_patch = patch.dict(os.environ, {"TMPDIR": self._fake_tmpdir})
        with env_patch, subprocess_patch:
            state = initialize_overnight_state(selection)

        self.assertEqual(
            next(iter(state.integration_branches)),
            str(Path.cwd().resolve()),
        )

    # ------------------------------------------------------------------
    # Stale branch cleanup
    # ------------------------------------------------------------------

    def test_stale_branch_deleted_before_worktree_add(self):
        """When integration branch already exists, git branch -D is called before worktree add."""
        selection = _make_selection("Feature StaleBranch")

        call_log: list[list[str]] = []

        def tracking_run(cmd, **kwargs):
            call_log.append(cmd)
            mock = MagicMock()
            # show-ref returns 0 = branch exists
            if cmd[:3] == ["git", "show-ref", "--verify"]:
                mock.returncode = 0
                return mock
            # branch -D succeeds
            if cmd[:3] == ["git", "branch", "-D"]:
                mock.returncode = 0
                return mock
            # Everything else (prune, worktree add) succeeds
            mock.returncode = 0
            return mock

        env_patch = patch.dict(os.environ, {"TMPDIR": self._fake_tmpdir})
        subprocess_patch = patch("cortex_command.overnight.plan.subprocess.run", side_effect=tracking_run)

        with env_patch, subprocess_patch:
            state = initialize_overnight_state(selection)

        # Find indices of branch -D and worktree add
        branch_d_idx = next(
            (i for i, cmd in enumerate(call_log) if cmd[:3] == ["git", "branch", "-D"]),
            None,
        )
        add_idx = next(
            (i for i, cmd in enumerate(call_log) if cmd[:3] == ["git", "worktree", "add"]),
            None,
        )
        self.assertIsNotNone(branch_d_idx, "git branch -D not found in calls")
        self.assertIsNotNone(add_idx, "git worktree add not found in calls")
        self.assertLess(branch_d_idx, add_idx, "branch -D must be called before worktree add")

        # Verify the correct branch name was deleted
        branch_d_cmd = call_log[branch_d_idx]
        self.assertEqual(branch_d_cmd[3], f"overnight/{state.session_id}")

    def test_branch_delete_failure_raises_runtime_error(self):
        """When git branch -D fails, a RuntimeError is raised with an informative message."""
        selection = _make_selection("Feature BranchFail")

        def failing_run(cmd, **kwargs):
            mock = MagicMock()
            # show-ref returns 0 = branch exists
            if cmd[:3] == ["git", "show-ref", "--verify"]:
                mock.returncode = 0
                return mock
            # branch -D fails (check=True raises CalledProcessError)
            if cmd[:3] == ["git", "branch", "-D"]:
                raise subprocess.CalledProcessError(1, cmd)
            # Everything else succeeds
            mock.returncode = 0
            return mock

        env_patch = patch.dict(os.environ, {"TMPDIR": self._fake_tmpdir})
        subprocess_patch = patch("cortex_command.overnight.plan.subprocess.run", side_effect=failing_run)

        with env_patch, subprocess_patch:
            with self.assertRaises(RuntimeError) as ctx:
                initialize_overnight_state(selection)

        self.assertIn("could not be deleted", str(ctx.exception))

    # ------------------------------------------------------------------
    # Collision-avoidance suffix
    # ------------------------------------------------------------------

    def test_collision_suffix_appended_when_session_dir_exists(self):
        """When session dir already exists, session_id gets a -2 suffix."""
        selection = _make_selection("Feature Collision")

        def exists_side_effect(path):
            # The path is a Path object from session_dir(). Convert to string
            # to check whether it ends with the base session_id or the suffixed one.
            path_str = str(path)
            # Base session_id (no suffix) -> exists
            # Suffixed with -2 -> does not exist
            if path_str.endswith("-2"):
                return False
            return True

        mock_session_dir = MagicMock(side_effect=lambda sid, **kw: Path(f"/fake/lifecycle/sessions/{sid}"))
        mock_run = MagicMock(return_value=MagicMock(returncode=0))

        env_patch = patch.dict(os.environ, {"TMPDIR": self._fake_tmpdir})
        subprocess_patch = patch("cortex_command.overnight.plan.subprocess.run", mock_run)
        session_dir_patch = patch("cortex_command.overnight.plan.session_dir", mock_session_dir)
        exists_patch = patch("cortex_command.overnight.plan.os.path.exists", side_effect=exists_side_effect)

        with env_patch, subprocess_patch, session_dir_patch, exists_patch:
            state = initialize_overnight_state(selection)

        # suffix -1 would match "ends with -2" = False, so first suffix tried is -1
        # but -1 path does NOT end with -2 so exists returns True
        # suffix -2 path ends with -2 so exists returns False -> loop exits
        self.assertTrue(state.session_id.endswith("-2"), f"Expected session_id ending with -2, got {state.session_id!r}")
        self.assertEqual(state.integration_branch, f"overnight/{state.session_id}")

    # ------------------------------------------------------------------
    # Cross-repo worktree creation
    # ------------------------------------------------------------------

    def _cross_repo_side_effects(self, stale_branch_exists: bool = False):
        """Build a side_effect list for subprocess.run covering home-repo + 1 cross-repo target.

        Call sequence:
        1. Home-repo git worktree prune (no cwd)
        2. Home-repo git show-ref --verify (no cwd) -> returncode 1 (no stale branch)
        3. Home-repo git worktree add (no cwd, check=True) -> returncode 0
        4. Cross-repo git rev-parse origin/HEAD (cwd=repo, capture_output) -> "abc123\\n"
        5. Cross-repo git worktree prune (cwd=repo)
        6. Cross-repo git show-ref --verify (cwd=repo) -> returncode 0 or 1
        7a. If stale: git branch -D (cwd=repo, check=True) -> returncode 0
        7b. Cross-repo git worktree add (cwd=repo, check=True)
        """
        effects = []
        # 1. Home-repo prune
        effects.append(MagicMock(returncode=0))
        # 2. Home-repo show-ref -> no stale branch
        effects.append(MagicMock(returncode=1))
        # 3. Home-repo worktree add
        effects.append(MagicMock(returncode=0))
        # 4. cross-repo rev-parse -> stdout "abc123\n"
        rev_parse_mock = MagicMock(returncode=0)
        rev_parse_mock.stdout = b"abc123\n"
        effects.append(rev_parse_mock)
        # 5. cross-repo prune
        effects.append(MagicMock(returncode=0))
        # 6. cross-repo show-ref
        if stale_branch_exists:
            effects.append(MagicMock(returncode=0))
            # 7a. branch -D
            effects.append(MagicMock(returncode=0))
        else:
            effects.append(MagicMock(returncode=1))
        # 7b (or 7). cross-repo worktree add
        effects.append(MagicMock(returncode=0))
        return effects

    def test_cross_repo_worktree_add_called_with_cwd(self):
        """git worktree add for cross-repo is called with cwd=cross_repo_path and correct args."""
        selection = _make_cross_repo_selection("test-session")

        effects = self._cross_repo_side_effects()
        mock_run = MagicMock(side_effect=effects)

        cross_repo_path = str(Path("/tmp/test-wild-light").resolve())

        env_patch = patch.dict(os.environ, {"TMPDIR": self._fake_tmpdir})
        subprocess_patch = patch("cortex_command.overnight.plan.subprocess.run", mock_run)
        exists_patch = patch("cortex_command.overnight.plan.Path.exists", return_value=False)

        with env_patch, subprocess_patch, exists_patch:
            state = initialize_overnight_state(selection)

        # Find the cross-repo worktree add call (the one with cwd=cross_repo_path)
        cross_add_calls = [
            c for c in mock_run.call_args_list
            if c.args and c.args[0][:3] == ["git", "worktree", "add"]
            and c.kwargs.get("cwd") == cross_repo_path
        ]
        self.assertEqual(len(cross_add_calls), 1, "Expected exactly 1 cross-repo worktree add call")

        cmd = cross_add_calls[0].args[0]
        # Path should end with "{session_id}-test-wild-light" (name of the repo dir)
        worktree_arg = cmd[3]  # the path argument
        expected_suffix = f"{state.session_id}-test-wild-light"
        self.assertTrue(
            worktree_arg.endswith(expected_suffix),
            f"Worktree path {worktree_arg!r} should end with {expected_suffix!r}",
        )
        # Last arg should be the resolved base ref "abc123"
        self.assertEqual(cmd[-1], "abc123")

    def test_cross_repo_integration_worktrees_populated_on_state(self):
        """Returned OvernightState.integration_worktrees has key for cross-repo target."""
        selection = _make_cross_repo_selection("test-session")

        effects = self._cross_repo_side_effects()
        mock_run = MagicMock(side_effect=effects)

        cross_repo_path = str(Path("/tmp/test-wild-light").resolve())

        env_patch = patch.dict(os.environ, {"TMPDIR": self._fake_tmpdir})
        subprocess_patch = patch("cortex_command.overnight.plan.subprocess.run", mock_run)
        exists_patch = patch("cortex_command.overnight.plan.Path.exists", return_value=False)

        with env_patch, subprocess_patch, exists_patch:
            state = initialize_overnight_state(selection)

        self.assertIn(cross_repo_path, state.integration_worktrees)
        # Value should be the cross-repo worktree path under TMPDIR
        expected_suffix = f"{state.session_id}-test-wild-light"
        self.assertTrue(
            state.integration_worktrees[cross_repo_path].endswith(expected_suffix),
            f"integration_worktrees value {state.integration_worktrees[cross_repo_path]!r} "
            f"should end with {expected_suffix!r}",
        )

    def test_cross_repo_prune_called_with_cwd(self):
        """git worktree prune for cross-repo is called with cwd=cross_repo_path."""
        selection = _make_cross_repo_selection("test-session")

        effects = self._cross_repo_side_effects()
        mock_run = MagicMock(side_effect=effects)

        cross_repo_path = str(Path("/tmp/test-wild-light").resolve())

        env_patch = patch.dict(os.environ, {"TMPDIR": self._fake_tmpdir})
        subprocess_patch = patch("cortex_command.overnight.plan.subprocess.run", mock_run)
        exists_patch = patch("cortex_command.overnight.plan.Path.exists", return_value=False)

        with env_patch, subprocess_patch, exists_patch:
            initialize_overnight_state(selection)

        # Find cross-repo prune calls (the one with cwd kwarg)
        cross_prune_calls = [
            c for c in mock_run.call_args_list
            if c.args and c.args[0] == ["git", "worktree", "prune", "--expire", "now"]
            and c.kwargs.get("cwd") == cross_repo_path
        ]
        self.assertEqual(
            len(cross_prune_calls), 1,
            f"Expected 1 cross-repo prune call with cwd={cross_repo_path!r}, "
            f"found {len(cross_prune_calls)}",
        )

    def test_cross_repo_stale_branch_cleanup_with_cwd(self):
        """When show-ref finds stale branch in cross-repo, git branch -D is called with cwd."""
        selection = _make_cross_repo_selection("test-session")

        effects = self._cross_repo_side_effects(stale_branch_exists=True)
        mock_run = MagicMock(side_effect=effects)

        cross_repo_path = str(Path("/tmp/test-wild-light").resolve())

        env_patch = patch.dict(os.environ, {"TMPDIR": self._fake_tmpdir})
        subprocess_patch = patch("cortex_command.overnight.plan.subprocess.run", mock_run)
        exists_patch = patch("cortex_command.overnight.plan.Path.exists", return_value=False)

        with env_patch, subprocess_patch, exists_patch:
            initialize_overnight_state(selection)

        # Find branch -D calls with cwd=cross_repo_path
        branch_d_calls = [
            c for c in mock_run.call_args_list
            if c.args and c.args[0][:3] == ["git", "branch", "-D"]
            and c.kwargs.get("cwd") == cross_repo_path
        ]
        self.assertEqual(
            len(branch_d_calls), 1,
            f"Expected 1 cross-repo branch -D call with cwd={cross_repo_path!r}, "
            f"found {len(branch_d_calls)}",
        )

    # ------------------------------------------------------------------
    # Cross-repo failure handling and edge cases
    # ------------------------------------------------------------------

    def test_cross_repo_prune_failure_logs_warning_and_continues(self):
        """When git worktree prune raises for a cross-repo target, it logs a warning and continues."""
        selection = _make_cross_repo_selection("test-session")

        # Build side effects: same as _cross_repo_side_effects but with prune raising.
        effects = []
        # 1. Home-repo prune
        effects.append(MagicMock(returncode=0))
        # 2. Home-repo show-ref -> no stale branch
        effects.append(MagicMock(returncode=1))
        # 3. Home-repo worktree add
        effects.append(MagicMock(returncode=0))
        # 4. cross-repo rev-parse -> stdout "abc123\n"
        rev_parse_mock = MagicMock(returncode=0)
        rev_parse_mock.stdout = b"abc123\n"
        effects.append(rev_parse_mock)
        # 5. cross-repo prune -> RAISES CalledProcessError
        effects.append(subprocess.CalledProcessError(1, ["git", "worktree", "prune"]))
        # 6. cross-repo show-ref -> no stale branch
        effects.append(MagicMock(returncode=1))
        # 7. cross-repo worktree add
        effects.append(MagicMock(returncode=0))

        mock_run = MagicMock(side_effect=effects)
        cross_repo_path = str(Path("/tmp/test-wild-light").resolve())

        env_patch = patch.dict(os.environ, {"TMPDIR": self._fake_tmpdir})
        subprocess_patch = patch("cortex_command.overnight.plan.subprocess.run", mock_run)
        exists_patch = patch("cortex_command.overnight.plan.Path.exists", return_value=False)

        with env_patch, subprocess_patch, exists_patch:
            # Must not raise despite prune failure
            state = initialize_overnight_state(selection)

        # integration_worktrees should still be populated (worktree add succeeded)
        self.assertIn(cross_repo_path, state.integration_worktrees)

    def test_home_only_selection_produces_empty_integration_worktrees(self):
        """A selection with no cross-repo items produces empty integration_worktrees."""
        selection = _make_selection("Home Repo Only Feature")
        state, _ = self._run(selection)

        self.assertEqual(state.integration_worktrees, {})

    def test_cross_repo_base_ref_origin_head_fallback(self):
        """When git rev-parse origin/HEAD fails, git worktree add uses 'origin/main' as base ref."""
        selection = _make_cross_repo_selection("test-session")

        # Build side effects with rev-parse returning failure.
        effects = []
        # 1. Home-repo prune
        effects.append(MagicMock(returncode=0))
        # 2. Home-repo show-ref -> no stale branch
        effects.append(MagicMock(returncode=1))
        # 3. Home-repo worktree add
        effects.append(MagicMock(returncode=0))
        # 4. cross-repo rev-parse -> FAILS (returncode=1, empty stdout)
        rev_parse_mock = MagicMock(returncode=1)
        rev_parse_mock.stdout = b""
        rev_parse_mock.stderr = b""
        effects.append(rev_parse_mock)
        # 5. cross-repo prune
        effects.append(MagicMock(returncode=0))
        # 6. cross-repo show-ref -> no stale branch
        effects.append(MagicMock(returncode=1))
        # 7. cross-repo worktree add
        effects.append(MagicMock(returncode=0))

        mock_run = MagicMock(side_effect=effects)
        cross_repo_path = str(Path("/tmp/test-wild-light").resolve())

        env_patch = patch.dict(os.environ, {"TMPDIR": self._fake_tmpdir})
        subprocess_patch = patch("cortex_command.overnight.plan.subprocess.run", mock_run)
        exists_patch = patch("cortex_command.overnight.plan.Path.exists", return_value=False)

        with env_patch, subprocess_patch, exists_patch:
            state = initialize_overnight_state(selection)

        # Find the cross-repo worktree add call (the one with cwd=cross_repo_path)
        cross_add_calls = [
            c for c in mock_run.call_args_list
            if c.args and c.args[0][:3] == ["git", "worktree", "add"]
            and c.kwargs.get("cwd") == cross_repo_path
        ]
        self.assertEqual(len(cross_add_calls), 1, "Expected exactly 1 cross-repo worktree add call")

        # Last positional arg should be "origin/main" (the fallback)
        cmd = cross_add_calls[0].args[0]
        self.assertEqual(cmd[-1], "origin/main")

    def test_no_pointer_file_created(self):
        """No lifecycle/.overnight-worktree pointer file is created."""
        selection = _make_selection("Feature Xi")

        mock_run = MagicMock(return_value=MagicMock(returncode=0))
        env_patch = patch.dict(os.environ, {"TMPDIR": self._fake_tmpdir})
        subprocess_patch = patch("cortex_command.overnight.plan.subprocess.run", mock_run)

        # Patch open/write to detect any pointer file writes
        written_paths: list[str] = []
        real_open = open

        def tracking_open(path, *args, **kwargs):
            written_paths.append(str(path))
            return real_open(path, *args, **kwargs)

        with env_patch, subprocess_patch:
            with patch("builtins.open", side_effect=tracking_open):
                initialize_overnight_state(selection)

        overnight_worktree_writes = [
            p for p in written_paths if ".overnight-worktree" in p
        ]
        self.assertEqual(
            overnight_worktree_writes,
            [],
            f"No pointer file should be written; found: {overnight_worktree_writes}",
        )


def _make_selection_with_repos(repos: list[str | None]) -> SelectionResult:
    """Build a SelectionResult with one Batch containing BacklogItems with given repo values."""
    items = [
        BacklogItem(id=i + 1, title=f"Item {i + 1}", status="backlog", priority="medium", repo=repo)
        for i, repo in enumerate(repos)
    ]
    batch = Batch(items=items, batch_context="test context", batch_id=1)
    return SelectionResult(batches=[batch], ineligible=[], summary="test")


def _make_cross_repo_selection(session_id: str) -> SelectionResult:
    """Build a SelectionResult with one item targeting a cross-repo path.

    The item has repo="/tmp/test-wild-light" and a lifecycle_slug so the
    feature slug is deterministic (avoids depending on slugify internals).
    """
    items = [
        BacklogItem(
            id=1,
            title="Cross Repo Feature",
            status="backlog",
            priority="medium",
            repo="/tmp/test-wild-light",
            lifecycle_slug="cross-repo-feature",
        ),
    ]
    batch = Batch(items=items, batch_context="test context", batch_id=1)
    return SelectionResult(batches=[batch], ineligible=[], summary="test")


class TestValidateTargetRepos(unittest.TestCase):
    """Tests for validate_target_repos() repo validation."""

    def test_no_repo_fields_returns_empty(self):
        """Returns empty list when no items have a repo: field."""
        selection = _make_selection_with_repos([None, None])
        result = validate_target_repos(selection)
        self.assertEqual(result, [])

    def test_all_valid_repos_returns_empty(self):
        """Returns empty list when all repo paths are valid git repos."""
        selection = _make_selection_with_repos(["/some/repo", "/other/repo"])
        mock_run = MagicMock(return_value=MagicMock(returncode=0))
        with patch("cortex_command.overnight.plan.subprocess.run", mock_run):
            result = validate_target_repos(selection)
        self.assertEqual(result, [])

    def test_one_invalid_path_returns_that_path(self):
        """Returns the raw repo string for a path that fails git validation."""
        selection = _make_selection_with_repos(["/not/a/repo"])
        mock_run = MagicMock(return_value=MagicMock(returncode=1))
        with patch("cortex_command.overnight.plan.subprocess.run", mock_run):
            result = validate_target_repos(selection)
        self.assertEqual(result, ["/not/a/repo"])

    def test_multiple_invalid_paths_returns_all(self):
        """Returns all raw repo strings that fail git validation."""
        selection = _make_selection_with_repos(["/bad/repo/one", "/bad/repo/two"])
        mock_run = MagicMock(return_value=MagicMock(returncode=1))
        with patch("cortex_command.overnight.plan.subprocess.run", mock_run):
            result = validate_target_repos(selection)
        self.assertEqual(sorted(result), sorted(["/bad/repo/one", "/bad/repo/two"]))

    def test_tilde_expansion_used_as_cwd(self):
        """subprocess.run is called with the tilde-expanded path as cwd, not the raw value."""
        selection = _make_selection_with_repos(["~/myrepo"])
        mock_run = MagicMock(return_value=MagicMock(returncode=0))
        with patch("cortex_command.overnight.plan.subprocess.run", mock_run):
            validate_target_repos(selection)
        expected_cwd = os.path.expanduser("~/myrepo")
        actual_cwd = mock_run.call_args_list[0].kwargs.get("cwd") or mock_run.call_args_list[0][1].get("cwd")
        self.assertEqual(actual_cwd, expected_cwd)

    def test_duplicate_repo_values_subprocess_called_once(self):
        """Two items with the same repo value result in subprocess.run being called only once."""
        selection = _make_selection_with_repos(["/shared/repo", "/shared/repo"])
        mock_run = MagicMock(return_value=MagicMock(returncode=0))
        with patch("cortex_command.overnight.plan.subprocess.run", mock_run):
            validate_target_repos(selection)
        self.assertEqual(mock_run.call_count, 1)

    def test_file_not_found_treated_as_failure(self):
        """FileNotFoundError from subprocess.run is treated as validation failure."""
        selection = _make_selection_with_repos(["/nonexistent/path"])
        mock_run = MagicMock(side_effect=FileNotFoundError)
        with patch("cortex_command.overnight.plan.subprocess.run", mock_run):
            result = validate_target_repos(selection)
        self.assertEqual(result, ["/nonexistent/path"])


if __name__ == "__main__":
    unittest.main()
