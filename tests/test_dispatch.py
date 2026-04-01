"""Unit tests for dispatch.py budget-exhausted path, rate-limit classification,
and stderr accumulator integration.

These tests use asyncio.run() inside synchronous test methods because
pytest-asyncio is not a project dependency.
"""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# Install the SDK stub before importing dispatch.
from claude.tests._stubs import _install_sdk_stub
_install_sdk_stub()

import claude.pipeline.dispatch as _dispatch_module  # noqa: E402

_sdk = sys.modules["claude_agent_sdk"]
ResultMessage = _sdk.ResultMessage
ProcessError = _sdk.ProcessError
ClaudeAgentOptions = _sdk.ClaudeAgentOptions


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _async_gen(*items):
    for item in items:
        yield item


# ---------------------------------------------------------------------------
# Test 1: budget-exhausted dispatch path
# ---------------------------------------------------------------------------

class TestBudgetExhaustedDispatchPath(unittest.TestCase):
    """dispatch_task returns success=False / error_type=budget_exhausted when
    ResultMessage.is_error is True with subtype error_max_budget_usd."""

    def test_budget_exhausted_returns_failure_result(self):
        async def _run():
            async def mock_query(**kwargs):
                msg = ResultMessage(
                    subtype="error_max_budget_usd",
                    duration_ms=100,
                    duration_api_ms=80,
                    is_error=True,
                    num_turns=1,
                    session_id="sess-budget-test",
                    total_cost_usd=0.01,
                )
                async for m in _async_gen(msg):
                    yield m

            with patch("claude.pipeline.dispatch.query", new=mock_query):
                return await _dispatch_module.dispatch_task(
                    feature="budget-test",
                    task="do something",
                    worktree_path=Path("/tmp"),
                    complexity="simple",
                    system_prompt="test",
                )

        result = asyncio.run(_run())
        self.assertFalse(result.success)
        self.assertEqual(result.error_type, "budget_exhausted")


# ---------------------------------------------------------------------------
# Test 2: rate-limit classify_error
# ---------------------------------------------------------------------------

class TestRateLimitClassifyError(unittest.TestCase):
    """classify_error returns api_rate_limit when the ProcessError message
    contains a rate-limit keyword pattern."""

    def test_rate_limit_error_in_output_returns_api_rate_limit(self):
        err = ProcessError("Command failed")
        result = _dispatch_module.classify_error(err, "rate_limit_error in response")
        self.assertEqual(result, "api_rate_limit")


# ---------------------------------------------------------------------------
# Test 3: stderr accumulator integration
# ---------------------------------------------------------------------------

class TestStderrAccumulatorIntegration(unittest.TestCase):
    """dispatch_task classifies error as api_rate_limit when stderr lines
    contain a rate-limit keyword and query raises ProcessError."""

    def test_stderr_rate_limit_line_yields_api_rate_limit_error_type(self):
        async def _run():
            captured_options = {}

            # Wrap ClaudeAgentOptions to intercept the stderr callback.
            _original_cls = ClaudeAgentOptions

            class _CapturingOptions(_original_cls):
                def __init__(self, **kwargs):
                    super().__init__(**kwargs)
                    captured_options["stderr"] = kwargs.get("stderr")

            async def mock_query(**kwargs):
                # Call the stderr callback with a rate-limit line before raising.
                stderr_cb = captured_options.get("stderr")
                if stderr_cb is not None:
                    stderr_cb("rate limit error received from API")
                raise ProcessError("Command failed")
                # Make this an async generator (required yield for the type).
                yield  # pragma: no cover  -- never reached

            with patch("claude.pipeline.dispatch.ClaudeAgentOptions", new=_CapturingOptions):
                with patch("claude.pipeline.dispatch.query", new=mock_query):
                    return await _dispatch_module.dispatch_task(
                        feature="stderr-test",
                        task="do something",
                        worktree_path=Path("/tmp"),
                        complexity="simple",
                        system_prompt="test",
                    )

        result = asyncio.run(_run())
        self.assertFalse(result.success)
        self.assertEqual(result.error_type, "api_rate_limit")


if __name__ == "__main__":
    unittest.main()
