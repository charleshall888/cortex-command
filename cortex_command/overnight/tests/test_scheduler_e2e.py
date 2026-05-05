"""End-to-end smoke test for the LaunchAgent-based scheduler (Task 13).

Exercises the full schedule-then-cancel lifecycle and the fail-marker
surface path against mocked ``launchctl`` invocations so no real launchd
interaction is required.

Three scenarios:
  1. schedule-then-cancel — verifies that after ``handle_schedule`` returns:
       - the sidecar entry exists
       - the plist file was written to the plist-dir
       - the launcher script was written to the plist-dir
       - ``scheduled_start`` appears in the state file

     Then after ``handle_cancel`` returns 0:
       - the sidecar entry is gone
       - the plist file is removed
       - the launcher script is removed
       - ``scheduled_start`` is cleared/absent in the state file

  2. fail-marker → status surface — simulates the launcher writing a
     ``scheduled-fire-failed.json`` sentinel directly, then calls
     ``handle_status`` and asserts the ``fire_failures`` field in the
     JSON output is non-empty.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from cortex_command.overnight import cli_handler
from cortex_command.overnight.scheduler import sidecar

# ---------------------------------------------------------------------------
# Platform gate
# ---------------------------------------------------------------------------

# All paths through handle_schedule and the macOS backend require darwin.
pytestmark = pytest.mark.skipif(
    sys.platform != "darwin",
    reason="macOS-only backend; scheduler e2e requires darwin",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_state(session_dir: Path, session_id: str) -> Path:
    """Create a minimal valid ``overnight-state.json`` under ``session_dir``."""
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


def _future_hhmm(minutes_from_now: int = 60) -> str:
    """Return an HH:MM string safely in the future."""
    target = datetime.now() + timedelta(minutes=minutes_from_now)
    return target.strftime("%H:%M")


def _make_schedule_args(
    *,
    target_time: str,
    state_path: Path,
    fmt: str = "json",
    dry_run: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        target_time=target_time,
        state=str(state_path),
        dry_run=dry_run,
        format=fmt,
    )


def _make_cancel_args(
    *,
    session_id: str,
    fmt: str = "json",
) -> argparse.Namespace:
    return argparse.Namespace(
        session_id=session_id,
        session_dir=None,
        format=fmt,
        force=False,
        list_only=False,
    )


def _make_status_args(*, session_dir: str, fmt: str = "json") -> argparse.Namespace:
    return argparse.Namespace(
        format=fmt,
        session_dir=session_dir,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def home_redirect(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect ``Path.home()`` at all sidecar/lock sites to keep the real
    ``~/.cache/cortex-command/`` untouched during tests.
    """
    fake_home = tmp_path / "home"
    fake_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "cortex_command.overnight.scheduler.sidecar.Path.home",
        lambda: fake_home,
    )
    monkeypatch.setattr(
        "cortex_command.overnight.scheduler.lock.Path.home",
        lambda: fake_home,
    )
    return fake_home


