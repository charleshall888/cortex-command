"""Verification tests for Task 13 — ``overnight_logs`` MCP tool.

Covers R5/R10/R11/R14:

* a 100-line page's serialized JSON byte-length stays within a coarse
  smoke budget (≤ 30 000 chars, ~10 000 tokens at 3 chars/token);
* the opaque cursor a client receives round-trips back through
  :func:`cortex_command.overnight.cursor.decode` (server sees the
  decoded ``{offset, file_size_at_emit}`` shape, clients only ever see
  the opaque base64-JSON string);
* a missing ``session_id`` raises a :class:`mcp.server.fastmcp.exceptions.ToolError`
  whose body is JSON with ``{error: "session_not_found", session_id: ...}``
  per MCP SEP-1303.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from cortex_command.mcp_server import tools
from cortex_command.mcp_server.schema import LogsInput, LogsOutput
from cortex_command.overnight import cli_handler
from cortex_command.overnight import cursor as cursor_codec


def _write_events_log(session_dir: Path, lines: list[dict]) -> None:
    """Write JSONL events under ``session_dir/overnight-events.log``."""
    session_dir.mkdir(parents=True, exist_ok=True)
    log_path = session_dir / "overnight-events.log"
    log_path.write_text(
        "\n".join(json.dumps(line) for line in lines) + "\n",
        encoding="utf-8",
    )


def _make_event(seq: int) -> dict:
    """A representative compact event line for the budget smoke test."""
    return {
        "ts": f"2026-04-24T22:00:{seq % 60:02d}+00:00",
        "kind": "feature_event",
        "feature": f"feat-{seq:03d}",
        "round": (seq % 5) + 1,
        "msg": "feature progressed",
    }


def test_logs_100_line_page_within_budget(monkeypatch, tmp_path) -> None:
    """A 100-line page serializes within the 30 000-char smoke budget."""
    repo_path = tmp_path
    session_id = "overnight-2026-04-24-budget"
    session_dir = repo_path / "lifecycle" / "sessions" / session_id

    # 200 events on disk so the tail-mode read can return a full page of
    # 100 without running out of fixture content.
    _write_events_log(session_dir, [_make_event(i) for i in range(200)])

    monkeypatch.setattr(
        cli_handler, "_resolve_repo_path", lambda: repo_path
    )

    result = asyncio.run(
        tools.overnight_logs(
            LogsInput(session_id=session_id, files=["events"], limit=100)
        )
    )

    assert isinstance(result, LogsOutput)
    # tail-mode default reads last 20 lines; force a 100-line read by
    # passing tail=100 so the budget check is meaningful.
    result_full = asyncio.run(
        tools.overnight_logs(
            LogsInput(
                session_id=session_id,
                files=["events"],
                limit=100,
                tail=100,
            )
        )
    )
    assert len(result_full.lines) == 100
    payload = result_full.model_dump_json()
    assert len(payload) <= 30_000, (
        f"100-line logs page byte-length {len(payload)} exceeds "
        f"30 000-char smoke budget"
    )


def test_logs_cursor_round_trips_through_decode(
    monkeypatch, tmp_path
) -> None:
    """The opaque ``next_cursor`` decodes to ``{offset, file_size_at_emit}``.

    The server sees the structured form via the codec; clients only see
    the opaque base64-JSON string and pass it back unmodified (R23).
    """
    repo_path = tmp_path
    session_id = "overnight-2026-04-24-cursor"
    session_dir = repo_path / "lifecycle" / "sessions" / session_id
    _write_events_log(session_dir, [_make_event(i) for i in range(10)])

    monkeypatch.setattr(
        cli_handler, "_resolve_repo_path", lambda: repo_path
    )

    result = asyncio.run(
        tools.overnight_logs(
            LogsInput(
                session_id=session_id, files=["events"], limit=100, tail=10
            )
        )
    )

    assert isinstance(result, LogsOutput)
    assert result.next_cursor is not None

    # Server-internal: decode the opaque token to confirm the structured
    # shape. Clients never do this — they pass the string back verbatim.
    decoded = cursor_codec.decode(result.next_cursor)
    assert isinstance(decoded["offset"], int)
    assert isinstance(decoded["file_size_at_emit"], int)
    assert decoded["offset"] >= 0
    assert decoded["file_size_at_emit"] >= 0

    # Round-trip: passing the opaque token back yields a valid (possibly
    # empty, since we tailed the whole file) read with no cursor_invalid.
    follow_up = asyncio.run(
        tools.overnight_logs(
            LogsInput(
                session_id=session_id,
                files=["events"],
                cursor=result.next_cursor,
                limit=100,
            )
        )
    )
    assert isinstance(follow_up, LogsOutput)
    assert follow_up.cursor_invalid is None


def test_logs_session_not_found_raises_tool_error(
    monkeypatch, tmp_path
) -> None:
    """Missing session_id → ToolError with JSON body per MCP SEP-1303."""
    repo_path = tmp_path
    (repo_path / "lifecycle" / "sessions").mkdir(parents=True)

    monkeypatch.setattr(
        cli_handler, "_resolve_repo_path", lambda: repo_path
    )

    missing_id = "overnight-does-not-exist"

    with pytest.raises(ToolError) as excinfo:
        asyncio.run(
            tools.overnight_logs(
                LogsInput(session_id=missing_id, files=["events"])
            )
        )

    # Body must be JSON-encoded ``{error, session_id}`` so MCP clients
    # receive isError:true with a structured payload.
    body = json.loads(str(excinfo.value))
    assert body == {
        "error": "session_not_found",
        "session_id": missing_id,
    }


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
