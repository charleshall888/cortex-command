"""Unit tests for _read_learnings(), _apply_feature_result(), and _effective_merge_repo_path().

Task 3 — TestReadLearnings: 4-branch coverage of _read_learnings().
Task 4 — TestApplyFeatureResult: circuit-breaker counter and status-dispatch
          regression tests using the extracted _apply_feature_result() helper.
Task 5 — TestEffectiveMergeRepoPath: 5-case coverage of worktree resolution,
          plus integration test asserting merge vs cleanup path invariant.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch

import asyncio

import cortex_command.overnight.orchestrator as orchestrator_module
import cortex_command.overnight.feature_executor as feature_executor_module
import cortex_command.overnight.outcome_router as outcome_router_module
from cortex_command.overnight.orchestrator import (
    BatchResult,
    BatchConfig,
)
from cortex_command.overnight.constants import CIRCUIT_BREAKER_THRESHOLD
from cortex_command.overnight.types import CircuitBreakerState, FeatureResult
from cortex_command.overnight.feature_executor import execute_feature
from cortex_command.overnight.outcome_router import (
    OutcomeContext,
    _apply_feature_result,
    _effective_merge_repo_path,
)
from cortex_command.overnight.feature_executor import _read_learnings


def _make_outcome_ctx(
    config,
    batch_result,
    pauses_ref,
    feature_names,
    *,
    worktree_branches=None,
    repo_path=None,
    worktree_path=None,
    integration_worktrees=None,
    integration_branches=None,
    session_id="s1",
    recovery_attempts_map=None,
    backlog_ids=None,
):
    """Build an OutcomeContext for direct _apply_feature_result() call sites.

    Adapter for tests that originally called _apply_feature_result with the
    pre-Task 8 positional-argument signature. Mirrors the context constructed
    by batch_runner's _accumulate_result shim.
    """
    name = feature_names[0] if feature_names else None
    repo_path_map = {name: repo_path} if name is not None else {}
    worktree_paths = {name: worktree_path} if (name is not None and worktree_path is not None) else {}
    if isinstance(pauses_ref, CircuitBreakerState):
        cb_state_arg = pauses_ref
    elif isinstance(pauses_ref, list):
        cb_state_arg = CircuitBreakerState(consecutive_pauses=pauses_ref[0])
    else:
        cb_state_arg = CircuitBreakerState(consecutive_pauses=int(pauses_ref))
    return OutcomeContext(
        batch_result=batch_result,
        lock=asyncio.Lock(),
        cb_state=cb_state_arg,
        recovery_attempts_map=recovery_attempts_map if recovery_attempts_map is not None else {},
        worktree_paths=worktree_paths,
        worktree_branches=worktree_branches if worktree_branches is not None else {},
        repo_path_map=repo_path_map,
        integration_worktrees=integration_worktrees if integration_worktrees is not None else {},
        integration_branches=integration_branches if integration_branches is not None else {},
        session_id=session_id,
        backlog_ids=backlog_ids if backlog_ids is not None else {},
        feature_names=list(feature_names),
        config=config,
    )
from cortex_command.overnight.events import (
    FEATURE_COMPLETE,
    FEATURE_DEFERRED,
    FEATURE_FAILED,
    FEATURE_PAUSED,
    REPAIR_AGENT_RESOLVED,
)
from cortex_command.pipeline.parser import FeaturePlan, FeatureTask
from cortex_command.pipeline.retry import RetryResult


# ---------------------------------------------------------------------------
# Task 3: _read_learnings() — 4 branch coverage
# ---------------------------------------------------------------------------


class TestReadLearnings(unittest.TestCase):
    """Tests for _read_learnings() — both-absent, progress-only, note-only, both."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._orig_cwd = os.getcwd()
        os.chdir(self._tmpdir.name)

    def tearDown(self):
        os.chdir(self._orig_cwd)
        self._tmpdir.cleanup()

    def _make_learnings_dir(self, feature: str = "feat-a") -> Path:
        d = Path(f"lifecycle/{feature}/learnings")
        d.mkdir(parents=True, exist_ok=True)
        return d

    def test_neither_file_present(self):
        result = _read_learnings("feat-a")
        self.assertEqual(result, "(No prior learnings.)")

    def test_only_progress_txt(self):
        d = self._make_learnings_dir()
        (d / "progress.txt").write_text("Prior attempt notes.", encoding="utf-8")
        result = _read_learnings("feat-a")
        self.assertEqual(result, "Prior attempt notes.")

    def test_only_orchestrator_note(self):
        d = self._make_learnings_dir()
        (d / "orchestrator-note.md").write_text("Orchestrator insight.", encoding="utf-8")
        result = _read_learnings("feat-a")
        self.assertEqual(result, "## Orchestrator Note\nOrchestrator insight.")

    def test_both_files_present(self):
        d = self._make_learnings_dir()
        (d / "progress.txt").write_text("Task progress.", encoding="utf-8")
        (d / "orchestrator-note.md").write_text("Key insight.", encoding="utf-8")
        result = _read_learnings("feat-a")
        self.assertEqual(result, "Task progress.\n\n## Orchestrator Note\nKey insight.")


# ---------------------------------------------------------------------------
# Task 4: _apply_feature_result() — circuit-breaker regression tests
# ---------------------------------------------------------------------------


