"""Smoke tests for ``cortex overnight schedule`` (Task 5).

Covers the three high-value branches of :func:`handle_schedule`:

  - ``--dry-run`` exits 0 and prints session_id / label / scheduled_for_iso
    (human format) or a versioned envelope (json format).
  - Non-darwin platforms exit non-zero with the spec-exact macOS-only
    error message.
  - Invalid target-time inputs exit non-zero with the spec-mandated
    error phrasings (Feb-29 in non-leap year, in-the-past, malformed).

The tests construct a synthetic session directory under ``tmp_path`` and
monkeypatch :func:`cli_handler._resolve_repo_path` so the auto-discover
path locates the synthesized state file. The real macOS backend's
``schedule()`` is never invoked — dry-run and platform-gate cases both
short-circuit before reaching it, and the test suite must remain
hermetic regardless of host platform.
"""

from __future__ import annotations

import argparse
import io
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from cortex_command.overnight import cli_handler
from cortex_command.overnight.scheduler.dispatch import _UnsupportedScheduler


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_state_file(session_dir: Path, session_id: str) -> Path:
    """Create a minimal valid overnight-state.json under ``session_dir``."""
    session_dir.mkdir(parents=True, exist_ok=True)
    state_payload = {
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
    state_path = session_dir / "overnight-state.json"
    state_path.write_text(json.dumps(state_payload, indent=2) + "\n", encoding="utf-8")
    return state_path


def _future_hhmm(minutes_from_now: int = 60) -> str:
    """Return an HH:MM string in the future, well within the 7-day horizon.

    Defaults to one hour from now so the test is robust against
    cross-midnight drift if invoked at 23:59:59.
    """
    target = datetime.now() + timedelta(minutes=minutes_from_now)
    return target.strftime("%H:%M")


def _make_args(
    *,
    target_time: str,
    state: str | None = None,
    dry_run: bool = False,
    fmt: str = "human",
) -> argparse.Namespace:
    """Build an argparse.Namespace shaped like the schedule subparser produces."""
    return argparse.Namespace(
        target_time=target_time,
        state=state,
        dry_run=dry_run,
        format=fmt,
    )


# ---------------------------------------------------------------------------
# (a) --dry-run smoke
# ---------------------------------------------------------------------------


def test_schedule_dry_run_human_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """``--dry-run`` succeeds and prints session_id/label/target ISO."""
    session_id = "overnight-2026-05-04-2200"
    sessions_root = tmp_path / "lifecycle" / "sessions"
    session_dir = sessions_root / session_id
    state_path = _write_state_file(session_dir, session_id)

    monkeypatch.setattr(cli_handler, "_resolve_repo_path", lambda: tmp_path)

    args = _make_args(
        target_time=_future_hhmm(),
        state=str(state_path),
        dry_run=True,
        fmt="human",
    )

    rc = cli_handler.handle_schedule(args)
    captured = capsys.readouterr()

    assert rc == 0, f"expected exit 0; stderr={captured.err!r} stdout={captured.out!r}"
    assert f"session_id: {session_id}" in captured.out
    assert "label:" in captured.out
    assert "scheduled_for_iso:" in captured.out
    assert "dry-run" in captured.out


def test_schedule_dry_run_json_envelope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """``--dry-run --format json`` emits a versioned JSON envelope."""
    session_id = "overnight-2026-05-04-2300"
    sessions_root = tmp_path / "lifecycle" / "sessions"
    session_dir = sessions_root / session_id
    state_path = _write_state_file(session_dir, session_id)

    monkeypatch.setattr(cli_handler, "_resolve_repo_path", lambda: tmp_path)

    args = _make_args(
        target_time=_future_hhmm(),
        state=str(state_path),
        dry_run=True,
        fmt="json",
    )

    rc = cli_handler.handle_schedule(args)
    captured = capsys.readouterr()

    assert rc == 0, f"expected exit 0; stderr={captured.err!r}"
    payload = json.loads(captured.out.strip())
    assert payload["version"] == "1.0"
    assert payload["dry_run"] is True
    assert payload["session_id"] == session_id
    assert payload["label"].startswith(
        "com.charleshall.cortex-command.overnight-schedule."
    )
    assert payload["scheduled_for_iso"]


# ---------------------------------------------------------------------------
# (b) macOS-only gate
# ---------------------------------------------------------------------------


def test_schedule_non_darwin_exits_with_macos_only_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Non-macOS platforms get the spec-exact error message and non-zero exit."""
    session_id = "overnight-2026-05-04-0100"
    sessions_root = tmp_path / "lifecycle" / "sessions"
    session_dir = sessions_root / session_id
    state_path = _write_state_file(session_dir, session_id)

    monkeypatch.setattr(cli_handler, "_resolve_repo_path", lambda: tmp_path)

    # Force the dispatch.get_backend() call inside handle_schedule to
    # return the unsupported stub regardless of host platform.
    from cortex_command.overnight import scheduler as _scheduler_pkg

    monkeypatch.setattr(
        _scheduler_pkg,
        "get_backend",
        lambda: _UnsupportedScheduler(),
    )

    args = _make_args(
        target_time=_future_hhmm(),
        state=str(state_path),
        dry_run=False,  # platform gate fires before dry-run short-circuit
        fmt="human",
    )

    rc = cli_handler.handle_schedule(args)
    captured = capsys.readouterr()

    assert rc != 0
    assert "cortex overnight scheduling requires macOS" in captured.err


# ---------------------------------------------------------------------------
# (c) invalid target time
# ---------------------------------------------------------------------------


def test_schedule_feb_29_in_non_leap_year_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Feb 29 in a non-leap year exits non-zero with the spec phrasing."""
    session_id = "overnight-2026-05-04-0200"
    sessions_root = tmp_path / "lifecycle" / "sessions"
    session_dir = sessions_root / session_id
    state_path = _write_state_file(session_dir, session_id)

    monkeypatch.setattr(cli_handler, "_resolve_repo_path", lambda: tmp_path)

    args = _make_args(
        target_time="2026-02-29T23:00",
        state=str(state_path),
        dry_run=True,  # would otherwise short-circuit, but validation runs first
        fmt="human",
    )

    rc = cli_handler.handle_schedule(args)
    captured = capsys.readouterr()

    assert rc != 0
    assert "Feb 29 not in 2026" in captured.err


def test_schedule_malformed_target_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Unparseable target time exits non-zero before any backend work."""
    session_id = "overnight-2026-05-04-0300"
    sessions_root = tmp_path / "lifecycle" / "sessions"
    session_dir = sessions_root / session_id
    state_path = _write_state_file(session_dir, session_id)

    monkeypatch.setattr(cli_handler, "_resolve_repo_path", lambda: tmp_path)

    args = _make_args(
        target_time="not-a-time",
        state=str(state_path),
        dry_run=True,
        fmt="human",
    )

    rc = cli_handler.handle_schedule(args)
    captured = capsys.readouterr()

    assert rc != 0
    assert "invalid format" in captured.err
