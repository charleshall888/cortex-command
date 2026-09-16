"""Unit tests for dispatch.py classify_failure() and ERROR_RECOVERY.

Tests cover every classification subtype introduced by the failure
classification feature, driven through ``classify_failure``'s structured
inputs (exit code, last result frame, last rate-limit frame, keyword corpus)
or through ``dispatch_task`` with the frame-level ``claude`` double:

  - spawn failure (ClaudeSpawnError)              -> infrastructure_failure
  - non-spawn exception during the run            -> unknown
  - non-zero exit + timeout keyword in stderr     -> agent_timeout
  - non-zero exit + timeout keyword in output     -> agent_timeout
  - non-zero exit + test-failure keyword          -> agent_test_failure
  - non-zero exit + refusal keyword               -> agent_refusal
  - non-zero exit + confusion keyword             -> agent_confused
  - non-zero exit with no matching keyword        -> task_failure
  - ERROR_RECOVERY maps each subtype to the correct recovery path
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

import cortex_command.pipeline.dispatch as _dispatch_module
from cortex_command.claude_stream import ClaudeSpawnError
from cortex_command.pipeline.parser import parse_feature_plan
from cortex_command.tests._claude_double import fake_run_claude, result_frame


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE_CLI = "/fake/bin/claude"


def _classify(corpus: str, output: str = "", *, exit_code: int = 1) -> str | None:
    """Classify a non-zero exit with no result frame over ``corpus`` + ``output``.

    ``corpus`` stands in for captured child stderr and ``output`` for the
    assistant text; dispatch_task joins both into the keyword corpus.
    """
    text = corpus if not output else f"{output}\n{corpus}"
    return _dispatch_module.classify_failure(exit_code, None, None, text, 30)


@contextlib.contextmanager
def _patched_claude(frames=(), **double_kwargs):
    """Patch dispatch.py's bound ``run_claude`` with the frame double and pin
    ``resolve_claude_cli`` to a fake path, yielding a capture dict.

    The capture dict receives the double's ``argv``/``prompt``/``cwd``/``env``
    plus the ``on_stderr`` callback dispatch_task handed to the seam.
    """
    capture: dict = {}
    inner = fake_run_claude(frames, capture=capture, **double_kwargs)

    def _recording_run_claude(argv, **kwargs):
        capture["on_stderr"] = kwargs.get("on_stderr")
        return inner(argv, **kwargs)

    with patch.object(_dispatch_module, "run_claude", _recording_run_claude), \
            patch.object(_dispatch_module, "resolve_claude_cli", return_value=_FAKE_CLI):
        yield capture


def _settings_from_capture(capture: dict) -> dict:
    """Load the sandbox settings JSON named by ``--settings <path>`` in argv."""
    argv = capture.get("argv")
    assert argv is not None, "run_claude was not called"
    assert "--settings" in argv, f"--settings missing from argv: {argv!r}"
    path = argv[argv.index("--settings") + 1]
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _stored_stderr_lines(capture: dict) -> list[str] | None:
    """Return the ``_stderr_lines`` closure cell of the captured on_stderr."""
    on_stderr = capture["on_stderr"]
    for name, cell in zip(on_stderr.__code__.co_freevars, on_stderr.__closure__ or ()):
        if name == "_stderr_lines":
            return cell.cell_contents
    return None


async def _dispatch_simple(worktree: Path, **kwargs) -> "_dispatch_module.DispatchResult":
    return await _dispatch_module.dispatch_task(
        feature=kwargs.pop("feature", "classify-test"),
        task="do something",
        worktree_path=worktree,
        complexity="simple",
        system_prompt="",
        skill="implement",
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Tests: classify_failure()
# ---------------------------------------------------------------------------

class TestClassifyError(unittest.TestCase):
    """Tests for classify_failure() covering all subtypes."""

    # --- Run-level failure branches (spawn errors and unexpected exceptions) ---

    def test_timeout_keyword_returns_agent_timeout(self):
        """Spec R10: the SDK's ``asyncio.TimeoutError`` arm is gone with the
        SDK; ``agent_timeout`` stays reachable through the timeout keywords."""
        self.assertEqual(_classify("operation timed out"), "agent_timeout")

    def test_timeout_keyword_wins_over_refusal_in_output(self):
        """Spec R10: with no typed timeout exception left, a timeout signal
        still outranks refusal text in the assistant output."""
        self.assertEqual(
            _classify("timed out", output="i cannot help you"),
            "agent_timeout",
        )

    def test_spawn_error_returns_infrastructure_failure(self):
        """Spec R11: an unspawnable ``claude`` (formerly CLIConnectionError)
        classifies as infrastructure_failure."""
        spawn_error = ClaudeSpawnError(_FAKE_CLI, FileNotFoundError("Claude CLI not found"))

        async def _run():
            with tempfile.TemporaryDirectory() as tmp:
                with _patched_claude(spawn_error=spawn_error):
                    return await _dispatch_simple(Path(tmp))

        self.assertEqual(asyncio.run(_run()).error_type, "infrastructure_failure")

    def _dispatch_with_run_exception(self, exc: Exception) -> str | None:
        async def _run():
            with tempfile.TemporaryDirectory() as tmp:
                with _patched_claude(spawn_error=exc):
                    return await _dispatch_simple(Path(tmp))

        return asyncio.run(_run()).error_type

    def test_generic_exception_returns_unknown(self):
        self.assertEqual(
            self._dispatch_with_run_exception(ValueError("something unexpected")),
            "unknown",
        )

    def test_generic_exception_with_timeout_in_message_returns_unknown(self):
        """Generic exceptions are not inspected for keywords; must stay 'unknown'."""
        self.assertEqual(
            self._dispatch_with_run_exception(RuntimeError("timeout occurred")),
            "unknown",
        )

    # --- Non-zero exit: timeout keyword in captured stderr ---

    def test_process_error_timeout_keyword_returns_agent_timeout(self):
        self.assertEqual(_classify("operation timed out after 30 s"), "agent_timeout")

    def test_process_error_timeout_literal_keyword(self):
        self.assertEqual(_classify("timeout reached"), "agent_timeout")

    def test_process_error_time_out_two_words(self):
        self.assertEqual(_classify("session will time out shortly"), "agent_timeout")

    # --- Non-zero exit: timeout keyword detected via output ---

    def test_process_error_timeout_in_output_returns_agent_timeout(self):
        self.assertEqual(
            _classify("task failed", output="process timed out"),
            "agent_timeout",
        )

    # --- Non-zero exit: test-failure keywords ---

    def test_process_error_test_failed_returns_agent_test_failure(self):
        self.assertEqual(_classify("test failed: test_foo"), "agent_test_failure")

    def test_process_error_pytest_keyword_returns_agent_test_failure(self):
        self.assertEqual(_classify("pytest exited with status 1"), "agent_test_failure")

    def test_process_error_assertion_error_keyword_returns_agent_test_failure(self):
        self.assertEqual(_classify("AssertionError: expected True"), "agent_test_failure")

    def test_process_error_test_failure_in_output(self):
        self.assertEqual(
            _classify("agent exited non-zero", output="failing tests detected"),
            "agent_test_failure",
        )

    # --- Non-zero exit: refusal keywords ---

    def test_process_error_i_cannot_returns_agent_refusal(self):
        self.assertEqual(_classify("I cannot complete this task"), "agent_refusal")

    def test_process_error_i_will_not_returns_agent_refusal(self):
        self.assertEqual(_classify("I will not do that"), "agent_refusal")

    def test_process_error_cannot_help_in_output(self):
        self.assertEqual(
            _classify("agent stopped", output="I cannot help with this request"),
            "agent_refusal",
        )

    def test_process_error_i_must_refuse_returns_agent_refusal(self):
        self.assertEqual(_classify("I must refuse this operation"), "agent_refusal")

    # --- Non-zero exit: confusion keywords ---

    def test_process_error_im_not_sure_returns_agent_confused(self):
        self.assertEqual(_classify("I'm not sure what to do here"), "agent_confused")

    def test_process_error_i_dont_understand_returns_agent_confused(self):
        self.assertEqual(_classify("I don't understand the requirements"), "agent_confused")

    def test_process_error_unclear_to_me_returns_agent_confused(self):
        self.assertEqual(_classify("This is unclear to me"), "agent_confused")

    def test_process_error_im_lost_in_output_returns_agent_confused(self):
        self.assertEqual(
            _classify(
                "agent exited unexpectedly",
                output="I am lost and don't know how to proceed",
            ),
            "agent_confused",
        )

    # --- Non-zero exit: no keyword match ---

    def test_process_error_no_matching_keyword_returns_task_failure(self):
        self.assertEqual(_classify("exit code 1"), "task_failure")

    def test_process_error_empty_message_returns_task_failure(self):
        self.assertEqual(_classify(""), "task_failure")

    def test_process_error_empty_message_empty_output_returns_task_failure(self):
        self.assertEqual(_classify("", output=""), "task_failure")

    # --- Priority ordering: timeout > test_failure ---

    def test_timeout_takes_priority_over_test_failure_in_corpus(self):
        """When both timeout and test-failure patterns present, timeout wins."""
        self.assertEqual(_classify("timed out while running pytest"), "agent_timeout")

    # --- Case insensitivity ---

    def test_refusal_pattern_case_insensitive(self):
        self.assertEqual(_classify("I CANNOT do that"), "agent_refusal")

    def test_test_failure_pattern_case_insensitive(self):
        self.assertEqual(_classify("TESTS FAILED"), "agent_test_failure")


# ---------------------------------------------------------------------------
# Tests: ERROR_RECOVERY
# ---------------------------------------------------------------------------

class TestErrorRecovery(unittest.TestCase):
    """Tests that ERROR_RECOVERY maps every error type to the correct path."""

    def test_agent_timeout_recovery_is_retry(self):
        self.assertEqual(_dispatch_module.ERROR_RECOVERY["agent_timeout"], "retry")

    def test_agent_test_failure_recovery_is_retry(self):
        # Formerly "escalate" (climb the model ladder). cortex no longer picks
        # models, so there is no tier to climb and it plain-retries.
        self.assertEqual(_dispatch_module.ERROR_RECOVERY["agent_test_failure"], "retry")

    def test_agent_refusal_recovery_is_pause_human(self):
        self.assertEqual(_dispatch_module.ERROR_RECOVERY["agent_refusal"], "pause_human")

    def test_agent_confused_recovery_is_retry(self):
        self.assertEqual(_dispatch_module.ERROR_RECOVERY["agent_confused"], "retry")

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


class TestDispatchTaskSandboxSettings(unittest.IsolatedAsyncioTestCase):
    """Tests that dispatch_task passes the correct sandbox settings to ``claude --settings``."""

    async def test_worktree_path_in_write_allowlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            worktree = Path(tmp) / "feature-worktree"
            worktree.mkdir()

            with _patched_claude([result_frame(total_cost_usd=0.0)]) as capture:
                await _dispatch_module.dispatch_task(
                    feature="sandbox-test",
                    task="do something",
                    worktree_path=worktree,
                    complexity="simple",
                    system_prompt="",
                    skill="implement",
                )

            self.assertIsNotNone(capture.get("argv"), "argv was not captured from run_claude call")
            self.assertIn("--settings", capture["argv"], "--settings was not passed to claude")

            # Per spec Req 5 (REVISED 2026-05-05), --settings names a filepath
            # to a per-dispatch tempfile containing the sandbox JSON.
            settings = _settings_from_capture(capture)
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

            with _patched_claude([result_frame(total_cost_usd=0.0)]) as capture:
                await _dispatch_module.dispatch_task(
                    feature="tmpdir-absent-test",
                    task="do something",
                    worktree_path=worktree,
                    complexity="simple",
                    system_prompt="",
                    skill="implement",
                )

            settings = _settings_from_capture(capture)
            allowlist = settings["sandbox"]["filesystem"]["allowWrite"]
            self.assertNotIn("/tmp/claude", allowlist)
            self.assertNotIn("/private/tmp/claude", allowlist)

    async def test_only_worktree_paths_in_allowlist_without_integration_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            worktree = Path(tmp) / "feature-worktree"
            worktree.mkdir()

            with _patched_claude([result_frame(total_cost_usd=0.0)]) as capture:
                await _dispatch_module.dispatch_task(
                    feature="only-worktree-test",
                    task="do something",
                    worktree_path=worktree,
                    complexity="simple",
                    system_prompt="",
                    skill="implement",
                )

            settings = _settings_from_capture(capture)
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

            with _patched_claude([result_frame(total_cost_usd=0.0)]) as capture:
                await _dispatch_module.dispatch_task(
                    feature="integration-base-test",
                    task="do something",
                    worktree_path=worktree,
                    complexity="simple",
                    system_prompt="",
                    integration_base_path=integration_base,
                    skill="implement",
                )

            settings = _settings_from_capture(capture)
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

            with _patched_claude([result_frame(total_cost_usd=0.0)]) as capture:
                await _dispatch_module.dispatch_task(
                    feature="tmpdir-integration-test",
                    task="do something",
                    worktree_path=worktree,
                    complexity="simple",
                    system_prompt="",
                    integration_base_path=integration_base,
                    skill="implement",
                )

            settings = _settings_from_capture(capture)
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
# Tests: dispatch_task budget exhaustion (result frame subtype=error_max_budget_usd)
# ---------------------------------------------------------------------------

class TestDispatchTaskBudgetExhausted(unittest.IsolatedAsyncioTestCase):
    """Tests that dispatch_task detects a budget-exhausted result frame."""

    async def test_budget_exhausted_returns_failure(self):
        """dispatch_task returns DispatchResult(success=False, error_type=budget_exhausted)
        when the result frame reports ``subtype="error_max_budget_usd"``.

        Spec R1: the SDK's ``ResultMessage`` type is gone with the SDK, so the
        detail reports the result frame's ``is_error`` and ``subtype`` fields.
        """
        with tempfile.TemporaryDirectory() as tmp:
            worktree = Path(tmp) / "feature-worktree"
            worktree.mkdir()

            frames = [result_frame(is_error=True, subtype="error_max_budget_usd", total_cost_usd=0.5)]
            with _patched_claude(frames, exit_code=1):
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
            self.assertIn("is_error=True", result.error_detail)
            self.assertIn("error_max_budget_usd", result.error_detail)
            self.assertIn("[budget_exhausted: subtype=error_max_budget_usd]", result.output)
            self.assertEqual(result.cost_usd, 0.5)

    async def test_no_budget_exhausted_on_success_result(self):
        """dispatch_task returns DispatchResult(success=True) when the result frame's
        is_error is False — no regression for the normal path."""
        with tempfile.TemporaryDirectory() as tmp:
            worktree = Path(tmp) / "feature-worktree"
            worktree.mkdir()

            with _patched_claude([result_frame(total_cost_usd=0.1)]):
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

            frames = [result_frame(is_error=True, subtype="error_max_budget_usd", total_cost_usd=0.5)]
            with _patched_claude(frames, exit_code=1):
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
# Tests: dispatch_task DispatchDiagnostics bundle (#309 R4)
# ---------------------------------------------------------------------------


class TestDispatchTaskDiagnostics(unittest.IsolatedAsyncioTestCase):
    """DispatchResult.diagnostics carries captured stderr/exit_code/cwd on the
    failure paths, and is None on the success path."""

    async def test_diagnostics_populated_on_process_error(self):
        """A non-zero-exit dispatch carries the captured stderr, exit_code, and
        cwd in DispatchResult.diagnostics."""
        with tempfile.TemporaryDirectory() as tmp:
            worktree = Path(tmp) / "feature-worktree"
            worktree.mkdir()

            # Drive a known stderr line through the real _on_stderr capture,
            # then exit non-zero with no result frame.
            with _patched_claude([], exit_code=42, stderr_lines=["child process failed: boom"]):
                result = await _dispatch_module.dispatch_task(
                    feature="diagnostics-test",
                    task="do something",
                    worktree_path=worktree,
                    complexity="simple",
                    system_prompt="",
                    skill="implement",
                )

            self.assertFalse(result.success)
            self.assertIsNotNone(result.diagnostics)
            self.assertEqual(result.diagnostics.child_stderr, "child process failed: boom")
            self.assertEqual(result.diagnostics.exit_code, 42)
            self.assertEqual(result.diagnostics.cwd, str(worktree))

    async def test_diagnostics_none_on_success(self):
        """A successful dispatch leaves DispatchResult.diagnostics as None."""
        with tempfile.TemporaryDirectory() as tmp:
            worktree = Path(tmp) / "feature-worktree"
            worktree.mkdir()

            with _patched_claude([result_frame(total_cost_usd=0.1)]):
                result = await _dispatch_module.dispatch_task(
                    feature="diagnostics-ok-test",
                    task="do something",
                    worktree_path=worktree,
                    complexity="simple",
                    system_prompt="",
                    skill="implement",
                )

            self.assertTrue(result.success)
            self.assertIsNone(result.diagnostics)


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

            # Emit a synthetic stderr line containing a sk-ant-* token.
            with _patched_claude(
                [result_frame(total_cost_usd=0.0)],
                stderr_lines=["error: leaked key sk-ant-abc123def trailing text"],
            ) as capture:
                await _dispatch_module.dispatch_task(
                    feature="stderr-redact-test",
                    task="do something",
                    worktree_path=worktree,
                    complexity="simple",
                    system_prompt="",
                    skill="implement",
                )

            # _stderr_lines is a closure cell on the _on_stderr callback.
            stderr_lines = _stored_stderr_lines(capture)

            self.assertIsNotNone(stderr_lines, "_stderr_lines closure cell not found")
            self.assertEqual(len(stderr_lines), 1)
            line = stderr_lines[-1]
            self.assertIn("sk-ant-<redacted>", line)
            self.assertNotIn("sk-ant-abc123def", line)


# ---------------------------------------------------------------------------
# Tests: cue-anchored value-level redaction + over-redaction guard (#309 R1)
# ---------------------------------------------------------------------------


def _capture_stderr_via_dispatch(emitted_line: str) -> str:
    """Drive `emitted_line` through dispatch_task's real `_on_stderr` capture
    path and return the single stored (post-redaction) stderr line."""

    async def _run() -> str:
        with tempfile.TemporaryDirectory() as tmp:
            worktree = Path(tmp) / "feature-worktree"
            worktree.mkdir()
            with _patched_claude(
                [result_frame(total_cost_usd=0.0)], stderr_lines=[emitted_line],
            ) as capture:
                await _dispatch_module.dispatch_task(
                    feature="redact-test",
                    task="do something",
                    worktree_path=worktree,
                    complexity="simple",
                    system_prompt="",
                    skill="implement",
                )
        lines = _stored_stderr_lines(capture)
        if lines is None:
            raise AssertionError("_stderr_lines closure cell not found")
        return lines[-1] if lines else ""

    return asyncio.run(_run())


class TestRedactCueAnchored(unittest.TestCase):
    """Cue-anchored credential shapes are scrubbed value-level (#309 R1a)."""

    def test_prefix_cued_shapes_redacted(self):
        cases = [
            # (emitted line, marker present after redact, secret absent after redact)
            (
                "fatal: auth failed token ghp_AbCdEf0123456789xyz tail",
                "<redacted-github-token>",
                "ghp_AbCdEf0123456789xyz",
            ),
            (
                "oauth gho_0123456789abcdefABCDEF done",
                "<redacted-github-token>",
                "gho_0123456789abcdefABCDEF",
            ),
            (
                "slack xoxb-FAKE-FIXTURE-NOT-A-REAL-TOKEN posted",
                "<redacted-slack-token>",
                "xoxb-FAKE-FIXTURE-NOT-A-REAL-TOKEN",
            ),
            (
                "creds AKIAIOSFODNN7EXAMPLE region us-east-1",
                "<redacted-aws-key>",
                "AKIAIOSFODNN7EXAMPLE",
            ),
            (
                "clone https://alice:s3cr3tP4ssw0rdXYZ@github.com/o/r.git failed",
                "<redacted>",
                "s3cr3tP4ssw0rdXYZ",
            ),
        ]
        for line, marker, secret in cases:
            with self.subTest(line=line):
                out = _capture_stderr_via_dispatch(line)
                self.assertIn(marker, out)
                self.assertNotIn(secret, out)

    def test_keyword_delimiter_secret_shaped_values_redacted(self):
        # token="<≥16-char secret>"
        out = _capture_stderr_via_dispatch(
            'auth header token="abcDEF0123456789ghIJ" rejected'
        )
        self.assertNotIn("abcDEF0123456789ghIJ", out)
        self.assertIn("token=", out)
        self.assertIn("rejected", out)

        # password=<long unquoted secret>
        out = _capture_stderr_via_dispatch(
            "connect failed password=Sup3rSecretValue123456 host=db"
        )
        self.assertNotIn("Sup3rSecretValue123456", out)
        self.assertIn("password=", out)
        self.assertIn("host=db", out)

        # Bearer <secret>
        out = _capture_stderr_via_dispatch(
            "401 Bearer eyJ0eXAabcdef0123456789ABCDEF denied"
        )
        self.assertNotIn("eyJ0eXAabcdef0123456789ABCDEF", out)
        self.assertIn("denied", out)

    def test_pem_private_key_cue_masks_line_level(self):
        out = _capture_stderr_via_dispatch(
            "key: -----BEGIN RSA PRIVATE KEY-----MIIEpAIBAAKCAQ"
        )
        self.assertIn("<redacted-private-key-block>", out)
        self.assertNotIn("MIIEpAIBAAKCAQ", out)


class TestRedactOverRedactionGuard(unittest.TestCase):
    """Benign high-entropy / cued-keyword diagnostics survive redaction (#309 R1b)."""

    def test_prefixless_blobs_survive(self):
        cases = [
            # 40-char hex git SHA
            "merge base da39a3ee5e6b4b0d3255bfef95601890afd80709 resolved",
            # UUID
            "trace id 550e8400-e29b-41d4-a716-446655440000 emitted",
            # base64 fixture (prefixless blob)
            "fixture YWJjZGVmZ2hpamtsbW5vcHFyc3R1dnd4eXowMTIzNDU= loaded",
        ]
        for line in cases:
            with self.subTest(line=line):
                out = _capture_stderr_via_dispatch(line)
                self.assertEqual(out, line, "benign high-entropy text was redacted")

    def test_cued_keyword_benign_context_survives(self):
        cases = [
            "unexpected token=RPAREN at position 12",
            "expected token='EOF' but found ';'",
            "Bearer of bad news: the build is broken",
            "config error password=changeme is too weak",
        ]
        for line in cases:
            with self.subTest(line=line):
                out = _capture_stderr_via_dispatch(line)
                self.assertEqual(out, line, "benign cued-keyword text was redacted")


class TestStderrByteCap(unittest.TestCase):
    """A single >cap-byte stderr line is bounded by total bytes (#309 R2)."""

    def test_single_oversize_line_capped_to_byte_bound(self):
        # One stderr line far larger than the byte cap. The line-count cap (100
        # lines) alone would let this pathological multi-megabyte line through.
        oversize = "x" * (_dispatch_module._MAX_STDERR_BYTES * 4)
        out = _capture_stderr_via_dispatch(oversize)
        self.assertLessEqual(
            len(out.encode("utf-8")),
            _dispatch_module._MAX_STDERR_BYTES,
            "stored stderr tail exceeded the byte cap",
        )
        # Tail-anchored: the kept slice is the end of the emitted line.
        self.assertTrue(oversize.endswith(out), "byte cap was not tail-anchored")


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
        ("simple",   "low"):      "low",
        ("simple",   "medium"):   "low",
        ("simple",   "high"):     "high",
        ("simple",   "critical"): "high",
        ("moderate", "low"):      "high",
        ("moderate", "medium"):   "high",
        ("moderate", "high"):     "high",
        ("moderate", "critical"): "high",
        ("complex",  "low"):      "high",
        ("complex",  "medium"):   "high",
        ("complex",  "high"):     "xhigh",
        ("complex",  "critical"): "xhigh",
    }
    assert len(_dispatch_module._EFFORT_MATRIX) == 12, (
        "matrix must have exactly 12 cells (3 complexity x 4 criticality)"
    )
    assert _dispatch_module._EFFORT_MATRIX == expected, (
        f"matrix policy mismatch: got {_dispatch_module._EFFORT_MATRIX!r}, "
        f"expected {expected!r}"
    )