@pytest.fixture()
def plist_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the macOS backend's plist directory to a tmp-path sub-dir
    and set ``$TMPDIR`` to the parent so ``_plist_dir()`` resolves there.
    """
    plists = tmp_path / "cortex-overnight-launch"
    plists.mkdir(parents=True, exist_ok=True)
    # _plist_dir() reads os.environ["TMPDIR"] — point it at tmp_path so
    # the path resolves to tmp_path/cortex-overnight-launch.
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    return plists


@pytest.fixture()
def fake_launchctl(monkeypatch: pytest.MonkeyPatch):
    """Stub ``subprocess.run`` at the macOS-backend boundary so no real
    ``launchctl`` binary is invoked.

    bootstrap → exit 0
    print     → exit 0, stdout contains "state = waiting"
    bootout   → exit 0
    """

    def _fake_run(cmd, *args, **kwargs):
        if not (isinstance(cmd, list) and cmd and cmd[0] == "launchctl"):
            # Pass-through any non-launchctl calls (shouldn't happen here,
            # but keep the stub narrow).
            return subprocess.run(cmd, *args, **kwargs)  # noqa: S603
        subverb = cmd[1] if len(cmd) > 1 else ""
        if subverb == "bootstrap":
            return subprocess.CompletedProcess(cmd, 0, b"", b"")
        if subverb == "print":
            return subprocess.CompletedProcess(
                cmd, 0, b"state = waiting\n", b""
            )
        if subverb == "bootout":
            return subprocess.CompletedProcess(cmd, 0, b"", b"")
        # Any other subverb — succeed silently.
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    monkeypatch.setattr(
        "cortex_command.overnight.scheduler.macos.subprocess.run",
        _fake_run,
    )


# ---------------------------------------------------------------------------
# Test 1: schedule-then-cancel full lifecycle
# ---------------------------------------------------------------------------


def test_schedule_then_cancel_full_lifecycle(
    tmp_path: Path,
    home_redirect: Path,
    plist_dir: Path,
    fake_launchctl,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """Schedule fires, creates all four artifacts; cancel removes all four."""
    session_id = "overnight-2026-05-04-2200"
    sessions_root = tmp_path / "lifecycle" / "sessions"
    session_dir = sessions_root / session_id
    state_path = _write_state(session_dir, session_id)

    # Wire repo root so session-path resolution and state-load work.
    monkeypatch.setattr(cli_handler, "_resolve_repo_path", lambda: tmp_path)

    # Redirect state.session_dir() so the backend writes launcher/plist
    # logs to our tmp session dir rather than the real one. The backend
    # imports it as a local ``from cortex_command.overnight.state import
    # session_dir`` at call-time, so we patch at the module level.
    def _fake_session_dir(sid: str) -> Path:
        d = sessions_root / sid
        d.mkdir(parents=True, exist_ok=True)
        return d

    monkeypatch.setattr(
        "cortex_command.overnight.state.session_dir",
        _fake_session_dir,
    )

    # ---- schedule ----
    schedule_args = _make_schedule_args(
        target_time=_future_hhmm(),
        state_path=state_path,
        fmt="json",
    )
    rc_schedule = cli_handler.handle_schedule(schedule_args)
    captured = capsys.readouterr()

    assert rc_schedule == 0, (
        f"handle_schedule failed; stdout={captured.out!r} stderr={captured.err!r}"
    )

    sched_payload = json.loads(captured.out.strip())
    assert sched_payload["scheduled"] is True
    assert sched_payload["session_id"] == session_id
    label = sched_payload["label"]
    assert label.startswith(
        "com.charleshall.cortex-command.overnight-schedule."
    )

    # --- assert: sidecar entry exists ---
    sidecar_handle = sidecar.find_by_session_id(session_id)
    assert sidecar_handle is not None, "sidecar entry missing after schedule"
    assert sidecar_handle.label == label

    # --- assert: plist file exists ---
    plist_path = sidecar_handle.plist_path
    assert plist_path.exists(), f"plist file missing: {plist_path}"

    # --- assert: launcher script exists ---
    launcher_path = sidecar_handle.launcher_path
    assert launcher_path.exists(), f"launcher script missing: {launcher_path}"

    # --- assert: scheduled_start written to state file ---
    state_data = json.loads(state_path.read_text(encoding="utf-8"))
    assert "scheduled_start" in state_data, (
        "scheduled_start field not written to state file"
    )
    assert isinstance(state_data["scheduled_start"], str)
    assert state_data["scheduled_start"]

    # ---- cancel ----
    cancel_args = _make_cancel_args(session_id=session_id, fmt="json")
    rc_cancel = cli_handler.handle_cancel(cancel_args)
    captured = capsys.readouterr()

    assert rc_cancel == 0, (
        f"handle_cancel failed; stdout={captured.out!r} stderr={captured.err!r}"
    )

    cancel_payload = json.loads(captured.out.strip())
    assert cancel_payload["cancelled"] is True
    assert cancel_payload["session_id"] == session_id
    assert cancel_payload["kind"] == "scheduled"
    assert cancel_payload["bootout_exit_code"] == 0
    assert cancel_payload["sidecar_removed"] is True

    # --- assert: sidecar entry removed ---
    assert sidecar.find_by_session_id(session_id) is None, (
        "sidecar entry still present after cancel"
    )

    # --- assert: plist file removed ---
    assert not plist_path.exists(), f"plist file still present after cancel: {plist_path}"

    # --- assert: launcher script removed ---
    assert not launcher_path.exists(), (
        f"launcher script still present after cancel: {launcher_path}"
    )

    # --- assert: scheduled_start cleared in state file ---
    state_data_after = json.loads(state_path.read_text(encoding="utf-8"))
    assert state_data_after.get("scheduled_start") is None, (
        f"scheduled_start not cleared after cancel; got {state_data_after.get('scheduled_start')!r}"
    )


# ---------------------------------------------------------------------------
# Test 2: fail-marker write → handle_status surfaces fire_failures
# ---------------------------------------------------------------------------


def test_fail_marker_surfaces_in_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """Touching a ``scheduled-fire-failed.json`` sentinel then calling
    ``handle_status`` populates ``fire_failures`` in the JSON envelope.
    """
    session_id = "overnight-2026-05-04-2300"
    sessions_root = tmp_path / "lifecycle" / "sessions"
    session_dir = sessions_root / session_id
    state_path = _write_state(session_dir, session_id)

    # Simulate the launcher writing a fail-marker for this session.
    label = (
        f"com.charleshall.cortex-command.overnight-schedule.{session_id}.999999"
    )
    fail_marker = session_dir / "scheduled-fire-failed.json"
    fail_marker.write_text(
        json.dumps(
            {
                "ts": "2026-05-04T22:00:11Z",
                "error_class": "EPERM",
                "error_text": "Operation not permitted: /usr/local/bin/cortex",
                "label": label,
                "session_id": session_id,
            }
        ),
        encoding="utf-8",
    )

    # Wire repo root and suppress the active-session pointer so
    # handle_status falls back to the latest state file we just wrote.
    monkeypatch.setattr(cli_handler, "_resolve_repo_path", lambda: tmp_path)
    monkeypatch.setattr(
        "cortex_command.overnight.cli_handler.ipc.read_active_session",
        lambda: None,
    )

    status_args = _make_status_args(session_dir=str(session_dir), fmt="json")
    rc = cli_handler.handle_status(status_args)
    captured = capsys.readouterr()

    assert rc == 0, f"handle_status failed; stderr={captured.err!r}"

    payload = json.loads(captured.out.strip())
    assert "fire_failures" in payload, (
        f"fire_failures field missing from status payload; got keys={list(payload)}"
    )
    fire_failures = payload["fire_failures"]
    assert len(fire_failures) == 1, (
        f"expected 1 fire_failure entry, got {len(fire_failures)}: {fire_failures!r}"
    )

    failure = fire_failures[0]
    assert failure["error_class"] == "EPERM"
    assert failure["session_id"] == session_id
    assert failure["label"] == label
    assert failure["ts"] == "2026-05-04T22:00:11Z"
    # session_dir is the absolute path to the session directory
    assert str(session_dir.resolve()) in failure["session_dir"]
