"""Unit tests for cortex_command.lifecycle.counters.count_rework_cycles.

The counter is re-sourced (defect 4) to count ``review_verdict`` events with
``verdict == "CHANGES_REQUESTED"`` in a feature's ``events.log``, replacing the
old ``review.md`` verdict-block regex. These tests own counter correctness with
hardcoded ground-truth expectations:

- no events.log                                      -> 0
- one APPROVED review_verdict (cycle 1)              -> 0
- one CHANGES_REQUESTED then APPROVED                -> 1
- two CHANGES_REQUESTED then APPROVED                -> 2
- a malformed (non-JSON) line plus one CHANGES_REQUESTED -> 1 (line skipped)
"""

from __future__ import annotations

import json
from pathlib import Path

from cortex_command.lifecycle.counters import count_rework_cycles


def _write_events_log(tmp_path: Path, *events: object) -> Path:
    """Write one JSON object per line to events.log, return its path.

    A raw ``str`` event is written verbatim (used to inject malformed lines);
    any other object is serialized with ``json.dumps``.
    """
    feature_dir = tmp_path / "feat"
    feature_dir.mkdir(parents=True, exist_ok=True)
    events_log = feature_dir / "events.log"
    lines = [
        ev if isinstance(ev, str) else json.dumps(ev) for ev in events
    ]
    events_log.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return events_log


def test_no_events_log_returns_zero(tmp_path: Path) -> None:
    """A missing events.log yields 0 rework cycles."""
    missing = tmp_path / "feat" / "events.log"
    assert count_rework_cycles(missing) == 0


def test_empty_events_log_returns_zero(tmp_path: Path) -> None:
    """An empty events.log yields 0 rework cycles."""
    events_log = _write_events_log(tmp_path)
    assert count_rework_cycles(events_log) == 0


def test_single_approved_returns_zero(tmp_path: Path) -> None:
    """One APPROVED review_verdict (cycle 1) is not rework -> 0."""
    events_log = _write_events_log(
        tmp_path,
        {"event": "lifecycle_start", "feature": "feat"},
        {"event": "review_verdict", "verdict": "APPROVED", "cycle": 1},
    )
    assert count_rework_cycles(events_log) == 0


def test_one_changes_requested_then_approved_returns_one(tmp_path: Path) -> None:
    """One CHANGES_REQUESTED then APPROVED -> 1 rework cycle."""
    events_log = _write_events_log(
        tmp_path,
        {"event": "review_verdict", "verdict": "CHANGES_REQUESTED", "cycle": 1},
        {"event": "review_verdict", "verdict": "APPROVED", "cycle": 2},
    )
    assert count_rework_cycles(events_log) == 1


def test_two_changes_requested_then_approved_returns_two(tmp_path: Path) -> None:
    """Two CHANGES_REQUESTED then APPROVED -> 2 rework cycles."""
    events_log = _write_events_log(
        tmp_path,
        {"event": "review_verdict", "verdict": "CHANGES_REQUESTED", "cycle": 1},
        {"event": "review_verdict", "verdict": "CHANGES_REQUESTED", "cycle": 2},
        {"event": "review_verdict", "verdict": "APPROVED", "cycle": 3},
    )
    assert count_rework_cycles(events_log) == 2


def test_malformed_line_is_skipped(tmp_path: Path) -> None:
    """A malformed (non-JSON) line is skipped, not raised on -> 1."""
    events_log = _write_events_log(
        tmp_path,
        {"event": "lifecycle_start", "feature": "feat"},
        "MALFORMED LINE NOT JSON {{{",
        {"event": "review_verdict", "verdict": "CHANGES_REQUESTED", "cycle": 1},
    )
    assert count_rework_cycles(events_log) == 1


def test_synthetic_approved_cycle_zero_not_counted(tmp_path: Path) -> None:
    """A synthetic APPROVED review_verdict with cycle 0 is not rework -> 0."""
    events_log = _write_events_log(
        tmp_path,
        {"event": "review_verdict", "verdict": "APPROVED", "cycle": 0},
    )
    assert count_rework_cycles(events_log) == 0


def test_rejected_verdict_not_counted(tmp_path: Path) -> None:
    """REJECTED is not CHANGES_REQUESTED -> not counted as rework."""
    events_log = _write_events_log(
        tmp_path,
        {"event": "review_verdict", "verdict": "REJECTED", "cycle": 1},
    )
    assert count_rework_cycles(events_log) == 0
