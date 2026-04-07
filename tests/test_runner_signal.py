"""Integration test: SIGHUP triggers cleanup() with correct events and exit code.

Runs the real runner.sh in a fully isolated tmpdir environment, sends SIGHUP,
and verifies that the cleanup() handler fires — producing a circuit_breaker
event with reason: signal and exit code 130.
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
RUNNER_SH = REAL_REPO_ROOT / "claude" / "overnight" / "runner.sh"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture()
def runner_env(tmp_path: Path):
    """Build a fully isolated environment for runner.sh.

    Yields a dict with 'env', 'state_path', 'events_path', and 'proc_args'
    ready to launch the runner subprocess.
    """
    repo = tmp_path / "repo"
    repo.mkdir()

    # (a) Symlink .venv from the real repo so venv activation works
    (repo / ".venv").symlink_to(REAL_REPO_ROOT / ".venv")

    # (b) HOME=$tmpdir — create ~/.claude/notify.sh (no-op executable)
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    notify = claude_dir / "notify.sh"
    notify.write_text("#!/bin/bash\nexit 0\n")
    notify.chmod(notify.stat().st_mode | stat.S_IEXEC)

    # Create ~/.local/share/overnight-sessions/ so active-session pointer works
    (tmp_path / ".local" / "share" / "overnight-sessions").mkdir(parents=True)

    # (c) State JSON — structurally complete for load_state()
    session_id = "test-signal-session"
    session_dir = repo / "lifecycle" / "sessions" / session_id
    session_dir.mkdir(parents=True)

    state = {
        "session_id": session_id,
        "phase": "executing",
        "plan_ref": "",
        "current_round": 1,
        "started_at": _iso_now(),
        "updated_at": _iso_now(),
        "features": {
            "test-feature": {"status": "pending"},
        },
        "integration_branch": "test-integration-branch",
    }
    state_path = session_dir / "overnight-state.json"
    state_path.write_text(json.dumps(state))

    # Overnight plan file (runner reads PLAN_PATH from session dir)
    (session_dir / "overnight-plan.md").write_text("# Test plan\n")

    # (d) Mock claude binary — sleeps so main loop blocks at `wait $CLAUDE_PID`
    mock_bin = tmp_path / "mock-bin"
    mock_bin.mkdir()
    mock_claude = mock_bin / "claude"
    mock_claude.write_text("#!/bin/bash\nsleep 60\n")
    mock_claude.chmod(mock_claude.stat().st_mode | stat.S_IEXEC)

    # (e) Orchestrator prompt template
    prompt_dir = repo / "claude" / "overnight" / "prompts"
    prompt_dir.mkdir(parents=True)
    (prompt_dir / "orchestrator-round.md").write_text(
        "Round {round_number} prompt for {state_path}\n"
    )

    # (f) Events log path — writable, inside session dir
    events_path = session_dir / "overnight-events.log"

    # (g) PYTHONPATH pointing to real repo so claude.overnight.* imports resolve
    env = os.environ.copy()
    env["REPO_ROOT"] = str(repo)
    env["HOME"] = str(tmp_path)
    env["PYTHONPATH"] = str(REAL_REPO_ROOT)
    # Put mock claude binary first in PATH
    env["PATH"] = str(mock_bin) + os.pathsep + env.get("PATH", "")
    # Ensure TMPDIR is set (macOS may use /var/folders/...)
    env.setdefault("TMPDIR", str(tmp_path / "tmp"))
    (tmp_path / "tmp").mkdir(exist_ok=True)
    # lifecycle/sessions/ directory for symlink creation
    (repo / "lifecycle" / "sessions").mkdir(parents=True, exist_ok=True)

    yield {
        "env": env,
        "state_path": str(state_path),
        "events_path": events_path,
        "session_dir": session_dir,
        "proc_args": [
            "bash", str(RUNNER_SH),
            "--state", str(state_path),
            "--max-rounds", "1",
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
    """Return the first event matching event_type, or None."""
    if not events_path.exists():
        return None
    for line in events_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            evt = json.loads(line)
            if evt.get("event") == event_type:
                return evt
        except json.JSONDecodeError:
            continue
    return None


def test_sighup_triggers_cleanup(runner_env: dict):
    """Start runner.sh, send SIGHUP, verify cleanup ran correctly."""
    proc = subprocess.Popen(
        runner_env["proc_args"],
        env=runner_env["env"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        # Start in its own process group so we can signal it cleanly
        preexec_fn=os.setsid,
    )

    try:
        # Poll for session_start event — confirms trap is registered
        found = _poll_for_event(runner_env["events_path"], "session_start", timeout=15.0)
        assert found, (
            "session_start event never appeared in events log — "
            "runner.sh may have failed during setup"
        )

        # Send SIGHUP to the runner process
        os.kill(proc.pid, signal.SIGHUP)

        # Wait for process to exit (cleanup should complete within 10 seconds)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            # Safety net — kill if hung
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            proc.wait(timeout=5)
            pytest.fail("runner.sh did not exit within 10 seconds after SIGHUP")

        # Assert exit code 130
        assert proc.returncode == 130, (
            f"Expected exit code 130, got {proc.returncode}"
        )

        # Assert circuit_breaker event with reason: signal
        cb_event = _find_event(runner_env["events_path"], "circuit_breaker")
        assert cb_event is not None, (
            "circuit_breaker event not found in events log after SIGHUP"
        )
        details = cb_event.get("details", {})
        assert details.get("reason") == "signal", (
            f"Expected circuit_breaker reason='signal', got {details!r}"
        )

    finally:
        # Safety net: ensure process is dead
        if proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            proc.wait(timeout=5)
