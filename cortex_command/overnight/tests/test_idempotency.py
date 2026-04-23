"""Unit tests for idempotency helpers in cortex_command.overnight.batch_runner (DR-2).

Covers:
  TestComputePlanHash    — _compute_plan_hash() file-read and fallback behaviour
  TestMakeIdempotencyToken — _make_idempotency_token() determinism and uniqueness
  TestCheckTaskCompleted — _check_task_completed() scanning logic and error paths
  TestWriteCompletionToken — _write_completion_token() append and silent-OSError
  TestRoundTrip          — write then read back; resume skips already-complete tasks
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from cortex_command.overnight.feature_executor import (
    _check_task_completed,
    _compute_plan_hash,
    _make_idempotency_token,
    _write_completion_token,
)


# ---------------------------------------------------------------------------
# TestComputePlanHash
# ---------------------------------------------------------------------------


class TestComputePlanHash(unittest.TestCase):
    """Tests for _compute_plan_hash()."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._tmp = Path(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_known_content_matches_sha256(self):
        """Hash matches the SHA-256 of the exact file content."""
        plan = self._tmp / "plan.md"
        content = "# My Plan\n\nTask 1\nTask 2\n"
        plan.write_text(content, encoding="utf-8")
        expected = hashlib.sha256(content.encode()).hexdigest()
        self.assertEqual(_compute_plan_hash(plan), expected)

    def test_missing_file_returns_empty_string_hash(self):
        """Missing file falls back to SHA-256('') — does not raise."""
        plan = self._tmp / "nonexistent.md"
        expected = hashlib.sha256(b"").hexdigest()
        self.assertEqual(_compute_plan_hash(plan), expected)

    def test_hash_is_stable_across_calls(self):
        """Two consecutive calls on the same file return identical hashes."""
        plan = self._tmp / "plan.md"
        plan.write_text("stable content", encoding="utf-8")
        h1 = _compute_plan_hash(plan)
        h2 = _compute_plan_hash(plan)
        self.assertEqual(h1, h2)

    def test_different_content_different_hash(self):
        """Changing file content changes the hash."""
        plan = self._tmp / "plan.md"
        plan.write_text("version A", encoding="utf-8")
        ha = _compute_plan_hash(plan)
        plan.write_text("version B", encoding="utf-8")
        hb = _compute_plan_hash(plan)
        self.assertNotEqual(ha, hb)


# ---------------------------------------------------------------------------
# TestMakeIdempotencyToken
# ---------------------------------------------------------------------------


class TestMakeIdempotencyToken(unittest.TestCase):
    """Tests for _make_idempotency_token()."""

    def test_token_is_32_hex_chars(self):
        token = _make_idempotency_token("feat-a", 1, "abc123")
        self.assertEqual(len(token), 32)
        self.assertRegex(token, r"^[0-9a-f]{32}$")

    def test_token_is_deterministic(self):
        """Same inputs always produce the same token."""
        t1 = _make_idempotency_token("feat-a", 3, "hash1")
        t2 = _make_idempotency_token("feat-a", 3, "hash1")
        self.assertEqual(t1, t2)

    def test_different_feature_different_token(self):
        t1 = _make_idempotency_token("feat-a", 1, "h")
        t2 = _make_idempotency_token("feat-b", 1, "h")
        self.assertNotEqual(t1, t2)

    def test_different_task_number_different_token(self):
        t1 = _make_idempotency_token("feat-a", 1, "h")
        t2 = _make_idempotency_token("feat-a", 2, "h")
        self.assertNotEqual(t1, t2)

    def test_different_plan_hash_different_token(self):
        """Changing the plan hash produces a different token (plan change invalidates)."""
        t1 = _make_idempotency_token("feat-a", 1, "hash-old")
        t2 = _make_idempotency_token("feat-a", 1, "hash-new")
        self.assertNotEqual(t1, t2)

    def test_empty_plan_hash_is_valid(self):
        """Empty-string plan hash (degraded fallback) still produces a token."""
        token = _make_idempotency_token("feat-a", 1, "")
        self.assertEqual(len(token), 32)

    def test_token_is_prefix_of_full_sha256(self):
        """Token equals the first 32 hex chars of SHA-256 of the canonical key."""
        feature, task_number, plan_hash = "my-feature", 7, "abc"
        key = f"{feature}:{task_number}:{plan_hash}"
        expected = hashlib.sha256(key.encode()).hexdigest()[:32]
        self.assertEqual(_make_idempotency_token(feature, task_number, plan_hash), expected)


