"""Unit tests for parser.py separator tolerance and backward compatibility.

Task 6 — TestSeparatorVariants: all four separator styles parse correctly.
Task 6 — TestEmbeddedSeparator: em dashes in task names are preserved.
Task 6 — TestMixedSeparators: plans with mixed separator styles parse all tasks.
Task 6 — TestNormalizationIdempotent: normalization is a no-op on correct plans.
Task 6 — TestNormalizationPreservesBody: body text with separators is unchanged.
037-T4 — TestMasterPlanConcurrencyLimitBackwardCompat: historical plans with
         concurrency_limit config rows parse without error.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cortex_command.pipeline.parser import (
    FeaturePlan,
    parse_feature_plan,
    parse_master_plan,
    _normalize_task_separators,
    _parse_field_status,
)


def _make_plan(tasks_body: str) -> str:
    """Return a minimal valid plan with the given tasks section."""
    return (
        "# Plan: test-feature\n\n"
        "## Overview\ntest\n\n"
        "## Tasks\n"
        f"{tasks_body}"
    )


def _task_block(heading: str, **fields: str) -> str:
    """Build a single task block from a heading and optional fields."""
    lines = [heading]
    for key, value in fields.items():
        lines.append(f"- **{key}**: {value}")
    return "\n".join(lines) + "\n"


class TestSeparatorVariants(unittest.TestCase):
    """Task headings with all four separator variants parse to correct task number and description."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmpdir.cleanup()

    def _parse(self, tasks_body: str) -> FeaturePlan:
        plan_path = Path(self._tmpdir.name) / "plan.md"
        plan_path.write_text(_make_plan(tasks_body), encoding="utf-8")
        return parse_feature_plan(plan_path)

    def test_colon_separator(self):
        """### Task 1: Description parses correctly."""
        plan = self._parse(_task_block(
            "### Task 1: Build the widget",
            Complexity="simple",
        ))
        self.assertEqual(len(plan.tasks), 1)
        self.assertEqual(plan.tasks[0].number, 1)
        self.assertEqual(plan.tasks[0].description, "Build the widget")

    def test_em_dash_separator(self):
        """### Task 1 \u2014 Description (em dash) parses correctly."""
        plan = self._parse(_task_block(
            "### Task 1 \u2014 Build the widget",
            Complexity="simple",
        ))
        self.assertEqual(len(plan.tasks), 1)
        self.assertEqual(plan.tasks[0].number, 1)
        self.assertEqual(plan.tasks[0].description, "Build the widget")

    def test_en_dash_separator(self):
        """### Task 1\u2013 Description (en dash) parses correctly."""
        plan = self._parse(_task_block(
            "### Task 1\u2013 Build the widget",
            Complexity="simple",
        ))
        self.assertEqual(len(plan.tasks), 1)
        self.assertEqual(plan.tasks[0].number, 1)
        self.assertEqual(plan.tasks[0].description, "Build the widget")

    def test_hyphen_separator(self):
        """### Task 1 - Description (hyphen-minus) parses correctly."""
        plan = self._parse(_task_block(
            "### Task 1 - Build the widget",
            Complexity="simple",
        ))
        self.assertEqual(len(plan.tasks), 1)
        self.assertEqual(plan.tasks[0].number, 1)
        self.assertEqual(plan.tasks[0].description, "Build the widget")


class TestEmbeddedSeparator(unittest.TestCase):
    """Task names with embedded em dashes don't get truncated."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmpdir.cleanup()

    def _parse(self, tasks_body: str) -> FeaturePlan:
        plan_path = Path(self._tmpdir.name) / "plan.md"
        plan_path.write_text(_make_plan(tasks_body), encoding="utf-8")
        return parse_feature_plan(plan_path)

    def test_embedded_em_dash_preserved(self):
        """### Task 1 \u2014 Fix em-dash parser \u2014 round 2 keeps full description."""
        plan = self._parse(_task_block(
            "### Task 1 \u2014 Fix em-dash parser \u2014 round 2",
            Complexity="simple",
        ))
        self.assertEqual(len(plan.tasks), 1)
        self.assertEqual(plan.tasks[0].number, 1)
        self.assertEqual(
            plan.tasks[0].description,
            "Fix em-dash parser \u2014 round 2",
        )


