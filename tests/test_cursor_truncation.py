"""Cursor-invalid + oversized-line tests for read_log_structured (R11, R14 prep).

R11 acceptance: ``read_log`` returns ``{cursor_invalid: true, current_size,
next_cursor: null}`` when the cursor's ``file_size_at_emit > current_size``
(i.e. the log file shrank between an emit and a re-read). R14 prep: the
oversized-line path is tested here even though the MAX_TOOL_FILE_READ_BYTES
constant proper lives in ``tools.py`` (Task 13) — ``read_log_structured``
honors the ``max_bytes`` parameter directly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cortex_command.overnight import cursor as cursor_codec
from cortex_command.overnight import logs as logs_module


def _write(path: Path, *lines: str) -> None:
    """Write a sequence of lines (each terminated with '\\n') to ``path``."""
    path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")


def test_shrunk_file_returns_cursor_invalid(tmp_path: Path) -> None:
    """File shrank below the cursor's file_size_at_emit → cursor_invalid+null."""
    log = tmp_path / "events.log"
    _write(log, "alpha", "beta", "gamma")
    initial_size = log.stat().st_size

    # Emit a cursor pretending we've read up to byte 5 when the file was
    # `initial_size` bytes large.
    stale_cursor = cursor_codec.encode(offset=5, file_size_at_emit=initial_size)

    # Truncate the file (e.g. operator rotated the log).
    log.write_text("a\n", encoding="utf-8")
    assert log.stat().st_size < initial_size

    result = logs_module.read_log_structured(
        log_path=log,
        cursor=stale_cursor,
        tail=None,
        limit=100,
    )

    # Per R11: cursor_invalid: True AND next_cursor: None AND empty lines.
    assert result["cursor_invalid"] is True
    assert result["next_cursor"] is None
    assert result["lines"] == []
    assert result["eof"] is False
    assert result["current_size"] == log.stat().st_size


def test_unshrunk_file_does_not_signal_cursor_invalid(tmp_path: Path) -> None:
    """When the file has only grown (or stayed the same) since emit, the
    read proceeds normally and cursor_invalid is False."""
    log = tmp_path / "events.log"
    _write(log, "alpha", "beta")
    size_at_emit = log.stat().st_size
    cursor = cursor_codec.encode(offset=0, file_size_at_emit=size_at_emit)

    # File grows.
    with log.open("a", encoding="utf-8") as f:
        f.write("gamma\n")

    result = logs_module.read_log_structured(
        log_path=log, cursor=cursor, tail=None, limit=100
    )
    assert result["cursor_invalid"] is False
    assert result["next_cursor"] is not None
    assert result["lines"] == ["alpha", "beta", "gamma"]
    assert result["eof"] is True


def test_legacy_byte_offset_cursor_still_works(tmp_path: Path) -> None:
    """Backwards compat: ``@<int>`` cursors are accepted by the structured
    reader as well, returning a structured dict (used by callers that want
    truncation signaling on top of the legacy form)."""
    log = tmp_path / "events.log"
    _write(log, "first", "second", "third")

    result = logs_module.read_log_structured(
        log_path=log, cursor="@0", tail=None, limit=2
    )
    assert result["lines"] == ["first", "second"]
    assert result["cursor_invalid"] is False
    assert result["next_cursor"] is not None
    # The new cursor is opaque (base64-JSON), not @<int>.
    decoded = cursor_codec.decode(result["next_cursor"])
    assert decoded["offset"] == len("first\nsecond\n")


def test_invalid_cursor_raises(tmp_path: Path) -> None:
    """Garbage in the cursor slot → ValueError('invalid cursor')."""
    log = tmp_path / "events.log"
    _write(log, "x")

    with pytest.raises(ValueError, match="invalid cursor"):
        logs_module.read_log_structured(
            log_path=log, cursor="!!!nope!!!", tail=None, limit=10
        )


