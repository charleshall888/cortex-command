"""Tests for ``handle_status`` surfacing of ``scheduled_start`` (Task 7).

Covers the JSON envelope and the human-readable output paths:

  - When the state file has no ``scheduled_start`` field, the JSON
    envelope reports ``scheduled_start: null``; the human output omits
    the "Scheduled fire:" line.
  - When the state file has a ``scheduled_start`` ISO 8601 string, the
    JSON envelope echoes the value; the human output includes a line
    starting with ``Scheduled fire:`` whose value matches.

Also covers the ``render_status`` scheduled-dormant render (Task 11 / R12):

  - A future ``scheduled_start`` with no live ``runner.pid`` and a
    non-executing/non-complete phase renders a "Scheduled (dormant) —
    fires at {scheduled_start}" line and suppresses the
    Elapsed/Watchdog block.
  - The persisted ``PHASES`` tuple is unchanged — no display-only value
    is leaked into it.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from cortex_command.overnight import cli_handler, status as status_module
from cortex_command.overnight.state import PHASES


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
        "plan_ref": "cortex/lifecycle/test/plan.md",
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
    sessions_root = tmp_path / "cortex" / "lifecycle" / "sessions"
    session_dir = sessions_root / session_id
    _write_state(session_dir, session_id, scheduled_start=None)

    monkeypatch.setattr(cli_handler, "_resolve_repo_path", lambda: tmp_path)
    # Force the active-session pointer to be empty so the fallback uses
    # the latest-state path under our tmp_path cortex/lifecycle/sessions dir.
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
    sessions_root = tmp_path / "cortex" / "lifecycle" / "sessions"
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
    sessions_root = tmp_path / "cortex" / "lifecycle" / "sessions"
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
    sessions_root = tmp_path / "cortex" / "lifecycle" / "sessions"
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


# ---------------------------------------------------------------------------
# render_status scheduled-dormant render (Task 11 / R12)
# ---------------------------------------------------------------------------


def _write_render_state(
    tmp_path: Path,
    session_id: str,
    *,
    phase: str,
    scheduled_start: str | None,
) -> Path:
    """Write a session state under tmp_path's cortex/lifecycle/sessions tree.

    Returns the per-session state path. No ``runner.pid`` is created, so the
    liveness probe reports no live runner.
    """
    sessions_root = tmp_path / "cortex" / "lifecycle" / "sessions"
    session_dir = sessions_root / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "session_id": session_id,
        "plan_ref": "cortex/lifecycle/test/plan.md",
        "current_round": 1,
        "phase": phase,
        "features": {},
        "round_history": [],
        "started_at": "2026-05-04T10:00:00+00:00",
        "updated_at": "2026-05-04T10:00:00+00:00",
        "schema_version": 1,
    }
    if scheduled_start is not None:
        payload["scheduled_start"] = scheduled_start
    state_path = session_dir / "overnight-state.json"
    state_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return state_path


def test_render_status_dormant_when_future_schedule_and_no_live_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Future scheduled_start + no live runner.pid renders the dormant line.

    The Elapsed and Watchdog lines (executing-run metrics) are suppressed so
    a merely-pending fire does not read as an alarm.
    """
    future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    _write_render_state(
        tmp_path,
        "overnight-2026-05-04-2200",
        phase="planning",
        scheduled_start=future,
    )

    # Point the status renderer's project root at our tmp tree.
    monkeypatch.setattr(
        status_module, "_resolve_user_project_root", lambda: tmp_path
    )

    status_module.render_status()
    out = capsys.readouterr().out

    assert f"Scheduled (dormant) — fires at {future}" in out
    # The executing/elapsed-watchdog block is suppressed.
    assert "Elapsed" not in out
    assert "Watchdog" not in out


def test_render_status_not_dormant_when_phase_executing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """An executing session is never shown dormant even with a future schedule.

    The conjunctive predicate (F5) requires the session to be neither
    executing nor complete, guarding against misclassifying a just-started
    run as dormant near the fire boundary.
    """
    future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    _write_render_state(
        tmp_path,
        "overnight-2026-05-04-2300",
        phase="executing",
        scheduled_start=future,
    )

    monkeypatch.setattr(
        status_module, "_resolve_user_project_root", lambda: tmp_path
    )

    status_module.render_status()
    out = capsys.readouterr().out

    assert "Scheduled (dormant)" not in out
    assert "Elapsed" in out


def test_render_status_not_dormant_when_runner_pid_live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """A live runner.pid suppresses the dormant render despite a future schedule.

    Simulated by forcing the liveness probe to report a live runner; the
    conjunctive predicate then keeps the normal (non-dormant) render.
    """
    future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    _write_render_state(
        tmp_path,
        "overnight-2026-05-04-0100",
        phase="planning",
        scheduled_start=future,
    )

    monkeypatch.setattr(
        status_module, "_resolve_user_project_root", lambda: tmp_path
    )
    # Force the liveness probe to report a live runner.
    monkeypatch.setattr(
        status_module, "_is_runner_pid_live", lambda _dir: True
    )

    status_module.render_status()
    out = capsys.readouterr().out

    assert "Scheduled (dormant)" not in out
    assert "Elapsed" in out


def test_phases_tuple_unchanged_no_display_only_leak() -> None:
    """The persisted PHASES tuple gains no scheduled-dormant display value."""
    assert len(PHASES) == 5
    assert "scheduled_dormant" not in PHASES
    assert "scheduled" not in PHASES
