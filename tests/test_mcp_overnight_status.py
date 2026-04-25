"""Verification tests for Task 12 — ``overnight_status`` MCP tool.

Covers R4: the tool reads
``lifecycle/sessions/{session_id}/overnight-state.json`` (or
auto-discovers via ``~/.local/share/overnight-sessions/active-session.json``
when ``session_id`` is omitted) and returns a structured status object
whose JSON byte-length stays ≤ 4 500 chars (coarse 1 500-token smoke
check at 3 chars/token, per the spec).
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from cortex_command.mcp_server import tools
from cortex_command.mcp_server.schema import StatusInput, StatusOutput
from cortex_command.overnight import cli_handler, ipc


def _write_state_file(session_dir: Path, data: dict) -> None:
    """Write ``overnight-state.json`` under ``session_dir``."""
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "overnight-state.json").write_text(
        json.dumps(data, indent=2), encoding="utf-8"
    )


def _fixture_state(session_id: str, phase: str = "executing") -> dict:
    """A representative state dict with every FeatureCounts bucket populated."""
    return {
        "session_id": session_id,
        "plan_ref": f"lifecycle/sessions/{session_id}/overnight-plan.md",
        "plan_hash": "a" * 64,
        "current_round": 3,
        "phase": phase,
        "started_at": "2026-04-24T22:00:00+00:00",
        "updated_at": "2026-04-25T02:15:30+00:00",
        "integration_branch": "integration/overnight-2026-04-24",
        "paused_reason": None,
        "features": {
            "feat-a": {"status": "merged"},
            "feat-b": {"status": "running"},
            "feat-c": {"status": "pending"},
            "feat-d": {"status": "pending"},
            "feat-e": {"status": "deferred"},
            "feat-f": {"status": "failed"},
            "feat-g": {"status": "paused"},
        },
        "round_history": [],
    }


def test_status_by_session_id_reads_state_file(monkeypatch) -> None:
    """Passing ``session_id`` resolves under the caller's repo root."""
    with tempfile.TemporaryDirectory() as tmp:
        repo_path = Path(tmp)
        session_id = "overnight-2026-04-24-2200"
        session_dir = repo_path / "lifecycle" / "sessions" / session_id
        _write_state_file(session_dir, _fixture_state(session_id))

        monkeypatch.setattr(
            cli_handler, "_resolve_repo_path", lambda: repo_path
        )

        result = asyncio.run(
            tools.overnight_status(StatusInput(session_id=session_id))
        )

        assert isinstance(result, StatusOutput)
        assert result.session_id == session_id
        assert result.phase == "executing"
        assert result.current_round == 3
        assert result.integration_branch == (
            "integration/overnight-2026-04-24"
        )

        # FeatureCounts — each bucket from the fixture populated exactly.
        assert result.features.merged == 1
        assert result.features.running == 1
        assert result.features.pending == 2
        assert result.features.deferred == 1
        assert result.features.failed == 1
        assert result.features.paused == 1


def test_status_omitted_session_id_uses_active_pointer(
    monkeypatch, tmp_path
) -> None:
    """Omitting ``session_id`` falls back to the active-session pointer."""
    session_id = "overnight-2026-04-24-auto"
    session_dir = tmp_path / "lifecycle" / "sessions" / session_id
    _write_state_file(session_dir, _fixture_state(session_id))

    # Point the active-session pointer at a throwaway path so the real
    # ``~/.local/share/overnight-sessions/active-session.json`` is not
    # touched by the test run.
    active_path = tmp_path / "active-session.json"
    active_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "magic": "cortex-runner-v1",
                "session_id": session_id,
                "session_dir": str(session_dir),
                "phase": "executing",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(ipc, "ACTIVE_SESSION_PATH", active_path)

    result = asyncio.run(tools.overnight_status(StatusInput()))

    assert isinstance(result, StatusOutput)
    assert result.session_id == session_id
    assert result.phase == "executing"


def test_status_no_active_session_returns_sentinel(
    monkeypatch, tmp_path
) -> None:
    """No pointer + no ``session_id`` yields ``phase="no_active_session"``."""
    monkeypatch.setattr(
        ipc, "ACTIVE_SESSION_PATH", tmp_path / "nonexistent.json"
    )

    result = asyncio.run(tools.overnight_status(StatusInput()))

    assert isinstance(result, StatusOutput)
    assert result.session_id is None
    assert result.phase == "no_active_session"


def test_status_response_byte_length_within_budget(monkeypatch) -> None:
    """R4: the status JSON stays ≤ 4 500 chars (coarse 1 500-token cap)."""
    with tempfile.TemporaryDirectory() as tmp:
        repo_path = Path(tmp)
        session_id = "overnight-2026-04-24-budget"
        session_dir = repo_path / "lifecycle" / "sessions" / session_id
        # Pad the state file with many features so the response has
        # non-trivial size; assert the coarse budget holds.
        state = _fixture_state(session_id)
        for i in range(40):
            state["features"][f"feat-pad-{i}"] = {"status": "merged"}
        _write_state_file(session_dir, state)

        monkeypatch.setattr(
            cli_handler, "_resolve_repo_path", lambda: repo_path
        )

        result = asyncio.run(
            tools.overnight_status(StatusInput(session_id=session_id))
        )
        payload = result.model_dump_json()

        # Coarse smoke check per R4 — not a tokenizer-accurate contract.
        assert len(payload) <= 4500, (
            f"status response byte-length {len(payload)} exceeds "
            f"4 500-char budget"
        )


def test_status_missing_state_file_returns_sentinel(monkeypatch) -> None:
    """A ``session_id`` that has no state file returns the sentinel."""
    with tempfile.TemporaryDirectory() as tmp:
        repo_path = Path(tmp)
        (repo_path / "lifecycle" / "sessions").mkdir(parents=True)

        monkeypatch.setattr(
            cli_handler, "_resolve_repo_path", lambda: repo_path
        )

        result = asyncio.run(
            tools.overnight_status(StatusInput(session_id="nope"))
        )

        assert result.phase == "no_active_session"
        assert result.session_id == "nope"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
