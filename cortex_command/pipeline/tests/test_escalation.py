"""Unit tests for the escalation ladder in retry.py.

Tests cover MODEL_ESCALATION_LADDER in dispatch.py and the model-tier
escalation behavior in retry_task():

  - Ladder structure: haiku → sonnet → opus → None
  - agent_test_failure triggers model escalation
  - agent_confused triggers model escalation
  - agent_refusal pauses immediately without escalation
  - infrastructure_failure pauses immediately without escalation
  - agent_timeout retries without model escalation
  - task_failure retries without model escalation
  - unknown retries without model escalation
  - Opus failure with escalate recovery → ladder exhausted → paused for human
  - Full escalation path haiku → sonnet → opus → pause (≤3 attempts)
  - Log events record model names at each escalation step
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# conftest.py runs before this module under pytest and installs the SDK stub.
# Under plain unittest, call _install_sdk_stub() directly here.
from cortex_command.pipeline.tests.conftest import _install_sdk_stub
_install_sdk_stub()

import cortex_command.pipeline.dispatch as _dispatch_module
from cortex_command.pipeline.dispatch import (
    MODEL_ESCALATION_LADDER,
    DispatchResult,
)
from cortex_command.pipeline.retry import RetryResult, retry_task


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
    """Return a function that produces a different diff string on each call.

    Used to prevent the circuit breaker from firing during multi-attempt
    escalation tests (the circuit breaker trips when two consecutive diffs
    are identical).
    """
    counter = [0]

    def unique_diff(path: Path) -> str:
        counter[0] += 1
        return f"diff-{counter[0]}"

    return unique_diff


# ---------------------------------------------------------------------------
# Tests: MODEL_ESCALATION_LADDER constant (synchronous)
# ---------------------------------------------------------------------------

class TestModelEscalationLadder(unittest.TestCase):
    """Tests for the MODEL_ESCALATION_LADDER constant in dispatch.py."""

    def test_haiku_escalates_to_sonnet(self):
        self.assertEqual(MODEL_ESCALATION_LADDER["haiku"], "sonnet")

    def test_sonnet_escalates_to_opus(self):
        self.assertEqual(MODEL_ESCALATION_LADDER["sonnet"], "opus")

    def test_opus_has_no_escalation(self):
        self.assertIsNone(MODEL_ESCALATION_LADDER["opus"])

    def test_all_three_models_present(self):
        for model in ("haiku", "sonnet", "opus"):
            self.assertIn(model, MODEL_ESCALATION_LADDER)

    def test_escalation_chain_terminates_at_opus(self):
        """Following the chain from haiku reaches opus then terminates."""
        model: str | None = "haiku"
        visited: list[str] = []
        while model is not None:
            visited.append(model)
            model = MODEL_ESCALATION_LADDER.get(model)
        self.assertEqual(visited, ["haiku", "sonnet", "opus"])

    def test_no_model_escalates_to_itself(self):
        """A model must never escalate to the same model (infinite loop guard)."""
        for model, next_model in MODEL_ESCALATION_LADDER.items():
            if next_model is not None:
                self.assertNotEqual(
                    model,
                    next_model,
                    f"{model!r} escalates to itself",
                )


# ---------------------------------------------------------------------------
# Tests: retry_task escalation behavior (async)
# ---------------------------------------------------------------------------

class TestRetryTaskEscalation(unittest.IsolatedAsyncioTestCase):
    """Tests for model-tier escalation in retry_task (Req 8).

    All tests patch three names inside cortex_command.pipeline.retry:
      - dispatch_task: replaced with an async function returning controlled results
      - cleanup_stale_lock: replaced with a no-op to avoid filesystem side effects
      - _get_worktree_diff: replaced to return unique diffs (prevents circuit breaker)
    """

    async def test_first_attempt_success_no_escalation(self):
        """Success on the first attempt: attempts=1, paused=False."""
        async def mock_dispatch(**kwargs) -> DispatchResult:
            return _succeeded()

        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch("cortex_command.pipeline.retry.dispatch_task", new=mock_dispatch),
                patch("cortex_command.pipeline.retry.cleanup_stale_lock"),
                patch("cortex_command.pipeline.retry._get_worktree_diff", return_value=""),
            ):
                result = await retry_task(
                    feature="feat",
                    task="do something",
                    worktree_path=Path(tmp),
                    complexity="trivial",   # → haiku (medium criticality)
                    system_prompt="",
                    learnings_dir=Path(tmp) / "learnings",
                    skill="implement",
                    max_retries=3,
                )

        self.assertTrue(result.success)
        self.assertEqual(result.attempts, 1)
        self.assertFalse(result.paused)

    async def test_agent_test_failure_triggers_escalation(self):
        """agent_test_failure → escalate recovery → model upgraded for next attempt."""
        call_models: list[str | None] = []

        async def mock_dispatch(*, model_override=None, **kwargs) -> DispatchResult:
            call_models.append(model_override)
            if len(call_models) == 1:
                return _failed("agent_test_failure")
            return _succeeded()

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
                    complexity="trivial",   # → haiku initially
                    system_prompt="",
                    learnings_dir=Path(tmp) / "learnings",
                    skill="implement",
                    max_retries=3,
                )

        self.assertTrue(result.success)
        self.assertEqual(result.attempts, 2)
        # First attempt: haiku; second attempt: escalated to sonnet.
        self.assertEqual(call_models[0], "haiku")
        self.assertEqual(call_models[1], "sonnet")

    async def test_agent_confused_triggers_escalation(self):
        """agent_confused → escalate recovery → model upgraded for next attempt."""
        call_models: list[str | None] = []

        async def mock_dispatch(*, model_override=None, **kwargs) -> DispatchResult:
            call_models.append(model_override)
            if len(call_models) == 1:
                return _failed("agent_confused")
            return _succeeded()

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
                    complexity="trivial",
                    system_prompt="",
                    learnings_dir=Path(tmp) / "learnings",
                    skill="implement",
                    max_retries=3,
                )

        self.assertTrue(result.success)
        self.assertEqual(call_models[0], "haiku")
        self.assertEqual(call_models[1], "sonnet")

    async def test_agent_refusal_pauses_immediately_without_escalation(self):
        """agent_refusal → pause_human recovery → paused=True on attempt 1, no retry."""
        dispatch_calls = [0]

        async def mock_dispatch(**kwargs) -> DispatchResult:
            dispatch_calls[0] += 1
            return _failed("agent_refusal")

        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch("cortex_command.pipeline.retry.dispatch_task", new=mock_dispatch),
                patch("cortex_command.pipeline.retry.cleanup_stale_lock"),
                patch("cortex_command.pipeline.retry._get_worktree_diff", return_value=""),
            ):
                result = await retry_task(
                    feature="feat",
                    task="do something",
                    worktree_path=Path(tmp),
                    complexity="trivial",
                    system_prompt="",
                    learnings_dir=Path(tmp) / "learnings",
                    skill="implement",
                    max_retries=3,
                )

        self.assertFalse(result.success)
        self.assertTrue(result.paused)
        self.assertEqual(result.attempts, 1)
        self.assertEqual(dispatch_calls[0], 1, "Must not have retried after refusal")

    async def test_infrastructure_failure_pauses_immediately(self):
        """infrastructure_failure → pause_human → paused=True on attempt 1."""
        dispatch_calls = [0]

        async def mock_dispatch(**kwargs) -> DispatchResult:
            dispatch_calls[0] += 1
            return _failed("infrastructure_failure")

        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch("cortex_command.pipeline.retry.dispatch_task", new=mock_dispatch),
                patch("cortex_command.pipeline.retry.cleanup_stale_lock"),
                patch("cortex_command.pipeline.retry._get_worktree_diff", return_value=""),
            ):
                result = await retry_task(
                    feature="feat",
                    task="do something",
                    worktree_path=Path(tmp),
                    complexity="trivial",
                    system_prompt="",
                    learnings_dir=Path(tmp) / "learnings",
                    skill="implement",
                    max_retries=3,
                )

        self.assertFalse(result.success)
        self.assertTrue(result.paused)
        self.assertEqual(result.attempts, 1)
        self.assertEqual(dispatch_calls[0], 1)

    async def test_agent_timeout_retries_without_escalation(self):
        """agent_timeout → retry recovery → same model used on retry, no escalation."""
        call_models: list[str | None] = []

        async def mock_dispatch(*, model_override=None, **kwargs) -> DispatchResult:
            call_models.append(model_override)
            if len(call_models) < 2:
                return _failed("agent_timeout")
            return _succeeded()

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
                    complexity="trivial",   # → haiku
                    system_prompt="",
                    learnings_dir=Path(tmp) / "learnings",
                    skill="implement",
                    max_retries=3,
                )

        self.assertTrue(result.success)
        # Both attempts use haiku — no escalation for timeout.
        self.assertEqual(call_models[0], "haiku")
        self.assertEqual(call_models[1], "haiku")

    async def test_task_failure_retries_without_escalation(self):
        """task_failure → retry recovery → same model, no escalation."""
        call_models: list[str | None] = []

        async def mock_dispatch(*, model_override=None, **kwargs) -> DispatchResult:
            call_models.append(model_override)
            if len(call_models) < 2:
                return _failed("task_failure")
            return _succeeded()

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
                    complexity="trivial",
                    system_prompt="",
                    learnings_dir=Path(tmp) / "learnings",
                    skill="implement",
                    max_retries=3,
                )

        self.assertTrue(result.success)
        self.assertEqual(call_models[0], "haiku")
        self.assertEqual(call_models[1], "haiku")

    async def test_unknown_error_retries_without_escalation(self):
        """unknown → retry recovery → same model, no escalation."""
        call_models: list[str | None] = []

        async def mock_dispatch(*, model_override=None, **kwargs) -> DispatchResult:
            call_models.append(model_override)
            if len(call_models) < 2:
                return _failed("unknown")
            return _succeeded()

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
                    complexity="trivial",
                    system_prompt="",
                    learnings_dir=Path(tmp) / "learnings",
                    skill="implement",
                    max_retries=3,
                )

        self.assertTrue(result.success)
        self.assertEqual(call_models[0], "haiku")
        self.assertEqual(call_models[1], "haiku")

    async def test_opus_failure_with_escalate_pauses_immediately(self):
        """Opus + escalate recovery → ladder exhausted → paused=True, attempts=1."""
        async def mock_dispatch(**kwargs) -> DispatchResult:
            return _failed("agent_test_failure")

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
                    # complex + high criticality resolves to opus
                    complexity="complex",
                    criticality="high",
                    system_prompt="",
                    learnings_dir=Path(tmp) / "learnings",
                    skill="implement",
                    max_retries=3,
                )

        self.assertFalse(result.success)
        self.assertTrue(result.paused)
        self.assertEqual(result.attempts, 1)

    async def test_full_escalation_haiku_sonnet_opus_then_pause(self):
        """Haiku→Sonnet→Opus all fail → paused for human in ≤3 attempts (Req 8)."""
        call_models: list[str | None] = []

        async def mock_dispatch(*, model_override=None, **kwargs) -> DispatchResult:
            call_models.append(model_override)
            return _failed("agent_test_failure")

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
                    complexity="trivial",   # starts at haiku
                    system_prompt="",
                    learnings_dir=Path(tmp) / "learnings",
                    skill="implement",
                    max_retries=5,          # allow enough budget
                )

        self.assertFalse(result.success)
        self.assertTrue(result.paused)

        # Spec criterion: no task fails more than 3 times without human awareness.
        self.assertLessEqual(result.attempts, 3)

        # The escalation sequence must be haiku → sonnet → opus (then paused).
        self.assertEqual(len(call_models), 3)
        self.assertEqual(call_models[0], "haiku")
        self.assertEqual(call_models[1], "sonnet")
        self.assertEqual(call_models[2], "opus")

    async def test_escalation_log_event_records_from_and_to_model(self):
        """retry_escalate events capture from_model and to_model correctly."""
        async def mock_dispatch(*, model_override=None, **kwargs) -> DispatchResult:
            if model_override == "haiku":
                return _failed("agent_test_failure")
            return _succeeded()

        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "events.jsonl"
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
                    complexity="trivial",
                    system_prompt="",
                    learnings_dir=Path(tmp) / "learnings",
                    skill="implement",
                    log_path=log_path,
                    max_retries=3,
                )

            # Assertions inside the 'with' block so the temp dir still exists.
            self.assertTrue(result.success)
            events = _read_jsonl(log_path)
            escalate_events = [e for e in events if e["event"] == "retry_escalate"]
            self.assertEqual(len(escalate_events), 1)
            self.assertEqual(escalate_events[0]["from_model"], "haiku")
            self.assertEqual(escalate_events[0]["to_model"], "sonnet")

    async def test_retry_attempt_log_events_include_model(self):
        """retry_attempt events record the active model at each attempt."""
        async def mock_dispatch(*, model_override=None, **kwargs) -> DispatchResult:
            if model_override == "haiku":
                return _failed("agent_test_failure")
            return _succeeded()

        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "events.jsonl"
            with (
                patch("cortex_command.pipeline.retry.dispatch_task", new=mock_dispatch),
                patch("cortex_command.pipeline.retry.cleanup_stale_lock"),
                patch(
                    "cortex_command.pipeline.retry._get_worktree_diff",
                    side_effect=_make_unique_diff_fn(),
                ),
            ):
                await retry_task(
                    feature="feat",
                    task="do something",
                    worktree_path=Path(tmp),
                    complexity="trivial",
                    system_prompt="",
                    learnings_dir=Path(tmp) / "learnings",
                    skill="implement",
                    log_path=log_path,
                    max_retries=3,
                )

            # Assertions inside the 'with' block so the temp dir still exists.
            events = _read_jsonl(log_path)
            attempt_events = [e for e in events if e["event"] == "retry_attempt"]
            models_logged = [e["model"] for e in attempt_events]

            # Both models used during escalation must appear in attempt logs.
            self.assertIn("haiku", models_logged)
            self.assertIn("sonnet", models_logged)

    async def test_opus_exhausted_pause_log_event_has_reason(self):
        """Pausing at opus logs a retry_paused_for_human event with reason and model."""
        async def mock_dispatch(**kwargs) -> DispatchResult:
            return _failed("agent_test_failure")

        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "events.jsonl"
            with (
                patch("cortex_command.pipeline.retry.dispatch_task", new=mock_dispatch),
                patch("cortex_command.pipeline.retry.cleanup_stale_lock"),
                patch(
                    "cortex_command.pipeline.retry._get_worktree_diff",
                    side_effect=_make_unique_diff_fn(),
                ),
            ):
                await retry_task(
                    feature="feat",
                    task="do something",
                    worktree_path=Path(tmp),
                    complexity="trivial",
                    system_prompt="",
                    learnings_dir=Path(tmp) / "learnings",
                    skill="implement",
                    log_path=log_path,
                    max_retries=5,
                )

            # Assertions inside the 'with' block so the temp dir still exists.
            events = _read_jsonl(log_path)
            paused_events = [e for e in events if e["event"] == "retry_paused_for_human"]
            opus_pause = next(
                (e for e in paused_events if e.get("model") == "opus"),
                None,
            )
            self.assertIsNotNone(
                opus_pause,
                "Expected a retry_paused_for_human event with model=opus",
            )
            self.assertIn(
                "exhausted",
                opus_pause.get("reason", "").lower(),
                "Pause reason must mention that the escalation ladder is exhausted",
            )

    async def test_total_cost_accumulates_across_escalated_attempts(self):
        """Total cost from all escalated attempts is summed in RetryResult."""
        async def mock_dispatch(*, model_override=None, **kwargs) -> DispatchResult:
            if model_override == "haiku":
                return _failed("agent_test_failure", cost=0.10)
            return _succeeded(cost=0.20)

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
                    complexity="trivial",
                    system_prompt="",
                    learnings_dir=Path(tmp) / "learnings",
                    skill="implement",
                    max_retries=3,
                )

        self.assertTrue(result.success)
        self.assertAlmostEqual(result.total_cost_usd, 0.30, places=6)


    async def test_budget_exhausted_pauses_immediately_without_retry(self):
        """budget_exhausted → pause_session → paused=True on attempt 1, no retry."""
        dispatch_calls = [0]

        async def mock_dispatch(**kwargs) -> DispatchResult:
            dispatch_calls[0] += 1
            return _failed("budget_exhausted")

        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch("cortex_command.pipeline.retry.dispatch_task", new=mock_dispatch),
                patch("cortex_command.pipeline.retry.cleanup_stale_lock"),
                patch("cortex_command.pipeline.retry._get_worktree_diff", return_value=""),
            ):
                result = await retry_task(
                    feature="feat",
                    task="do something",
                    worktree_path=Path(tmp),
                    complexity="trivial",
                    system_prompt="",
                    learnings_dir=Path(tmp) / "learnings",
                    skill="implement",
                    max_retries=3,
                )

        self.assertFalse(result.success)
        self.assertTrue(result.paused)
        self.assertEqual(result.attempts, 1)
        self.assertEqual(dispatch_calls[0], 1, "Must not have retried after budget_exhausted")

    async def test_budget_exhausted_logs_retry_paused_budget_exhausted_event(self):
        """budget_exhausted logs a retry_paused_budget_exhausted event to the log file."""
        import json as _json

        async def mock_dispatch(**kwargs) -> DispatchResult:
            return _failed("budget_exhausted")

        with tempfile.TemporaryDirectory() as tmp:
            log_file = Path(tmp) / "events.jsonl"
            with (
                patch("cortex_command.pipeline.retry.dispatch_task", new=mock_dispatch),
                patch("cortex_command.pipeline.retry.cleanup_stale_lock"),
                patch("cortex_command.pipeline.retry._get_worktree_diff", return_value=""),
            ):
                await retry_task(
                    feature="feat",
                    task="do something",
                    worktree_path=Path(tmp),
                    complexity="trivial",
                    system_prompt="",
                    learnings_dir=Path(tmp) / "learnings",
                    skill="implement",
                    log_path=log_file,
                    max_retries=3,
                )

            events = [_json.loads(line) for line in log_file.read_text().splitlines() if line.strip()]

        pause_events = [e for e in events if e.get("event") == "retry_paused_budget_exhausted"]
        self.assertEqual(len(pause_events), 1)
        self.assertEqual(pause_events[0]["error_type"], "budget_exhausted")
        self.assertEqual(pause_events[0]["recovery"], "pause_session")


if __name__ == "__main__":
    unittest.main()
