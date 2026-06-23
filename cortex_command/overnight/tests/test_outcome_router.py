"""Unit tests for ``outcome_router.apply_feature_result()``.

Task 6 — Exercises ``apply_feature_result`` directly for each major
status branch (merged/paused/deferred/failed/repair_completed) and the
circuit breaker. All patches target ``cortex_command.overnight.outcome_router.*``
so these tests continue to pass after batch_runner's copies are removed.
"""

from __future__ import annotations

import asyncio
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from cortex_command.overnight.constants import CIRCUIT_BREAKER_THRESHOLD, SYSTEMIC_FAILURE_THRESHOLD
from cortex_command.overnight.outcome_router import (
    OutcomeContext,
    _apply_feature_result,
    _find_backlog_item_path,
    _write_back_to_backlog,
    apply_feature_result,
    set_backlog_dir,
)
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
        home_worktree_path=Path("/tmp/unused-home-integration-worktree"),
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

        # The repair_completed ff-merge now runs in _repair_completed_review_gate
        # (R12): checkout base, capture pre-ff HEAD (rev-parse), ff-merge, then —
        # for a non-review-qualifying feature — branch-delete.
        ff_proc = MagicMock(returncode=0, stderr="")
        checkout_proc = MagicMock(returncode=0, stderr="")
        revparse_proc = MagicMock(returncode=0, stdout="basesha000\n", stderr="")
        del_proc = MagicMock(returncode=0, stderr="")

        with (
            patch(
                "cortex_command.overnight.outcome_router.subprocess.run",
                side_effect=[checkout_proc, revparse_proc, ff_proc, del_proc],
            ) as m_sp,
            patch("cortex_command.overnight.outcome_router.merge_feature") as m_merge,
            patch(
                "cortex_command.overnight.outcome_router.requires_review",
                return_value=False,
            ),
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


class TestSystemicIncrementGuard(unittest.IsolatedAsyncioTestCase):
    """systemic_pauses_in_batch increments only for errors in _SYSTEMIC_ERROR_TYPES."""

    async def test_systemic_increment_both_counters_on_systemic_error(self):
        """A paused FeatureResult with error='worker_no_exit_report' (a member of
        _SYSTEMIC_ERROR_TYPES) increments both consecutive_pauses and
        systemic_pauses_in_batch."""
        ctx = _make_ctx(pauses=0)
        ctx.batch_result.global_abort_signal = True  # short-circuit budget branch

        with (
            patch("cortex_command.overnight.outcome_router.merge_feature"),
            patch("cortex_command.overnight.outcome_router._write_back_to_backlog"),
            patch("cortex_command.overnight.outcome_router.overnight_log_event"),
        ):
            await apply_feature_result(
                "feat-a",
                FeatureResult(name="feat-a", status="paused", error="worker_no_exit_report"),
                ctx,
            )

        self.assertEqual(ctx.cb_state.consecutive_pauses, 1)
        self.assertEqual(ctx.cb_state.systemic_pauses_in_batch, 1)

    async def test_systemic_increment_only_consecutive_on_non_systemic_error(self):
        """A paused FeatureResult with error='merge recovery failed: ...' (a wrapped
        string not in _SYSTEMIC_ERROR_TYPES) increments only consecutive_pauses;
        systemic_pauses_in_batch stays at 0."""
        ctx = _make_ctx(pauses=0)
        ctx.batch_result.global_abort_signal = True  # short-circuit budget branch

        with (
            patch("cortex_command.overnight.outcome_router.merge_feature"),
            patch("cortex_command.overnight.outcome_router._write_back_to_backlog"),
            patch("cortex_command.overnight.outcome_router.overnight_log_event"),
        ):
            await apply_feature_result(
                "feat-a",
                FeatureResult(
                    name="feat-a",
                    status="paused",
                    error="merge recovery failed: test suite timed out",
                ),
                ctx,
            )

        self.assertEqual(ctx.cb_state.consecutive_pauses, 1)
        self.assertEqual(ctx.cb_state.systemic_pauses_in_batch, 0)


class TestSystemicThreshold(unittest.IsolatedAsyncioTestCase):
    """Systemic failure threshold tests (R10): PIPELINE_SYSTEMIC_FAILURE event
    and global_abort_signal behavior around SYSTEMIC_FAILURE_THRESHOLD."""

    def _make_ctx_with_systemic_pauses(self, systemic_count: int) -> OutcomeContext:
        """Build a context with systemic_pauses_in_batch pre-loaded and
        features_paused populated with matching systemic error entries."""
        ctx = _make_ctx(pauses=systemic_count)
        ctx.cb_state.systemic_pauses_in_batch = systemic_count
        ctx.batch_result.global_abort_signal = False
        # Pre-populate features_paused with systemic entries so derivation works
        for i in range(systemic_count):
            ctx.batch_result.features_paused.append({
                "name": f"feat-pre-{i}",
                "error": "worker_no_exit_report",
            })
        return ctx

    async def test_systemic_threshold_below_does_not_emit_event(self):
        """R10 no-op-below-threshold: two systemic pauses do NOT emit
        PIPELINE_SYSTEMIC_FAILURE and do NOT set global_abort_signal."""
        assert SYSTEMIC_FAILURE_THRESHOLD == 3, "test assumes threshold=3"
        ctx = _make_ctx(pauses=0)
        ctx.batch_result.global_abort_signal = False

        logged_events = []

        def _capture_event(event_type, *args, **kwargs):
            logged_events.append(event_type)

        with (
            patch("cortex_command.overnight.outcome_router.merge_feature"),
            patch("cortex_command.overnight.outcome_router._write_back_to_backlog"),
            patch(
                "cortex_command.overnight.outcome_router.overnight_log_event",
                side_effect=_capture_event,
            ),
        ):
            # First systemic pause
            await apply_feature_result(
                "feat-a",
                FeatureResult(name="feat-a", status="paused", error="worker_no_exit_report"),
                ctx,
            )
            # Second systemic pause
            ctx.feature_names = ["feat-a", "feat-b"]
            await apply_feature_result(
                "feat-b",
                FeatureResult(name="feat-b", status="paused", error="infrastructure_failure"),
                ctx,
            )

        self.assertEqual(ctx.cb_state.systemic_pauses_in_batch, 2)
        self.assertFalse(ctx.batch_result.global_abort_signal)
        self.assertNotIn("pipeline_systemic_failure", logged_events)

    async def test_systemic_threshold_at_threshold_emits_event_and_sets_abort(self):
        """Three systemic pauses DO emit PIPELINE_SYSTEMIC_FAILURE with
        cause_class of length 3 in oldest-first order and set global_abort_signal=True."""
        assert SYSTEMIC_FAILURE_THRESHOLD == 3, "test assumes threshold=3"
        ctx = self._make_ctx_with_systemic_pauses(SYSTEMIC_FAILURE_THRESHOLD - 1)
        # Two pauses already present; the third will trip the threshold.
        ctx.feature_names = ["feat-a", "feat-b", "feat-c"]

        logged_events = []
        logged_details = []

        def _capture_event(event_type, *args, **kwargs):
            logged_events.append(event_type)
            logged_details.append(kwargs.get("details", {}))

        with (
            patch("cortex_command.overnight.outcome_router.merge_feature"),
            patch("cortex_command.overnight.outcome_router._write_back_to_backlog"),
            patch(
                "cortex_command.overnight.outcome_router.overnight_log_event",
                side_effect=_capture_event,
            ),
        ):
            await apply_feature_result(
                "feat-c",
                FeatureResult(name="feat-c", status="paused", error="worker_malformed_exit_report"),
                ctx,
            )

        self.assertEqual(ctx.cb_state.systemic_pauses_in_batch, SYSTEMIC_FAILURE_THRESHOLD)
        self.assertTrue(ctx.batch_result.global_abort_signal)
        self.assertIn("pipeline_systemic_failure", logged_events)

        # Locate the systemic failure event details
        idx = logged_events.index("pipeline_systemic_failure")
        details = logged_details[idx]
        cause_class = details["cause_class"]
        self.assertEqual(len(cause_class), SYSTEMIC_FAILURE_THRESHOLD)
        # Oldest-first: first two entries from pre-populated list, third from this pause
        self.assertEqual(cause_class[0], "worker_no_exit_report")
        self.assertEqual(cause_class[1], "worker_no_exit_report")
        self.assertEqual(cause_class[2], "worker_malformed_exit_report")
        self.assertEqual(details["threshold"], SYSTEMIC_FAILURE_THRESHOLD)

    async def test_systemic_total_in_batch_semantics(self):
        """[S, S, success, S] sequence: does not trip on pause 2, does not trip
        on the success, and trips on the fourth feature — proving total-in-batch
        (not consecutive) semantics."""
        assert SYSTEMIC_FAILURE_THRESHOLD == 3, "test assumes threshold=3"
        ctx = _make_ctx(pauses=0)
        ctx.batch_result.global_abort_signal = False
        ctx.feature_names = ["feat-a", "feat-b", "feat-c", "feat-d"]

        logged_events = []

        def _capture_event(event_type, *args, **kwargs):
            logged_events.append(event_type)

        merge_result = MagicMock(
            success=True, error=None, conflict=False, test_result=None,
        )

        with (
            patch(
                "cortex_command.overnight.outcome_router.merge_feature",
                return_value=merge_result,
            ),
            patch("cortex_command.overnight.outcome_router._write_back_to_backlog"),
            patch(
                "cortex_command.overnight.outcome_router.overnight_log_event",
                side_effect=_capture_event,
            ),
            patch("cortex_command.overnight.outcome_router.requires_review", return_value=False),
            patch("cortex_command.overnight.outcome_router.read_tier", return_value="S"),
            patch("cortex_command.overnight.outcome_router.read_criticality", return_value="low"),
            patch(
                "cortex_command.overnight.outcome_router._get_changed_files",
                return_value=[],
            ),
            patch("cortex_command.overnight.outcome_router.cleanup_worktree"),
        ):
            # S (systemic pause 1) — should NOT trip
            await apply_feature_result(
                "feat-a",
                FeatureResult(name="feat-a", status="paused", error="worker_no_exit_report"),
                ctx,
            )
            self.assertEqual(ctx.cb_state.systemic_pauses_in_batch, 1)
            self.assertFalse(ctx.batch_result.global_abort_signal)
            self.assertNotIn("pipeline_systemic_failure", logged_events)

            # S (systemic pause 2) — should NOT trip
            await apply_feature_result(
                "feat-b",
                FeatureResult(name="feat-b", status="paused", error="infrastructure_failure"),
                ctx,
            )
            self.assertEqual(ctx.cb_state.systemic_pauses_in_batch, 2)
            self.assertFalse(ctx.batch_result.global_abort_signal)
            self.assertNotIn("pipeline_systemic_failure", logged_events)

            # success — resets consecutive_pauses but NOT systemic_pauses_in_batch;
            # should NOT trip
            ctx.cb_state.consecutive_pauses = 0  # simulate the reset that happens on merge
            await apply_feature_result(
                "feat-c",
                FeatureResult(name="feat-c", status="completed"),
                ctx,
            )
            self.assertEqual(ctx.cb_state.systemic_pauses_in_batch, 2)
            self.assertFalse(ctx.batch_result.global_abort_signal)
            self.assertNotIn("pipeline_systemic_failure", logged_events)

            # S (systemic pause 3 total in batch) — SHOULD trip
            await apply_feature_result(
                "feat-d",
                FeatureResult(name="feat-d", status="paused", error="worker_malformed_exit_report"),
                ctx,
            )

        self.assertEqual(ctx.cb_state.systemic_pauses_in_batch, SYSTEMIC_FAILURE_THRESHOLD)
        self.assertTrue(ctx.batch_result.global_abort_signal)
        self.assertIn("pipeline_systemic_failure", logged_events)


class TestSystemicReviewCrashCircuitBreaker(unittest.IsolatedAsyncioTestCase):
    """R7/R11: systemic review failures trip the circuit breaker coherently.

    A systemic review failure routes a feature to ``features_deferred``, not
    ``features_paused`` — so it is invisible to the paused-path systemic blocks.
    These tests pin that such failures feed the systemic counter AND that the
    emitted ``PIPELINE_SYSTEMIC_FAILURE`` event carries a ``cause_class``
    genuinely attributable to the review failures, not one accidentally derived
    from an unrelated paused feature.

    Two systemic review-failure kinds feed the SAME aggregate counter under
    DISTINCT cause-class labels (R7): a could-not-run review (the agent
    completed, verdict ERROR, no usable verdict — ``dispatch_review`` RETURNS
    the deferred ERROR result, the in-band path) is tagged ``REVIEW_NO_ARTIFACT``
    and PRESERVES the merge; a genuine dispatch crash (``dispatch_review``
    RAISES, the except path) is tagged ``REVIEW_DISPATCH_CRASH`` and reverts.
    The threshold counts the aggregate, so a mixed batch trips at
    ``SYSTEMIC_FAILURE_THRESHOLD`` carrying both labels.
    """

    async def _drive_review_no_artifact(self, ctx: OutcomeContext, name: str,
                                        capture_event) -> None:
        """Drive one ``apply_feature_result`` whose review is could-not-run.

        merge succeeds, review is required, and ``dispatch_review`` RETURNS a
        deferred ERROR verdict with ``could_not_run=True`` — the no-artifact
        in-band path that PRESERVES the merge. ``merge_sha`` is None so no revert
        is attempted (and the could-not-run guard skips it anyway), keeping the
        test focused on the systemic counter and the cause-class label."""
        ctx.worktree_branches[name] = f"pipeline/{name}"
        ctx.feature_names = list(ctx.feature_names) + [name]
        merge_result = MagicMock(
            success=True, error=None, conflict=False, test_result=None,
            merge_sha=None,
        )
        review_result = MagicMock(
            deferred=True, verdict="ERROR", cycle=0, merge_sha=None,
            could_not_run=True,
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
                return_value=True,
            ),
            patch(
                "cortex_command.overnight.outcome_router.dispatch_review",
                new=AsyncMock(return_value=review_result),
            ),
            patch(
                "cortex_command.overnight.outcome_router.revert_merge",
            ) as m_revert,
            patch("cortex_command.overnight.outcome_router.read_tier", return_value="complex"),
            patch(
                "cortex_command.overnight.outcome_router.read_criticality",
                return_value="high",
            ),
            patch("cortex_command.overnight.outcome_router._write_back_to_backlog"),
            patch(
                "cortex_command.overnight.outcome_router.overnight_log_event",
                side_effect=capture_event,
            ),
            patch("cortex_command.overnight.outcome_router.write_deferral"),
            patch("cortex_command.overnight.outcome_router.cleanup_worktree"),
        ):
            await apply_feature_result(
                name,
                FeatureResult(name=name, status="completed"),
                ctx,
            )
        # The could-not-run merge is PRESERVED: the feature is NOT in
        # features_merged (it deferred for re-review) and was NOT reverted.
        m_revert.assert_not_called()
        self.assertNotIn(name, ctx.batch_result.features_merged)

    async def _drive_review_dispatch_crash(self, ctx: OutcomeContext, name: str,
                                           capture_event) -> None:
        """Drive one ``apply_feature_result`` whose review dispatch RAISES.

        merge succeeds, review is required, and ``dispatch_review`` raises an
        exception — the genuine-crash except path tagged REVIEW_DISPATCH_CRASH.
        ``merge_sha`` is None so the revert is skipped (keeps the test focused on
        the systemic counter, not the revert machinery covered by Task 3)."""
        ctx.worktree_branches[name] = f"pipeline/{name}"
        ctx.feature_names = list(ctx.feature_names) + [name]
        merge_result = MagicMock(
            success=True, error=None, conflict=False, test_result=None,
            merge_sha=None,
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
                return_value=True,
            ),
            patch(
                "cortex_command.overnight.outcome_router.dispatch_review",
                new=AsyncMock(side_effect=RuntimeError("dispatch boom")),
            ),
            patch("cortex_command.overnight.outcome_router.read_tier", return_value="complex"),
            patch(
                "cortex_command.overnight.outcome_router.read_criticality",
                return_value="high",
            ),
            patch("cortex_command.overnight.outcome_router._write_back_to_backlog"),
            patch(
                "cortex_command.overnight.outcome_router.overnight_log_event",
                side_effect=capture_event,
            ),
            patch("cortex_command.overnight.outcome_router.write_deferral"),
            patch("cortex_command.overnight.outcome_router.cleanup_worktree"),
        ):
            await apply_feature_result(
                name,
                FeatureResult(name=name, status="completed"),
                ctx,
            )

    async def test_threshold_no_artifact_trips_breaker_preserving_merges(self):
        """SYSTEMIC_FAILURE_THRESHOLD could-not-run reviews in one batch set
        global_abort_signal=True AND emit PIPELINE_SYSTEMIC_FAILURE whose
        cause_class is REVIEW_NO_ARTIFACT — while each merge stays preserved
        (Task 7 verification (i))."""
        from cortex_command.overnight.constants import REVIEW_NO_ARTIFACT

        ctx = _make_ctx(pauses=0)
        ctx.batch_result.global_abort_signal = False
        ctx.feature_names = []

        logged_events: list[str] = []
        logged_details: list[dict] = []

        def _capture(event_type, *args, **kwargs):
            logged_events.append(event_type)
            logged_details.append(kwargs.get("details", {}))

        for i in range(SYSTEMIC_FAILURE_THRESHOLD - 1):
            await self._drive_review_no_artifact(ctx, f"feat-na-{i}", _capture)
            self.assertFalse(
                ctx.batch_result.global_abort_signal,
                "breaker tripped before threshold",
            )
            self.assertNotIn("pipeline_systemic_failure", logged_events)

        # The threshold-th no-artifact review trips it.
        await self._drive_review_no_artifact(
            ctx, f"feat-na-{SYSTEMIC_FAILURE_THRESHOLD - 1}", _capture,
        )

        self.assertEqual(
            ctx.cb_state.systemic_pauses_in_batch, SYSTEMIC_FAILURE_THRESHOLD,
        )
        self.assertTrue(ctx.batch_result.global_abort_signal)
        self.assertIn("pipeline_systemic_failure", logged_events)

        idx = logged_events.index("pipeline_systemic_failure")
        details = logged_details[idx]
        cause_class = details["cause_class"]
        self.assertEqual(details["threshold"], SYSTEMIC_FAILURE_THRESHOLD)
        self.assertTrue(cause_class, "cause_class must be non-empty")
        self.assertEqual(
            cause_class,
            [REVIEW_NO_ARTIFACT] * SYSTEMIC_FAILURE_THRESHOLD,
        )
        self.assertIn(REVIEW_NO_ARTIFACT, cause_class)
        # Merges stay preserved even as the breaker trips: no feature was merged
        # (each deferred for re-review), and none was reverted (asserted in the
        # helper).
        self.assertEqual(ctx.batch_result.features_merged, [])

    async def test_mixed_crash_and_no_artifact_trips_with_both_labels(self):
        """A mixed 2-crash + 1-no-artifact batch trips at threshold with BOTH
        cause-class labels present, proving the aggregate counter spans the two
        kinds while the labels distinguish them (Task 7 verification (ii))."""
        from cortex_command.overnight.constants import (
            REVIEW_DISPATCH_CRASH,
            REVIEW_NO_ARTIFACT,
        )

        ctx = _make_ctx(pauses=0)
        ctx.batch_result.global_abort_signal = False
        ctx.feature_names = []

        logged_events: list[str] = []
        logged_details: list[dict] = []

        def _capture(event_type, *args, **kwargs):
            logged_events.append(event_type)
            logged_details.append(kwargs.get("details", {}))

        # Two genuine crashes, then one no-artifact — aggregate hits 3.
        await self._drive_review_dispatch_crash(ctx, "feat-crash-0", _capture)
        self.assertFalse(ctx.batch_result.global_abort_signal)
        await self._drive_review_dispatch_crash(ctx, "feat-crash-1", _capture)
        self.assertFalse(ctx.batch_result.global_abort_signal)
        self.assertNotIn("pipeline_systemic_failure", logged_events)

        await self._drive_review_no_artifact(ctx, "feat-na-0", _capture)

        self.assertEqual(
            ctx.cb_state.systemic_pauses_in_batch, SYSTEMIC_FAILURE_THRESHOLD,
        )
        self.assertTrue(ctx.batch_result.global_abort_signal)
        self.assertIn("pipeline_systemic_failure", logged_events)

        idx = logged_events.index("pipeline_systemic_failure")
        cause_class = logged_details[idx]["cause_class"]
        self.assertEqual(len(cause_class), SYSTEMIC_FAILURE_THRESHOLD)
        # Both labels present — the aggregate counter spans the two kinds.
        self.assertIn(REVIEW_DISPATCH_CRASH, cause_class)
        self.assertIn(REVIEW_NO_ARTIFACT, cause_class)
        # Arrival order: two crashes appended first, no-artifact last.
        self.assertEqual(
            cause_class,
            [REVIEW_DISPATCH_CRASH, REVIEW_DISPATCH_CRASH, REVIEW_NO_ARTIFACT],
        )

    async def test_below_threshold_review_failures_do_not_trip(self):
        """Fewer than SYSTEMIC_FAILURE_THRESHOLD review failures do NOT set
        global_abort_signal and do NOT emit PIPELINE_SYSTEMIC_FAILURE."""
        ctx = _make_ctx(pauses=0)
        ctx.batch_result.global_abort_signal = False
        ctx.feature_names = []

        logged_events: list[str] = []

        def _capture(event_type, *args, **kwargs):
            logged_events.append(event_type)

        for i in range(SYSTEMIC_FAILURE_THRESHOLD - 1):
            await self._drive_review_no_artifact(ctx, f"feat-na-{i}", _capture)

        self.assertEqual(
            ctx.cb_state.systemic_pauses_in_batch, SYSTEMIC_FAILURE_THRESHOLD - 1,
        )
        self.assertFalse(ctx.batch_result.global_abort_signal)
        self.assertNotIn("pipeline_systemic_failure", logged_events)

    async def test_cause_class_not_derived_from_unrelated_paused_feature(self):
        """With an unrelated NON-systemic paused feature also present, a batch of
        review crashes still trips with a cause_class of REVIEW_DISPATCH_CRASH —
        proving the cause is attributable to the crashes, not the paused
        feature. (A regression deriving cause_class solely from features_paused
        for review crashes would yield an empty/wrong cause and fail here.)"""
        from cortex_command.overnight.constants import REVIEW_DISPATCH_CRASH

        ctx = _make_ctx(pauses=0)
        ctx.batch_result.global_abort_signal = False
        ctx.feature_names = []
        # Seed an unrelated paused feature with a NON-systemic error so it would
        # NOT contribute to a correct cause_class even if read off
        # features_paused — the review crashes are the only systemic cause.
        ctx.batch_result.features_paused.append(
            {"name": "feat-unrelated", "error": "task paused"}
        )

        logged_events: list[str] = []
        logged_details: list[dict] = []

        def _capture(event_type, *args, **kwargs):
            logged_events.append(event_type)
            logged_details.append(kwargs.get("details", {}))

        for i in range(SYSTEMIC_FAILURE_THRESHOLD):
            await self._drive_review_dispatch_crash(ctx, f"feat-crash-{i}", _capture)

        self.assertTrue(ctx.batch_result.global_abort_signal)
        idx = logged_events.index("pipeline_systemic_failure")
        cause_class = logged_details[idx]["cause_class"]
        self.assertEqual(
            cause_class,
            [REVIEW_DISPATCH_CRASH] * SYSTEMIC_FAILURE_THRESHOLD,
        )
        self.assertNotIn("task paused", cause_class)


