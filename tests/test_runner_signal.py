"""Integration test: SIGHUP to ``cortex overnight start`` triggers R14 cleanup.

Spawns ``cortex overnight start`` as a real subprocess in an isolated
``HOME`` + ``PATH`` environment (mock ``claude`` on PATH so the spawned
orchestrator blocks, rather than contacting a live API), sends SIGHUP,
and verifies the runner's signal-cleanup path per R14:

  (a) Process exits with the canonical SIGHUP signal-death code (129).
      The spec prose at R14.5 (spec.md line 105) names 130 but that is
      SIGINT's canonical code; the cleanup path replays the actual
      received signal via ``os.kill(os.getpid(), signum)`` with the
      default handler restored, so SIGHUP yields 128+1 == 129. The task
      spec context's reference to 130 is tracked as a spec discrepancy
      (see PR body / retro).
  (b) ``overnight-events.log`` contains a ``circuit_breaker`` event with
      ``details.reason == "signal"``.
  (c) ``~/.local/share/overnight-sessions/active-session.json`` exists
      with ``phase == "paused"`` (pointer retained, not cleared).
  (d) No half-written backlog file appears under ``backlog/``.
  (e) The whole path completes within 30 seconds.
"""

from __future__ import annotations

import json
import os
import signal
import stat
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

REAL_REPO_ROOT = Path(__file__).resolve().parent.parent


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture()
def runner_env(tmp_path: Path):
    """Build an isolated ``HOME`` + state fixture for ``cortex overnight start``.

    Yields a dict with ``env``, ``state_path``, ``events_path``,
    ``session_dir``, ``active_session_path``, ``backlog_dir``, and
    ``proc_args`` ready to spawn the CLI subprocess.
    """
    repo = tmp_path / "repo"
    repo.mkdir()

    # Initialise as a git repo so `git rev-parse --show-toplevel` (used
    # by cli_handler._resolve_repo_path) resolves `repo` rather than
    # falling back to the test-runner's cwd.
    subprocess.run(
        ["git", "init", "--quiet", str(repo)],
        check=True,
        capture_output=True,
    )

    # Backlog directory is referenced by the R14 cleanup sequence
    # (report.create_followup_backlog_items) — leave it empty so we can
    # assert nothing was written mid-cleanup.
    backlog_dir = repo / "backlog"
    backlog_dir.mkdir()

    # HOME isolation: ipc.ACTIVE_SESSION_PATH resolves via Path.home()
    # at import time; the spawned subprocess's HOME controls the pointer
    # location. ~/.claude/notify.sh is optional (runner falls back to
    # stderr when missing) — omit it so the cleanup path exercises the
    # fallback.
    (tmp_path / ".local" / "share" / "overnight-sessions").mkdir(parents=True)

    # State fixture — structurally complete for state.load_state().
    session_id = "overnight-2026-04-24-signal"
    session_dir = repo / "lifecycle" / "sessions" / session_id
    session_dir.mkdir(parents=True)

    state = {
        "session_id": session_id,
        "phase": "executing",
        "plan_ref": "lifecycle/overnight-plan.md",
        "current_round": 1,
        "started_at": _iso_now(),
        "updated_at": _iso_now(),
        "features": {
            "feat-sighup": {"status": "pending"},
        },
        "integration_branch": "overnight-integration",
    }
    state_path = session_dir / "overnight-state.json"
    state_path.write_text(json.dumps(state), encoding="utf-8")

    # Orchestrator plan file (read by fill_prompt).
    (session_dir / "overnight-plan.md").write_text("# Test plan\n")

    # Mock ``claude`` binary on PATH — sleeps so the orchestrator Popen
    # blocks in _poll_subprocess. The signal handler installed by
    # runner.run() sets shutdown_event; the next POLL_INTERVAL tick
    # detects it and invokes _cleanup on the main thread.
    mock_bin = tmp_path / "mock-bin"
    mock_bin.mkdir()
    mock_claude = mock_bin / "claude"
    mock_claude.write_text("#!/bin/bash\nsleep 60\n")
    mock_claude.chmod(mock_claude.stat().st_mode | stat.S_IEXEC)

    events_path = session_dir / "overnight-events.log"
    active_session_path = (
        tmp_path / ".local" / "share" / "overnight-sessions" / "active-session.json"
    )

    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    env["PATH"] = str(mock_bin) + os.pathsep + env.get("PATH", "")
    env.setdefault("TMPDIR", str(tmp_path / "tmp"))
    (tmp_path / "tmp").mkdir(exist_ok=True)

    yield {
        "env": env,
        "state_path": state_path,
        "events_path": events_path,
        "session_dir": session_dir,
        "active_session_path": active_session_path,
        "backlog_dir": backlog_dir,
        "repo": repo,
        "proc_args": [
            "cortex", "overnight", "start",
            "--state", str(state_path),
            "--time-limit", "3600",
            "--max-rounds", "1",
            "--tier", "simple",
        ],
    }


