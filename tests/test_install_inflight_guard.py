"""Tests for the pre-install in-flight guard (R28).

Covers :func:`cortex_command.install_guard.check_in_flight_install` and
the carve-outs it uses. The guard's job is to abort the upgrade
dispatch path while an overnight runner is alive mid-session so a
concurrent ``uv tool install --reinstall`` cannot clobber the running
package on disk. Carve-outs keep it from misfiring on explicit user
opt-out and the cancel-force bypass — and a liveness check prevents a
permanent lockout when the runner crashes leaving a stale pointer
behind.

Test matrix:

* ``test_install_aborts_on_executing_phase_with_live_runner`` — real
  in-flight (phase=``executing`` + live pid).
* ``test_install_succeeds_when_phase_complete`` — pointer present but
  phase=``complete`` is a normal fresh-install state.
* ``test_install_succeeds_when_runner_pid_dead`` — phase=``executing``
  BUT runner.pid points at a dead process; stale pointer treated as
  not-in-flight; stderr recommends ``cancel --force``.
* ``test_bypass_via_env_var`` — ``CORTEX_ALLOW_INSTALL_DURING_RUN=1``
  unblocks.
* ``test_cancel_force_bypass`` — the three argparse-equivalent
  orderings of ``overnight cancel <id> --force`` all bypass.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import psutil
import pytest

from cortex_command import install_guard
from cortex_command.install_guard import (
    InstallInFlightError,
    check_in_flight_install,
)
from cortex_command.overnight import ipc


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Clear env vars so each test is in a clean slate."""
    for var in (
        "CORTEX_ALLOW_INSTALL_DURING_RUN",
    ):
        monkeypatch.delenv(var, raising=False)
    yield


@pytest.fixture
def isolated_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Path]:
    """Redirect ``ACTIVE_SESSION_PATH`` into a tmp-path ``HOME``.

    The guard reads ``~/.local/share/overnight-sessions/active-session.json``
    via :data:`install_guard._ACTIVE_SESSION_PATH` (its own copy of the
    path so the read can avoid importing ``ipc`` — see install_guard.py
    docstring). The legacy ``ipc.ACTIVE_SESSION_PATH`` is also patched so
    any code path that still goes through ``ipc`` (e.g. write_active_session
    in fixtures) stays aligned. Each test gets a fresh filesystem slate.
    """
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    active_path = (
        fake_home
        / ".local"
        / "share"
        / "overnight-sessions"
        / "active-session.json"
    )
    monkeypatch.setattr(ipc, "ACTIVE_SESSION_PATH", active_path)
    monkeypatch.setattr(install_guard, "_ACTIVE_SESSION_PATH", active_path)
    yield fake_home


def _live_start_time_iso() -> str:
    """Return this test process's create_time as ISO-8601 (UTC)."""
    epoch = psutil.Process(os.getpid()).create_time()
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def _write_active_pointer(
    active_path: Path,
    session_id: str,
    session_dir: Path,
    phase: str,
    pid: int,
    start_time: str,
) -> None:
    """Write an active-session.json pointer payload matching ipc schema."""
    active_path.parent.mkdir(parents=True, exist_ok=True)
    active_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "magic": "cortex-runner-v1",
                "pid": pid,
                "pgid": pid,
                "start_time": start_time,
                "session_id": session_id,
                "session_dir": str(session_dir),
                "repo_path": str(session_dir),
                "phase": phase,
            }
        ),
        encoding="utf-8",
    )


def _write_runner_pid(
    session_dir: Path,
    session_id: str,
    pid: int,
    start_time: str,
) -> None:
    """Write a runner.pid file into the session dir."""
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "runner.pid").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "magic": "cortex-runner-v1",
                "pid": pid,
                "pgid": pid,
                "start_time": start_time,
                "session_id": session_id,
                "session_dir": str(session_dir),
                "repo_path": str(session_dir),
            }
        ),
        encoding="utf-8",
    )


def _setup_live_inflight(
    tmp_path: Path,
    session_id: str = "session-test-20260424-000000",
) -> Path:
    """Write an active-pointer + runner.pid for *this* live test pid."""
    session_dir = tmp_path / "sessions" / session_id
    start_time = _live_start_time_iso()
    _write_active_pointer(
        ipc.ACTIVE_SESSION_PATH,
        session_id=session_id,
        session_dir=session_dir,
        phase="executing",
        pid=os.getpid(),
        start_time=start_time,
    )
    _write_runner_pid(
        session_dir,
        session_id=session_id,
        pid=os.getpid(),
        start_time=start_time,
    )
    return session_dir


# ---------------------------------------------------------------------------
# (i) Real in-flight: phase=executing AND live pid
# ---------------------------------------------------------------------------

