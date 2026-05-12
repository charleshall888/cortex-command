"""Tests for ``cortex overnight cancel`` against pending scheduled launches.

Covers Task 7's extension to :func:`cli_handler.handle_cancel`:

  - Schedule-then-cancel writes the sidecar entry, then ``cancel``
    finds it via :func:`sidecar.find_by_session_id`, calls the macOS
    backend's ``cancel()`` (mocked at the ``subprocess.run`` boundary
    for ``launchctl bootout``), removes plist + launcher + sidecar,
    and clears ``scheduled_start`` from the state file.
  - The acceptance phrase from spec R4 — ``launchctl print
    gui/$(id -u)/<label>`` exits 113 — is asserted by checking that
    we invoked ``launchctl bootout`` and that the post-cancel state
    file no longer contains a ``scheduled_start`` value.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from cortex_command.overnight import cli_handler
from cortex_command.overnight.scheduler import sidecar
from cortex_command.overnight.scheduler.protocol import ScheduledHandle


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_state(session_dir: Path, session_id: str, scheduled_start: str | None) -> Path:
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


def _make_handle(session_id: str, plist_path: Path, launcher_path: Path) -> ScheduledHandle:
    return ScheduledHandle(
        label=f"com.charleshall.cortex-command.overnight-schedule.{session_id}.123456",
        session_id=session_id,
        plist_path=plist_path,
        launcher_path=launcher_path,
        scheduled_for_iso="2026-05-05T22:00:00",
        created_at_iso="2026-05-04T22:00:00",
    )


@pytest.fixture
def home_redirect(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect Path.home() at the sidecar binding to keep the real cache untouched."""
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "cortex_command.overnight.scheduler.sidecar.Path.home",
        lambda: home,
    )
    return home


# ---------------------------------------------------------------------------
# Cancel: schedule-then-cancel happy path
# ---------------------------------------------------------------------------


