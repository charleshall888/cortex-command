"""Unit tests for brain.py and the _handle_failed_task circuit breaker check.

Tasks 2-3 — TestParseBrainResponse: 11 methods for _parse_brain_response().
Task 4    — TestDefaultDecision: 2 methods for _default_decision().
Tasks 5-6 — TestRequestBrainDecision: 5 async methods for request_brain_decision().
Task 7    — TestHandleFailedTask: 1 async method for the circuit-breaker pre-check.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import cortex_command.overnight.brain as brain_module
from cortex_command.overnight.brain import (
    BrainAction,
    BrainContext,
    BrainDecision,
    _default_decision,
    _parse_brain_response,
    request_brain_decision,
)
from cortex_command.overnight.feature_executor import _handle_failed_task
from cortex_command.overnight.types import CircuitBreakerState
from cortex_command.pipeline.dispatch import DispatchResult
from cortex_command.pipeline.parser import FeatureTask


# ---------------------------------------------------------------------------
# Task 2 + 3: _parse_brain_response() — parse variant and field coverage
# ---------------------------------------------------------------------------


class TestParseBrainResponse(unittest.TestCase):
    """Tests for _parse_brain_response() — all parse paths and field extraction."""

    # --- Task 2: 7 parse-variant tests ---

    def test_raw_json_object(self):
        """Plain JSON object in output → BrainDecision."""
        result = _parse_brain_response('{"action": "skip", "reasoning": "looks fine"}')
        self.assertIsInstance(result, BrainDecision)
        self.assertEqual(result.action, BrainAction.SKIP)

    def test_code_fenced_with_json_tag(self):
        """Code-fenced JSON with ```json tag → BrainDecision."""
        output = '```json\n{"action": "defer", "reasoning": "need info"}\n```'
        result = _parse_brain_response(output)
        self.assertIsInstance(result, BrainDecision)
        self.assertEqual(result.action, BrainAction.DEFER)

    def test_code_fenced_without_language_tag(self):
        """Code-fenced JSON without language tag → BrainDecision."""
        output = '```\n{"action": "pause", "reasoning": "unclear"}\n```'
        result = _parse_brain_response(output)
        self.assertIsInstance(result, BrainDecision)
        self.assertEqual(result.action, BrainAction.PAUSE)

    def test_malformed_non_json_string(self):
        """Completely non-JSON output → None."""
        result = _parse_brain_response("I cannot make a decision right now.")
        self.assertIsNone(result)

    def test_valid_json_that_is_list(self):
        """JSON array (not dict) → None (no {...} match)."""
        result = _parse_brain_response("[1, 2, 3]")
        self.assertIsNone(result)

    def test_json_dict_missing_action_field(self):
        """Dict without 'action' key → None."""
        result = _parse_brain_response('{"reasoning": "just a note"}')
        self.assertIsNone(result)

    def test_json_dict_with_unknown_action(self):
        """Dict with action not in {skip, defer, pause} → None."""
        result = _parse_brain_response('{"action": "retry", "reasoning": "try again"}')
        self.assertIsNone(result)

    # --- Task 3: 4 field-extraction tests ---

    def test_confidence_absent_defaults_to_half(self):
        """Missing confidence field defaults to 0.5."""
        result = _parse_brain_response('{"action": "skip", "reasoning": "ok"}')
        self.assertIsNotNone(result)
        self.assertEqual(result.confidence, 0.5)

    def test_confidence_integer_coerces_to_float(self):
        """Integer confidence coerces to float."""
        result = _parse_brain_response('{"action": "skip", "reasoning": "ok", "confidence": 1}')
        self.assertIsNotNone(result)
        self.assertEqual(result.confidence, 1.0)

    def test_confidence_non_numeric_string_fallback(self):
        """Non-numeric confidence string falls back to 0.5."""
        result = _parse_brain_response(
            '{"action": "skip", "reasoning": "ok", "confidence": "high"}'
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.confidence, 0.5)

    def test_optional_question_and_severity_extracted(self):
        """Optional question and severity fields are extracted when present."""
        result = _parse_brain_response(
            '{"action": "defer", "reasoning": "need input",'
            ' "question": "Is X correct?", "severity": "blocking"}'
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.question, "Is X correct?")
        self.assertEqual(result.severity, "blocking")


# ---------------------------------------------------------------------------
# Task 4: _default_decision() — always PAUSE
# ---------------------------------------------------------------------------


class TestDefaultDecision(unittest.TestCase):
    """Tests for _default_decision() — always returns PAUSE."""

    def test_returns_pause(self):
        result = _default_decision()
        self.assertEqual(result.action, BrainAction.PAUSE)
        self.assertEqual(result.confidence, 0.3)

    def test_no_severity_or_question(self):
        result = _default_decision()
        self.assertIsNone(result.severity)
        self.assertIsNone(result.question)


# ---------------------------------------------------------------------------
# Tasks 5-6: request_brain_decision() — success and failure paths
# ---------------------------------------------------------------------------


class TestRequestBrainDecision(unittest.IsolatedAsyncioTestCase):
    """Async tests for request_brain_decision() success and failure paths."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._log_path = Path(self._tmpdir.name) / "brain.log"
        self._ctx = BrainContext(
            feature="test-feat",
            task_description="do something",
            retry_count=1,
            learnings="none",
            spec_excerpt="spec text",
            last_attempt_output="failed output",
            has_dependents=False,
        )

    def tearDown(self):
        self._tmpdir.cleanup()

    def _start_patch(self, *args, **kwargs):
        p = patch(*args, **kwargs)
        mock = p.start()
        self.addCleanup(p.stop)
        return mock

    # --- Task 5: success paths ---

    async def test_dispatch_success_valid_json_returns_parsed_decision(self):
        """Dispatch succeeds with valid JSON → returns parsed BrainDecision."""
        mock_render = self._start_patch(
            "claude.overnight.brain._render_template", return_value="stub"
        )
        mock_dispatch = self._start_patch(
            "claude.overnight.brain.dispatch_task", new_callable=AsyncMock
        )
        mock_dispatch.return_value = DispatchResult(
            success=True,
            output='{"action": "skip", "reasoning": "all good"}',
        )
        mock_log = self._start_patch("claude.overnight.brain.pipeline_log_event")

        result = await request_brain_decision(self._ctx, None, self._log_path)

        self.assertIsInstance(result, BrainDecision)
        self.assertEqual(result.action, BrainAction.SKIP)
        mock_render.assert_called_once()

    async def test_dispatch_success_garbage_output_returns_fallback(self):
        """Dispatch succeeds but output unparseable → falls back to _default_decision."""
        self._start_patch(
            "claude.overnight.brain._render_template", return_value="stub"
        )
        mock_dispatch = self._start_patch(
            "claude.overnight.brain.dispatch_task", new_callable=AsyncMock
        )
        mock_dispatch.return_value = DispatchResult(success=True, output="garbage")
        self._start_patch("claude.overnight.brain.pipeline_log_event")

        result = await request_brain_decision(self._ctx, None, self._log_path)

        self.assertIsInstance(result, BrainDecision)
        self.assertEqual(result.action, BrainAction.PAUSE)

    async def test_parse_failure_emits_brain_unavailable_event(self):
        """Dispatch succeeds but parse returns None → brain_unavailable event logged."""
        self._start_patch(
            "claude.overnight.brain._render_template", return_value="stub"
        )
        mock_dispatch = self._start_patch(
            "claude.overnight.brain.dispatch_task", new_callable=AsyncMock
        )
        mock_dispatch.return_value = DispatchResult(success=True, output="valid looking")
        self._start_patch(
            "claude.overnight.brain._parse_brain_response", return_value=None
        )
        mock_log = self._start_patch("claude.overnight.brain.pipeline_log_event")

        result = await request_brain_decision(self._ctx, None, self._log_path)

        self.assertIsInstance(result, BrainDecision)
        self.assertEqual(result.action, BrainAction.PAUSE)
        mock_log.assert_called_once()
        event_dict = mock_log.call_args.args[1]
        self.assertEqual(event_dict["event"], "brain_unavailable")
        self.assertEqual(event_dict["error_type"], "parse_failure")
        self.assertEqual(event_dict["feature"], "test-feat")

    # --- Task 6: failure paths ---

    async def test_dispatch_failure_generic_logs_brain_unavailable(self):
        """Dispatch fails (generic) → pipeline_log_event called with brain_unavailable."""
        self._start_patch(
            "claude.overnight.brain._render_template", return_value="stub"
        )
        mock_dispatch = self._start_patch(
            "claude.overnight.brain.dispatch_task", new_callable=AsyncMock
        )
        mock_dispatch.return_value = DispatchResult(
            success=False, output="", error_type="generic_error"
        )
        mock_log = self._start_patch("claude.overnight.brain.pipeline_log_event")

        result = await request_brain_decision(self._ctx, None, self._log_path)

        self.assertIsInstance(result, BrainDecision)
        mock_log.assert_called_once()
        event_dict = mock_log.call_args.args[1]
        self.assertEqual(event_dict["event"], "brain_unavailable")

    async def test_dispatch_failure_infrastructure_calls_report_rate_limit(self):
        """Dispatch fails (infrastructure) with manager → manager.report_rate_limit() called."""
        self._start_patch(
            "claude.overnight.brain._render_template", return_value="stub"
        )
        mock_dispatch = self._start_patch(
            "claude.overnight.brain.dispatch_task", new_callable=AsyncMock
        )
        mock_dispatch.return_value = DispatchResult(
            success=False, output="", error_type="infrastructure_failure"
        )
        self._start_patch("claude.overnight.brain.pipeline_log_event")

        mock_manager = MagicMock()
        result = await request_brain_decision(self._ctx, mock_manager, self._log_path)

        self.assertIsInstance(result, BrainDecision)
        mock_manager.report_rate_limit.assert_called_once()


# ---------------------------------------------------------------------------
# Task 7: _handle_failed_task() — circuit breaker pre-check
# ---------------------------------------------------------------------------


class TestHandleFailedTask(unittest.IsolatedAsyncioTestCase):
    """Tests for the circuit-breaker pre-dispatch check in _handle_failed_task()."""

    async def test_circuit_breaker_skips_brain_call(self):
        """consecutive_pauses_ref=[2] fires the pre-check; brain is never called."""
        task = FeatureTask(
            number=1,
            description="desc",
            depends_on=[],
            files=[],
            complexity="simple",
        )
        retry_result = MagicMock(attempts=1, final_output="err")

        with patch(
            "claude.overnight.feature_executor.request_brain_decision", new_callable=AsyncMock
        ) as mock_request_brain:
            result = await _handle_failed_task(
                feature="test-feat",
                task=task,
                all_tasks=[],
                spec_excerpt="s",
                retry_result=retry_result,
                cb_state=CircuitBreakerState(consecutive_pauses=2),
                manager=None,
            )

        self.assertIsNone(result)
        self.assertEqual(mock_request_brain.call_count, 0)


# ---------------------------------------------------------------------------
# TestHandleFailedTaskBrainActions: SKIP / DEFER / PAUSE action dispatch
# ---------------------------------------------------------------------------


class TestHandleFailedTaskBrainActions(unittest.IsolatedAsyncioTestCase):
    """Tests for _handle_failed_task() brain-decision action dispatch (SKIP/DEFER/PAUSE)."""

    def _start_patch(self, *args, **kwargs):
        p = patch(*args, **kwargs)
        mock = p.start()
        self.addCleanup(p.stop)
        return mock

    def _make_task(self):
        return FeatureTask(
            number=1,
            description="desc",
            depends_on=[],
            files=[],
            complexity="simple",
        )

    async def test_skip_action_marks_task_done_and_returns_none(self):
        """SKIP action → returns None and mark_task_done_in_plan was called."""
        task = self._make_task()
        retry_result = MagicMock(attempts=1, final_output="err")

        mock_request_brain = self._start_patch(
            "claude.overnight.feature_executor.request_brain_decision",
            new_callable=AsyncMock,
        )
        mock_request_brain.return_value = BrainDecision(
            action=BrainAction.SKIP, reasoning="r", confidence=0.9
        )
        self._start_patch("claude.overnight.feature_executor.overnight_log_event")
        mock_mark_done = self._start_patch(
            "claude.overnight.feature_executor.mark_task_done_in_plan"
        )
        mock_write_deferral = self._start_patch(
            "claude.overnight.feature_executor.write_deferral"
        )
        self._start_patch(
            "claude.overnight.feature_executor._read_learnings",
            return_value="(No prior learnings.)",
        )

        result = await _handle_failed_task(
            feature="test-feat",
            task=task,
            all_tasks=[],
            spec_excerpt="s",
            retry_result=retry_result,
            cb_state=CircuitBreakerState(),
            manager=None,
        )

        self.assertIsNone(result)
        mock_mark_done.assert_called_once()
        mock_write_deferral.assert_not_called()

    async def test_defer_action_writes_deferral_and_returns_deferred_result(self):
        """DEFER action → returns FeatureResult(status='deferred') and write_deferral was called."""
        task = self._make_task()
        retry_result = MagicMock(attempts=1, final_output="err")

        mock_request_brain = self._start_patch(
            "claude.overnight.feature_executor.request_brain_decision",
            new_callable=AsyncMock,
        )
        mock_request_brain.return_value = BrainDecision(
            action=BrainAction.DEFER, reasoning="r", confidence=0.9
        )
        self._start_patch("claude.overnight.feature_executor.overnight_log_event")
        mock_mark_done = self._start_patch(
            "claude.overnight.feature_executor.mark_task_done_in_plan"
        )
        mock_write_deferral = self._start_patch(
            "claude.overnight.feature_executor.write_deferral"
        )
        self._start_patch(
            "claude.overnight.feature_executor._read_learnings",
            return_value="(No prior learnings.)",
        )

        result = await _handle_failed_task(
            feature="test-feat",
            task=task,
            all_tasks=[],
            spec_excerpt="s",
            retry_result=retry_result,
            cb_state=CircuitBreakerState(),
            manager=None,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.status, "deferred")
        self.assertEqual(result.deferred_question_count, 1)
        mock_write_deferral.assert_called_once()
        mock_mark_done.assert_not_called()

    async def test_pause_action_returns_none_without_side_effects(self):
        """PAUSE action → returns None and neither mark_task_done_in_plan nor write_deferral was called."""
        task = self._make_task()
        retry_result = MagicMock(attempts=1, final_output="err")

        mock_request_brain = self._start_patch(
            "claude.overnight.feature_executor.request_brain_decision",
            new_callable=AsyncMock,
        )
        mock_request_brain.return_value = BrainDecision(
            action=BrainAction.PAUSE, reasoning="r", confidence=0.9
        )
        self._start_patch("claude.overnight.feature_executor.overnight_log_event")
        mock_mark_done = self._start_patch(
            "claude.overnight.feature_executor.mark_task_done_in_plan"
        )
        mock_write_deferral = self._start_patch(
            "claude.overnight.feature_executor.write_deferral"
        )
        self._start_patch(
            "claude.overnight.feature_executor._read_learnings",
            return_value="(No prior learnings.)",
        )

        result = await _handle_failed_task(
            feature="test-feat",
            task=task,
            all_tasks=[],
            spec_excerpt="s",
            retry_result=retry_result,
            cb_state=CircuitBreakerState(),
            manager=None,
        )

        self.assertIsNone(result)
        mock_mark_done.assert_not_called()
        mock_write_deferral.assert_not_called()


if __name__ == "__main__":
    unittest.main()
