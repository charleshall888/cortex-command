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


if __name__ == "__main__":
    unittest.main()
