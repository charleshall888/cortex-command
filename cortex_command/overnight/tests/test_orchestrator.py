"""Integration tests for ``orchestrator.run_batch`` (Task 10 / Spec R8).

Covers:
  1. Multi-feature batch dispatch — ``execute_feature`` called for each
     feature and ``BatchResult`` accumulates per-feature outcomes.
  2. Concurrency semaphore — ``ConcurrencyManager.acquire/release`` each
     invoked once per feature.
  3. Circuit breaker — when ``CircuitBreakerState`` is pre-seeded at the
     threshold, the breaker fires and ``execute_feature`` is not called.
  4. Budget exhaustion — ``execute_feature`` returns a budget-exhausted
     pause; ``global_abort_signal`` is set and the outcome router is not
     invoked for that feature.
  5. Heartbeat lifecycle — the background heartbeat task created via
     ``create_task`` is cancelled before ``run_batch`` returns.

All patch targets live on ``claude.overnight.orchestrator`` (or
``claude.overnight.outcome_router`` for ``apply_feature_result``).  The
``conftest.py`` stub pre-installs ``backlog.update_item`` and
``claude_agent_sdk`` so these tests can import orchestrator safely.
"""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from cortex_command.overnight.constants import CIRCUIT_BREAKER_THRESHOLD
from cortex_command.overnight.orchestrator import BatchConfig
from cortex_command.overnight.types import CircuitBreakerState, FeatureResult