def test_oversized_single_line_truncates_with_advancing_cursor(
    tmp_path: Path,
) -> None:
    """A single line larger than max_bytes is truncated with a sentinel; the
    next_cursor advances past the line's terminating newline so the client
    paginates past the monster line on the next call."""
    log = tmp_path / "events.log"
    monster = "x" * 5000
    log.write_text(f"{monster}\nshort-after\n", encoding="utf-8")

    result = logs_module.read_log_structured(
        log_path=log,
        cursor=cursor_codec.encode(0, log.stat().st_size),
        tail=None,
        limit=100,
        max_bytes=1000,  # < 5000 → triggers oversized-line path
    )

    assert result["oversized_line"] is True
    assert result["original_line_bytes"] == len(monster) + 1  # +1 for "\n"
    assert len(result["lines"]) == 1
    assert "...(line truncated, original" in result["lines"][0]
    assert result["cursor_invalid"] is False

    # next_cursor advances past the monster line's trailing newline.
    decoded = cursor_codec.decode(result["next_cursor"])
    assert decoded["offset"] == len(monster) + 1

    # Paginating with the returned cursor returns the line *after* the
    # monster, proving the client can't get stuck.
    follow = logs_module.read_log_structured(
        log_path=log,
        cursor=result["next_cursor"],
        tail=None,
        limit=100,
        max_bytes=1000,
    )
    assert follow["lines"] == ["short-after"]
    assert follow.get("oversized_line") is None or follow["oversized_line"] is False


def test_aggregate_byte_budget_paginates_normally(tmp_path: Path) -> None:
    """When normal-sized lines aggregate past max_bytes, the standard
    pagination cursor lets the client resume — no oversized_line flag."""
    log = tmp_path / "events.log"
    # Five lines of ~100 bytes each (~500 bytes total); cap at 250 should
    # return ~two lines and a cursor pointing into the middle.
    line = "y" * 99  # 99 + "\n" = 100 bytes
    log.write_text("\n".join([line] * 5) + "\n", encoding="utf-8")

    result = logs_module.read_log_structured(
        log_path=log, cursor="@0", tail=None, limit=100, max_bytes=250
    )

    # No oversized_line flag: aggregate path uses the normal pagination
    # contract per spec R14.
    assert result.get("oversized_line") is None or not result["oversized_line"]
    assert result["cursor_invalid"] is False
    # Two lines fit within 250 bytes (200 < 250 < 300).
    assert len(result["lines"]) == 2

    # Resume from the returned cursor — should pick up the remaining lines.
    follow = logs_module.read_log_structured(
        log_path=log,
        cursor=result["next_cursor"],
        tail=None,
        limit=100,
        max_bytes=250,
    )
    assert len(follow["lines"]) == 2  # next two of the same


def test_missing_log_file_returns_empty_eof(tmp_path: Path) -> None:
    """A non-existent log file returns a well-formed empty result."""
    log = tmp_path / "does-not-exist.log"
    result = logs_module.read_log_structured(
        log_path=log, cursor=None, tail=20, limit=100
    )
    assert result["lines"] == []
    assert result["eof"] is True
    assert result["cursor_invalid"] is False
    assert result["next_cursor"] is None
    assert result["current_size"] == 0


def test_past_eof_cursor_returns_eof_true(tmp_path: Path) -> None:
    """A cursor whose offset >= current_size (but file_size_at_emit ==
    current_size, i.e. no shrink) returns empty lines, eof=True, and a
    fresh cursor pinned to current_size for the next-poll write."""
    log = tmp_path / "events.log"
    _write(log, "a", "b")
    size = log.stat().st_size
    cursor = cursor_codec.encode(offset=size, file_size_at_emit=size)

    result = logs_module.read_log_structured(
        log_path=log, cursor=cursor, tail=None, limit=100
    )
    assert result["lines"] == []
    assert result["eof"] is True
    assert result["cursor_invalid"] is False
    decoded = cursor_codec.decode(result["next_cursor"])
    assert decoded["offset"] == size
