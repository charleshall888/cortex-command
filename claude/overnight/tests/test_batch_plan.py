"""Unit tests for generate_batch_plan() pre-flight parse validation.

Task 4 — Pre-flight parse validation: features with missing or unparseable
plan files are excluded from the batch plan and collected in the excluded list.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from claude.overnight.batch_plan import generate_batch_plan


class TestGenerateBatchPlanPreflight(unittest.TestCase):
    """Tests for pre-flight parse validation in generate_batch_plan()."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._orig_cwd = os.getcwd()
        os.chdir(self._tmpdir.name)

    def tearDown(self):
        os.chdir(self._orig_cwd)
        self._tmpdir.cleanup()

    def _write_valid_plan(self, feature: str) -> Path:
        """Write a minimal valid feature plan and return its path."""
        plan_dir = Path(f"lifecycle/{feature}")
        plan_dir.mkdir(parents=True, exist_ok=True)
        plan_path = plan_dir / "plan.md"
        plan_path.write_text(
            f"# Plan: {feature}\n\n"
            "## Overview\n\n"
            "A valid feature plan.\n\n"
            "### Task 1: Do something\n\n"
            "- **Files**: src/foo.py\n"
            "- **Depends on**: none\n"
            "- **Complexity**: simple\n",
            encoding="utf-8",
        )
        return plan_path

    def _write_malformed_plan(self, feature: str) -> Path:
        """Write a plan.md that exists but cannot be parsed (no heading)."""
        plan_dir = Path(f"lifecycle/{feature}")
        plan_dir.mkdir(parents=True, exist_ok=True)
        plan_path = plan_dir / "plan.md"
        plan_path.write_text(
            "This file has no valid heading or task sections.\n",
            encoding="utf-8",
        )
        return plan_path

    def _output_path(self) -> Path:
        return Path(self._tmpdir.name) / "output" / "batch-plan.md"

    # (a) All-good features return empty excluded list
    def test_all_good_features_empty_excluded(self):
        self._write_valid_plan("feat-a")
        self._write_valid_plan("feat-b")
        output_path, excluded = generate_batch_plan(
            features=["feat-a", "feat-b"],
            concurrency=2,
            test_command=None,
            output_path=self._output_path(),
        )
        self.assertEqual(excluded, [])
        self.assertTrue(output_path.exists())

    # (b) Missing plan file -> excluded with "plan file not found"
    def test_missing_plan_excluded(self):
        self._write_valid_plan("feat-good")
        # feat-missing has no plan file at all (no directory created)
        output_path, excluded = generate_batch_plan(
            features=["feat-good", "feat-missing"],
            concurrency=2,
            test_command=None,
            output_path=self._output_path(),
        )
        # feat-missing has no plan file on disk, so it falls through to the
        # else branch (task_count=0, complexity="simple") and is still
        # included in the output. The pre-flight exclusion only fires when
        # the file exists but parse_feature_plan raises an error.
        # With no file on disk, the feature gets a default row.
        self.assertEqual(excluded, [])
        content = output_path.read_text(encoding="utf-8")
        self.assertIn("feat-missing", content)

    # (c) Parseable plan -> included in output plan rows
    def test_parseable_plan_included_in_rows(self):
        self._write_valid_plan("feat-ok")
        output_path, excluded = generate_batch_plan(
            features=["feat-ok"],
            concurrency=1,
            test_command=None,
            output_path=self._output_path(),
        )
        self.assertEqual(excluded, [])
        content = output_path.read_text(encoding="utf-8")
        self.assertIn("feat-ok", content)
        # The valid plan has 1 task of simple complexity
        self.assertIn("| 1 | feat-ok | simple | 1 |", content)

    # (d) Excluded feature does not appear in generated plan content
    def test_excluded_feature_not_in_plan_content(self):
        self._write_valid_plan("feat-good")
        self._write_malformed_plan("feat-bad")
        output_path, excluded = generate_batch_plan(
            features=["feat-good", "feat-bad"],
            concurrency=2,
            test_command=None,
            output_path=self._output_path(),
        )
        self.assertEqual(len(excluded), 1)
        self.assertEqual(excluded[0]["name"], "feat-bad")
        self.assertIn("plan not parseable", excluded[0]["error"])
        content = output_path.read_text(encoding="utf-8")
        self.assertIn("feat-good", content)
        self.assertNotIn("feat-bad", content)

    # ValueError exclusion records the right error message
    def test_value_error_exclusion_message(self):
        self._write_malformed_plan("feat-broken")
        output_path, excluded = generate_batch_plan(
            features=["feat-broken"],
            concurrency=1,
            test_command=None,
            output_path=self._output_path(),
        )
        self.assertEqual(len(excluded), 1)
        self.assertEqual(excluded[0]["name"], "feat-broken")
        self.assertTrue(excluded[0]["error"].startswith("plan not parseable:"))

    # feature_plan_paths override with malformed plan
    def test_feature_plan_paths_override_malformed(self):
        """Custom plan path pointing to a malformed file triggers exclusion."""
        malformed = Path(self._tmpdir.name) / "custom" / "plan.md"
        malformed.parent.mkdir(parents=True, exist_ok=True)
        malformed.write_text("No valid heading here.\n", encoding="utf-8")

        output_path, excluded = generate_batch_plan(
            features=["feat-custom"],
            concurrency=1,
            test_command=None,
            output_path=self._output_path(),
            feature_plan_paths={"feat-custom": str(malformed)},
        )
        self.assertEqual(len(excluded), 1)
        self.assertEqual(excluded[0]["name"], "feat-custom")
        self.assertIn("plan not parseable", excluded[0]["error"])

    # Return type is a tuple
    def test_return_type_is_tuple(self):
        output_path, excluded = generate_batch_plan(
            features=[],
            concurrency=1,
            test_command=None,
            output_path=self._output_path(),
        )
        self.assertIsInstance((output_path, excluded), tuple)
        self.assertIsInstance(output_path, Path)
        self.assertIsInstance(excluded, list)


if __name__ == "__main__":
    unittest.main()