# ---------------------------------------------------------------------------
# TestCheckTaskCompleted
# ---------------------------------------------------------------------------


class TestCheckTaskCompleted(unittest.TestCase):
    """Tests for _check_task_completed()."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._log = Path(self._tmpdir.name) / "pipeline-events.log"

    def tearDown(self):
        self._tmpdir.cleanup()

    def _append(self, obj: dict) -> None:
        with self._log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(obj) + "\n")

    def test_missing_file_returns_false(self):
        """No log file → never-dispatched task → should dispatch."""
        self.assertFalse(_check_task_completed(self._log, "abc123"))

    def test_token_present_returns_true(self):
        """Matching completion record found → skip dispatch."""
        self._append({
            "event": "task_idempotency_complete",
            "idempotency_token": "deadbeef" * 4,
        })
        self.assertTrue(_check_task_completed(self._log, "deadbeef" * 4))

    def test_wrong_token_returns_false(self):
        """Completion record exists but for a different token → dispatch."""
        self._append({
            "event": "task_idempotency_complete",
            "idempotency_token": "aaaaaaaabbbbbbbbccccccccdddddddd",
        })
        self.assertFalse(_check_task_completed(self._log, "ffffffffffffffffffffffffffffffff"))

    def test_wrong_event_type_returns_false(self):
        """Record has matching token but wrong event type → dispatch."""
        self._append({
            "event": "task_output",
            "idempotency_token": "tok1tok1tok1tok1tok1tok1tok1tok1",
        })
        self.assertFalse(_check_task_completed(self._log, "tok1tok1tok1tok1tok1tok1tok1tok1"))

    def test_malformed_json_line_skipped(self):
        """Malformed JSON lines are skipped; valid lines are still checked."""
        with self._log.open("w", encoding="utf-8") as fh:
            fh.write("not-json\n")
            fh.write(json.dumps({
                "event": "task_idempotency_complete",
                "idempotency_token": "goodtoken12345678901234567890ab",
            }) + "\n")
        self.assertTrue(_check_task_completed(self._log, "goodtoken12345678901234567890ab"))

    def test_blank_lines_skipped(self):
        """Blank lines in the log do not cause errors."""
        with self._log.open("w", encoding="utf-8") as fh:
            fh.write("\n\n")
            fh.write(json.dumps({
                "event": "task_idempotency_complete",
                "idempotency_token": "targettoken1234567890123456789a",
            }) + "\n")
        self.assertTrue(_check_task_completed(self._log, "targettoken1234567890123456789a"))

    def test_multiple_records_token_found_later(self):
        """Token found in a later line (multiple records) → still returns True."""
        token = "latetoken1234567890123456789012"
        self._append({"event": "task_idempotency_complete", "idempotency_token": "other1"})
        self._append({"event": "task_idempotency_complete", "idempotency_token": token})
        self.assertTrue(_check_task_completed(self._log, token))

    def test_empty_log_file_returns_false(self):
        """Empty file → no completions → dispatch."""
        self._log.write_text("", encoding="utf-8")
        self.assertFalse(_check_task_completed(self._log, "anytoken12345678901234567890ab"))

    def test_other_events_interspersed(self):
        """Non-idempotency events do not interfere with token lookup."""
        token = "realtoken1234567890123456789012"
        self._append({"event": "feature_start", "feature": "feat-a"})
        self._append({"event": "task_output", "task_number": 1})
        self._append({"event": "task_idempotency_complete", "idempotency_token": token})
        self._append({"event": "feature_complete", "feature": "feat-a"})
        self.assertTrue(_check_task_completed(self._log, token))


# ---------------------------------------------------------------------------
# TestWriteCompletionToken
# ---------------------------------------------------------------------------


class TestWriteCompletionToken(unittest.TestCase):
    """Tests for _write_completion_token()."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._log = Path(self._tmpdir.name) / "pipeline-events.log"

    def tearDown(self):
        self._tmpdir.cleanup()

    def _parse_lines(self) -> list[dict]:
        return [
            json.loads(line)
            for line in self._log.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def test_creates_file_if_absent(self):
        """Token is written even when the log file does not yet exist."""
        self.assertFalse(self._log.exists())
        _write_completion_token(self._log, "feat-a", 1, "tok1" * 8)
        self.assertTrue(self._log.exists())

    def test_written_record_has_required_fields(self):
        """Written record contains event, feature, task_number, idempotency_token."""
        token = "tok2" * 8
        _write_completion_token(self._log, "feat-b", 2, token)
        records = self._parse_lines()
        self.assertEqual(len(records), 1)
        r = records[0]
        self.assertEqual(r["event"], "task_idempotency_complete")
        self.assertEqual(r["feature"], "feat-b")
        self.assertEqual(r["task_number"], 2)
        self.assertEqual(r["idempotency_token"], token)

    def test_appends_to_existing_log(self):
        """Writes append rather than overwrite pre-existing content."""
        existing = json.dumps({"event": "session_start"}) + "\n"
        self._log.write_text(existing, encoding="utf-8")
        _write_completion_token(self._log, "feat-c", 3, "tok3" * 8)
        records = self._parse_lines()
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["event"], "session_start")
        self.assertEqual(records[1]["event"], "task_idempotency_complete")

    def test_multiple_writes_produce_multiple_records(self):
        """Each call appends one line."""
        _write_completion_token(self._log, "feat-a", 1, "token1" * 5 + "ab")
        _write_completion_token(self._log, "feat-a", 2, "token2" * 5 + "ab")
        records = self._parse_lines()
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["task_number"], 1)
        self.assertEqual(records[1]["task_number"], 2)

    def test_silent_on_unwritable_path(self):
        """OSError on write does not raise — best-effort semantics."""
        bad_path = Path("/no/such/directory/pipeline-events.log")
        # Must not raise
        _write_completion_token(bad_path, "feat-x", 9, "tok4" * 8)


