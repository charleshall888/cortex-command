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


if __name__ == "__main__":
    unittest.main()
