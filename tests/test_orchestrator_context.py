"""Unit tests for aggregate_round_context in cortex_command.overnight.orchestrator_context.

Covers spec acceptance criteria:
  R3  — returned dict shape (5 top-level keys, merge_conflict_events dropped per plan deviation)
  R4  — strategy passes through unchanged (no truncation)
  R5  — missing-file tolerance (FileNotFoundError on absent overnight-state.json; defaults elsewhere)
  R6  — malformed escalations.jsonl line skipped with stderr WARNING
  R8  — schema-version drift raises RuntimeError
  R10 — contract fixture pins the exact top-level key set
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

import cortex_command.overnight.orchestrator_context as _ctx_module
from cortex_command.overnight.orchestrator_context import aggregate_round_context
from cortex_command.overnight.state import OvernightState, save_state
from cortex_command.overnight.strategy import OvernightStrategy, save_strategy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_minimal_state(session_dir: Path) -> OvernightState:
    """Write a minimal valid overnight-state.json and return the state object."""
    state = OvernightState(
        session_id="test-session-001",
        plan_ref="cortex/lifecycle/test/plan.md",
    )
    save_state(state, session_dir / "overnight-state.json")
    return state


# ---------------------------------------------------------------------------
# R3: dict shape — 5 top-level keys (merge_conflict_events dropped per plan deviation)
# ---------------------------------------------------------------------------

def test_dict_shape_returns_five_top_level_keys(tmp_path: Path) -> None:
    """R3: aggregate_round_context returns a dict with exactly 5 top-level keys."""
    _write_minimal_state(tmp_path)

    result = aggregate_round_context(tmp_path, round_number=1)

    assert isinstance(result, dict)
    assert "schema_version" in result
    assert isinstance(result["schema_version"], int)
    assert "state" in result
    assert isinstance(result["state"], dict)
    assert "strategy" in result
    assert isinstance(result["strategy"], dict)
    assert "escalations" in result
    assert isinstance(result["escalations"], dict)
    assert "unresolved" in result["escalations"]
    assert "prior_resolutions_by_feature" in result["escalations"]
    assert "session_plan_text" in result
    assert isinstance(result["session_plan_text"], str)

    assert len(result) == 5, (
        f"Expected 5 top-level keys, got {len(result)}: {sorted(result.keys())}"
    )


# ---------------------------------------------------------------------------
# R4: strategy passthrough — no truncation
# ---------------------------------------------------------------------------

def test_strategy_passthrough_no_truncation(tmp_path: Path) -> None:
    """R4: strategy sub-object preserves all round_history_notes entries (no truncation)."""
    _write_minimal_state(tmp_path)

    notes = [f"round {i}: note" for i in range(10)]
    strategy = OvernightStrategy(round_history_notes=notes)
    save_strategy(strategy, tmp_path / "overnight-strategy.json")

    result = aggregate_round_context(tmp_path, round_number=1)

    assert len(result["strategy"]["round_history_notes"]) == 10, (
        f"Expected 10 round_history_notes, got {len(result['strategy']['round_history_notes'])}"
    )
    assert result["strategy"]["round_history_notes"] == notes


# ---------------------------------------------------------------------------
# R5: missing-file tolerance
# ---------------------------------------------------------------------------

def test_missing_files_use_per_source_defaults(tmp_path: Path) -> None:
    """R5: missing overnight-state.json raises FileNotFoundError; other absent files use defaults."""
    # No files at all — state is missing → must raise FileNotFoundError
    with pytest.raises(FileNotFoundError):
        aggregate_round_context(tmp_path, round_number=1)

    # Write only the state file; all others remain absent
    _write_minimal_state(tmp_path)

    result = aggregate_round_context(tmp_path, round_number=1)

    # strategy defaults
    default_strategy = dataclasses.asdict(OvernightStrategy())
    assert result["strategy"] == default_strategy

    # escalations defaults
    assert result["escalations"] == {"unresolved": [], "prior_resolutions_by_feature": {}}

    # session_plan_text defaults to empty string
    assert result["session_plan_text"] == ""


# ---------------------------------------------------------------------------
# R6: malformed escalations.jsonl line skipped with stderr WARNING
# ---------------------------------------------------------------------------

def test_malformed_jsonl_line_skipped_with_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """R6: malformed line is skipped, valid entries are present, stderr has WARNING."""
    _write_minimal_state(tmp_path)

    entry1 = {"type": "resolution", "escalation_id": "e1", "feature": "feat-a", "message": "first"}
    entry2 = {"type": "resolution", "escalation_id": "e2", "feature": "feat-a", "message": "second"}
    bad_line = "this is not valid json {"

    escalations_path = tmp_path / "escalations.jsonl"
    escalations_path.write_text(
        "\n".join([json.dumps(entry1), bad_line, json.dumps(entry2)]) + "\n",
        encoding="utf-8",
    )

    result = aggregate_round_context(tmp_path, round_number=1)

    prior = result["escalations"]["prior_resolutions_by_feature"]
    feat_entries = prior.get("feat-a", [])
    assert len(feat_entries) == 2, (
        f"Expected 2 valid resolution entries under feat-a, got {len(feat_entries)}: {feat_entries}"
    )
    assert feat_entries[0] == entry1
    assert feat_entries[1] == entry2

    # Malformed line must not appear
    for entry in feat_entries:
        assert "not valid json" not in str(entry)

    captured = capsys.readouterr()
    assert "WARNING" in captured.err, (
        f"Expected 'WARNING' in stderr, got: {captured.err!r}"
    )


# ---------------------------------------------------------------------------
# R8: schema-version drift raises RuntimeError
# ---------------------------------------------------------------------------

def test_schema_version_drift_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R8: RuntimeError('schema_version drift') raised when schema version mismatches."""
    _write_minimal_state(tmp_path)

    # Monkeypatch _EXPECTED_SCHEMA_VERSION to a value that won't match the literal 1
    # in the dict-construction site, triggering the drift guard.
    monkeypatch.setattr(_ctx_module, "_EXPECTED_SCHEMA_VERSION", 99)

    with pytest.raises(RuntimeError, match="schema_version drift"):
        aggregate_round_context(tmp_path, round_number=1)


# ---------------------------------------------------------------------------
# R10: contract fixture — pin top-level key set
# ---------------------------------------------------------------------------

def test_dict_top_level_keys_pinned(tmp_path: Path) -> None:
    """R10: top-level key set is exactly pinned; adding a new key without updating this test
    breaks the build, surfacing the schema-version-bump decision.
    """
    _write_minimal_state(tmp_path)

    result = aggregate_round_context(tmp_path, round_number=1)

    assert set(result.keys()) == {
        "schema_version",
        "state",
        "strategy",
        "escalations",
        "session_plan_text",
    }, (
        f"Top-level key set drift detected — update _EXPECTED_SCHEMA_VERSION and this "
        f"fixture if adding a new key. Got: {sorted(result.keys())}"
    )