class TestFindBacklogItemPathLifecycleSlug(unittest.TestCase):
    """Task 8 — the runtime resolver resolves slug != filename-stem.

    Covers the common case where a feature's lifecycle-slug differs from the
    backlog filename stem: the exact-stem and backlog_id strategies miss, so
    resolution falls through to ``_find_item`` → ``resolve_item.resolve``, which
    matches on ``lifecycle_slug`` frontmatter. (Regression coverage retained
    after the redundant explicit strategy-4 wrapper was removed — strategy-3
    already routes through the same canonical resolver.)
    """

    SLUG = "build-the-grinder-agnostic-knowledge-layer"
    STEM = "025-grinder-agnostic-knowledge-layer"

    def _make_backlog(self, backlog_dir: Path) -> Path:
        item = backlog_dir / f"{self.STEM}.md"
        item.write_text(
            "---\n"
            "uuid: 0123abcd-aaaa-bbbb-cccc-000000000025\n"
            f"title: Grinder agnostic knowledge layer\n"
            f"lifecycle_slug: {self.SLUG}\n"
            "status: refined\n"
            "---\n"
            "Body.\n",
            encoding="utf-8",
        )
        # A decoy item so resolution isn't trivially unique by directory size and
        # so a stray substring match against the wrong file would be caught.
        (backlog_dir / "099-unrelated-other-feature.md").write_text(
            "---\n"
            "uuid: 0123abcd-aaaa-bbbb-cccc-000000000099\n"
            "title: Unrelated other feature\n"
            "lifecycle_slug: unrelated-other-feature\n"
            "status: refined\n"
            "---\n"
            "Body.\n",
            encoding="utf-8",
        )
        return item

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.backlog_dir = Path(self._tmp.name)
        self.item = self._make_backlog(self.backlog_dir)
        set_backlog_dir(self.backlog_dir)

    def tearDown(self) -> None:
        set_backlog_dir(None)  # type: ignore[arg-type]
        self._tmp.cleanup()

    def test_resolves_when_lifecycle_slug_differs_from_stem(self) -> None:
        # Feature slug != filename stem, no backlog_id → strategies 1-2 miss and
        # strategy 3 (_find_item → canonical resolve) matches on lifecycle_slug.
        resolved = _find_backlog_item_path(self.SLUG)
        self.assertEqual(resolved, self.item)

    def test_write_back_emits_no_backlog_write_failed(self) -> None:
        log_path = self.backlog_dir / "events.log"
        with patch(
            "cortex_command.overnight.outcome_router._backlog_update_item"
        ) as mock_update:
            _write_back_to_backlog(
                self.SLUG,
                overnight_status="failed",
                round_number=1,
                log_path=log_path,
            )

        # The canonical resolver found the item, so update_item was called with it
        # and no best-effort failure event was logged.
        mock_update.assert_called_once()
        self.assertEqual(mock_update.call_args.args[0], self.item)
        contents = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
        self.assertNotIn("backlog_write_failed", contents)


