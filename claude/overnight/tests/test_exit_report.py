"""Unit tests for _read_exit_report() and the execute_feature() validation loop.

Task 2 — TestReadExitReport: all 9 branches of _read_exit_report().
Task 3 — TestValidationLoop: 5 scenarios of the exit-report branch inside
          execute_feature(), exercising FEATURE_DEFERRED, WORKER_NO_EXIT_REPORT,
          and WORKER_MALFORMED_EXIT_REPORT paths.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from claude.overnight.orchestrator import BatchConfig
from claude.overnight.feature_executor import execute_feature
from claude.overnight.feature_executor import _read_exit_report
from claude.overnight.events import (
    FEATURE_DEFERRED,
    WORKER_MALFORMED_EXIT_REPORT,
    WORKER_NO_EXIT_REPORT,
)
from claude.pipeline.parser import FeaturePlan, FeatureTask


# ---------------------------------------------------------------------------
# Task 2: _read_exit_report() branch coverage
# ---------------------------------------------------------------------------


class TestReadExitReport(unittest.TestCase):
    """Tests for _read_exit_report() — 9 branches (7 error + 2 success)."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._orig_cwd = os.getcwd()
        os.chdir(self._tmpdir.name)

    def tearDown(self):
        os.chdir(self._orig_cwd)
        self._tmpdir.cleanup()

    def _make_report(self, data, feature: str = "test-feat", task: int = 1) -> Path:
        """Write a report file and return its path."""
        p = Path(f"lifecycle/{feature}/exit-reports/{task}.json")
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, str):
            p.write_text(data, encoding="utf-8")
        else:
            p.write_text(json.dumps(data), encoding="utf-8")
        return p

    # --- error branches ---

    def test_missing_file(self):
        result = _read_exit_report("test-feat", 1)
        self.assertEqual(result, (None, None, None))

    def test_malformed_json(self):
        self._make_report("not { valid } json {{ }")
        result = _read_exit_report("test-feat", 1)
        self.assertEqual(result, (None, None, None))

    def test_oserror_on_read(self):
        # Create a real file so is_file() returns True, then fault read_text.
        self._make_report({})
        with patch("pathlib.Path.read_text", side_effect=OSError("disk error")):
            result = _read_exit_report("test-feat", 1)
        self.assertEqual(result, (None, None, None))

    def test_non_dict_json(self):
        self._make_report([1, 2, 3])
        result = _read_exit_report("test-feat", 1)
        self.assertEqual(result, (None, None, None))

    def test_missing_action_key(self):
        self._make_report({"reason": "done"})
        result = _read_exit_report("test-feat", 1)
        self.assertEqual(result, (None, None, None))

    def test_unrecognised_action(self):
        self._make_report({"action": "skip", "reason": "nope"})
        result = _read_exit_report("test-feat", 1)
        self.assertEqual(result, (None, None, None))

    # --- success branches ---

    def test_valid_complete(self):
        self._make_report({"action": "complete", "reason": "all done"})
        result = _read_exit_report("test-feat", 1)
        self.assertEqual(result, ("complete", "all done", None))

    def test_valid_question_with_question_field(self):
        self._make_report({
            "action": "question",
            "reason": "need input",
            "question": "Is X correct?",
        })
        result = _read_exit_report("test-feat", 1)
        self.assertEqual(result, ("question", "need input", "Is X correct?"))

    def test_valid_question_without_question_field(self):
        self._make_report({"action": "question", "reason": "unclear"})
        result = _read_exit_report("test-feat", 1)
        self.assertEqual(result, ("question", "unclear", None))


# ---------------------------------------------------------------------------
# Task 3: execute_feature() validation loop — 5 scenarios
# ---------------------------------------------------------------------------


