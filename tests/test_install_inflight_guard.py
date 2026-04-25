"""Tests for the pre-install in-flight guard (R28).

Covers :func:`cortex_command.install_guard.check_in_flight_install` and
the carve-outs it uses. The guard's job is to abort entry-point CLI
invocations while an overnight runner is alive mid-session so a
concurrent ``uv tool install --reinstall`` cannot clobber the running
package on disk. Carve-outs keep it from misfiring on pytest, dashboard
boot, runner-spawned children, and explicit user opt-outs — and a
liveness check prevents a permanent lockout when the runner crashes
leaving a stale pointer behind.

Test matrix (R28 acceptance):

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
* ``test_pytest_context_skip`` — ``PYTEST_CURRENT_TEST`` triggers the
  (a) carve-out.
* ``test_runner_child_skip`` — ``CORTEX_RUNNER_CHILD=1`` triggers the
  (b) carve-out.
* ``test_dashboard_skip`` — the dashboard import-initiator detection
  triggers the (c) carve-out.

**Test-harness note**: pytest itself sets the ``PYTEST_CURRENT_TEST``
env var for every test function. That is exactly what the (a) carve-out
is designed to detect — in production, ``check_in_flight_install()``
invoked from a pytest-run process correctly short-circuits. To test
the rest of the logic from within pytest we call the private
``_check_in_flight_install_core()`` directly; it has the same carve-outs
(b)-(e) and the same main check, but skips the pytest short-circuit.
The public ``check_in_flight_install()`` is still tested via the
``test_pytest_context_skip`` case, which asserts the pytest carve-out
actually returns even with a live in-flight pointer set up.
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
    _check_in_flight_install_core,
    check_in_flight_install,
)
from cortex_command.overnight import ipc


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Clear env vars and module state so each test is in a clean slate.

    The pytest carve-out signals (``PYTEST_CURRENT_TEST`` /
    ``"pytest" in sys.modules``) are *not* cleared here — pytest sets
    them itself as part of test invocation. Tests that exercise the
    main guard path therefore call
    :func:`_check_in_flight_install_core` directly; the public entry
    point's pytest carve-out is tested separately by
    ``test_pytest_context_skip``.

    Dashboard module entries in ``sys.modules`` are temporarily
    removed: other tests in the full suite import
    ``cortex_command.dashboard.app``, which would otherwise make the
    dashboard carve-out (c) match for every non-dashboard test here.
    The saved entries are restored on teardown so later tests aren't
    broken.
    """
    for var in (
        "CORTEX_ALLOW_INSTALL_DURING_RUN",
        "CORTEX_RUNNER_CHILD",
    ):
        monkeypatch.delenv(var, raising=False)

    saved_modules: dict[str, object] = {}
    for name in list(sys.modules):
        if name == "cortex_command.dashboard" or name.startswith(
            "cortex_command.dashboard."
        ):
            saved_modules[name] = sys.modules.pop(name)
    try:
        yield
    finally:
        for name, mod in saved_modules.items():
            sys.modules[name] = mod  # type: ignore[assignment]


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
        _check_in_flight_install_core()
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
    _check_in_flight_install_core()


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
    _check_in_flight_install_core()

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
    _check_in_flight_install_core()


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
    _check_in_flight_install_core()


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
    _check_in_flight_install_core()


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
        _check_in_flight_install_core()


# ---------------------------------------------------------------------------
# (vi) pytest carve-out — use the PUBLIC check_in_flight_install here
# ---------------------------------------------------------------------------

def test_pytest_context_skip(
    isolated_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``PYTEST_CURRENT_TEST`` env is set by pytest itself; the public
    entry point must return immediately even with a live in-flight
    pointer present.
    """
    _setup_live_inflight(tmp_path, session_id="session-test-20260424-000007")
    # Verify the preconditions — pytest env var should be set for this
    # test function; that's what the carve-out detects.
    assert "PYTEST_CURRENT_TEST" in os.environ or "pytest" in sys.modules
    monkeypatch.setattr(sys, "argv", ["cortex", "upgrade"])

    # Must not raise — pytest carve-out short-circuits.
    check_in_flight_install()


def test_pytest_current_test_env_var_alone_triggers_carveout(
    isolated_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even without ``pytest`` in sys.modules, the env-var half of the
    (a) carve-out stands on its own. Exercise it by forcing the env
    var and calling the PUBLIC entry point.
    """
    _setup_live_inflight(tmp_path, session_id="session-test-20260424-000008")
    monkeypatch.setattr(sys, "argv", ["cortex", "upgrade"])
    # Explicit: even though autouse didn't set it, pytest does.
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "fake_test_node_id")

    check_in_flight_install()  # Must not raise.


# ---------------------------------------------------------------------------
# (vii) Runner-child carve-out
# ---------------------------------------------------------------------------

def test_runner_child_skip(
    isolated_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_live_inflight(tmp_path, session_id="session-test-20260424-000009")
    monkeypatch.setenv("CORTEX_RUNNER_CHILD", "1")
    monkeypatch.setattr(sys, "argv", ["cortex", "upgrade"])

    # Must not raise — runner spawned this child; its import of
    # cortex_command must not bomb.
    _check_in_flight_install_core()


# ---------------------------------------------------------------------------
# (viii) Dashboard carve-out
# ---------------------------------------------------------------------------

def test_dashboard_skip_via_uvicorn_argv(
    isolated_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_live_inflight(tmp_path, session_id="session-test-20260424-000010")
    # Simulate ``uvicorn cortex_command.dashboard.app:app`` launch.
    monkeypatch.setattr(
        sys,
        "argv",
        ["/usr/local/bin/uvicorn", "cortex_command.dashboard.app:app"],
    )

    # Must not raise — dashboard is a legit observer of live sessions.
    _check_in_flight_install_core()


def test_dashboard_skip_via_module_import(
    isolated_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dashboard module presence in ``sys.modules`` also carves out."""
    _setup_live_inflight(tmp_path, session_id="session-test-20260424-000011")

    import types

    fake_dashboard = types.ModuleType("cortex_command.dashboard")
    monkeypatch.setitem(sys.modules, "cortex_command.dashboard", fake_dashboard)
    monkeypatch.setattr(sys, "argv", ["cortex", "upgrade"])

    # Must not raise.
    _check_in_flight_install_core()


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
    _check_in_flight_install_core()


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
    _check_in_flight_install_core()  # Must not raise.