def test_effort_skill_overrides():
    """``review-fix`` and ``integration-recovery`` always resolve ``max``.

    The override used to be gated on the resolved model being opus. cortex no
    longer selects a model, so the gate is gone and the override is
    unconditional — these two skills get the highest ceiling wherever they run.
    """
    for complexity, criticality in (
        ("complex", "high"),
        ("complex", "critical"),
        ("simple", "high"),
        ("complex", "low"),
        ("simple", "low"),
    ):
        assert _dispatch_module.resolve_effort(
            complexity=complexity, criticality=criticality, skill="review-fix",
        ) == "max"
        assert _dispatch_module.resolve_effort(
            complexity=complexity, criticality=criticality,
            skill="integration-recovery",
        ) == "max"

    # A non-overriding skill still takes the matrix value.
    assert _dispatch_module.resolve_effort(
        complexity="complex", criticality="high", skill="implement",
    ) == "xhigh"
    assert _dispatch_module.resolve_effort(
        complexity="simple", criticality="high", skill="implement",
    ) == "high"
    assert _dispatch_module.resolve_effort(
        complexity="simple", criticality="low", skill="implement",
    ) == "low"


def test_effort_rejects_unknown_tier_and_criticality():
    """``resolve_effort`` owns the enum guards that ``resolve_model`` used to.

    The old model-capability guard (fail loudly when e.g. ``xhigh`` was
    resolved for Sonnet) is deliberately gone: cortex does not choose the
    model, so the check cannot be evaluated here. An unacceptable ``--effort``
    is caught at the CLI boundary instead — see the ``effort_unsupported``
    classification and the one-shot clamp in retry.py.
    """
    with pytest.raises(ValueError, match="Unknown complexity tier"):
        _dispatch_module.resolve_effort(
            complexity="medium", criticality="high", skill="implement",
        )
    with pytest.raises(ValueError, match="Unknown criticality"):
        _dispatch_module.resolve_effort(
            complexity="simple", criticality="urgent", skill="implement",
        )


