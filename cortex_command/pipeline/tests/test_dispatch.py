"""Unit tests for dispatch.py classify_error() and ERROR_RECOVERY.

Tests cover every classification subtype introduced by the failure
classification feature:

  - asyncio.TimeoutError  -> agent_timeout
  - CLIConnectionError    -> infrastructure_failure
  - ProcessError + timeout keyword in message     -> agent_timeout
  - ProcessError + timeout keyword in output      -> agent_timeout
  - ProcessError + test-failure keyword           -> agent_test_failure
  - ProcessError + refusal keyword                -> agent_refusal
  - ProcessError + confusion keyword              -> agent_confused
  - ProcessError with no matching keyword         -> task_failure
  - Generic Exception                             -> unknown
  - ERROR_RECOVERY maps each subtype to the correct recovery path
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

# conftest.py runs before this module under pytest and installs the SDK stub.
# Under plain unittest, we call _install_sdk_stub() directly here.
from cortex_command.pipeline.tests.conftest import _install_sdk_stub
_install_sdk_stub()

import cortex_command.pipeline.dispatch as _dispatch_module

# Pull stub exception types so isinstance checks match exactly.
_sdk = sys.modules["claude_agent_sdk"]
CLIConnectionError = _sdk.CLIConnectionError
ProcessError = _sdk.ProcessError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _process_error(msg: str) -> ProcessError:
    return ProcessError(msg)


def _cli_error(msg: str) -> CLIConnectionError:
    return CLIConnectionError(msg)


# ---------------------------------------------------------------------------
# Tests: classify_error()
# ---------------------------------------------------------------------------

class TestClassifyError(unittest.TestCase):
    """Tests for classify_error() covering all subtypes."""

    # --- Hard-typed exception branches ---

    def test_asyncio_timeout_error_returns_agent_timeout(self):
        err = asyncio.TimeoutError()
        self.assertEqual(_dispatch_module.classify_error(err), "agent_timeout")

    def test_asyncio_timeout_error_ignores_output(self):
        """Output is irrelevant when error is a hard asyncio.TimeoutError."""
        err = asyncio.TimeoutError()
        self.assertEqual(
            _dispatch_module.classify_error(err, "i cannot help you"),
            "agent_timeout",
        )

    def test_cli_connection_error_returns_infrastructure_failure(self):
        err = _cli_error("Claude CLI not found")
        self.assertEqual(
            _dispatch_module.classify_error(err), "infrastructure_failure"
        )

    def test_generic_exception_returns_unknown(self):
        err = ValueError("something unexpected")
        self.assertEqual(_dispatch_module.classify_error(err), "unknown")

    def test_generic_exception_with_timeout_in_message_returns_unknown(self):
        """Generic exceptions are not inspected for keywords; must stay 'unknown'."""
        err = RuntimeError("timeout occurred")
        self.assertEqual(_dispatch_module.classify_error(err), "unknown")

    # --- ProcessError: timeout keyword in exception message ---

    def test_process_error_timeout_keyword_returns_agent_timeout(self):
        err = _process_error("operation timed out after 30 s")
        self.assertEqual(_dispatch_module.classify_error(err), "agent_timeout")

    def test_process_error_timeout_literal_keyword(self):
        err = _process_error("timeout reached")
        self.assertEqual(_dispatch_module.classify_error(err), "agent_timeout")

    def test_process_error_time_out_two_words(self):
        err = _process_error("session will time out shortly")
        self.assertEqual(_dispatch_module.classify_error(err), "agent_timeout")

    # --- ProcessError: timeout keyword detected via output ---

    def test_process_error_timeout_in_output_returns_agent_timeout(self):
        err = _process_error("task failed")
        self.assertEqual(
            _dispatch_module.classify_error(err, output="process timed out"),
            "agent_timeout",
        )

    # --- ProcessError: test-failure keywords ---

    def test_process_error_test_failed_returns_agent_test_failure(self):
        err = _process_error("test failed: test_foo")
        self.assertEqual(_dispatch_module.classify_error(err), "agent_test_failure")

    def test_process_error_pytest_keyword_returns_agent_test_failure(self):
        err = _process_error("pytest exited with status 1")
        self.assertEqual(_dispatch_module.classify_error(err), "agent_test_failure")

    def test_process_error_assertion_error_keyword_returns_agent_test_failure(self):
        err = _process_error("AssertionError: expected True")
        self.assertEqual(_dispatch_module.classify_error(err), "agent_test_failure")

    def test_process_error_test_failure_in_output(self):
        err = _process_error("agent exited non-zero")
        self.assertEqual(
            _dispatch_module.classify_error(err, output="failing tests detected"),
            "agent_test_failure",
        )

    # --- ProcessError: refusal keywords ---

    def test_process_error_i_cannot_returns_agent_refusal(self):
        err = _process_error("I cannot complete this task")
        self.assertEqual(_dispatch_module.classify_error(err), "agent_refusal")

    def test_process_error_i_will_not_returns_agent_refusal(self):
        err = _process_error("I will not do that")
        self.assertEqual(_dispatch_module.classify_error(err), "agent_refusal")

    def test_process_error_cannot_help_in_output(self):
        err = _process_error("agent stopped")
        self.assertEqual(
            _dispatch_module.classify_error(err, output="I cannot help with this request"),
            "agent_refusal",
        )

    def test_process_error_i_must_refuse_returns_agent_refusal(self):
        err = _process_error("I must refuse this operation")
        self.assertEqual(_dispatch_module.classify_error(err), "agent_refusal")

    # --- ProcessError: confusion keywords ---

    def test_process_error_im_not_sure_returns_agent_confused(self):
        err = _process_error("I'm not sure what to do here")
        self.assertEqual(_dispatch_module.classify_error(err), "agent_confused")

    def test_process_error_i_dont_understand_returns_agent_confused(self):
        err = _process_error("I don't understand the requirements")
        self.assertEqual(_dispatch_module.classify_error(err), "agent_confused")

    def test_process_error_unclear_to_me_returns_agent_confused(self):
        err = _process_error("This is unclear to me")
        self.assertEqual(_dispatch_module.classify_error(err), "agent_confused")

    def test_process_error_im_lost_in_output_returns_agent_confused(self):
        err = _process_error("agent exited unexpectedly")
        self.assertEqual(
            _dispatch_module.classify_error(err, output="I am lost and don't know how to proceed"),
            "agent_confused",
        )

    # --- ProcessError: no keyword match ---

    def test_process_error_no_matching_keyword_returns_task_failure(self):
        err = _process_error("exit code 1")
        self.assertEqual(_dispatch_module.classify_error(err), "task_failure")

    def test_process_error_empty_message_returns_task_failure(self):
        err = _process_error("")
        self.assertEqual(_dispatch_module.classify_error(err), "task_failure")

    def test_process_error_empty_message_empty_output_returns_task_failure(self):
        err = _process_error("")
        self.assertEqual(_dispatch_module.classify_error(err, output=""), "task_failure")

    # --- Priority ordering: timeout > test_failure ---

    def test_timeout_takes_priority_over_test_failure_in_corpus(self):
        """When both timeout and test-failure patterns present, timeout wins."""
        err = _process_error("timed out while running pytest")
        self.assertEqual(_dispatch_module.classify_error(err), "agent_timeout")

    # --- Case insensitivity ---

    def test_refusal_pattern_case_insensitive(self):
        err = _process_error("I CANNOT do that")
        self.assertEqual(_dispatch_module.classify_error(err), "agent_refusal")

    def test_test_failure_pattern_case_insensitive(self):
        err = _process_error("TESTS FAILED")
        self.assertEqual(_dispatch_module.classify_error(err), "agent_test_failure")


# ---------------------------------------------------------------------------
# Tests: ERROR_RECOVERY
# ---------------------------------------------------------------------------

class TestErrorRecovery(unittest.TestCase):
    """Tests that ERROR_RECOVERY maps every error type to the correct path."""

    def test_agent_timeout_recovery_is_retry(self):
        self.assertEqual(_dispatch_module.ERROR_RECOVERY["agent_timeout"], "retry")

    def test_agent_test_failure_recovery_is_escalate(self):
        self.assertEqual(_dispatch_module.ERROR_RECOVERY["agent_test_failure"], "escalate")

    def test_agent_refusal_recovery_is_pause_human(self):
        self.assertEqual(_dispatch_module.ERROR_RECOVERY["agent_refusal"], "pause_human")

    def test_agent_confused_recovery_is_escalate(self):
        self.assertEqual(_dispatch_module.ERROR_RECOVERY["agent_confused"], "escalate")

    def test_task_failure_recovery_is_retry(self):
        self.assertEqual(_dispatch_module.ERROR_RECOVERY["task_failure"], "retry")

    def test_infrastructure_failure_recovery_is_pause_human(self):
        self.assertEqual(_dispatch_module.ERROR_RECOVERY["infrastructure_failure"], "pause_human")

    def test_unknown_recovery_is_retry(self):
        self.assertEqual(_dispatch_module.ERROR_RECOVERY["unknown"], "retry")

    def test_budget_exhausted_recovery_is_pause_session(self):
        self.assertEqual(_dispatch_module.ERROR_RECOVERY["budget_exhausted"], "pause_session")

    def test_all_new_subtypes_present_in_error_recovery(self):
        """All four new subtypes must appear in ERROR_RECOVERY."""
        new_subtypes = {
            "agent_timeout", "agent_test_failure", "agent_refusal", "agent_confused"
        }
        for subtype in new_subtypes:
            self.assertIn(
                subtype,
                _dispatch_module.ERROR_RECOVERY,
                f"Missing subtype {subtype!r} in ERROR_RECOVERY",
            )


# ---------------------------------------------------------------------------
# Tests: dispatch_task sandbox settings (async)
# ---------------------------------------------------------------------------

_sdk = sys.modules["claude_agent_sdk"]
ResultMessage = _sdk.ResultMessage


async def _async_gen(*items):
    for item in items:
        yield item


class TestDispatchTaskSandboxSettings(unittest.IsolatedAsyncioTestCase):
    """Tests that dispatch_task passes the correct sandbox settings to ClaudeAgentOptions."""

    async def test_worktree_path_in_write_allowlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            worktree = Path(tmp) / "feature-worktree"
            worktree.mkdir()

            captured: dict = {}

            async def mock_query(**kwargs):
                captured["options"] = kwargs.get("options")
                result_msg = ResultMessage(
                    subtype="success",
                    duration_ms=100,
                    duration_api_ms=80,
                    is_error=False,
                    num_turns=1,
                    session_id="sess-sandbox",
                    total_cost_usd=0.0,
                )
                async for m in _async_gen(result_msg):
                    yield m

            with patch.object(_dispatch_module, "query", mock_query):
                await _dispatch_module.dispatch_task(
                    feature="sandbox-test",
                    task="do something",
                    worktree_path=worktree,
                    complexity="simple",
                    system_prompt="",
                    skill="implement",
                )

            options = captured.get("options")
            self.assertIsNotNone(options, "ClaudeAgentOptions was not captured from query call")
            self.assertIsNotNone(options.settings, "settings= was not passed to ClaudeAgentOptions")

            # Per spec Req 5 (REVISED 2026-05-05), options.settings is a filepath
            # to a per-dispatch tempfile containing the sandbox JSON.
            settings = json.loads(Path(options.settings).read_text(encoding="utf-8"))
            allowlist = settings["sandbox"]["filesystem"]["allowWrite"]
            self.assertIn(
                str(worktree),
                allowlist,
                f"worktree path {worktree} not found in write allowlist: {allowlist}",
            )

    async def test_tmpdir_paths_absent_from_allowlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            worktree = Path(tmp) / "feature-worktree"
            worktree.mkdir()

            captured: dict = {}

            async def mock_query(**kwargs):
                captured["options"] = kwargs.get("options")
                result_msg = ResultMessage(
                    subtype="success",
                    duration_ms=100,
                    duration_api_ms=80,
                    is_error=False,
                    num_turns=1,
                    session_id="sess-tmpdir-absent",
                    total_cost_usd=0.0,
                )
                async for m in _async_gen(result_msg):
                    yield m

            with patch.object(_dispatch_module, "query", mock_query):
                await _dispatch_module.dispatch_task(
                    feature="tmpdir-absent-test",
                    task="do something",
                    worktree_path=worktree,
                    complexity="simple",
                    system_prompt="",
                    skill="implement",
                )

            options = captured.get("options")
            settings = json.loads(Path(options.settings).read_text(encoding="utf-8"))
            allowlist = settings["sandbox"]["filesystem"]["allowWrite"]
            self.assertNotIn("/tmp/claude", allowlist)
            self.assertNotIn("/private/tmp/claude", allowlist)

    async def test_only_worktree_paths_in_allowlist_without_integration_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            worktree = Path(tmp) / "feature-worktree"
            worktree.mkdir()

            captured: dict = {}

            async def mock_query(**kwargs):
                captured["options"] = kwargs.get("options")
                result_msg = ResultMessage(
                    subtype="success",
                    duration_ms=100,
                    duration_api_ms=80,
                    is_error=False,
                    num_turns=1,
                    session_id="sess-only-worktree",
                    total_cost_usd=0.0,
                )
                async for m in _async_gen(result_msg):
                    yield m

            with patch.object(_dispatch_module, "query", mock_query):
                await _dispatch_module.dispatch_task(
                    feature="only-worktree-test",
                    task="do something",
                    worktree_path=worktree,
                    complexity="simple",
                    system_prompt="",
                    skill="implement",
                )

            options = captured.get("options")
            settings = json.loads(Path(options.settings).read_text(encoding="utf-8"))
            allowlist = settings["sandbox"]["filesystem"]["allowWrite"]
            worktree_str = str(worktree)
            worktree_real = os.path.realpath(worktree_str)
            # The allowlist also includes the six OUT_OF_WORKTREE_ALLOW_WRITERS
            # entries per spec Req 10. Assert the worktree path is present;
            # any other entry must be one of the documented out-of-worktree writers.
            self.assertTrue(
                worktree_str in allowlist or worktree_real in allowlist,
                f"worktree path {worktree_str!r} (or its realpath) not in allowlist: {allowlist}",
            )

    async def test_integration_base_path_in_allowlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            worktree = Path(tmp) / "feature-worktree"
            worktree.mkdir()
            integration_base = Path("/some/integration/path")

            captured: dict = {}

            async def mock_query(**kwargs):
                captured["options"] = kwargs.get("options")
                result_msg = ResultMessage(
                    subtype="success",
                    duration_ms=100,
                    duration_api_ms=80,
                    is_error=False,
                    num_turns=1,
                    session_id="sess-integration-base",
                    total_cost_usd=0.0,
                )
                async for m in _async_gen(result_msg):
                    yield m

            with patch.object(_dispatch_module, "query", mock_query):
                await _dispatch_module.dispatch_task(
                    feature="integration-base-test",
                    task="do something",
                    worktree_path=worktree,
                    complexity="simple",
                    system_prompt="",
                    integration_base_path=integration_base,
                    skill="implement",
                )

            options = captured.get("options")
            settings = json.loads(Path(options.settings).read_text(encoding="utf-8"))
            allowlist = settings["sandbox"]["filesystem"]["allowWrite"]
            integration_str = str(integration_base)
            integration_real = os.path.realpath(integration_str)
            self.assertTrue(
                integration_str in allowlist or integration_real in allowlist,
                f"integration_base_path {integration_str!r} (or its realpath) "
                f"not found in allowlist: {allowlist}",
            )

    async def test_tmpdir_absent_with_integration_base_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            worktree = Path(tmp) / "feature-worktree"
            worktree.mkdir()
            integration_base = Path("/tmp/claude/overnight-worktrees/abc")

            captured: dict = {}

            async def mock_query(**kwargs):
                captured["options"] = kwargs.get("options")
                result_msg = ResultMessage(
                    subtype="success",
                    duration_ms=100,
                    duration_api_ms=80,
                    is_error=False,
                    num_turns=1,
                    session_id="sess-tmpdir-integration",
                    total_cost_usd=0.0,
                )
                async for m in _async_gen(result_msg):
                    yield m

            with patch.object(_dispatch_module, "query", mock_query):
                await _dispatch_module.dispatch_task(
                    feature="tmpdir-integration-test",
                    task="do something",
                    worktree_path=worktree,
                    complexity="simple",
                    system_prompt="",
                    integration_base_path=integration_base,
                    skill="implement",
                )

            options = captured.get("options")
            settings = json.loads(Path(options.settings).read_text(encoding="utf-8"))
            allowlist = settings["sandbox"]["filesystem"]["allowWrite"]
            # The specific integration path must be present (it was explicitly added)
            integration_str = str(integration_base)
            integration_real = os.path.realpath(integration_str)
            self.assertTrue(
                integration_str in allowlist or integration_real in allowlist,
                f"integration_base_path {integration_str!r} not found in allowlist: {allowlist}",
            )
            # But the parent /tmp/claude must NOT be in the allowlist
            self.assertNotIn(
                "/tmp/claude",
                allowlist,
                f"/tmp/claude (TMPDIR parent) should not be in allowlist: {allowlist}",
            )


# ---------------------------------------------------------------------------
# Tests: project settings propagation via repo_root — REMOVED
#
# These tests asserted that `dispatch_task` force-injected the merged project
# `.claude/settings*.json` blob (hooks, env, attribution, sandbox) into the
# dispatched-agent settings via `--settings`. Per spec Req 6 (lifecycle:
# apply-per-spawn-sandboxfilesystemdenywrite-at-all-overnight-spawn-sites),
# that blob-injection was deliberately removed: only the sandbox subtree is
# now consumed (via the `--settings <tempfile>` mechanism in spec Req 5);
# other project-settings keys merge naturally via Claude Code's documented
# multi-scope merge from project scope. The negative assertion (no hooks/env
# in the dispatched settings JSON) is covered by
# `tests/test_dispatch.py::test_no_blob_injection`.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Tests: dispatch_task budget exhaustion (ResultMessage.is_error=True)
# ---------------------------------------------------------------------------

class TestDispatchTaskBudgetExhausted(unittest.IsolatedAsyncioTestCase):
    """Tests that dispatch_task correctly detects ResultMessage.is_error=True."""

    async def test_budget_exhausted_returns_failure(self):
        """dispatch_task returns DispatchResult(success=False, error_type=budget_exhausted)
        when ResultMessage.is_error is True."""
        with tempfile.TemporaryDirectory() as tmp:
            worktree = Path(tmp) / "feature-worktree"
            worktree.mkdir()

            async def mock_query(**kwargs):
                result_msg = ResultMessage(
                    subtype="error_max_budget_usd",
                    duration_ms=100,
                    duration_api_ms=80,
                    is_error=True,
                    num_turns=1,
                    session_id="sess-budget-exhausted",
                    total_cost_usd=0.5,
                )
                async for m in _async_gen(result_msg):
                    yield m

            with patch.object(_dispatch_module, "query", mock_query):
                result = await _dispatch_module.dispatch_task(
                    feature="budget-test",
                    task="do something",
                    worktree_path=worktree,
                    complexity="simple",
                    system_prompt="",
                    skill="implement",
                )

            self.assertFalse(result.success)
            self.assertEqual(result.error_type, "budget_exhausted")
            self.assertIn("ResultMessage.is_error=True", result.error_detail)
            self.assertIn("error_max_budget_usd", result.error_detail)
            self.assertIn("[budget_exhausted: subtype=error_max_budget_usd]", result.output)
            self.assertEqual(result.cost_usd, 0.5)

    async def test_no_budget_exhausted_on_success_result(self):
        """dispatch_task returns DispatchResult(success=True) when ResultMessage.is_error
        is False — no regression for the normal path."""
        with tempfile.TemporaryDirectory() as tmp:
            worktree = Path(tmp) / "feature-worktree"
            worktree.mkdir()

            async def mock_query(**kwargs):
                result_msg = ResultMessage(
                    subtype="success",
                    duration_ms=100,
                    duration_api_ms=80,
                    is_error=False,
                    num_turns=1,
                    session_id="sess-budget-ok",
                    total_cost_usd=0.1,
                )
                async for m in _async_gen(result_msg):
                    yield m

            with patch.object(_dispatch_module, "query", mock_query):
                result = await _dispatch_module.dispatch_task(
                    feature="budget-ok-test",
                    task="do something",
                    worktree_path=worktree,
                    complexity="simple",
                    system_prompt="",
                    skill="implement",
                )

            self.assertTrue(result.success)
            self.assertIsNone(result.error_type)

    async def test_budget_exhausted_logs_dispatch_error_event(self):
        """dispatch_task logs a dispatch_error event with error_type=budget_exhausted."""
        with tempfile.TemporaryDirectory() as tmp:
            worktree = Path(tmp) / "feature-worktree"
            worktree.mkdir()
            log_file = Path(tmp) / "events.jsonl"

            async def mock_query(**kwargs):
                result_msg = ResultMessage(
                    subtype="error_max_budget_usd",
                    duration_ms=100,
                    duration_api_ms=80,
                    is_error=True,
                    num_turns=1,
                    session_id="sess-budget-log",
                    total_cost_usd=0.5,
                )
                async for m in _async_gen(result_msg):
                    yield m

            with patch.object(_dispatch_module, "query", mock_query):
                await _dispatch_module.dispatch_task(
                    feature="budget-log-test",
                    task="do something",
                    worktree_path=worktree,
                    complexity="simple",
                    system_prompt="",
                    log_path=log_file,
                    skill="implement",
                )

            import json as _json
            events = [_json.loads(line) for line in log_file.read_text().splitlines() if line.strip()]
            error_events = [e for e in events if e.get("event") == "dispatch_error"]
            self.assertEqual(len(error_events), 1)
            self.assertEqual(error_events[0]["error_type"], "budget_exhausted")


# ---------------------------------------------------------------------------
# Tests: dispatch_task _on_stderr redaction of sk-ant-* tokens
# ---------------------------------------------------------------------------


class TestDispatchTaskStderrRedaction(unittest.IsolatedAsyncioTestCase):
    """Tests that _on_stderr redacts sk-ant-* tokens before storing stderr."""

    async def test_on_stderr_redacts_sk_ant_tokens_stderr_redact(self):
        """sk-ant-abc123def in a stderr line is rewritten to sk-ant-<redacted>."""
        with tempfile.TemporaryDirectory() as tmp:
            worktree = Path(tmp) / "feature-worktree"
            worktree.mkdir()

            captured: dict = {}

            async def mock_query(**kwargs):
                options = kwargs.get("options")
                captured["options"] = options
                # Emit a synthetic stderr line containing a sk-ant-* token.
                if options is not None and options.stderr is not None:
                    options.stderr("error: leaked key sk-ant-abc123def trailing text")
                result_msg = ResultMessage(
                    subtype="success",
                    duration_ms=100,
                    duration_api_ms=80,
                    is_error=False,
                    num_turns=1,
                    session_id="sess-stderr-redact",
                    total_cost_usd=0.0,
                )
                async for m in _async_gen(result_msg):
                    yield m

            with patch.object(_dispatch_module, "query", mock_query):
                await _dispatch_module.dispatch_task(
                    feature="stderr-redact-test",
                    task="do something",
                    worktree_path=worktree,
                    complexity="simple",
                    system_prompt="",
                    skill="implement",
                )

            # _stderr_lines is a closure cell on the _on_stderr callback.
            on_stderr = captured["options"].stderr
            stderr_lines = None
            for name, cell in zip(on_stderr.__code__.co_freevars, on_stderr.__closure__ or ()):
                if name == "_stderr_lines":
                    stderr_lines = cell.cell_contents
                    break

            self.assertIsNotNone(stderr_lines, "_stderr_lines closure cell not found")
            self.assertEqual(len(stderr_lines), 1)
            line = stderr_lines[-1]
            self.assertIn("sk-ant-<redacted>", line)
            self.assertNotIn("sk-ant-abc123def", line)


# ---------------------------------------------------------------------------
# Tests: dispatch_task runtime validation guards (R3, R14)
# ---------------------------------------------------------------------------


class TestDispatchTaskValidation(unittest.IsolatedAsyncioTestCase):
    """Tests that dispatch_task raises ValueError on invalid skill / cycle args.

    These exercise the two runtime guards in dispatch.py (R3 + R14):
      - skill string not in get_args(Skill) -> ValueError mentioning the value.
      - cycle is not None and skill != "review-fix" -> ValueError mentioning cycle.
    Both guards must trigger before any sub-agent is launched, so no real
    SDK call is made.
    """

    async def test_dispatch_task_rejects_unregistered_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            worktree = Path(tmp) / "feature-worktree"
            worktree.mkdir()
            with pytest.raises(ValueError, match="not-a-real-skill"):
                await _dispatch_module.dispatch_task(
                    feature="validation-test",
                    task="do something",
                    worktree_path=worktree,
                    complexity="simple",
                    system_prompt="",
                    skill="not-a-real-skill",  # type: ignore[arg-type]
                )

    async def test_dispatch_task_rejects_cycle_for_non_review_fix(self):
        with tempfile.TemporaryDirectory() as tmp:
            worktree = Path(tmp) / "feature-worktree"
            worktree.mkdir()
            with pytest.raises(ValueError, match="cycle"):
                await _dispatch_module.dispatch_task(
                    feature="validation-test",
                    task="do something",
                    worktree_path=worktree,
                    complexity="simple",
                    system_prompt="",
                    skill="implement",
                    cycle=2,
                )


# ---------------------------------------------------------------------------
# Tests: SDK message parser extracts stop_reason
# ---------------------------------------------------------------------------

def test_sdk_parser_extracts_stop_reason():
    """Verifies that the upgraded claude-agent-sdk's CLI message parser extracts
    `stop_reason` from a result-type JSON line into the typed `ResultMessage`.

    This is the load-bearing gate of Spec Req #6: if the upgraded SDK's parser
    drops `stop_reason`, this test fails and the implementation must add a
    wrapper/extractor before the truncation observability stack can rely on it.

    The conftest installs a stub at ``sys.modules['claude_agent_sdk']`` for all
    other tests in this package. We bypass that stub here by temporarily removing
    the stub modules from sys.modules, importing the real SDK's
    ``_internal.message_parser`` directly, then restoring the stub so the rest
    of the test session is unaffected.
    """
    import importlib

    # Snapshot and remove any stub/real modules so a fresh import binds to
    # the real package on disk.
    saved: dict[str, Any] = {}
    for key in list(sys.modules):
        if key == "claude_agent_sdk" or key.startswith("claude_agent_sdk."):
            saved[key] = sys.modules.pop(key)

    try:
        real_parser = importlib.import_module(
            "claude_agent_sdk._internal.message_parser"
        )
        real_types = importlib.import_module("claude_agent_sdk.types")

        # Confirm we actually loaded the real SDK (not the stub) — the stub
        # has the marker attribute set in _stubs.py:_install_sdk_stub.
        real_sdk_root = sys.modules["claude_agent_sdk"]
        assert not getattr(real_sdk_root, "_is_test_stub", False), (
            "Expected to load the real claude_agent_sdk, not the test stub"
        )

        # Canned CLI JSON line for a result-type message containing
        # stop_reason="max_tokens". Field shape mirrors what the CLI emits.
        cli_json_line = (
            '{"type": "result", "subtype": "success", "duration_ms": 1234,'
            ' "duration_api_ms": 1000, "is_error": false, "num_turns": 3,'
            ' "session_id": "sess-abc", "stop_reason": "max_tokens",'
            ' "total_cost_usd": 0.012, "usage": {"input_tokens": 10},'
            ' "result": "partial output", "structured_output": null}'
        )
        data = json.loads(cli_json_line)

        parsed = real_parser.parse_message(data)

        assert isinstance(parsed, real_types.ResultMessage)
        assert parsed.stop_reason == "max_tokens"
    finally:
        # Restore the stub so subsequent tests in this session see what
        # they expect.
        for key in list(sys.modules):
            if key == "claude_agent_sdk" or key.startswith("claude_agent_sdk."):
                del sys.modules[key]
        sys.modules.update(saved)


# ---------------------------------------------------------------------------
# Tests: _EFFORT_MATRIX policy and resolve_effort()
# ---------------------------------------------------------------------------

def test_effort_matrix_policy():
    """Iterates all 12 (complexity, criticality) cells and asserts the policy
    table from spec §1 Technical Constraints.

    The matrix is the single source of truth for baseline effort resolution
    (Spec Req #1, #2). Cell values are verbatim from the policy table — 8 of
    12 cells change effort relative to the previous 1D ``EFFORT_MAP``.
    """
    expected: dict[tuple[str, str], str] = {
        ("trivial", "low"):      "low",
        ("trivial", "medium"):   "low",
        ("trivial", "high"):     "high",
        ("trivial", "critical"): "high",
        ("simple",  "low"):      "high",
        ("simple",  "medium"):   "high",
        ("simple",  "high"):     "high",
        ("simple",  "critical"): "high",
        ("complex", "low"):      "high",
        ("complex", "medium"):   "high",
        ("complex", "high"):     "xhigh",
        ("complex", "critical"): "xhigh",
    }
    assert len(_dispatch_module._EFFORT_MATRIX) == 12, (
        "matrix must have exactly 12 cells (3 complexity x 4 criticality)"
    )
    assert _dispatch_module._EFFORT_MATRIX == expected, (
        f"matrix policy mismatch: got {_dispatch_module._EFFORT_MATRIX!r}, "
        f"expected {expected!r}"
    )


def test_effort_skill_overrides():
    """Exercises review-fix and integration-recovery on opus and on sonnet.

    Spec Req #3 + §2: ``review-fix`` and ``integration-recovery`` get
    ``effort="max"`` when the resolved (post-``model_override``) model is opus;
    on any other model the matrix value applies. No silent downgrade.
    """
    # review-fix on opus -> max (overrides the matrix's xhigh).
    assert _dispatch_module.resolve_effort(
        complexity="complex", criticality="high",
        skill="review-fix", model="opus",
    ) == "max"
    assert _dispatch_module.resolve_effort(
        complexity="complex", criticality="critical",
        skill="review-fix", model="opus",
    ) == "max"

    # review-fix on sonnet -> matrix value (high), no override.
    assert _dispatch_module.resolve_effort(
        complexity="simple", criticality="high",
        skill="review-fix", model="sonnet",
    ) == "high"
    assert _dispatch_module.resolve_effort(
        complexity="complex", criticality="low",
        skill="review-fix", model="sonnet",
    ) == "high"

    # integration-recovery on opus -> max.
    assert _dispatch_module.resolve_effort(
        complexity="complex", criticality="high",
        skill="integration-recovery", model="opus",
    ) == "max"

    # integration-recovery on sonnet -> matrix value (high).
    assert _dispatch_module.resolve_effort(
        complexity="complex", criticality="medium",
        skill="integration-recovery", model="sonnet",
    ) == "high"

    # Non-overriding skill on opus -> matrix value (xhigh, no override).
    assert _dispatch_module.resolve_effort(
        complexity="complex", criticality="high",
        skill="implement", model="opus",
    ) == "xhigh"


def test_effort_value_passthrough():
    """Verifies that each effort value in the closed vocabulary constructs
    cleanly via ``ClaudeAgentOptions(effort=v)`` AND that the SDK's
    ``SubprocessCLITransport._build_command`` propagates it as
    ``["--effort", v]`` in the constructed argv.

    Covers Spec Req #10. Bypasses the conftest stub so we exercise the real
    SDK's ``ClaudeAgentOptions`` and CLI-argv builder; restores the stub on
    exit so subsequent tests in this session are unaffected.
    """
    import importlib

    saved: dict[str, Any] = {}
    for key in list(sys.modules):
        if key == "claude_agent_sdk" or key.startswith("claude_agent_sdk."):
            saved[key] = sys.modules.pop(key)

    try:
        real_sdk = importlib.import_module("claude_agent_sdk")
        # Confirm we have the real SDK, not the stub.
        assert not getattr(real_sdk, "_is_test_stub", False), (
            "Expected to load the real claude_agent_sdk, not the test stub"
        )
        real_options_cls = real_sdk.ClaudeAgentOptions
        transport_mod = importlib.import_module(
            "claude_agent_sdk._internal.transport.subprocess_cli"
        )
        SubprocessCLITransport = transport_mod.SubprocessCLITransport

        for value in ("low", "medium", "high", "xhigh", "max"):
            # Constructs cleanly. The SDK currently types effort as
            # Literal["low","medium","high","max"], but Python does not enforce
            # Literal at runtime, so xhigh passes through as an opaque string
            # (Spec §3, Req #10).
            opts = real_options_cls(effort=value)
            assert opts.effort == value

            # Build CLI argv via the SDK's transport. We avoid actually
            # connecting (which would call the CLI binary) by constructing
            # the transport with a synthetic cli_path so _build_command
            # can run without _find_cli failing.
            opts_with_cli = real_options_cls(
                effort=value,
                cli_path="/usr/bin/true",  # any path; we never exec it.
            )
            transport = SubprocessCLITransport(
                prompt="", options=opts_with_cli,
            )
            argv = transport._build_command()
            # The argv must contain the pair `["--effort", value]` in order.
            for i in range(len(argv) - 1):
                if argv[i] == "--effort":
                    assert argv[i + 1] == value, (
                        f"effort flag value mismatch for {value!r}: argv={argv!r}"
                    )
                    break
            else:
                raise AssertionError(
                    f"--effort flag missing from argv for value {value!r}: {argv!r}"
                )
    finally:
        for key in list(sys.modules):
            if key == "claude_agent_sdk" or key.startswith("claude_agent_sdk."):
                del sys.modules[key]
        sys.modules.update(saved)


def test_effort_runtime_guard_rejects_unsupported_effort_for_model(monkeypatch):
    """Asserts the runtime guard fires loudly when a resolved effort is not
    supported by the resolved model per spec §3.

    The runtime guard MUST be ``raise ValueError`` (not ``assert``) per the
    plan's Risks section — ``assert`` is stripped under ``python -O`` /
    ``PYTHONOPTIMIZE=1``, defeating spec §3's "MUST fail loudly" intent.

    We force a synthetic matrix entry to ``"xhigh"`` for a (complexity,
    criticality) pair that resolves to a non-Opus model, then call
    ``resolve_effort`` for a non-overriding skill so the guard branch fires.
    """
    forced = dict(_dispatch_module._EFFORT_MATRIX)
    forced[("simple", "low")] = "xhigh"
    monkeypatch.setattr(_dispatch_module, "_EFFORT_MATRIX", forced)

    with pytest.raises(ValueError, match="not supported by model 'haiku'"):
        _dispatch_module.resolve_effort(
            complexity="simple",
            criticality="low",
            skill="implement",
            model="haiku",
        )


if __name__ == "__main__":
    unittest.main()
