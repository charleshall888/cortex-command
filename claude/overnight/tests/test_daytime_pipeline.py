"""Unit tests for ``claude.overnight.daytime_pipeline``.

Covers startup guards (CWD, plan.md presence, live PID, stale PID),
success/deferred/paused routing through ``run_daytime``, and behavioural
``deferred_dir`` threading tests that verify both ``feature_executor``
and ``outcome_router`` forward the custom deferred directory to
``write_deferral``.
"""

from __future__ import annotations

import asyncio
import io
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from claude.overnight import daytime_pipeline
from claude.overnight.brain import BrainAction, BrainDecision
from claude.overnight.daytime_pipeline import run_daytime
from claude.overnight.feature_executor import execute_feature
from claude.overnight.orchestrator import BatchResult
from claude.overnight.outcome_router import (
    OutcomeContext,
    apply_feature_result,
)
from claude.overnight.types import CircuitBreakerState, FeatureResult


def _make_ctx(feature: str = "feat") -> OutcomeContext:
    """Factory: build an ``OutcomeContext`` mirroring test_outcome_router."""
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
    config.overnight_events_path = Path("/tmp/unused-overnight.log")
    config.pipeline_events_path = Path("/tmp/unused-pipeline.log")
    config.overnight_state_path = Path("/tmp/unused-state.json")

    return OutcomeContext(
        batch_result=batch_result,
        lock=asyncio.Lock(),
        cb_state=CircuitBreakerState(),
        recovery_attempts_map={},
        worktree_paths={feature: Path("/tmp/worktree")},
        worktree_branches={feature: f"pipeline/{feature}"},
        repo_path_map={feature: None},
        integration_worktrees={},
        integration_branches={},
        session_id="s1",
        backlog_ids={feature: None},
        feature_names=[feature],
        config=config,
    )


class _CwdCtx:
    """Chdir context manager used by the CWD-based tests."""

    def __init__(self, path: Path):
        self._path = path
        self._orig: str | None = None

    def __enter__(self) -> None:
        self._orig = os.getcwd()
        os.chdir(self._path)

    def __exit__(self, *exc) -> None:
        if self._orig is not None:
            os.chdir(self._orig)


class TestRunDaytimeStartupGuards(unittest.IsolatedAsyncioTestCase):
    """Startup-layer guard behaviours for ``run_daytime``."""

    async def test_cwd_guard_rejects_wrong_directory(self) -> None:
        """Running outside the repo root (no ``lifecycle/`` dir) must
        exit with code 1 and emit ``must be run from the repo root`` on
        stderr."""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            # Confirm no lifecycle dir exists.
            self.assertFalse((Path(td) / "lifecycle").exists())
            stderr = io.StringIO()
            with _CwdCtx(Path(td)), patch.object(sys, "stderr", stderr):
                with self.assertRaises(SystemExit) as cm:
                    await run_daytime("feat")
        self.assertEqual(cm.exception.code, 1)
        self.assertIn("must be run from the repo root", stderr.getvalue())

    async def test_plan_check_rejects_missing_plan(self) -> None:
        """With ``lifecycle/feat/`` present but no ``plan.md``, must
        return 1 and emit ``plan.md not found`` on stderr."""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            feat_dir = Path(td) / "lifecycle" / "feat"
            feat_dir.mkdir(parents=True)
            stderr = io.StringIO()
            with _CwdCtx(Path(td)), patch.object(sys, "stderr", stderr):
                rc = await run_daytime("feat")
        self.assertEqual(rc, 1)
        self.assertIn("plan.md not found", stderr.getvalue())

    async def test_live_pid_guard_rejects_running_instance(self) -> None:
        """If ``daytime.pid`` contains the current (live) PID,
        ``run_daytime`` must return 1 and emit ``already running``."""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            feat_dir = Path(td) / "lifecycle" / "feat"
            feat_dir.mkdir(parents=True)
            (feat_dir / "plan.md").write_text("# feat\n", encoding="utf-8")
            (feat_dir / "daytime.pid").write_text(
                str(os.getpid()), encoding="utf-8"
            )
            stderr = io.StringIO()
            with _CwdCtx(Path(td)), patch.object(sys, "stderr", stderr):
                rc = await run_daytime("feat")
        self.assertEqual(rc, 1)
        self.assertIn("already running", stderr.getvalue())

    async def test_stale_pid_triggers_recovery_and_proceeds(self) -> None:
        """A PID file referencing a dead process (99999) must result in
        a single ``_recover_stale`` call, and ``run_daytime`` must
        proceed past the PID check (reaching ``create_worktree``)."""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            feat_dir = Path(td) / "lifecycle" / "feat"
            feat_dir.mkdir(parents=True)
            (feat_dir / "plan.md").write_text("# feat\n", encoding="utf-8")
            (feat_dir / "daytime.pid").write_text("99999", encoding="utf-8")

            worktree_info = MagicMock()
            worktree_info.path = Path("/tmp/fake-worktree")
            worktree_info.branch = "pipeline/feat"

            with (
                _CwdCtx(Path(td)),
                patch.object(
                    daytime_pipeline, "_recover_stale"
                ) as m_recover,
                patch.object(
                    daytime_pipeline,
                    "create_worktree",
                    return_value=worktree_info,
                ),
                patch.object(
                    daytime_pipeline,
                    "execute_feature",
                    new=AsyncMock(
                        return_value=FeatureResult(
                            name="feat", status="completed",
                        )
                    ),
                ),
                patch.object(
                    daytime_pipeline,
                    "apply_feature_result",
                    new=AsyncMock(),
                ),
                patch.object(daytime_pipeline, "cleanup_worktree"),
            ):
                await run_daytime("feat")

        m_recover.assert_called_once()