def _poll_for_event(events_path: Path, event_type: str, timeout: float = 15.0) -> bool:
    """Poll the events log until an event of the given type appears."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if events_path.exists():
            for line in events_path.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    evt = json.loads(line)
                    if evt.get("event") == event_type:
                        return True
                except json.JSONDecodeError:
                    continue
        time.sleep(0.2)
    return False


def _find_event(events_path: Path, event_type: str) -> dict | None:
    """Return the last event matching event_type, or None."""
    if not events_path.exists():
        return None
    found: dict | None = None
    for line in events_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            evt = json.loads(line)
            if evt.get("event") == event_type:
                found = evt
        except json.JSONDecodeError:
            continue
    return found


def test_sighup_triggers_cleanup(runner_env: dict):
    """Send SIGHUP to ``cortex overnight start``; verify R14 cleanup behavior."""
    overall_deadline = time.monotonic() + 30.0

    proc = subprocess.Popen(
        runner_env["proc_args"],
        env=runner_env["env"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=str(runner_env["repo"]),
        # Own process group so we can signal it cleanly.
        preexec_fn=os.setsid,
    )

    try:
        # Wait for session_start — confirms signal handlers are installed
        # and the runner is inside the round loop.
        remaining = max(1.0, overall_deadline - time.monotonic())
        found = _poll_for_event(
            runner_env["events_path"],
            "session_start",
            timeout=min(15.0, remaining),
        )
        assert found, (
            "session_start event never appeared — cortex overnight start "
            "may have failed during setup"
        )

        os.kill(proc.pid, signal.SIGHUP)

        # Cleanup should complete well within the remaining budget.
        remaining = max(1.0, overall_deadline - time.monotonic())
        try:
            proc.wait(timeout=min(10.0, remaining))
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            proc.wait(timeout=5)
            pytest.fail(
                "cortex overnight start did not exit within 10s after SIGHUP"
            )

        # (a) Exit code: SIGHUP canonical signal-death code is 129
        # (128 + SIGHUP=1) under shell convention. Python's
        # ``subprocess.Popen.returncode`` reports killed-by-signal-N as
        # ``-N`` — so for SIGHUP (signum=1) the expected value is ``-1``.
        # The spec prose at R14.5 says "130" but that is SIGINT's code;
        # cleanup replays the actual signal received (here SIGHUP), so
        # the signal-death code is 129 / ``-1``. See module docstring
        # for the discrepancy note.
        assert proc.returncode == -signal.SIGHUP, (
            f"Expected returncode == -SIGHUP ({-signal.SIGHUP}) "
            f"(shell convention 129), got {proc.returncode}"
        )

        # (b) Last circuit_breaker event has reason: signal.
        cb_event = _find_event(runner_env["events_path"], "circuit_breaker")
        assert cb_event is not None, (
            "circuit_breaker event not found in events log after SIGHUP"
        )
        details = cb_event.get("details", {})
        assert details.get("reason") == "signal", (
            f"Expected circuit_breaker reason='signal', got {details!r}"
        )

        # (c) active-session.json exists with phase=="paused".
        active_path = runner_env["active_session_path"]
        assert active_path.exists(), (
            f"active-session.json should be retained (not cleared) on "
            f"signal-driven pause; expected at {active_path}"
        )
        active = json.loads(active_path.read_text(encoding="utf-8"))
        assert active.get("phase") == "paused", (
            f"Expected active-session phase='paused', got {active.get('phase')!r}"
        )

        # (d) No half-written backlog files. The cleanup path invokes
        # report.create_followup_backlog_items; we assert no .md files
        # were written for this session (empty fixture has no deferred
        # questions to promote).
        backlog_entries = list(runner_env["backlog_dir"].iterdir())
        assert backlog_entries == [], (
            f"Expected empty backlog directory after signal cleanup; "
            f"found {[p.name for p in backlog_entries]}"
        )

        # (e) Wall-clock budget check.
        assert time.monotonic() < overall_deadline, (
            "test exceeded 30-second wall-clock budget"
        )

    finally:
        # Safety net: ensure process is dead.
        if proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            proc.wait(timeout=5)