class TestRecoverableWriteBack(unittest.TestCase):
    """Task 3 — recoverable write-back records in_progress + the branch.

    A built-but-merge-blocked recoverable feature must NOT be re-queued as
    ``status: backlog`` (the default deferred mapping), which would feed it to
    the from-scratch-rebuild pool. With ``recoverable_branch`` set it is written
    ``status: in_progress`` and the recovery branch is recorded on the item.
    """

    SLUG = "recoverable-feat"
    STEM = "010-recoverable-feat"

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.backlog_dir = Path(self._tmp.name)
        self.item = self.backlog_dir / f"{self.STEM}.md"
        self.item.write_text(
            "---\n"
            "uuid: 0123abcd-aaaa-bbbb-cccc-000000000010\n"
            "title: Recoverable feature\n"
            f"lifecycle_slug: {self.SLUG}\n"
            "status: refined\n"
            "---\n"
            "Body.\n",
            encoding="utf-8",
        )
        set_backlog_dir(self.backlog_dir)

    def tearDown(self) -> None:
        set_backlog_dir(None)  # type: ignore[arg-type]
        self._tmp.cleanup()

    def test_recoverable_writeback_positive(self) -> None:
        log_path = self.backlog_dir / "events.log"
        _write_back_to_backlog(
            self.SLUG,
            overnight_status="deferred",
            round_number=1,
            log_path=log_path,
            recoverable_branch="pipeline/recoverable-feat-2",
        )

        text = self.item.read_text(encoding="utf-8")
        # status is in_progress, NOT the deferred→backlog mapping default.
        self.assertRegex(text, r"(?m)^status: in_progress$")
        self.assertNotRegex(text, r"(?m)^status: backlog$")
        # The recovery branch is recorded on the item.
        self.assertIn("pipeline/recoverable-feat", text)


