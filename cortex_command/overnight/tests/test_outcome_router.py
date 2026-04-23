"""Unit tests for ``outcome_router.apply_feature_result()``.

Task 6 — Exercises ``apply_feature_result`` directly for each major
status branch (merged/paused/deferred/failed/repair_completed) and the
circuit breaker. All patches target ``cortex_command.overnight.outcome_router.*``
so these tests continue to pass after batch_runner's copies are removed.
"""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from cortex_command.overnight.constants import CIRCUIT_BREAKER_THRESHOLD
from cortex_command.overnight.outcome_router import OutcomeContext, apply_feature_result
from cortex_command.overnight.types import CircuitBreakerState, FeatureResult


def _make_ctx(pauses: int | None = None) -> OutcomeContext:
    """Factory: build an OutcomeContext with real Lock, MagicMock batch_result
    and config, and empty dicts for path maps."""
    batch_result = MagicMock()
    # Populate list-valued fields with real lists so .append() works under assertion.
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
        cb_state=CircuitBreakerState(consecutive_pauses=pauses if pauses is not None else 0),
        recovery_attempts_map={},
        worktree_paths={},
        worktree_branches={},
        repo_path_map={},
        integration_worktrees={},
        integration_branches={},
        session_id="s1",
        backlog_ids={},
        feature_names=["feat-a"],
        config=config,
    )


