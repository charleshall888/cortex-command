"""Tests for ``handle_status`` surfacing of ``scheduled_start`` (Task 7).

Covers the JSON envelope and the human-readable output paths:

  - When the state file has no ``scheduled_start`` field, the JSON
    envelope reports ``scheduled_start: null``; the human output omits
    the "Scheduled fire:" line.
  - When the state file has a ``scheduled_start`` ISO 8601 string, the
    JSON envelope echoes the value; the human output includes a line
    starting with ``Scheduled fire:`` whose value matches.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from cortex_command.overnight import cli_handler


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_state(
    session_dir: Path,
    session_id: str,
    *,
    scheduled_start: str | None,
) -> Path:
    session_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "session_id": session_id,
        "plan_ref": "lifecycle/test/plan.md",
        "current_round": 1,
        "phase": "planning",
        "features": {},
        "round_history": [],
        "started_at": "2026-05-04T10:00:00",
        "updated_at": "2026-05-04T10:00:00",
        "schema_version": 1,
    }
    if scheduled_start is not None:
        payload["scheduled_start"] = scheduled_start
    state_path = session_dir / "overnight-state.json"
    state_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return state_path


def _make_args(*, session_dir: str | None = None, fmt: str = "json") -> argparse.Namespace:
    return argparse.Namespace(
        format=fmt,
        session_dir=session_dir,
    )


# ---------------------------------------------------------------------------
# JSON output
# ---------------------------------------------------------------------------


def test_status_json_includes_scheduled_start_null_when_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """JSON envelope reports ``scheduled_start: null`` when the field is absent."""
    session_id = "overnight-2026-05-04-2200"
    sessions_root = tmp_path / "lifecycle" / "sessions"
    session_dir = sessions_root / session_id
    _write_state(session_dir, session_id, scheduled_start=None)

    monkeypatch.setattr(cli_handler, "_resolve_repo_path", lambda: tmp_path)
    # Force the active-session pointer to be empty so the fallback uses
    # the latest-state path under our tmp_path lifecycle/sessions dir.
    monkeypatch.setattr(
        "cortex_command.overnight.cli_handler.ipc.read_active_session",
        lambda: None,
    )

    args = _make_args(session_dir=None, fmt="json")
    rc = cli_handler.handle_status(args)
    captured = capsys.readouterr()

    assert rc == 0, f"unexpected stderr={captured.err!r}"
    payload = json.loads(captured.out.strip())
    assert "scheduled_start" in payload
    assert payload["scheduled_start"] is None


def test_status_json_includes_scheduled_start_iso_when_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """JSON envelope echoes ``scheduled_start`` as an ISO 8601 string."""
    session_id = "overnight-2026-05-04-2300"
    sessions_root = tmp_path / "lifecycle" / "sessions"
    session_dir = sessions_root / session_id
    iso = "2026-05-05T22:00:00"
    _write_state(session_dir, session_id, scheduled_start=iso)

    monkeypatch.setattr(cli_handler, "_resolve_repo_path", lambda: tmp_path)
    monkeypatch.setattr(
        "cortex_command.overnight.cli_handler.ipc.read_active_session",
        lambda: None,
    )

    args = _make_args(session_dir=None, fmt="json")
    rc = cli_handler.handle_status(args)
    captured = capsys.readouterr()

    assert rc == 0, f"unexpected stderr={captured.err!r}"
    payload = json.loads(captured.out.strip())
    assert payload["scheduled_start"] == iso


# ---------------------------------------------------------------------------
# Human output
# ---------------------------------------------------------------------------


def test_status_human_includes_scheduled_fire_line_when_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Human output prints ``Scheduled fire: <iso>`` when scheduled_start is set."""
    session_id = "overnight-2026-05-04-0100"
    sessions_root = tmp_path / "lifecycle" / "sessions"
    session_dir = sessions_root / session_id
    iso = "2026-05-05T22:00:00"
    _write_state(session_dir, session_id, scheduled_start=iso)

    monkeypatch.setattr(cli_handler, "_resolve_repo_path", lambda: tmp_path)
    monkeypatch.setattr(
        "cortex_command.overnight.cli_handler.ipc.read_active_session",
        lambda: None,
    )

    # Stub render_status so we don't depend on its output for the
    # assertion (the scheduled-fire line is appended outside it).
    monkeypatch.setattr(
        "cortex_command.overnight.cli_handler.status_module.render_status",
        lambda: None,
    )

    args = _make_args(session_dir=str(session_dir), fmt="human")
    rc = cli_handler.handle_status(args)
    captured = capsys.readouterr()

    assert rc == 0
    assert f"Scheduled fire: {iso}" in captured.out


def test_status_human_omits_scheduled_fire_line_when_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Human output does not print Scheduled fire when scheduled_start is null."""
    session_id = "overnight-2026-05-04-0200"
    sessions_root = tmp_path / "lifecycle" / "sessions"
    session_dir = sessions_root / session_id
    _write_state(session_dir, session_id, scheduled_start=None)

    monkeypatch.setattr(cli_handler, "_resolve_repo_path", lambda: tmp_path)
    monkeypatch.setattr(
        "cortex_command.overnight.cli_handler.ipc.read_active_session",
        lambda: None,
    )
    monkeypatch.setattr(
        "cortex_command.overnight.cli_handler.status_module.render_status",
        lambda: None,
    )

    args = _make_args(session_dir=str(session_dir), fmt="human")
    rc = cli_handler.handle_status(args)
    captured = capsys.readouterr()

    assert rc == 0
    assert "Scheduled fire:" not in captured.out
