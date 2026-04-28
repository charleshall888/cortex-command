"""Unit tests for dispatch.py instrumentation (activity log / JSONL events).

Tests cover:
  - Tool call + tool result events written to JSONL on a normal run
  - ToolResultBlock with is_error=True produces "success": false
  - Write errors in _write_activity_event do not crash dispatch
  - _extract_input_summary truncates to 80 chars
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# conftest.py runs before this module under pytest and installs the SDK stub.
# Under plain unittest, we call _install_sdk_stub() directly here.
from cortex_command.pipeline.tests.conftest import _install_sdk_stub
_install_sdk_stub()
import cortex_command.pipeline.dispatch as _dispatch_module

# Pull stub types from the installed stub module so isinstance checks in
# dispatch.py and the types used in test message construction match exactly.
_sdk = sys.modules["claude_agent_sdk"]
AssistantMessage = _sdk.AssistantMessage
UserMessage = _sdk.UserMessage
ResultMessage = _sdk.ResultMessage
TextBlock = _sdk.TextBlock
ToolUseBlock = _sdk.ToolUseBlock
ToolResultBlock = _sdk.ToolResultBlock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _async_gen(*items):
    """Yield items from a scripted async generator."""
    for item in items:
        yield item


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


# ---------------------------------------------------------------------------
# Tests: _extract_input_summary (synchronous, no SDK interaction)
# ---------------------------------------------------------------------------

class TestExtractInputSummary(unittest.TestCase):
    """Tests for _extract_input_summary — pure string logic."""

    def test_truncates_to_80_chars(self):
        long_path = "x" * 200
        result = _dispatch_module._extract_input_summary("Read", {"file_path": long_path})
        self.assertEqual(len(result), 80)
        self.assertEqual(result, long_path[:80])

    def test_short_value_not_truncated(self):
        result = _dispatch_module._extract_input_summary("Read", {"file_path": "foo.py"})
        self.assertEqual(result, "foo.py")

    def test_bash_uses_command_key(self):
        result = _dispatch_module._extract_input_summary("Bash", {"command": "ls -la"})
        self.assertEqual(result, "ls -la")

    def test_glob_uses_pattern_key(self):
        result = _dispatch_module._extract_input_summary("Glob", {"pattern": "**/*.py"})
        self.assertEqual(result, "**/*.py")

    def test_grep_uses_pattern_key(self):
        result = _dispatch_module._extract_input_summary("Grep", {"pattern": "def.*func"})
        self.assertEqual(result, "def.*func")

    def test_write_uses_file_path_key(self):
        result = _dispatch_module._extract_input_summary("Write", {"file_path": "out.txt"})
        self.assertEqual(result, "out.txt")

    def test_unknown_tool_uses_first_value(self):
        result = _dispatch_module._extract_input_summary("Unknown", {"some_key": "val"})
        self.assertEqual(result, "val")

    def test_empty_input_dict(self):
        result = _dispatch_module._extract_input_summary("Unknown", {})
        self.assertEqual(result, "")

    def test_exactly_80_chars_not_truncated(self):
        val = "a" * 80
        result = _dispatch_module._extract_input_summary("Bash", {"command": val})
        self.assertEqual(result, val)


# ---------------------------------------------------------------------------
# Tests: dispatch_task JSONL instrumentation (async)
# ---------------------------------------------------------------------------

class TestActivityLogJSONL(unittest.IsolatedAsyncioTestCase):
    """Tests that dispatch_task writes correct events to the activity JSONL."""

    async def test_tool_call_and_result_events_written(self):
        """Normal run: tool_call + tool_result + turn_complete events in JSONL."""
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "activity.jsonl"

            assistant_msg = AssistantMessage(
                content=[
                    ToolUseBlock(id="tu1", name="Write", input={"file_path": "foo.py"}),
                ],
                model="sonnet",
            )
            user_msg = UserMessage(
                content=[
                    ToolResultBlock(tool_use_id="tu1", content="ok", is_error=None),
                ]
            )
            result_msg = ResultMessage(
                subtype="success",
                duration_ms=1000,
                duration_api_ms=800,
                is_error=False,
                num_turns=1,
                session_id="sess-1",
                total_cost_usd=0.01,
            )

            async def mock_query(**kwargs):
                async for m in _async_gen(assistant_msg, user_msg, result_msg):
                    yield m

            with patch.object(_dispatch_module, "query", mock_query):
                result = await _dispatch_module.dispatch_task(
                    feature="test-feat",
                    task="do something",
                    worktree_path=Path(tmp),
                    complexity="simple",
                    system_prompt="",
                    activity_log_path=log_path,
                    skill="implement",
                )

            # Assertions inside the 'with' block so the temp dir still exists.
            self.assertTrue(result.success, f"dispatch failed: {result.error_detail}")
            events = _read_jsonl(log_path)

            event_types = [e["event"] for e in events]
            self.assertIn("tool_call", event_types)
            self.assertIn("tool_result", event_types)
            self.assertIn("turn_complete", event_types)

            tool_call_evt = next(e for e in events if e["event"] == "tool_call")
            self.assertEqual(tool_call_evt["tool"], "Write")
            self.assertEqual(tool_call_evt["input_summary"], "foo.py")

            tool_result_evt = next(e for e in events if e["event"] == "tool_result")
            self.assertEqual(tool_result_evt["tool"], "Write")
            self.assertTrue(tool_result_evt["success"])

            turn_evt = next(e for e in events if e["event"] == "turn_complete")
            self.assertEqual(turn_evt["turn"], 1)
            self.assertAlmostEqual(turn_evt["cost_usd"], 0.01)

    async def test_tool_result_is_error_true_produces_success_false(self):
        """ToolResultBlock with is_error=True -> "success": false in JSONL."""
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "activity.jsonl"

            assistant_msg = AssistantMessage(
                content=[
                    ToolUseBlock(id="tu2", name="Bash", input={"command": "bad-cmd"}),
                ],
                model="sonnet",
            )
            user_msg = UserMessage(
                content=[
                    ToolResultBlock(tool_use_id="tu2", content="error output", is_error=True),
                ]
            )
            result_msg = ResultMessage(
                subtype="success",
                duration_ms=500,
                duration_api_ms=400,
                is_error=False,
                num_turns=1,
                session_id="sess-2",
                total_cost_usd=0.005,
            )

            async def mock_query(**kwargs):
                async for m in _async_gen(assistant_msg, user_msg, result_msg):
                    yield m

            with patch.object(_dispatch_module, "query", mock_query):
                result = await _dispatch_module.dispatch_task(
                    feature="test-feat",
                    task="run failing command",
                    worktree_path=Path(tmp),
                    complexity="simple",
                    system_prompt="",
                    activity_log_path=log_path,
                    skill="implement",
                )

            # Assertions inside 'with' so temp dir still exists.
            self.assertTrue(result.success, f"dispatch failed: {result.error_detail}")
            events = _read_jsonl(log_path)

            tool_result_evts = [e for e in events if e["event"] == "tool_result"]
            self.assertEqual(len(tool_result_evts), 1)
            self.assertFalse(
                tool_result_evts[0]["success"],
                "Expected success=false for is_error=True tool result",
            )
            self.assertEqual(tool_result_evts[0]["tool"], "Bash")

    async def test_write_error_does_not_propagate(self):
        """A write error in _write_activity_event must not crash dispatch."""
        with tempfile.TemporaryDirectory() as tmp:
            # Use a path whose parent does not exist to ensure the write would
            # fail if log_event were called normally; we also patch it to raise.
            log_path = Path(tmp) / "nonexistent_dir" / "activity.jsonl"

            assistant_msg = AssistantMessage(
                content=[
                    ToolUseBlock(id="tu3", name="Read", input={"file_path": "bar.py"}),
                ],
                model="sonnet",
            )
            user_msg = UserMessage(
                content=[
                    ToolResultBlock(tool_use_id="tu3", content="content"),
                ]
            )
            result_msg = ResultMessage(
                subtype="success",
                duration_ms=200,
                duration_api_ms=150,
                is_error=False,
                num_turns=1,
                session_id="sess-3",
                total_cost_usd=0.001,
            )

            async def mock_query(**kwargs):
                async for m in _async_gen(assistant_msg, user_msg, result_msg):
                    yield m

            # Patch log_event (called inside _write_activity_event) to raise
            with patch.object(_dispatch_module, "query", mock_query):
                with patch("cortex_command.pipeline.dispatch.log_event", side_effect=OSError("disk full")):
                    result = await _dispatch_module.dispatch_task(
                        feature="test-feat",
                        task="task with failing log",
                        worktree_path=Path(tmp),
                        complexity="simple",
                        system_prompt="",
                        activity_log_path=log_path,
                        skill="implement",
                    )

            # dispatch must succeed even though all log writes raised
            self.assertTrue(
                result.success,
                f"dispatch should succeed despite log errors: {result.error_detail}",
            )

    async def test_dispatch_start_includes_skill_fields(self):
        """dispatch_start JSONL emission contains new keys in spec'd order.

        Verifies (a) review-fix invocation with cycle=1 produces keys in the
        order: event, feature, skill, attempt, escalated, escalation_event,
        cycle, complexity, criticality, model, effort, max_turns,
        max_budget_usd; and (b) non-review-fix invocation (skill='implement')
        omits the cycle key entirely.
        """
        expected_with_cycle = [
            "event",
            "feature",
            "skill",
            "attempt",
            "escalated",
            "escalation_event",
            "cycle",
            "complexity",
            "criticality",
            "model",
            "effort",
            "max_turns",
            "max_budget_usd",
        ]
        expected_without_cycle = [k for k in expected_with_cycle if k != "cycle"]

        # Case 1: review-fix with cycle -> cycle key present.
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "pipeline-events.log"

            assistant_msg = AssistantMessage(
                content=[TextBlock(text="done")],
                model="sonnet",
            )
            result_msg = ResultMessage(
                subtype="success",
                duration_ms=100,
                duration_api_ms=80,
                is_error=False,
                num_turns=1,
                session_id="sess-rf",
                total_cost_usd=0.0,
            )

            async def mock_query(**kwargs):
                async for m in _async_gen(assistant_msg, result_msg):
                    yield m

            with patch.object(_dispatch_module, "query", mock_query):
                await _dispatch_module.dispatch_task(
                    feature="test-feat",
                    task="review-fix task",
                    worktree_path=Path(tmp),
                    complexity="simple",
                    system_prompt="",
                    log_path=log_path,
                    skill="review-fix",
                    attempt=1,
                    escalated=False,
                    escalation_event=False,
                    cycle=1,
                )

            events = _read_jsonl(log_path)
            start_evts = [e for e in events if e["event"] == "dispatch_start"]
            self.assertEqual(len(start_evts), 1, f"expected 1 dispatch_start, got {len(start_evts)}")
            start_evt = start_evts[0]
            self.assertEqual(
                list(start_evt.keys()),
                expected_with_cycle,
                f"key order mismatch for review-fix dispatch_start: {list(start_evt.keys())}",
            )
            self.assertEqual(start_evt["skill"], "review-fix")
            self.assertEqual(start_evt["cycle"], 1)

        # Case 2: non-review-fix (cycle=None) -> cycle key absent.
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "pipeline-events.log"

            assistant_msg = AssistantMessage(
                content=[TextBlock(text="done")],
                model="sonnet",
            )
            result_msg = ResultMessage(
                subtype="success",
                duration_ms=100,
                duration_api_ms=80,
                is_error=False,
                num_turns=1,
                session_id="sess-impl",
                total_cost_usd=0.0,
            )

            async def mock_query(**kwargs):
                async for m in _async_gen(assistant_msg, result_msg):
                    yield m

            with patch.object(_dispatch_module, "query", mock_query):
                await _dispatch_module.dispatch_task(
                    feature="test-feat",
                    task="implement task",
                    worktree_path=Path(tmp),
                    complexity="simple",
                    system_prompt="",
                    log_path=log_path,
                    skill="implement",
                )

            events = _read_jsonl(log_path)
            start_evts = [e for e in events if e["event"] == "dispatch_start"]
            self.assertEqual(len(start_evts), 1, f"expected 1 dispatch_start, got {len(start_evts)}")
            start_evt = start_evts[0]
            self.assertNotIn("cycle", start_evt, "cycle must be absent for non-review-fix dispatch_start")
            self.assertEqual(
                list(start_evt.keys()),
                expected_without_cycle,
                f"key order mismatch for non-review-fix dispatch_start: {list(start_evt.keys())}",
            )
            self.assertEqual(start_evt["skill"], "implement")

    async def test_no_activity_log_path_does_not_write_file(self):
        """When activity_log_path is None, no JSONL file is created."""
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "should_not_exist.jsonl"

            assistant_msg = AssistantMessage(
                content=[TextBlock(text="hello")],
                model="sonnet",
            )
            result_msg = ResultMessage(
                subtype="success",
                duration_ms=100,
                duration_api_ms=80,
                is_error=False,
                num_turns=1,
                session_id="sess-4",
                total_cost_usd=0.0,
            )

            async def mock_query(**kwargs):
                async for m in _async_gen(assistant_msg, result_msg):
                    yield m

            with patch.object(_dispatch_module, "query", mock_query):
                await _dispatch_module.dispatch_task(
                    feature="test-feat",
                    task="no log",
                    worktree_path=Path(tmp),
                    complexity="simple",
                    system_prompt="",
                    activity_log_path=None,
                    skill="implement",
                )

            self.assertFalse(log_path.exists())


if __name__ == "__main__":
    unittest.main()