class TestApplyFeatureResult(unittest.TestCase):
    """Circuit-breaker counter and status-dispatch regression tests."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        tmp = self._tmpdir.name
        self._config = BatchConfig(
            batch_id=1,
            plan_path=Path(tmp) / "plan.md",
            overnight_events_path=Path(tmp) / "overnight.log",
            pipeline_events_path=Path(tmp) / "pipeline.log",
        )

    def tearDown(self):
        self._tmpdir.cleanup()

    def _call(self, name, status, batch_result, pauses_ref, **result_kwargs):
        """Helper: call _apply_feature_result with standard mocks."""
        result = FeatureResult(name=name, status=status, **result_kwargs)
        ctx = _make_outcome_ctx(self._config, batch_result, pauses_ref, [name])
        _apply_feature_result(name, result, ctx)

    def test_three_deferred_no_circuit_breaker(self):
        """Deferred results do not increment the pause counter."""
        batch = BatchResult(batch_id=1)
        cb_state = CircuitBreakerState()
        with (
            patch.object(outcome_router_module, "_write_back_to_backlog"),
            patch.object(orchestrator_module, "overnight_log_event"),
        ):
            self._call("feat-a", "deferred", batch, cb_state, deferred_question_count=1)
            self._call("feat-b", "deferred", batch, cb_state, deferred_question_count=1)
            self._call("feat-c", "deferred", batch, cb_state, deferred_question_count=1)

        self.assertFalse(batch.circuit_breaker_fired)
        self.assertEqual(cb_state.consecutive_pauses, 0)
        self.assertEqual(len(batch.features_deferred), 3)

    def test_three_paused_fires_circuit_breaker(self):
        """Three consecutive paused results trip the circuit breaker."""
        batch = BatchResult(batch_id=1)
        cb_state = CircuitBreakerState()
        with (
            patch.object(outcome_router_module, "_write_back_to_backlog"),
            patch.object(orchestrator_module, "overnight_log_event"),
        ):
            self._call("feat-a", "paused", batch, cb_state, error="task failed")
            self._call("feat-b", "paused", batch, cb_state, error="task failed")
            self._call("feat-c", "paused", batch, cb_state, error="task failed")

        self.assertTrue(batch.circuit_breaker_fired)
        self.assertEqual(cb_state.consecutive_pauses, 3)

    def test_two_paused_one_deferred_no_circuit_breaker(self):
        """Two paused then one deferred: counter stays at 2, no breaker."""
        batch = BatchResult(batch_id=1)
        cb_state = CircuitBreakerState()
        with (
            patch.object(outcome_router_module, "_write_back_to_backlog"),
            patch.object(orchestrator_module, "overnight_log_event"),
        ):
            self._call("feat-a", "paused", batch, cb_state, error="fail")
            self._call("feat-b", "paused", batch, cb_state, error="fail")
            self._call("feat-c", "deferred", batch, cb_state, deferred_question_count=1)

        self.assertFalse(batch.circuit_breaker_fired)
        self.assertEqual(cb_state.consecutive_pauses, 2)

    def test_one_failed_increments_counter(self):
        """Failed result increments the consecutive-pause counter."""
        batch = BatchResult(batch_id=1)
        cb_state = CircuitBreakerState()
        with (
            patch.object(outcome_router_module, "_write_back_to_backlog"),
            patch.object(orchestrator_module, "overnight_log_event"),
        ):
            self._call("feat-a", "failed", batch, cb_state, error="error msg")

        self.assertFalse(batch.circuit_breaker_fired)
        self.assertEqual(cb_state.consecutive_pauses, 1)
        self.assertEqual(len(batch.features_failed), 1)

    def test_completed_no_files_increments_counter(self):
        """Completed with no changed files falls into the paused guard path."""
        batch = BatchResult(batch_id=1)
        cb_state = CircuitBreakerState()
        with (
            patch.object(outcome_router_module, "_write_back_to_backlog"),
            patch.object(orchestrator_module, "overnight_log_event"),
            patch.object(outcome_router_module, "_get_changed_files", return_value=[]),
            patch.object(outcome_router_module, "merge_feature"),
        ):
            self._call("feat-a", "completed", batch, cb_state)

        self.assertFalse(batch.circuit_breaker_fired)
        self.assertEqual(cb_state.consecutive_pauses, 1)
        self.assertEqual(len(batch.features_paused), 1)

    def test_completed_with_suffixed_branch_uses_actual_branch(self):
        """_get_changed_files is called with the actual suffixed branch when worktree_branches is set."""
        batch = BatchResult(batch_id=1)
        cb_state = CircuitBreakerState()
        worktree_branches = {"feat-a": "pipeline/feat-a-2"}
        with (
            patch.object(outcome_router_module, "_write_back_to_backlog"),
            patch.object(orchestrator_module, "overnight_log_event"),
            patch.object(outcome_router_module, "_get_changed_files", return_value=["some/file.py"]) as mock_gcf,
            patch.object(outcome_router_module, "merge_feature") as mock_merge,
        ):
            result = FeatureResult(name="feat-a", status="completed")
            ctx = _make_outcome_ctx(
                self._config, batch, cb_state, ["feat-a"],
                worktree_branches=worktree_branches,
            )
            _apply_feature_result("feat-a", result, ctx)

        mock_gcf.assert_called_once_with("feat-a", self._config.base_branch, branch="pipeline/feat-a-2")
        mock_merge.assert_called_once()
        merge_kwargs = mock_merge.call_args.kwargs
        self.assertEqual(merge_kwargs.get("branch"), "pipeline/feat-a-2")
        self.assertEqual(cb_state.consecutive_pauses, 0)

    def test_completed_suffixed_branch_no_commits_fires_guard(self):
        """No-commit guard fires correctly when the suffixed branch has no new commits."""
        batch = BatchResult(batch_id=1)
        cb_state = CircuitBreakerState()
        worktree_branches = {"feat-a": "pipeline/feat-a-2"}
        with (
            patch.object(outcome_router_module, "_write_back_to_backlog"),
            patch.object(orchestrator_module, "overnight_log_event"),
            patch.object(outcome_router_module, "_get_changed_files", return_value=[]) as mock_gcf,
            patch.object(outcome_router_module, "merge_feature"),
        ):
            result = FeatureResult(name="feat-a", status="completed")
            ctx = _make_outcome_ctx(
                self._config, batch, cb_state, ["feat-a"],
                worktree_branches=worktree_branches,
            )
            _apply_feature_result("feat-a", result, ctx)

        mock_gcf.assert_called_once_with("feat-a", self._config.base_branch, branch="pipeline/feat-a-2")
        self.assertEqual(cb_state.consecutive_pauses, 1)
        self.assertEqual(len(batch.features_paused), 1)
        # Error message should reference the actual branch
        error_msg = batch.features_paused[0]["error"]
        self.assertIn("pipeline/feat-a-2", error_msg)

    def test_parse_errors_do_not_increment_counter(self):
        """Five consecutive failed results with parse_error=True leave counter at 0."""
        batch = BatchResult(batch_id=1)
        cb_state = CircuitBreakerState()
        with (
            patch.object(outcome_router_module, "_write_back_to_backlog"),
            patch.object(orchestrator_module, "overnight_log_event"),
        ):
            for i in range(5):
                self._call(f"feat-{i}", "failed", batch, cb_state,
                           error="parse error", parse_error=True)

        self.assertFalse(batch.circuit_breaker_fired)
        self.assertEqual(cb_state.consecutive_pauses, 0)
        self.assertEqual(len(batch.features_failed), 5)

    def test_parse_error_then_operational_failure_increments_once(self):
        """A parse_error failure followed by a paused failure increments counter to 1."""
        batch = BatchResult(batch_id=1)
        cb_state = CircuitBreakerState()
        with (
            patch.object(outcome_router_module, "_write_back_to_backlog"),
            patch.object(orchestrator_module, "overnight_log_event"),
        ):
            self._call("feat-a", "failed", batch, cb_state,
                        error="parse error", parse_error=True)
            self._call("feat-b", "paused", batch, cb_state,
                        error="task failed")

        self.assertFalse(batch.circuit_breaker_fired)
        self.assertEqual(cb_state.consecutive_pauses, 1)
        self.assertEqual(len(batch.features_failed), 1)
        self.assertEqual(len(batch.features_paused), 1)

    def test_failed_with_parse_error_false_increments_counter(self):
        """Failed result with parse_error=False (default) increments the counter."""
        batch = BatchResult(batch_id=1)
        cb_state = CircuitBreakerState()
        with (
            patch.object(outcome_router_module, "_write_back_to_backlog"),
            patch.object(orchestrator_module, "overnight_log_event"),
        ):
            self._call("feat-a", "failed", batch, cb_state, error="error msg",
                        parse_error=False)

        self.assertFalse(batch.circuit_breaker_fired)
        self.assertEqual(cb_state.consecutive_pauses, 1)
        self.assertEqual(len(batch.features_failed), 1)


# ---------------------------------------------------------------------------
# TestRecoveryGate: recovery_attempts >= 1 prevents recover_test_failure call
# ---------------------------------------------------------------------------


class TestRecoveryDispatchPersistence(unittest.IsolatedAsyncioTestCase):
    """Task 6 acceptance: recovery_attempts is incremented and persisted
    in the state file inside the lock scope when the recovery path fires."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmpdir.cleanup()

    async def test_recovery_attempts_persisted_per_feature(self):
        """Triggering test-failure recovery increments and persists
        recovery_attempts=1 in the on-disk state file."""
        from cortex_command.overnight.orchestrator import run_batch
        from cortex_command.overnight.types import FeatureResult
        from cortex_command.overnight.state import (
            OvernightState,
            OvernightFeatureStatus,
            save_state,
            load_state,
        )
        from cortex_command.pipeline.merge import MergeResult, TestResult
        from cortex_command.pipeline.merge_recovery import MergeRecoveryResult

        feat_name = "feat-persist-test"
        tmp = self._tmpdir.name
        state_path = Path(tmp) / "overnight-state.json"

        # Write real state file with recovery_attempts=0
        initial_state = OvernightState(
            session_id="s-persist",
            plan_ref="plan.md",
            features={feat_name: OvernightFeatureStatus(recovery_attempts=0)},
        )
        save_state(initial_state, state_path)

        mock_feature = MagicMock()
        mock_feature.name = feat_name
        mock_plan = MagicMock()
        mock_plan.features = [mock_feature]

        mock_worktree = MagicMock()
        mock_worktree.path = Path(tmp) / "wt"
        mock_worktree.branch = f"pipeline/{feat_name}"

        mock_manager = MagicMock()
        mock_manager.acquire = AsyncMock()
        mock_manager.release = MagicMock()
        mock_manager.stats = {}

        # A test failure result (not conflict, not CI error)
        test_failure = MergeResult(
            success=False,
            feature=feat_name,
            conflict=False,
            test_result=TestResult(passed=False, output="FAILED", return_code=1),
            error="Tests failed (exit code 1)",
        )

        # Recovery returns success so the batch finishes cleanly
        recovery_ok = MergeRecoveryResult(
            success=True,
            attempts=1,
            paused=False,
            flaky=False,
            error=None,
        )

        config = BatchConfig(
            batch_id=1,
            plan_path=Path(tmp) / "plan.md",
            result_dir=Path(tmp),
            overnight_state_path=state_path,
            overnight_events_path=Path(tmp) / "overnight.log",
            pipeline_events_path=Path(tmp) / "pipeline.log",
        )

        with (
            patch.object(orchestrator_module, "parse_master_plan", return_value=mock_plan),
            patch.object(orchestrator_module, "create_worktree", return_value=mock_worktree),
            patch.object(orchestrator_module, "load_throttle_config", return_value=MagicMock()),
            patch.object(orchestrator_module, "ConcurrencyManager", return_value=mock_manager),
            patch.object(
                orchestrator_module, "execute_feature",
                new_callable=AsyncMock,
                return_value=FeatureResult(name=feat_name, status="completed"),
            ),
            patch.object(outcome_router_module, "_get_changed_files", return_value=["src/foo.py"]),
            patch.object(outcome_router_module, "merge_feature", return_value=test_failure),
            patch.object(orchestrator_module, "overnight_log_event"),
            patch.object(outcome_router_module, "_write_back_to_backlog"),
            patch.object(outcome_router_module, "cleanup_worktree"),
            patch.object(
                outcome_router_module, "recover_test_failure",
                new_callable=AsyncMock,
                return_value=recovery_ok,
            ) as mock_recover,
        ):
            await run_batch(config)

        # Recovery was called (gate passed because recovery_attempts was 0)
        mock_recover.assert_called_once()

        # Read the persisted state file — recovery_attempts must be 1
        persisted = load_state(state_path)
        fs = persisted.features.get(feat_name)
        if fs is None:
            self.fail(f"{feat_name} not found in persisted state")
        self.assertEqual(
            fs.recovery_attempts, 1,
            f"expected recovery_attempts=1 persisted on disk, got {fs.recovery_attempts}",
        )


