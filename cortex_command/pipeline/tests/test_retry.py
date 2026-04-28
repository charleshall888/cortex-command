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

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# conftest.py runs before this module under pytest and installs the SDK stub.
# Under plain unittest, call _install_sdk_stub() directly here to keep parity
# with the other retry-related test modules.
from cortex_command.pipeline.tests.conftest import _install_sdk_stub
_install_sdk_stub()

from cortex_command.pipeline.dispatch import DispatchResult
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
    """Verify retry_task threads attempt/escalated/escalation_event correctly.

    Patches dispatch_task at its import site in retry.py so we can capture
    each call's kwargs without spawning real sub-agents.
    """

    async def test_retry_threads_attempt_escalated_and_escalation_event(self):
        """Drive 4 attempts (Sonnet→Opus escalation → 2 retries at Opus).

        Per-attempt expectations for (attempt, escalated, escalation_event):

          - Attempt 1: (1, False, False) — initial Sonnet dispatch.
            Returns agent_test_failure → ERROR_RECOVERY classifies as
            "escalate", so retry.py upgrades sonnet → opus for attempt 2.
          - Attempt 2: (2, True, True) — first dispatch at the escalated
            tier. escalated=True (sticky: opus != sonnet); escalation_event=True
            (one-shot: opus != prev sonnet). Returns task_failure →
            "retry" recovery, so attempt 3 stays at Opus.
          - Attempt 3: (3, True, False) — still at Opus. escalated stays
            sticky-True; escalation_event flips to False because
            current_model == previous_attempt_model (both opus).
            Returns task_failure → "retry", attempt 4 stays at Opus.
          - Attempt 4: (4, True, False) — final attempt. Same kwarg shape
            as attempt 3 (sticky-True / one-shot-False). Returns success
            so the loop exits cleanly without exhausting retries.
        """
        # Sequential side_effects driving the 4-attempt scenario:
        #   1) sonnet fails with agent_test_failure  → escalate
        #   2) opus fails with task_failure          → retry
        #   3) opus fails with task_failure          → retry
        #   4) opus succeeds                         → loop exits
        side_effects = [
            _failed("agent_test_failure"),   # attempt 1: triggers Sonnet→Opus escalation
            _failed("task_failure"),         # attempt 2: retry-class failure at Opus
            _failed("task_failure"),         # attempt 3: retry-class failure at Opus
            _succeeded(),                    # attempt 4: terminate the loop
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
                    # simple + medium → sonnet initially; escalates to opus.
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

        # ---- Attempt 1: initial Sonnet dispatch — neither flag set. ----
        kwargs = captured_calls[0]
        self.assertEqual(kwargs["attempt"], 1, "attempt 1 kwargs[attempt] mismatch")
        self.assertEqual(kwargs["escalated"], False, "attempt 1 kwargs[escalated] mismatch")
        self.assertEqual(kwargs["escalation_event"], False, "attempt 1 kwargs[escalation_event] mismatch")
        self.assertEqual(kwargs["model_override"], "sonnet", "attempt 1 should run on Sonnet")

        # ---- Attempt 2: first dispatch at Opus — both flags set. ----
        kwargs = captured_calls[1]
        self.assertEqual(kwargs["attempt"], 2, "attempt 2 kwargs[attempt] mismatch")
        self.assertEqual(kwargs["escalated"], True, "attempt 2 kwargs[escalated] mismatch")
        self.assertEqual(kwargs["escalation_event"], True, "attempt 2 kwargs[escalation_event] mismatch")
        self.assertEqual(kwargs["model_override"], "opus", "attempt 2 should run on Opus after escalation")

        # ---- Attempt 3: stays at Opus — escalated sticky, escalation_event one-shot off. ----
        kwargs = captured_calls[2]
        self.assertEqual(kwargs["attempt"], 3, "attempt 3 kwargs[attempt] mismatch")
        self.assertEqual(kwargs["escalated"], True, "attempt 3 kwargs[escalated] mismatch (must stay sticky)")
        self.assertEqual(kwargs["escalation_event"], False, "attempt 3 kwargs[escalation_event] mismatch (one-shot off)")
        self.assertEqual(kwargs["model_override"], "opus", "attempt 3 should remain on Opus")

        # ---- Attempt 4: still Opus — same shape as attempt 3. ----
        kwargs = captured_calls[3]
        self.assertEqual(kwargs["attempt"], 4, "attempt 4 kwargs[attempt] mismatch")
        self.assertEqual(kwargs["escalated"], True, "attempt 4 kwargs[escalated] mismatch (still sticky)")
        self.assertEqual(kwargs["escalation_event"], False, "attempt 4 kwargs[escalation_event] mismatch (still one-shot off)")
        self.assertEqual(kwargs["model_override"], "opus", "attempt 4 should remain on Opus")


if __name__ == "__main__":
    unittest.main()