class TestValidationLoop(unittest.IsolatedAsyncioTestCase):
    """Tests for the exit-report validation branch inside execute_feature()."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._orig_cwd = os.getcwd()
        # chdir so lifecycle/ relative paths resolve inside the temp dir.
        os.chdir(self._tmpdir.name)

        self._stub_plan = FeaturePlan(
            feature="test-feat",
            overview="test overview",
            tasks=[
                FeatureTask(
                    number=1,
                    description="test task",
                    depends_on=[],
                    files=[],
                    complexity="simple",
                )
            ],
        )

        tmp = self._tmpdir.name
        self._config = BatchConfig(
            batch_id=1,
            plan_path=Path(tmp) / "plan.md",
            overnight_events_path=Path(tmp) / "overnight.log",
            pipeline_events_path=Path(tmp) / "pipeline.log",
        )
        self._worktree_path = Path(tmp) / "worktree"
        self._worktree_path.mkdir()

    def tearDown(self):
        os.chdir(self._orig_cwd)
        self._tmpdir.cleanup()

    def _start_patch(self, *args, **kwargs):
        p = patch(*args, **kwargs)
        mock = p.start()
        self.addCleanup(p.stop)
        return mock

    def _apply_common_mocks(self):
        """Install all mocks shared across all 5 scenarios."""
        mock_parse = self._start_patch(
            "claude.overnight.feature_executor.parse_feature_plan",
            return_value=self._stub_plan,
        )
        retry_result = MagicMock(success=True, paused=False, attempts=1, final_output="", idempotency_skipped=False)
        mock_retry = self._start_patch(
            "claude.overnight.feature_executor.retry_task",
            new_callable=AsyncMock,
        )
        mock_retry.return_value = retry_result

        mock_pipeline_log = self._start_patch("claude.overnight.feature_executor.pipeline_log_event")
        self._start_patch(
            "claude.overnight.feature_executor.subprocess.run",
            side_effect=OSError("not a git repo"),
        )
        self._start_patch(
            "claude.overnight.feature_executor._render_template",
            return_value="stub prompt",
        )
        self._start_patch(
            "claude.overnight.feature_executor.read_criticality",
            return_value="normal",
        )
        mock_overnight_log = self._start_patch("claude.overnight.feature_executor.overnight_log_event")
        mock_mark_done = self._start_patch("claude.overnight.feature_executor.mark_task_done_in_plan")
        mock_write_esc = self._start_patch("claude.overnight.feature_executor.write_escalation")
        mock_next_n = self._start_patch(
            "claude.overnight.feature_executor._next_escalation_n", return_value=1
        )
        return {
            "parse": mock_parse,
            "retry": mock_retry,
            "pipeline_log": mock_pipeline_log,
            "overnight_log": mock_overnight_log,
            "mark_done": mock_mark_done,
            "write_esc": mock_write_esc,
            "next_n": mock_next_n,
        }

    def _logged_events(self, mocks):
        return [call.args[0] for call in mocks["overnight_log"].call_args_list]

    # --- scenario (a): no exit report, file absent ---

    async def test_no_exit_report_file_absent(self):
        """No exit report written by worker — logs WORKER_NO_EXIT_REPORT."""
        mocks = self._apply_common_mocks()
        self._start_patch(
            "claude.overnight.feature_executor._read_exit_report",
            return_value=(None, None, None),
        )
        # Do NOT patch Path.is_file — file genuinely absent in temp cwd.

        result = await execute_feature(
            "test-feat", self._worktree_path, self._config
        )

        self.assertEqual(result.status, "completed")
        mocks["mark_done"].assert_called_once()
        events = self._logged_events(mocks)
        self.assertIn(WORKER_NO_EXIT_REPORT, events)
        self.assertNotIn(WORKER_MALFORMED_EXIT_REPORT, events)

    # --- scenario (b): action="complete" ---

    async def test_action_complete(self):
        """Worker declared complete — no anomaly events, task marked done."""
        mocks = self._apply_common_mocks()
        self._start_patch(
            "claude.overnight.feature_executor._read_exit_report",
            return_value=("complete", "all done", None),
        )

        result = await execute_feature(
            "test-feat", self._worktree_path, self._config
        )

        self.assertEqual(result.status, "completed")
        mocks["mark_done"].assert_called_once()
        events = self._logged_events(mocks)
        self.assertNotIn(WORKER_NO_EXIT_REPORT, events)
        self.assertNotIn(WORKER_MALFORMED_EXIT_REPORT, events)

    # --- scenario (c): action="question" with question text ---

    async def test_action_question_with_question_text(self):
        """Worker declared a question — feature deferred, escalation written."""
        mocks = self._apply_common_mocks()
        self._start_patch(
            "claude.overnight.feature_executor._read_exit_report",
            return_value=("question", "need input", "Is X correct?"),
        )

        result = await execute_feature(
            "test-feat", self._worktree_path, self._config
        )

        self.assertEqual(result.status, "deferred")
        mocks["write_esc"].assert_called_once()
        mocks["next_n"].assert_called_once()
        mocks["mark_done"].assert_not_called()
        events = self._logged_events(mocks)
        self.assertIn(FEATURE_DEFERRED, events)

    # --- scenario (d): malformed report (file present, parse returns None) ---

    async def test_malformed_exit_report(self):
        """Exit report file exists but is unparseable — logs WORKER_MALFORMED."""
        mocks = self._apply_common_mocks()
        self._start_patch(
            "claude.overnight.feature_executor._read_exit_report",
            return_value=(None, None, None),
        )
        # File present but unparseable: patch is_file() to True so the
        # malformed path is taken instead of the missing-file path.
        self._start_patch("pathlib.Path.is_file", return_value=True)

        result = await execute_feature(
            "test-feat", self._worktree_path, self._config
        )

        self.assertEqual(result.status, "completed")
        mocks["mark_done"].assert_called_once()
        events = self._logged_events(mocks)
        self.assertIn(WORKER_MALFORMED_EXIT_REPORT, events)
        self.assertNotIn(WORKER_NO_EXIT_REPORT, events)

    # --- scenario (e): action="question" but question field absent ---

    async def test_action_question_missing_question_field(self):
        """Worker set action=question but omitted the question field — malformed."""
        mocks = self._apply_common_mocks()
        self._start_patch(
            "claude.overnight.feature_executor._read_exit_report",
            return_value=("question", "some reason", None),
        )
        # action="question" with no question falls into the malformed branch;
        # is_file() must return True so MALFORMED fires (not NO_EXIT_REPORT).
        self._start_patch("pathlib.Path.is_file", return_value=True)

        result = await execute_feature(
            "test-feat", self._worktree_path, self._config
        )

        self.assertEqual(result.status, "completed")
        mocks["mark_done"].assert_called_once()
        events = self._logged_events(mocks)
        self.assertIn(WORKER_MALFORMED_EXIT_REPORT, events)
        self.assertNotIn(WORKER_NO_EXIT_REPORT, events)


if __name__ == "__main__":
    unittest.main()