class TestRecoveryGate(unittest.IsolatedAsyncioTestCase):
    """When recovery_attempts_map[name] >= 1, recover_test_failure is not called."""

    async def test_gate_blocks_recovery_when_exhausted(self):
        """Feature with recovery_attempts=1 in state falls through to paused without calling recovery."""
        from cortex_command.overnight.orchestrator import run_batch
        from cortex_command.overnight.types import FeatureResult
        from cortex_command.overnight.state import OvernightState, OvernightFeatureStatus
        from cortex_command.pipeline.merge import MergeResult, TestResult

        feat_name = "feat-gate-test"

        mock_state = OvernightState(
            session_id="s1",
            plan_ref="plan.md",
            features={feat_name: OvernightFeatureStatus(recovery_attempts=1)},
        )

        mock_feature = MagicMock()
        mock_feature.name = feat_name
        mock_plan = MagicMock()
        mock_plan.features = [mock_feature]

        mock_worktree = MagicMock()
        mock_worktree.path = Path(self._tmpdir.name) / "wt"
        mock_worktree.branch = f"pipeline/{feat_name}"

        mock_manager = MagicMock()
        mock_manager.acquire = AsyncMock()
        mock_manager.release = MagicMock()
        mock_manager.stats = {}

        test_failure = MergeResult(
            success=False,
            feature=feat_name,
            conflict=False,
            test_result=TestResult(passed=False, output="FAILED", return_code=1),
            error="Tests failed (exit code 1)",
        )

        config = BatchConfig(
            batch_id=1,
            plan_path=Path(self._tmpdir.name) / "plan.md",
            result_dir=Path(self._tmpdir.name),
            overnight_events_path=Path(self._tmpdir.name) / "overnight.log",
            pipeline_events_path=Path(self._tmpdir.name) / "pipeline.log",
        )

        with (
            patch.object(orchestrator_module, "parse_master_plan", return_value=mock_plan),
            patch.object(orchestrator_module, "load_state", return_value=mock_state),
            patch.object(orchestrator_module, "save_state"),
            patch.object(orchestrator_module, "create_worktree", return_value=mock_worktree),
            patch.object(orchestrator_module, "load_throttle_config", return_value=MagicMock()),
            patch.object(orchestrator_module, "ConcurrencyManager", return_value=mock_manager),
            patch.object(
                orchestrator_module, "execute_feature",
                new_callable=AsyncMock,
                return_value=FeatureResult(name=feat_name, status="completed"),
            ),
            patch.object(outcome_router_module, "_get_changed_files", return_value=["src/foo.py"]),
            patch.object(outcome_router_module, "merge_feature", return_value=test_failure),
            patch.object(outcome_router_module, "_apply_feature_result"),
            patch.object(orchestrator_module, "overnight_log_event"),
            patch.object(
                outcome_router_module, "recover_test_failure",
                new_callable=AsyncMock,
            ) as mock_recover,
        ):
            await run_batch(config)

        mock_recover.assert_not_called()

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmpdir.cleanup()


# ---------------------------------------------------------------------------
# Task 8: Budget exhaustion signal — BatchResult defaults and independence
# ---------------------------------------------------------------------------


