"""Unit tests for write_recovery_log_entry() in claude.pipeline.merge_recovery.

Uses tmp_path fixture for isolated filesystem — no git operations, no SDK calls.
"""

from pathlib import Path

import pytest

from claude.pipeline.merge_recovery import write_recovery_log_entry


# ---------------------------------------------------------------------------
# test_first_entry_format
# ---------------------------------------------------------------------------

def test_first_entry_format(tmp_path: Path) -> None:
    """First entry is N=1 and contains all required fields."""
    log_path = tmp_path / "recovery-log.md"
    write_recovery_log_entry(
        feature="my-feature",
        recovery_type="test_failure",
        outcome="paused",
        what_was_tried="the agent tried X",
        result="tests still failing: AssertionError",
        _log_path=log_path,
    )
    content = log_path.read_text(encoding="utf-8")
    assert "## Recovery attempt 1 —" in content
    assert "Type: test_failure" in content
    assert "Outcome: paused" in content
    assert "What was tried: the agent tried X" in content
    assert "Result: tests still failing: AssertionError" in content


# ---------------------------------------------------------------------------
# test_n_increments_on_second_entry
# ---------------------------------------------------------------------------

def test_n_increments_on_second_entry(tmp_path: Path) -> None:
    """N increments to 2 when a second entry is appended."""
    log_path = tmp_path / "recovery-log.md"
    write_recovery_log_entry(
        feature="feat",
        recovery_type="merge_conflict",
        outcome="failed",
        what_was_tried="sonnet repair",
        result="markers remain",
        _log_path=log_path,
    )
    write_recovery_log_entry(
        feature="feat",
        recovery_type="merge_conflict",
        outcome="paused",
        what_was_tried="opus repair",
        result="still failing",
        _log_path=log_path,
    )
    content = log_path.read_text(encoding="utf-8")
    assert "## Recovery attempt 1 —" in content
    assert "## Recovery attempt 2 —" in content
    assert content.count("## Recovery attempt") == 2


# ---------------------------------------------------------------------------
# test_missing_directory_created
# ---------------------------------------------------------------------------

def test_missing_directory_created(tmp_path: Path) -> None:
    """Parent directory is created when it does not exist."""
    log_path = tmp_path / "nested" / "dirs" / "recovery-log.md"
    assert not log_path.parent.exists()
    write_recovery_log_entry(
        feature="feat",
        recovery_type="trivial_conflict",
        outcome="success",
        what_was_tried="git checkout --theirs",
        result="resolved: foo.py",
        _log_path=log_path,
    )
    assert log_path.exists()


# ---------------------------------------------------------------------------
# test_empty_file_produces_n_equals_one
# ---------------------------------------------------------------------------

def test_empty_file_produces_n_equals_one(tmp_path: Path) -> None:
    """An existing but empty file produces N=1."""
    log_path = tmp_path / "recovery-log.md"
    log_path.write_text("", encoding="utf-8")
    write_recovery_log_entry(
        feature="feat",
        recovery_type="test_failure",
        outcome="success",
        what_was_tried="flaky guard re-merge",
        result="tests passed",
        _log_path=log_path,
    )
    content = log_path.read_text(encoding="utf-8")
    assert "## Recovery attempt 1 —" in content


# ---------------------------------------------------------------------------
# test_what_was_tried_preserved_verbatim
# ---------------------------------------------------------------------------

def test_what_was_tried_preserved_verbatim(tmp_path: Path) -> None:
    """what_was_tried content is written exactly as provided."""
    log_path = tmp_path / "recovery-log.md"
    long_text = "agent output: " + "x" * 200
    write_recovery_log_entry(
        feature="feat",
        recovery_type="test_failure",
        outcome="failed",
        what_was_tried=long_text,
        result="error",
        _log_path=log_path,
    )
    content = log_path.read_text(encoding="utf-8")
    assert long_text in content