class TestRunDaytimeRouting(unittest.IsolatedAsyncioTestCase):
    """Exit-code routing for the three terminal outcomes."""

    def _setup_dirs(self, td: str, feature: str = "feat") -> None:
        feat_dir = Path(td) / "lifecycle" / feature
        feat_dir.mkdir(parents=True)
        (feat_dir / "plan.md").write_text(f"# {feature}\n", encoding="utf-8")

    async def test_success_routing_returns_zero(self) -> None:
        """``apply_feature_result`` appends to ``features_merged`` →
        ``run_daytime`` returns 0."""
        import tempfile

        feature = "feat"
        worktree_info = MagicMock()
        worktree_info.path = Path("/tmp/fake-worktree")
        worktree_info.branch = f"pipeline/{feature}"

        async def _apply_side_effect(name, result, ctx, **kwargs):
            ctx.batch_result.features_merged.append(name)

        with tempfile.TemporaryDirectory() as td:
            self._setup_dirs(td, feature)
            with (
                _CwdCtx(Path(td)),
                patch.object(
                    daytime_pipeline,
                    "create_worktree",
                    return_value=worktree_info,
                ),
                patch.object(
                    daytime_pipeline,
                    "execute_feature",
                    new=AsyncMock(
                        return_value=FeatureResult(
                            name=feature, status="completed",
                        )
                    ),
                ),
                patch.object(
                    daytime_pipeline,
                    "apply_feature_result",
                    new=AsyncMock(side_effect=_apply_side_effect),
                ),
                patch.object(daytime_pipeline, "cleanup_worktree"),
            ):
                rc = await run_daytime(feature)

        self.assertEqual(rc, 0)

    async def test_deferred_routing_returns_one(self) -> None:
        """``apply_feature_result`` appends to ``features_deferred`` →
        ``run_daytime`` returns 1."""
        import tempfile

        feature = "feat"
        worktree_info = MagicMock()
        worktree_info.path = Path("/tmp/fake-worktree")
        worktree_info.branch = f"pipeline/{feature}"

        async def _apply_side_effect(name, result, ctx, **kwargs):
            ctx.batch_result.features_deferred.append(
                {"name": name, "question_count": 1}
            )

        with tempfile.TemporaryDirectory() as td:
            self._setup_dirs(td, feature)
            with (
                _CwdCtx(Path(td)),
                patch.object(
                    daytime_pipeline,
                    "create_worktree",
                    return_value=worktree_info,
                ),
                patch.object(
                    daytime_pipeline,
                    "execute_feature",
                    new=AsyncMock(
                        return_value=FeatureResult(
                            name=feature, status="deferred",
                            deferred_question_count=1,
                        )
                    ),
                ),
                patch.object(
                    daytime_pipeline,
                    "apply_feature_result",
                    new=AsyncMock(side_effect=_apply_side_effect),
                ),
                patch.object(daytime_pipeline, "cleanup_worktree"),
            ):
                rc = await run_daytime(feature)

        self.assertEqual(rc, 1)

    async def test_paused_routing_returns_one(self) -> None:
        """``apply_feature_result`` appends to ``features_paused`` →
        ``run_daytime`` returns 1."""
        import tempfile

        feature = "feat"
        worktree_info = MagicMock()
        worktree_info.path = Path("/tmp/fake-worktree")
        worktree_info.branch = f"pipeline/{feature}"

        async def _apply_side_effect(name, result, ctx, **kwargs):
            ctx.batch_result.features_paused.append(
                {"name": name, "error": "boom"}
            )

        with tempfile.TemporaryDirectory() as td:
            self._setup_dirs(td, feature)
            with (
                _CwdCtx(Path(td)),
                patch.object(
                    daytime_pipeline,
                    "create_worktree",
                    return_value=worktree_info,
                ),
                patch.object(
                    daytime_pipeline,
                    "execute_feature",
                    new=AsyncMock(
                        return_value=FeatureResult(
                            name=feature, status="paused", error="boom",
                        )
                    ),
                ),
                patch.object(
                    daytime_pipeline,
                    "apply_feature_result",
                    new=AsyncMock(side_effect=_apply_side_effect),
                ),
                patch.object(daytime_pipeline, "cleanup_worktree"),
            ):
                rc = await run_daytime(feature)

        self.assertEqual(rc, 1)


