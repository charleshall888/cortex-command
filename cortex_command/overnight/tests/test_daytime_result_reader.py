"""Tests for cortex_command.overnight.daytime_result_reader — 3-tier fallback logic.

Validates Tier-1 (daytime-result.json + freshness check), Tier-2 (daytime-state.json
discrimination), and Tier-3 (outcome="unknown" + discriminated messages) per spec R6/R7.

The three Tier-3 discriminated messages are asserted verbatim against spec R6 text so
that any wording change in the helper is caught immediately.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cortex_command.overnight.daytime_result_reader import (
    _MSG_ABSENT,
    _MSG_NON_TERMINAL,
    _MSG_TERMINAL,
    classify_result,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SLUG = "my-feature"
DISPATCH_ID_A = "a" * 32
DISPATCH_ID_B = "b" * 32


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_lifecycle_root(tmp_path: Path) -> Path:
    """Return a lifecycle root with the feature subdirectory created."""
    root = tmp_path / "lifecycle"
    (root / SLUG).mkdir(parents=True, exist_ok=True)
    return root


def _valid_result(dispatch_id: str = DISPATCH_ID_A, outcome: str = "merged") -> dict:
    return {
        "schema_version": 1,
        "dispatch_id": dispatch_id,
        "feature": SLUG,
        "start_ts": "2026-01-01T00:00:00+00:00",
        "end_ts": "2026-01-01T01:00:00+00:00",
        "outcome": outcome,
        "terminated_via": "classification",
        "deferred_files": [],
        "error": None,
        "pr_url": None,
    }


def _valid_dispatch(dispatch_id: str = DISPATCH_ID_A) -> dict:
    return {
        "schema_version": 1,
        "dispatch_id": dispatch_id,
        "feature": SLUG,
        "start_ts": "2026-01-01T00:00:00+00:00",
        "pid": None,
    }


# ---------------------------------------------------------------------------
# Tier-1 success cases
# ---------------------------------------------------------------------------


class TestTier1Success:
    def test_merged_outcome(self, tmp_path: Path) -> None:
        """Tier 1 succeeds with a valid result + matching dispatch; outcome=merged."""
        root = _make_lifecycle_root(tmp_path)
        _write_json(root / SLUG / "daytime-result.json", _valid_result(outcome="merged"))
        _write_json(root / SLUG / "daytime-dispatch.json", _valid_dispatch())

        result = classify_result(SLUG, lifecycle_root=root)

        assert result["source_tier"] == 1
        assert result["outcome"] == "merged"
        assert result["terminated_via"] == "classification"
        assert result["pr_url"] is None
        assert result["deferred_files"] == []
        assert result["error"] is None
        assert result["log_tail"] is None

    def test_deferred_outcome_with_files(self, tmp_path: Path) -> None:
        """Tier 1 succeeds and surfaces deferred_files from the result dict."""
        root = _make_lifecycle_root(tmp_path)
        deferred_path = str(root / SLUG / "deferred" / "deferral.md")
        result_data = _valid_result(outcome="deferred")
        result_data["terminated_via"] = "classification"
        result_data["deferred_files"] = [deferred_path]
        _write_json(root / SLUG / "daytime-result.json", result_data)
        _write_json(root / SLUG / "daytime-dispatch.json", _valid_dispatch())

        result = classify_result(SLUG, lifecycle_root=root)

        assert result["source_tier"] == 1
        assert result["outcome"] == "deferred"
        assert result["deferred_files"] == [deferred_path]

    def test_pr_url_surfaced(self, tmp_path: Path) -> None:
        """Tier 1 returns pr_url from result file when present."""
        root = _make_lifecycle_root(tmp_path)
        result_data = _valid_result(outcome="merged")
        result_data["pr_url"] = "https://github.com/org/repo/pull/42"
        _write_json(root / SLUG / "daytime-result.json", result_data)
        _write_json(root / SLUG / "daytime-dispatch.json", _valid_dispatch())

        result = classify_result(SLUG, lifecycle_root=root)

        assert result["source_tier"] == 1
        assert result["pr_url"] == "https://github.com/org/repo/pull/42"

    def test_error_surfaced_for_failed_outcome(self, tmp_path: Path) -> None:
        """Tier 1 returns error from result file for failed outcomes."""
        root = _make_lifecycle_root(tmp_path)
        result_data = _valid_result(outcome="failed")
        result_data["terminated_via"] = "exception"
        result_data["error"] = "Something went wrong"
        _write_json(root / SLUG / "daytime-result.json", result_data)
        _write_json(root / SLUG / "daytime-dispatch.json", _valid_dispatch())

        result = classify_result(SLUG, lifecycle_root=root)

        assert result["source_tier"] == 1
        assert result["outcome"] == "failed"
        assert result["error"] == "Something went wrong"


# ---------------------------------------------------------------------------
# Tier-1 fallback cases — dispatch_id / freshness / schema checks
# ---------------------------------------------------------------------------


class TestTier1FallbackToTier2:
    def test_freshness_mismatch_falls_to_tier2(self, tmp_path: Path) -> None:
        """Dispatch_id in result != dispatch_id in dispatch file → falls to tier 2/3."""
        root = _make_lifecycle_root(tmp_path)
        # result has dispatch_id A, dispatch file has dispatch_id B
        _write_json(root / SLUG / "daytime-result.json", _valid_result(dispatch_id=DISPATCH_ID_A))
        _write_json(root / SLUG / "daytime-dispatch.json", _valid_dispatch(dispatch_id=DISPATCH_ID_B))

        result = classify_result(SLUG, lifecycle_root=root)

        assert result["source_tier"] == 3
        assert result["outcome"] == "unknown"

    def test_dispatch_file_missing_falls_to_tier2(self, tmp_path: Path) -> None:
        """Only result file present — cannot validate freshness → falls to tier 2/3."""
        root = _make_lifecycle_root(tmp_path)
        _write_json(root / SLUG / "daytime-result.json", _valid_result())
        # No daytime-dispatch.json written

        result = classify_result(SLUG, lifecycle_root=root)

        assert result["source_tier"] == 3
        assert result["outcome"] == "unknown"

    def test_schema_version_wrong_falls_to_tier2(self, tmp_path: Path) -> None:
        """schema_version=99 → hard equality check fails → falls to tier 2/3."""
        root = _make_lifecycle_root(tmp_path)
        result_data = _valid_result()
        result_data["schema_version"] = 99
        _write_json(root / SLUG / "daytime-result.json", result_data)
        _write_json(root / SLUG / "daytime-dispatch.json", _valid_dispatch())

        result = classify_result(SLUG, lifecycle_root=root)

        assert result["source_tier"] == 3
        assert result["outcome"] == "unknown"

    def test_schema_version_missing_falls_to_tier2(self, tmp_path: Path) -> None:
        """schema_version absent → missing counts as != 1 → falls to tier 2/3."""
        root = _make_lifecycle_root(tmp_path)
        result_data = _valid_result()
        del result_data["schema_version"]
        _write_json(root / SLUG / "daytime-result.json", result_data)
        _write_json(root / SLUG / "daytime-dispatch.json", _valid_dispatch())

        result = classify_result(SLUG, lifecycle_root=root)

        assert result["source_tier"] == 3
        assert result["outcome"] == "unknown"

    def test_malformed_json_falls_to_tier2_without_raising(self, tmp_path: Path) -> None:
        """Truncated result file → falls to tier 2/3 without raising an exception."""
        root = _make_lifecycle_root(tmp_path)
        _write_text(root / SLUG / "daytime-result.json", "{")  # truncated
        _write_json(root / SLUG / "daytime-dispatch.json", _valid_dispatch())

        # Must not raise
        result = classify_result(SLUG, lifecycle_root=root)

        assert result["source_tier"] == 3
        assert result["outcome"] == "unknown"


# ---------------------------------------------------------------------------
# Tier-2 → Tier-3 discrimination messages (verbatim spec R6 assertions)
# ---------------------------------------------------------------------------


class TestTier3DiscriminatedMessages:
    """All three messages are asserted verbatim against spec R6 text."""

    def test_tier2_terminal_phase_complete(self, tmp_path: Path) -> None:
        """phase='complete' → terminal discrimination → verbatim spec R6 terminal message."""
        root = _make_lifecycle_root(tmp_path)
        # No result file, no dispatch file
        state = {"phase": "complete", "session_id": "s", "plan_ref": "p", "current_round": 1}
        _write_json(root / SLUG / "daytime-state.json", state)

        result = classify_result(SLUG, lifecycle_root=root)

        assert result["source_tier"] == 3
        assert result["outcome"] == "unknown"
        expected_message = _MSG_TERMINAL.format(slug=SLUG)
        assert result["message"] == expected_message, (
            f"Expected verbatim spec R6 terminal message.\n"
            f"Expected: {expected_message!r}\n"
            f"Got:      {result['message']!r}"
        )

    def test_tier2_non_terminal_phase_executing(self, tmp_path: Path) -> None:
        """phase='executing' → non-terminal discrimination → verbatim spec R6 non-terminal message."""
        root = _make_lifecycle_root(tmp_path)
        state = {"phase": "executing", "session_id": "s", "plan_ref": "p", "current_round": 1}
        _write_json(root / SLUG / "daytime-state.json", state)

        result = classify_result(SLUG, lifecycle_root=root)

        assert result["source_tier"] == 3
        assert result["outcome"] == "unknown"
        expected_message = _MSG_NON_TERMINAL.format(slug=SLUG)
        assert result["message"] == expected_message, (
            f"Expected verbatim spec R6 non-terminal message.\n"
            f"Expected: {expected_message!r}\n"
            f"Got:      {result['message']!r}"
        )

    def test_tier2_state_file_absent(self, tmp_path: Path) -> None:
        """No state file → absent discrimination → verbatim spec R6 absent message."""
        root = _make_lifecycle_root(tmp_path)
        # No result, no dispatch, no state file

        result = classify_result(SLUG, lifecycle_root=root)

        assert result["source_tier"] == 3
        assert result["outcome"] == "unknown"
        expected_message = _MSG_ABSENT.format(slug=SLUG)
        assert result["message"] == expected_message, (
            f"Expected verbatim spec R6 absent message.\n"
            f"Expected: {expected_message!r}\n"
            f"Got:      {result['message']!r}"
        )

    def test_log_tail_included_in_tier3(self, tmp_path: Path) -> None:
        """Tier 3 includes log_tail from daytime.log when present."""
        root = _make_lifecycle_root(tmp_path)
        log_lines = [f"line {i}" for i in range(30)]
        _write_text(root / SLUG / "daytime.log", "\n".join(log_lines))

        result = classify_result(SLUG, lifecycle_root=root)

        assert result["source_tier"] == 3
        # Should include last 20 lines
        assert result["log_tail"] is not None
        tail_lines = result["log_tail"].splitlines()
        assert len(tail_lines) == 20
        assert tail_lines[-1] == "line 29"

    def test_log_tail_none_when_log_absent(self, tmp_path: Path) -> None:
        """Tier 3 log_tail is None when daytime.log does not exist."""
        root = _make_lifecycle_root(tmp_path)
        # No daytime.log

        result = classify_result(SLUG, lifecycle_root=root)

        assert result["source_tier"] == 3
        assert result["log_tail"] is None

    def test_tier2_non_terminal_other_phases(self, tmp_path: Path) -> None:
        """Non-complete, non-absent phases (e.g. 'planning') → non-terminal message."""
        root = _make_lifecycle_root(tmp_path)
        state = {"phase": "planning", "session_id": "s", "plan_ref": "p", "current_round": 1}
        _write_json(root / SLUG / "daytime-state.json", state)

        result = classify_result(SLUG, lifecycle_root=root)

        assert result["source_tier"] == 3
        expected_message = _MSG_NON_TERMINAL.format(slug=SLUG)
        assert result["message"] == expected_message


# ---------------------------------------------------------------------------
# Verbatim message string constants — guard against accidental edits
# ---------------------------------------------------------------------------


class TestVerbatimMessageConstants:
    """Pin the exact message strings from spec R6 so wording changes are caught."""

    def test_terminal_message_verbatim(self) -> None:
        assert _MSG_TERMINAL == (
            "Subprocess likely completed but its result file is missing or invalid. "
            "Check `lifecycle/{slug}/daytime.log` for the final outcome."
        )

    def test_non_terminal_message_verbatim(self) -> None:
        assert _MSG_NON_TERMINAL == (
            "Subprocess did not complete (still running, killed, or crashed "
            "mid-execution). Check `lifecycle/{slug}/daytime.log`."
        )

    def test_absent_message_verbatim(self) -> None:
        assert _MSG_ABSENT == (
            "Subprocess never started (pre-flight failure). "
            "Check `lifecycle/{slug}/daytime.log`."
        )
