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
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from cortex_command.overnight import daytime_pipeline
from cortex_command.overnight.brain import BrainAction, BrainDecision
from cortex_command.overnight.daytime_pipeline import run_daytime
from cortex_command.overnight.feature_executor import execute_feature
from cortex_command.overnight.orchestrator import BatchResult
from cortex_command.overnight.outcome_router import (
    OutcomeContext,
    apply_feature_result,
)
from cortex_command.overnight.types import CircuitBreakerState, FeatureResult


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
        from cortex_command.pipeline.parser import FeaturePlan, FeatureTask
        from cortex_command.pipeline.retry import RetryResult

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


class TestDaytimeResultFile(unittest.IsolatedAsyncioTestCase):
    """Result-file semantics: every exit path of run_daytime must emit
    a valid daytime-result.json with the correct outcome and terminated_via."""

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _setup_dirs(self, td: Path, feature: str = "feat") -> None:
        feat_dir = td / "lifecycle" / feature
        feat_dir.mkdir(parents=True)
        (feat_dir / "plan.md").write_text(f"# {feature}\n", encoding="utf-8")
        (feat_dir / "deferred").mkdir(parents=True, exist_ok=True)

    def _read_result(self, td: Path, feature: str = "feat") -> dict:
        import json

        result_path = td / "lifecycle" / feature / "daytime-result.json"
        self.assertTrue(result_path.exists(), "daytime-result.json not found")
        with result_path.open(encoding="utf-8") as fh:
            return json.load(fh)

    def _worktree_info(self, feature: str = "feat") -> MagicMock:
        info = MagicMock()
        info.path = Path("/tmp/fake-worktree")
        info.branch = f"pipeline/{feature}"
        return info

    # ------------------------------------------------------------------
    # Classification paths (terminated_via="classification")
    # ------------------------------------------------------------------

    async def test_merged_writes_result_file(self) -> None:
        """apply_feature_result populates features_merged -> outcome="merged",
        terminated_via="classification", error=None."""
        feature = "feat"

        async def _apply(name, result, ctx, **kwargs):
            ctx.batch_result.features_merged.append(name)

        with _CwdCtx(Path("/tmp")):
            import tempfile

            with tempfile.TemporaryDirectory() as raw_td:
                td = Path(raw_td)
                self._setup_dirs(td, feature)
                with (
                    _CwdCtx(td),
                    patch.dict(
                        os.environ,
                        {"DAYTIME_DISPATCH_ID": "a" * 32},
                        clear=False,
                    ),
                    patch.object(
                        daytime_pipeline,
                        "create_worktree",
                        return_value=self._worktree_info(feature),
                    ),
                    patch.object(
                        daytime_pipeline,
                        "execute_feature",
                        new=AsyncMock(
                            return_value=MagicMock(name="feat", status="completed")
                        ),
                    ),
                    patch.object(
                        daytime_pipeline,
                        "apply_feature_result",
                        new=AsyncMock(side_effect=_apply),
                    ),
                    patch.object(daytime_pipeline, "cleanup_worktree"),
                ):
                    rc = await run_daytime(feature)

                result = self._read_result(td, feature)

        self.assertEqual(rc, 0)
        self.assertEqual(result["outcome"], "merged")
        self.assertEqual(result["terminated_via"], "classification")
        self.assertIsNone(result["error"])
        self.assertEqual(result["schema_version"], 1)
        self.assertRegex(result["dispatch_id"], r"^[a-f0-9]{32}$")

    async def test_deferred_with_file_writes_result_file(self) -> None:
        """apply_feature_result populates features_deferred + a file under
        deferred_dir -> outcome="deferred", deferred_files=[absolute_path]."""
        feature = "feat"

        async def _apply(name, result, ctx, **kwargs):
            ctx.batch_result.features_deferred.append(
                {"name": name, "question_count": 1}
            )

        import tempfile

        with tempfile.TemporaryDirectory() as raw_td:
            td = Path(raw_td)
            self._setup_dirs(td, feature)

            # Pre-create a deferral file so deferred_files is populated.
            deferred_dir = td / "lifecycle" / feature / "deferred"
            deferred_file = deferred_dir / "x.md"
            deferred_file.write_text("# question\n", encoding="utf-8")

            with (
                _CwdCtx(td),
                patch.dict(
                    os.environ,
                    {"DAYTIME_DISPATCH_ID": "a" * 32},
                    clear=False,
                ),
                patch.object(
                    daytime_pipeline,
                    "create_worktree",
                    return_value=self._worktree_info(feature),
                ),
                patch.object(
                    daytime_pipeline,
                    "execute_feature",
                    new=AsyncMock(
                        return_value=MagicMock(name="feat", status="deferred")
                    ),
                ),
                patch.object(
                    daytime_pipeline,
                    "apply_feature_result",
                    new=AsyncMock(side_effect=_apply),
                ),
                patch.object(daytime_pipeline, "cleanup_worktree"),
            ):
                rc = await run_daytime(feature)

            result = self._read_result(td, feature)

        self.assertEqual(rc, 1)
        self.assertEqual(result["outcome"], "deferred")
        self.assertEqual(result["terminated_via"], "classification")
        self.assertIsNone(result["error"])
        self.assertEqual(len(result["deferred_files"]), 1)
        # The implementation globs relative to CWD and stores the path as
        # str(Path("lifecycle/feat/deferred/x.md")) — a relative path.
        # We assert the filename is present rather than requiring an absolute path,
        # pinning the actual behavior while remaining cross-platform.
        self.assertIn("x.md", result["deferred_files"][0])

    async def test_paused_writes_result_file(self) -> None:
        """apply_feature_result populates features_paused ->
        outcome="paused", terminated_via="classification"."""
        feature = "feat"

        async def _apply(name, result, ctx, **kwargs):
            ctx.batch_result.features_paused.append(
                {"name": name, "error": "boom"}
            )

        import tempfile

        with tempfile.TemporaryDirectory() as raw_td:
            td = Path(raw_td)
            self._setup_dirs(td, feature)
            with (
                _CwdCtx(td),
                patch.dict(
                    os.environ,
                    {"DAYTIME_DISPATCH_ID": "a" * 32},
                    clear=False,
                ),
                patch.object(
                    daytime_pipeline,
                    "create_worktree",
                    return_value=self._worktree_info(feature),
                ),
                patch.object(
                    daytime_pipeline,
                    "execute_feature",
                    new=AsyncMock(
                        return_value=MagicMock(name="feat", status="paused")
                    ),
                ),
                patch.object(
                    daytime_pipeline,
                    "apply_feature_result",
                    new=AsyncMock(side_effect=_apply),
                ),
                patch.object(daytime_pipeline, "cleanup_worktree"),
            ):
                rc = await run_daytime(feature)

            result = self._read_result(td, feature)

        self.assertEqual(rc, 1)
        self.assertEqual(result["outcome"], "paused")
        self.assertEqual(result["terminated_via"], "classification")
        self.assertIsNone(result["error"])

    async def test_failed_with_error_writes_result_file(self) -> None:
        """apply_feature_result populates features_failed with error ->
        outcome="failed", terminated_via="classification", error populated."""
        feature = "feat"
        fail_msg = "some CI error"

        async def _apply(name, result, ctx, **kwargs):
            ctx.batch_result.features_failed.append(
                {"name": name, "error": fail_msg}
            )

        import tempfile

        with tempfile.TemporaryDirectory() as raw_td:
            td = Path(raw_td)
            self._setup_dirs(td, feature)
            with (
                _CwdCtx(td),
                patch.dict(
                    os.environ,
                    {"DAYTIME_DISPATCH_ID": "a" * 32},
                    clear=False,
                ),
                patch.object(
                    daytime_pipeline,
                    "create_worktree",
                    return_value=self._worktree_info(feature),
                ),
                patch.object(
                    daytime_pipeline,
                    "execute_feature",
                    new=AsyncMock(
                        return_value=MagicMock(name="feat", status="failed")
                    ),
                ),
                patch.object(
                    daytime_pipeline,
                    "apply_feature_result",
                    new=AsyncMock(side_effect=_apply),
                ),
                patch.object(daytime_pipeline, "cleanup_worktree"),
            ):
                rc = await run_daytime(feature)

            result = self._read_result(td, feature)

        self.assertEqual(rc, 1)
        self.assertEqual(result["outcome"], "failed")
        self.assertEqual(result["terminated_via"], "classification")
        self.assertEqual(result["error"], fail_msg)

    # ------------------------------------------------------------------
    # Exception-in-body path (terminated_via="exception")
    # ------------------------------------------------------------------

    async def test_exception_in_body_writes_result_file(self) -> None:
        """execute_feature raises RuntimeError -> outcome="failed",
        terminated_via="exception", error contains "boom"."""
        feature = "feat"

        import tempfile

        with tempfile.TemporaryDirectory() as raw_td:
            td = Path(raw_td)
            self._setup_dirs(td, feature)
            with (
                _CwdCtx(td),
                patch.dict(
                    os.environ,
                    {"DAYTIME_DISPATCH_ID": "a" * 32},
                    clear=False,
                ),
                patch.object(
                    daytime_pipeline,
                    "create_worktree",
                    return_value=self._worktree_info(feature),
                ),
                patch.object(
                    daytime_pipeline,
                    "execute_feature",
                    new=AsyncMock(side_effect=RuntimeError("boom")),
                ),
                patch.object(
                    daytime_pipeline,
                    "apply_feature_result",
                    new=AsyncMock(),
                ),
                patch.object(daytime_pipeline, "cleanup_worktree"),
            ):
                rc = await run_daytime(feature)

            result = self._read_result(td, feature)

        self.assertEqual(rc, 1)
        self.assertEqual(result["outcome"], "failed")
        self.assertEqual(result["terminated_via"], "exception")
        self.assertIsNotNone(result["error"])
        self.assertIn("boom", result["error"])

    # ------------------------------------------------------------------
    # Startup-failure paths (terminated_via="startup_failure")
    # ------------------------------------------------------------------

    async def test_startup_failure_post_094_exception_shape(self) -> None:
        """create_worktree raises ValueError("worktree_creation_failed: stderr") ->
        outcome="failed", terminated_via="startup_failure",
        error contains "worktree_creation_failed". Pins R3 type-robustness."""
        feature = "feat"

        import tempfile

        with tempfile.TemporaryDirectory() as raw_td:
            td = Path(raw_td)
            self._setup_dirs(td, feature)
            with (
                _CwdCtx(td),
                patch.dict(
                    os.environ,
                    {"DAYTIME_DISPATCH_ID": "a" * 32},
                    clear=False,
                ),
                patch.object(
                    daytime_pipeline,
                    "create_worktree",
                    side_effect=ValueError("worktree_creation_failed: stderr text"),
                ),
                patch.object(daytime_pipeline, "cleanup_worktree"),
            ):
                rc = await run_daytime(feature)

            result = self._read_result(td, feature)

        self.assertEqual(rc, 1)
        self.assertEqual(result["outcome"], "failed")
        self.assertEqual(result["terminated_via"], "startup_failure")
        self.assertIsNotNone(result["error"])
        self.assertIn("worktree_creation_failed", result["error"])

    async def test_startup_failure_pre_094_exception_shape(self) -> None:
        """create_worktree raises subprocess.CalledProcessError(returncode=128) ->
        result file still valid with terminated_via="startup_failure".
        Pins R3's type-robustness: except Exception catches both types."""
        feature = "feat"

        import tempfile

        with tempfile.TemporaryDirectory() as raw_td:
            td = Path(raw_td)
            self._setup_dirs(td, feature)
            with (
                _CwdCtx(td),
                patch.dict(
                    os.environ,
                    {"DAYTIME_DISPATCH_ID": "a" * 32},
                    clear=False,
                ),
                patch.object(
                    daytime_pipeline,
                    "create_worktree",
                    side_effect=subprocess.CalledProcessError(
                        returncode=128, cmd=["git"]
                    ),
                ),
                patch.object(daytime_pipeline, "cleanup_worktree"),
            ):
                rc = await run_daytime(feature)

            result = self._read_result(td, feature)

        self.assertEqual(rc, 1)
        self.assertEqual(result["outcome"], "failed")
        self.assertEqual(result["terminated_via"], "startup_failure")
        self.assertIsNotNone(result["error"])
        # CalledProcessError str includes "returned non-zero exit status 128"
        self.assertIn("128", result["error"])
        # Verify the result is valid JSON with all required keys.
        for key in (
            "schema_version",
            "dispatch_id",
            "feature",
            "start_ts",
            "end_ts",
            "outcome",
            "terminated_via",
            "deferred_files",
            "error",
            "pr_url",
        ):
            self.assertIn(key, result)

    async def test_pid_guard_startup_failure(self) -> None:
        """A live PID file causes run_daytime to return 1 with a startup_failure
        result file.

        Per the Task-2 implementation, the PID-guard early-return is INSIDE
        the outer try block, which means _top_exc and _terminated_via are set
        and the outer finally always writes daytime-result.json. The result
        file is therefore expected with terminated_via="startup_failure".
        """
        feature = "feat"

        import tempfile

        with tempfile.TemporaryDirectory() as raw_td:
            td = Path(raw_td)
            self._setup_dirs(td, feature)
            # Write a PID file pointing at the current (live) process.
            pid_path = td / "lifecycle" / feature / "daytime.pid"
            pid_path.write_text(str(os.getpid()), encoding="utf-8")

            with (
                _CwdCtx(td),
                patch.dict(
                    os.environ,
                    {"DAYTIME_DISPATCH_ID": "a" * 32},
                    clear=False,
                ),
            ):
                rc = await run_daytime(feature)

            result = self._read_result(td, feature)

        self.assertEqual(rc, 1)
        # The PID guard runs inside the outer try -> result file is written.
        self.assertEqual(result["outcome"], "failed")
        self.assertEqual(result["terminated_via"], "startup_failure")

    # ------------------------------------------------------------------
    # DAYTIME_DISPATCH_ID env-var validation paths
    # ------------------------------------------------------------------

    async def test_dispatch_id_missing_generates_own_uuid(self) -> None:
        """When DAYTIME_DISPATCH_ID is absent the subprocess generates its own
        32-hex-char dispatch_id, writes a valid result file, and logs a
        warning to stderr."""
        feature = "feat"

        async def _apply(name, result, ctx, **kwargs):
            ctx.batch_result.features_merged.append(name)

        import tempfile

        with tempfile.TemporaryDirectory() as raw_td:
            td = Path(raw_td)
            self._setup_dirs(td, feature)

            stderr_buf = io.StringIO()
            with (
                _CwdCtx(td),
                # Ensure the env var is absent.
                patch.dict(os.environ, {}, clear=False),
            ):
                # Remove DAYTIME_DISPATCH_ID if present.
                os.environ.pop("DAYTIME_DISPATCH_ID", None)

                with (
                    patch.object(
                        daytime_pipeline,
                        "create_worktree",
                        return_value=self._worktree_info(feature),
                    ),
                    patch.object(
                        daytime_pipeline,
                        "execute_feature",
                        new=AsyncMock(
                            return_value=MagicMock(name="feat", status="completed")
                        ),
                    ),
                    patch.object(
                        daytime_pipeline,
                        "apply_feature_result",
                        new=AsyncMock(side_effect=_apply),
                    ),
                    patch.object(daytime_pipeline, "cleanup_worktree"),
                    patch.object(sys, "stderr", stderr_buf),
                ):
                    rc = await run_daytime(feature)

            result = self._read_result(td, feature)

        # Result file must be valid with a well-formed dispatch_id.
        self.assertRegex(result["dispatch_id"], r"^[a-f0-9]{32}$")
        self.assertEqual(result["schema_version"], 1)
        # A warning must have been written to stderr.
        self.assertIn("DAYTIME_DISPATCH_ID", stderr_buf.getvalue())

    async def test_dispatch_id_malformed_generates_own_uuid(self) -> None:
        """When DAYTIME_DISPATCH_ID is malformed the subprocess rejects at
        the validation regex, generates its own uuid4, writes a valid result
        file, and logs a warning to stderr."""
        feature = "feat"

        async def _apply(name, result, ctx, **kwargs):
            ctx.batch_result.features_merged.append(name)

        import tempfile

        with tempfile.TemporaryDirectory() as raw_td:
            td = Path(raw_td)
            self._setup_dirs(td, feature)

            stderr_buf = io.StringIO()
            with (
                _CwdCtx(td),
                patch.dict(
                    os.environ,
                    {"DAYTIME_DISPATCH_ID": "not-a-uuid!"},
                    clear=False,
                ),
                patch.object(
                    daytime_pipeline,
                    "create_worktree",
                    return_value=self._worktree_info(feature),
                ),
                patch.object(
                    daytime_pipeline,
                    "execute_feature",
                    new=AsyncMock(
                        return_value=MagicMock(name="feat", status="completed")
                    ),
                ),
                patch.object(
                    daytime_pipeline,
                    "apply_feature_result",
                    new=AsyncMock(side_effect=_apply),
                ),
                patch.object(daytime_pipeline, "cleanup_worktree"),
                patch.object(sys, "stderr", stderr_buf),
            ):
                rc = await run_daytime(feature)

            result = self._read_result(td, feature)

        # The result file must use the subprocess-generated uuid, not the bad value.
        self.assertRegex(result["dispatch_id"], r"^[a-f0-9]{32}$")
        self.assertNotEqual(result["dispatch_id"], "not-a-uuid!")
        self.assertEqual(result["schema_version"], 1)
        # A warning mentioning the bad value must appear in stderr.
        self.assertIn("DAYTIME_DISPATCH_ID", stderr_buf.getvalue())
        self.assertIn("not-a-uuid!", stderr_buf.getvalue())

    # ------------------------------------------------------------------
    # PR URL optional subtest
    # ------------------------------------------------------------------

    async def test_pr_url_populated_from_daytime_log(self) -> None:
        """When daytime.log contains a GitHub PR URL, pr_url in the result
        file is populated with the first matching URL."""
        feature = "feat"

        async def _apply(name, result, ctx, **kwargs):
            ctx.batch_result.features_merged.append(name)

        import tempfile

        with tempfile.TemporaryDirectory() as raw_td:
            td = Path(raw_td)
            self._setup_dirs(td, feature)

            # Pre-create a daytime.log with a PR URL embedded.
            pr_url = "https://github.com/owner/repo/pull/42"
            log_path = td / "lifecycle" / feature / "daytime.log"
            log_path.write_text(
                f"Some output\nCreated PR: {pr_url}\nMore output\n",
                encoding="utf-8",
            )

            with (
                _CwdCtx(td),
                patch.dict(
                    os.environ,
                    {"DAYTIME_DISPATCH_ID": "a" * 32},
                    clear=False,
                ),
                patch.object(
                    daytime_pipeline,
                    "create_worktree",
                    return_value=self._worktree_info(feature),
                ),
                patch.object(
                    daytime_pipeline,
                    "execute_feature",
                    new=AsyncMock(
                        return_value=MagicMock(name="feat", status="completed")
                    ),
                ),
                patch.object(
                    daytime_pipeline,
                    "apply_feature_result",
                    new=AsyncMock(side_effect=_apply),
                ),
                patch.object(daytime_pipeline, "cleanup_worktree"),
            ):
                rc = await run_daytime(feature)

            result = self._read_result(td, feature)

        self.assertEqual(rc, 0)
        self.assertEqual(result["pr_url"], pr_url)


if __name__ == "__main__":
    unittest.main()