class TestDeferredDirThreadingFeatureExecutor(
    unittest.IsolatedAsyncioTestCase
):
    """Req 6: ``execute_feature`` must forward a custom ``deferred_dir``
    through to ``write_deferral`` in the DEFER path of the brain agent
    triage."""

    async def test_execute_feature_forwards_deferred_dir_to_write_deferral(
        self,
    ) -> None:
        from claude.pipeline.parser import FeaturePlan, FeatureTask
        from claude.pipeline.retry import RetryResult

        feature = "feat"
        custom_dir = Path("/custom")

        fake_plan = FeaturePlan(
            feature=feature,
            overview="stub",
            tasks=[
                FeatureTask(
                    number=1,
                    description="stub task",
                    files=[],
                    depends_on=[],
                    complexity="simple",
                )
            ],
        )

        failing_retry = RetryResult(
            success=False,
            attempts=3,
            final_output="error",
            learnings_path=None,
            paused=True,
        )

        brain_decision = BrainDecision(
            action=BrainAction.DEFER,
            reasoning="unanswered spec question",
            question="How should X behave?",
            severity="blocking",
            confidence=0.8,
        )

        config = MagicMock()
        config.batch_id = 1
        config.base_branch = "main"
        config.test_command = None
        config.overnight_state_path = Path("/tmp/unused-state.json")
        config.overnight_events_path = Path("/tmp/unused-overnight.log")
        config.pipeline_events_path = Path("/tmp/unused-pipeline.log")

        with (
            patch(
                "claude.overnight.feature_executor.write_deferral",
                MagicMock(return_value=Path("/custom/feat-q001.md")),
            ) as m_write,
            patch(
                "claude.overnight.feature_executor.parse_feature_plan",
                return_value=fake_plan,
            ),
            patch(
                "claude.overnight.feature_executor.load_state",
                side_effect=Exception("skip conflict recovery"),
            ),
            patch(
                "claude.overnight.feature_executor.retry_task",
                new=AsyncMock(return_value=failing_retry),
            ),
            patch(
                "claude.overnight.feature_executor.request_brain_decision",
                new=AsyncMock(return_value=brain_decision),
            ),
            patch(
                "claude.overnight.feature_executor._read_learnings",
                return_value="(none)",
            ),
            patch(
                "claude.overnight.feature_executor._read_spec_content",
                return_value="spec text",
            ),
            patch(
                "claude.overnight.feature_executor.read_criticality",
                return_value="low",
            ),
            patch(
                "claude.overnight.feature_executor.pipeline_log_event"
            ),
            patch(
                "claude.overnight.feature_executor.overnight_log_event"
            ),
            patch(
                "claude.overnight.feature_executor.subprocess.run",
                return_value=MagicMock(returncode=0, stdout="0\n", stderr=""),
            ),
        ):
            result = await execute_feature(
                feature,
                Path("/tmp/wt"),
                config,
                deferred_dir=custom_dir,
            )

        self.assertEqual(result.status, "deferred")
        m_write.assert_called_once()
        self.assertEqual(
            m_write.call_args.kwargs.get("deferred_dir"), custom_dir
        )


class TestDeferredDirThreadingOutcomeRouter(
    unittest.IsolatedAsyncioTestCase
):
    """Req 6: ``apply_feature_result`` must forward a custom
    ``deferred_dir`` to ``write_deferral`` on CI-blocking outcomes."""

    async def test_apply_feature_result_forwards_deferred_dir_ci_failing(
        self,
    ) -> None:
        feature = "feat"
        custom_dir = Path("/custom")
        ctx = _make_ctx(feature)

        merge_result = MagicMock()
        merge_result.success = False
        merge_result.error = "ci_failing"
        merge_result.conflict = False
        merge_result.test_result = None

        with (
            patch(
                "claude.overnight.outcome_router.write_deferral",
                MagicMock(return_value=Path("/custom/feat-q001.md")),
            ) as m_write,
            patch(
                "claude.overnight.outcome_router._get_changed_files",
                return_value=["src/a.py"],
            ),
            patch(
                "claude.overnight.outcome_router.merge_feature",
                return_value=merge_result,
            ),
            patch(
                "claude.overnight.outcome_router._write_back_to_backlog",
            ),
            patch(
                "claude.overnight.outcome_router.overnight_log_event"
            ),
            patch(
                "claude.overnight.outcome_router._next_escalation_n",
                return_value=1,
            ),
        ):
            await apply_feature_result(
                feature,
                FeatureResult(name=feature, status="completed"),
                ctx,
                deferred_dir=custom_dir,
            )

        m_write.assert_called_once()
        self.assertEqual(
            m_write.call_args.kwargs.get("deferred_dir"), custom_dir
        )


if __name__ == "__main__":
    unittest.main()