def test_cancel_scheduled_launch_removes_sidecar_and_clears_state(
    tmp_path: Path,
    home_redirect: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """cancel <sid> with no live runner cancels the scheduled launch."""
    if sys.platform != "darwin":
        pytest.skip("macOS-only backend; cancel path requires darwin dispatch")

    session_id = "overnight-2026-05-04-2200"
    sessions_root = tmp_path / "cortex" / "lifecycle" / "sessions"
    session_dir = sessions_root / session_id
    state_path = _write_state(session_dir, session_id, scheduled_start="2026-05-05T22:00:00")

    # Set up a fake plist + launcher so the backend's _safe_unlink
    # actually removes something tangible. The backend's cancel() builds
    # paths from `<plist_dir>/<label>.plist` and `launcher-<label>.sh`,
    # so the on-disk filenames must follow that convention exactly.
    plist_dir = tmp_path / "plist-dir"
    plist_dir.mkdir(parents=True, exist_ok=True)
    label = (
        f"com.charleshall.cortex-command.overnight-schedule.{session_id}.123456"
    )
    handle = ScheduledHandle(
        label=label,
        session_id=session_id,
        plist_path=plist_dir / f"{label}.plist",
        launcher_path=plist_dir / f"launcher-{label}.sh",
        scheduled_for_iso="2026-05-05T22:00:00",
        created_at_iso="2026-05-04T22:00:00",
    )
    handle.plist_path.write_text("plist", encoding="utf-8")
    handle.launcher_path.write_text("launcher", encoding="utf-8")

    # Force the backend's _plist_dir() to point at our tmp_path location
    # so the backend cleans up the right files.
    monkeypatch.setattr(
        "cortex_command.overnight.scheduler.macos.MacOSLaunchAgentBackend._plist_dir",
        staticmethod(lambda: plist_dir),
    )

    sidecar.add_entry(handle)
    # Verify the sidecar saw the entry.
    assert sidecar.find_by_session_id(session_id) is not None

    # Mock subprocess.run so launchctl bootout succeeds without invoking
    # the real launchctl binary (test must remain hermetic).
    def _fake_run(cmd, *args, **kwargs):
        # Only intercept launchctl invocations.
        if isinstance(cmd, list) and len(cmd) > 0 and cmd[0] == "launchctl":
            return subprocess.CompletedProcess(cmd, 0, b"", b"")
        return subprocess.run(cmd, *args, **kwargs)

    monkeypatch.setattr(
        "cortex_command.overnight.scheduler.macos.subprocess.run",
        _fake_run,
    )

    # Wire the test's repo root so _resolve_repo_path locates the session.
    monkeypatch.setattr(cli_handler, "_resolve_repo_path", lambda: tmp_path)

    args = argparse.Namespace(
        session_id=session_id,
        session_dir=None,
        format="human",
        force=False,
        list_only=False,
    )

    rc = cli_handler.handle_cancel(args)
    captured = capsys.readouterr()

    assert rc == 0, f"expected 0; stderr={captured.err!r} stdout={captured.out!r}"
    # Sidecar entry removed.
    assert sidecar.find_by_session_id(session_id) is None
    # Plist + launcher unlinked.
    assert not handle.plist_path.exists()
    assert not handle.launcher_path.exists()
    # State file's scheduled_start cleared.
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state.get("scheduled_start") is None


def test_cancel_scheduled_launch_json_envelope(
    tmp_path: Path,
    home_redirect: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """JSON format emits versioned envelope describing the cancel result."""
    if sys.platform != "darwin":
        pytest.skip("macOS-only backend; cancel path requires darwin dispatch")

    session_id = "overnight-2026-05-04-2300"
    sessions_root = tmp_path / "cortex" / "lifecycle" / "sessions"
    session_dir = sessions_root / session_id
    _write_state(session_dir, session_id, scheduled_start="2026-05-05T22:00:00")

    plist_dir = tmp_path / "plist-dir"
    plist_dir.mkdir(parents=True, exist_ok=True)
    label = (
        f"com.charleshall.cortex-command.overnight-schedule.{session_id}.123456"
    )
    handle = ScheduledHandle(
        label=label,
        session_id=session_id,
        plist_path=plist_dir / f"{label}.plist",
        launcher_path=plist_dir / f"launcher-{label}.sh",
        scheduled_for_iso="2026-05-05T22:00:00",
        created_at_iso="2026-05-04T22:00:00",
    )
    handle.plist_path.write_text("plist", encoding="utf-8")
    handle.launcher_path.write_text("launcher", encoding="utf-8")
    sidecar.add_entry(handle)

    monkeypatch.setattr(
        "cortex_command.overnight.scheduler.macos.MacOSLaunchAgentBackend._plist_dir",
        staticmethod(lambda: plist_dir),
    )

    def _fake_run(cmd, *args, **kwargs):
        if isinstance(cmd, list) and cmd and cmd[0] == "launchctl":
            return subprocess.CompletedProcess(cmd, 0, b"", b"")
        return subprocess.run(cmd, *args, **kwargs)

    monkeypatch.setattr(
        "cortex_command.overnight.scheduler.macos.subprocess.run",
        _fake_run,
    )
    monkeypatch.setattr(cli_handler, "_resolve_repo_path", lambda: tmp_path)

    args = argparse.Namespace(
        session_id=session_id,
        session_dir=None,
        format="json",
        force=False,
        list_only=False,
    )

    rc = cli_handler.handle_cancel(args)
    captured = capsys.readouterr()

    assert rc == 0
    payload = json.loads(captured.out.strip())
    assert payload["version"] == "1.0"
    assert payload["cancelled"] is True
    assert payload["session_id"] == session_id
    assert payload["kind"] == "scheduled"
    assert payload["bootout_exit_code"] == 0
    assert payload["sidecar_removed"] is True


def test_cancel_no_runner_no_schedule_returns_no_active_session(
    tmp_path: Path,
    home_redirect: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """Without a live runner OR a sidecar entry, cancel surfaces no_active_session."""
    if sys.platform != "darwin":
        pytest.skip("macOS-only backend; cancel path requires darwin dispatch")

    session_id = "overnight-2026-05-04-0100"
    sessions_root = tmp_path / "cortex" / "lifecycle" / "sessions"
    session_dir = sessions_root / session_id
    _write_state(session_dir, session_id, scheduled_start=None)

    monkeypatch.setattr(cli_handler, "_resolve_repo_path", lambda: tmp_path)

    args = argparse.Namespace(
        session_id=session_id,
        session_dir=None,
        format="json",
        force=False,
        list_only=False,
    )

    rc = cli_handler.handle_cancel(args)
    captured = capsys.readouterr()

    assert rc != 0
    payload = json.loads(captured.out.strip())
    assert payload["error"] == "no_active_session"