# ---------------------------------------------------------------------------
# Tests: dispatch enum guard remains an invariant backstop after parser
# normalization of out-of-vocabulary complexity (OOV-complexity hardening)
# ---------------------------------------------------------------------------

def test_resolve_effort_raises_on_directly_passed_unknown_tier():
    """The tier enum guard still fires for a directly-passed OOV complexity.

    Parser-boundary normalization (Task 1) coerces a present-but-OOV
    ``**Complexity**`` to ``complex`` before it reaches dispatch — but the
    ``ValueError`` is an independent invariant assertion that must keep firing
    for any unknown value reaching it directly. ``"medium"`` is the canonical
    OOV value: it is a valid *criticality* but not a member of the
    ``{trivial, simple, complex}`` complexity vocabulary. The guard used to live
    on ``resolve_model``; it moved to ``resolve_effort`` when model selection
    was removed.
    """
    with pytest.raises(ValueError, match="Unknown complexity tier"):
        _dispatch_module.resolve_effort("medium", "high", "implement")


def test_normalized_plan_never_triggers_tier_guard(tmp_path):
    """An end-to-end normalized plan never reaches the enum guard on the normal
    path: a present-but-OOV ``**Complexity**: medium`` is normalized to
    ``complex`` by ``parse_feature_plan`` (Task 1), so ``resolve_effort`` on the
    parsed tier returns without raising.

    This proves the guard is a backstop, not a live failure mode, once
    normalization is in place.
    """
    plan = tmp_path / "plan.md"
    plan.write_text(
        "# Plan: OOV complexity normalization\n"
        "\n"
        "## Overview\n"
        "\n"
        "Exercise parser-boundary normalization of an OOV complexity tier.\n"
        "\n"
        "## Tasks\n"
        "\n"
        "### Task 1: Do the thing\n"
        "- **Files**: foo.py\n"
        "- **Complexity**: medium\n",
        encoding="utf-8",
    )

    parsed = parse_feature_plan(plan)

    # Sanity: the parser recorded the OOV coercion and normalized to complex.
    assert parsed.normalized_complexities == [
        {"task": 1, "original": "medium", "resolved": "complex"}
    ]
    task = parsed.tasks[0]
    assert task.complexity == "complex"

    # The normalized tier reaches resolve_effort without tripping the guard.
    effort = _dispatch_module.resolve_effort(task.complexity, "high", "implement")
    assert effort in {"low", "medium", "high", "xhigh", "max"}


