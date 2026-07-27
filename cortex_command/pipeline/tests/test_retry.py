"""Unit tests for kwarg threading in retry.py's call to dispatch_task.

These tests focus on the per-attempt instrumentation forwarded to
dispatch_task: ``attempt`` (1-indexed counter), ``escalated`` (sticky bool —
true on every dispatch where ``current_model != initial_model``), and
``escalation_event`` (one-shot bool — true ONLY on the first attempt at a
newly-escalated tier).

The escalation-vs-event distinction lets downstream aggregators answer two
separate questions:

  - "How often did we escalate?"  → count ``escalation_event=True``
  - "How much cost lives at escalated tiers?" → filter ``escalated=True``

Spec reference: instrument-skill-name-on-dispatch-start-for-per-skill-pipeline-aggregates
Requirement 6 (R6.b): the retry loop must thread these three kwargs through
to dispatch_task on every dispatch, with the values pinned across at least
the four-attempt scenario verified below (Sonnet→Opus escalation followed
by two retry-class failures at Opus).
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# conftest.py runs before this module under pytest and installs the SDK stub.
# Under plain unittest, call _install_sdk_stub() directly here to keep parity
# with the other retry-related test modules.
from cortex_command.pipeline.tests.conftest import _install_sdk_stub
_install_sdk_stub()

from cortex_command.pipeline.dispatch import DispatchDiagnostics, DispatchResult
from cortex_command.pipeline.retry import retry_task


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _failed(error_type: str, cost: float = 0.01) -> DispatchResult:
    """Return a failed DispatchResult with the given error_type."""
    return DispatchResult(
        success=False,
        output=f"agent failed: {error_type}",
        error_type=error_type,
        error_detail=f"detail for {error_type}",
        cost_usd=cost,
    )


def _failed_with_diag(
    error_type: str,
    stderr: str,
    cost: float = 0.01,
) -> DispatchResult:
    """Return a failed DispatchResult carrying a DispatchDiagnostics bundle.

    The ``output`` and the diagnostics ``child_stderr`` both embed ``stderr``
    so a test can assert that the bundle and ``final_output`` describe the
    SAME attempt (same-attempt provenance invariant).
    """
    return DispatchResult(
        success=False,
        output=f"agent failed [{stderr}]",
        error_type=error_type,
        error_detail=f"detail for {error_type}",
        cost_usd=cost,
        diagnostics=DispatchDiagnostics(
            child_stderr=stderr,
            exit_code=1,
            cwd="/tmp/worktree",
        ),
    )


def _succeeded(output: str = "done", cost: float = 0.02) -> DispatchResult:
    """Return a successful DispatchResult."""
    return DispatchResult(
        success=True,
        output=output,
        cost_usd=cost,
    )


def _make_unique_diff_fn():
    """Return a function producing a unique diff string per call.

    Used to suppress the circuit breaker, which would otherwise fire when
    two consecutive retries produce identical (empty) diffs and short-circuit
    the test before all four attempts run.
    """
    counter = [0]

    def unique_diff(path: Path) -> str:
        counter[0] += 1
        return f"diff-{counter[0]}"

    return unique_diff


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

class TestRetryThreadsKwargs(unittest.IsolatedAsyncioTestCase):
    """Verify retry_task threads the per-attempt kwargs correctly.

    Patches dispatch_task at its import site in retry.py so we can capture
    each call's kwargs without spawning real sub-agents.
    """

    async def test_retry_threads_attempt_number_and_no_model(self):
        """Drive 4 attempts and assert the kwargs each one receives.

        This test used to assert a Sonnet -> Opus escalation and the
        ``escalated`` / ``escalation_event`` flags that tracked it. cortex no
        longer selects a model, so all four attempts are identical apart from
        the attempt counter, and no model-bearing kwarg is threaded at all.

          - Attempt 1: agent_test_failure -> "retry" recovery (it used to be
            "escalate" and would have upgraded the tier here).
          - Attempts 2 and 3: task_failure -> "retry".
          - Attempt 4: success, so the loop exits without exhausting retries.
        """
        side_effects = [
            _failed("agent_test_failure"),
            _failed("task_failure"),
            _failed("task_failure"),
            _succeeded(),
        ]

        captured_calls: list[dict] = []

        async def mock_dispatch(**kwargs) -> DispatchResult:
            # Capture the kwargs for each call so we can assert per-attempt
            # threading after the loop completes.
            captured_calls.append(kwargs)
            idx = len(captured_calls) - 1
            return side_effects[idx]

        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch("cortex_command.pipeline.retry.dispatch_task", new=mock_dispatch),
                patch("cortex_command.pipeline.retry.cleanup_stale_lock"),
                patch(
                    "cortex_command.pipeline.retry._get_worktree_diff",
                    side_effect=_make_unique_diff_fn(),
                ),
            ):
                result = await retry_task(
                    feature="feat",
                    task="do something",
                    worktree_path=Path(tmp),
                    complexity="simple",
                    criticality="medium",
                    system_prompt="",
                    learnings_dir=Path(tmp) / "learnings",
                    max_retries=3,   # total_attempts = max_retries + 1 = 4
                    skill="implement",
                )

        # Sanity: all four scripted attempts ran, and the loop exited on success.
        self.assertEqual(
            len(captured_calls),
            4,
            f"expected exactly 4 dispatch_task calls, got {len(captured_calls)}",
        )
        self.assertTrue(result.success, f"final attempt should succeed: {result}")
        self.assertEqual(result.attempts, 4)

        for idx, kwargs in enumerate(captured_calls, start=1):
            self.assertEqual(kwargs["attempt"], idx, f"attempt {idx} kwargs[attempt] mismatch")
            # No model-bearing kwargs survive: selection and the escalation
            # flags that tracked it were both removed.
            self.assertNotIn("model_override", kwargs, f"attempt {idx} must not pin a model")
            self.assertNotIn("escalated", kwargs, f"attempt {idx} must not carry escalated")
            self.assertNotIn("escalation_event", kwargs, f"attempt {idx} must not carry escalation_event")


class TestPauseHumanErrorType(unittest.IsolatedAsyncioTestCase):
    """Verify that the pause_human branch sets error_type on RetryResult.

    Before the fix, the RetryResult returned from pause_human omitted
    error_type=error_type, so RetryResult.error_type was always None for
    infrastructure_failure and agent_refusal paths.
    """

    async def test_pause_human_error_type_propagated(self):
        """infrastructure_failure triggers pause_human; RetryResult.error_type must match."""
        async def mock_dispatch(**kwargs) -> DispatchResult:
            return _failed("infrastructure_failure")

        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch("cortex_command.pipeline.retry.dispatch_task", new=mock_dispatch),
                patch("cortex_command.pipeline.retry.cleanup_stale_lock"),
                patch(
                    "cortex_command.pipeline.retry._get_worktree_diff",
                    return_value="some-diff",
                ),
            ):
                result = await retry_task(
                    feature="feat",
                    task="do something",
                    worktree_path=Path(tmp),
                    complexity="simple",
                    criticality="medium",
                    system_prompt="",
                    learnings_dir=Path(tmp) / "learnings",
                    max_retries=3,
                    skill="implement",
                )

        self.assertFalse(result.success, "pause_human result must be failure")
        self.assertTrue(result.paused, "pause_human result must be paused")
        self.assertEqual(
            result.error_type,
            "infrastructure_failure",
            f"expected error_type='infrastructure_failure', got {result.error_type!r}",
        )


class TestDiagnosticsThreading(unittest.IsolatedAsyncioTestCase):
    """Verify RetryResult.last_dispatch_diagnostics threads from the final result.

    Each failure-path RetryResult exit must propagate the diagnostics bundle
    from the SAME final ``result`` binding that supplies ``final_output``
    (same-attempt provenance). The success exit must leave it None.

    These tests guard a missed wiring site (per-site propagation) and the
    invariant that the bundle and ``final_output`` describe the same attempt.
    """

    async def _run(self, mock_dispatch, *, diff_value="some-diff", max_retries=3):
        """Drive retry_task with the given dispatch mock; return the result.

        ``diff_value`` is returned by every ``_get_worktree_diff`` call. A
        constant value makes consecutive diffs identical, which trips the
        circuit breaker on the second failure.
        """
        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch("cortex_command.pipeline.retry.dispatch_task", new=mock_dispatch),
                patch("cortex_command.pipeline.retry.cleanup_stale_lock"),
                patch(
                    "cortex_command.pipeline.retry._get_worktree_diff",
                    return_value=diff_value,
                ),
            ):
                return await retry_task(
                    feature="feat",
                    task="do something",
                    worktree_path=Path(tmp),
                    complexity="simple",
                    criticality="medium",
                    system_prompt="",
                    learnings_dir=Path(tmp) / "learnings",
                    max_retries=max_retries,
                    skill="implement",
                )

    async def test_success_exit_leaves_diagnostics_none(self):
        """Success on first attempt → last_dispatch_diagnostics is None."""
        async def mock_dispatch(**kwargs) -> DispatchResult:
            return _succeeded()

        result = await self._run(mock_dispatch)
        self.assertTrue(result.success)
        self.assertIsNone(result.last_dispatch_diagnostics)

    async def test_pause_human_propagates_diagnostics(self):
        """infrastructure_failure → pause_human exit carries result.diagnostics."""
        async def mock_dispatch(**kwargs) -> DispatchResult:
            return _failed_with_diag("infrastructure_failure", "stderr-pause-human")

        result = await self._run(mock_dispatch)
        self.assertTrue(result.paused)
        self.assertIsNotNone(result.last_dispatch_diagnostics)
        self.assertEqual(
            result.last_dispatch_diagnostics.child_stderr, "stderr-pause-human"
        )
        # Same-attempt provenance: the bundle's stderr is embedded in final_output.
        self.assertIn(
            result.last_dispatch_diagnostics.child_stderr, result.final_output
        )

    async def test_escalation_exhausted_propagates_diagnostics(self):
        """agent_confused at Opus → ladder exhausted → exit carries diagnostics.

        Start at complex+high (resolves to Opus); agent_confused → escalate,
        but Opus is the ladder top so the escalation-exhausted exit fires on
        the first attempt.
        """
        async def mock_dispatch(**kwargs) -> DispatchResult:
            return _failed_with_diag("agent_confused", "stderr-escalation-exhausted")

        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch("cortex_command.pipeline.retry.dispatch_task", new=mock_dispatch),
                patch("cortex_command.pipeline.retry.cleanup_stale_lock"),
                patch(
                    "cortex_command.pipeline.retry._get_worktree_diff",
                    return_value="some-diff",
                ),
            ):
                result = await retry_task(
                    feature="feat",
                    task="do something",
                    worktree_path=Path(tmp),
                    complexity="complex",
                    criticality="high",  # → opus, top of ladder
                    system_prompt="",
                    learnings_dir=Path(tmp) / "learnings",
                    max_retries=3,
                    skill="implement",
                )

        self.assertTrue(result.paused)
        self.assertIsNotNone(result.last_dispatch_diagnostics)
        self.assertEqual(
            result.last_dispatch_diagnostics.child_stderr,
            "stderr-escalation-exhausted",
        )
        self.assertIn(
            result.last_dispatch_diagnostics.child_stderr, result.final_output
        )

    async def test_pause_session_propagates_diagnostics_value(self):
        """budget_exhausted → pause_session exit threads result.diagnostics.

        In production this site's diagnostics is None by construction (the
        budget-exhausted DispatchResult comes from the non-exception return).
        Here we inject a bundle to prove the threading is wired uniformly —
        the production None is correct, not a missed site.
        """
        async def mock_dispatch(**kwargs) -> DispatchResult:
            return _failed_with_diag("budget_exhausted", "stderr-pause-session")

        result = await self._run(mock_dispatch)
        self.assertTrue(result.paused)
        self.assertIsNotNone(result.last_dispatch_diagnostics)
        self.assertEqual(
            result.last_dispatch_diagnostics.child_stderr, "stderr-pause-session"
        )

    async def test_circuit_breaker_propagates_diagnostics(self):
        """Identical diffs across retries → circuit-breaker exit carries diagnostics.

        retry-class failures with a constant diff trip the breaker on attempt 2;
        assert the final attempt's diagnostics surface.
        """
        side_effects = [
            _failed_with_diag("task_failure", "stderr-cb-attempt-1"),
            _failed_with_diag("task_failure", "stderr-cb-attempt-2"),
        ]
        captured = []

        async def mock_dispatch(**kwargs) -> DispatchResult:
            idx = len(captured)
            captured.append(kwargs)
            return side_effects[idx]

        # Constant diff so the breaker trips after the second failure.
        result = await self._run(mock_dispatch, diff_value="identical")
        self.assertTrue(result.paused)
        self.assertIsNotNone(result.last_dispatch_diagnostics)
        # The circuit breaker fires on attempt 2; the final result is attempt 2.
        self.assertEqual(
            result.last_dispatch_diagnostics.child_stderr, "stderr-cb-attempt-2"
        )
        self.assertIn(
            result.last_dispatch_diagnostics.child_stderr, result.final_output
        )

    async def test_all_retries_exhausted_surfaces_final_attempt_diagnostics(self):
        """Drive a retry-recovery type to exhaustion → loop-exit site fires.

        Construct a multi-attempt retry where the final attempt's stderr
        differs from earlier attempts. The loop-exit RetryResult (retry.py
        all-retries-exhausted) must surface the FINAL attempt's diagnostics
        (the leaked final-iteration ``result`` binding), and that bundle must
        match ``final_output`` (same-attempt provenance).

        Uses task_failure (recovery: retry) with unique diffs so the circuit
        breaker never trips and all attempts run to exhaustion.
        """
        # 4 attempts (max_retries=3), each task_failure (retry-recovery), with
        # distinct stderr per attempt so we can prove the LAST one surfaces.
        side_effects = [
            _failed_with_diag("task_failure", "stderr-attempt-1"),
            _failed_with_diag("task_failure", "stderr-attempt-2"),
            _failed_with_diag("task_failure", "stderr-attempt-3"),
            _failed_with_diag("task_failure", "stderr-attempt-4-FINAL"),
        ]
        captured = []

        async def mock_dispatch(**kwargs) -> DispatchResult:
            idx = len(captured)
            captured.append(kwargs)
            return side_effects[idx]

        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch("cortex_command.pipeline.retry.dispatch_task", new=mock_dispatch),
                patch("cortex_command.pipeline.retry.cleanup_stale_lock"),
                patch(
                    "cortex_command.pipeline.retry._get_worktree_diff",
                    side_effect=_make_unique_diff_fn(),
                ),
            ):
                result = await retry_task(
                    feature="feat",
                    task="do something",
                    worktree_path=Path(tmp),
                    complexity="simple",
                    criticality="medium",
                    system_prompt="",
                    learnings_dir=Path(tmp) / "learnings",
                    max_retries=3,  # total_attempts = 4
                    skill="implement",
                )

        self.assertEqual(len(captured), 4, "all four attempts should run to exhaustion")
        self.assertFalse(result.success)
        self.assertTrue(result.paused)
        self.assertEqual(result.attempts, 4)
        self.assertIsNotNone(result.last_dispatch_diagnostics)
        # The FINAL attempt's diagnostics — not an earlier attempt's — must surface.
        self.assertEqual(
            result.last_dispatch_diagnostics.child_stderr,
            "stderr-attempt-4-FINAL",
        )
        # Same-attempt provenance: bundle stderr and final_output agree.
        self.assertIn(
            result.last_dispatch_diagnostics.child_stderr, result.final_output
        )


class TestEffortClamp(unittest.IsolatedAsyncioTestCase):
    """#313 R4: an effort_unsupported rejection clamps once to ``max`` and
    retries — without blind-retrying the invalid flag and without the circuit
    breaker preempting the clamp."""

    async def _run(self, side_effects, *, diff_value, max_retries=3):
        captured: list[dict] = []

        async def mock_dispatch(**kwargs) -> DispatchResult:
            captured.append(kwargs)
            return side_effects[len(captured) - 1]

        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "events.log"
            with (
                patch("cortex_command.pipeline.retry.dispatch_task", new=mock_dispatch),
                patch("cortex_command.pipeline.retry.cleanup_stale_lock"),
                patch(
                    "cortex_command.pipeline.retry._get_worktree_diff",
                    return_value=diff_value,
                ),
            ):
                result = await retry_task(
                    feature="feat",
                    task="do something",
                    worktree_path=Path(tmp),
                    complexity="complex",
                    criticality="high",
                    system_prompt="",
                    learnings_dir=Path(tmp) / "learnings",
                    log_path=log_path,
                    max_retries=max_retries,
                    skill="implement",
                )
            events = [
                json.loads(line)
                for line in log_path.read_text().splitlines()
                if line.strip()
            ]
        return result, captured, events

    async def test_clamps_once_on_first_attempt(self):
        result, captured, events = await self._run(
            [_failed("effort_unsupported"), _succeeded()],
            diff_value="d",
        )
        # Exactly one clamped retry: 2 dispatches, not the blind 4-attempt ladder.
        self.assertEqual(len(captured), 2)
        self.assertIsNone(captured[0]["effort_override"])
        self.assertEqual(captured[1]["effort_override"], "max")
        self.assertTrue(result.success)
        clamp_events = [e for e in events if e.get("event") == "retry_effort_clamped"]
        self.assertEqual(len(clamp_events), 1)
        self.assertEqual(clamp_events[0]["to_effort"], "max")

    async def test_clamps_on_attempt_2_despite_empty_diff_circuit_breaker(self):
        # Empty diffs would trip the circuit breaker on attempt 2; the clamp must
        # be evaluated BEFORE the breaker so the clamped retry still fires.
        result, captured, events = await self._run(
            [
                _failed("task_failure"),
                _failed("effort_unsupported"),
                _succeeded(),
            ],
            diff_value="",
        )
        self.assertEqual(len(captured), 3, "clamp must run despite empty diffs")
        self.assertEqual(captured[2]["effort_override"], "max")
        self.assertTrue(result.success)
        self.assertFalse(result.paused)


class TestProgressStderr(unittest.IsolatedAsyncioTestCase):
    """#313 R6: the captured child_stderr is surfaced in progress.txt instead of
    only an opaque ProcessError detail."""

    async def test_child_stderr_written_to_progress(self):
        sentinel = "option '--effort <level>' argument 'xhigh' is invalid"

        async def mock_dispatch(**kwargs) -> DispatchResult:
            return _failed_with_diag("infrastructure_failure", stderr=sentinel)

        with tempfile.TemporaryDirectory() as tmp:
            learnings_dir = Path(tmp) / "learnings"
            with (
                patch("cortex_command.pipeline.retry.dispatch_task", new=mock_dispatch),
                patch("cortex_command.pipeline.retry.cleanup_stale_lock"),
                patch(
                    "cortex_command.pipeline.retry._get_worktree_diff",
                    return_value="d",
                ),
            ):
                result = await retry_task(
                    feature="feat",
                    task="t",
                    worktree_path=Path(tmp),
                    complexity="simple",
                    criticality="medium",
                    system_prompt="",
                    learnings_dir=learnings_dir,
                    max_retries=3,
                    skill="implement",
                )
            progress = (learnings_dir / "progress.txt").read_text()
        self.assertIn(sentinel, progress)
        self.assertIn("CLI stderr:", progress)
        self.assertFalse(result.success)


if __name__ == "__main__":
    unittest.main()
