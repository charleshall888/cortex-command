"""Unit tests for CI check paths in merge.py.

Tests cover:
  - _check_ci_status(): all return values (pass, pending, failing, skipped)
  - merge_feature() CI gate: ci_pending, ci_failing, ci_skipped (warn-and-proceed)
  - merge_feature() with ci_check=False skips the gate entirely
  - JSONL event logging for all CI check events (ci_check_start, ci_check_passed,
    ci_check_pending, ci_check_failed, ci_check_skipped)
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from cortex_command.pipeline.merge import (
    _check_ci_status,
    merge_feature,
    run_tests,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_proc(returncode: int = 0, stdout: str = "", stderr: str = "") -> CompletedProcess:
    """Build a CompletedProcess suitable for use as a subprocess.run mock return value."""
    result = CompletedProcess(args=[], returncode=returncode)
    result.stdout = stdout
    result.stderr = stderr
    return result


def _runs_json(status: str, conclusion: str) -> str:
    """Return a JSON string matching the shape of ``gh run list --json status,conclusion``."""
    return json.dumps([{"status": status, "conclusion": conclusion}])


def _patch_subprocess_run(returncode: int = 0, stdout: str = "", stderr: str = ""):
    """Patch subprocess.run in the merge module to return a fixed CompletedProcess."""
    return patch(
        "claude.pipeline.merge.subprocess.run",
        return_value=_make_proc(returncode, stdout, stderr),
    )


def _git_success_side_effect(cmd, **kwargs):
    """Side-effect for subprocess.run that handles git and returns success for all calls.

    - git rev-parse --show-toplevel → stdout="/fake/repo"
    - everything else → returncode=0, empty stdout
    """
    if isinstance(cmd, list) and "rev-parse" in cmd:
        return _make_proc(returncode=0, stdout="/fake/repo\n")
    return _make_proc(returncode=0)


def _patch_git_success():
    """Patch subprocess.run so all git commands appear to succeed."""
    return patch("claude.pipeline.merge.subprocess.run", side_effect=_git_success_side_effect)


def _patch_ci(ci_result: str):
    """Patch _check_ci_status to return a fixed result string."""
    return patch("claude.pipeline.merge._check_ci_status", return_value=ci_result)


# ---------------------------------------------------------------------------
# Tests: _check_ci_status()
# ---------------------------------------------------------------------------

class TestCheckCiStatusPass(unittest.TestCase):
    """_check_ci_status() returns "pass" for a successful CI run."""

    def test_success_conclusion_returns_pass(self):
        with _patch_subprocess_run(stdout=_runs_json("completed", "success")):
            self.assertEqual(_check_ci_status("pipeline/my-feature"), "pass")


class TestCheckCiStatusPending(unittest.TestCase):
    """_check_ci_status() returns "pending" for in-progress or queued runs."""

    def test_in_progress_status_returns_pending(self):
        with _patch_subprocess_run(stdout=_runs_json("in_progress", "")):
            self.assertEqual(_check_ci_status("pipeline/my-feature"), "pending")

    def test_queued_status_returns_pending(self):
        with _patch_subprocess_run(stdout=_runs_json("queued", "")):
            self.assertEqual(_check_ci_status("pipeline/my-feature"), "pending")


class TestCheckCiStatusFailing(unittest.TestCase):
    """_check_ci_status() returns "failing" for each non-success conclusion."""

    def test_failure_conclusion_returns_failing(self):
        with _patch_subprocess_run(stdout=_runs_json("completed", "failure")):
            self.assertEqual(_check_ci_status("pipeline/my-feature"), "failing")

    def test_cancelled_conclusion_returns_failing(self):
        with _patch_subprocess_run(stdout=_runs_json("completed", "cancelled")):
            self.assertEqual(_check_ci_status("pipeline/my-feature"), "failing")

    def test_timed_out_conclusion_returns_failing(self):
        with _patch_subprocess_run(stdout=_runs_json("completed", "timed_out")):
            self.assertEqual(_check_ci_status("pipeline/my-feature"), "failing")

    def test_action_required_conclusion_returns_failing(self):
        with _patch_subprocess_run(stdout=_runs_json("completed", "action_required")):
            self.assertEqual(_check_ci_status("pipeline/my-feature"), "failing")


class TestCheckCiStatusSkipped(unittest.TestCase):
    """_check_ci_status() returns "skipped" for all error / no-data conditions."""

    def test_gh_not_installed_returns_skipped(self):
        with patch(
            "claude.pipeline.merge.subprocess.run",
            side_effect=FileNotFoundError("gh: not found"),
        ):
            self.assertEqual(_check_ci_status("pipeline/my-feature"), "skipped")

    def test_gh_nonzero_exit_returns_skipped(self):
        with _patch_subprocess_run(returncode=1, stderr="authentication required"):
            self.assertEqual(_check_ci_status("pipeline/my-feature"), "skipped")

    def test_malformed_json_returns_skipped(self):
        with _patch_subprocess_run(stdout="not-valid-json{"):
            self.assertEqual(_check_ci_status("pipeline/my-feature"), "skipped")

    def test_empty_json_array_returns_skipped(self):
        with _patch_subprocess_run(stdout="[]"):
            self.assertEqual(_check_ci_status("pipeline/my-feature"), "skipped")

    def test_empty_stdout_returns_skipped(self):
        with _patch_subprocess_run(stdout=""):
            self.assertEqual(_check_ci_status("pipeline/my-feature"), "skipped")

    def test_non_list_json_returns_skipped(self):
        with _patch_subprocess_run(stdout='{"status": "completed"}'):
            self.assertEqual(_check_ci_status("pipeline/my-feature"), "skipped")

    def test_non_dict_run_entry_returns_skipped(self):
        with _patch_subprocess_run(stdout='["not-a-dict"]'):
            self.assertEqual(_check_ci_status("pipeline/my-feature"), "skipped")


class TestCheckCiStatusCliInvocation(unittest.TestCase):
    """_check_ci_status() calls gh with the correct arguments."""

    def test_correct_gh_command_and_flags(self):
        with patch("claude.pipeline.merge.subprocess.run") as mock_run:
            mock_run.return_value = _make_proc(stdout=_runs_json("completed", "success"))
            _check_ci_status("pipeline/some-branch")
            mock_run.assert_called_once_with(
                [
                    "gh", "run", "list",
                    "--branch", "pipeline/some-branch",
                    "--limit", "1",
                    "--json", "status,conclusion",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

    def test_branch_name_passed_verbatim(self):
        """Branch names with special characters are forwarded unchanged."""
        with patch("claude.pipeline.merge.subprocess.run") as mock_run:
            mock_run.return_value = _make_proc(stdout="[]")
            _check_ci_status("pipeline/feat/with-slash")
            call_args = mock_run.call_args[0][0]
            branch_index = call_args.index("--branch")
            self.assertEqual(call_args[branch_index + 1], "pipeline/feat/with-slash")


# ---------------------------------------------------------------------------
# Tests: merge_feature() CI gate (return values)
# ---------------------------------------------------------------------------

class TestMergeFeatureCiPending(unittest.TestCase):
    """merge_feature() returns a deferral result when CI is pending."""

    def test_returns_failure_with_ci_pending_error(self):
        with _patch_ci("pending"):
            result = merge_feature("my-feature")
        self.assertFalse(result.success)
        self.assertEqual(result.error, "ci_pending")

    def test_conflict_is_false(self):
        with _patch_ci("pending"):
            result = merge_feature("my-feature")
        self.assertFalse(result.conflict)

    def test_feature_name_preserved_in_result(self):
        with _patch_ci("pending"):
            result = merge_feature("special-feature")
        self.assertEqual(result.feature, "special-feature")

    def test_git_merge_not_called(self):
        """No git merge should be attempted when CI is pending."""
        with _patch_ci("pending"):
            with patch("claude.pipeline.merge.subprocess.run") as mock_run:
                mock_run.return_value = _make_proc(stdout="/fake/repo\n")
                merge_feature("my-feature")
            for call_args in mock_run.call_args_list:
                cmd = call_args[0][0]
                if isinstance(cmd, list):
                    self.assertNotIn("--no-ff", cmd)


class TestMergeFeatureCiFailing(unittest.TestCase):
    """merge_feature() returns a deferral result when CI is failing."""

    def test_returns_failure_with_ci_failing_error(self):
        with _patch_ci("failing"):
            result = merge_feature("my-feature")
        self.assertFalse(result.success)
        self.assertEqual(result.error, "ci_failing")

    def test_conflict_is_false(self):
        with _patch_ci("failing"):
            result = merge_feature("my-feature")
        self.assertFalse(result.conflict)

    def test_git_merge_not_called(self):
        """No git merge should be attempted when CI is failing."""
        with _patch_ci("failing"):
            with patch("claude.pipeline.merge.subprocess.run") as mock_run:
                mock_run.return_value = _make_proc(stdout="/fake/repo\n")
                merge_feature("my-feature")
            for call_args in mock_run.call_args_list:
                cmd = call_args[0][0]
                if isinstance(cmd, list):
                    self.assertNotIn("--no-ff", cmd)


class TestMergeFeatureCiSkipped(unittest.TestCase):
    """merge_feature() warns and proceeds when CI check is skipped."""

    def test_does_not_return_ci_pending(self):
        with _patch_ci("skipped"):
            with _patch_git_success():
                result = merge_feature("my-feature")
        self.assertNotEqual(result.error, "ci_pending")

    def test_does_not_return_ci_failing(self):
        with _patch_ci("skipped"):
            with _patch_git_success():
                result = merge_feature("my-feature")
        self.assertNotEqual(result.error, "ci_failing")


class TestMergeFeatureCiPass(unittest.TestCase):
    """merge_feature() proceeds normally when CI passes."""

    def test_does_not_return_ci_pending(self):
        with _patch_ci("pass"):
            with _patch_git_success():
                result = merge_feature("my-feature")
        self.assertNotEqual(result.error, "ci_pending")

    def test_does_not_return_ci_failing(self):
        with _patch_ci("pass"):
            with _patch_git_success():
                result = merge_feature("my-feature")
        self.assertNotEqual(result.error, "ci_failing")


class TestMergeFeatureCiCheckDisabled(unittest.TestCase):
    """merge_feature(ci_check=False) skips the CI gate entirely."""

    def test_check_ci_status_not_called_when_ci_check_false(self):
        with patch("claude.pipeline.merge._check_ci_status") as mock_ci:
            with _patch_git_success():
                merge_feature("my-feature", ci_check=False)
        mock_ci.assert_not_called()

    def test_ci_check_false_is_backward_compatible_default(self):
        """ci_check=True is the default; ci_check=False must be explicitly set."""
        with patch("claude.pipeline.merge._check_ci_status") as mock_ci:
            mock_ci.return_value = "pass"
            with _patch_git_success():
                merge_feature("my-feature")
        mock_ci.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: JSONL event logging for CI check paths
# ---------------------------------------------------------------------------

class TestMergeFeatureCiEventLogging(unittest.TestCase):
    """The correct JSONL events are appended for each CI check outcome."""

    def _events(self, log_path: Path) -> list[str]:
        lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        return [json.loads(line)["event"] for line in lines if line.strip()]

    def test_ci_pending_emits_ci_check_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "events.jsonl"
            with _patch_ci("pending"):
                merge_feature("feat", log_path=log_path)
            self.assertIn("ci_check_start", self._events(log_path))

    def test_ci_pending_emits_ci_check_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "events.jsonl"
            with _patch_ci("pending"):
                merge_feature("feat", log_path=log_path)
            self.assertIn("ci_check_pending", self._events(log_path))

    def test_ci_failing_emits_ci_check_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "events.jsonl"
            with _patch_ci("failing"):
                merge_feature("feat", log_path=log_path)
            self.assertIn("ci_check_start", self._events(log_path))

    def test_ci_failing_emits_ci_check_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "events.jsonl"
            with _patch_ci("failing"):
                merge_feature("feat", log_path=log_path)
            self.assertIn("ci_check_failed", self._events(log_path))

    def test_ci_skipped_emits_ci_check_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "events.jsonl"
            with _patch_ci("skipped"):
                with _patch_git_success():
                    merge_feature("feat", log_path=log_path)
            self.assertIn("ci_check_start", self._events(log_path))

    def test_ci_skipped_emits_ci_check_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "events.jsonl"
            with _patch_ci("skipped"):
                with _patch_git_success():
                    merge_feature("feat", log_path=log_path)
            self.assertIn("ci_check_skipped", self._events(log_path))

    def test_ci_pass_emits_ci_check_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "events.jsonl"
            with _patch_ci("pass"):
                with _patch_git_success():
                    merge_feature("feat", log_path=log_path)
            self.assertIn("ci_check_start", self._events(log_path))

    def test_ci_pass_emits_ci_check_passed(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "events.jsonl"
            with _patch_ci("pass"):
                with _patch_git_success():
                    merge_feature("feat", log_path=log_path)
            self.assertIn("ci_check_passed", self._events(log_path))

    def test_ci_check_false_emits_no_ci_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "events.jsonl"
            with _patch_git_success():
                merge_feature("feat", log_path=log_path, ci_check=False)
            ci_events = [e for e in self._events(log_path) if e.startswith("ci_")]
            self.assertEqual(ci_events, [])

    def test_log_path_none_does_not_raise_for_pending(self):
        """No exception when log_path is None (events silently skipped)."""
        with _patch_ci("pending"):
            result = merge_feature("feat", log_path=None)
        self.assertEqual(result.error, "ci_pending")

    def test_log_path_none_does_not_raise_for_failing(self):
        with _patch_ci("failing"):
            result = merge_feature("feat", log_path=None)
        self.assertEqual(result.error, "ci_failing")

    def test_event_includes_feature_name(self):
        """Each CI event entry should carry the feature name for traceability."""
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "events.jsonl"
            with _patch_ci("pending"):
                merge_feature("named-feature", log_path=log_path)
            lines = log_path.read_text(encoding="utf-8").strip().splitlines()
            for line in lines:
                entry = json.loads(line)
                if entry["event"].startswith("ci_"):
                    self.assertEqual(entry["feature"], "named-feature")


class TestRunTestsNoneNormalization(unittest.TestCase):
    """run_tests() treats the string 'none' as no test command configured."""

    def test_run_tests_string_none_returns_passing(self):
        """run_tests('none') must return TestResult(passed=True) without spawning a subprocess."""
        with patch("claude.pipeline.merge.subprocess.run") as mock_run:
            result = run_tests("none")
        mock_run.assert_not_called()
        self.assertTrue(result.passed)
        self.assertEqual(result.return_code, 0)

    def test_run_tests_string_none_uppercase(self):
        """run_tests('NONE') is also treated as no test command."""
        with patch("claude.pipeline.merge.subprocess.run") as mock_run:
            result = run_tests("NONE")
        mock_run.assert_not_called()
        self.assertTrue(result.passed)

    def test_run_tests_none_value_unchanged(self):
        """run_tests(None) still returns passing without subprocess."""
        with patch("claude.pipeline.merge.subprocess.run") as mock_run:
            result = run_tests(None)
        mock_run.assert_not_called()
        self.assertTrue(result.passed)


if __name__ == "__main__":
    unittest.main()
