"""Verification tests for Task 14 — ``overnight_cancel`` MCP tool.

Covers R6: the tool reads ``runner.pid``, calls
:func:`ipc.verify_runner_pid`, sends ``SIGTERM`` to the recorded PG,
polls for exit up to 12 s, escalates to ``SIGKILL`` on timeout, and
self-heals the lock when ``force=True`` against a SIGSTOP'd /
unkillable runner.

Each test that spawns a real subprocess registers it on a per-test
finalizer so the suite never leaks live PGs across tests, even on
assertion failure. The 12 s outer cap is patched down to ~1.5 s in
tests that exercise the timeout path so a single failed case never
balloons the suite to 12 s wall-clock.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil
import pytest

from cortex_command.mcp_server import tools
from cortex_command.mcp_server.schema import CancelInput, CancelOutput
from cortex_command.overnight import cli_handler, ipc

# Spawns real subprocesses with their own PGs — keep serialized against the
# other subprocess-spawning suites (R26 / Task 20).
pytestmark = pytest.mark.serial


# ---------------------------------------------------------------------------
# Subprocess fixtures
# ---------------------------------------------------------------------------


def _terminate_pg_safely(pgid: int) -> None:
    """Best-effort PG SIGKILL — never raises."""
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        pass


def _terminate_pid_safely(pid: int) -> None:
    """Best-effort PID SIGKILL — never raises."""
    try:
        os.kill(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        pass


@pytest.fixture
def cleanup_processes():
    """Yield a list; SIGKILL every recorded ``(pid, pgid)`` on teardown.

    Tests append ``(pid, pgid)`` tuples for every spawn — the finalizer
    runs even when assertions fail, so a runaway PG cannot leak across
    tests. We attempt PG kill first (closes runner + descendants in one
    call), then fall back to PID kill in case PG kill fails because the
    PG is already gone.
    """
    spawned: list[tuple[int, int]] = []
    yield spawned
    for pid, pgid in spawned:
        _terminate_pg_safely(pgid)
        _terminate_pid_safely(pid)
        # Reap so the parent process doesn't accumulate zombies.
        try:
            os.waitpid(pid, os.WNOHANG)
        except (ChildProcessError, OSError):
            pass


def _spawn_sleep_runner(
    duration_seconds: float = 30.0,
) -> tuple[subprocess.Popen, dict]:
    """Spawn a real ``python`` subprocess in its own session.

    Returns ``(proc, pid_data_dict)``. The pid_data_dict is shaped
    exactly like ``runner.pid`` so it can be written to disk via
    :func:`_write_runner_pid_dict`.
    """
    proc = subprocess.Popen(
        [
            sys.executable,
            "-c",
            f"import time; time.sleep({duration_seconds})",
        ],
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Allow psutil to observe the process before we record its
    # create_time — racing the spawn → recorded-start_time read can
    # produce a tiny skew that the verifier still tolerates within ±2s,
    # but waiting up to 0.5 s is cheap insurance against flakiness.
    deadline = time.monotonic() + 0.5
    while time.monotonic() < deadline:
        try:
            create_time = psutil.Process(proc.pid).create_time()
            break
        except psutil.NoSuchProcess:
            time.sleep(0.01)
    else:
        create_time = time.time()

    pgid = os.getpgid(proc.pid)
    start_time_iso = datetime.fromtimestamp(
        create_time, tz=timezone.utc
    ).isoformat()
    pid_data = {
        "schema_version": 1,
        "magic": "cortex-runner-v1",
        "pid": proc.pid,
        "pgid": pgid,
        "start_time": start_time_iso,
        "session_id": "test-session",
        "session_dir": "/tmp/test-session",
        "repo_path": "/tmp/test-repo",
    }
    return proc, pid_data


def _spawn_sigterm_ignoring_runner_with_grandchild(
    grandchild_sleep: float = 30.0,
) -> tuple[subprocess.Popen, dict, int]:
    """Spawn a runner that ignores SIGTERM and forks a SIGTERM-ignoring grandchild.

    Returns ``(runner_proc, pid_data, grandchild_pid)``. The grandchild
    is started with ``start_new_session=True`` so its PG diverges from
    the runner's — meaning the cancel tool's ``os.killpg(pgid, ...)``
    cannot reach it. Termination of the grandchild is delegated to the
    runner's in-handler tree-walker (Task 3) — but in this test the
    runner is pure-Python and does not install Task 3's handler. We
    instead emulate the runner's tree-walk by having the parent install
    a SIGTERM handler that walks ``psutil.Process(os.getpid()).children``
    on receipt and SIGKILLs each — matching Task 3's contract. This
    keeps the test focused on the cancel-tool composed path: outer
    SIGTERM-to-PG → runner-SIGTERM-handler → grandchild reaped.
    """
    runner_code = f"""
