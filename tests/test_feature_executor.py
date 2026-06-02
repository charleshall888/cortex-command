"""Tests for cortex_command.overnight.feature_executor cross-repo allowlist fix.

Covers spec Req 7: ``execute_feature`` resolves ``integration_base_path`` to the
cross-repo's integration-worktree path when ``repo_path`` is non-None and to
``Path.cwd()`` when ``repo_path`` is None. The pre-fix unconditional
``Path.cwd()`` admitted the home repo into cross-repo dispatch allowlists; the
fix routes through the canonical ``_effective_merge_repo_path`` helper.

These tests follow the patching pattern established in
``cortex_command/overnight/tests/test_lead_unit.py`` (TestExecuteFeature):
mock ``retry_task`` and capture the kwargs it was called with so we can
assert the resolved ``integration_base_path``.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import cortex_command.overnight.feature_executor as feature_executor_module
from cortex_command.overnight.feature_executor import execute_feature
from cortex_command.overnight.orchestrator import BatchConfig
from cortex_command.overnight.state import (
    OvernightState,
    OvernightFeatureStatus,
    _normalize_repo_key,
)
from cortex_command.pipeline.parser import FeaturePlan, FeatureTask
from cortex_command.pipeline.retry import RetryResult


class TestCrossRepoIntegrationBasePath(unittest.IsolatedAsyncioTestCase):
    """Spec Req 7: ``integration_base_path`` is conditionally routed through
    ``_effective_merge_repo_path`` based on whether ``repo_path`` is None.

    Pattern: mock ``retry_task`` to capture its kwargs; mock ``load_state`` to
    return a populated ``OvernightState``; mock parser/template/log helpers
    so ``execute_feature`` runs the dispatch block straight through to the
    captured ``retry_task`` call.
    """

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._tmp = Path(self._tmpdir.name)
        self._config = BatchConfig(
            batch_id=1,
            plan_path=self._tmp / "plan.md",
            overnight_events_path=self._tmp / "overnight.log",
            pipeline_events_path=self._tmp / "pipeline.log",
            overnight_state_path=self._tmp / "state.json",
            session_id="test-session",
            session_dir=self._tmp,
        )
        self._feature_plan = FeaturePlan(
            feature="test-feat",
            overview="",
            tasks=[
                FeatureTask(
                    number=1,
                    description="do something",
                    depends_on=[],
                    files=["test.py"],
                    complexity="simple",
                )
            ],
        )

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _make_retry_capture(self):
        """Return an AsyncMock that captures the kwargs ``retry_task`` is called
        with and returns a successful RetryResult."""
        captured: dict = {}

        async def _capture(**kwargs):
            captured.update(kwargs)
            return RetryResult(
                success=True,
                attempts=1,
                final_output="done",
                paused=False,
                idempotency_skipped=False,
            )

        mock = AsyncMock(side_effect=_capture)
        return mock, captured

    def _base_patches(self, mock_retry, overnight_state):
        """Build the patch list shared across the two tests."""
        return [
            patch.object(
                feature_executor_module,
                "load_state",
                return_value=overnight_state,
            ),
            patch.object(
                feature_executor_module,
                "parse_feature_plan",
                return_value=self._feature_plan,
            ),
            patch.object(feature_executor_module, "retry_task", new=mock_retry),
            patch.object(
                feature_executor_module,
                "_read_exit_report",
                return_value=("complete", None, None),
            ),
            patch.object(feature_executor_module, "mark_task_done_in_plan"),
            patch.object(feature_executor_module, "pipeline_log_event"),
            patch.object(feature_executor_module, "overnight_log_event"),
            patch.object(
                feature_executor_module, "read_criticality", return_value="medium"
            ),
            patch.object(
                feature_executor_module,
                "_render_template",
                return_value="stub system prompt",
            ),
            patch.object(
                feature_executor_module,
                "read_events",
                return_value=[],
            ),
            patch.object(
                subprocess,
                "run",
                return_value=MagicMock(returncode=0, stdout="0\n", stderr=""),
            ),
        ]

    async def test_cross_repo_uses_integration_worktree(self) -> None:
        """When ``repo_path`` is non-None, ``integration_base_path`` resolves to
        the cross-repo's integration-worktree path (NOT ``Path.cwd()``).
        """
        cross_repo = self._tmp / "cross-repo"
        cross_repo.mkdir()
        cross_worktree = self._tmp / "wt-cross"
        cross_worktree.mkdir()  # exists on disk so cached hit fires

        repo_key = _normalize_repo_key(str(cross_repo))
        overnight_state = OvernightState(
            session_id="test-session",
            integration_worktrees={repo_key: str(cross_worktree)},
            integration_branches={repo_key: "overnight/test"},
            features={
                "test-feat": OvernightFeatureStatus(status="pending")
            },
        )

        mock_retry, captured = self._make_retry_capture()
        patches = self._base_patches(mock_retry, overnight_state)

        with patches[0], patches[1], patches[2], patches[3], patches[4], \
             patches[5], patches[6], patches[7], patches[8], patches[9], \
             patches[10]:
            await execute_feature(
                feature="test-feat",
                worktree_path=self._tmp / "worktree",
                config=self._config,
                repo_path=cross_repo,
            )

        captured_path = captured.get("integration_base_path")
        assert captured_path is not None, "retry_task was not called"
        # integration_base_path must equal the cross-repo's integration-worktree path
        # via _effective_merge_repo_path resolution. The helper returns
        # Path(cross_worktree) — which on macOS may have a /private prefix
        # under tempfile resolution. Compare the resolved real paths.
        self.assertEqual(
            Path(captured_path).resolve(),
            cross_worktree.resolve(),
            f"Expected cross-repo worktree {cross_worktree}, got {captured_path}",
        )
        # Must NOT equal Path.cwd() — that would be the pre-fix bug.
        self.assertNotEqual(
            Path(captured_path).resolve(),
            Path.cwd().resolve(),
            "integration_base_path leaked Path.cwd() (pre-fix behavior)",
        )

    async def test_same_repo_uses_cwd(self) -> None:
        """When ``repo_path`` is None, ``integration_base_path`` resolves to
        ``Path.cwd()`` (preserved same-repo behavior).
        """
        overnight_state = OvernightState(
            session_id="test-session",
            integration_worktrees={},
            integration_branches={},
            features={
                "test-feat": OvernightFeatureStatus(status="pending")
            },
        )

        mock_retry, captured = self._make_retry_capture()
        patches = self._base_patches(mock_retry, overnight_state)

        with patches[0], patches[1], patches[2], patches[3], patches[4], \
             patches[5], patches[6], patches[7], patches[8], patches[9], \
             patches[10]:
            await execute_feature(
                feature="test-feat",
                worktree_path=self._tmp / "worktree",
                config=self._config,
                repo_path=None,
            )

        captured_path = captured.get("integration_base_path")
        assert captured_path is not None, "retry_task was not called"
        self.assertEqual(
            Path(captured_path).resolve(),
            Path.cwd().resolve(),
            f"Expected Path.cwd() for repo_path=None, got {captured_path}",
        )


class TestSystemicFallthrough(unittest.IsolatedAsyncioTestCase):
    """Verify that a systemic error_type propagated through _run_feature_tasks
    yields FeatureResult(status='paused', error=error_type) rather than the
    generic 'Task N failed after M attempts' string.

    Covers: _SYSTEMIC_ERROR_TYPES guard inserted after brain-triage returns None.
    """

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._tmp = Path(self._tmpdir.name)
        self._config = BatchConfig(
            batch_id=1,
            plan_path=self._tmp / "plan.md",
            overnight_events_path=self._tmp / "overnight.log",
            pipeline_events_path=self._tmp / "pipeline.log",
            overnight_state_path=self._tmp / "state.json",
            session_id="test-session",
            session_dir=self._tmp,
        )
        self._feature_plan = FeaturePlan(
            feature="test-feat",
            overview="",
            tasks=[
                FeatureTask(
                    number=1,
                    description="do something",
                    depends_on=[],
                    files=["test.py"],
                    complexity="simple",
                )
            ],
        )

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    async def test_systemic_fallthrough_infrastructure_failure(self) -> None:
        """A RetryResult(success=False, paused=True, error_type='infrastructure_failure')
        where _handle_failed_task returns None produces
        FeatureResult(status='paused', error='infrastructure_failure').
        """
        systemic_retry = RetryResult(
            success=False,
            attempts=3,
            final_output="",
            paused=True,
            idempotency_skipped=False,
            error_type="infrastructure_failure",
        )

        overnight_state = OvernightState(
            session_id="test-session",
            integration_worktrees={},
            integration_branches={},
            features={
                "test-feat": OvernightFeatureStatus(status="pending")
            },
        )

        patches = [
            patch.object(
                feature_executor_module,
                "load_state",
                return_value=overnight_state,
            ),
            patch.object(
                feature_executor_module,
                "parse_feature_plan",
                return_value=self._feature_plan,
            ),
            patch.object(
                feature_executor_module,
                "retry_task",
                new=AsyncMock(return_value=systemic_retry),
            ),
            # Brain triage returns None — systemic guard should fire
            patch.object(
                feature_executor_module,
                "_handle_failed_task",
                new=AsyncMock(return_value=None),
            ),
            patch.object(feature_executor_module, "pipeline_log_event"),
            patch.object(feature_executor_module, "overnight_log_event"),
            patch.object(
                feature_executor_module, "read_criticality", return_value="medium"
            ),
            patch.object(
                feature_executor_module,
                "_render_template",
                return_value="stub system prompt",
            ),
            patch.object(
                feature_executor_module,
                "read_events",
                return_value=[],
            ),
        ]

        with patches[0], patches[1], patches[2], patches[3], patches[4], \
             patches[5], patches[6], patches[7], patches[8]:
            result = await feature_executor_module.execute_feature(
                feature="test-feat",
                worktree_path=self._tmp / "worktree",
                config=self._config,
                repo_path=None,
            )

        self.assertEqual(result.status, "paused")
        self.assertEqual(result.error, "infrastructure_failure")
        self.assertNotIn(
            "failed after",
            result.error or "",
            "Generic fallthrough string should not appear for systemic errors",
        )


class TestSilentWorkerExitReport(unittest.IsolatedAsyncioTestCase):
    """Task 3: silent-worker zero-commits gate.

    Covers three cases described in the task spec:
    (a) WORKER_NO_EXIT_REPORT on task 1 but task 2 produces commits -> completed
    (b) WORKER_NO_EXIT_REPORT on only task, zero commits -> paused/worker_no_exit_report
    (c) WORKER_MALFORMED_EXIT_REPORT on only task, zero commits -> paused/worker_malformed_exit_report
    """

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._tmp = Path(self._tmpdir.name)
        self._config = BatchConfig(
            batch_id=1,
            plan_path=self._tmp / "plan.md",
            overnight_events_path=self._tmp / "overnight.log",
            pipeline_events_path=self._tmp / "pipeline.log",
            overnight_state_path=self._tmp / "state.json",
            session_id="test-session",
            session_dir=self._tmp,
        )

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _make_two_task_plan(self) -> FeaturePlan:
        return FeaturePlan(
            feature="test-feat",
            overview="",
            tasks=[
                FeatureTask(
                    number=1,
                    description="task one",
                    depends_on=[],
                    files=["a.py"],
                    complexity="simple",
                ),
                FeatureTask(
                    number=2,
                    description="task two",
                    depends_on=[1],
                    files=["b.py"],
                    complexity="simple",
                ),
            ],
        )

    def _make_single_task_plan(self) -> FeaturePlan:
        return FeaturePlan(
            feature="test-feat",
            overview="",
            tasks=[
                FeatureTask(
                    number=1,
                    description="task one",
                    depends_on=[],
                    files=["a.py"],
                    complexity="simple",
                ),
            ],
        )

    def _good_retry_result(self) -> RetryResult:
        return RetryResult(
            success=True,
            attempts=1,
            final_output="done",
            paused=False,
            idempotency_skipped=False,
        )

    def _base_patches(self, mock_retry):
        overnight_state = OvernightState(
            session_id="test-session",
            integration_worktrees={},
            integration_branches={},
            features={"test-feat": OvernightFeatureStatus(status="pending")},
        )
        return [
            patch.object(feature_executor_module, "load_state", return_value=overnight_state),
            patch.object(feature_executor_module, "retry_task", new=mock_retry),
            patch.object(feature_executor_module, "mark_task_done_in_plan"),
            patch.object(feature_executor_module, "pipeline_log_event"),
            patch.object(feature_executor_module, "overnight_log_event"),
            patch.object(feature_executor_module, "read_criticality", return_value="medium"),
            patch.object(feature_executor_module, "_render_template", return_value="stub"),
            patch.object(feature_executor_module, "read_events", return_value=[]),
        ]

    async def test_silent_worker_no_exit_report_with_later_commit_completes(self) -> None:
        """Case (a): task 1 has no exit report (zero commits), task 2 produces a
        commit. Because total_commits > 0, the feature should return completed.
        """
        feature_plan = self._make_two_task_plan()

        call_count = 0

        async def _retry_side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            return self._good_retry_result()

        mock_retry = AsyncMock(side_effect=_retry_side_effect)

        # subprocess.run: first two calls are for task 1 (status=0 commits),
        # second two calls are for task 2 (status=1 commit).
        run_call_count = 0

        def _run_side_effect(*args, **kwargs):
            nonlocal run_call_count
            run_call_count += 1
            # git status call (odd-numbered within each task pair)
            if run_call_count % 2 == 1:
                return MagicMock(returncode=0, stdout="", stderr="")
            # git rev-list call: task 1 -> 0 commits, task 2 -> 1 commit
            task_n = (run_call_count // 2)
            count = "0\n" if task_n == 0 else "1\n"
            return MagicMock(returncode=0, stdout=count, stderr="")

        # _read_exit_report: task 1 returns (None, None, None) to trigger no-exit-report path;
        # task 2 returns ("complete", None, None).
        exit_report_call_count = 0

        def _exit_report_side_effect(feature, task_number, worktree_path=None, **kwargs):
            if task_number == 1:
                return (None, None, None)
            return ("complete", None, None)

        patches = self._base_patches(mock_retry)
        patches.append(
            patch.object(
                feature_executor_module,
                "parse_feature_plan",
                return_value=feature_plan,
            )
        )
        patches.append(
            patch.object(
                feature_executor_module,
                "_read_exit_report",
                side_effect=_exit_report_side_effect,
            )
        )
        patches.append(
            patch(
                "subprocess.run",
                side_effect=_run_side_effect,
            )
        )

        with patches[0], patches[1], patches[2], patches[3], patches[4], \
             patches[5], patches[6], patches[7], patches[8], patches[9], patches[10]:
            result = await feature_executor_module.execute_feature(
                feature="test-feat",
                worktree_path=self._tmp / "worktree",
                config=self._config,
                repo_path=None,
            )

        self.assertEqual(result.status, "completed",
                         f"Expected completed, got {result.status!r} (error={result.error!r})")

    async def test_silent_worker_no_exit_report_zero_commits_pauses(self) -> None:
        """Case (b): single task with WORKER_NO_EXIT_REPORT and zero commits ->
        FeatureResult(status='paused', error='worker_no_exit_report').
        """
        feature_plan = self._make_single_task_plan()
        mock_retry = AsyncMock(return_value=self._good_retry_result())

        patches = self._base_patches(mock_retry)
        patches.append(
            patch.object(
                feature_executor_module,
                "parse_feature_plan",
                return_value=feature_plan,
            )
        )
        # No exit report file -> no-exit-report path
        patches.append(
            patch.object(
                feature_executor_module,
                "_read_exit_report",
                return_value=(None, None, None),
            )
        )
        # git rev-list returns 0 commits; git status returns empty
        patches.append(
            patch(
                "subprocess.run",
                side_effect=[
                    MagicMock(returncode=0, stdout="", stderr=""),   # git status
                    MagicMock(returncode=0, stdout="0\n", stderr=""),  # git rev-list
                ],
            )
        )

        with patches[0], patches[1], patches[2], patches[3], patches[4], \
             patches[5], patches[6], patches[7], patches[8], patches[9], patches[10]:
            result = await feature_executor_module.execute_feature(
                feature="test-feat",
                worktree_path=self._tmp / "worktree",
                config=self._config,
                repo_path=None,
            )

        self.assertEqual(result.status, "paused")
        self.assertEqual(result.error, "worker_no_exit_report")

    async def test_silent_worker_malformed_exit_report_zero_commits_pauses(self) -> None:
        """Case (c): single task with WORKER_MALFORMED_EXIT_REPORT and zero commits ->
        FeatureResult(status='paused', error='worker_malformed_exit_report').
        """
        feature_plan = self._make_single_task_plan()
        mock_retry = AsyncMock(return_value=self._good_retry_result())

        # Create the exit-report file so the malformed branch fires
        exit_reports_dir = Path("cortex/lifecycle/test-feat/exit-reports")
        exit_reports_dir.mkdir(parents=True, exist_ok=True)
        (exit_reports_dir / "1.json").write_text('{"action": "unknown_action"}', encoding="utf-8")

        try:
            patches = self._base_patches(mock_retry)
            patches.append(
                patch.object(
                    feature_executor_module,
                    "parse_feature_plan",
                    return_value=feature_plan,
                )
            )
            # _read_exit_report returns (None, None, None) — malformed report
            patches.append(
                patch.object(
                    feature_executor_module,
                    "_read_exit_report",
                    return_value=(None, None, None),
                )
            )
            # Make report_path.is_file() return True by patching Path.is_file within
            # the feature_executor module's check. We achieve this by having the
            # actual file exist and patching only _read_exit_report above while
            # not patching Path.is_file — the file we created above will be found.
            # git subprocess calls
            patches.append(
                patch(
                    "subprocess.run",
                    side_effect=[
                        MagicMock(returncode=0, stdout="", stderr=""),   # git status
                        MagicMock(returncode=0, stdout="0\n", stderr=""),  # git rev-list
                    ],
                )
            )

            with patches[0], patches[1], patches[2], patches[3], patches[4], \
                 patches[5], patches[6], patches[7], patches[8], patches[9], patches[10]:
                result = await feature_executor_module.execute_feature(
                    feature="test-feat",
                    worktree_path=self._tmp / "worktree",
                    config=self._config,
                    repo_path=None,
                )

            self.assertEqual(result.status, "paused")
            self.assertEqual(result.error, "worker_malformed_exit_report")
        finally:
            import shutil
            shutil.rmtree("cortex/lifecycle/test-feat", ignore_errors=True)


class TestRootResolvedLifecycleReads:
    """Task 7: the dispatch path's plan read and ``read_criticality`` read
    resolve against ``_resolve_user_project_root()`` (via ``CORTEX_REPO_ROOT``),
    not the CWD.

    Reproduces the production env-set / CWD-divergent branch: ``CORTEX_REPO_ROOT``
    points at a fixture root containing ``cortex/lifecycle/{feature}/`` while the
    process CWD is a *different* directory. A pre-fix dispatch path would read
    ``cortex/lifecycle/{feature}/plan.md`` relative to the divergent CWD (missing →
    parse error) and ``read_criticality`` would fall back to the ``medium`` default.
    """

    def _write_fixture(self, root: Path, feature: str, criticality: str) -> None:
        lifecycle = root / "cortex" / "lifecycle" / feature
        lifecycle.mkdir(parents=True, exist_ok=True)
        (lifecycle / "plan.md").write_text(
            "# Plan: "
            + feature
            + "\n\n## Overview\nDo a thing.\n\n"
            + "### Task 1: do something\n"
            + "- **Files**: a.py\n"
            + "- **Depends on**: None\n"
            + "- **Complexity**: simple\n",
            encoding="utf-8",
        )
        (lifecycle / "events.log").write_text(
            json.dumps(
                {
                    "event": "lifecycle_start",
                    "feature": feature,
                    "criticality": criticality,
                }
            )
            + "\n",
            encoding="utf-8",
        )

    def test_env_set_cwd_divergent_reads_resolve_against_root(
        self, tmp_path, monkeypatch
    ) -> None:
        feature = "root-resolve-feat"
        declared_criticality = "critical"  # NOT the "medium" default

        # Fixture root holds the lifecycle dir; CWD diverges to an empty dir.
        repo_root = tmp_path / "repo-root"
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        self._write_fixture(repo_root, feature, declared_criticality)

        # Reproduce the production branch: env set, CWD elsewhere.
        monkeypatch.setenv("CORTEX_REPO_ROOT", str(repo_root))
        monkeypatch.chdir(elsewhere)

        # read_criticality is lru_cached on the events.log stat key; clear to
        # avoid cross-test contamination on the (path, exists, mtime, size) key.
        import cortex_command.common as common_module
        common_module._read_criticality_inner.cache_clear()

        session_dir = tmp_path / "session"
        session_dir.mkdir()
        config = BatchConfig(
            batch_id=1,
            plan_path=session_dir / "plan.md",
            overnight_events_path=session_dir / "overnight.log",
            pipeline_events_path=session_dir / "pipeline.log",
            overnight_state_path=session_dir / "state.json",
            session_id="test-session",
            session_dir=session_dir,
        )

        overnight_state = OvernightState(
            session_id="test-session",
            integration_worktrees={},
            integration_branches={},
            features={feature: OvernightFeatureStatus(status="pending")},
        )

        captured: dict = {}

        async def _capture(**kwargs):
            captured.update(kwargs)
            return RetryResult(
                success=True,
                attempts=1,
                final_output="done",
                paused=False,
                idempotency_skipped=False,
            )

        mock_retry = AsyncMock(side_effect=_capture)

        # Real parse_feature_plan and real read_criticality run against the
        # fixture root — only the dispatch-incidental helpers are mocked.
        with patch.object(
            feature_executor_module, "load_state", return_value=overnight_state
        ), patch.object(
            feature_executor_module, "retry_task", new=mock_retry
        ), patch.object(
            feature_executor_module,
            "_read_exit_report",
            return_value=("complete", None, None),
        ), patch.object(
            feature_executor_module, "mark_task_done_in_plan"
        ), patch.object(
            feature_executor_module, "pipeline_log_event"
        ), patch.object(
            feature_executor_module, "overnight_log_event"
        ), patch.object(
            feature_executor_module, "_render_template", return_value="stub"
        ), patch.object(
            feature_executor_module, "read_events", return_value=[]
        ), patch.object(
            subprocess,
            "run",
            return_value=MagicMock(returncode=0, stdout="0\n", stderr=""),
        ):
            result = asyncio.run(
                execute_feature(
                    feature=feature,
                    worktree_path=tmp_path / "worktree",
                    config=config,
                    repo_path=None,
                )
            )

        # The plan parsed (no parse_error) — it was found under the fixture root,
        # not the divergent CWD.
        assert result.parse_error is False, (
            f"plan read failed under divergent CWD: {result.error!r}"
        )
        assert captured.get("complexity") == "simple", (
            "plan was not parsed from the root-resolved path"
        )
        # read_criticality returned the declared value, not the medium default.
        assert captured.get("criticality") == declared_criticality, (
            f"expected {declared_criticality!r}, got "
            f"{captured.get('criticality')!r} (medium default = CWD-relative bug)"
        )


if __name__ == "__main__":
    unittest.main()
