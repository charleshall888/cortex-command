"""Tests for read_dispatch_choice — the Plan→Implement carry-forward resolver.

Covers the line-position-last contract and the three "no recorded branch mode"
fallback shapes the Implement consumer must treat as picker-fallback.
"""

from __future__ import annotations

from pathlib import Path

from cortex_command.lifecycle_implement import read_dispatch_choice


def _write(path: Path, *lines: str) -> Path:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_single_plan_approved_returns_value(tmp_path: Path) -> None:
    log = _write(
        tmp_path / "events.log",
        '{"event": "lifecycle_start", "feature": "f"}',
        '{"event": "plan_approved", "feature": "f", "dispatch_choice": "worktree-interactive"}',
    )
    assert read_dispatch_choice(log) == "worktree-interactive"


def test_two_plan_approved_returns_line_position_last(tmp_path: Path) -> None:
    # Rework cycle: an earlier plan_approved is superseded by a later one.
    log = _write(
        tmp_path / "events.log",
        '{"event": "plan_approved", "feature": "f", "dispatch_choice": "trunk"}',
        '{"event": "phase_transition", "from": "review", "to": "implement-rework"}',
        '{"event": "plan_approved", "feature": "f", "dispatch_choice": "feature-branch"}',
    )
    assert read_dispatch_choice(log) == "feature-branch"


def test_plan_approved_without_field_returns_none(tmp_path: Path) -> None:
    log = _write(
        tmp_path / "events.log",
        '{"event": "plan_approved", "feature": "f"}',
    )
    assert read_dispatch_choice(log) is None


def test_later_fieldless_supersedes_earlier_choice(tmp_path: Path) -> None:
    # The latest plan_approved carries no field — it must reset to None, not
    # leak the earlier recorded choice.
    log = _write(
        tmp_path / "events.log",
        '{"event": "plan_approved", "feature": "f", "dispatch_choice": "trunk"}',
        '{"event": "plan_approved", "feature": "f"}',
    )
    assert read_dispatch_choice(log) is None


def test_no_plan_approved_returns_none(tmp_path: Path) -> None:
    # Migration-sentinel / legacy log: reached implement via phase_transition.
    log = _write(
        tmp_path / "events.log",
        '{"event": "lifecycle_start", "feature": "f"}',
        '{"event": "phase_transition", "from": "plan", "to": "implement"}',
    )
    assert read_dispatch_choice(log) is None


def test_wait_value_returned_verbatim(tmp_path: Path) -> None:
    log = _write(
        tmp_path / "events.log",
        '{"event": "plan_approved", "feature": "f", "dispatch_choice": "wait"}',
    )
    assert read_dispatch_choice(log) == "wait"


def test_missing_file_returns_none(tmp_path: Path) -> None:
    assert read_dispatch_choice(tmp_path / "absent.log") is None


def test_torn_line_skipped_not_collapsed(tmp_path: Path) -> None:
    log = _write(
        tmp_path / "events.log",
        "{not valid json",
        '{"event": "plan_approved", "feature": "f", "dispatch_choice": "trunk"}',
    )
    assert read_dispatch_choice(log) == "trunk"
