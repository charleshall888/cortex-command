"""Tests for the async-spawn handshake in ``cli_handler.handle_start``.

Covers spec R2 / R18 (Task 6):

  - happy path: handshake completes within a fraction of the budget
    when the child writes ``runner.pid`` quickly.
  - slow spawn: handshake at ~4.5 seconds still returns ``started: True``.
  - timeout-with-orphan-kill: child never writes ``runner.pid``; the
    parent times out at 5 s, terminates the orphan child, and a late
    ``runner.pid`` write does not appear after return.
  - runner-died: the child writes ``runner.pid`` then exits before the
    parent's liveness probe runs; ``os.kill(pid, 0)`` raises
    ``ProcessLookupError`` and the parent returns
    ``started: False, error_class: spawn_died``.
  - ``--launchd`` flag: bypasses the handshake fork entirely.
  - ``--dry-run`` flag: bypasses the handshake fork and emits
    ``DRY-RUN`` lines on the parent's stdout.

The runner-died test cannot reproduce the production kernel-scheduler
race in pure Python — but with the liveness probe added, the load-
bearing behavior under test is the LIVENESS-PROBE BRANCH, not the race
itself: any time ``os.kill(pid, 0)`` raises ``ProcessLookupError`` the
function returns ``started: False, error_class: spawn_died``.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from typing import Iterator

import pytest

from cortex_command.overnight import cli_handler
from cortex_command.overnight.scheduler import spawn as spawn_module


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _write_minimal_state(session_dir: Path, session_id: str) -> Path:
    """Write a minimal but loadable ``overnight-state.json`` to ``session_dir``."""
    session_dir.mkdir(parents=True, exist_ok=True)
    state_path = session_dir / "overnight-state.json"
    state_path.write_text(
        json.dumps(
            {
                "session_id": session_id,
                "phase": "executing",
                "plan_ref": "cortex/lifecycle/overnight-plan.md",
                "current_round": 1,
                "started_at": "2026-04-26T00:00:00+00:00",
                "updated_at": "2026-04-26T00:00:00+00:00",
                "features": {},
            }
        ),
        encoding="utf-8",
    )
    return state_path


def _build_args(state_path: Path, **overrides) -> argparse.Namespace:
    """Construct an argparse.Namespace mimicking ``cortex overnight start`` defaults."""
    base = dict(
        state=str(state_path),
        time_limit=None,
        max_rounds=None,
        tier="simple",
        dry_run=False,
        format="json",
        launchd=False,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


# ---------------------------------------------------------------------------
# Liveness-helper unit tests (no fork required).
# ---------------------------------------------------------------------------


def test_wait_for_pid_file_returns_none_on_timeout(tmp_path: Path) -> None:
    """A path that never appears yields ``None`` after the timeout."""
    pid_path = tmp_path / "runner.pid"

    start = time.monotonic()
    result = spawn_module.wait_for_pid_file(
        pid_path, timeout=0.2, poll_interval=0.05
    )
    elapsed = time.monotonic() - start

    assert result is None
    assert elapsed >= 0.18  # at least the timeout
    assert elapsed < 1.0    # bounded


def test_wait_for_pid_file_returns_pid_on_live_process(tmp_path: Path) -> None:
    """When ``runner.pid`` points at this very test process, liveness verifies."""
    pid_path = tmp_path / "runner.pid"
    pid_path.write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")

    result = spawn_module.wait_for_pid_file(
        pid_path, timeout=1.0, poll_interval=0.01
    )
    assert result == os.getpid()


def test_wait_for_pid_file_returns_none_on_dead_process(tmp_path: Path) -> None:
    """When ``runner.pid`` points at a dead PID, liveness probe returns ``None``."""
    pid_path = tmp_path / "runner.pid"

    # Spawn a quick child, capture its PID, wait for exit. Once exited
    # the PID is reaped by Popen — which is fine, the PID itself is now
    # not assigned to a live process.
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    dead_pid = child.pid

    pid_path.write_text(json.dumps({"pid": dead_pid}), encoding="utf-8")

    result = spawn_module.wait_for_pid_file(
        pid_path, timeout=0.5, poll_interval=0.01
    )
    assert result is None


# ---------------------------------------------------------------------------
# End-to-end async-spawn tests using a fake child invocation.
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake_runner_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[dict]:
    """Yield session paths + a monkeypatch hook for replacing the spawned argv.

    The async-spawn path normally execs ``python -m cortex_command.cli
    overnight start --launchd``; for tests we monkeypatch
    :func:`cli_handler._build_async_spawn_argv` to return a small
    Python program that simulates runner behavior (write
    ``runner.pid`` then sleep) without pulling in the full overnight
    runner.
    """
    session_id = "spawn-handshake-test"
    session_dir = tmp_path / "cortex" / "lifecycle" / "sessions" / session_id
    state_path = _write_minimal_state(session_dir, session_id)

    monkeypatch.setattr(
        cli_handler, "_resolve_repo_path", lambda: tmp_path
    )

    yield {
        "session_dir": session_dir,
        "state_path": state_path,
        "session_id": session_id,
    }


def _make_fake_runner_script(
    session_dir: Path,
    *,
    delay_before_pid_write: float,
    sleep_after_pid_write: float,
    exit_after_pid_write: bool = False,
) -> str:
    """Generate a Python source string for a fake runner child."""
    pid_path = session_dir / "runner.pid"
    return textwrap.dedent(
        f"""
        import json
        import os
        import sys
        import time

        time.sleep({delay_before_pid_write})

        payload = {{
            "schema_version": 1,
            "magic": "cortex-runner-v1",
            "pid": os.getpid(),
            "pgid": os.getpgid(os.getpid()),
            "start_time": "2026-04-26T00:00:00+00:00",
            "session_id": "{session_dir.name}",
            "session_dir": "{session_dir}",
            "repo_path": "/tmp",
        }}
        path = "{pid_path}"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
            f.flush()
            os.fsync(f.fileno())

        if {exit_after_pid_write!r}:
            sys.exit(0)
        time.sleep({sleep_after_pid_write})
        """
    )


def test_async_spawn_happy_path(
    fake_runner_env: dict,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """Child writes runner.pid quickly; handshake returns started: True."""
    session_dir: Path = fake_runner_env["session_dir"]
    script = _make_fake_runner_script(
        session_dir,
        delay_before_pid_write=0.1,
        sleep_after_pid_write=10.0,
    )

    def fake_argv(args, state_path):  # type: ignore[no-untyped-def]
        return [sys.executable, "-c", script]

    monkeypatch.setattr(
        cli_handler, "_build_async_spawn_argv", fake_argv
    )

    args = _build_args(fake_runner_env["state_path"])

    start = time.monotonic()
    rc = cli_handler.handle_start(args)
    elapsed = time.monotonic() - start

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    try:
        assert rc == 0
        assert payload.get("started") is True
        assert payload.get("session_id") == fake_runner_env["session_id"]
        assert isinstance(payload.get("pid"), int)
        # Sentinel cleaned up after success.
        assert not (session_dir / "runner.spawn-pending").exists()
        # Handshake budget honored — well under 5 s.
        assert elapsed < 4.0
    finally:
        # Tear down the fake child.
        pid = payload.get("pid")
        if isinstance(pid, int):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_async_spawn_slow_handshake_within_budget(
    fake_runner_env: dict,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """Child writes runner.pid at ~3.0s; handshake still succeeds before 5.0s."""
    session_dir: Path = fake_runner_env["session_dir"]
    script = _make_fake_runner_script(
        session_dir,
        delay_before_pid_write=3.0,
        sleep_after_pid_write=10.0,
    )

    def fake_argv(args, state_path):  # type: ignore[no-untyped-def]
        return [sys.executable, "-c", script]

    monkeypatch.setattr(
        cli_handler, "_build_async_spawn_argv", fake_argv
    )

    args = _build_args(fake_runner_env["state_path"])

    rc = cli_handler.handle_start(args)
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    try:
        assert rc == 0
        assert payload.get("started") is True
        pid = payload.get("pid")
        assert isinstance(pid, int)
    finally:
        pid = payload.get("pid")
        if isinstance(pid, int):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_async_spawn_timeout_live_child_left_running(
    fake_runner_env: dict,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """A live-but-slow child that never writes runner.pid is LEFT RUNNING.

    Spec R8: the old code unconditionally killed the orphan on timeout —
    THAT was the original fire-but-do-nothing bug. The handshake budget
    elapsing on a still-alive child must NOT killpg the runner; it returns
    the non-failure advisory ``spawn_unconfirmed`` (``child_alive: True``)
    and leaves the runner coming up.

    Verifies:
      - return is ``started: false`` with ``error_class: spawn_unconfirmed``
        and ``child_alive: True`` (a distinct, non-failure envelope);
      - the runner process is still alive after the shim returns;
      - the spawn-pending sentinel is cleaned up.
    """
    session_dir: Path = fake_runner_env["session_dir"]
    # Child sleeps well beyond the (shortened) budget without writing
    # runner.pid — so it is deterministically still alive at timeout.
    script = "import time; time.sleep(30)"

    def fake_argv(args, state_path):  # type: ignore[no-untyped-def]
        return [sys.executable, "-c", script]

    monkeypatch.setattr(
        cli_handler, "_build_async_spawn_argv", fake_argv
    )
    # Tighten the handshake budget so the test finishes quickly.
    monkeypatch.setattr(
        cli_handler, "_SPAWN_HANDSHAKE_TIMEOUT_SECONDS", 0.5
    )

    args = _build_args(fake_runner_env["state_path"])

    rc = cli_handler.handle_start(args)
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert rc == 1
    assert payload.get("started") is False
    assert payload.get("error_class") == "spawn_unconfirmed"
    assert payload.get("child_alive") is True
    assert not (session_dir / "runner.spawn-pending").exists()

    # The sleeper is still running — find and reap it so the test does not
    # leak a process. We do not know its PID from the envelope (the runner
    # never claimed runner.pid), so kill by the unique script marker.
    subprocess.run(
        ["pkill", "-f", "time.sleep(30)"],
        check=False,
    )


def test_fire_handshake_budget_exceeds_run_now_budget() -> None:
    """The fire-path handshake budget is a named constant > 5.0 (R8).

    At fire the runner does more cold-start work (state load, lock
    acquisition, post-sleep cold caches), so the scheduled path must wait
    longer than the run-now ``_SPAWN_HANDSHAKE_TIMEOUT_SECONDS = 5.0``
    before declaring the handshake inconclusive.
    """
    assert cli_handler._FIRE_HANDSHAKE_TIMEOUT_SECONDS > 5.0
    assert cli_handler._SPAWN_HANDSHAKE_TIMEOUT_SECONDS == 5.0


def test_scheduled_live_child_timeout_left_alive_and_outcome_written(
    fake_runner_env: dict,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """``--scheduled`` live-child timeout: no kill, runner alive, token file.

    Spec R6/R8, Task 4 verification. Uses a CONTROLLABLE child — a stub
    ``_build_async_spawn_argv`` pointing at a sleeper that sleeps ≫ the
    test-shortened fire budget and never writes ``runner.pid`` — so the
    "child is still alive at timeout" outcome is deterministic, not
    timing-flaky.

    Asserts:
      (a) no ``killpg``/``SIGKILL`` is sent (``_terminate_orphan_child``
          is never invoked, and ``os.killpg`` is never called);
      (b) ``child.poll() is None`` — the runner is left alive;
      (c) the JSON envelope is the non-failure ``spawn_unconfirmed``
          advisory (``child_alive: True``) AND the single-token
          ``<session_dir>/spawn-outcome`` file is written with
          ``spawn_unconfirmed``.
    """
    session_dir: Path = fake_runner_env["session_dir"]

    # Controllable child: sleeps far beyond the shortened fire budget and
    # never writes runner.pid → deterministically alive at timeout.
    script = "import time; time.sleep(30)"

    def fake_argv(args, state_path):  # type: ignore[no-untyped-def]
        return [sys.executable, "-c", script]

    monkeypatch.setattr(cli_handler, "_build_async_spawn_argv", fake_argv)

    # Shorten the FIRE budget (the scheduled path uses this constant) so
    # the live-child timeout fires quickly. The sleeper (30s) ≫ this.
    monkeypatch.setattr(
        cli_handler, "_FIRE_HANDSHAKE_TIMEOUT_SECONDS", 0.5
    )

    # (a) Record whether the orphan-kill path is ever taken.
    terminate_calls: list = []
    monkeypatch.setattr(
        cli_handler,
        "_terminate_orphan_child",
        lambda child: terminate_calls.append(child),
    )
    killpg_calls: list = []
    real_killpg = os.killpg
    monkeypatch.setattr(
        os,
        "killpg",
        lambda pgid, sig: killpg_calls.append((pgid, sig)),
    )

    # (b) Capture the child handle so we can probe ``child.poll()``.
    captured_children: list = []
    real_popen = subprocess.Popen

    def recording_popen(*popen_args, **popen_kwargs):  # type: ignore[no-untyped-def]
        child = real_popen(*popen_args, **popen_kwargs)
        captured_children.append(child)
        return child

    monkeypatch.setattr(subprocess, "Popen", recording_popen)

    args = _build_args(fake_runner_env["state_path"], scheduled=True)

    try:
        rc = cli_handler.handle_start(args)
        captured = capsys.readouterr()
        payload = json.loads(captured.out)

        # (c) Non-failure advisory envelope.
        assert rc == 1
        assert payload.get("started") is False
        assert payload.get("error_class") == "spawn_unconfirmed"
        assert payload.get("child_alive") is True

        # (a) No kill of the live child — neither the orphan-kill helper
        # nor os.killpg fired.
        assert terminate_calls == [], (
            "live child was terminated on timeout — the kill-on-timeout "
            "regression has returned"
        )
        assert killpg_calls == [], "os.killpg was called on a live child"

        # (b) The runner child is still alive.
        assert len(captured_children) == 1
        child = captured_children[0]
        assert child.poll() is None, "runner child is not alive after timeout"

        # (c) The launcher-robust single-token discriminator was written.
        outcome_path = session_dir / "spawn-outcome"
        assert outcome_path.exists()
        assert outcome_path.read_text(encoding="utf-8").strip() == "spawn_unconfirmed"
    finally:
        # Reap the controllable child via the real APIs.
        for child in captured_children:
            try:
                real_killpg(os.getpgid(child.pid), signal.SIGKILL)
            except (ProcessLookupError, OSError):
                pass
            try:
                child.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                pass


def test_async_spawn_runner_died_returns_spawn_died(
    fake_runner_env: dict,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """runner.pid appears but the runner has already exited.

    Asserts the LIVENESS-PROBE BRANCH: the production kernel race
    cannot be reproduced in pure Python, but the load-bearing behavior
    under test is that ``os.kill(pid, 0)`` raising
    ``ProcessLookupError`` causes the parent to return
    ``started: False, error_class: spawn_died`` regardless of how the
    process became dead.
    """
    session_dir: Path = fake_runner_env["session_dir"]
    pid_path = session_dir / "runner.pid"
    session_dir.mkdir(parents=True, exist_ok=True)

    # We simulate the race by: (a) preventing the real child from
    # writing runner.pid (it just exits 0 immediately), (b) writing a
    # runner.pid file that points at a known-dead PID, in advance.
    # The parent's wait_for_pid_file then reads the file, runs the
    # liveness probe against the dead PID, and returns None →
    # spawn_died branch fires.
    dead_proc = subprocess.Popen([sys.executable, "-c", "pass"])
    dead_proc.wait()
    dead_pid = dead_proc.pid

    pid_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "magic": "cortex-runner-v1",
                "pid": dead_pid,
                "pgid": dead_pid,
                "start_time": "2026-04-26T00:00:00+00:00",
                "session_id": fake_runner_env["session_id"],
                "session_dir": str(session_dir),
                "repo_path": "/tmp",
            }
        ),
        encoding="utf-8",
    )

    # Child exits immediately and does not interfere with the
    # pre-written pid file.
    def fake_argv(args, state_path):  # type: ignore[no-untyped-def]
        return [sys.executable, "-c", "pass"]

    monkeypatch.setattr(
        cli_handler, "_build_async_spawn_argv", fake_argv
    )

    args = _build_args(fake_runner_env["state_path"])

    rc = cli_handler.handle_start(args)
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert rc == 1
    assert payload.get("started") is False
    assert payload.get("error_class") == "spawn_died"
    assert not (session_dir / "runner.spawn-pending").exists()


def test_launchd_flag_bypasses_handshake(
    fake_runner_env: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--launchd`` makes ``handle_start`` invoke ``_run_runner_inline`` directly."""
    called: dict = {}

    def fake_inline(*, state_path, session_dir, repo_path, plan_path,
                    events_path, args):  # type: ignore[no-untyped-def]
        called["state_path"] = state_path
        called["launchd"] = getattr(args, "launchd", False)
        return 0

    monkeypatch.setattr(cli_handler, "_run_runner_inline", fake_inline)

    # Make _spawn_runner_async fail loudly if it ever fires.
    def fail_spawn(**kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("async spawn must not run under --launchd")

    monkeypatch.setattr(cli_handler, "_spawn_runner_async", fail_spawn)

    args = _build_args(fake_runner_env["state_path"], launchd=True, format="human")
    rc = cli_handler.handle_start(args)

    assert rc == 0
    assert called.get("launchd") is True
    assert called.get("state_path") == fake_runner_env["state_path"]


def test_dry_run_flag_bypasses_handshake_and_uses_inline_path(
    fake_runner_env: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--dry-run`` short-circuits to inline so DRY-RUN lines hit parent stdout."""
    called: dict = {}

    def fake_inline(*, state_path, session_dir, repo_path, plan_path,
                    events_path, args):  # type: ignore[no-untyped-def]
        called["dry_run"] = getattr(args, "dry_run", False)
        return 0

    monkeypatch.setattr(cli_handler, "_run_runner_inline", fake_inline)

    def fail_spawn(**kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("async spawn must not run under --dry-run")

    monkeypatch.setattr(cli_handler, "_spawn_runner_async", fail_spawn)

    args = _build_args(fake_runner_env["state_path"], dry_run=True, format="human")
    rc = cli_handler.handle_start(args)

    assert rc == 0
    assert called.get("dry_run") is True


def test_status_reports_starting_when_sentinel_present(
    fake_runner_env: dict,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """``cortex overnight status`` reports ``starting`` during the handshake window."""
    session_dir: Path = fake_runner_env["session_dir"]

    # Prepopulate the sentinel without runner.pid.
    (session_dir / "runner.spawn-pending").write_text("", encoding="utf-8")

    # No active-session pointer — force the fallback path.
    monkeypatch.setattr(
        cli_handler.ipc, "read_active_session", lambda: None
    )

    args = argparse.Namespace(
        format="json",
        session_dir=str(session_dir),
    )
    rc = cli_handler.handle_status(args)
    captured = capsys.readouterr()

    assert rc == 0
    payload = json.loads(captured.out)
    assert payload.get("phase") == "starting"