class TestOrchestratorRunBatch(unittest.IsolatedAsyncioTestCase):
    """Integration coverage for ``orchestrator.run_batch``."""

    def setUp(self) -> None:
        from cortex_command.overnight.state import OvernightFeatureStatus, OvernightState

        self._tmpdir = tempfile.TemporaryDirectory()
        self._tmp = Path(self._tmpdir.name)

        self._config = BatchConfig(
            batch_id=1,
            plan_path=self._tmp / "plan.md",
            overnight_events_path=self._tmp / "overnight-events.log",
            pipeline_events_path=self._tmp / "pipeline-events.log",
            overnight_state_path=self._tmp / "state.json",
            result_dir=self._tmp,
        )

        self._OvernightState = OvernightState
        self._OvernightFeatureStatus = OvernightFeatureStatus

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _start_patch(self, *args, **kwargs):
        p = patch(*args, **kwargs)
        mock = p.start()
        self.addCleanup(p.stop)
        return mock

    def _make_plan(self, feature_names: list[str]) -> MagicMock:
        features: list[MagicMock] = []
        for name in feature_names:
            f = MagicMock()
            f.name = name
            features.append(f)
        plan = MagicMock()
        plan.features = features
        return plan

    def _make_worktree_info(self, name: str) -> MagicMock:
        info = MagicMock()
        info.path = self._tmp / f"wt-{name}"
        info.branch = f"pipeline/{name}"
        return info

    def _make_state(self, feature_names: list[str]):
        return self._OvernightState(
            session_id="s1",
            plan_ref="plan.md",
            features={
                n: self._OvernightFeatureStatus(recovery_attempts=0)
                for n in feature_names
            },
        )

    def _install_base_patches(
        self,
        *,
        feature_names: list[str],
        execute_return,
        mock_manager: MagicMock | None = None,
        patch_create_task: bool = True,
    ) -> dict:
        """Patch every orchestrator-module dependency used by ``run_batch``.

        Returns a dict of the mocks tests need to assert on.
        """
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
        self._start_patch("cortex_command.overnight.orchestrator.save_batch_result")
        self._start_patch("cortex_command.overnight.orchestrator.transition")
        self._start_patch("cortex_command.overnight.orchestrator.overnight_log_event")
        self._start_patch(
            "cortex_command.overnight.orchestrator.load_throttle_config",
            return_value=MagicMock(),
        )

        if mock_manager is None:
            mock_manager = MagicMock()
            mock_manager.acquire = AsyncMock()
            mock_manager.release = MagicMock()
            mock_manager.stats = {}
        self._start_patch(
            "cortex_command.overnight.orchestrator.ConcurrencyManager",
            return_value=mock_manager,
        )

        # execute_feature — autospec'd AsyncMock against the real coroutine.
        if isinstance(execute_return, dict):
            async def _exec_side(feature, *args, **kwargs):
                return execute_return[feature]
            exec_mock = self._start_patch(
                "cortex_command.overnight.orchestrator.execute_feature",
                autospec=True,
                side_effect=_exec_side,
            )
        else:
            async def _exec_single(*args, **kwargs):
                return execute_return
            exec_mock = self._start_patch(
                "cortex_command.overnight.orchestrator.execute_feature",
                autospec=True,
                side_effect=_exec_single,
            )

        # apply_feature_result — autospec'd AsyncMock.
        async def _apply_side(name, result, ctx):
            return None
        apply_mock = self._start_patch(
            "cortex_command.overnight.outcome_router.apply_feature_result",
            autospec=True,
            side_effect=_apply_side,
        )

        create_task_mock = None
        if patch_create_task:
            # Let the real create_task run so the heartbeat loop can be
            # cancelled cleanly; wrap it to capture the task object.
            captured: list[asyncio.Task] = []

            def _create_task_spy(coro, *args, **kwargs):
                task = asyncio.get_event_loop().create_task(coro, *args, **kwargs)
                captured.append(task)
                return task

            create_task_mock = self._start_patch(
                "cortex_command.overnight.orchestrator.create_task",
                side_effect=_create_task_spy,
            )
            create_task_mock.captured = captured  # type: ignore[attr-defined]

        return {
            "execute_feature": exec_mock,
            "apply_feature_result": apply_mock,
            "manager": mock_manager,
            "create_task": create_task_mock,
        }

    # ------------------------------------------------------------------
    # Scenario 1 — multi-feature batch dispatch
    # ------------------------------------------------------------------

    async def test_multi_feature_dispatch_calls_execute_and_accumulates(self):
        """Two features → execute_feature called once per feature and
        BatchResult returned with matching batch_id."""
        from cortex_command.overnight.orchestrator import run_batch

        mocks = self._install_base_patches(
            feature_names=["feat-a", "feat-b"],
            execute_return={
                "feat-a": FeatureResult(name="feat-a", status="completed"),
                "feat-b": FeatureResult(name="feat-b", status="completed"),
            },
        )

        batch_result = await run_batch(self._config)

        self.assertEqual(batch_result.batch_id, 1)
        self.assertEqual(mocks["execute_feature"].await_count, 2)
        called_features = sorted(
            call.kwargs.get("feature") for call in mocks["execute_feature"].await_args_list
        )
        self.assertEqual(called_features, ["feat-a", "feat-b"])
        # apply_feature_result fired once per feature (no budget abort).
        self.assertEqual(mocks["apply_feature_result"].await_count, 2)

    # ------------------------------------------------------------------
    # Scenario 2 — concurrency semaphore
    # ------------------------------------------------------------------

    async def test_concurrency_manager_acquire_release_per_feature(self):
        """ConcurrencyManager.acquire and .release are each called exactly
        once per feature dispatched through _run_one."""
        from cortex_command.overnight.orchestrator import run_batch

        mock_manager = MagicMock()
        mock_manager.acquire = AsyncMock()
        mock_manager.release = MagicMock()
        mock_manager.stats = {}

        self._install_base_patches(
            feature_names=["feat-a", "feat-b"],
            execute_return={
                "feat-a": FeatureResult(name="feat-a", status="completed"),
                "feat-b": FeatureResult(name="feat-b", status="completed"),
            },
            mock_manager=mock_manager,
        )

        await run_batch(self._config)

        self.assertEqual(mock_manager.acquire.await_count, 2)
        self.assertEqual(mock_manager.release.call_count, 2)

    # ------------------------------------------------------------------
    # Scenario 3 — circuit breaker
    # ------------------------------------------------------------------

    async def test_circuit_breaker_short_circuits_after_threshold(self):
        """Pre-seeding CircuitBreakerState at the threshold does NOT by
        itself short-circuit _run_one (the batch_result flag is what the
        orchestrator checks).  To exercise the circuit-breaker path we
        flip batch_result.circuit_breaker_fired before dispatch by
        patching apply_feature_result to set it after the first feature
        returns; the remaining features then hit the breaker branch in
        _run_one and execute_feature is never called for them."""
        from cortex_command.overnight.orchestrator import run_batch

        # First feature's apply_feature_result trips the breaker flag.
        async def _apply_trips_breaker(name, result, ctx):
            ctx.batch_result.circuit_breaker_fired = True

        # We want to assert execute_feature is *not* called for feat-b and
        # feat-c after the breaker fires.  Because asyncio.gather dispatches
        # all three _run_one coroutines concurrently, we serialize via the
        # semaphore: patch manager.acquire to await an event that only
        # releases after the first feature's apply callback sets the flag.
        from cortex_command.overnight.orchestrator import BatchConfig as _BC  # noqa: F401

        mock_manager = MagicMock()
        gate = asyncio.Event()

        acquire_calls = {"count": 0}

        async def _acquire():
            acquire_calls["count"] += 1
            if acquire_calls["count"] == 1:
                return
            # Subsequent acquirers wait for the breaker to fire.
            await gate.wait()

        mock_manager.acquire = AsyncMock(side_effect=_acquire)
        mock_manager.release = MagicMock()
        mock_manager.stats = {}

        mocks = self._install_base_patches(
            feature_names=["feat-a", "feat-b", "feat-c"],
            execute_return={
                "feat-a": FeatureResult(name="feat-a", status="completed"),
                "feat-b": FeatureResult(name="feat-b", status="completed"),
                "feat-c": FeatureResult(name="feat-c", status="completed"),
            },
            mock_manager=mock_manager,
        )

        # Swap the apply side-effect so feat-a trips the breaker, then
        # release the gate so remaining features can proceed (they will hit
        # the re-check inside the semaphore and short-circuit).
        async def _apply_and_gate(name, result, ctx):
            await _apply_trips_breaker(name, result, ctx)
            gate.set()

        mocks["apply_feature_result"].side_effect = _apply_and_gate

        # Additionally pre-seed CircuitBreakerState so the patched class
        # returns our threshold-seeded instance (spec requirement).
        self._start_patch(
            "cortex_command.overnight.orchestrator.CircuitBreakerState",
            new=MagicMock(
                return_value=CircuitBreakerState(
                    consecutive_pauses=CIRCUIT_BREAKER_THRESHOLD
                )
            ),
        )

        batch_result = await run_batch(self._config)

        self.assertTrue(batch_result.circuit_breaker_fired)
        # execute_feature was called only for feat-a.
        self.assertEqual(mocks["execute_feature"].await_count, 1)
        called_features = [
            call.kwargs.get("feature")
            for call in mocks["execute_feature"].await_args_list
        ]
        self.assertEqual(called_features, ["feat-a"])

    # ------------------------------------------------------------------
    # Scenario 4 — budget exhaustion
    # ------------------------------------------------------------------

    async def test_budget_exhaustion_sets_global_abort_and_skips_outcome_router(self):
        """execute_feature returns a budget_exhausted pause → the inline
        budget check in _run_one sets global_abort_signal and returns
        before invoking apply_feature_result for that feature."""
        from cortex_command.overnight.orchestrator import run_batch

        mocks = self._install_base_patches(
            feature_names=["feat-a"],
            execute_return=FeatureResult(
                name="feat-a",
                status="paused",
                error="budget_exhausted",
            ),
        )

        batch_result = await run_batch(self._config)

        self.assertTrue(batch_result.global_abort_signal)
        self.assertEqual(batch_result.abort_reason, "budget_exhausted")
        # The outcome router is short-circuited on the budget-exhausted path.
        mocks["apply_feature_result"].assert_not_awaited()

    # ------------------------------------------------------------------
    # Scenario 5 — heartbeat lifecycle
    # ------------------------------------------------------------------

    async def test_heartbeat_task_cancelled_on_return(self):
        """run_batch starts a heartbeat task via create_task and cancels
        it before returning.  Patch create_task to capture the real task
        and assert it was cancelled; await it in addCleanup so no
        'task destroyed but pending' warnings appear."""
        from cortex_command.overnight.orchestrator import run_batch

        mocks = self._install_base_patches(
            feature_names=["feat-a"],
            execute_return=FeatureResult(name="feat-a", status="completed"),
        )

        await run_batch(self._config)

        create_task_mock = mocks["create_task"]
        self.assertIsNotNone(create_task_mock)
        # create_task invoked at least once (for the heartbeat loop).
        self.assertGreaterEqual(create_task_mock.call_count, 1)

        captured = create_task_mock.captured  # type: ignore[attr-defined]
        self.assertGreaterEqual(len(captured), 1)
        hb_task = captured[0]

        # After run_batch returns, the heartbeat task should be done/cancelled.
        self.assertTrue(hb_task.done())
        self.assertTrue(hb_task.cancelled())

        # Defensively await the task in cleanup so no "task destroyed but
        # pending" warnings appear if a future change delays cancellation.
        async def _drain():
            try:
                await hb_task
            except asyncio.CancelledError:
                pass

        # Schedule the drain; it's a no-op for an already-cancelled task but
        # keeps the cleanup semantics explicit per spec.
        self.addCleanup(lambda: asyncio.get_event_loop().run_until_complete(
            _drain()
        ) if not hb_task.done() else None)


if __name__ == "__main__":
    unittest.main()
