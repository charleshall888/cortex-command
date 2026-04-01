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

# conftest.py runs before this module under pytest and installs the SDK stub.
# Under plain unittest, we call _install_sdk_stub() directly here.
from claude.pipeline.tests.conftest import _install_sdk_stub
_install_sdk_stub()

import claude.pipeline.dispatch as _dispatch_module

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
                )

            options = captured.get("options")
            self.assertIsNotNone(options, "ClaudeAgentOptions was not captured from query call")
            self.assertIsNotNone(options.settings, "settings= was not passed to ClaudeAgentOptions")

            settings = json.loads(options.settings)
            allowlist = settings["sandbox"]["write"]["allowOnly"]
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
                )

            options = captured.get("options")
            settings = json.loads(options.settings)
            allowlist = settings["sandbox"]["write"]["allowOnly"]
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
                )

            options = captured.get("options")
            settings = json.loads(options.settings)
            allowlist = settings["sandbox"]["write"]["allowOnly"]
            worktree_str = str(worktree)
            worktree_real = os.path.realpath(worktree_str)
            for entry in allowlist:
                self.assertIn(
                    entry,
                    {worktree_str, worktree_real},
                    f"Unexpected entry in allowlist: {entry!r}; "
                    f"expected only worktree paths {worktree_str!r} or {worktree_real!r}",
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
                )

            options = captured.get("options")
            settings = json.loads(options.settings)
            allowlist = settings["sandbox"]["write"]["allowOnly"]
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
                )

            options = captured.get("options")
            settings = json.loads(options.settings)
            allowlist = settings["sandbox"]["write"]["allowOnly"]
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
# Tests: project settings propagation via repo_root (async)
# ---------------------------------------------------------------------------

class TestProjectSettingsPropagation(unittest.IsolatedAsyncioTestCase):
    """Tests that dispatch_task merges project settings from repo_root/.claude/."""

    def _make_result_message(self, session_id: str) -> "ResultMessage":
        return ResultMessage(
            subtype="success",
            duration_ms=100,
            duration_api_ms=80,
            is_error=False,
            num_turns=1,
            session_id=session_id,
            total_cost_usd=0.0,
        )

    async def _call_dispatch(self, worktree: Path, repo_root=None, **kwargs):
        """Helper: call dispatch_task with a mock_query and return captured settings dict."""
        captured: dict = {}

        async def mock_query(**kw):
            captured["options"] = kw.get("options")
            async for m in _async_gen(self._make_result_message("sess-proj-settings")):
                yield m

        with patch.object(_dispatch_module, "query", mock_query):
            await _dispatch_module.dispatch_task(
                feature="proj-settings-test",
                task="do something",
                worktree_path=worktree,
                complexity="simple",
                system_prompt="",
                repo_root=repo_root,
                **kwargs,
            )

        options = captured.get("options")
        self.assertIsNotNone(options, "ClaudeAgentOptions was not captured")
        self.assertIsNotNone(options.settings, "settings= was not set on ClaudeAgentOptions")
        return json.loads(options.settings)

    async def test_settings_loaded_from_settings_json(self):
        """Project settings.json is read and merged into the dispatched settings."""
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            worktree = repo_root / "worktree"
            worktree.mkdir(parents=True)
            claude_dir = repo_root / ".claude"
            claude_dir.mkdir()
            (claude_dir / "settings.json").write_text(
                json.dumps({"attribution": {"commit": ""}}), encoding="utf-8"
            )

            settings = await self._call_dispatch(worktree, repo_root=repo_root)
            self.assertEqual(settings["attribution"]["commit"], "")

    async def test_settings_local_json_overrides_settings_json(self):
        """settings.local.json values win over settings.json values."""
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            worktree = repo_root / "worktree"
            worktree.mkdir(parents=True)
            claude_dir = repo_root / ".claude"
            claude_dir.mkdir()
            (claude_dir / "settings.json").write_text(
                json.dumps({"foo": "base"}), encoding="utf-8"
            )
            (claude_dir / "settings.local.json").write_text(
                json.dumps({"foo": "override"}), encoding="utf-8"
            )

            settings = await self._call_dispatch(worktree, repo_root=repo_root)
            self.assertEqual(settings["foo"], "override")

    async def test_sandbox_allowlist_wins_over_project_sandbox_key(self):
        """dispatch_task's computed allowlist overrides any sandbox key in settings.json."""
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            worktree = repo_root / "worktree"
            worktree.mkdir(parents=True)
            claude_dir = repo_root / ".claude"
            claude_dir.mkdir()
            (claude_dir / "settings.json").write_text(
                json.dumps({"sandbox": {"write": {"allowOnly": ["/malicious"]}}}),
                encoding="utf-8",
            )

            settings = await self._call_dispatch(worktree, repo_root=repo_root)
            allowlist = settings["sandbox"]["write"]["allowOnly"]
            self.assertIn(
                str(worktree),
                allowlist,
                f"worktree path not in allowlist after override: {allowlist}",
            )
            self.assertNotEqual(
                allowlist,
                ["/malicious"],
                "project sandbox key was not overridden by dispatch allowlist",
            )

    async def test_malformed_settings_json_logs_warning_and_falls_back(self):
        """Invalid JSON in settings.json prints a warning and settings still has sandbox key."""
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            worktree = repo_root / "worktree"
            worktree.mkdir(parents=True)
            claude_dir = repo_root / ".claude"
            claude_dir.mkdir()
            (claude_dir / "settings.json").write_text("not valid json", encoding="utf-8")

            import io
            import sys as _sys

            stderr_capture = io.StringIO()
            old_stderr = _sys.stderr
            _sys.stderr = stderr_capture
            try:
                settings = await self._call_dispatch(worktree, repo_root=repo_root)
            finally:
                _sys.stderr = old_stderr

            warning_output = stderr_capture.getvalue()
            self.assertIn(
                "settings.json",
                warning_output,
                f"Expected warning about settings.json in stderr, got: {warning_output!r}",
            )
            # Fallback: sandbox write key is still present (from dispatch's own allowlist)
            self.assertIn("sandbox", settings)
            self.assertIn("write", settings["sandbox"])

    async def test_repo_root_none_produces_unchanged_behavior(self):
        """Without repo_root, settings contains only the sandbox write allowlist."""
        with tempfile.TemporaryDirectory() as tmp:
            worktree = Path(tmp) / "worktree"
            worktree.mkdir()

            settings = await self._call_dispatch(worktree, repo_root=None)
            # Only key should be sandbox
            self.assertEqual(
                set(settings.keys()),
                {"sandbox"},
                f"Expected only 'sandbox' key when repo_root=None, got: {set(settings.keys())}",
            )
            # The sandbox write allowOnly must contain the worktree path
            allowlist = settings["sandbox"]["write"]["allowOnly"]
            self.assertIn(str(worktree), allowlist)


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
                )

            import json as _json
            events = [_json.loads(line) for line in log_file.read_text().splitlines() if line.strip()]
            error_events = [e for e in events if e.get("event") == "dispatch_error"]
            self.assertEqual(len(error_events), 1)
            self.assertEqual(error_events[0]["error_type"], "budget_exhausted")


if __name__ == "__main__":
    unittest.main()