class TestMixedSeparators(unittest.TestCase):
    """Plans with mixed separator styles parse all tasks correctly."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmpdir.cleanup()

    def _parse(self, tasks_body: str) -> FeaturePlan:
        plan_path = Path(self._tmpdir.name) / "plan.md"
        plan_path.write_text(_make_plan(tasks_body), encoding="utf-8")
        return parse_feature_plan(plan_path)

    def test_mixed_separators_all_parsed(self):
        """Four tasks with different separators all parse successfully."""
        body = (
            _task_block("### Task 1: Colon task", Complexity="simple")
            + _task_block("### Task 2 \u2014 Em dash task", Complexity="moderate")
            + _task_block("### Task 3\u2013 En dash task", Complexity="simple")
            + _task_block("### Task 4 - Hyphen task", Complexity="simple")
        )
        plan = self._parse(body)
        self.assertEqual(len(plan.tasks), 4)
        self.assertEqual(plan.tasks[0].number, 1)
        self.assertEqual(plan.tasks[0].description, "Colon task")
        self.assertEqual(plan.tasks[1].number, 2)
        self.assertEqual(plan.tasks[1].description, "Em dash task")
        self.assertEqual(plan.tasks[2].number, 3)
        self.assertEqual(plan.tasks[2].description, "En dash task")
        self.assertEqual(plan.tasks[3].number, 4)
        self.assertEqual(plan.tasks[3].description, "Hyphen task")


class TestNormalizationIdempotent(unittest.TestCase):
    """Normalization is a no-op on already-correct plans (colon separators)."""

    def test_colon_plan_unchanged(self):
        """A plan that already uses colons is not modified by normalization."""
        text = _make_plan(
            _task_block("### Task 1: First task", Complexity="simple")
            + _task_block("### Task 2: Second task", Complexity="simple")
        )
        normalized = _normalize_task_separators(text)
        self.assertEqual(normalized, text)


class TestNormalizationPreservesBody(unittest.TestCase):
    """Normalization does not corrupt task body text containing separator characters."""

    def test_body_em_dash_unchanged(self):
        """Em dash in bullet text within a task body is preserved after normalization."""
        task_body = (
            "### Task 1 \u2014 My task\n"
            "- **What**: Fix the parser \u2014 this is important\n"
            "- **Files**: `src/parser.py`\n"
            "- **Complexity**: simple\n"
        )
        text = _make_plan(task_body)
        normalized = _normalize_task_separators(text)
        # The heading should be normalized to colon
        self.assertIn("### Task 1: My task", normalized)
        # The body line with em dash should be unchanged
        self.assertIn("Fix the parser \u2014 this is important", normalized)

    def test_body_hyphen_in_description_unchanged(self):
        """Hyphen-minus in non-heading body text is not affected by normalization."""
        task_body = (
            "### Task 1 - My task\n"
            "- **What**: Use key-value pairs - they are faster\n"
            "- **Complexity**: simple\n"
        )
        text = _make_plan(task_body)
        normalized = _normalize_task_separators(text)
        # The heading should be normalized to colon
        self.assertIn("### Task 1: My task", normalized)
        # The body line with hyphen should be unchanged
        self.assertIn("Use key-value pairs - they are faster", normalized)


class TestMasterPlanConcurrencyLimitBackwardCompat(unittest.TestCase):
    """Historical master plans with a concurrency_limit config row parse without error.

    Protects the 4 historical plans in lifecycle/sessions/ that map_results.py
    processes. The concurrency_limit field was removed from MasterPlanConfig but
    the parser must silently ignore it so old plans remain parseable.
    """

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_concurrency_limit_row_ignored_gracefully(self):
        """A config table with concurrency_limit parses without error."""
        master_plan_md = (
            "# Master Plan: legacy-batch\n\n"
            "## Configuration\n\n"
            "| Key | Value |\n"
            "| --- | ----- |\n"
            "| test_command | just test |\n"
            "| concurrency_limit | 2 |\n"
            "| base_branch | main |\n\n"
            "## Features\n\n"
            "| Priority | Feature | Complexity | Tasks | Summary |\n"
            "| -------- | ------- | ---------- | ----- | ------- |\n"
            "| 1 | alpha-feature | simple | 3 | First feature |\n"
        )
        plan_path = Path(self._tmpdir.name) / "master-plan.md"
        plan_path.write_text(master_plan_md, encoding="utf-8")

        plan = parse_master_plan(plan_path)

        self.assertEqual(plan.name, "legacy-batch")
        self.assertEqual(plan.config.test_command, "just test")
        self.assertEqual(plan.config.base_branch, "main")
        self.assertFalse(hasattr(plan.config, "concurrency_limit"))
        self.assertEqual(len(plan.features), 1)
        self.assertEqual(plan.features[0].name, "alpha-feature")


class TestParseTasksStripsTrailingXXFromHeading(unittest.TestCase):
    """E1: trailing [x] or [X] on task headings is stripped from description; [ ] is preserved."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmpdir.cleanup()

    def _parse(self, tasks_body: str) -> FeaturePlan:
        plan_path = Path(self._tmpdir.name) / "plan.md"
        plan_path.write_text(_make_plan(tasks_body), encoding="utf-8")
        return parse_feature_plan(plan_path)

    def test_parse_tasks_strips_trailing_xX_from_heading(self):
        """Trailing [x]/[X] stripped from description; literal [ ] preserved."""
        body = (
            _task_block("### Task 2: Do the thing [x]", Complexity="simple")
            + _task_block("### Task 3: Other [X]", Complexity="simple")
            + _task_block("### Task 5: Reserve slot [ ]", Complexity="simple")
        )
        plan = self._parse(body)
        self.assertEqual(len(plan.tasks), 3)
        self.assertEqual(plan.tasks[0].description, "Do the thing")
        self.assertEqual(plan.tasks[1].description, "Other")
        self.assertEqual(plan.tasks[2].description, "Reserve slot [ ]")