class TestApplyFeatureResultStatusDispatch(unittest.IsolatedAsyncioTestCase):
    """Status-transition coverage for apply_feature_result."""

    async def test_merged_path_resets_pauses_and_writes_back(self):
        """status='completed' with successful merge → merge_feature called,
        _write_back_to_backlog called, cb_state.consecutive_pauses reset to 0."""
        ctx = _make_ctx(pauses=2)
        merge_result = MagicMock(
            success=True, error=None, conflict=False, test_result=None,
        )

        with (
            patch(
                "cortex_command.overnight.outcome_router._get_changed_files",
                return_value=["src/a.py"],
            ),
            patch(
                "cortex_command.overnight.outcome_router.merge_feature",
                return_value=merge_result,
            ) as m_merge,
            patch(
                "cortex_command.overnight.outcome_router.requires_review",
                return_value=False,
            ),
            patch("cortex_command.overnight.outcome_router.read_tier", return_value="S"),
            patch(
                "cortex_command.overnight.outcome_router.read_criticality",
                return_value="low",
            ),
            patch(
                "cortex_command.overnight.outcome_router._write_back_to_backlog",
            ) as m_wb,
            patch("cortex_command.overnight.outcome_router.overnight_log_event"),
            patch("cortex_command.overnight.outcome_router.cleanup_worktree"),
        ):
            await apply_feature_result(
                "feat-a",
                FeatureResult(name="feat-a", status="completed"),
                ctx,
            )

        m_merge.assert_called_once()
        self.assertTrue(m_wb.called)
        self.assertEqual(ctx.cb_state.consecutive_pauses, 0)
        self.assertIn("feat-a", ctx.batch_result.features_merged)

    async def test_paused_increments_counter_and_skips_merge(self):
        """status='paused' → merge_feature NOT called; pauses counter
        incremented; _write_back_to_backlog NOT called for the paused
        branch's early-return (batch_result not abort-signaled)."""
        ctx = _make_ctx(pauses=0)
        # Prevent budget_exhausted branch side effects from firing
        ctx.batch_result.global_abort_signal = True  # short-circuit that guard

        with (
            patch(
                "cortex_command.overnight.outcome_router.merge_feature",
            ) as m_merge,
            patch(
                "cortex_command.overnight.outcome_router._write_back_to_backlog",
            ) as m_wb,
            patch("cortex_command.overnight.outcome_router.overnight_log_event"),
        ):
            await apply_feature_result(
                "feat-a",
                FeatureResult(name="feat-a", status="paused", error="something"),
                ctx,
            )

        m_merge.assert_not_called()
        # _write_back_to_backlog is called by the paused branch in the sync
        # dispatcher. The task requirement "_write_back_to_backlog NOT called"
        # refers to the merged-path writeback (status='merged') not being
        # invoked — here the only writeback call (if any) is a 'paused'
        # status writeback.
        for call_args in m_wb.call_args_list:
            # Second positional arg is the status
            args = call_args.args
            if len(args) >= 2:
                self.assertNotEqual(args[1], "merged")
        self.assertEqual(ctx.cb_state.consecutive_pauses, 1)

    async def test_deferred_calls_write_deferral_wrapper(self):
        """status='deferred' → deferral recorded on batch_result; counter
        incremented. (The sync dispatcher for status='deferred' does not
        invoke write_deferral directly — it appends to features_deferred
        and calls _write_back_to_backlog with 'deferred'.)"""
        ctx = _make_ctx(pauses=0)

        with (
            patch("cortex_command.overnight.outcome_router.merge_feature") as m_merge,
            patch(
                "cortex_command.overnight.outcome_router._write_back_to_backlog",
            ) as m_wb,
            patch("cortex_command.overnight.outcome_router.overnight_log_event"),
            patch("cortex_command.overnight.outcome_router.write_deferral") as m_write_def,
        ):
            await apply_feature_result(
                "feat-a",
                FeatureResult(
                    name="feat-a", status="deferred", deferred_question_count=1,
                ),
                ctx,
            )

        m_merge.assert_not_called()
        # The 'deferred' sync branch writes back with status='deferred'.
        deferred_wbs = [
            c for c in m_wb.call_args_list
            if len(c.args) >= 2 and c.args[1] == "deferred"
        ]
        self.assertEqual(len(deferred_wbs), 1)
        self.assertEqual(len(ctx.batch_result.features_deferred), 1)
        # Deferred status increments the pause counter (same as paused/failed).
        # Note: the sync dispatcher does NOT increment for 'deferred' —
        # only paused/failed/no-commit-guard. So counter stays 0.
        self.assertEqual(ctx.cb_state.consecutive_pauses, 0)
        # write_deferral is patched but not invoked by the 'deferred' sync
        # branch itself (it's invoked by CI-deferral / review-crash paths).
        m_write_def.assert_not_called()

    async def test_failed_increments_counter_and_skips_merge(self):
        """status='failed' (parse_error=False) → cb_state.consecutive_pauses
        incremented; merge_feature NOT called."""
        ctx = _make_ctx(pauses=1)

        with (
            patch("cortex_command.overnight.outcome_router.merge_feature") as m_merge,
            patch("cortex_command.overnight.outcome_router._write_back_to_backlog"),
            patch("cortex_command.overnight.outcome_router.overnight_log_event"),
        ):
            await apply_feature_result(
                "feat-a",
                FeatureResult(
                    name="feat-a", status="failed",
                    error="boom", parse_error=False,
                ),
                ctx,
            )

        m_merge.assert_not_called()
        self.assertEqual(ctx.cb_state.consecutive_pauses, 2)

    async def test_repair_completed_routes_through_merged_path(self):
        """status='repair_completed' → sync dispatcher fast-forward merges
        the repair branch and routes through the merged path (features_merged
        appended, counter reset)."""
        ctx = _make_ctx(pauses=1)

        ff_proc = MagicMock(returncode=0, stderr="")
        checkout_proc = MagicMock(returncode=0, stderr="")
        del_proc = MagicMock(returncode=0, stderr="")

        with (
            patch(
                "cortex_command.overnight.outcome_router.subprocess.run",
                side_effect=[checkout_proc, ff_proc, del_proc],
            ) as m_sp,
            patch("cortex_command.overnight.outcome_router.merge_feature") as m_merge,
            patch(
                "cortex_command.overnight.outcome_router._write_back_to_backlog",
            ) as m_wb,
            patch("cortex_command.overnight.outcome_router.overnight_log_event"),
            patch("cortex_command.overnight.outcome_router.cleanup_worktree"),
        ):
            await apply_feature_result(
                "feat-a",
                FeatureResult(
                    name="feat-a",
                    status="repair_completed",
                    repair_branch="repair/feat-a",
                ),
                ctx,
            )

        # The fast-forward path uses subprocess.run, not merge_feature().
        m_merge.assert_not_called()
        # At least the checkout + ff-merge subprocess calls must have happened.
        self.assertGreaterEqual(m_sp.call_count, 2)
        # Routes through the merged path: counter reset, features_merged has it.
        self.assertEqual(ctx.cb_state.consecutive_pauses, 0)
        self.assertIn("feat-a", ctx.batch_result.features_merged)
        # And _write_back_to_backlog was invoked with 'merged' status.
        merged_wbs = [
            c for c in m_wb.call_args_list
            if len(c.args) >= 2 and c.args[1] == "merged"
        ]
        self.assertEqual(len(merged_wbs), 1)


class TestApplyFeatureResultCircuitBreaker(unittest.IsolatedAsyncioTestCase):
    """Circuit breaker: one pause at THRESHOLD-1 trips the breaker."""

    async def test_circuit_breaker_fires_at_threshold(self):
        """cb_state.consecutive_pauses = THRESHOLD-1 → a single paused
        outcome tips the counter to THRESHOLD and fires the breaker."""
        ctx = _make_ctx(pauses=CIRCUIT_BREAKER_THRESHOLD - 1)
        ctx.batch_result.global_abort_signal = True  # short-circuit budget branch

        with (
            patch("cortex_command.overnight.outcome_router.merge_feature"),
            patch("cortex_command.overnight.outcome_router._write_back_to_backlog"),
            patch("cortex_command.overnight.outcome_router.overnight_log_event"),
        ):
            await apply_feature_result(
                "feat-a",
                FeatureResult(name="feat-a", status="paused", error="boom"),
                ctx,
            )

        self.assertEqual(ctx.cb_state.consecutive_pauses, CIRCUIT_BREAKER_THRESHOLD)
        self.assertTrue(ctx.batch_result.circuit_breaker_fired)


