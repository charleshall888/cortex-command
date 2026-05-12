#!/usr/bin/env python3
"""Phase-detector regression tests for the auto-progress lifecycle feature.

Covers R1 (cycle counter reads events.log, not review.md), R3 (approval-event
lookup with migration sentinel), and R4 (per-phase completion rule) by
constructing synthetic ``cortex/lifecycle/{feature}/`` fixtures and asserting that
``cortex_command.common.detect_lifecycle_phase`` returns the expected phase
and cycle.
"""

import json
from pathlib import Path

import pytest

from cortex_command.common import detect_lifecycle_phase


def _write_events(events_log: Path, events: list[dict]) -> None:
    """Write a list of event dicts as JSONL to ``events.log``."""
    events_log.write_text("\n".join(json.dumps(e) for e in events) + ("\n" if events else ""))


# ---------------------------------------------------------------------------
# Phase-routing fixtures
# ---------------------------------------------------------------------------


def test_happy_path_advances_to_complete(tmp_path: Path) -> None:
    """Full forward sequence with feature_complete → phase=complete."""
    fdir = tmp_path / "feature"
    fdir.mkdir()
    (fdir / "research.md").write_text("research")
    (fdir / "spec.md").write_text("spec")
    (fdir / "plan.md").write_text("- **Status**: [x]\n")
    (fdir / "review.md").write_text('{"verdict": "APPROVED"}')
    _write_events(
        fdir / "events.log",
        [
            {"event": "phase_transition", "from": "clarify", "to": "research"},
            {"event": "phase_transition", "from": "research", "to": "specify"},
            {"event": "spec_approved", "feature": "f"},
            {"event": "phase_transition", "from": "specify", "to": "plan"},
            {"event": "plan_approved", "feature": "f"},
            {"event": "phase_transition", "from": "plan", "to": "implement"},
            {"event": "phase_transition", "from": "implement", "to": "review"},
            {"event": "review_verdict", "verdict": "APPROVED", "cycle": 1},
            {"event": "phase_transition", "from": "review", "to": "complete"},
            {"event": "feature_complete", "feature": "f"},
        ],
    )
    result = detect_lifecycle_phase(fdir)
    assert result["phase"] == "complete"


def test_specify_blocks_without_approval(tmp_path: Path) -> None:
    """spec.md present, no spec_approved event, no transition → phase=specify."""
    fdir = tmp_path / "feature"
    fdir.mkdir()
    (fdir / "spec.md").write_text("spec body")
    (fdir / "events.log").write_text("")
    result = detect_lifecycle_phase(fdir)
    assert result["phase"] == "specify"


def test_spec_approval_unlocks_plan(tmp_path: Path) -> None:
    """spec.md + spec_approved event → phase=plan."""
    fdir = tmp_path / "feature"
    fdir.mkdir()
    (fdir / "spec.md").write_text("spec body")
    _write_events(
        fdir / "events.log",
        [{"event": "spec_approved", "feature": "f"}],
    )
    result = detect_lifecycle_phase(fdir)
    assert result["phase"] == "plan"


def test_migration_sentinel_unlocks_in_flight_spec(tmp_path: Path) -> None:
    """spec.md, no spec_approved event, but phase_transition from=specify → phase=plan."""
    fdir = tmp_path / "feature"
    fdir.mkdir()
    (fdir / "spec.md").write_text("spec body")
    _write_events(
        fdir / "events.log",
        [{"event": "phase_transition", "from": "specify", "to": "plan"}],
    )
    result = detect_lifecycle_phase(fdir)
    assert result["phase"] == "plan"


def test_plan_blocks_without_approval(tmp_path: Path) -> None:
    """plan.md present, no plan_approved event, no transition out → phase=plan."""
    fdir = tmp_path / "feature"
    fdir.mkdir()
    (fdir / "spec.md").write_text("spec body")
    (fdir / "plan.md").write_text("- **Status**: [ ]\n")
    # Spec is approved (otherwise we'd be in specify), but plan is not.
    _write_events(
        fdir / "events.log",
        [{"event": "spec_approved", "feature": "f"}],
    )
    result = detect_lifecycle_phase(fdir)
    assert result["phase"] == "plan"


def test_plan_migration_sentinel_unlocks_in_flight(tmp_path: Path) -> None:
    """plan.md, no plan_approved event, but phase_transition from=plan → phase=implement."""
    fdir = tmp_path / "feature"
    fdir.mkdir()
    (fdir / "spec.md").write_text("spec body")
    (fdir / "plan.md").write_text("- **Status**: [ ]\n- **Status**: [x]\n")
    _write_events(
        fdir / "events.log",
        [
            {"event": "spec_approved", "feature": "f"},
            {"event": "phase_transition", "from": "specify", "to": "plan"},
            {"event": "phase_transition", "from": "plan", "to": "implement"},
        ],
    )
    result = detect_lifecycle_phase(fdir)
    # Some tasks still unchecked → implement, not review.
    assert result["phase"] == "implement"


def test_cycle_2_changes_requested_escalates(tmp_path: Path) -> None:
    """Two review_verdict events with CHANGES_REQUESTED → cycle 2, phase=implement-rework."""
    fdir = tmp_path / "feature"
    fdir.mkdir()
    (fdir / "spec.md").write_text("spec body")
    (fdir / "plan.md").write_text("- **Status**: [x]\n")
    (fdir / "review.md").write_text('{"verdict": "CHANGES_REQUESTED"}')
    _write_events(
        fdir / "events.log",
        [
            {"event": "spec_approved", "feature": "f"},
            {"event": "plan_approved", "feature": "f"},
            {"event": "review_verdict", "verdict": "CHANGES_REQUESTED", "cycle": 1},
            {"event": "review_verdict", "verdict": "CHANGES_REQUESTED", "cycle": 2},
        ],
    )
    result = detect_lifecycle_phase(fdir)
    assert result["cycle"] == 2
    # review.md verdict drives the phase routing; CHANGES_REQUESTED → implement-rework.
    assert result["phase"] == "implement-rework"


def test_cycle_counter_ignores_review_md(tmp_path: Path) -> None:
    """Empty events.log + two verdict strings in review.md → cycle=1.

    The pre-fix regex-counter would have returned cycle=2 by counting the two
    "verdict" matches in review.md. The fix sources cycle exclusively from
    events.log, so an empty log yields cycle=1.
    """
    fdir = tmp_path / "feature"
    fdir.mkdir()
    (fdir / "spec.md").write_text("spec body")
    (fdir / "plan.md").write_text("- **Status**: [x]\n")
    (fdir / "review.md").write_text(
        '{"verdict": "APPROVED"}\n{"verdict": "APPROVED"}'
    )
    (fdir / "events.log").write_text("")
    result = detect_lifecycle_phase(fdir)
    assert result["cycle"] == 1