import os
import signal
import subprocess
import sys
import time

import psutil


def handle_sigterm(signum, frame):
    # Mimic Task 3's tree-walker — SIGKILL all descendants on SIGTERM.
    try:
        descendants = psutil.Process(os.getpid()).children(recursive=True)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        descendants = []
    for proc in descendants:
        try:
            proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    sys.exit(0)


signal.signal(signal.SIGTERM, handle_sigterm)

grandchild = subprocess.Popen(
    [sys.executable, "-c", "import time; time.sleep({grandchild_sleep})"],
    start_new_session=True,
    stdin=subprocess.DEVNULL,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
sys.stdout.write(str(grandchild.pid) + "\\n")
sys.stdout.flush()

while True:
    time.sleep(0.5)
"""
    proc = subprocess.Popen(
        [sys.executable, "-c", runner_code],
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )

    # Read the grandchild PID line from runner stdout — line-buffered
    # write + flush from the runner script means this is bounded.
    assert proc.stdout is not None
    grandchild_line = proc.stdout.readline().strip()
    grandchild_pid = int(grandchild_line)

    # Wait briefly for psutil to see the runner.
    deadline = time.monotonic() + 0.5
    while time.monotonic() < deadline:
        try:
            create_time = psutil.Process(proc.pid).create_time()
            break
        except psutil.NoSuchProcess:
            time.sleep(0.01)
    else:
        create_time = time.time()

    pgid = os.getpgid(proc.pid)
    start_time_iso = datetime.fromtimestamp(
        create_time, tz=timezone.utc
    ).isoformat()
    pid_data = {
        "schema_version": 1,
        "magic": "cortex-runner-v1",
        "pid": proc.pid,
        "pgid": pgid,
        "start_time": start_time_iso,
        "session_id": "test-session",
        "session_dir": "/tmp/test-session",
        "repo_path": "/tmp/test-repo",
    }
    return proc, pid_data, grandchild_pid


def _write_runner_pid_dict(session_dir: Path, pid_data: dict) -> None:
    """Write a runner.pid file under ``session_dir`` with the given payload."""
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "runner.pid").write_text(
        json.dumps(pid_data, indent=2, sort_keys=True), encoding="utf-8"
    )


def _make_session_dir(repo_path: Path, session_id: str) -> Path:
    """Return the canonical per-session dir under ``repo_path``."""
    return repo_path / "lifecycle" / "sessions" / session_id


def _patch_active_session_to_tmp(monkeypatch, tmp_path: Path) -> None:
    """Redirect the active-session pointer to a tmp file.

    Prevents tests from clobbering the user's real
    ``~/.local/share/overnight-sessions/active-session.json``.
    """
    monkeypatch.setattr(
        ipc, "ACTIVE_SESSION_PATH", tmp_path / "active-session.json"
    )


def _shrink_cancel_budget(monkeypatch, seconds: float = 1.5) -> None:
    """Patch the 12 s graceful budget down so timeout tests stay snappy.

    Callers that test the SIGSTOP'd-runner timeout path otherwise pay
    the full 12 s — and we have two such tests, plus the post-SIGKILL
    settle window (default 1 s). Shrinking to 1.5 s keeps cumulative
    test time bounded while still being long enough for the runner to
    exit cleanly under the live-runner-cancel test.
    """
    monkeypatch.setattr(tools, "_CANCEL_GRACEFUL_TIMEOUT_SECONDS", seconds)
    monkeypatch.setattr(
        tools, "_CANCEL_POST_SIGKILL_SETTLE_SECONDS", min(seconds, 0.5)
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_live_runner_cancel(monkeypatch, tmp_path, cleanup_processes) -> None:
    """A real running subprocess is cancelled, lock is unlinked."""
    _patch_active_session_to_tmp(monkeypatch, tmp_path)
    repo_path = tmp_path
    monkeypatch.setattr(
        cli_handler, "_resolve_repo_path", lambda: repo_path
    )

    session_id = "overnight-2026-04-24-livecancel"
    session_dir = _make_session_dir(repo_path, session_id)

    proc, pid_data = _spawn_sleep_runner(duration_seconds=30.0)
    cleanup_processes.append((proc.pid, pid_data["pgid"]))
    pid_data["session_id"] = session_id
    pid_data["session_dir"] = str(session_dir)
    pid_data["repo_path"] = str(repo_path)
    _write_runner_pid_dict(session_dir, pid_data)

    # Normal 12 s budget is fine here — sleep responds to SIGTERM in
    # well under a second on every platform we care about.
    result = asyncio.run(
        tools.overnight_cancel(CancelInput(session_id=session_id))
    )

    assert isinstance(result, CancelOutput)
    assert result.cancelled is True
    assert result.reason == "cancelled"
    assert "SIGTERM" in result.signal_sent
    assert result.pid_file_unlinked is True
    assert not (session_dir / "runner.pid").exists()
    assert result.pid == proc.pid


def test_stale_pid_self_heal(monkeypatch, tmp_path) -> None:
    """A runner.pid for a dead PID is unlinked; reason is start_time_skew."""
    _patch_active_session_to_tmp(monkeypatch, tmp_path)
    repo_path = tmp_path
    monkeypatch.setattr(
        cli_handler, "_resolve_repo_path", lambda: repo_path
    )

    session_id = "overnight-2026-04-24-stalepid"
    session_dir = _make_session_dir(repo_path, session_id)

    # Pick a PID that is unlikely to be running. spawn-and-reap a
    # short-lived subprocess and use its now-dead pid.
    short = subprocess.Popen(
        [sys.executable, "-c", "import sys; sys.exit(0)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    short.wait(timeout=5)
    dead_pid = short.pid

    pid_data = {
        "schema_version": 1,
        "magic": "cortex-runner-v1",
        "pid": dead_pid,
        "pgid": dead_pid,
        "start_time": "2026-04-24T22:00:00+00:00",
        "session_id": session_id,
        "session_dir": str(session_dir),
        "repo_path": str(repo_path),
    }
    _write_runner_pid_dict(session_dir, pid_data)

    result = asyncio.run(
        tools.overnight_cancel(CancelInput(session_id=session_id))
    )

    assert result.cancelled is False
    # Spec R6 enumerates ``no_runner_pid`` for "no runner.pid file
    # present"; stale-pid self-heal is bucketed under
    # ``start_time_skew`` per the granular classifier.
    assert result.reason == "start_time_skew"
    assert result.pid_file_unlinked is True
    assert not (session_dir / "runner.pid").exists()
    assert result.signal_sent == []


def test_no_runner_pid_returns_sentinel(monkeypatch, tmp_path) -> None:
    """A session without runner.pid returns ``no_runner_pid``."""
    _patch_active_session_to_tmp(monkeypatch, tmp_path)
    repo_path = tmp_path
    monkeypatch.setattr(
        cli_handler, "_resolve_repo_path", lambda: repo_path
    )

    session_id = "overnight-2026-04-24-nopid"
    session_dir = _make_session_dir(repo_path, session_id)
    session_dir.mkdir(parents=True, exist_ok=True)

    result = asyncio.run(
        tools.overnight_cancel(CancelInput(session_id=session_id))
    )

    assert result.cancelled is False
    assert result.reason == "no_runner_pid"
    assert result.signal_sent == []
    assert result.pid_file_unlinked is False
    assert result.pid is None


def test_magic_mismatch_refusal(monkeypatch, tmp_path) -> None:
    """A runner.pid with bad magic is rejected with reason=magic_mismatch."""
    _patch_active_session_to_tmp(monkeypatch, tmp_path)
    repo_path = tmp_path
    monkeypatch.setattr(
        cli_handler, "_resolve_repo_path", lambda: repo_path
    )

    session_id = "overnight-2026-04-24-magic"
    session_dir = _make_session_dir(repo_path, session_id)

    pid_data = {
        "schema_version": 1,
        "magic": "wrong-magic",
        "pid": os.getpid(),
        "pgid": os.getpgrp(),
        "start_time": "2026-04-24T22:00:00+00:00",
        "session_id": session_id,
        "session_dir": str(session_dir),
        "repo_path": str(repo_path),
    }
    _write_runner_pid_dict(session_dir, pid_data)

    result = asyncio.run(
        tools.overnight_cancel(CancelInput(session_id=session_id))
    )

    assert result.cancelled is False
    assert result.reason == "magic_mismatch"
    assert result.signal_sent == []
    assert result.pid_file_unlinked is True


def test_start_time_skew_refusal(
    monkeypatch, tmp_path, cleanup_processes
) -> None:
    """A live PID with a wrong-recorded start_time is rejected as skew."""
    _patch_active_session_to_tmp(monkeypatch, tmp_path)
    repo_path = tmp_path
    monkeypatch.setattr(
        cli_handler, "_resolve_repo_path", lambda: repo_path
    )

    session_id = "overnight-2026-04-24-skew"
    session_dir = _make_session_dir(repo_path, session_id)

    proc, pid_data = _spawn_sleep_runner(duration_seconds=30.0)
    cleanup_processes.append((proc.pid, pid_data["pgid"]))

    # Force a 1-hour start_time skew — well outside the ±2 s tolerance.
    pid_data["start_time"] = "2020-01-01T00:00:00+00:00"
    pid_data["session_id"] = session_id
    pid_data["session_dir"] = str(session_dir)
    pid_data["repo_path"] = str(repo_path)
    _write_runner_pid_dict(session_dir, pid_data)

    result = asyncio.run(
        tools.overnight_cancel(CancelInput(session_id=session_id))
    )

    assert result.cancelled is False
    assert result.reason == "start_time_skew"
    assert result.signal_sent == []
    assert result.pid_file_unlinked is True


def _force_unkillable_runner_view(monkeypatch) -> list[tuple[int, int]]:
    """Patch the cancel-tool exit-watcher AND ``os.killpg`` for portability.

    Simulates a SIGSTOP'd / unkillable runner without depending on the
    host kernel's signal-delivery semantics for stopped processes —
    macOS, for instance, delivers SIGTERM to a SIGSTOP'd process via
    ``killpg`` and turns it into a zombie almost immediately, so the
    real signal path on Darwin wouldn't reach the
    ``signal_not_delivered_within_timeout`` branch the spec calls out.

    Returns a captured-calls list shared between the watcher and the
    ``os.killpg`` interceptor so the test can assert which signals were
    *attempted* without relying on the kernel actually delivering them.
    The patched ``os.killpg`` records the call and returns ``None``
    (success) so the handler proceeds; the watcher always returns
    ``True`` so the handler always reaches the SIGKILL escalation and
    timeout branches.
    """
    captured: list[tuple[int, int]] = []

    def _mocked_killpg(pgid: int, sig: int) -> None:
        captured.append((pgid, sig))
        # Don't actually deliver — we want the runner subprocess kept
        # alive for the cleanup_processes finalizer.
        return None

    monkeypatch.setattr(tools, "_is_pid_running", lambda _pid: True)
    monkeypatch.setattr(os, "killpg", _mocked_killpg)
    return captured


def test_sigstopd_runner_force_false_leaves_lock(
    monkeypatch, tmp_path, cleanup_processes
) -> None:
    """SIGSTOP'd runner with force=False reports timeout; lock remains.

    Uses a real subprocess + the unkillable-watcher / mocked-killpg
    patch so the test exercises the actual cancel-handler control flow
    (verify → SIGTERM-attempt → poll → SIGKILL-attempt → settle →
    timeout-decision) without depending on host-kernel signal-delivery
    quirks against stopped processes (macOS terminates SIGSTOP'd
    processes via ``killpg(SIGTERM)`` almost immediately, which would
    short-circuit the timeout branch this test is asserting against).
    """
    _patch_active_session_to_tmp(monkeypatch, tmp_path)
    _shrink_cancel_budget(monkeypatch)
    captured = _force_unkillable_runner_view(monkeypatch)

    repo_path = tmp_path
    monkeypatch.setattr(
        cli_handler, "_resolve_repo_path", lambda: repo_path
    )

    session_id = "overnight-2026-04-24-sigstopf"
    session_dir = _make_session_dir(repo_path, session_id)

    proc, pid_data = _spawn_sleep_runner(duration_seconds=60.0)
    cleanup_processes.append((proc.pid, pid_data["pgid"]))
    pid_data["session_id"] = session_id
    pid_data["session_dir"] = str(session_dir)
    pid_data["repo_path"] = str(repo_path)
    _write_runner_pid_dict(session_dir, pid_data)

    result = asyncio.run(
        tools.overnight_cancel(
            CancelInput(session_id=session_id, force=False)
        )
    )

    assert result.cancelled is False
    assert result.reason == "signal_not_delivered_within_timeout"
    assert "SIGTERM" in result.signal_sent
    assert "SIGKILL" in result.signal_sent
    # ``force=False`` must NOT unlink the lock per spec.
    assert result.pid_file_unlinked is False
    assert (session_dir / "runner.pid").exists()
    # The handler attempted both SIGTERM and SIGKILL on the runner's PG.
    assert (pid_data["pgid"], signal.SIGTERM) in captured
    assert (pid_data["pgid"], signal.SIGKILL) in captured


def test_sigstopd_runner_force_true_unlinks_lock(
    monkeypatch, tmp_path, cleanup_processes
) -> None:
    """SIGSTOP'd runner with force=True reports timeout AND unlinks lock."""
    _patch_active_session_to_tmp(monkeypatch, tmp_path)
    _shrink_cancel_budget(monkeypatch)
    captured = _force_unkillable_runner_view(monkeypatch)

    repo_path = tmp_path
    monkeypatch.setattr(
        cli_handler, "_resolve_repo_path", lambda: repo_path
    )

    session_id = "overnight-2026-04-24-sigstopt"
    session_dir = _make_session_dir(repo_path, session_id)

    proc, pid_data = _spawn_sleep_runner(duration_seconds=60.0)
    cleanup_processes.append((proc.pid, pid_data["pgid"]))
    pid_data["session_id"] = session_id
    pid_data["session_dir"] = str(session_dir)
    pid_data["repo_path"] = str(repo_path)
    _write_runner_pid_dict(session_dir, pid_data)

    result = asyncio.run(
        tools.overnight_cancel(
            CancelInput(session_id=session_id, force=True)
        )
    )

    assert result.cancelled is False
    assert result.reason == "signal_not_delivered_within_timeout"
    assert "SIGTERM" in result.signal_sent
    assert "SIGKILL" in result.signal_sent
    # ``force=True`` MUST unlink the lock so a fresh run can claim
    # the O_EXCL slot.
    assert result.pid_file_unlinked is True
    assert not (session_dir / "runner.pid").exists()
    assert (pid_data["pgid"], signal.SIGTERM) in captured
    assert (pid_data["pgid"], signal.SIGKILL) in captured


def test_grandchild_in_separate_pg_reaped_via_tree_walk(
    monkeypatch, tmp_path, cleanup_processes
) -> None:
    """Composed cancel reaps a SIGTERM-handling-runner's separate-PG grandchild.

    Verifies the end-to-end path Task 14 closes: cancel sends SIGTERM
    to the runner's PG → runner's own SIGTERM handler walks descendants
    (Task 3 contract, emulated here in the spawned script) → the
    grandchild — whose PG diverges from the runner's because it was
    spawned with ``start_new_session=True`` — is reached and reaped
    even though the cancel tool's ``os.killpg`` cannot signal it
    directly.
    """
    _patch_active_session_to_tmp(monkeypatch, tmp_path)
    repo_path = tmp_path
    monkeypatch.setattr(
        cli_handler, "_resolve_repo_path", lambda: repo_path
    )

    session_id = "overnight-2026-04-24-grand"
    session_dir = _make_session_dir(repo_path, session_id)

    runner_proc, pid_data, grandchild_pid = (
        _spawn_sigterm_ignoring_runner_with_grandchild(
            grandchild_sleep=60.0
        )
    )
    cleanup_processes.append((runner_proc.pid, pid_data["pgid"]))
    cleanup_processes.append((grandchild_pid, grandchild_pid))
    pid_data["session_id"] = session_id
    pid_data["session_dir"] = str(session_dir)
    pid_data["repo_path"] = str(repo_path)
    _write_runner_pid_dict(session_dir, pid_data)

    # Sanity: grandchild is alive before cancel.
    assert psutil.pid_exists(grandchild_pid)

    result = asyncio.run(
        tools.overnight_cancel(CancelInput(session_id=session_id))
    )

    assert isinstance(result, CancelOutput)
    assert result.cancelled is True
    assert result.reason == "cancelled"
    # Grandchild must be reaped — verifies the composed cancel-path
    # matches Task 3's in-handler tree-walk closure (the cancel tool
    # delegates descendant cleanup to the runner's SIGTERM handler).
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if not psutil.pid_exists(grandchild_pid):
            break
        time.sleep(0.05)
    else:
        pytest.fail(
            f"grandchild PID {grandchild_pid} survived overnight_cancel"
        )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
