"""Unit tests for classify_conflict() in claude.pipeline.conflict.

Uses unittest.mock.patch to simulate git command outputs and file reads
so no real git operations are performed.
"""

from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from cortex_command.pipeline.conflict import ConflictClassification, classify_conflict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_run_result(stdout: str = "", returncode: int = 0) -> MagicMock:
    """Return a mock CompletedProcess-like object."""
    result = MagicMock()
    result.stdout = stdout
    result.returncode = returncode
    return result


# ---------------------------------------------------------------------------
# test_conflicted_files_detected
# ---------------------------------------------------------------------------

def test_conflicted_files_detected(tmp_path: Path) -> None:
    """Files listed by git diff with <<<<<<<< markers are in conflicted_files."""
    # Create the files with conflict markers so read_text() works
    (tmp_path / "foo.py").write_text("<<<<<<< HEAD\nfoo\n=======\nbar\n>>>>>>> branch\n")
    (tmp_path / "bar.py").write_text("<<<<<<< HEAD\nbaz\n=======\nqux\n>>>>>>> branch\n")

    diff_result = _make_run_result(stdout="foo.py\nbar.py\n")
    abort_result = _make_run_result()

    with patch("cortex_command.pipeline.conflict.subprocess.run", side_effect=[diff_result, abort_result]) as mock_run:
        result = classify_conflict(tmp_path)

    assert result.conflicted_files == ["foo.py", "bar.py"]
    assert "foo.py" in result.conflict_summary
    assert "bar.py" in result.conflict_summary


# ---------------------------------------------------------------------------
# test_no_marker_conflict
# ---------------------------------------------------------------------------

def test_no_marker_conflict(tmp_path: Path) -> None:
    """Binary files (UnicodeDecodeError on read) are excluded from conflicted_files."""
    diff_result = _make_run_result(stdout="binary.png\n")
    abort_result = _make_run_result()

    with patch("cortex_command.pipeline.conflict.subprocess.run", side_effect=[diff_result, abort_result]):
        with patch.object(Path, "read_text", side_effect=UnicodeDecodeError("utf-8", b"", 0, 1, "invalid")):
            result = classify_conflict(tmp_path)

    assert result.conflicted_files == []
    assert "binary" in result.conflict_summary


# ---------------------------------------------------------------------------
# test_abort_always_called
# ---------------------------------------------------------------------------

def test_abort_always_called(tmp_path: Path) -> None:
    """git merge --abort is called even when an exception occurs during classification."""
    abort_result = _make_run_result()

    with patch("cortex_command.pipeline.conflict.subprocess.run", side_effect=[RuntimeError("git exploded"), abort_result]) as mock_run:
        result = classify_conflict(tmp_path)

    # Confirm abort was called
    abort_calls = [c for c in mock_run.call_args_list if c.args[0] == ["git", "merge", "--abort"]]
    assert len(abort_calls) == 1, f"Expected git merge --abort to be called once, got: {mock_run.call_args_list}"


# ---------------------------------------------------------------------------
# test_classification_failed_result
# ---------------------------------------------------------------------------

def test_classification_failed_result(tmp_path: Path) -> None:
    """On any exception during classification, return conflicted_files=[] and summary='classification failed'."""
    abort_result = _make_run_result()

    with patch("cortex_command.pipeline.conflict.subprocess.run", side_effect=[RuntimeError("unexpected error"), abort_result]):
        result = classify_conflict(tmp_path)

    assert result.conflicted_files == []
    assert result.conflict_summary == "classification failed"
