"""Unit tests for review_dispatch.py: parse_verdict() and dispatch_review().

Tests cover:
  - Valid JSON verdict block extraction from review.md
  - Malformed JSON returns ERROR result
  - Missing file returns ERROR result
  - Multiple JSON blocks returns the first match
  - cycle threading at review-fix dispatch sites
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

# conftest.py installs the SDK stub before this module is imported under
# pytest, but the dispatch import below also triggers under unittest runs;
# call it directly to keep both runners happy.
from cortex_command.pipeline.tests.conftest import _install_sdk_stub
_install_sdk_stub()

# Pre-load the overnight package before importing review_dispatch so its
# transitive `from cortex_command.overnight.deferral import …` does not
# trigger overnight/__init__.py to circle back through outcome_router →
# review_dispatch while review_dispatch is still mid-import.  Importing
# overnight.deferral first leaves overnight.__init__ already executed by
# the time review_dispatch.py runs its own deferral import, so the cycle
# closes cleanly.  See the cortex_command/overnight/__init__.py top-level
# imports for the dependency chain.
import cortex_command.overnight.deferral  # noqa: F401, E402

import cortex_command.pipeline.review_dispatch as _review_dispatch_module  # noqa: E402
from cortex_command.pipeline.dispatch import DispatchResult  # noqa: E402
from cortex_command.pipeline.merge import MergeResult  # noqa: E402
from cortex_command.pipeline.review_dispatch import dispatch_review, parse_verdict  # noqa: E402


class TestParseVerdict:
    """Tests for parse_verdict()."""

    def test_valid_verdict_block(self, tmp_path: Path):
        """Extracts a well-formed JSON verdict block from review.md."""
        review_path = tmp_path / "review.md"
        verdict_data = {
            "verdict": "APPROVED",
            "cycle": 1,
            "issues": [],
        }
        review_path.write_text(
            "# Review\n\nSome commentary.\n\n"
            f"```json\n{json.dumps(verdict_data, indent=2)}\n```\n",
            encoding="utf-8",
        )

        result = parse_verdict(review_path)
        assert result["verdict"] == "APPROVED"
        assert result["cycle"] == 1
        assert result["issues"] == []

    def test_changes_requested_verdict(self, tmp_path: Path):
        """Extracts a CHANGES_REQUESTED verdict correctly."""
        review_path = tmp_path / "review.md"
        verdict_data = {
            "verdict": "CHANGES_REQUESTED",
            "cycle": 2,
            "issues": ["Missing tests", "Unused import"],
        }
        review_path.write_text(
            "# Review\n\n"
            f"```json\n{json.dumps(verdict_data)}\n```\n",
            encoding="utf-8",
        )

        result = parse_verdict(review_path)
        assert result["verdict"] == "CHANGES_REQUESTED"
        assert result["cycle"] == 2
        assert result["issues"] == ["Missing tests", "Unused import"]

    def test_malformed_json_returns_error(self, tmp_path: Path):
        """Malformed JSON inside a code block returns the ERROR result."""
        review_path = tmp_path / "review.md"
        review_path.write_text(
            "# Review\n\n```json\n{not valid json}\n```\n",
            encoding="utf-8",
        )

        result = parse_verdict(review_path)
        assert result["verdict"] == "ERROR"
        assert result["cycle"] == 0
        assert result["issues"] == []

    def test_missing_file_returns_error(self, tmp_path: Path):
        """Non-existent review.md returns the ERROR result."""
        review_path = tmp_path / "nonexistent" / "review.md"

        result = parse_verdict(review_path)
        assert result["verdict"] == "ERROR"
        assert result["cycle"] == 0
        assert result["issues"] == []

    def test_no_json_block_returns_error(self, tmp_path: Path):
        """Review file without a JSON code block returns the ERROR result."""
        review_path = tmp_path / "review.md"
        review_path.write_text(
            "# Review\n\nThis review has no JSON block.\n",
            encoding="utf-8",
        )

        result = parse_verdict(review_path)
        assert result["verdict"] == "ERROR"
        assert result["cycle"] == 0
        assert result["issues"] == []

    def test_empty_file_returns_error(self, tmp_path: Path):
        """Empty review.md returns the ERROR result."""
        review_path = tmp_path / "review.md"
        review_path.write_text("", encoding="utf-8")

        result = parse_verdict(review_path)
        assert result["verdict"] == "ERROR"
        assert result["cycle"] == 0
        assert result["issues"] == []

    def test_verdict_with_surrounding_text(self, tmp_path: Path):
        """JSON block surrounded by prose is still extracted correctly."""
        review_path = tmp_path / "review.md"
        verdict_data = {
            "verdict": "REJECTED",
            "cycle": 1,
            "issues": ["Fundamental design flaw"],
        }
        review_path.write_text(
            "# Code Review\n\n"
            "The implementation has issues.\n\n"
            f"```json\n{json.dumps(verdict_data)}\n```\n\n"
            "Please address the above.\n",
            encoding="utf-8",
        )

        result = parse_verdict(review_path)
        assert result["verdict"] == "REJECTED"
        assert result["cycle"] == 1
        assert result["issues"] == ["Fundamental design flaw"]


class TestCycleThreading(unittest.IsolatedAsyncioTestCase):
    """Tests that cycle is threaded at the review-fix dispatch sites (R13)."""

    async def test_cycle_threaded_at_review_fix_sites(self):
        """cycle=1 at review_dispatch.py:383 and cycle=2 at review_dispatch.py:496.

        Drives the CHANGES_REQUESTED -> fix -> re-review -> APPROVED path
        so both review-fix dispatch_task call sites fire. Asserts:
          - call 0 (initial review, skill="review"): no "cycle" kwarg
          - call 1 (cycle-1 fix site, line 383): kwargs["cycle"] == 1
          - call 2 (cycle-2 re-review site, line 496): kwargs["cycle"] == 2
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            feature = "feat-cycle-threading"
            lifecycle_base = tmp_path / "cortex" / "lifecycle"
            feature_dir = lifecycle_base / feature
            feature_dir.mkdir(parents=True)

            spec_path = feature_dir / "spec.md"
            spec_path.write_text("# Spec\n\nSpec content.\n", encoding="utf-8")

            review_md_path = feature_dir / "review.md"

            # Pre-stage cycle 1 verdict (CHANGES_REQUESTED) so the first
            # parse_verdict() call after the initial review returns the
            # value that drives the rework path.
            cycle1_verdict = json.dumps({
                "verdict": "CHANGES_REQUESTED",
                "cycle": 1,
                "issues": ["fix this"],
            })
            review_md_path.write_text(
                f"# Review\n\n```json\n{cycle1_verdict}\n```\n",
                encoding="utf-8",
            )

            cycle2_verdict = json.dumps({
                "verdict": "APPROVED",
                "cycle": 2,
                "issues": [],
            })

            # Track dispatch_task invocations and rewrite review.md after
            # the cycle-2 dispatch so the second parse_verdict() sees
            # APPROVED.
            async def fake_dispatch(**kwargs) -> DispatchResult:
                if kwargs.get("skill") == "review-fix" and kwargs.get("cycle") == 2:
                    review_md_path.write_text(
                        f"# Review\n\n```json\n{cycle2_verdict}\n```\n",
                        encoding="utf-8",
                    )
                return DispatchResult(
                    success=True,
                    output="ok",
                    cost_usd=0.01,
                )

            mock_dispatch = AsyncMock(side_effect=fake_dispatch)

            # subprocess.run side effect: emit different SHAs for
            # before/after so the SHA circuit breaker does not fire.
            sha_counter = {"n": 0}

            def fake_run(*args, **kwargs):
                sha_counter["n"] += 1

                class _Result:
                    stdout = f"sha{sha_counter['n']}\n"
                    stderr = ""
                    returncode = 0

                return _Result()

            # merge_feature must succeed for the cycle-2 review to fire.
            def fake_merge(*args, **kwargs) -> MergeResult:
                return MergeResult(success=True, feature=feature, conflict=False)

            with (
                patch.object(_review_dispatch_module, "dispatch_task", new=mock_dispatch),
                patch.object(_review_dispatch_module.subprocess, "run", side_effect=fake_run),
                patch.object(_review_dispatch_module, "merge_feature", side_effect=fake_merge),
            ):
                result = await dispatch_review(
                    feature=feature,
                    worktree_path=tmp_path / "worktree",
                    branch="pipeline/feat-cycle-threading",
                    spec_path=spec_path,
                    complexity="simple",
                    criticality="medium",
                    lifecycle_base=lifecycle_base,
                    deferred_dir=tmp_path / "deferred",
                    base_branch="main",
                )

            # Sanity: the rework path completed (cycle 2 APPROVED).
            self.assertTrue(result.approved)
            self.assertEqual(result.verdict, "APPROVED")
            self.assertEqual(result.cycle, 2)

            # Three dispatch_task calls: initial review, cycle-1 fix,
            # cycle-2 re-review.
            self.assertEqual(len(mock_dispatch.call_args_list), 3)

            # Call 0: initial review at line 252 — skill="review" with
            # NO cycle kwarg (defends against accidental cycle pollution
            # at the non-review-fix call site).
            call0 = mock_dispatch.call_args_list[0]
            self.assertEqual(call0.kwargs["skill"], "review")
            self.assertNotIn(
                "cycle",
                call0.kwargs,
                "Initial review dispatch must not carry a cycle kwarg "
                "(would trip the runtime guard for skill != 'review-fix').",
            )

            # Call 1: cycle-1 fix site at review_dispatch.py:383.
            call1 = mock_dispatch.call_args_list[1]
            self.assertEqual(call1.kwargs["skill"], "review-fix")
            self.assertEqual(call1.kwargs["cycle"], 1)

            # Call 2: cycle-2 re-review site at review_dispatch.py:496.
            call2 = mock_dispatch.call_args_list[2]
            self.assertEqual(call2.kwargs["skill"], "review-fix")
            self.assertEqual(call2.kwargs["cycle"], 2)