# ---------------------------------------------------------------------------
# TestRoundTrip
# ---------------------------------------------------------------------------


class TestRoundTrip(unittest.TestCase):
    """Integration: write a token, then verify the check detects it.

    Simulates the resume-protection contract: after a token is written for
    a completed task, _check_task_completed must return True for that same
    (feature, task_number, plan_hash) triple.
    """

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._log = Path(self._tmpdir.name) / "pipeline-events.log"

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_completed_task_is_detected_on_resume(self):
        """Write token → check returns True (simulates clean resume)."""
        feature, task_num, plan_hash = "my-feature", 3, "planhash123"
        token = _make_idempotency_token(feature, task_num, plan_hash)

        # Simulate: task completed, write completion token
        _write_completion_token(self._log, feature, task_num, token)

        # Simulate: session resumes, checks whether task needs dispatch
        self.assertTrue(_check_task_completed(self._log, token))

    def test_different_task_not_affected_by_other_completion(self):
        """Token for task 1 does not suppress dispatch of task 2."""
        plan_hash = "shared-plan-hash"
        token1 = _make_idempotency_token("feat-a", 1, plan_hash)
        token2 = _make_idempotency_token("feat-a", 2, plan_hash)

        _write_completion_token(self._log, "feat-a", 1, token1)

        self.assertTrue(_check_task_completed(self._log, token1))
        self.assertFalse(_check_task_completed(self._log, token2))

    def test_changed_plan_hash_invalidates_token(self):
        """After plan content changes, old token is not found for new hash."""
        old_hash = "old-plan-hash"
        new_hash = "new-plan-hash"
        old_token = _make_idempotency_token("feat-a", 1, old_hash)
        new_token = _make_idempotency_token("feat-a", 1, new_hash)

        _write_completion_token(self._log, "feat-a", 1, old_token)

        # Old token is still found
        self.assertTrue(_check_task_completed(self._log, old_token))
        # New token (from changed plan) is NOT found → task will re-dispatch
        self.assertFalse(_check_task_completed(self._log, new_token))

    def test_multiple_features_independent(self):
        """Completions for different features do not cross-contaminate."""
        plan_hash = "shared"
        tok_a = _make_idempotency_token("feat-a", 1, plan_hash)
        tok_b = _make_idempotency_token("feat-b", 1, plan_hash)

        _write_completion_token(self._log, "feat-a", 1, tok_a)

        self.assertTrue(_check_task_completed(self._log, tok_a))
        self.assertFalse(_check_task_completed(self._log, tok_b))


if __name__ == "__main__":
    unittest.main()