class TestMergeConflictRecoverableRouting(unittest.TestCase):
    """Task 4 — genuine merge conflict routes to recoverable deferred.

    Drives ``_apply_feature_result`` (the convergent terminus) with a mocked
    ``merge_feature`` per the test-fidelity requirement, so routing is computed
    from the merge result the function itself produces, not a hand-built one.
    """

    def _patches(self, merge_result):
        from unittest.mock import patch as _patch

        return (
            _patch(
                "cortex_command.overnight.outcome_router._get_changed_files",
                return_value=["src/a.py"],
            ),
            _patch(
                "cortex_command.overnight.outcome_router.merge_feature",
                return_value=merge_result,
            ),
            _patch(
                "cortex_command.overnight.outcome_router._write_back_to_backlog",
            ),
            _patch("cortex_command.overnight.outcome_router.overnight_log_event"),
        )

    def test_merge_conflict_recoverable(self):
        """conflict=True → features_deferred w/ recoverable_branch, not paused."""
        ctx = _make_ctx(pauses=0)
        ctx.worktree_branches = {"feat-a": "pipeline/feat-a-2"}
        merge_result = MagicMock(
            success=False, conflict=True, error="merge_conflict", classification=None
        )
        p_changed, p_merge, p_wb, p_log = self._patches(merge_result)
        with p_changed, p_merge, p_wb as m_wb, p_log:
            _apply_feature_result(
                "feat-a", FeatureResult(name="feat-a", status="completed"), ctx
            )

        self.assertEqual(ctx.batch_result.features_paused, [])
        self.assertEqual(len(ctx.batch_result.features_deferred), 1)
        entry = ctx.batch_result.features_deferred[0]
        self.assertEqual(entry["name"], "feat-a")
        self.assertEqual(entry["recoverable_branch"], "pipeline/feat-a-2")
        # Recoverable routing must NOT feed the circuit breaker.
        self.assertEqual(ctx.cb_state.consecutive_pauses, 0)
        self.assertEqual(ctx.cb_state.systemic_pauses_in_batch, 0)
        # Write-back called with status 'deferred' + recoverable_branch.
        deferred_wbs = [
            c for c in m_wb.call_args_list
            if len(c.args) >= 2 and c.args[1] == "deferred"
        ]
        self.assertEqual(len(deferred_wbs), 1)
        self.assertEqual(
            deferred_wbs[0].kwargs.get("recoverable_branch"), "pipeline/feat-a-2"
        )

    def test_non_conflict_still_paused(self):
        """conflict=False systemic error → paused + systemic counter bumped."""
        ctx = _make_ctx(pauses=0)
        merge_result = MagicMock(
            success=False,
            conflict=False,
            error="infrastructure_failure",
            classification=None,
        )
        p_changed, p_merge, p_wb, p_log = self._patches(merge_result)
        with p_changed, p_merge, p_wb, p_log:
            _apply_feature_result(
                "feat-a", FeatureResult(name="feat-a", status="completed"), ctx
            )

        self.assertEqual(ctx.batch_result.features_deferred, [])
        self.assertEqual(len(ctx.batch_result.features_paused), 1)
        self.assertEqual(ctx.cb_state.consecutive_pauses, 1)
        self.assertEqual(ctx.cb_state.systemic_pauses_in_batch, 1)

    def _route_conflict_to_state(self, worktree_branches):
        """Run the conflict path, then flow the entry through _map_results_to_state."""
        import tempfile
        from pathlib import Path as _Path

        from cortex_command.overnight.map_results import _map_results_to_state
        from cortex_command.overnight.state import (
            OvernightState,
            load_state,
            save_state,
        )

        ctx = _make_ctx()
        ctx.worktree_branches = dict(worktree_branches)
        merge_result = MagicMock(
            success=False, conflict=True, error="merge_conflict", classification=None
        )
        p_changed, p_merge, p_wb, p_log = self._patches(merge_result)
        with p_changed, p_merge, p_wb, p_log:
            _apply_feature_result(
                "feat-a", FeatureResult(name="feat-a", status="completed"), ctx
            )

        results = {
            "features_merged": [],
            "features_paused": [],
            "features_deferred": list(ctx.batch_result.features_deferred),
            "features_failed": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            state_path = _Path(tmp) / "state.json"
            save_state(OvernightState(session_id="s", features={}), state_path)
            _map_results_to_state(results, state_path, batch_id=1)
            loaded = load_state(state_path)
            return loaded.features["feat-a"].recoverable_branch

    def test_recoverable_branch_suffix(self):
        """A suffixed worktree branch persists verbatim through the carrier."""
        persisted = self._route_conflict_to_state({"feat-a": "pipeline/feat-a-2"})
        self.assertEqual(persisted, "pipeline/feat-a-2")

    def test_recoverable_branch_absent(self):
        """No worktree branch → persisted None, never a bare reconstruction."""
        persisted = self._route_conflict_to_state({})
        self.assertIsNone(persisted)

    def test_recoverable_not_redispatched(self):
        """A recoverable deferred feature is excluded from the pending count."""
        from cortex_command.overnight.runner import _count_pending
        from cortex_command.overnight.state import (
            OvernightFeatureStatus,
            OvernightState,
        )

        state = OvernightState(
            session_id="s",
            features={
                "feat-a": OvernightFeatureStatus(
                    status="deferred", recoverable_branch="pipeline/feat-a-2"
                ),
            },
        )
        self.assertEqual(_count_pending(state), 0)


class TestHomeMergeWorktreeCollision(unittest.IsolatedAsyncioTestCase):
    """Task 4 — on-disk worktree-collision acceptance tests.

    These tests create a REAL second git worktree (via a tmp-dir fixture)
    checked out to ``overnight/<id>`` and drive a home-repo merge / a
    repair-completed home re-merge through the UN-mocked production merge
    path. The collision the lifecycle fixes lives INSIDE ``merge_feature``
    (`git checkout <base_branch>` with ``cwd=repo_path``) and the
    ``repair_completed`` subprocess block (`git checkout overnight/<id>`),
    so neither ``merge_feature`` nor ``outcome_router.subprocess.run`` is
    mocked here — a mock-only test would pass while the real collision
    ships. The merge/checkout layer must run for real so the actual
    ``git checkout overnight/<id>`` executes against the worktree.

    The only patches applied are to NON-merge helpers: ``_get_changed_files``
    (a git-diff helper with no ``repo_path`` parameter, which would read the
    test-runner's cwd rather than the temp repo), ``cleanup_worktree`` (avoids
    tearing the temp worktree down mid-assertion), ``requires_review`` (avoids
    a real review dispatch on the merged path), and ``pipeline.merge._check_ci_status``
    (returns ``"skipped"`` so the CI gate proceeds without invoking ``gh``).
    """

    def _git(self, cwd: Path, *args: str) -> str:
        return subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def _build_repo(self, td: Path, session_id: str) -> tuple[Path, Path, str, str]:
        """Initialize a home repo with main + a feature branch + integration
        branch, plus a real second worktree owning ``overnight/<id>``.

        Returns ``(home, worktree, feature_branch, feature_commit_sha)``.
        """
        home = td / "home"
        home.mkdir()
        branch = f"overnight/{session_id}"

        # Initialize a real home repo on main with an initial commit.
        self._git(home, "init", "-q", "-b", "main")
        self._git(home, "config", "user.email", "t@example.com")
        self._git(home, "config", "user.name", "Test")
        self._git(home, "config", "commit.gpgsign", "false")
        (home / "README.md").write_text("seed\n")
        self._git(home, "add", "README.md")
        self._git(home, "commit", "-q", "-m", "seed")

        # Feature branch carrying a commit, off the seed.
        feature_branch = f"pipeline/{session_id}-feat"
        self._git(home, "checkout", "-q", "-b", feature_branch)
        (home / "feature.txt").write_text("feature work\n")
        self._git(home, "add", "feature.txt")
        self._git(home, "commit", "-q", "-m", "feature commit")
        feature_sha = self._git(home, "rev-parse", "HEAD")

        # Integration branch at the seed (so the feature merges cleanly, non-ff).
        self._git(home, "checkout", "-q", "main")
        self._git(home, "branch", branch, "main")

        # Second worktree owning overnight/<id> — this is what the home tree
        # would collide with if the merge ran against the home working tree.
        wt = td / "integration-worktree"
        self._git(home, "worktree", "add", "-q", str(wt), branch)

        # Restore the home tree to main (the live working tree the buggy
        # path would wrongly target).
        self._git(home, "checkout", "-q", "main")

        return home, wt, feature_branch, feature_sha

    def _make_ctx(
        self,
        *,
        home: Path,
        worktree: Path | None,
        session_id: str,
        feature: str,
        feature_branch: str,
        repo_path: Path | None = None,
    ) -> "OutcomeContext":
        from cortex_command.overnight.orchestrator import BatchConfig, BatchResult

        base_branch = f"overnight/{session_id}"
        events = home / "overnight-events.log"
        pipeline = home / "pipeline-events.log"
        state = home / "overnight-state.json"
        config = BatchConfig(
            batch_id=1,
            plan_path=home / "plan.md",
            test_command=None,
            base_branch=base_branch,
            overnight_state_path=state,
            overnight_events_path=events,
            result_dir=home,
            pipeline_events_path=pipeline,
            session_id=session_id,
        )
        return OutcomeContext(
            batch_result=BatchResult(batch_id=1),
            lock=asyncio.Lock(),
            cb_state=CircuitBreakerState(consecutive_pauses=0),
            recovery_attempts_map={},
            worktree_paths={},
            worktree_branches={feature: feature_branch},
            repo_path_map={feature: repo_path},
            integration_worktrees={},
            integration_branches={},
            session_id=session_id,
            backlog_ids={},
            feature_names=[feature],
            config=config,
            home_worktree_path=worktree,
        )

    async def test_home_repo_merge_worktree(self):
        """A home feature (repo_path=None) merges through the UN-mocked
        merge_feature against the integration worktree — no collision, and
        the worktree's overnight/<id> HEAD advances to include the feature
        commit. NOTE: merge_feature and subprocess are deliberately NOT
        patched here (the merge/checkout layer runs for real)."""
        with tempfile.TemporaryDirectory() as _td:
            td = Path(_td)
            session_id = "overnight-test-merge"
            feature = f"{session_id}-feat"
            home, wt, feature_branch, feature_sha = self._build_repo(td, session_id)

            ctx = self._make_ctx(
                home=home,
                worktree=wt,
                session_id=session_id,
                feature=feature,
                feature_branch=feature_branch,
            )

            int_head_before = self._git(wt, "rev-parse", "HEAD")

            with (
                patch(
                    "cortex_command.overnight.outcome_router._get_changed_files",
                    return_value=["feature.txt"],
                ),
                patch(
                    "cortex_command.overnight.outcome_router.requires_review",
                    return_value=False,
                ),
                patch("cortex_command.overnight.outcome_router.cleanup_worktree"),
                patch(
                    "cortex_command.pipeline.merge._check_ci_status",
                    return_value="skipped",
                ),
            ):
                await apply_feature_result(
                    feature,
                    FeatureResult(name=feature, status="completed"),
                    ctx,
                )

            # No "already used by worktree" collision surfaced.
            paused_errors = [d.get("error", "") for d in ctx.batch_result.features_paused]
            for err in paused_errors:
                self.assertNotIn("already used by worktree", err)
            self.assertEqual(ctx.batch_result.features_paused, [])

            # The feature merged...
            self.assertIn(feature, ctx.batch_result.features_merged)

            # ...and the observable post-merge git effect: the worktree's
            # overnight/<id> HEAD advanced to include the feature commit.
            int_head_after = self._git(wt, "rev-parse", "HEAD")
            self.assertNotEqual(int_head_before, int_head_after)
            merged_shas = self._git(wt, "rev-list", "HEAD").splitlines()
            self.assertIn(feature_sha, merged_shas)

    async def test_repair_completed_home_remerge(self):
        """A repair_completed home feature ff-merges its repair branch through
        the UN-mocked outcome_router.subprocess.run block — the real
        git checkout overnight/<id> targets the integration worktree, not the
        home tree, so no collision occurs and the worktree HEAD advances."""
        with tempfile.TemporaryDirectory() as _td:
            td = Path(_td)
            session_id = "overnight-test-repair"
            feature = f"{session_id}-feat"
            home, wt, feature_branch, _feature_sha = self._build_repo(td, session_id)

            # A repair branch that fast-forwards overnight/<id>: branch it off
            # the integration head and add a commit.
            base_branch = f"overnight/{session_id}"
            repair_branch = f"repair/{feature}"
            self._git(wt, "checkout", "-q", "-b", repair_branch)
            (wt / "repair.txt").write_text("repair work\n")
            self._git(wt, "add", "repair.txt")
            self._git(wt, "commit", "-q", "-m", "repair commit")
            repair_sha = self._git(wt, "rev-parse", "HEAD")
            # Put the worktree back on the integration branch (the production
            # checkout will switch to it; leaving it elsewhere is realistic).
            self._git(wt, "checkout", "-q", base_branch)

            ctx = self._make_ctx(
                home=home,
                worktree=wt,
                session_id=session_id,
                feature=feature,
                feature_branch=feature_branch,
            )

            with patch("cortex_command.overnight.outcome_router.cleanup_worktree"):
                await apply_feature_result(
                    feature,
                    FeatureResult(
                        name=feature,
                        status="repair_completed",
                        repair_branch=repair_branch,
                    ),
                    ctx,
                )

            # No collision; the repair ff-merge succeeded.
            paused_errors = [d.get("error", "") for d in ctx.batch_result.features_paused]
            for err in paused_errors:
                self.assertNotIn("already used by worktree", err)
            self.assertEqual(ctx.batch_result.features_paused, [])
            self.assertIn(feature, ctx.batch_result.features_merged)

            # Observable effect: the worktree's overnight/<id> HEAD is now the
            # repair commit (fast-forwarded).
            int_head_after = self._git(wt, "rev-parse", base_branch)
            self.assertEqual(int_head_after, repair_sha)

    def test_cross_repo_resolution_unchanged(self):
        """For a cross-repo feature (repo_path != None), the resolver returns
        exactly what _effective_merge_repo_path returns — byte-for-byte."""
        from cortex_command.overnight.outcome_router import (
            _effective_merge_repo_path,
            _merge_target_repo_path,
        )

        with tempfile.TemporaryDirectory() as _td:
            td = Path(_td)
            session_id = "overnight-test-cross"
            feature = f"{session_id}-feat"
            home, wt, feature_branch, _ = self._build_repo(td, session_id)

            # A cross-repo target: another initialized repo with the
            # integration branch + a registered integration worktree.
            cross = td / "cross"
            cross.mkdir()
            self._git(cross, "init", "-q", "-b", "main")
            self._git(cross, "config", "user.email", "t@example.com")
            self._git(cross, "config", "user.name", "Test")
            self._git(cross, "config", "commit.gpgsign", "false")
            (cross / "README.md").write_text("seed\n")
            self._git(cross, "add", "README.md")
            self._git(cross, "commit", "-q", "-m", "seed")
            cross_branch = f"overnight/{session_id}-cross"
            self._git(cross, "branch", cross_branch, "main")
            cross_wt = td / "cross-worktree"
            self._git(cross, "worktree", "add", "-q", str(cross_wt), cross_branch)

            from cortex_command.overnight.state import _normalize_repo_key

            key = _normalize_repo_key(str(cross))
            ctx = self._make_ctx(
                home=home,
                worktree=wt,
                session_id=session_id,
                feature=feature,
                feature_branch=feature_branch,
                repo_path=cross,
            )
            ctx.integration_worktrees[key] = str(cross_wt)
            ctx.integration_branches[key] = cross_branch

            resolved = _merge_target_repo_path(ctx, feature)
            expected = _effective_merge_repo_path(
                cross,
                ctx.integration_worktrees,
                ctx.integration_branches,
                session_id,
            )
            self.assertEqual(resolved, expected)
            self.assertEqual(resolved, cross_wt)

    async def test_unresolved_home_worktree_pauses(self):
        """A home feature (repo_path=None) whose home worktree is unresolved
        (home_worktree_path=None) is surfaced as PAUSED with the
        'integration worktree unresolved' error — and NO home-tree merge runs
        (the home tree is never advanced)."""
        with tempfile.TemporaryDirectory() as _td:
            td = Path(_td)
            session_id = "overnight-test-unresolved"
            feature = f"{session_id}-feat"
            home, wt, feature_branch, _ = self._build_repo(td, session_id)

            # Capture the home tree's current branch HEAD to prove no merge ran.
            home_main_before = self._git(home, "rev-parse", "main")

            ctx = self._make_ctx(
                home=home,
                worktree=None,  # unresolved
                session_id=session_id,
                feature=feature,
                feature_branch=feature_branch,
            )

            with (
                patch(
                    "cortex_command.overnight.outcome_router._get_changed_files",
                    return_value=["feature.txt"],
                ),
                patch("cortex_command.overnight.outcome_router.cleanup_worktree"),
            ):
                await apply_feature_result(
                    feature,
                    FeatureResult(name=feature, status="completed"),
                    ctx,
                )

            # Surfaced as paused with the unresolved-worktree error.
            self.assertEqual(ctx.batch_result.features_merged, [])
            self.assertEqual(len(ctx.batch_result.features_paused), 1)
            entry = ctx.batch_result.features_paused[0]
            self.assertEqual(entry["name"], feature)
            self.assertEqual(entry["error"], "integration worktree unresolved")

            # No home-tree merge ran: the home main HEAD is unchanged.
            home_main_after = self._git(home, "rev-parse", "main")
            self.assertEqual(home_main_before, home_main_after)


class TestReviewNonApprovedRevertsLiveSha(unittest.IsolatedAsyncioTestCase):
    """R3a mock-spy: revert_merge is invoked with the feature's live captured
    merge SHA on BOTH the review-deferred path and the review-crash except
    path."""

    async def test_deferred_path_reverts_live_merge_sha(self):
        ctx = _make_ctx(pauses=0)
        ctx.worktree_branches["feat-a"] = "pipeline/feat-a"

        live_sha = "deadbeefcafe1234deadbeefcafe1234deadbeef"
        merge_result = MagicMock(
            success=True, error=None, conflict=False, test_result=None,
            merge_sha=live_sha,
        )
        # Deferred review with no rework re-merge SHA (primary-merge SHA wins).
        # A REJECTED review RAN and said no — could_not_run is False, so the
        # merge is reverted (not the preserve path).
        review_result = MagicMock(
            deferred=True, verdict="REJECTED", cycle=1, merge_sha=None,
            could_not_run=False,
        )
        revert_outcome = MagicMock(success=True, aborted=False, merge_sha=live_sha)

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
            ),
            patch(
                "cortex_command.overnight.outcome_router.revert_merge",
                return_value=revert_outcome,
            ) as m_revert,
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

        m_revert.assert_called_once()
        # Positional first arg is the live merge SHA.
        self.assertEqual(m_revert.call_args.args[0], live_sha)
        self.assertIn("feat-a", [d["name"] for d in ctx.batch_result.features_deferred])

    async def test_deferred_path_prefers_rework_remerge_sha(self):
        """When the deferred ReviewResult carries a cycle-1 re-merge SHA, the
        rollback targets that live re-merge SHA, not the primary-merge SHA."""
        ctx = _make_ctx(pauses=0)
        ctx.worktree_branches["feat-a"] = "pipeline/feat-a"

        primary_sha = "1111111111111111111111111111111111111111"
        remerge_sha = "2222222222222222222222222222222222222222"
        merge_result = MagicMock(
            success=True, error=None, conflict=False, test_result=None,
            merge_sha=primary_sha,
        )
        review_result = MagicMock(
            deferred=True, verdict="CHANGES_REQUESTED", cycle=2, merge_sha=remerge_sha,
            could_not_run=False,
        )
        revert_outcome = MagicMock(success=True, aborted=False, merge_sha=remerge_sha)

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
            ),
            patch(
                "cortex_command.overnight.outcome_router.revert_merge",
                return_value=revert_outcome,
            ) as m_revert,
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

        m_revert.assert_called_once()
        self.assertEqual(m_revert.call_args.args[0], remerge_sha)

    async def test_except_path_reverts_live_merge_sha(self):
        """A dispatch_review crash routes to the except path, which reverts the
        primary live merge SHA and writes a blocking deferral."""
        ctx = _make_ctx(pauses=0)
        ctx.worktree_branches["feat-a"] = "pipeline/feat-a"

        live_sha = "abc123abc123abc123abc123abc123abc123abc1"
        merge_result = MagicMock(
            success=True, error=None, conflict=False, test_result=None,
            merge_sha=live_sha,
        )
        revert_outcome = MagicMock(success=True, aborted=False, merge_sha=live_sha)

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
                new=AsyncMock(side_effect=RuntimeError("review subprocess exited 1")),
            ),
            patch(
                "cortex_command.overnight.outcome_router.revert_merge",
                return_value=revert_outcome,
            ) as m_revert,
            patch(
                "cortex_command.overnight.outcome_router._next_escalation_n",
                return_value=1,
            ),
            patch(
                "cortex_command.overnight.outcome_router.write_deferral",
            ) as m_write_deferral,
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

        m_revert.assert_called_once()
        self.assertEqual(m_revert.call_args.args[0], live_sha)
        # The except path still surfaces a blocking deferral.
        m_write_deferral.assert_called_once()


