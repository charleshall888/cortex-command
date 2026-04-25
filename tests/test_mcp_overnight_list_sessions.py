"""Verification tests for Task 12 — ``overnight_list_sessions`` MCP tool.

Covers R7: the tool globs
``lifecycle/sessions/*/overnight-state.json``, partitions by phase into
``active`` / ``recent``, applies optional ``status`` / ``since`` /
``limit`` filters, and returns a response whose default shape stays
within the 4 000-token budget (~12 000-char coarse proxy at 3 chars /
token) even when 50 fixture sessions are present on disk.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from cortex_command.mcp_server import tools
from cortex_command.mcp_server.schema import (
    ListSessionsInput,
    ListSessionsOutput,
)
from cortex_command.overnight import cli_handler


def _write_session(
    sessions_root: Path,
    session_id: str,
    phase: str,
    updated_at: str,
) -> None:
    """Write a minimal overnight-state.json for a fixture session."""
    session_dir = sessions_root / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "session_id": session_id,
        "plan_ref": f"lifecycle/sessions/{session_id}/overnight-plan.md",
        "plan_hash": "a" * 64,
        "current_round": 1,
        "phase": phase,
        "started_at": updated_at,
        "updated_at": updated_at,
        "integration_branch": f"integration/{session_id}",
        "features": {},
        "round_history": [],
    }
    (session_dir / "overnight-state.json").write_text(
        json.dumps(data), encoding="utf-8"
    )


def _seed_50_sessions(sessions_root: Path) -> None:
    """Create 50 fixture sessions — 1 executing, rest complete."""
    base = datetime(2026, 4, 1, 22, 0, tzinfo=timezone.utc)
    for i in range(50):
        session_id = f"overnight-2026-04-{i:02d}-2200"
        phase = "executing" if i == 0 else "complete"
        updated = (base + timedelta(hours=i)).isoformat()
        _write_session(sessions_root, session_id, phase, updated)


def test_list_sessions_default_shape_within_budget(monkeypatch) -> None:
    """R7: 50 fixture sessions → default response ≤ 12 000 chars."""
    with tempfile.TemporaryDirectory() as tmp:
        repo_path = Path(tmp)
        sessions_root = repo_path / "lifecycle" / "sessions"
        sessions_root.mkdir(parents=True)
        _seed_50_sessions(sessions_root)

        monkeypatch.setattr(
            cli_handler, "_resolve_repo_path", lambda: repo_path
        )

        result = asyncio.run(
            tools.overnight_list_sessions(ListSessionsInput())
        )

        assert isinstance(result, ListSessionsOutput)
        # One executing session + 49 complete; default limit=10 on recent.
        assert len(result.active) == 1
        assert len(result.recent) == 10
        assert result.total_count == 50
        assert result.next_cursor is None

        payload = result.model_dump_json()
        # Coarse smoke check per R7 — 4 000-token budget proxied at
        # 3 chars/token → 12 000 chars.
        assert len(payload) <= 12_000, (
            f"list_sessions default response {len(payload)} chars "
            f"exceeds 12 000-char budget"
        )


def test_list_sessions_empty_repo_returns_empty_shape(
    monkeypatch, tmp_path
) -> None:
    """A fresh repo with no sessions returns zero-length lists."""
    monkeypatch.setattr(
        cli_handler, "_resolve_repo_path", lambda: tmp_path
    )

    result = asyncio.run(
        tools.overnight_list_sessions(ListSessionsInput())
    )

    assert result.active == []
    assert result.recent == []
    assert result.total_count == 0
    assert result.next_cursor is None


def test_list_sessions_status_filter(monkeypatch) -> None:
    """``status=["complete"]`` excludes active sessions."""
    with tempfile.TemporaryDirectory() as tmp:
        repo_path = Path(tmp)
        sessions_root = repo_path / "lifecycle" / "sessions"
        sessions_root.mkdir(parents=True)
        _write_session(
            sessions_root, "s-exec", "executing",
            "2026-04-24T22:00:00+00:00",
        )
        _write_session(
            sessions_root, "s-done-1", "complete",
            "2026-04-23T22:00:00+00:00",
        )
        _write_session(
            sessions_root, "s-done-2", "complete",
            "2026-04-22T22:00:00+00:00",
        )

        monkeypatch.setattr(
            cli_handler, "_resolve_repo_path", lambda: repo_path
        )

        result = asyncio.run(
            tools.overnight_list_sessions(
                ListSessionsInput(status=["complete"])
            )
        )

        # Only complete sessions included.
        assert result.active == []
        assert {s.session_id for s in result.recent} == {
            "s-done-1",
            "s-done-2",
        }


def test_list_sessions_since_filter(monkeypatch) -> None:
    """``since`` excludes sessions older than the cutoff."""
    with tempfile.TemporaryDirectory() as tmp:
        repo_path = Path(tmp)
        sessions_root = repo_path / "lifecycle" / "sessions"
        sessions_root.mkdir(parents=True)
        _write_session(
            sessions_root, "s-old", "complete",
            "2026-04-01T00:00:00+00:00",
        )
        _write_session(
            sessions_root, "s-new", "complete",
            "2026-04-24T00:00:00+00:00",
        )

        monkeypatch.setattr(
            cli_handler, "_resolve_repo_path", lambda: repo_path
        )

        result = asyncio.run(
            tools.overnight_list_sessions(
                ListSessionsInput(since="2026-04-15T00:00:00+00:00")
            )
        )

        assert [s.session_id for s in result.recent] == ["s-new"]


def test_list_sessions_limit_caps_recent(monkeypatch) -> None:
    """``limit`` caps the ``recent`` slice but leaves ``total_count`` full."""
    with tempfile.TemporaryDirectory() as tmp:
        repo_path = Path(tmp)
        sessions_root = repo_path / "lifecycle" / "sessions"
        sessions_root.mkdir(parents=True)
        _seed_50_sessions(sessions_root)

        monkeypatch.setattr(
            cli_handler, "_resolve_repo_path", lambda: repo_path
        )

        result = asyncio.run(
            tools.overnight_list_sessions(ListSessionsInput(limit=3))
        )

        assert len(result.recent) == 3
        assert result.total_count == 50


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