# ---------------------------------------------------------------------------
# Tests: #313 R4 — effort hard-rejection classification + recovery
# ---------------------------------------------------------------------------

_EFFORT_REJECT_STDERR = (
    "error: option '--effort <level>' argument 'xhigh' is invalid. "
    "It must be one of: low, medium, high, max"
)


def test_classify_effort_rejection_returns_effort_unsupported():
    """A captured `--effort ... is invalid` stderr classifies distinctly so the
    retry loop clamps rather than blind-retrying the permanently-invalid flag."""
    assert (
        _classify(_EFFORT_REJECT_STDERR, output="Command failed with exit code 1")
        == "effort_unsupported"
    )


def test_effort_unsupported_recovery_is_clamp_effort():
    assert _dispatch_module.ERROR_RECOVERY["effort_unsupported"] == "clamp_effort"


def test_non_effort_process_error_still_task_failure():
    """A non-zero exit without the effort-rejection text is unchanged."""
    assert (
        _classify("some other failure", output="Command failed with exit code 1")
        == "task_failure"
    )


# ---------------------------------------------------------------------------
# Tests: #313 R5 — warn-ignored effort detection on the success path
# ---------------------------------------------------------------------------

class TestEffortWarnIgnore(unittest.IsolatedAsyncioTestCase):
    """A modern CLI warn-ignores an unsupported --effort (exit 0); the dispatch
    still succeeds but records a visible degraded-effort note (#313 R5)."""

    async def test_warn_ignore_recorded_and_success_preserved(self):
        import json as _json

        warn = (
            "Warning: Unknown --effort value 'xhigh' — ignoring it and using "
            "the default effort. Valid values: low, medium, high, xhigh, max."
        )

        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "events.log"
            # Drive the stderr callback so _stderr_lines is populated, then
            # yield a successful result.
            with _patched_claude(
                [result_frame(duration_ms=1, total_cost_usd=0.01)],
                stderr_lines=[warn],
            ):
                result = await _dispatch_module.dispatch_task(
                    feature="feat",
                    task="t",
                    worktree_path=Path(tmp),
                    complexity="complex",
                    criticality="high",
                    system_prompt="",
                    log_path=log_path,
                    skill="implement",
                )
            self.assertTrue(result.success, "warn-ignore must not fail the dispatch")
            events = [
                _json.loads(line)
                for line in log_path.read_text().splitlines()
                if line.strip()
            ]
            ignored = [e for e in events if e.get("event") == "dispatch_effort_ignored"]
            self.assertEqual(len(ignored), 1, "expected one dispatch_effort_ignored note")
            self.assertEqual(ignored[0]["effort"], "xhigh")


if __name__ == "__main__":
    unittest.main()