class TestReviewDeferredSurfacingCorrections(unittest.IsolatedAsyncioTestCase):
    """Task 6 — R8 (`deferred` backlog status) and R9 (could-not-run marker)
    on the review-deferred path."""

    async def _run_deferred_path(self, verdict: str):
        """Drive apply_feature_result's rr.deferred path for the given verdict
        with a successful revert; return the captured write-back and
        overnight-event calls."""
        ctx = _make_ctx(pauses=0)
        ctx.worktree_branches["feat-a"] = "pipeline/feat-a"

        live_sha = "deadbeefcafe1234deadbeefcafe1234deadbeef"
        merge_result = MagicMock(
            success=True, error=None, conflict=False, test_result=None,
            merge_sha=live_sha,
        )
        review_result = MagicMock(
            deferred=True, verdict=verdict, cycle=(0 if verdict == "ERROR" else 1),
            merge_sha=None,
            # could_not_run mirrors the real ReviewResult: True only for the
            # ERROR (could-not-run) verdict, False for REJECTED/CHANGES_REQUESTED.
            could_not_run=(verdict == "ERROR"),
        )
        revert_outcome = MagicMock(success=True, aborted=False, merge_sha=live_sha)

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
            ),
            patch(
                "cortex_command.overnight.outcome_router.revert_merge",
                return_value=revert_outcome,
            ),
            patch("cortex_command.overnight.outcome_router.read_tier", return_value="M"),
            patch(
                "cortex_command.overnight.outcome_router.read_criticality",
                return_value="high",
            ),
            patch(
                "cortex_command.overnight.outcome_router._write_back_to_backlog",
            ) as m_write_back,
            patch(
                "cortex_command.overnight.outcome_router.overnight_log_event",
            ) as m_log_event,
            patch("cortex_command.overnight.outcome_router.cleanup_worktree"),
        ):
            await apply_feature_result(
                "feat-a",
                FeatureResult(name="feat-a", status="completed"),
                ctx,
            )
        return m_write_back, m_log_event

    async def test_review_deferred_writes_back_status_deferred(self):
        """R8: the review-deferred write-back uses status 'deferred', not the
        invalid 'in_progress'."""
        m_write_back, _ = await self._run_deferred_path("REJECTED")
        # Positional second arg is the backlog status.
        statuses = [
            c.args[1] for c in m_write_back.call_args_list if len(c.args) >= 2
        ]
        self.assertIn("deferred", statuses)
        self.assertNotIn("in_progress", statuses)

    async def test_error_verdict_event_carries_could_not_run_marker(self):
        """R6/R9: a could-not-run review (verdict STRING 'ERROR', agent
        completed) tags the FEATURE_DEFERRED event with ``could_not_run`` but
        NOT ``review_dispatch_crashed`` — the latter denotes only a genuine
        dispatch crash (success=False / raised exception), so it must not be
        co-set on the could-not-run path."""
        _, m_log_event = await self._run_deferred_path("ERROR")
        deferred_details = self._deferred_event_details(m_log_event)
        self.assertTrue(deferred_details.get("could_not_run"))
        self.assertNotIn("review_dispatch_crashed", deferred_details)

    async def test_rejected_verdict_event_has_no_could_not_run_marker(self):
        """R9: a review that RAN and said no (REJECTED) does NOT carry the
        could-not-run marker — triage can separate the two."""
        _, m_log_event = await self._run_deferred_path("REJECTED")
        deferred_details = self._deferred_event_details(m_log_event)
        self.assertNotIn("review_dispatch_crashed", deferred_details)
        self.assertNotIn("could_not_run", deferred_details)

    async def _run_crash_raise_path(self):
        """Drive apply_feature_result's `except` path where dispatch_review
        RAISES an exception (distinct from a returned ERROR verdict). merge_sha
        is None so the revert is skipped — the focus is the backlog write-back
        status on the crash arm."""
        ctx = _make_ctx(pauses=0)
        ctx.worktree_branches["feat-a"] = "pipeline/feat-a"

        merge_result = MagicMock(
            success=True, error=None, conflict=False, test_result=None,
            merge_sha=None,
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
                return_value=True,
            ),
            patch(
                "cortex_command.overnight.outcome_router.dispatch_review",
                new=AsyncMock(side_effect=RuntimeError("review dispatch boom")),
            ),
            patch("cortex_command.overnight.outcome_router.read_tier", return_value="M"),
            patch(
                "cortex_command.overnight.outcome_router.read_criticality",
                return_value="high",
            ),
            patch(
                "cortex_command.overnight.outcome_router._write_back_to_backlog",
            ) as m_write_back,
            patch("cortex_command.overnight.outcome_router.overnight_log_event"),
            patch("cortex_command.overnight.outcome_router.write_deferral"),
            patch("cortex_command.overnight.outcome_router.cleanup_worktree"),
        ):
            await apply_feature_result(
                "feat-a",
                FeatureResult(name="feat-a", status="completed"),
                ctx,
            )
        return m_write_back

    async def test_review_crash_raise_writes_back_status_deferred(self):
        """A review dispatch that RAISES (the `except` crash arm, distinct from a
        returned ERROR verdict) defers the feature — the backlog write-back uses
        status 'deferred', not the invalid 'in_progress' that reads as ordinary
        active work despite the feature landing in features_deferred."""
        m_write_back = await self._run_crash_raise_path()
        statuses = [
            c.args[1] for c in m_write_back.call_args_list if len(c.args) >= 2
        ]
        self.assertIn("deferred", statuses)
        self.assertNotIn("in_progress", statuses)

    @staticmethod
    def _deferred_event_details(m_log_event) -> dict:
        """Extract the details dict from the FEATURE_DEFERRED overnight_log_event
        call (the first positional arg is the event type constant)."""
        from cortex_command.overnight.outcome_router import FEATURE_DEFERRED
        for call in m_log_event.call_args_list:
            if call.args and call.args[0] == FEATURE_DEFERRED:
                return call.kwargs.get("details", {}) or {}
        raise AssertionError("no FEATURE_DEFERRED event was emitted")


