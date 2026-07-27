"""Unit tests for the recovery paths in retry.py.

Replaces the former test_escalation.py. cortex no longer selects a model for a
dispatch, so the haiku -> sonnet -> opus ladder and every assertion about
``model_override`` are gone. What survives is the part that was never about
models: which error classifications retry, which pause immediately, and how the
loop terminates.

  - agent_test_failure retries (it used to escalate a model tier)
  - agent_confused retries (likewise)
  - agent_timeout / task_failure / unknown retry
  - agent_refusal pauses immediately for human triage
  - infrastructure_failure pauses immediately for human triage
  - budget_exhausted pauses the session without retrying
  - a persistently failing retry-classified error exhausts attempts and pauses
  - cost accumulates across attempts
  - no dispatch is handed a model (the caller does not choose one)
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# conftest.py runs before this module under pytest and installs the SDK stub.
# Under plain unittest, call _install_sdk_stub() directly here.
from cortex_command.pipeline.tests.conftest import _install_sdk_stub
_install_sdk_stub()

from cortex_command.pipeline.dispatch import DispatchResult, ERROR_RECOVERY
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
    return DispatchResult(success=True, output=output, cost_usd=cost)


def _read_jsonl(path: Path) -> list[dict]:
    """Parse a JSONL file; strip 'ts' for stable comparisons."""
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            d = json.loads(line)
            d.pop("ts", None)
            events.append(d)
    return events


def _make_unique_diff_fn():
    """Return a function producing a different diff string on each call.

    Prevents the circuit breaker (which trips on two identical consecutive
    diffs) from firing during multi-attempt tests.
    """
    counter = [0]

    def unique_diff(path: Path) -> str:
        counter[0] += 1
        return f"diff-{counter[0]}"

    return unique_diff


async def _run(mock_dispatch, tmp: str, *, log_path: Path | None = None,
               max_retries: int = 3, complexity: str = "trivial",
               unique_diffs: bool = True):
    """Drive retry_task against a mocked dispatch_task."""
    diff_patch = (
        patch("cortex_command.pipeline.retry._get_worktree_diff",
              side_effect=_make_unique_diff_fn())
        if unique_diffs
        else patch("cortex_command.pipeline.retry._get_worktree_diff", return_value="")
    )
    with (
        patch("cortex_command.pipeline.retry.dispatch_task", new=mock_dispatch),
        patch("cortex_command.pipeline.retry.cleanup_stale_lock"),
        diff_patch,
    ):
        return await retry_task(
            feature="feat",
            task="do something",
            worktree_path=Path(tmp),
            complexity=complexity,
            system_prompt="",
            learnings_dir=Path(tmp) / "learnings",
            skill="implement",
            max_retries=max_retries,
            log_path=log_path,
        )


# ---------------------------------------------------------------------------
# Tests: the recovery table itself
# ---------------------------------------------------------------------------

class TestErrorRecoveryTable(unittest.TestCase):
    """The classification -> recovery-path mapping."""

    def test_former_escalate_errors_now_retry(self):
        """The two error types that drove the model ladder now plain-retry."""
        self.assertEqual(ERROR_RECOVERY["agent_test_failure"], "retry")
        self.assertEqual(ERROR_RECOVERY["agent_confused"], "retry")

    def test_no_recovery_path_is_escalate(self):
        """`escalate` is gone from the vocabulary — nothing to climb."""
        self.assertNotIn("escalate", set(ERROR_RECOVERY.values()))

    def test_pause_paths_unchanged(self):
        self.assertEqual(ERROR_RECOVERY["agent_refusal"], "pause_human")
        self.assertEqual(ERROR_RECOVERY["infrastructure_failure"], "pause_human")
        self.assertEqual(ERROR_RECOVERY["budget_exhausted"], "pause_session")
        self.assertEqual(ERROR_RECOVERY["api_rate_limit"], "pause_session")


# ---------------------------------------------------------------------------
# Tests: retry_task recovery behavior (async)
# ---------------------------------------------------------------------------

class TestRetryTaskRecoveryPaths(unittest.IsolatedAsyncioTestCase):
    """Which classifications retry, which pause, and how the loop terminates."""

    async def test_first_attempt_success(self):
        async def mock_dispatch(**kwargs) -> DispatchResult:
            return _succeeded()

        with tempfile.TemporaryDirectory() as tmp:
            result = await _run(mock_dispatch, tmp, unique_diffs=False)

        self.assertTrue(result.success)
        self.assertEqual(result.attempts, 1)
        self.assertFalse(result.paused)

    async def test_dispatch_is_never_handed_a_model(self):
        """The retry loop must not pass model_override — cortex picks no model."""
        seen_kwargs: list[dict] = []

        async def mock_dispatch(**kwargs) -> DispatchResult:
            seen_kwargs.append(kwargs)
            if len(seen_kwargs) == 1:
                return _failed("agent_test_failure")
            return _succeeded()

        with tempfile.TemporaryDirectory() as tmp:
            result = await _run(mock_dispatch, tmp)

        self.assertTrue(result.success)
        self.assertEqual(len(seen_kwargs), 2)
        for kwargs in seen_kwargs:
            self.assertNotIn("model_override", kwargs)
            self.assertNotIn("escalated", kwargs)
            self.assertNotIn("escalation_event", kwargs)

    async def test_agent_test_failure_retries_then_succeeds(self):
        calls = [0]

        async def mock_dispatch(**kwargs) -> DispatchResult:
            calls[0] += 1
            if calls[0] == 1:
                return _failed("agent_test_failure")
            return _succeeded()

        with tempfile.TemporaryDirectory() as tmp:
            result = await _run(mock_dispatch, tmp)

        self.assertTrue(result.success)
        self.assertEqual(result.attempts, 2)
        self.assertFalse(result.paused)

    async def test_agent_confused_retries_then_succeeds(self):
        calls = [0]

        async def mock_dispatch(**kwargs) -> DispatchResult:
            calls[0] += 1
            if calls[0] == 1:
                return _failed("agent_confused")
            return _succeeded()

        with tempfile.TemporaryDirectory() as tmp:
            result = await _run(mock_dispatch, tmp)

        self.assertTrue(result.success)
        self.assertEqual(result.attempts, 2)

    async def test_persistent_retry_error_exhausts_and_pauses(self):
        """No ladder to climb: repeated failures burn attempts, then pause."""
        calls = [0]

        async def mock_dispatch(**kwargs) -> DispatchResult:
            calls[0] += 1
            return _failed("agent_test_failure")

        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "events.log"
            result = await _run(mock_dispatch, tmp, log_path=log_path, max_retries=2)
            events = _read_jsonl(log_path)

        self.assertFalse(result.success)
        self.assertTrue(result.paused)
        self.assertEqual(calls[0], 3)  # max_retries=2 → 3 attempts
        self.assertEqual(result.attempts, 3)
        self.assertIn("retry_exhausted", {e.get("event") for e in events})

    async def test_agent_refusal_pauses_immediately(self):
        calls = [0]

        async def mock_dispatch(**kwargs) -> DispatchResult:
            calls[0] += 1
            return _failed("agent_refusal")

        with tempfile.TemporaryDirectory() as tmp:
            result = await _run(mock_dispatch, tmp)

        self.assertFalse(result.success)
        self.assertTrue(result.paused)
        self.assertEqual(calls[0], 1)
        self.assertEqual(result.error_type, "agent_refusal")

    async def test_infrastructure_failure_pauses_immediately(self):
        calls = [0]

        async def mock_dispatch(**kwargs) -> DispatchResult:
            calls[0] += 1
            return _failed("infrastructure_failure")

        with tempfile.TemporaryDirectory() as tmp:
            result = await _run(mock_dispatch, tmp)

        self.assertFalse(result.success)
        self.assertTrue(result.paused)
        self.assertEqual(calls[0], 1)

    async def test_budget_exhausted_pauses_without_retry(self):
        calls = [0]

        async def mock_dispatch(**kwargs) -> DispatchResult:
            calls[0] += 1
            return _failed("budget_exhausted")

        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "events.log"
            result = await _run(mock_dispatch, tmp, log_path=log_path)
            events = _read_jsonl(log_path)

        self.assertFalse(result.success)
        self.assertTrue(result.paused)
        self.assertEqual(calls[0], 1)
        self.assertIn("retry_paused_session", {e.get("event") for e in events})

    async def test_timeout_task_failure_and_unknown_all_retry(self):
        for error_type in ("agent_timeout", "task_failure", "unknown"):
            with self.subTest(error_type=error_type):
                calls = [0]

                async def mock_dispatch(**kwargs) -> DispatchResult:
                    calls[0] += 1
                    if calls[0] == 1:
                        return _failed(error_type)
                    return _succeeded()

                with tempfile.TemporaryDirectory() as tmp:
                    result = await _run(mock_dispatch, tmp)

                self.assertTrue(result.success)
                self.assertEqual(result.attempts, 2)

    async def test_retry_attempt_events_carry_no_model(self):
        """retry_attempt used to name the tier it was about to run on."""
        calls = [0]

        async def mock_dispatch(**kwargs) -> DispatchResult:
            calls[0] += 1
            if calls[0] == 1:
                return _failed("agent_test_failure")
            return _succeeded()

        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "events.log"
            await _run(mock_dispatch, tmp, log_path=log_path)
            events = _read_jsonl(log_path)

        attempts = [e for e in events if e.get("event") == "retry_attempt"]
        self.assertEqual(len(attempts), 2)
        for event in attempts:
            self.assertNotIn("model", event)
        self.assertEqual([e["attempt"] for e in attempts], [1, 2])

    async def test_no_escalation_events_are_emitted(self):
        calls = [0]

        async def mock_dispatch(**kwargs) -> DispatchResult:
            calls[0] += 1
            return _failed("agent_test_failure")

        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "events.log"
            await _run(mock_dispatch, tmp, log_path=log_path, max_retries=2)
            events = _read_jsonl(log_path)

        self.assertNotIn("retry_escalate", {e.get("event") for e in events})

    async def test_total_cost_accumulates_across_attempts(self):
        calls = [0]

        async def mock_dispatch(**kwargs) -> DispatchResult:
            calls[0] += 1
            if calls[0] < 3:
                return _failed("agent_test_failure", cost=0.10)
            return _succeeded(cost=0.05)

        with tempfile.TemporaryDirectory() as tmp:
            result = await _run(mock_dispatch, tmp)

        self.assertTrue(result.success)
        self.assertAlmostEqual(result.total_cost_usd, 0.25, places=6)


if __name__ == "__main__":
    unittest.main()