class TestBudgetExhaustionSignal(unittest.TestCase):
    """Tests for global_abort_signal / abort_reason fields and their interaction
    with _apply_feature_result and circuit_breaker_fired."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        tmp = self._tmpdir.name
        self._config = BatchConfig(
            batch_id=1,
            plan_path=Path(tmp) / "plan.md",
            overnight_events_path=Path(tmp) / "overnight.log",
            pipeline_events_path=Path(tmp) / "pipeline.log",
        )

    def tearDown(self):
        self._tmpdir.cleanup()

    def _call(self, name, status, batch_result, pauses_ref, **result_kwargs):
        """Helper: call _apply_feature_result with standard mocks."""
        result = FeatureResult(name=name, status=status, **result_kwargs)
        ctx = _make_outcome_ctx(self._config, batch_result, pauses_ref, [name])
        _apply_feature_result(name, result, ctx)

    # (b) BatchResult default values for the two new fields
    def test_batch_result_defaults(self):
        """BatchResult defaults global_abort_signal=False, abort_reason=None."""
        batch = BatchResult(batch_id=1)
        self.assertFalse(batch.global_abort_signal)
        self.assertIsNone(batch.abort_reason)

    # (a) _apply_feature_result with budget_exhausted paused records in
    #     features_paused but does NOT set global_abort_signal
    def test_apply_budget_exhausted_records_pause_not_signal(self):
        """Paused/budget_exhausted via _apply_feature_result lands in
        features_paused without setting global_abort_signal (that is
        _accumulate_result's responsibility)."""
        batch = BatchResult(batch_id=1)
        pauses = 0
        with (
            patch.object(outcome_router_module, "_write_back_to_backlog"),
            patch.object(orchestrator_module, "overnight_log_event"),
        ):
            self._call("feat-budget", "paused", batch, pauses,
                        error="budget_exhausted")

        # Feature is recorded in the paused list
        self.assertEqual(len(batch.features_paused), 1)
        self.assertEqual(batch.features_paused[0]["name"], "feat-budget")
        self.assertEqual(batch.features_paused[0]["error"], "budget_exhausted")
        # global_abort_signal is NOT set by _apply_feature_result
        self.assertFalse(batch.global_abort_signal)
        self.assertIsNone(batch.abort_reason)

    # (c) global_abort_signal is independent of circuit_breaker_fired
    def test_global_abort_independent_of_circuit_breaker(self):
        """global_abort_signal and circuit_breaker_fired are independent flags."""
        # abort without circuit breaker
        batch_abort_only = BatchResult(batch_id=1)
        batch_abort_only.global_abort_signal = True
        batch_abort_only.abort_reason = "budget_exhausted"
        self.assertTrue(batch_abort_only.global_abort_signal)
        self.assertFalse(batch_abort_only.circuit_breaker_fired)

        # circuit breaker without abort
        batch_cb_only = BatchResult(batch_id=1)
        batch_cb_only.circuit_breaker_fired = True
        self.assertTrue(batch_cb_only.circuit_breaker_fired)
        self.assertFalse(batch_cb_only.global_abort_signal)
        self.assertIsNone(batch_cb_only.abort_reason)

        # both set simultaneously
        batch_both = BatchResult(batch_id=1)
        batch_both.global_abort_signal = True
        batch_both.abort_reason = "budget_exhausted"
        batch_both.circuit_breaker_fired = True
        self.assertTrue(batch_both.global_abort_signal)
        self.assertTrue(batch_both.circuit_breaker_fired)


# ---------------------------------------------------------------------------
# Task 5: _effective_merge_repo_path() — worktree resolution logic
# ---------------------------------------------------------------------------


class TestEffectiveMergeRepoPath(unittest.TestCase):
    """Tests for _effective_merge_repo_path() — 5 resolution cases."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._tmp = Path(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_repo_path_none_returns_none(self):
        """When repo_path is None, return None (default-repo case)."""
        result = _effective_merge_repo_path(
            repo_path=None,
            integration_worktrees={},
            integration_branches={},
            session_id="s1",
        )
        self.assertIsNone(result)

    def test_cached_hit_returns_worktree_path(self):
        """Key in integration_worktrees and path exists on disk returns the worktree path."""
        repo_path = self._tmp / "my-repo"
        repo_path.mkdir()
        worktree_dir = self._tmp / "worktrees" / "my-repo-wt"
        worktree_dir.mkdir(parents=True)

        # _normalize_repo_key resolves the path, so use the resolved string as key
        key = str(repo_path.resolve())
        integration_worktrees = {key: str(worktree_dir)}

        result = _effective_merge_repo_path(
            repo_path=repo_path,
            integration_worktrees=integration_worktrees,
            integration_branches={},
            session_id="s1",
        )
        self.assertEqual(result, worktree_dir)

    def test_lazy_creation_when_key_in_integration_branches(self):
        """Key absent from worktrees but present in integration_branches triggers lazy creation."""
        repo_path = self._tmp / "my-repo"
        repo_path.mkdir()
        key = str(repo_path.resolve())
        integration_worktrees: dict[str, str] = {}
        integration_branches = {key: "integration/main"}

        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch.object(subprocess, "run", return_value=mock_result) as mock_run:
            result = _effective_merge_repo_path(
                repo_path=repo_path,
                integration_worktrees=integration_worktrees,
                integration_branches=integration_branches,
                session_id="s1",
            )

        # subprocess.run was called at least once for git worktree add
        mock_run.assert_called()
        first_call_args = mock_run.call_args_list[0]
        self.assertIn("worktree", first_call_args[0][0])
        self.assertIn("add", first_call_args[0][0])

        # Result is a Path and the worktree was cached
        self.assertIsInstance(result, Path)
        self.assertIn(key, integration_worktrees)

    def test_already_exists_returns_existing_path(self):
        """git worktree add returning 128 with 'already exists' returns the existing path."""
        repo_path = self._tmp / "my-repo"
        repo_path.mkdir()
        key = str(repo_path.resolve())
        integration_worktrees: dict[str, str] = {}
        integration_branches = {key: "integration/main"}

        mock_result = MagicMock()
        mock_result.returncode = 128
        mock_result.stderr = "fatal: '/tmp/overnight-worktrees/s1-lazy-my-repo' already exists"

        with patch.object(subprocess, "run", return_value=mock_result) as mock_run:
            # The worktree path must actually exist on disk for the fallback
            tmpdir_env = os.environ.get("TMPDIR", "/tmp")
            worktree_path = Path(tmpdir_env) / "overnight-worktrees" / "s1-lazy-my-repo"
            worktree_path.mkdir(parents=True, exist_ok=True)
            try:
                result = _effective_merge_repo_path(
                    repo_path=repo_path,
                    integration_worktrees=integration_worktrees,
                    integration_branches=integration_branches,
                    session_id="s1",
                )
                self.assertEqual(result, worktree_path)
            finally:
                # Clean up the created directory
                import shutil
                shutil.rmtree(worktree_path.parent, ignore_errors=True)

    def test_key_absent_from_both_raises_runtime_error(self):
        """Key absent from both integration_worktrees and integration_branches raises RuntimeError."""
        repo_path = self._tmp / "my-repo"
        repo_path.mkdir()

        with self.assertRaises(RuntimeError) as ctx:
            _effective_merge_repo_path(
                repo_path=repo_path,
                integration_worktrees={},
                integration_branches={},
                session_id="s1",
            )
        self.assertIn("No integration branch configured", str(ctx.exception))


# ---------------------------------------------------------------------------
# Task 5: _apply_feature_result integration — merge gets worktree path,
#          cleanup gets live path
# ---------------------------------------------------------------------------


class TestApplyFeatureResultWorktreePaths(unittest.TestCase):
    """Verify that merge_feature receives the integration worktree path
    while cleanup_worktree receives the live repo path."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        tmp = self._tmpdir.name
        self._config = BatchConfig(
            batch_id=1,
            plan_path=Path(tmp) / "plan.md",
            overnight_events_path=Path(tmp) / "overnight.log",
            pipeline_events_path=Path(tmp) / "pipeline.log",
        )

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_merge_receives_worktree_path_cleanup_receives_live_path(self):
        """Completed feature: merge_feature gets the integration worktree path,
        cleanup_worktree gets the original live repo path."""
        from cortex_command.pipeline.merge import MergeResult

        live_repo = Path(self._tmpdir.name) / "live-repo"
        live_repo.mkdir()
        worktree_dir = Path(self._tmpdir.name) / "worktree-repo"
        worktree_dir.mkdir()
        worktree_path_for_cleanup = Path(self._tmpdir.name) / "feat-wt"
        worktree_path_for_cleanup.mkdir()

        key = str(live_repo.resolve())
        integration_worktrees = {key: str(worktree_dir)}
        integration_branches = {key: "integration/main"}

        merge_result = MergeResult(
            success=True,
            feature="feat-a",
            conflict=False,
        )

        batch = BatchResult(batch_id=1)
        pauses = 0

        with (
            patch.object(outcome_router_module, "_write_back_to_backlog"),
            patch.object(orchestrator_module, "overnight_log_event"),
            patch.object(outcome_router_module, "_get_changed_files", return_value=["src/foo.py"]),
            patch.object(outcome_router_module, "merge_feature", return_value=merge_result) as mock_merge,
            patch.object(outcome_router_module, "cleanup_worktree") as mock_cleanup,
        ):
            result = FeatureResult(name="feat-a", status="completed")
            ctx = _make_outcome_ctx(
                self._config, batch, pauses, ["feat-a"],
                repo_path=live_repo,
                worktree_path=worktree_path_for_cleanup,
                integration_worktrees=integration_worktrees,
                integration_branches=integration_branches,
                session_id="s1",
            )
            _apply_feature_result("feat-a", result, ctx)

        # merge_feature must receive the worktree path (not the live repo)
        mock_merge.assert_called_once()
        merge_kwargs = mock_merge.call_args.kwargs
        self.assertEqual(merge_kwargs["repo_path"], worktree_dir)

        # cleanup_worktree must receive the live repo path (not the worktree)
        mock_cleanup.assert_called_once()
        cleanup_kwargs = mock_cleanup.call_args.kwargs
        self.assertEqual(cleanup_kwargs["repo_path"], live_repo)


# ---------------------------------------------------------------------------
# Task 3 (R4): TestApplyFeatureResultVariants — per-status dispatch coverage
# ---------------------------------------------------------------------------


class TestApplyFeatureResultVariants(unittest.TestCase):
    """One test per status variant asserting BatchResult population and the
    matching overnight_log_event constant fires."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        tmp = self._tmpdir.name
        self._config = BatchConfig(
            batch_id=1,
            plan_path=Path(tmp) / "plan.md",
            overnight_events_path=Path(tmp) / "overnight.log",
            pipeline_events_path=Path(tmp) / "pipeline.log",
        )

    def tearDown(self):
        self._tmpdir.cleanup()

    def _event_constants(self, mock_log_event) -> list[str]:
        return [c.args[0] for c in mock_log_event.call_args_list]

    def test_completed_with_files_populates_features_merged(self):
        """completed + non-empty changed files + merge success → features_merged,
        FEATURE_COMPLETE event fires."""
        from cortex_command.pipeline.merge import MergeResult

        batch = BatchResult(batch_id=1)
        pauses = 0
        merge_result = MergeResult(success=True, feature="feat-a", conflict=False)
        with (
            patch.object(outcome_router_module, "_write_back_to_backlog"),
            patch.object(outcome_router_module, "overnight_log_event") as mock_log,
            patch.object(outcome_router_module, "_get_changed_files", return_value=["src/foo.py"]),
            patch.object(outcome_router_module, "merge_feature", return_value=merge_result),
            patch.object(outcome_router_module, "cleanup_worktree"),
        ):
            result = FeatureResult(name="feat-a", status="completed")
            ctx = _make_outcome_ctx(self._config, batch, pauses, ["feat-a"])
            _apply_feature_result("feat-a", result, ctx)

        self.assertEqual(batch.features_merged, ["feat-a"])
        self.assertIn(FEATURE_COMPLETE, self._event_constants(mock_log))

    def test_failed_populates_features_failed(self):
        """failed → features_failed, FEATURE_FAILED event fires."""
        batch = BatchResult(batch_id=1)
        pauses = 0
        with (
            patch.object(outcome_router_module, "_write_back_to_backlog"),
            patch.object(outcome_router_module, "overnight_log_event") as mock_log,
        ):
            result = FeatureResult(name="feat-a", status="failed", error="boom")
            ctx = _make_outcome_ctx(self._config, batch, pauses, ["feat-a"])
            _apply_feature_result("feat-a", result, ctx)

        self.assertEqual(len(batch.features_failed), 1)
        self.assertEqual(batch.features_failed[0]["name"], "feat-a")
        self.assertIn(FEATURE_FAILED, self._event_constants(mock_log))

    def test_paused_populates_features_paused(self):
        """paused → features_paused, FEATURE_PAUSED event fires."""
        batch = BatchResult(batch_id=1)
        pauses = 0
        with (
            patch.object(outcome_router_module, "_write_back_to_backlog"),
            patch.object(outcome_router_module, "overnight_log_event") as mock_log,
        ):
            result = FeatureResult(name="feat-a", status="paused", error="task paused")
            ctx = _make_outcome_ctx(self._config, batch, pauses, ["feat-a"])
            _apply_feature_result("feat-a", result, ctx)

        self.assertEqual(len(batch.features_paused), 1)
        self.assertEqual(batch.features_paused[0]["name"], "feat-a")
        self.assertIn(FEATURE_PAUSED, self._event_constants(mock_log))

    def test_deferred_populates_features_deferred(self):
        """deferred → features_deferred, FEATURE_DEFERRED event fires."""
        batch = BatchResult(batch_id=1)
        pauses = 0
        with (
            patch.object(outcome_router_module, "_write_back_to_backlog"),
            patch.object(outcome_router_module, "overnight_log_event") as mock_log,
        ):
            result = FeatureResult(name="feat-a", status="deferred", deferred_question_count=2)
            ctx = _make_outcome_ctx(self._config, batch, pauses, ["feat-a"])
            _apply_feature_result("feat-a", result, ctx)

        self.assertEqual(len(batch.features_deferred), 1)
        self.assertEqual(batch.features_deferred[0]["name"], "feat-a")
        self.assertIn(FEATURE_DEFERRED, self._event_constants(mock_log))

    def test_repair_completed_populates_features_merged(self):
        """repair_completed + ff-merge success → features_merged,
        REPAIR_AGENT_RESOLVED event fires."""
        batch = BatchResult(batch_id=1)
        pauses = 0
        ff_ok = MagicMock(returncode=0, stdout="", stderr="")
        with (
            patch.object(outcome_router_module, "_write_back_to_backlog"),
            patch.object(outcome_router_module, "overnight_log_event") as mock_log,
            patch.object(subprocess, "run", return_value=ff_ok),
            patch.object(outcome_router_module, "cleanup_worktree"),
        ):
            result = FeatureResult(name="feat-a", status="repair_completed")
            result.repair_branch = "repair/feat-a"
            result.trivial_resolved = False
            ctx = _make_outcome_ctx(self._config, batch, pauses, ["feat-a"])
            _apply_feature_result("feat-a", result, ctx)

        self.assertEqual(batch.features_merged, ["feat-a"])
        self.assertIn(REPAIR_AGENT_RESOLVED, self._event_constants(mock_log))


# ---------------------------------------------------------------------------
# Task 3 (R5): TestConsecutivePausesSequence — counter increment/reset
# ---------------------------------------------------------------------------


class TestConsecutivePausesSequence(unittest.TestCase):
    """Drive alternating pause/non-pause sequences through _apply_feature_result
    and verify consecutive_pauses_ref increments on pause, resets on a
    successful merge, and fires the circuit breaker at threshold."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        tmp = self._tmpdir.name
        self._config = BatchConfig(
            batch_id=1,
            plan_path=Path(tmp) / "plan.md",
            overnight_events_path=Path(tmp) / "overnight.log",
            pipeline_events_path=Path(tmp) / "pipeline.log",
        )

    def tearDown(self):
        self._tmpdir.cleanup()

    def _call(self, name, status, batch_result, pauses_ref, **result_kwargs):
        """Helper: call _apply_feature_result with standard mocks (non-merge paths)."""
        result = FeatureResult(name=name, status=status, **result_kwargs)
        ctx = _make_outcome_ctx(self._config, batch_result, pauses_ref, [name])
        _apply_feature_result(name, result, ctx)

    def _call_completed_success(self, name, batch_result, pauses_ref):
        """Helper: drive a completed + successful merge through _apply_feature_result."""
        from cortex_command.pipeline.merge import MergeResult

        merge_result = MergeResult(success=True, feature=name, conflict=False)
        with (
            patch.object(outcome_router_module, "_write_back_to_backlog"),
            patch.object(outcome_router_module, "overnight_log_event"),
            patch.object(outcome_router_module, "_get_changed_files", return_value=["src/foo.py"]),
            patch.object(outcome_router_module, "merge_feature", return_value=merge_result),
            patch.object(outcome_router_module, "cleanup_worktree"),
        ):
            result = FeatureResult(name=name, status="completed")
            ctx = _make_outcome_ctx(self._config, batch_result, pauses_ref, [name])
            _apply_feature_result(name, result, ctx)

    def test_pause_then_merge_resets_counter(self):
        """pause increments consecutive_pauses to 1; successful merge
        resets consecutive_pauses back to 0."""
        batch = BatchResult(batch_id=1)
        cb_state = CircuitBreakerState()

        with (
            patch.object(outcome_router_module, "_write_back_to_backlog"),
            patch.object(orchestrator_module, "overnight_log_event"),
        ):
            self._call("feat-a", "paused", batch, cb_state, error="fail")
        self.assertEqual(cb_state.consecutive_pauses, 1)

        self._call_completed_success("feat-b", batch, cb_state)
        self.assertEqual(cb_state.consecutive_pauses, 0)
        self.assertFalse(batch.circuit_breaker_fired)

    def test_pause_merge_pause_sequence(self):
        """pause / merge / pause drives consecutive_pauses 1 → 0 → 1
        with no circuit breaker."""
        batch = BatchResult(batch_id=1)
        cb_state = CircuitBreakerState()

        with (
            patch.object(outcome_router_module, "_write_back_to_backlog"),
            patch.object(orchestrator_module, "overnight_log_event"),
        ):
            self._call("feat-a", "paused", batch, cb_state, error="fail")
        self.assertEqual(cb_state.consecutive_pauses, 1)

        self._call_completed_success("feat-b", batch, cb_state)
        self.assertEqual(cb_state.consecutive_pauses, 0)

        with (
            patch.object(outcome_router_module, "_write_back_to_backlog"),
            patch.object(orchestrator_module, "overnight_log_event"),
        ):
            self._call("feat-c", "paused", batch, cb_state, error="fail again")
        self.assertEqual(cb_state.consecutive_pauses, 1)
        self.assertFalse(batch.circuit_breaker_fired)

    def test_threshold_consecutive_pauses_fires_circuit_breaker(self):
        """CIRCUIT_BREAKER_THRESHOLD consecutive pauses trips the breaker."""
        batch = BatchResult(batch_id=1)
        cb_state = CircuitBreakerState()
        with (
            patch.object(outcome_router_module, "_write_back_to_backlog"),
            patch.object(orchestrator_module, "overnight_log_event"),
        ):
            for i in range(CIRCUIT_BREAKER_THRESHOLD):
                self._call(f"feat-{i}", "paused", batch, cb_state, error="fail")

        self.assertTrue(batch.circuit_breaker_fired)
        self.assertEqual(cb_state.consecutive_pauses, CIRCUIT_BREAKER_THRESHOLD)


# ---------------------------------------------------------------------------
# Task 4: execute_feature() — happy path + brain-triage return-value handling
# ---------------------------------------------------------------------------


class TestExecuteFeature(unittest.IsolatedAsyncioTestCase):
    """Characterization tests for execute_feature() covering R1 (happy path)
    and R2 (brain-triage return-value dispatch: SKIP/DEFER/PAUSE).

    The merge-conflict recovery block at the top of execute_feature is
    skipped by mocking load_state with side_effect=Exception, which sets
    _skip_repair=True. SKIP and PAUSE are structurally identical at the
    execute_feature return boundary (both mock _handle_failed_task -> None
    and both expect status="paused"); DEFER returns a FeatureResult from
    _handle_failed_task which execute_feature propagates unchanged.
    """

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        tmp = self._tmpdir.name
        self._tmp = Path(tmp)
        self._config = BatchConfig(
            batch_id=1,
            plan_path=self._tmp / "plan.md",
            overnight_events_path=self._tmp / "overnight.log",
            pipeline_events_path=self._tmp / "pipeline.log",
            overnight_state_path=self._tmp / "state.json",
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

    def tearDown(self):
        self._tmpdir.cleanup()

    def _base_patches(self, retry_result, exit_report=("complete", None, None)):
        """Return a list of patch context managers covering the non-brain-triage
        surface used by both happy-path and failure-path tests."""
        return [
            patch.object(feature_executor_module, "load_state", side_effect=Exception("skip repair")),
            patch.object(feature_executor_module, "parse_feature_plan", return_value=self._feature_plan),
            patch.object(feature_executor_module, "retry_task", new=AsyncMock(return_value=retry_result)),
            patch.object(feature_executor_module, "_read_exit_report", return_value=exit_report),
            patch.object(feature_executor_module, "mark_task_done_in_plan"),
            patch.object(feature_executor_module, "pipeline_log_event"),
            patch.object(feature_executor_module, "overnight_log_event"),
            patch.object(feature_executor_module, "read_criticality", return_value="high"),
            patch.object(feature_executor_module, "_render_template", return_value="stub system prompt"),
            patch.object(
                subprocess,
                "run",
                return_value=MagicMock(returncode=0, stdout="0\n", stderr=""),
            ),
        ]

    async def test_happy_path_single_task_completes(self):
        """R1: execute_feature returns FeatureResult(status='completed') when
        the single task succeeds and the exit report is 'complete'."""
        retry_result = RetryResult(
            success=True,
            attempts=1,
            final_output="done",
            paused=False,
            idempotency_skipped=False,
        )
        patches = self._base_patches(retry_result)
        with patches[0], patches[1], patches[2], patches[3], patches[4], \
             patches[5], patches[6], patches[7], patches[8], patches[9]:
            result = await execute_feature(
                feature="test-feat",
                worktree_path=self._tmp,
                config=self._config,
            )

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.name, "test-feat")

    async def test_execute_feature_brain_triage_skip_returns_paused(self):
        """R2 SKIP: _handle_failed_task returns None → execute_feature falls
        through to return FeatureResult(status='paused')."""
        retry_result = RetryResult(
            success=False,
            attempts=2,
            final_output="task failed",
            paused=False,
            idempotency_skipped=False,
        )
        patches = self._base_patches(retry_result)
        with patches[0], patches[1], patches[2], patches[3], patches[4], \
             patches[5], patches[6], patches[7], patches[8], patches[9], \
             patch.object(
                 feature_executor_module,
                 "_handle_failed_task",
                 new=AsyncMock(return_value=None),
             ):
            result = await execute_feature(
                feature="test-feat",
                worktree_path=self._tmp,
                config=self._config,
            )

        self.assertEqual(result.status, "paused")
        self.assertEqual(result.name, "test-feat")

    async def test_execute_feature_brain_triage_defer_returns_deferred(self):
        """R2 DEFER: _handle_failed_task returns FeatureResult(status='deferred')
        → execute_feature propagates it unchanged."""
        retry_result = RetryResult(
            success=False,
            attempts=2,
            final_output="task failed",
            paused=False,
            idempotency_skipped=False,
        )
        deferred_result = FeatureResult(
            name="test-feat",
            status="deferred",
            deferred_question_count=1,
        )
        patches = self._base_patches(retry_result)
        with patches[0], patches[1], patches[2], patches[3], patches[4], \
             patches[5], patches[6], patches[7], patches[8], patches[9], \
             patch.object(
                 feature_executor_module,
                 "_handle_failed_task",
                 new=AsyncMock(return_value=deferred_result),
             ):
            result = await execute_feature(
                feature="test-feat",
                worktree_path=self._tmp,
                config=self._config,
            )

        self.assertEqual(result.status, "deferred")
        self.assertEqual(result.name, "test-feat")

    async def test_execute_feature_brain_triage_pause_returns_paused(self):
        """R2 PAUSE: _handle_failed_task returns None → execute_feature falls
        through to return FeatureResult(status='paused').

        Structurally identical to the SKIP test at the execute_feature return
        boundary. SKIP-specific side effects (mark_task_done_in_plan) live in
        _handle_failed_task and are covered by test_brain.py (Task 2)."""
        retry_result = RetryResult(
            success=False,
            attempts=2,
            final_output="task failed",
            paused=False,
            idempotency_skipped=False,
        )
        patches = self._base_patches(retry_result)
        with patches[0], patches[1], patches[2], patches[3], patches[4], \
             patches[5], patches[6], patches[7], patches[8], patches[9], \
             patch.object(
                 feature_executor_module,
                 "_handle_failed_task",
                 new=AsyncMock(return_value=None),
             ):
            result = await execute_feature(
                feature="test-feat",
                worktree_path=self._tmp,
                config=self._config,
            )

        self.assertEqual(result.status, "paused")
        self.assertEqual(result.name, "test-feat")


# ---------------------------------------------------------------------------
# Task 5 (R6): TestConflictRecoveryBranching — trivial / repair-agent / budget
# ---------------------------------------------------------------------------


class TestConflictRecoveryBranching(unittest.IsolatedAsyncioTestCase):
    """Characterization tests for the conflict-recovery block at the top of
    execute_feature (batch_runner.py lines 679–825).

    Three branches are covered:
      (a) trivial-eligible: <=3 conflicted files, none in hot-files →
          resolve_trivial_conflict is invoked; returns repair_completed with
          trivial_resolved=True.
      (b) non-trivial (>3 files): trivial path skipped, dispatch_repair_agent
          is invoked; returns repair_completed with repair_agent_used=True.
      (c) budget exhausted (recovery_attempts>=1): neither repair function
          is invoked; write_deferral is called and status='deferred'.
    """

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        tmp = self._tmpdir.name
        self._tmp = Path(tmp)
        self._config = BatchConfig(
            batch_id=1,
            plan_path=self._tmp / "plan.md",
            overnight_events_path=self._tmp / "overnight.log",
            pipeline_events_path=self._tmp / "pipeline.log",
            overnight_state_path=self._tmp / "state.json",
        )

    def tearDown(self):
        self._tmpdir.cleanup()

    def _make_state(self, *, recovery_depth: int = 0, recovery_attempts: int = 0):
        from cortex_command.overnight.state import OvernightFeatureStatus, OvernightState

        return OvernightState(
            session_id="s1",
            plan_ref="plan.md",
            features={
                "feat-a": OvernightFeatureStatus(
                    recovery_depth=recovery_depth,
                    recovery_attempts=recovery_attempts,
                )
            },
        )

    def _conflict_event(self, conflicted_files):
        return {
            "event": "merge_conflict_classified",
            "feature": "feat-a",
            "details": {
                "conflicted_files": conflicted_files,
                "conflict_summary": "conflict",
            },
        }

    async def test_trivial_eligible_conflict_resolves_via_trivial_path(self):
        """(a) <=3 conflicted files, no hot files → resolve_trivial_conflict
        is invoked and returns success; dispatch_repair_agent is NOT called."""
        state = self._make_state(recovery_depth=0, recovery_attempts=0)
        event = self._conflict_event(["f.py"])

        trivial_mock = AsyncMock(return_value=MagicMock(
            success=True,
            repair_branch="repair/feat-a",
            resolved_files=["f.py"],
        ))
        repair_mock = AsyncMock()

        with (
            patch.object(feature_executor_module, "load_state", return_value=state),
            patch.object(
                feature_executor_module,
                "read_events",
                MagicMock(return_value=iter([event])),
            ),
            patch.object(feature_executor_module, "resolve_trivial_conflict", new=trivial_mock),
            patch.object(feature_executor_module, "dispatch_repair_agent", new=repair_mock),
            patch.object(feature_executor_module, "save_state"),
            patch.object(feature_executor_module, "write_deferral"),
            patch.object(feature_executor_module, "overnight_log_event"),
            patch.object(feature_executor_module, "pipeline_log_event"),
            patch.object(feature_executor_module, "_render_template", return_value="stub"),
            patch.object(feature_executor_module, "read_criticality", return_value="high"),
            patch.object(feature_executor_module, "parse_feature_plan"),
        ):
            result = await execute_feature(
                feature="feat-a",
                worktree_path=self._tmp,
                config=self._config,
            )

        self.assertEqual(result.status, "repair_completed")
        self.assertTrue(result.trivial_resolved)
        trivial_mock.assert_awaited_once()
        repair_mock.assert_not_awaited()

    async def test_non_trivial_conflict_dispatches_repair_agent(self):
        """(b) >3 conflicted files, recovery_depth=0, recovery_attempts=0 →
        trivial path skipped; dispatch_repair_agent is invoked and returns
        success with repair_agent_used=True."""
        state = self._make_state(recovery_depth=0, recovery_attempts=0)
        event = self._conflict_event(["a.py", "b.py", "c.py", "d.py"])

        trivial_mock = AsyncMock()
        repair_mock = AsyncMock(return_value=MagicMock(
            success=True,
            repair_branch="repair/feat-a",
            error=None,
        ))

        with (
            patch.object(feature_executor_module, "load_state", return_value=state),
            patch.object(
                feature_executor_module,
                "read_events",
                MagicMock(return_value=iter([event])),
            ),
            patch.object(feature_executor_module, "resolve_trivial_conflict", new=trivial_mock),
            patch.object(feature_executor_module, "dispatch_repair_agent", new=repair_mock),
            patch.object(feature_executor_module, "save_state"),
            patch.object(feature_executor_module, "write_deferral"),
            patch.object(feature_executor_module, "overnight_log_event"),
            patch.object(feature_executor_module, "pipeline_log_event"),
            patch.object(feature_executor_module, "_render_template", return_value="stub"),
            patch.object(feature_executor_module, "read_criticality", return_value="high"),
            patch.object(feature_executor_module, "parse_feature_plan"),
        ):
            result = await execute_feature(
                feature="feat-a",
                worktree_path=self._tmp,
                config=self._config,
            )

        self.assertEqual(result.status, "repair_completed")
        self.assertTrue(result.repair_agent_used)
        trivial_mock.assert_not_awaited()
        repair_mock.assert_awaited_once()

    async def test_recovery_budget_exhausted_returns_deferred(self):
        """(c) recovery_attempts>=1 with recovery_depth<1 → neither repair
        function called; write_deferral invoked; status='deferred'."""
        state = self._make_state(recovery_depth=0, recovery_attempts=1)
        event = self._conflict_event(["a.py", "b.py", "c.py", "d.py"])

        trivial_mock = AsyncMock()
        repair_mock = AsyncMock()
        deferral_mock = MagicMock()

        with (
            patch.object(feature_executor_module, "load_state", return_value=state),
            patch.object(
                feature_executor_module,
                "read_events",
                MagicMock(return_value=iter([event])),
            ),
            patch.object(feature_executor_module, "resolve_trivial_conflict", new=trivial_mock),
            patch.object(feature_executor_module, "dispatch_repair_agent", new=repair_mock),
            patch.object(feature_executor_module, "save_state"),
            patch.object(feature_executor_module, "write_deferral", new=deferral_mock),
            patch.object(feature_executor_module, "overnight_log_event"),
            patch.object(feature_executor_module, "pipeline_log_event"),
            patch.object(feature_executor_module, "_render_template", return_value="stub"),
            patch.object(feature_executor_module, "read_criticality", return_value="high"),
            patch.object(feature_executor_module, "parse_feature_plan"),
        ):
            result = await execute_feature(
                feature="feat-a",
                worktree_path=self._tmp,
                config=self._config,
            )

        self.assertEqual(result.status, "deferred")
        trivial_mock.assert_not_awaited()
        repair_mock.assert_not_awaited()
        deferral_mock.assert_called_once()


# ---------------------------------------------------------------------------
# Task 6 (R7, R9, R10): TestAccumulateResultViaBatch — CI deferral,
# budget abort, multi-feature recovery
# ---------------------------------------------------------------------------


class TestAccumulateResultViaBatch(unittest.IsolatedAsyncioTestCase):
    """Characterization tests that drive ``run_batch`` end-to-end to exercise
    ``_accumulate_result`` branches without refactoring it out.

    Covers:
      (R7) CI deferral for ``ci_pending`` and ``ci_failing`` merge errors →
           ``batch_result.features_deferred`` contains the feature.
      (R9) ``budget_exhausted`` global abort signal propagates to
           ``batch_result.global_abort_signal == True``.
      (R10) Multi-feature batch: Feature A triggers test-failure recovery
            while Feature B does not — ``recover_test_failure`` called
            exactly once, Feature B ends up in ``features_merged``.
    """

    def setUp(self):
        from cortex_command.overnight.state import OvernightFeatureStatus, OvernightState

        self._tmpdir = tempfile.TemporaryDirectory()
        tmp = self._tmpdir.name
        self._tmp = Path(tmp)

        self._config = BatchConfig(
            batch_id=1,
            plan_path=self._tmp / "plan.md",
            overnight_events_path=self._tmp / "overnight.log",
            pipeline_events_path=self._tmp / "pipeline.log",
            overnight_state_path=self._tmp / "state.json",
            result_dir=self._tmp,
        )
        self._OvernightState = OvernightState
        self._OvernightFeatureStatus = OvernightFeatureStatus

    def tearDown(self):
        self._tmpdir.cleanup()

    def _start_patch(self, *args, **kwargs):
        p = patch(*args, **kwargs)
        mock = p.start()
        self.addCleanup(p.stop)
        return mock

    def _make_plan(self, feature_names):
        features = []
        for n in feature_names:
            f = MagicMock()
            f.name = n
            features.append(f)
        plan = MagicMock()
        plan.features = features
        return plan

    def _make_worktree_info(self, name):
        info = MagicMock()
        info.path = self._tmp / f"wt-{name}"
        info.branch = f"pipeline/{name}"
        return info

    def _make_state(self, feature_names):
        return self._OvernightState(
            session_id="s1",
            plan_ref="plan.md",
            features={
                n: self._OvernightFeatureStatus(recovery_attempts=0)
                for n in feature_names
            },
        )

    def _install_common_patches(self, *, feature_names, execute_return, merge_side_effect):
        """Install all common patches required for run_batch-level tests.

        Returns a dict of the mocks that callers typically need to assert on.
        """
        from cortex_command.overnight.types import FeatureResult as _FR

        self._start_patch.__self__  # sanity — ensure method is bound

        self._start_patch(
            "cortex_command.overnight.orchestrator.parse_master_plan",
            return_value=self._make_plan(feature_names),
        )
        self._start_patch(
            "cortex_command.overnight.orchestrator.create_worktree",
            side_effect=lambda name, *a, **kw: self._make_worktree_info(name),
        )
        self._start_patch(
            "cortex_command.overnight.orchestrator.load_state",
            return_value=self._make_state(feature_names),
        )
        self._start_patch("cortex_command.overnight.orchestrator.save_state")
        self._start_patch(
            "cortex_command.overnight.orchestrator.load_throttle_config",
            return_value=MagicMock(),
        )
        mock_manager = MagicMock()
        mock_manager.acquire = AsyncMock()
        mock_manager.release = MagicMock()
        mock_manager.stats = {}
        self._start_patch(
            "cortex_command.overnight.orchestrator.ConcurrencyManager",
            return_value=mock_manager,
        )

        # execute_feature: allow dict-keyed or single return
        if isinstance(execute_return, dict):
            async def _exec_side(feature, *args, **kwargs):
                return execute_return[feature]
            exec_mock = self._start_patch(
                "cortex_command.overnight.orchestrator.execute_feature",
                new=AsyncMock(side_effect=_exec_side),
            )
        else:
            exec_mock = self._start_patch(
                "cortex_command.overnight.orchestrator.execute_feature",
                new=AsyncMock(return_value=execute_return),
            )

        self._start_patch(
            "cortex_command.overnight.outcome_router._get_changed_files",
            return_value=["src/foo.py"],
        )
        if merge_side_effect is not None:
            merge_mock = self._start_patch(
                "cortex_command.overnight.outcome_router.merge_feature",
                side_effect=merge_side_effect,
            )
        else:
            merge_mock = None

        self._start_patch("cortex_command.overnight.orchestrator.overnight_log_event")
        self._start_patch("cortex_command.overnight.outcome_router._write_back_to_backlog")
        self._start_patch("cortex_command.overnight.outcome_router.cleanup_worktree")
        recovery_mock = self._start_patch(
            "cortex_command.overnight.outcome_router.recover_test_failure",
            new=AsyncMock(),
        )
        self._start_patch("cortex_command.overnight.orchestrator.save_batch_result")

        return {
            "execute_feature": exec_mock,
            "merge_feature": merge_mock,
            "recover_test_failure": recovery_mock,
            "manager": mock_manager,
            "_FeatureResult": _FR,
        }

    # --- R7: CI deferral for ci_pending and ci_failing ---

    async def test_ci_pending_defers_feature(self):
        """R7 (ci_pending): merge_feature returns error='ci_pending' →
        batch_result.features_deferred contains the feature."""
        from cortex_command.pipeline.merge import MergeResult

        merge_result = MergeResult(
            success=False,
            feature="feat-a",
            conflict=False,
            error="ci_pending",
        )
        mocks = self._install_common_patches(
            feature_names=["feat-a"],
            execute_return=FeatureResult(name="feat-a", status="completed"),
            merge_side_effect=lambda **kw: merge_result,
        )
        self._start_patch("cortex_command.overnight.outcome_router.write_deferral")

        from cortex_command.overnight.orchestrator import run_batch

        batch_result = await run_batch(self._config)

        self.assertEqual(len(batch_result.features_deferred), 1)
        self.assertEqual(batch_result.features_deferred[0]["name"], "feat-a")
        # Sanity: recovery wasn't triggered for a CI-deferral path.
        mocks["recover_test_failure"].assert_not_awaited()

    async def test_ci_failing_defers_feature(self):
        """R7 (ci_failing): merge_feature returns error='ci_failing' →
        batch_result.features_deferred contains the feature."""
        from cortex_command.pipeline.merge import MergeResult

        merge_result = MergeResult(
            success=False,
            feature="feat-a",
            conflict=False,
            error="ci_failing",
        )
        mocks = self._install_common_patches(
            feature_names=["feat-a"],
            execute_return=FeatureResult(name="feat-a", status="completed"),
            merge_side_effect=lambda **kw: merge_result,
        )
        self._start_patch("cortex_command.overnight.outcome_router.write_deferral")

        from cortex_command.overnight.orchestrator import run_batch

        batch_result = await run_batch(self._config)

        self.assertEqual(len(batch_result.features_deferred), 1)
        self.assertEqual(batch_result.features_deferred[0]["name"], "feat-a")
        mocks["recover_test_failure"].assert_not_awaited()

    # --- R9: budget_exhausted global abort signal ---

    async def test_budget_exhausted_sets_global_abort_signal(self):
        """R9: execute_feature returns paused with error='budget_exhausted'
        → batch_result.global_abort_signal == True."""
        self._install_common_patches(
            feature_names=["feat-a"],
            execute_return=FeatureResult(
                name="feat-a",
                status="paused",
                error="budget_exhausted",
            ),
            merge_side_effect=None,  # non-completed features skip merge
        )
        self._start_patch("cortex_command.overnight.orchestrator.transition")

        from cortex_command.overnight.orchestrator import run_batch

        batch_result = await run_batch(self._config)

        self.assertTrue(batch_result.global_abort_signal)
        self.assertEqual(batch_result.abort_reason, "budget_exhausted")

    # --- R10: multi-feature recovery — A recovers, B merges clean ---

    async def test_multi_feature_only_failing_feature_triggers_recovery(self):
        """R10: Two features — A fails tests on merge, B merges clean.
        recover_test_failure called exactly once; feat-b in features_merged."""
        from cortex_command.pipeline.merge import MergeResult, TestResult
        from cortex_command.pipeline.merge_recovery import MergeRecoveryResult

        feat_a_fail = MergeResult(
            success=False,
            feature="feat-a",
            conflict=False,
            test_result=TestResult(passed=False, output="FAILED", return_code=1),
            error="Tests failed (exit code 1)",
        )
        feat_b_ok = MergeResult(success=True, feature="feat-b", conflict=False)

        def merge_side_effect(**kwargs):
            return feat_a_fail if kwargs.get("feature") == "feat-a" else feat_b_ok

        mocks = self._install_common_patches(
            feature_names=["feat-a", "feat-b"],
            execute_return={
                "feat-a": FeatureResult(name="feat-a", status="completed"),
                "feat-b": FeatureResult(name="feat-b", status="completed"),
            },
            merge_side_effect=merge_side_effect,
        )
        mocks["recover_test_failure"].return_value = MergeRecoveryResult(
            success=True,
            attempts=1,
            paused=False,
            flaky=False,
            error=None,
        )
        # requires_review is invoked on the merge-success path for feat-b.
        self._start_patch(
            "cortex_command.overnight.outcome_router.requires_review",
            return_value=False,
        )
        self._start_patch("cortex_command.overnight.outcome_router.read_tier", return_value="S")
        self._start_patch(
            "cortex_command.overnight.outcome_router.read_criticality",
            return_value="low",
        )

        from cortex_command.overnight.orchestrator import run_batch

        batch_result = await run_batch(self._config)

        self.assertEqual(mocks["recover_test_failure"].await_count, 1)
        self.assertIn("feat-b", set(batch_result.features_merged))

    # --- R8: review-gating paths ---

    async def test_review_not_required(self):
        """R8 (a): requires_review=False → feature merged; dispatch_review not called."""
        from cortex_command.pipeline.merge import MergeResult

        merge_result = MergeResult(success=True, feature="feat-a", conflict=False)
        self._install_common_patches(
            feature_names=["feat-a"],
            execute_return=FeatureResult(name="feat-a", status="completed"),
            merge_side_effect=lambda **kw: merge_result,
        )
        self._start_patch(
            "cortex_command.overnight.outcome_router.requires_review",
            return_value=False,
        )
        self._start_patch(
            "cortex_command.overnight.outcome_router.read_tier",
            return_value="S",
        )
        self._start_patch(
            "cortex_command.overnight.outcome_router.read_criticality",
            return_value="low",
        )
        dispatch_mock = self._start_patch(
            "cortex_command.overnight.outcome_router.dispatch_review",
            new_callable=AsyncMock,
        )

        from cortex_command.overnight.orchestrator import run_batch

        batch_result = await run_batch(self._config)

        self.assertIn("feat-a", set(batch_result.features_merged))
        dispatch_mock.assert_not_awaited()

    async def test_review_approved(self):
        """R8 (b): requires_review=True and dispatch_review returns
        deferred=False, verdict='APPROVED' → feature merged."""
        from cortex_command.pipeline.merge import MergeResult

        merge_result = MergeResult(success=True, feature="feat-a", conflict=False)
        self._install_common_patches(
            feature_names=["feat-a"],
            execute_return=FeatureResult(name="feat-a", status="completed"),
            merge_side_effect=lambda **kw: merge_result,
        )
        self._start_patch(
            "cortex_command.overnight.outcome_router.requires_review",
            return_value=True,
        )
        self._start_patch(
            "cortex_command.overnight.outcome_router.read_tier",
            return_value="L",
        )
        self._start_patch(
            "cortex_command.overnight.outcome_router.read_criticality",
            return_value="high",
        )
        self._start_patch(
            "cortex_command.overnight.outcome_router.dispatch_review",
            new_callable=AsyncMock,
            return_value=MagicMock(deferred=False, verdict="APPROVED", cycle=1),
        )

        from cortex_command.overnight.orchestrator import run_batch

        batch_result = await run_batch(self._config)

        self.assertIn("feat-a", set(batch_result.features_merged))

    async def test_review_deferred(self):
        """R8 (c): requires_review=True and dispatch_review returns
        deferred=True → feature in features_deferred."""
        from cortex_command.pipeline.merge import MergeResult

        merge_result = MergeResult(success=True, feature="feat-a", conflict=False)
        self._install_common_patches(
            feature_names=["feat-a"],
            execute_return=FeatureResult(name="feat-a", status="completed"),
            merge_side_effect=lambda **kw: merge_result,
        )
        self._start_patch(
            "cortex_command.overnight.outcome_router.requires_review",
            return_value=True,
        )
        self._start_patch(
            "cortex_command.overnight.outcome_router.read_tier",
            return_value="L",
        )
        self._start_patch(
            "cortex_command.overnight.outcome_router.read_criticality",
            return_value="high",
        )
        self._start_patch(
            "cortex_command.overnight.outcome_router.dispatch_review",
            new_callable=AsyncMock,
            return_value=MagicMock(
                deferred=True,
                verdict="DEFERRED_FOR_REVIEW",
                cycle=1,
            ),
        )

        from cortex_command.overnight.orchestrator import run_batch

        batch_result = await run_batch(self._config)

        self.assertEqual(len(batch_result.features_deferred), 1)

    async def test_review_raises(self):
        """R8 (d): requires_review=True and dispatch_review raises →
        feature in features_deferred (crash path writes a deferral)."""
        from cortex_command.pipeline.merge import MergeResult

        merge_result = MergeResult(success=True, feature="feat-a", conflict=False)
        self._install_common_patches(
            feature_names=["feat-a"],
            execute_return=FeatureResult(name="feat-a", status="completed"),
            merge_side_effect=lambda **kw: merge_result,
        )
        self._start_patch(
            "cortex_command.overnight.outcome_router.requires_review",
            return_value=True,
        )
        self._start_patch(
            "cortex_command.overnight.outcome_router.read_tier",
            return_value="L",
        )
        self._start_patch(
            "cortex_command.overnight.outcome_router.read_criticality",
            return_value="high",
        )
        self._start_patch(
            "cortex_command.overnight.outcome_router.dispatch_review",
            new_callable=AsyncMock,
            side_effect=RuntimeError("crash"),
        )
        self._start_patch("cortex_command.overnight.outcome_router.write_deferral")

        from cortex_command.overnight.orchestrator import run_batch

        batch_result = await run_batch(self._config)

        self.assertEqual(len(batch_result.features_deferred), 1)


if __name__ == "__main__":
    unittest.main()