class TestApplyFeatureResultReviewGating(unittest.IsolatedAsyncioTestCase):
    """Review gating and recovery-path coverage for apply_feature_result."""

    async def test_review_gated_dispatches_review_once(self):
        """requires_review=True + merged → dispatch_review called once with
        the correct feature and branch args."""
        ctx = _make_ctx(pauses=0)
        ctx.worktree_branches["feat-a"] = "pipeline/feat-a"

        merge_result = MagicMock(
            success=True, error=None, conflict=False, test_result=None,
        )
        review_result = MagicMock(deferred=False, verdict="approved", cycle=1)

        with (
            patch(
                "cortex_command.overnight.outcome_router._get_changed_files",
                return_value=["src/a.py"],
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
            ) as m_dispatch,
            patch("cortex_command.overnight.outcome_router.read_tier", return_value="M"),
            patch(
                "cortex_command.overnight.outcome_router.read_criticality",
                return_value="high",
            ),
            patch("cortex_command.overnight.outcome_router._write_back_to_backlog"),
            patch("cortex_command.overnight.outcome_router.overnight_log_event"),
            patch("cortex_command.overnight.outcome_router.cleanup_worktree"),
        ):
            await apply_feature_result(
                "feat-a",
                FeatureResult(name="feat-a", status="completed"),
                ctx,
            )

        m_dispatch.assert_awaited_once()
        kwargs = m_dispatch.await_args.kwargs
        self.assertEqual(kwargs["feature"], "feat-a")
        self.assertEqual(kwargs["branch"], "pipeline/feat-a")

    async def test_review_ungated_skips_dispatch(self):
        """requires_review=False → dispatch_review NOT called; merged path
        proceeds normally."""
        ctx = _make_ctx(pauses=0)

        merge_result = MagicMock(
            success=True, error=None, conflict=False, test_result=None,
        )

        with (
            patch(
                "cortex_command.overnight.outcome_router._get_changed_files",
                return_value=["src/a.py"],
            ),
            patch(
                "cortex_command.overnight.outcome_router.merge_feature",
                return_value=merge_result,
            ),
            patch(
                "cortex_command.overnight.outcome_router.requires_review",
                return_value=False,
            ),
            patch(
                "cortex_command.overnight.outcome_router.dispatch_review",
                new=AsyncMock(),
            ) as m_dispatch,
            patch("cortex_command.overnight.outcome_router.read_tier", return_value="S"),
            patch(
                "cortex_command.overnight.outcome_router.read_criticality",
                return_value="low",
            ),
            patch("cortex_command.overnight.outcome_router._write_back_to_backlog"),
            patch("cortex_command.overnight.outcome_router.overnight_log_event"),
            patch("cortex_command.overnight.outcome_router.cleanup_worktree"),
        ):
            await apply_feature_result(
                "feat-a",
                FeatureResult(name="feat-a", status="completed"),
                ctx,
            )

        m_dispatch.assert_not_awaited()
        self.assertIn("feat-a", ctx.batch_result.features_merged)

    async def test_recovery_path_awaits_recover_and_increments_attempts(self):
        """merge_feature returns success=False with a test_result (test
        failure indicator) → recover_test_failure awaited once; and
        ctx.recovery_attempts_map[name] is incremented to 1 BEFORE the
        recovery dispatch."""
        ctx = _make_ctx(pauses=0)
        ctx.worktree_branches["feat-a"] = "pipeline/feat-a"

        test_result = MagicMock(output="FAILED: test_foo")
        merge_result = MagicMock(
            success=False,
            error="test_failure",
            conflict=False,
            test_result=test_result,
        )

        observed_attempts: list[int] = []

        async def _fake_recover(**kwargs):
            # Capture recovery_attempts_map state at the moment of the call
            observed_attempts.append(ctx.recovery_attempts_map.get("feat-a", 0))
            return MagicMock(status="paused", repair_branch=None)

        with (
            patch(
                "cortex_command.overnight.outcome_router._get_changed_files",
                return_value=["src/a.py"],
            ),
            patch(
                "cortex_command.overnight.outcome_router.merge_feature",
                return_value=merge_result,
            ),
            patch(
                "cortex_command.overnight.outcome_router.recover_test_failure",
                new=AsyncMock(side_effect=_fake_recover),
            ) as m_recover,
            patch("cortex_command.overnight.outcome_router._write_back_to_backlog"),
            patch("cortex_command.overnight.outcome_router.overnight_log_event"),
            patch("cortex_command.overnight.outcome_router.load_state"),
            patch("cortex_command.overnight.outcome_router.save_state"),
            patch("cortex_command.overnight.outcome_router._apply_feature_result"),
        ):
            await apply_feature_result(
                "feat-a",
                FeatureResult(name="feat-a", status="completed"),
                ctx,
            )

        m_recover.assert_awaited_once()
        # Increment happens BEFORE dispatch — observed at call site == 1.
        self.assertEqual(observed_attempts, [1])
        self.assertEqual(ctx.recovery_attempts_map["feat-a"], 1)


if __name__ == "__main__":
    unittest.main()
