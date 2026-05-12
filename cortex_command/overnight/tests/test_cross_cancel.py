"""Tests for the R14 cross-cancel guards (Task 7).

Two directions covered:

  - ``schedule`` while a runner is active OR while a fresh
    ``runner.spawn-pending`` sentinel is present → exits non-zero with
    ``active_runner_present``. A stale (>30s old) sentinel is ignored
    (treated as orphan) and scheduling proceeds to the platform gate.
  - ``start`` while a sidecar entry is pending for the same session →
    exits non-zero with ``pending_schedule``. ``--force`` bypasses the
    guard.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from cortex_command.overnight import cli_handler, ipc
from cortex_command.overnight.scheduler import sidecar
from cortex_command.overnight.scheduler.protocol import ScheduledHandle


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _write_state(session_dir: Path, session_id: str) -> Path:
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
    state_path = session_dir / "overnight-state.json"
    state_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return state_path


@pytest.fixture
def home_redirect(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "cortex_command.overnight.scheduler.sidecar.Path.home",
        lambda: home,
    )
    return home


def _future_hhmm(minutes_from_now: int = 60) -> str:
    target = datetime.now() + timedelta(minutes=minutes_from_now)
    return target.strftime("%H:%M")


def _make_schedule_args(
    *,
    target_time: str,
    state: str,
    fmt: str = "human",
    dry_run: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        target_time=target_time,
        state=state,
        dry_run=dry_run,
        format=fmt,
    )


def _make_start_args(
    *,
    state: str,
    fmt: str = "human",
    force: bool = False,
    dry_run: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        state=state,
        format=fmt,
        force=force,
        dry_run=dry_run,
        launchd=False,
        time_limit=None,
        max_rounds=None,
        tier="simple",
    )


# ---------------------------------------------------------------------------
# Schedule-side guard: live runner blocks
# ---------------------------------------------------------------------------


def test_schedule_blocked_when_runner_active(
    tmp_path: Path,
    home_redirect: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """A verified-live runner.pid causes schedule to exit non-zero."""
    session_id = "overnight-2026-05-04-2200"
    sessions_root = tmp_path / "cortex" / "lifecycle" / "sessions"
    session_dir = sessions_root / session_id
    state_path = _write_state(session_dir, session_id)

    monkeypatch.setattr(cli_handler, "_resolve_repo_path", lambda: tmp_path)
    # Force a live runner.pid + verify_runner_pid → True.
    monkeypatch.setattr(
        ipc,
        "read_runner_pid",
        lambda d: {"pid": 1, "session_id": session_id, "magic": "cortex-runner-v1"},
    )
    monkeypatch.setattr(ipc, "verify_runner_pid", lambda d: True)

    args = _make_schedule_args(
        target_time=_future_hhmm(),
        state=str(state_path),
        fmt="human",
    )

    rc = cli_handler.handle_schedule(args)
    captured = capsys.readouterr()

    assert rc != 0
    assert "active runner present" in captured.err


def test_schedule_blocked_when_spawn_pending_fresh(
    tmp_path: Path,
    home_redirect: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """A fresh spawn-pending sentinel blocks schedule (handshake gap guard)."""
    session_id = "overnight-2026-05-04-2300"
    sessions_root = tmp_path / "cortex" / "lifecycle" / "sessions"
    session_dir = sessions_root / session_id
    state_path = _write_state(session_dir, session_id)

    monkeypatch.setattr(cli_handler, "_resolve_repo_path", lambda: tmp_path)
    # No runner.pid.
    monkeypatch.setattr(ipc, "read_runner_pid", lambda d: None)
    monkeypatch.setattr(ipc, "verify_runner_pid", lambda d: False)

    sentinel = session_dir / "runner.spawn-pending"
    sentinel.write_text("", encoding="utf-8")
    # Fresh by virtue of just having been written.

    args = _make_schedule_args(
        target_time=_future_hhmm(),
        state=str(state_path),
        fmt="human",
    )

    rc = cli_handler.handle_schedule(args)
    captured = capsys.readouterr()

    assert rc != 0
    assert "active runner present" in captured.err


def test_schedule_proceeds_when_spawn_pending_stale(
    tmp_path: Path,
    home_redirect: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """A stale (>30s) spawn-pending sentinel is ignored; schedule proceeds."""
    session_id = "overnight-2026-05-04-0100"
    sessions_root = tmp_path / "cortex" / "lifecycle" / "sessions"
    session_dir = sessions_root / session_id
    state_path = _write_state(session_dir, session_id)

    monkeypatch.setattr(cli_handler, "_resolve_repo_path", lambda: tmp_path)
    monkeypatch.setattr(ipc, "read_runner_pid", lambda d: None)
    monkeypatch.setattr(ipc, "verify_runner_pid", lambda d: False)

    sentinel = session_dir / "runner.spawn-pending"
    sentinel.write_text("", encoding="utf-8")
    # Backdate mtime by 60s so the staleness check fires.
    stale_ts = time.time() - 60
    os.utime(sentinel, (stale_ts, stale_ts))

    # --dry-run so the test never reaches the real backend.
    args = _make_schedule_args(
        target_time=_future_hhmm(),
        state=str(state_path),
        dry_run=True,
        fmt="human",
    )

    rc = cli_handler.handle_schedule(args)
    captured = capsys.readouterr()

    # On non-darwin platforms the macOS gate fires first with a
    # different message; what we care about for this test is that the
    # cross-cancel guard did NOT fire.
    assert "active runner present" not in captured.err


# ---------------------------------------------------------------------------
# Start-side guard: pending schedule blocks (unless --force)
# ---------------------------------------------------------------------------


def test_start_blocked_when_pending_schedule(
    tmp_path: Path,
    home_redirect: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """A pending sidecar entry causes start to exit non-zero."""
    session_id = "overnight-2026-05-04-0200"
    sessions_root = tmp_path / "cortex" / "lifecycle" / "sessions"
    session_dir = sessions_root / session_id
    state_path = _write_state(session_dir, session_id)

    monkeypatch.setattr(cli_handler, "_resolve_repo_path", lambda: tmp_path)

    handle = ScheduledHandle(
        label=f"com.charleshall.cortex-command.overnight-schedule.{session_id}.111",
        session_id=session_id,
        plist_path=tmp_path / "fake.plist",
        launcher_path=tmp_path / "launcher.sh",
        scheduled_for_iso="2026-05-05T22:00:00",
        created_at_iso="2026-05-04T22:00:00",
    )
    sidecar.add_entry(handle)

    args = _make_start_args(state=str(state_path), fmt="human", force=False)

    rc = cli_handler.handle_start(args)
    captured = capsys.readouterr()

    assert rc != 0
    assert "pending schedule" in captured.err
    assert session_id in captured.err


def test_start_with_force_bypasses_pending_schedule_guard(
    tmp_path: Path,
    home_redirect: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """``--force`` skips the pending-schedule guard.

    We use ``--dry-run`` to avoid spawning the real runner; the goal is
    to assert the guard did NOT fire (rc would be 1 from the guard with
    a "pending schedule" stderr message).
    """
    session_id = "overnight-2026-05-04-0300"
    sessions_root = tmp_path / "cortex" / "lifecycle" / "sessions"
    session_dir = sessions_root / session_id
    state_path = _write_state(session_dir, session_id)

    monkeypatch.setattr(cli_handler, "_resolve_repo_path", lambda: tmp_path)

    handle = ScheduledHandle(
        label=f"com.charleshall.cortex-command.overnight-schedule.{session_id}.222",
        session_id=session_id,
        plist_path=tmp_path / "fake.plist",
        launcher_path=tmp_path / "launcher.sh",
        scheduled_for_iso="2026-05-05T22:00:00",
        created_at_iso="2026-05-04T22:00:00",
    )
    sidecar.add_entry(handle)

    # Stub the inline runner so we don't actually run anything.
    monkeypatch.setattr(cli_handler, "_run_runner_inline", lambda **kwargs: 0)

    args = _make_start_args(
        state=str(state_path),
        fmt="human",
        force=True,
        dry_run=True,
    )
    rc = cli_handler.handle_start(args)
    captured = capsys.readouterr()

    assert "pending schedule" not in captured.err
    # Either dry-run path returns 0 from our stub, or the guard fired
    # (it must not have given --force). Assert the guard did not fire.
    assert rc == 0