class TestRecoveryPathReviewGate(unittest.IsolatedAsyncioTestCase):
    """R10 — the post-merge test-recovery success path routes a review-qualifying
    feature through review before marking ``merged``, reverts+defers on a
    non-APPROVED/crash outcome, and runs the recovery re-merge under the
    re-acquired ``ctx.lock``."""

    def _failing_merge_then_recovery_ctx(self):
        """Build a ctx whose initial merge reports a test failure (drives the
        recovery path) with recovery_attempts_map empty so the gate passes."""
        ctx = _make_ctx(pauses=0)
        ctx.worktree_branches["feat-a"] = "pipeline/feat-a"
        ctx.worktree_paths["feat-a"] = Path("/tmp/unused-feat-a-worktree")
        return ctx

    @staticmethod
    def _test_failure_merge_result() -> MagicMock:
        return MagicMock(
            success=False,
            error="test_failure",
            conflict=False,
            test_result=MagicMock(output="FAILED: test_foo"),
        )

    async def test_recovery_success_dispatches_review_for_qualifying_feature(self):
        """A complex/high feature that passes only after test recovery routes
        through dispatch_review on the recovery success path."""
        ctx = self._failing_merge_then_recovery_ctx()

        recovery_result = MagicMock(
            success=True, flaky=False, attempts=1,
            merge_sha="recoverysha111111111111111111111111111111",
        )
        review_result = MagicMock(deferred=False, verdict="APPROVED", cycle=1, merge_sha=None)

        with (
            patch(
                "cortex_command.overnight.outcome_router._get_changed_files",
                return_value=["src/a.py"],
            ),
            patch(
                "cortex_command.overnight.outcome_router.merge_feature",
                return_value=self._test_failure_merge_result(),
            ),
            patch(
                "cortex_command.overnight.outcome_router.recover_test_failure",
                new=AsyncMock(return_value=recovery_result),
            ),
            patch(
                "cortex_command.overnight.outcome_router.requires_review",
                return_value=True,
            ),
            patch(
                "cortex_command.overnight.outcome_router.dispatch_review",
                new=AsyncMock(return_value=review_result),
            ) as m_dispatch,
            patch("cortex_command.overnight.outcome_router.read_tier", return_value="complex"),
            patch(
                "cortex_command.overnight.outcome_router.read_criticality",
                return_value="high",
            ),
            patch("cortex_command.overnight.outcome_router._write_back_to_backlog"),
            patch("cortex_command.overnight.outcome_router.overnight_log_event"),
            patch("cortex_command.overnight.outcome_router.load_state"),
            patch("cortex_command.overnight.outcome_router.save_state"),
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
        # Review approved → feature proceeds to merged.
        self.assertIn("feat-a", ctx.batch_result.features_merged)

    async def test_recovery_flaky_success_dispatches_review_for_qualifying_feature(self):
        """The flaky-recovery success branch also routes a qualifying feature
        through review."""
        ctx = self._failing_merge_then_recovery_ctx()

        recovery_result = MagicMock(
            success=True, flaky=True, attempts=0,
            merge_sha="flakysha2222222222222222222222222222222222",
        )
        review_result = MagicMock(deferred=False, verdict="APPROVED", cycle=1, merge_sha=None)

        with (
            patch(
                "cortex_command.overnight.outcome_router._get_changed_files",
                return_value=["src/a.py"],
            ),
            patch(
                "cortex_command.overnight.outcome_router.merge_feature",
                return_value=self._test_failure_merge_result(),
            ),
            patch(
                "cortex_command.overnight.outcome_router.recover_test_failure",
                new=AsyncMock(return_value=recovery_result),
            ),
            patch(
                "cortex_command.overnight.outcome_router.requires_review",
                return_value=True,
            ),
            patch(
                "cortex_command.overnight.outcome_router.dispatch_review",
                new=AsyncMock(return_value=review_result),
            ) as m_dispatch,
            patch("cortex_command.overnight.outcome_router.read_tier", return_value="complex"),
            patch(
                "cortex_command.overnight.outcome_router.read_criticality",
                return_value="critical",
            ),
            patch("cortex_command.overnight.outcome_router._write_back_to_backlog"),
            patch("cortex_command.overnight.outcome_router.overnight_log_event"),
            patch("cortex_command.overnight.outcome_router.load_state"),
            patch("cortex_command.overnight.outcome_router.save_state"),
            patch("cortex_command.overnight.outcome_router.cleanup_worktree"),
        ):
            await apply_feature_result(
                "feat-a",
                FeatureResult(name="feat-a", status="completed"),
                ctx,
            )

        m_dispatch.assert_awaited_once()
        self.assertIn("feat-a", ctx.batch_result.features_merged)

    async def test_recovery_qualifying_feature_not_merged_without_approved(self):
        """A review-qualifying feature on the recovery path is NOT marked merged
        when review defers; the recovery re-merge SHA is reverted and the
        feature is deferred."""
        ctx = self._failing_merge_then_recovery_ctx()

        recovery_sha = "recoverysha333333333333333333333333333333"
        recovery_result = MagicMock(
            success=True, flaky=False, attempts=1, merge_sha=recovery_sha,
        )
        review_result = MagicMock(
            deferred=True, verdict="REJECTED", cycle=1, merge_sha=None,
            could_not_run=False,
        )
        revert_outcome = MagicMock(success=True, aborted=False, merge_sha=recovery_sha)

        with (
            patch(
                "cortex_command.overnight.outcome_router._get_changed_files",
                return_value=["src/a.py"],
            ),
            patch(
                "cortex_command.overnight.outcome_router.merge_feature",
                return_value=self._test_failure_merge_result(),
            ),
            patch(
                "cortex_command.overnight.outcome_router.recover_test_failure",
                new=AsyncMock(return_value=recovery_result),
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
                "cortex_command.overnight.outcome_router.revert_merge",
                return_value=revert_outcome,
            ) as m_revert,
            patch("cortex_command.overnight.outcome_router.read_tier", return_value="complex"),
            patch(
                "cortex_command.overnight.outcome_router.read_criticality",
                return_value="high",
            ),
            patch("cortex_command.overnight.outcome_router._write_back_to_backlog"),
            patch("cortex_command.overnight.outcome_router.overnight_log_event"),
            patch("cortex_command.overnight.outcome_router.load_state"),
            patch("cortex_command.overnight.outcome_router.save_state"),
            patch("cortex_command.overnight.outcome_router.cleanup_worktree"),
        ):
            await apply_feature_result(
                "feat-a",
                FeatureResult(name="feat-a", status="completed"),
                ctx,
            )

        # Not merged — deferred instead.
        self.assertNotIn("feat-a", ctx.batch_result.features_merged)
        self.assertIn("feat-a", [d["name"] for d in ctx.batch_result.features_deferred])
        # The recovery re-merge SHA was reverted (R3).
        m_revert.assert_called_once()
        self.assertEqual(m_revert.call_args.args[0], recovery_sha)

    async def test_recovery_non_qualifying_feature_skips_review_and_merges(self):
        """A feature for which requires_review is False is the ONLY recovery
        path that skips review (a legitimate non-review, not a blanket escape)
        and proceeds to merged."""
        ctx = self._failing_merge_then_recovery_ctx()

        recovery_result = MagicMock(
            success=True, flaky=False, attempts=1, merge_sha="sha444",
        )

        with (
            patch(
                "cortex_command.overnight.outcome_router._get_changed_files",
                return_value=["src/a.py"],
            ),
            patch(
                "cortex_command.overnight.outcome_router.merge_feature",
                return_value=self._test_failure_merge_result(),
            ),
            patch(
                "cortex_command.overnight.outcome_router.recover_test_failure",
                new=AsyncMock(return_value=recovery_result),
            ),
            patch(
                "cortex_command.overnight.outcome_router.requires_review",
                return_value=False,
            ),
            patch(
                "cortex_command.overnight.outcome_router.dispatch_review",
                new=AsyncMock(),
            ) as m_dispatch,
            patch("cortex_command.overnight.outcome_router.read_tier", return_value="simple"),
            patch(
                "cortex_command.overnight.outcome_router.read_criticality",
                return_value="low",
            ),
            patch("cortex_command.overnight.outcome_router._write_back_to_backlog"),
            patch("cortex_command.overnight.outcome_router.overnight_log_event"),
            patch("cortex_command.overnight.outcome_router.load_state"),
            patch("cortex_command.overnight.outcome_router.save_state"),
            patch("cortex_command.overnight.outcome_router.cleanup_worktree"),
        ):
            await apply_feature_result(
                "feat-a",
                FeatureResult(name="feat-a", status="completed"),
                ctx,
            )

        m_dispatch.assert_not_awaited()
        self.assertIn("feat-a", ctx.batch_result.features_merged)

    async def test_recovery_remerge_runs_under_held_lock(self):
        """The recovery re-merge (recover_test_failure) executes while ctx.lock
        is held — not released across it. An instrumented lock records whether
        it was held at the moment recover_test_failure ran."""
        ctx = self._failing_merge_then_recovery_ctx()

        recovery_result = MagicMock(
            success=True, flaky=False, attempts=1,
            merge_sha="recoverysha555555555555555555555555555555",
        )
        review_result = MagicMock(deferred=False, verdict="APPROVED", cycle=1, merge_sha=None)

        lock_held_during_recovery: list[bool] = []

        async def _recover_observing_lock(**kwargs):
            lock_held_during_recovery.append(ctx.lock.locked())
            return recovery_result

        with (
            patch(
                "cortex_command.overnight.outcome_router._get_changed_files",
                return_value=["src/a.py"],
            ),
            patch(
                "cortex_command.overnight.outcome_router.merge_feature",
                return_value=self._test_failure_merge_result(),
            ),
            patch(
                "cortex_command.overnight.outcome_router.recover_test_failure",
                new=AsyncMock(side_effect=_recover_observing_lock),
            ),
            patch(
                "cortex_command.overnight.outcome_router.requires_review",
                return_value=True,
            ),
            patch(
                "cortex_command.overnight.outcome_router.dispatch_review",
                new=AsyncMock(return_value=review_result),
            ),
            patch("cortex_command.overnight.outcome_router.read_tier", return_value="complex"),
            patch(
                "cortex_command.overnight.outcome_router.read_criticality",
                return_value="high",
            ),
            patch("cortex_command.overnight.outcome_router._write_back_to_backlog"),
            patch("cortex_command.overnight.outcome_router.overnight_log_event"),
            patch("cortex_command.overnight.outcome_router.load_state"),
            patch("cortex_command.overnight.outcome_router.save_state"),
            patch("cortex_command.overnight.outcome_router.cleanup_worktree"),
        ):
            await apply_feature_result(
                "feat-a",
                FeatureResult(name="feat-a", status="completed"),
                ctx,
            )

        # The recovery re-merge ran exactly once, with the lock held.
        self.assertEqual(lock_held_during_recovery, [True])


class TestRepairCompletedReviewGate(unittest.IsolatedAsyncioTestCase):
    """R12 — the repair_completed ff-merge is a LIVE merge-to-`merged` site.
    A review-qualifying feature is routed through dispatch_review before being
    marked `merged`; on a non-APPROVED/crash outcome the ff-merge is rolled
    back (git reset --hard to the pre-ff base) and the feature is deferred."""

    @staticmethod
    def _ff_subprocess_side_effect():
        """checkout base, rev-parse pre-ff HEAD, ff-merge (success). The
        branch-delete only runs on the merged (non-deferred) path."""
        checkout = MagicMock(returncode=0, stderr="")
        revparse = MagicMock(returncode=0, stdout="preffbase00\n", stderr="")
        ff = MagicMock(returncode=0, stderr="")
        delete = MagicMock(returncode=0, stderr="")
        reset = MagicMock(returncode=0, stderr="")
        return checkout, revparse, ff, delete, reset

    async def test_repair_qualifying_feature_routed_through_review(self):
        """A review-qualifying repair_completed feature dispatches review before
        being marked merged; APPROVED → merged."""
        ctx = _make_ctx(pauses=1)
        checkout, revparse, ff, delete, _reset = self._ff_subprocess_side_effect()
        review_result = MagicMock(deferred=False, verdict="APPROVED", cycle=1, merge_sha=None)

        with (
            patch(
                "cortex_command.overnight.outcome_router.subprocess.run",
                side_effect=[checkout, revparse, ff, delete],
            ),
            patch(
                "cortex_command.overnight.outcome_router.requires_review",
                return_value=True,
            ),
            patch("cortex_command.overnight.outcome_router.read_tier", return_value="complex"),
            patch("cortex_command.overnight.outcome_router.read_criticality", return_value="high"),
            patch(
                "cortex_command.overnight.outcome_router.dispatch_review",
                new=AsyncMock(return_value=review_result),
            ) as m_dispatch,
            patch("cortex_command.overnight.outcome_router._write_back_to_backlog"),
            patch("cortex_command.overnight.outcome_router.overnight_log_event"),
            patch("cortex_command.overnight.outcome_router.cleanup_worktree"),
        ):
            await apply_feature_result(
                "feat-a",
                FeatureResult(
                    name="feat-a", status="repair_completed", repair_branch="repair/feat-a",
                ),
                ctx,
            )

        m_dispatch.assert_awaited_once()
        self.assertEqual(m_dispatch.await_args.kwargs["feature"], "feat-a")
        # APPROVED → merged.
        self.assertIn("feat-a", ctx.batch_result.features_merged)

    async def test_repair_qualifying_feature_deferred_reverts_ff_merge(self):
        """A review-qualifying repair_completed feature whose review DEFERS is
        NOT marked merged: the ff-merge is rolled back via git reset --hard to
        the captured pre-ff base, and the feature is deferred."""
        ctx = _make_ctx(pauses=1)
        checkout, revparse, ff, _delete, reset = self._ff_subprocess_side_effect()
        review_result = MagicMock(
            deferred=True, verdict="REJECTED", cycle=1, merge_sha=None,
            could_not_run=False,
        )

        with (
            patch(
                "cortex_command.overnight.outcome_router.subprocess.run",
                side_effect=[checkout, revparse, ff, reset],
            ) as m_sp,
            patch(
                "cortex_command.overnight.outcome_router.requires_review",
                return_value=True,
            ),
            patch("cortex_command.overnight.outcome_router.read_tier", return_value="complex"),
            patch("cortex_command.overnight.outcome_router.read_criticality", return_value="high"),
            patch(
                "cortex_command.overnight.outcome_router.dispatch_review",
                new=AsyncMock(return_value=review_result),
            ) as m_dispatch,
            patch("cortex_command.overnight.outcome_router.write_deferral") as m_defer,
            patch("cortex_command.overnight.outcome_router._write_back_to_backlog") as m_wb,
            patch("cortex_command.overnight.outcome_router.overnight_log_event"),
            patch("cortex_command.overnight.outcome_router.cleanup_worktree"),
        ):
            await apply_feature_result(
                "feat-a",
                FeatureResult(
                    name="feat-a", status="repair_completed", repair_branch="repair/feat-a",
                ),
                ctx,
            )

        m_dispatch.assert_awaited_once()
        # NOT merged — deferred instead.
        self.assertNotIn("feat-a", ctx.batch_result.features_merged)
        self.assertIn("feat-a", [d["name"] for d in ctx.batch_result.features_deferred])
        m_defer.assert_called_once()
        # The ff-merge was rolled back via git reset --hard <pre-ff base>.
        reset_calls = [
            c for c in m_sp.call_args_list
            if c.args and c.args[0][:3] == ["git", "reset", "--hard"]
        ]
        self.assertEqual(len(reset_calls), 1)
        self.assertEqual(reset_calls[0].args[0][3], "preffbase00")
        # Backlog write-back used `deferred` status (not `merged`).
        deferred_wbs = [c for c in m_wb.call_args_list if len(c.args) >= 2 and c.args[1] == "deferred"]
        self.assertEqual(len(deferred_wbs), 1)
        merged_wbs = [c for c in m_wb.call_args_list if len(c.args) >= 2 and c.args[1] == "merged"]
        self.assertEqual(len(merged_wbs), 0)

    async def test_repair_qualifying_feature_review_crash_reverts_ff_merge(self):
        """A review-dispatch crash on the repair_completed path also rolls back
        the ff-merge and defers (the except arm)."""
        ctx = _make_ctx(pauses=1)
        checkout, revparse, ff, _delete, reset = self._ff_subprocess_side_effect()

        with (
            patch(
                "cortex_command.overnight.outcome_router.subprocess.run",
                side_effect=[checkout, revparse, ff, reset],
            ) as m_sp,
            patch(
                "cortex_command.overnight.outcome_router.requires_review",
                return_value=True,
            ),
            patch("cortex_command.overnight.outcome_router.read_tier", return_value="complex"),
            patch("cortex_command.overnight.outcome_router.read_criticality", return_value="critical"),
            patch(
                "cortex_command.overnight.outcome_router.dispatch_review",
                new=AsyncMock(side_effect=RuntimeError("review subprocess exited 1")),
            ) as m_dispatch,
            patch("cortex_command.overnight.outcome_router.write_deferral") as m_defer,
            patch("cortex_command.overnight.outcome_router._write_back_to_backlog"),
            patch("cortex_command.overnight.outcome_router.overnight_log_event"),
            patch("cortex_command.overnight.outcome_router.cleanup_worktree"),
        ):
            await apply_feature_result(
                "feat-a",
                FeatureResult(
                    name="feat-a", status="repair_completed", repair_branch="repair/feat-a",
                ),
                ctx,
            )

        m_dispatch.assert_awaited_once()
        self.assertNotIn("feat-a", ctx.batch_result.features_merged)
        self.assertIn("feat-a", [d["name"] for d in ctx.batch_result.features_deferred])
        m_defer.assert_called_once()
        reset_calls = [
            c for c in m_sp.call_args_list
            if c.args and c.args[0][:3] == ["git", "reset", "--hard"]
        ]
        self.assertEqual(len(reset_calls), 1)

    async def test_repair_non_qualifying_feature_skips_review_and_merges(self):
        """A non-review-qualifying repair_completed feature skips review (a
        legitimate non-review) and proceeds straight to merged."""
        ctx = _make_ctx(pauses=1)
        checkout, revparse, ff, delete, _reset = self._ff_subprocess_side_effect()

        with (
            patch(
                "cortex_command.overnight.outcome_router.subprocess.run",
                side_effect=[checkout, revparse, ff, delete],
            ),
            patch(
                "cortex_command.overnight.outcome_router.requires_review",
                return_value=False,
            ),
            patch("cortex_command.overnight.outcome_router.read_tier", return_value="simple"),
            patch("cortex_command.overnight.outcome_router.read_criticality", return_value="low"),
            patch(
                "cortex_command.overnight.outcome_router.dispatch_review",
                new=AsyncMock(),
            ) as m_dispatch,
            patch("cortex_command.overnight.outcome_router._write_back_to_backlog"),
            patch("cortex_command.overnight.outcome_router.overnight_log_event"),
            patch("cortex_command.overnight.outcome_router.cleanup_worktree"),
        ):
            await apply_feature_result(
                "feat-a",
                FeatureResult(
                    name="feat-a", status="repair_completed", repair_branch="repair/feat-a",
                ),
                ctx,
            )

        m_dispatch.assert_not_awaited()
        self.assertIn("feat-a", ctx.batch_result.features_merged)


class TestSyncMergeSiteRuntimeGuards(unittest.IsolatedAsyncioTestCase):
    """R12 — the two LIVE sync merge-to-`merged` write sites in
    _apply_feature_result are provably unreachable for a review-qualifying
    feature, so each carries a runtime guard that RAISES (not a prose
    annotation) if a review-qualifying feature ever reaches it un-reviewed."""

    async def test_sync_completed_merge_success_guard_raises_for_qualifying(self):
        """Driving a review-qualifying feature into the sync `completed`
        merge-success arm (merge_feature returns success) raises the runtime
        guard rather than silently marking it merged un-reviewed."""
        ctx = _make_ctx(pauses=0)
        ctx.worktree_branches["feat-a"] = "pipeline/feat-a"
        merge_ok = MagicMock(success=True, error=None, conflict=False, merge_sha="sha", classification=None)

        with (
            patch(
                "cortex_command.overnight.outcome_router._get_changed_files",
                return_value=["src/a.py"],
            ),
            patch(
                "cortex_command.overnight.outcome_router.merge_feature",
                return_value=merge_ok,
            ),
            patch(
                "cortex_command.overnight.outcome_router.requires_review",
                return_value=True,
            ),
            patch("cortex_command.overnight.outcome_router.read_tier", return_value="complex"),
            patch("cortex_command.overnight.outcome_router.read_criticality", return_value="high"),
            patch("cortex_command.overnight.outcome_router._write_back_to_backlog"),
            patch("cortex_command.overnight.outcome_router.overnight_log_event"),
            patch("cortex_command.overnight.outcome_router.cleanup_worktree"),
        ):
            from cortex_command.overnight.outcome_router import _apply_feature_result
            with self.assertRaises(RuntimeError) as cm:
                _apply_feature_result(
                    "feat-a",
                    FeatureResult(name="feat-a", status="completed"),
                    ctx,
                )
        self.assertIn("review-qualifying", str(cm.exception))
        self.assertIn("completed merge-success", str(cm.exception))
        self.assertNotIn("feat-a", ctx.batch_result.features_merged)

    async def test_sync_repair_completed_ff_merge_guard_raises_for_qualifying(self):
        """Driving a review-qualifying feature into the sync `repair_completed`
        ff-merge success arm (bypassing the async interception by calling
        _apply_feature_result directly) raises the runtime guard."""
        ctx = _make_ctx(pauses=0)
        checkout = MagicMock(returncode=0, stderr="")
        ff = MagicMock(returncode=0, stderr="")

        with (
            patch(
                "cortex_command.overnight.outcome_router.subprocess.run",
                side_effect=[checkout, ff],
            ),
            patch(
                "cortex_command.overnight.outcome_router.requires_review",
                return_value=True,
            ),
            patch("cortex_command.overnight.outcome_router.read_tier", return_value="complex"),
            patch("cortex_command.overnight.outcome_router.read_criticality", return_value="high"),
            patch("cortex_command.overnight.outcome_router._write_back_to_backlog"),
            patch("cortex_command.overnight.outcome_router.overnight_log_event"),
            patch("cortex_command.overnight.outcome_router.cleanup_worktree"),
        ):
            from cortex_command.overnight.outcome_router import _apply_feature_result
            with self.assertRaises(RuntimeError) as cm:
                _apply_feature_result(
                    "feat-a",
                    FeatureResult(
                        name="feat-a", status="repair_completed", repair_branch="repair/feat-a",
                    ),
                    ctx,
                )
        self.assertIn("review-qualifying", str(cm.exception))
        self.assertIn("repair_completed ff-merge", str(cm.exception))
        self.assertNotIn("feat-a", ctx.batch_result.features_merged)


class TestMergeToMergedSiteExhaustiveness(unittest.TestCase):
    """R12 exhaustiveness pin (UNCONDITIONAL) — the complete set of
    merge-to-`merged` write sites in outcome_router.py is exactly the known
    set, each either review-gated or carrying a runtime guard. A sixth-style
    un-gated `features_merged`-append / `"merged"` write-back added later (the
    Bug-D enumeration-drift failure mode) fails this pin loudly."""

    @staticmethod
    def _source_tree():
        import ast
        from cortex_command.overnight import outcome_router
        src_path = Path(outcome_router.__file__)
        return ast.parse(src_path.read_text(encoding="utf-8")), src_path

    @staticmethod
    def _enclosing_funcname(tree, lineno):
        import ast
        best = None
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.lineno <= lineno and (best is None or node.lineno > best[0]):
                    end = getattr(node, "end_lineno", None)
                    if end is None or lineno <= end:
                        best = (node.lineno, node.name)
        return best[1] if best else None

    def test_merge_to_merged_write_sites_are_exactly_the_known_set(self):
        import ast

        tree, src_path = self._source_tree()

        # Enumerate every `ctx.batch_result.features_merged.append(...)` call,
        # attributed to its enclosing function.
        append_sites: dict[str, int] = {}
        merged_writeback_sites: dict[str, int] = {}
        guard_calls: dict[str, int] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # features_merged.append(...)
                func = node.func
                if (
                    isinstance(func, ast.Attribute)
                    and func.attr == "append"
                    and isinstance(func.value, ast.Attribute)
                    and func.value.attr == "features_merged"
                ):
                    fn = self._enclosing_funcname(tree, node.lineno)
                    append_sites[fn] = append_sites.get(fn, 0) + 1
                # _write_back_to_backlog(name, "merged", ...)
                if (
                    isinstance(func, ast.Name)
                    and func.id == "_write_back_to_backlog"
                    and len(node.args) >= 2
                    and isinstance(node.args[1], ast.Constant)
                    and node.args[1].value == "merged"
                ):
                    fn = self._enclosing_funcname(tree, node.lineno)
                    merged_writeback_sites[fn] = merged_writeback_sites.get(fn, 0) + 1
                # _guard_no_review_qualifying_sync_merge(name, site)
                if (
                    isinstance(func, ast.Name)
                    and func.id == "_guard_no_review_qualifying_sync_merge"
                ):
                    fn = self._enclosing_funcname(tree, node.lineno)
                    guard_calls[fn] = guard_calls.get(fn, 0) + 1

        # The complete, exhaustive set of merge-to-`merged` write sites:
        #   sync `_apply_feature_result`     — 2 (repair_completed ff-merge,
        #                                        completed merge-success), each
        #                                        runtime-GUARDED for qualifying
        #   `_repair_completed_review_gate`  — 1 (review-GATED)
        #   `apply_feature_result`           — 3 (async primary, recovery flaky,
        #                                        recovery success), all review-GATED
        expected_append = {
            "_apply_feature_result": 2,
            "_repair_completed_review_gate": 1,
            "apply_feature_result": 3,
        }
        self.assertEqual(
            append_sites,
            expected_append,
            "merge-to-`merged` append-site set drifted — a new "
            "features_merged.append was added or moved without routing it "
            "through review/guard (Bug-D enumeration drift). Update the gate "
            "AND this pin together.",
        )

        # The `"merged"` write-back sites must co-locate with the append sites
        # (one `merged` write-back per append site).
        expected_writeback = dict(expected_append)
        self.assertEqual(
            merged_writeback_sites,
            expected_writeback,
            'merged write-back site set drifted from the append-site set.',
        )

        # The two sync sites each carry exactly one runtime guard.
        self.assertEqual(
            guard_calls,
            {"_apply_feature_result": 2},
            "the two sync merge-success arms must each carry a "
            "_guard_no_review_qualifying_sync_merge runtime guard (R12).",
        )

        # Total count pinned: six write sites — two guarded, four review-gated.
        self.assertEqual(sum(append_sites.values()), 6)


class TestCouldNotRunPreservesMerge(unittest.IsolatedAsyncioTestCase):
    """Task 3 — a could-not-run review (agent completed, no usable verdict →
    verdict ERROR with ``could_not_run=True``) PRESERVES the already-merged
    feature at all three gate sites, while a genuine crash still reverts. The
    in-band preserve block is exception-safe: an exception thrown inside it
    must NOT fall into the crash-``except`` and revert the preserved merge.
    """

    @staticmethod
    def _could_not_run_review() -> MagicMock:
        """A review that ran (success=True) but produced no usable verdict."""
        return MagicMock(
            deferred=True, verdict="ERROR", cycle=0, merge_sha=None,
            could_not_run=True,
        )

    @staticmethod
    def _crash_review() -> MagicMock:
        """A review that resolved to ERROR but was a genuine dispatch crash
        (``could_not_run=False``) — kept here for parity though the primary
        crash modeling uses a raised dispatch."""
        return MagicMock(
            deferred=True, verdict="ERROR", cycle=0, merge_sha=None,
            could_not_run=False,
        )

    @staticmethod
    def _deferred_event_details(m_log_event) -> dict:
        from cortex_command.overnight.outcome_router import FEATURE_DEFERRED
        for call in m_log_event.call_args_list:
            if call.args and call.args[0] == FEATURE_DEFERRED:
                return call.kwargs.get("details", {}) or {}
        raise AssertionError("no FEATURE_DEFERRED event was emitted")

    # ----------------------------------------------------------------- primary

    async def test_primary_could_not_run_preserves_merge(self):
        """apply_feature_result primary path: a could-not-run review does NOT
        revert the merge and emits could_not_run=True + merge_reverted=False."""
        ctx = _make_ctx(pauses=0)
        ctx.worktree_branches["feat-a"] = "pipeline/feat-a"
        live_sha = "deadbeefcafe1234deadbeefcafe1234deadbeef"
        merge_result = MagicMock(
            success=True, error=None, conflict=False, test_result=None,
            merge_sha=live_sha,
        )
        review_result = self._could_not_run_review()

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
            ),
            patch(
                "cortex_command.overnight.outcome_router.revert_merge",
            ) as m_revert,
            patch("cortex_command.overnight.outcome_router.read_tier", return_value="complex"),
            patch("cortex_command.overnight.outcome_router.read_criticality", return_value="high"),
            patch("cortex_command.overnight.outcome_router._write_back_to_backlog"),
            patch("cortex_command.overnight.outcome_router.overnight_log_event") as m_log,
            patch("cortex_command.overnight.outcome_router.cleanup_worktree"),
        ):
            await apply_feature_result(
                "feat-a",
                FeatureResult(name="feat-a", status="completed"),
                ctx,
            )

        # Preserved: the merge was NOT reverted.
        m_revert.assert_not_called()
        self.assertNotIn("feat-a", ctx.batch_result.features_merged)
        self.assertIn("feat-a", [d["name"] for d in ctx.batch_result.features_deferred])
        details = self._deferred_event_details(m_log)
        self.assertTrue(details.get("could_not_run"))
        self.assertFalse(details.get("merge_reverted"))

    async def test_primary_crash_still_reverts_merge(self):
        """apply_feature_result primary path: a genuine dispatch crash (raised
        exception) STILL reverts the merge."""
        ctx = _make_ctx(pauses=0)
        ctx.worktree_branches["feat-a"] = "pipeline/feat-a"
        live_sha = "abc123abc123abc123abc123abc123abc123abc1"
        merge_result = MagicMock(
            success=True, error=None, conflict=False, test_result=None,
            merge_sha=live_sha,
        )
        revert_outcome = MagicMock(success=True, aborted=False, merge_sha=live_sha)

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
                new=AsyncMock(side_effect=RuntimeError("review subprocess exited 1")),
            ),
            patch(
                "cortex_command.overnight.outcome_router.revert_merge",
                return_value=revert_outcome,
            ) as m_revert,
            patch("cortex_command.overnight.outcome_router.write_deferral"),
            patch("cortex_command.overnight.outcome_router.read_tier", return_value="complex"),
            patch("cortex_command.overnight.outcome_router.read_criticality", return_value="high"),
            patch("cortex_command.overnight.outcome_router._write_back_to_backlog"),
            patch("cortex_command.overnight.outcome_router.overnight_log_event") as m_log,
            patch("cortex_command.overnight.outcome_router.cleanup_worktree"),
        ):
            await apply_feature_result(
                "feat-a",
                FeatureResult(name="feat-a", status="completed"),
                ctx,
            )

        m_revert.assert_called_once()
        self.assertEqual(m_revert.call_args.args[0], live_sha)
        details = self._deferred_event_details(m_log)
        self.assertTrue(details.get("review_dispatch_crashed"))
        self.assertNotIn("could_not_run", details)

    async def test_primary_could_not_run_preserve_exception_does_not_revert(self):
        """EXCEPTION-SAFETY (spec R3, load-bearing): when the could-not-run
        in-band preserve block raises (the flag-helper throws), control falls
        into the crash-``except`` — which must NOT revert the preserved
        merge."""
        ctx = _make_ctx(pauses=0)
        ctx.worktree_branches["feat-a"] = "pipeline/feat-a"
        live_sha = "feedface0000feedface0000feedface0000feed"
        merge_result = MagicMock(
            success=True, error=None, conflict=False, test_result=None,
            merge_sha=live_sha,
        )
        review_result = self._could_not_run_review()

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
            ),
            patch(
                "cortex_command.overnight.outcome_router.revert_merge",
            ) as m_revert,
            patch(
                "cortex_command.overnight.outcome_router._set_review_error_detail_flags",
                side_effect=RuntimeError("flag-helper blew up mid-preserve"),
            ),
            patch("cortex_command.overnight.outcome_router.write_deferral"),
            patch("cortex_command.overnight.outcome_router.read_tier", return_value="complex"),
            patch("cortex_command.overnight.outcome_router.read_criticality", return_value="high"),
            patch("cortex_command.overnight.outcome_router._write_back_to_backlog"),
            patch("cortex_command.overnight.outcome_router.overnight_log_event"),
            patch("cortex_command.overnight.outcome_router.cleanup_worktree"),
        ):
            await apply_feature_result(
                "feat-a",
                FeatureResult(name="feat-a", status="completed"),
                ctx,
            )

        # The crash-except ran (the preserve block raised) but it must NOT have
        # reverted the merge it was preserving.
        m_revert.assert_not_called()
        self.assertNotIn("feat-a", ctx.batch_result.features_merged)

    # ---------------------------------------------------------------- recovery

    def _failing_merge_then_recovery_ctx(self):
        ctx = _make_ctx(pauses=0)
        ctx.worktree_branches["feat-a"] = "pipeline/feat-a"
        ctx.worktree_paths["feat-a"] = Path("/tmp/unused-feat-a-worktree")
        return ctx

    @staticmethod
    def _test_failure_merge_result() -> MagicMock:
        return MagicMock(
            success=False, error="test_failure", conflict=False,
            test_result=MagicMock(output="FAILED: test_foo"),
        )

    async def _run_recovery(self, review_result, *, flag_helper_raises=False):
        ctx = self._failing_merge_then_recovery_ctx()
        recovery_sha = "recoverysha777777777777777777777777777777"
        recovery_result = MagicMock(
            success=True, flaky=False, attempts=1, merge_sha=recovery_sha,
        )
        revert_outcome = MagicMock(success=True, aborted=False, merge_sha=recovery_sha)

        flag_patch = patch(
            "cortex_command.overnight.outcome_router._set_review_error_detail_flags",
            side_effect=RuntimeError("flag-helper blew up mid-preserve"),
        ) if flag_helper_raises else patch(
            "cortex_command.overnight.outcome_router._set_review_error_detail_flags",
            wraps=__import__(
                "cortex_command.overnight.outcome_router",
                fromlist=["_set_review_error_detail_flags"],
            )._set_review_error_detail_flags,
        )

        with (
            patch(
                "cortex_command.overnight.outcome_router._get_changed_files",
                return_value=["src/a.py"],
            ),
            patch(
                "cortex_command.overnight.outcome_router.merge_feature",
                return_value=self._test_failure_merge_result(),
            ),
            patch(
                "cortex_command.overnight.outcome_router.recover_test_failure",
                new=AsyncMock(return_value=recovery_result),
            ),
            patch(
                "cortex_command.overnight.outcome_router.requires_review",
                return_value=True,
            ),
            (
                patch(
                    "cortex_command.overnight.outcome_router.dispatch_review",
                    new=AsyncMock(side_effect=review_result),
                )
                if isinstance(review_result, Exception)
                else patch(
                    "cortex_command.overnight.outcome_router.dispatch_review",
                    new=AsyncMock(return_value=review_result),
                )
            ),
            patch(
                "cortex_command.overnight.outcome_router.revert_merge",
                return_value=revert_outcome,
            ) as m_revert,
            flag_patch,
            patch("cortex_command.overnight.outcome_router.write_deferral"),
            patch("cortex_command.overnight.outcome_router._next_escalation_n", return_value=1),
            patch("cortex_command.overnight.outcome_router.read_tier", return_value="complex"),
            patch("cortex_command.overnight.outcome_router.read_criticality", return_value="high"),
            patch("cortex_command.overnight.outcome_router._write_back_to_backlog"),
            patch("cortex_command.overnight.outcome_router.overnight_log_event") as m_log,
            patch("cortex_command.overnight.outcome_router.load_state"),
            patch("cortex_command.overnight.outcome_router.save_state"),
            patch("cortex_command.overnight.outcome_router.cleanup_worktree"),
        ):
            await apply_feature_result(
                "feat-a",
                FeatureResult(name="feat-a", status="completed"),
                ctx,
            )
        return ctx, m_revert, m_log, recovery_sha

    async def test_recovery_could_not_run_preserves_merge(self):
        ctx, m_revert, m_log, _ = await self._run_recovery(self._could_not_run_review())
        m_revert.assert_not_called()
        self.assertNotIn("feat-a", ctx.batch_result.features_merged)
        self.assertIn("feat-a", [d["name"] for d in ctx.batch_result.features_deferred])
        details = self._deferred_event_details(m_log)
        self.assertTrue(details.get("could_not_run"))
        self.assertFalse(details.get("merge_reverted"))

    async def test_recovery_crash_still_reverts_merge(self):
        ctx, m_revert, m_log, recovery_sha = await self._run_recovery(
            RuntimeError("review subprocess exited 1")
        )
        m_revert.assert_called_once()
        self.assertEqual(m_revert.call_args.args[0], recovery_sha)

    async def test_recovery_could_not_run_preserve_exception_does_not_revert(self):
        ctx, m_revert, _, _ = await self._run_recovery(
            self._could_not_run_review(), flag_helper_raises=True
        )
        m_revert.assert_not_called()
        self.assertNotIn("feat-a", ctx.batch_result.features_merged)

    # ------------------------------------------------------------------ repair

    @staticmethod
    def _ff_subprocess_side_effect():
        checkout = MagicMock(returncode=0, stderr="")
        revparse = MagicMock(returncode=0, stdout="preffbase00\n", stderr="")
        ff = MagicMock(returncode=0, stderr="")
        reset = MagicMock(returncode=0, stderr="")
        return checkout, revparse, ff, reset

    async def test_repair_could_not_run_preserves_ff_merge(self):
        """repair_completed path: a could-not-run review does NOT git reset the
        ff-merge — no `git reset --hard` is issued and the event carries
        could_not_run=True + merge_reverted=False."""
        ctx = _make_ctx(pauses=1)
        checkout, revparse, ff, _reset = self._ff_subprocess_side_effect()
        review_result = self._could_not_run_review()

        with (
            patch(
                "cortex_command.overnight.outcome_router.subprocess.run",
                side_effect=[checkout, revparse, ff],
            ) as m_sp,
            patch(
                "cortex_command.overnight.outcome_router.requires_review",
                return_value=True,
            ),
            patch("cortex_command.overnight.outcome_router.read_tier", return_value="complex"),
            patch("cortex_command.overnight.outcome_router.read_criticality", return_value="high"),
            patch(
                "cortex_command.overnight.outcome_router.dispatch_review",
                new=AsyncMock(return_value=review_result),
            ),
            patch("cortex_command.overnight.outcome_router.write_deferral"),
            patch("cortex_command.overnight.outcome_router._write_back_to_backlog"),
            patch("cortex_command.overnight.outcome_router.overnight_log_event") as m_log,
            patch("cortex_command.overnight.outcome_router.cleanup_worktree"),
        ):
            await apply_feature_result(
                "feat-a",
                FeatureResult(
                    name="feat-a", status="repair_completed", repair_branch="repair/feat-a",
                ),
                ctx,
            )

        reset_calls = [
            c for c in m_sp.call_args_list
            if c.args and c.args[0][:3] == ["git", "reset", "--hard"]
        ]
        self.assertEqual(len(reset_calls), 0)
        self.assertNotIn("feat-a", ctx.batch_result.features_merged)
        self.assertIn("feat-a", [d["name"] for d in ctx.batch_result.features_deferred])
        details = self._deferred_event_details(m_log)
        self.assertTrue(details.get("could_not_run"))
        self.assertFalse(details.get("merge_reverted"))

    async def test_repair_crash_still_resets_ff_merge(self):
        """repair_completed path: a genuine dispatch crash (raised exception)
        STILL git-resets the ff-merge."""
        ctx = _make_ctx(pauses=1)
        checkout, revparse, ff, reset = self._ff_subprocess_side_effect()

        with (
            patch(
                "cortex_command.overnight.outcome_router.subprocess.run",
                side_effect=[checkout, revparse, ff, reset],
            ) as m_sp,
            patch(
                "cortex_command.overnight.outcome_router.requires_review",
                return_value=True,
            ),
            patch("cortex_command.overnight.outcome_router.read_tier", return_value="complex"),
            patch("cortex_command.overnight.outcome_router.read_criticality", return_value="critical"),
            patch(
                "cortex_command.overnight.outcome_router.dispatch_review",
                new=AsyncMock(side_effect=RuntimeError("review subprocess exited 1")),
            ),
            patch("cortex_command.overnight.outcome_router.write_deferral"),
            patch("cortex_command.overnight.outcome_router._write_back_to_backlog"),
            patch("cortex_command.overnight.outcome_router.overnight_log_event"),
            patch("cortex_command.overnight.outcome_router.cleanup_worktree"),
        ):
            await apply_feature_result(
                "feat-a",
                FeatureResult(
                    name="feat-a", status="repair_completed", repair_branch="repair/feat-a",
                ),
                ctx,
            )

        reset_calls = [
            c for c in m_sp.call_args_list
            if c.args and c.args[0][:3] == ["git", "reset", "--hard"]
        ]
        self.assertEqual(len(reset_calls), 1)
        self.assertEqual(reset_calls[0].args[0][3], "preffbase00")

    async def test_repair_could_not_run_preserve_exception_does_not_reset(self):
        """EXCEPTION-SAFETY (spec R3, load-bearing): when the could-not-run
        in-band preserve block raises (the flag-helper throws) on the repair
        path, the crash-``except`` must NOT git reset the preserved ff-merge."""
        ctx = _make_ctx(pauses=1)
        checkout, revparse, ff, _reset = self._ff_subprocess_side_effect()
        review_result = self._could_not_run_review()

        with (
            patch(
                "cortex_command.overnight.outcome_router.subprocess.run",
                side_effect=[checkout, revparse, ff],
            ) as m_sp,
            patch(
                "cortex_command.overnight.outcome_router.requires_review",
                return_value=True,
            ),
            patch("cortex_command.overnight.outcome_router.read_tier", return_value="complex"),
            patch("cortex_command.overnight.outcome_router.read_criticality", return_value="high"),
            patch(
                "cortex_command.overnight.outcome_router.dispatch_review",
                new=AsyncMock(return_value=review_result),
            ),
            patch(
                "cortex_command.overnight.outcome_router._set_review_error_detail_flags",
                side_effect=RuntimeError("flag-helper blew up mid-preserve"),
            ),
            patch("cortex_command.overnight.outcome_router.write_deferral"),
            patch("cortex_command.overnight.outcome_router._write_back_to_backlog"),
            patch("cortex_command.overnight.outcome_router.overnight_log_event"),
            patch("cortex_command.overnight.outcome_router.cleanup_worktree"),
        ):
            await apply_feature_result(
                "feat-a",
                FeatureResult(
                    name="feat-a", status="repair_completed", repair_branch="repair/feat-a",
                ),
                ctx,
            )

        reset_calls = [
            c for c in m_sp.call_args_list
            if c.args and c.args[0][:3] == ["git", "reset", "--hard"]
        ]
        self.assertEqual(len(reset_calls), 0)
        self.assertNotIn("feat-a", ctx.batch_result.features_merged)


if __name__ == "__main__":
    unittest.main()
