"""Unit tests for the deferral module (next_question_id, write_deferral,
read_deferrals, write_escalation, _next_escalation_n).

Task 1 — TestNextQuestionId: 3 tests for ID generation.
Task 2 — TestWriteDeferral: file naming, auto-ID mutation, section headers,
          Default Choice conditional.
Task 3 — TestReadDeferrals: round-trip and malformed-file resilience.
Task 4 — TestWriteEscalation: field presence, append behavior,
          _next_escalation_n sequential IDs.
"""

from __future__ import annotations

import json
import tempfile
import unittest
import warnings
from pathlib import Path

from cortex_command.overnight.deferral import (
    DeferralQuestion,
    EscalationEntry,
    _next_escalation_n,
    next_question_id,
    read_deferrals,
    write_deferral,
    write_escalation,
)


# ---------------------------------------------------------------------------
# Task 1: next_question_id() — ID generation
# ---------------------------------------------------------------------------


class TestNextQuestionId(unittest.TestCase):
    """Tests for next_question_id() — empty dir, non-zero max, feature isolation."""

    def test_empty_directory_returns_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = next_question_id(Path(tmp), "feat")
        self.assertEqual(result, 1)

    def test_returns_max_plus_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "feat-q003.md").touch()
            result = next_question_id(d, "feat")
        self.assertEqual(result, 4)

    def test_other_feature_files_not_counted(self):
        """Files from a different feature name are ignored."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "feat-q003.md").touch()
            (d / "other-q010.md").touch()
            result = next_question_id(d, "feat")
        self.assertEqual(result, 4)


# ---------------------------------------------------------------------------
# Task 2: write_deferral() — file naming, auto-ID, headers, Default Choice
# ---------------------------------------------------------------------------


class TestWriteDeferral(unittest.TestCase):
    """Tests for write_deferral() — all requirements."""

    def _make_question(self, question_id: int = 1, severity: str = "blocking",
                       default_choice: str | None = None) -> DeferralQuestion:
        return DeferralQuestion(
            feature="test-feat",
            question_id=question_id,
            severity=severity,
            context="Some context.",
            question="What should I do?",
            default_choice=default_choice,
        )

    def test_file_created_with_zero_padded_name_and_no_tmp_residue(self):
        """Correct filename is written atomically; no .tmp files remain."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            q = self._make_question(question_id=1)
            written = write_deferral(q, d)
            self.assertEqual(written.name, "test-feat-q001.md")
            self.assertTrue(written.is_file())
            self.assertEqual(list(d.glob("*.tmp")), [])

    def test_zero_question_id_auto_assigned_and_mutates(self):
        """question_id=0 triggers auto-assignment and mutates the object in place."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            q = DeferralQuestion(
                feature="test-feat",
                question_id=0,
                severity="blocking",
                context="ctx",
                question="q?",
            )
            write_deferral(q, d)
            self.assertNotEqual(q.question_id, 0)
            self.assertEqual(q.question_id, 1)

    def test_sequential_calls_produce_distinct_ids(self):
        """Two auto-assigned writes produce IDs 1 and 2."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            q1 = DeferralQuestion(
                feature="test-feat", question_id=0, severity="blocking",
                context="c1", question="q1?",
            )
            q2 = DeferralQuestion(
                feature="test-feat", question_id=0, severity="blocking",
                context="c2", question="q2?",
            )
            p1 = write_deferral(q1, d)
            p2 = write_deferral(q2, d)
            self.assertNotEqual(p1, p2)
            self.assertEqual(q1.question_id, 1)
            self.assertEqual(q2.question_id, 2)

    def test_all_four_required_section_headers_present(self):
        """Written file contains all four required ## section headers."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            q = self._make_question()
            written = write_deferral(q, d)
            content = written.read_text(encoding="utf-8")
            for header in ("## Context", "## Question",
                           "## Options Considered", "## What the Pipeline Tried"):
                self.assertIn(header, content, msg=f"Missing header: {header}")

    def test_default_choice_present_for_non_blocking(self):
        """Default Choice section appears when severity != 'blocking' and default_choice set."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            q = self._make_question(severity="non-blocking", default_choice="Option A")
            written = write_deferral(q, d)
            content = written.read_text(encoding="utf-8")
            self.assertIn("## Default Choice", content)
            self.assertIn("Option A", content)

    def test_default_choice_absent_for_blocking(self):
        """Default Choice section is omitted when severity == 'blocking'."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            q = self._make_question(severity="blocking", default_choice="Option A")
            written = write_deferral(q, d)
            content = written.read_text(encoding="utf-8")
            self.assertNotIn("## Default Choice", content)


# ---------------------------------------------------------------------------
# Task 3: read_deferrals() — round-trip and malformed-file resilience
# ---------------------------------------------------------------------------


class TestReadDeferrals(unittest.TestCase):
    """Tests for read_deferrals() — round-trip accuracy and malformed-file handling."""

    def test_round_trip_matches_original(self):
        """A question written via write_deferral() and read back matches key fields."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            q = DeferralQuestion(
                feature="round-trip-feat",
                question_id=0,
                severity="non-blocking",
                context="Round-trip context.",
                question="Is this correct?",
            )
            write_deferral(q, d)
            results = read_deferrals(d)
            self.assertEqual(len(results), 1)
            r = results[0]
            self.assertEqual(r.feature, "round-trip-feat")
            self.assertEqual(r.question_id, 1)
            self.assertEqual(r.severity, "non-blocking")
            self.assertEqual(r.question, "Is this correct?")

    def test_malformed_file_skipped_with_warning(self):
        """A malformed markdown file is skipped; valid files still returned."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            # Write one valid file
            q = DeferralQuestion(
                feature="valid-feat",
                question_id=1,
                severity="blocking",
                context="ctx",
                question="q?",
            )
            write_deferral(q, d)
            # Write a malformed file with a matching glob name
            (d / "valid-feat-q099.md").write_text(
                "this is not a valid deferral file", encoding="utf-8"
            )
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                results = read_deferrals(d)
            self.assertEqual(len(results), 1)
            self.assertEqual(len(caught), 1)
            self.assertTrue(issubclass(caught[0].category, UserWarning))


# ---------------------------------------------------------------------------
# Task 4: write_escalation() and _next_escalation_n()
# ---------------------------------------------------------------------------


class TestWriteEscalation(unittest.TestCase):
    """Tests for write_escalation() and _next_escalation_n()."""

    def test_all_seven_fields_present(self):
        """A single write produces a JSONL line with all 7 required fields."""
        with tempfile.TemporaryDirectory() as tmp:
            session_dir = Path(tmp)
            path = session_dir / "escalations.jsonl"
            entry = EscalationEntry.build(
                session_id="sess-1",
                feature="feat",
                round=1,
                n=1,
                question="Do this?",
                context="Doing thing.",
            )
            write_escalation(entry, session_dir=session_dir)
            data = json.loads(path.read_text(encoding="utf-8").strip())
            for key in ("type", "escalation_id", "feature", "round",
                        "question", "context", "ts"):
                self.assertIn(key, data)
                self.assertIsNotNone(data[key])

    def test_two_writes_produce_two_distinct_lines(self):
        """Two escalation writes append two separate lines with distinct IDs."""
        with tempfile.TemporaryDirectory() as tmp:
            session_dir = Path(tmp)
            path = session_dir / "escalations.jsonl"
            e1 = EscalationEntry.build(
                session_id="sess-1", feature="feat", round=1, n=1,
                question="Q1?", context="ctx1",
            )
            e2 = EscalationEntry.build(
                session_id="sess-1", feature="feat", round=1, n=2,
                question="Q2?", context="ctx2",
            )
            write_escalation(e1, session_dir=session_dir)
            write_escalation(e2, session_dir=session_dir)
            lines = [
                l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()
            ]
            self.assertEqual(len(lines), 2)
            ids = {json.loads(l)["escalation_id"] for l in lines}
            self.assertEqual(ids, {"sess-1-feat-1-q1", "sess-1-feat-1-q2"})

    def test_next_escalation_n_sequential_ids(self):
        """_next_escalation_n returns 1 before any write and 2 after first write."""
        with tempfile.TemporaryDirectory() as tmp:
            session_dir = Path(tmp)
            n_before = _next_escalation_n("feat", 1, session_dir)
            self.assertEqual(n_before, 1)
            entry = EscalationEntry.build(
                session_id="sess-1", feature="feat", round=1, n=1,
                question="Q?", context="ctx",
            )
            write_escalation(entry, session_dir=session_dir)
            n_after = _next_escalation_n("feat", 1, session_dir)
            self.assertEqual(n_after, 2)


if __name__ == "__main__":
    unittest.main()