class TestParseFieldStatusAnchoredMatch(unittest.TestCase):
    """E2: _parse_field_status matches [x]/[X] only at the anchor, not mid-line."""

    def test_parse_field_status_anchored_match(self):
        """Lowercase [x] prefix -> done."""
        body = "- **Status**: [x] complete\n"
        self.assertEqual(_parse_field_status(body), "done")

    def test_parse_field_status_anchored_match_uppercase(self):
        """Uppercase [X] prefix -> done."""
        body = "- **Status**: [X] complete\n"
        self.assertEqual(_parse_field_status(body), "done")

    def test_parse_field_status_anchored_match_rejects_mid_line_x(self):
        """Mid-line [x] no longer false-positives as done."""
        body = "- **Status**: see [x]y.txt pending\n"
        self.assertEqual(_parse_field_status(body), "pending")

    def test_parse_field_status_anchored_match_empty_box_is_pending(self):
        """Literal [ ] -> pending."""
        body = "- **Status**: [ ] pending\n"
        self.assertEqual(_parse_field_status(body), "pending")


def test_heading_and_status_round_trip(tmp_path):
    """R13: Parser round-trip integration — E1 heading strip + E2 Status anchor combined.

    Fixture plan.md has two tasks whose headings both end with trailing `[x]`:
      - Task 1: heading `[x]` AND Status `[x] complete` -> status=done, description stripped
      - Task 2: heading `[x]` AND Status `[ ] pending` -> status=pending, description stripped

    The second pattern mirrors `lifecycle/rewrite-verification-mindsetmd-to-positive-
    routing-structure-under-47-literalism/plan.md` Task 2, where an authored-`[x]` in
    the heading must not leak through as `status == done` when the Status field is
    genuinely `[ ] pending`.
    """
    plan_md = (
        "# Plan: round-trip-feature\n\n"
        "## Overview\n\n"
        "round-trip integration test\n\n"
        "## Tasks\n\n"
        "### Task 1: Do the complete thing [x]\n\n"
        "- **Files**: `src/a.py`\n"
        "- **What**: first task\n"
        "- **Depends on**: none\n"
        "- **Complexity**: simple\n"
        "- **Status**: [x] complete\n\n"
        "### Task 2: Capture baseline commit SHA and reference-file line counts [x]\n\n"
        "- **Files**: `src/b.py`\n"
        "- **What**: second task\n"
        "- **Depends on**: none\n"
        "- **Complexity**: simple\n"
        "- **Status**: [ ] pending\n"
    )
    plan_path = tmp_path / "plan.md"
    plan_path.write_text(plan_md, encoding="utf-8")

    plan = parse_feature_plan(plan_path)

    assert len(plan.tasks) == 2

    # Task 1: heading [x] stripped AND Status [x] complete -> done
    assert plan.tasks[0].number == 1
    assert plan.tasks[0].description == "Do the complete thing"
    assert plan.tasks[0].status == "done"

    # Task 2: heading [x] stripped AND Status [ ] pending -> pending
    # (exact pattern from the referenced lifecycle plan.md Task 2)
    assert plan.tasks[1].number == 2
    assert plan.tasks[1].description == (
        "Capture baseline commit SHA and reference-file line counts"
    )
    assert plan.tasks[1].status == "pending"


if __name__ == "__main__":
    unittest.main()
