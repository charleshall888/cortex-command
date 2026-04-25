"""Verification tests for Task 13 — ``MAX_TOOL_FILE_READ_BYTES`` cap (R14).

Three branches:

(i) **Oversized single line** — when one log line exceeds the cap, the
    handler returns ``oversized_line=True`` and an advancing
    ``next_cursor`` so the client paginates past it.
(ii) **Resume past the monster line** — passing the advancing cursor
    back returns lines that follow the monster line.
(iii) **Aggregate-cap normal pagination** — when no single line exceeds
    the cap but the aggregate would, the handler returns the lines that
    fit and a cursor pointing at the next unread line.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from cortex_command.mcp_server import tools
from cortex_command.mcp_server.schema import LogsInput, LogsOutput
from cortex_command.overnight import cli_handler


def _write_lines(session_dir: Path, lines: list[str]) -> None:
    """Write raw text lines to ``session_dir/overnight-events.log``."""
    session_dir.mkdir(parents=True, exist_ok=True)
    log_path = session_dir / "overnight-events.log"
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _event_line(seq: int, payload: str = "ok") -> str:
    """A small JSONL event line."""
    return json.dumps(
        {"ts": f"2026-04-24T22:00:{seq % 60:02d}+00:00", "n": seq, "msg": payload}
    )


def test_oversized_line_returns_flag_and_advancing_cursor(
    monkeypatch, tmp_path
) -> None:
    """A single line larger than the cap surfaces ``oversized_line=True``.

    The handler must also emit a ``next_cursor`` that advances past the
    monster line so the client can paginate forward without re-hitting
    the same line.
    """
    repo_path = tmp_path
    session_id = "overnight-oversized-line"
    session_dir = repo_path / "lifecycle" / "sessions" / session_id

    # Three lines: a tiny prefix, a monster, a tiny suffix. The monster's
    # length alone (5_000 bytes of payload + JSON envelope) busts the
    # 1_024-byte cap we install below.
    monster = json.dumps({"big": "X" * 5_000})
    lines = [_event_line(0, "before"), monster, _event_line(1, "after")]
    _write_lines(session_dir, lines)

    monkeypatch.setattr(
        cli_handler, "_resolve_repo_path", lambda: repo_path
    )
    # R14: the handler reads MAX_TOOL_FILE_READ_BYTES at module-import
    # time. Patch the in-process constant so a single 5 KB line trips
    # the oversized-line branch.
    monkeypatch.setattr(tools, "MAX_TOOL_FILE_READ_BYTES", 1_024)

    # Read from the start of the file with an offset cursor so we hit
    # the monster on the first call.
    result = asyncio.run(
        tools.overnight_logs(
            LogsInput(
                session_id=session_id,
                files=["events"],
                cursor="@0",
                limit=100,
            )
        )
    )

    assert isinstance(result, LogsOutput)
    assert result.oversized_line is True
    # next_cursor must advance — the client cannot resume from "@0".
    assert result.next_cursor is not None
    assert result.next_cursor != "@0"


def test_follow_up_cursor_returns_lines_after_monster(
    monkeypatch, tmp_path
) -> None:
    """Passing the advancing cursor back skips past the monster line."""
    repo_path = tmp_path
    session_id = "overnight-resume-after-monster"
    session_dir = repo_path / "lifecycle" / "sessions" / session_id

    monster = json.dumps({"big": "Y" * 5_000})
    lines = [_event_line(0, "before"), monster, _event_line(1, "after")]
    _write_lines(session_dir, lines)

    monkeypatch.setattr(
        cli_handler, "_resolve_repo_path", lambda: repo_path
    )
    monkeypatch.setattr(tools, "MAX_TOOL_FILE_READ_BYTES", 1_024)

    # Skip the small prefix line: start at byte-offset 0, take the
    # oversized-line branch, and capture the advancing cursor.
    first = asyncio.run(
        tools.overnight_logs(
            LogsInput(
                session_id=session_id,
                files=["events"],
                cursor="@0",
                limit=100,
            )
        )
    )
    assert first.oversized_line is True
    assert first.next_cursor is not None

    # Resume with the advancing cursor; the cap can stay tiny since the
    # remaining "after" line is small. We expect lines that come AFTER
    # the monster — the prefix "before" line was consumed in the first
    # call (the oversized-line branch breaks immediately on the monster,
    # so depending on read order we may or may not have captured the
    # before-line; the contract here is that the AFTER line is reachable).
    follow_up = asyncio.run(
        tools.overnight_logs(
            LogsInput(
                session_id=session_id,
                files=["events"],
                cursor=first.next_cursor,
                limit=100,
            )
        )
    )

    assert isinstance(follow_up, LogsOutput)
    # The "after" line is reachable post-resume.
    payloads = [line.get("msg") for line in follow_up.lines]
    assert "after" in payloads


def test_aggregate_cap_normal_pagination(monkeypatch, tmp_path) -> None:
    """Aggregate-cap path: lines that fit are returned, cursor advances."""
    repo_path = tmp_path
    session_id = "overnight-aggregate-cap"
    session_dir = repo_path / "lifecycle" / "sessions" / session_id

    # Twenty modest lines. Cap is just above one line's worth so the
    # aggregate budget kicks in after a small number of lines fit.
    lines = [_event_line(i, "ok") for i in range(20)]
    _write_lines(session_dir, lines)

    log_path = session_dir / "overnight-events.log"
    file_size = log_path.stat().st_size
    one_line_bytes = len(lines[0]) + 1  # +1 for the newline

    # Cap halfway through the file — we expect about half the lines
    # before the aggregate budget halts pagination.
    cap = file_size // 2
    assert cap > one_line_bytes  # sanity — cap admits at least one line.

    monkeypatch.setattr(
        cli_handler, "_resolve_repo_path", lambda: repo_path
    )
    monkeypatch.setattr(tools, "MAX_TOOL_FILE_READ_BYTES", cap)

    result = asyncio.run(
        tools.overnight_logs(
            LogsInput(
                session_id=session_id,
                files=["events"],
                cursor="@0",
                limit=100,
            )
        )
    )

    assert isinstance(result, LogsOutput)
    # Aggregate-cap path: oversized_line is NOT set (no single line
    # exceeded the cap), some lines came back, and next_cursor advances.
    assert result.oversized_line is None
    assert 0 < len(result.lines) < 20
    assert result.next_cursor is not None
    assert result.next_cursor != "@0"
    assert result.eof is False  # more to read

    # Resume: chain calls until EOF; the full 20 lines are reachable.
    accumulated = list(result.lines)
    cursor = result.next_cursor
    for _ in range(10):  # bounded loop — the cap admits ~half the file each call
        follow_up = asyncio.run(
            tools.overnight_logs(
                LogsInput(
                    session_id=session_id,
                    files=["events"],
                    cursor=cursor,
                    limit=100,
                )
            )
        )
        assert isinstance(follow_up, LogsOutput)
        accumulated.extend(follow_up.lines)
        if follow_up.eof:
            break
        cursor = follow_up.next_cursor

    # The chained run covers all 20 fixture lines, in order.
    assert len(accumulated) == 20
    assert [line["n"] for line in accumulated] == list(range(20))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