def test_install_aborts_on_executing_phase_with_live_runner(
    isolated_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    session_id = "session-test-20260424-000000"
    _setup_live_inflight(tmp_path, session_id=session_id)
    monkeypatch.setattr(sys, "argv", ["cortex", "upgrade"])

    with pytest.raises(SystemExit) as excinfo:
        check_in_flight_install()
    assert excinfo.value.code == 1

    captured = capsys.readouterr()
    assert session_id in captured.err
    assert "in-flight" in captured.err
    assert "cancel" in captured.err
    assert "CORTEX_ALLOW_INSTALL_DURING_RUN" in captured.err


# ---------------------------------------------------------------------------
# (ii) Phase=complete is a no-op
# ---------------------------------------------------------------------------

def test_install_succeeds_when_phase_complete(
    isolated_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id = "session-test-20260424-000001"
    session_dir = tmp_path / "sessions" / session_id
    _write_active_pointer(
        ipc.ACTIVE_SESSION_PATH,
        session_id=session_id,
        session_dir=session_dir,
        phase="complete",
        pid=os.getpid(),
        start_time=_live_start_time_iso(),
    )
    monkeypatch.setattr(sys, "argv", ["cortex", "upgrade"])

    # Must not raise.
    check_in_flight_install()


# ---------------------------------------------------------------------------
# (iii) Stale pointer: phase=executing BUT runner.pid dead → allow install
# ---------------------------------------------------------------------------

def test_install_succeeds_when_runner_pid_dead(
    isolated_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    session_id = "session-test-20260424-000002"
    session_dir = tmp_path / "sessions" / session_id

    _write_active_pointer(
        ipc.ACTIVE_SESSION_PATH,
        session_id=session_id,
        session_dir=session_dir,
        phase="executing",
        pid=0,
        start_time="1970-01-01T00:00:00+00:00",
    )
    # runner.pid refers to PID 0 which psutil rejects as NoSuchProcess.
    _write_runner_pid(
        session_dir,
        session_id=session_id,
        pid=0,
        start_time="1970-01-01T00:00:00+00:00",
    )
    monkeypatch.setattr(sys, "argv", ["cortex", "upgrade"])

    # Must not raise — stale pointer is warned about, not fatal.
    check_in_flight_install()

    captured = capsys.readouterr()
    assert "stale" in captured.err
    assert session_id in captured.err
    assert "cancel" in captured.err


def test_install_succeeds_when_runner_pid_missing(
    isolated_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Active pointer says executing; runner.pid does not exist."""
    session_id = "session-test-20260424-000003"
    session_dir = tmp_path / "sessions" / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    _write_active_pointer(
        ipc.ACTIVE_SESSION_PATH,
        session_id=session_id,
        session_dir=session_dir,
        phase="executing",
        pid=os.getpid(),
        start_time=_live_start_time_iso(),
    )
    monkeypatch.setattr(sys, "argv", ["cortex", "upgrade"])
    # Must not raise — missing runner.pid is treated as crashed-runner.
    check_in_flight_install()


# ---------------------------------------------------------------------------
# (iv) Explicit opt-out via env var
# ---------------------------------------------------------------------------

def test_bypass_via_env_var(
    isolated_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_live_inflight(tmp_path, session_id="session-test-20260424-000004")
    monkeypatch.setenv("CORTEX_ALLOW_INSTALL_DURING_RUN", "1")
    monkeypatch.setattr(sys, "argv", ["cortex", "upgrade"])

    # Must not raise — env var overrides.
    check_in_flight_install()


# ---------------------------------------------------------------------------
# (v) Cancel-force bypass — three argparse orderings
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "argv",
    [
        # Positional session-id then --force.
        ["cortex", "overnight", "cancel", "session-xyz", "--force"],
        # --force then positional session-id.
        ["cortex", "overnight", "cancel", "--force", "session-xyz"],
        # `python -m cortex_command.cli` invocation form — argv[0]
        # differs but argv[1:] is what the guard inspects (via
        # parse_known_args, which skips unrecognised leading tokens).
        [
            "python",
            "-m",
            "cortex_command.cli",
            "overnight",
            "cancel",
            "session-xyz",
            "--force",
        ],
    ],
    ids=["positional-then-flag", "flag-then-positional", "python-m-form"],
)
def test_cancel_force_bypass(
    argv: list[str],
    isolated_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_live_inflight(tmp_path, session_id="session-test-20260424-000005")
    monkeypatch.setattr(sys, "argv", argv)

    # Must not raise — cancel-bypass applies.
    check_in_flight_install()


def test_cancel_without_force_does_not_bypass(
    isolated_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A plain ``cancel`` without ``--force`` must NOT bypass the guard.

    This guards against the bypass getting too permissive — only the
    explicit force-cancel path short-circuits the guard. Other cancel
    flows should be protected so a regular-cancel-during-install race
    is still surfaced.
    """
    session_id = "session-test-20260424-000006"
    _setup_live_inflight(tmp_path, session_id=session_id)

    monkeypatch.setattr(
        sys, "argv", ["cortex", "overnight", "cancel", session_id]
    )
    with pytest.raises(SystemExit):
        check_in_flight_install()


# ---------------------------------------------------------------------------
# No-pointer case
# ---------------------------------------------------------------------------

def test_install_succeeds_with_no_active_session(
    isolated_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fresh machine with no overnight pointer must install cleanly."""
    assert not ipc.ACTIVE_SESSION_PATH.exists()
    monkeypatch.setattr(sys, "argv", ["cortex", "upgrade"])

    # Must not raise.
    check_in_flight_install()


# ---------------------------------------------------------------------------
# Malformed pointer (defensive)
# ---------------------------------------------------------------------------

def test_malformed_active_pointer_is_lenient(
    isolated_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pointer missing ``session_dir`` is treated as stale, not fatal."""
    ipc.ACTIVE_SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    ipc.ACTIVE_SESSION_PATH.write_text(
        json.dumps({"phase": "executing"}), encoding="utf-8"
    )
    monkeypatch.setattr(sys, "argv", ["cortex", "upgrade"])
    check_in_flight_install()  # Must not raise.
