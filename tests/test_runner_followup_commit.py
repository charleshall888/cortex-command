"""Integration test: SIGHUP trap commits followup backlog items to worktree.

Covers lifecycle 130 Task 7 — the SIGHUP trap / cleanup path calls
``create_followup_backlog_items`` with ``backlog_dir`` rooted at
``$WORKTREE_PATH`` and then runs ``git add backlog/ && git commit`` inside
the worktree so the followup items land on the integration branch, not
the home repo.

Port note (lifecycle ticket 115 Task 12):
- Subprocess invocations migrated from the bash runner to
  ``cortex overnight start`` (the installed console script wired up by
  ``pyproject.toml``'s ``[project.scripts]``).
- ``REPO_ROOT`` / ``PYTHONPATH`` env vars removed — the Python CLI
  resolves its own paths via ``git rev-parse`` (R20).
- State file fixture construction and ``_poll_for_event``-style assertion
  bodies are unchanged.
"""

from __future__ import annotations

import json
import os
import re
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


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git",
         "-c", "user.email=t@t",
         "-c", "user.name=T",
         "-c", "commit.gpgsign=false",
         *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=check,
    )


def _init_repo(path: Path) -> str:
    """Initialize a git repo and return the default branch name."""
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init")
    _git(path, "commit", "--allow-empty", "-m", "init")
    rev = _git(path, "rev-parse", "--abbrev-ref", "HEAD")
    return rev.stdout.strip()


@pytest.fixture()
def worktree_runner_env(tmp_path: Path):
    """Build a ``cortex overnight`` fixture with a real git repo + worktree.

    Populates:
      - repo/ (home repo, default branch)
      - worktree/ (git worktree on 'test-integration-branch')
      - state.json with worktree_path + failed feature so the SIGHUP trap's
        create_followup_backlog_items writes a real followup file.
    """
    repo = tmp_path / "repo"
    worktree = tmp_path / "worktree"

    # Home repo
    default_branch = _init_repo(repo)
    # Create integration branch first, then add the worktree checked out on it.
    _git(repo, "branch", "test-integration-branch")
    _git(repo, "worktree", "add", str(worktree), "test-integration-branch")

    # Baked-in user identity so `git commit` inside runner subshells (which
    # don't pass `-c` flags) can succeed. Config is local so each repo/worktree
    # sees it regardless of HOME.
    for d in (repo, worktree):
        _git(d, "config", "user.email", "t@t")
        _git(d, "config", "user.name", "T")
        _git(d, "config", "commit.gpgsign", "false")

    # Mirror bare minimum structure inside the worktree so commits can touch
    # backlog/ — the worktree is on its own branch, safe to mutate.
    (worktree / "backlog").mkdir(exist_ok=True)

    # Fake HOME
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    notify = claude_dir / "notify.sh"
    notify.write_text("#!/bin/bash\nexit 0\n")
    notify.chmod(notify.stat().st_mode | stat.S_IEXEC)
    (tmp_path / ".local" / "share" / "overnight-sessions").mkdir(parents=True)

    # Session state — features dict has one failed entry so the followup
    # writer produces a file and the SIGHUP path has something to commit.
    session_id = "overnight-test-followup"
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
            # failed feature → followup backlog item emitted in the trap
            "broken-feature": {
                "status": "failed",
                "error": "simulated failure",
            },
            # pending feature → keeps the round loop alive until SIGHUP
            # arrives. Without this, runner.run() sees pending==0 and
            # exits cleanly before the test delivers SIGHUP (exit 0),
            # failing the signal-exit assertion. The mock claude sleeps
            # 60s so the orchestrator subprocess blocks long enough for
            # SIGHUP delivery.
            "pending-feature": {
                "status": "pending",
            },
        },
        "integration_branch": "test-integration-branch",
        "worktree_path": str(worktree),
    }
    state_path = session_dir / "overnight-state.json"
    state_path.write_text(json.dumps(state))

    (session_dir / "overnight-plan.md").write_text("# test plan\n")

    # Mock claude binary — blocks so we can SIGHUP mid-loop.
    mock_bin = tmp_path / "mock-bin"
    mock_bin.mkdir()
    mock_claude = mock_bin / "claude"
    mock_claude.write_text("#!/bin/bash\nsleep 60\n")
    mock_claude.chmod(mock_claude.stat().st_mode | stat.S_IEXEC)

    events_path = session_dir / "overnight-events.log"

    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    env["PATH"] = str(mock_bin) + os.pathsep + env.get("PATH", "")
    env.setdefault("TMPDIR", str(tmp_path / "tmp"))
    (tmp_path / "tmp").mkdir(exist_ok=True)
    # Deterministic session_id for the trap's followup emitter — the runner
    # exports this itself later in its main loop, but the SIGHUP trap can fire
    # before that export, so pre-seed it here to match the state file.
    env["LIFECYCLE_SESSION_ID"] = session_id

    yield {
        "env": env,
        "state_path": str(state_path),
        "events_path": events_path,
        "repo": repo,
        "worktree": worktree,
        "session_id": session_id,
        "proc_args": [
            "cortex", "overnight", "start",
            "--state", str(state_path),
            "--max-rounds", "1",
        ],
    }


def _poll_for_event(events_path: Path, event_type: str, timeout: float = 15.0) -> bool:
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


def test_sighup_trap_commits_followup_to_worktree(worktree_runner_env: dict):
    """SIGHUP triggers cleanup; cleanup creates followup backlog item and commits it.

    Asserts:
      - Exit code 129 (SIGHUP-triggered cleanup — the Python runner
        replays the received signal so the process dies with the canonical
        signal-death exit code, per R14 cleanup step 7).
      - The worktree's integration branch has a commit whose message matches
        'Overnight session .* record followup' (Task 7 commit block).
      - The followup item's session_id frontmatter equals the session id
        (Task 3 session_id fix — NOT 'null' and NOT 'manual').
      - The home repo's backlog/ has no staged or unstaged changes.
    """
    stderr_capture = worktree_runner_env["events_path"].parent / "stderr.log"
    stdout_capture = worktree_runner_env["events_path"].parent / "stdout.log"
    proc = subprocess.Popen(
        worktree_runner_env["proc_args"],
        env=worktree_runner_env["env"],
        stdout=open(stdout_capture, "wb"),
        stderr=open(stderr_capture, "wb"),
        preexec_fn=os.setsid,
    )

    try:
        found = _poll_for_event(
            worktree_runner_env["events_path"], "session_start", timeout=15.0
        )
        assert found, "session_start event never appeared"

        os.kill(proc.pid, signal.SIGHUP)

        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            proc.wait(timeout=5)
            pytest.fail("cortex overnight start did not exit within 15 seconds after SIGHUP")

        # Python runner replays the signal via os.kill(os.getpid(), SIGHUP),
        # so the canonical SIGHUP exit is 128+1 = 129. The prior bash runner
        # exited 130 unconditionally via `exit 130` in its trap. This is the
        # only assertion-body change required by the port.
        assert proc.returncode in (129, -signal.SIGHUP, 130), (
            f"Expected signal-triggered exit (129/SIGHUP/130), got {proc.returncode}"
        )

        worktree = worktree_runner_env["worktree"]
        repo = worktree_runner_env["repo"]
        session_id = worktree_runner_env["session_id"]

        # (a) home repo backlog/ is clean — no write landed there.
        home_status = _git(
            repo, "status", "--porcelain", "backlog/",
        ).stdout.strip()
        assert home_status == "", (
            f"home repo backlog/ has changes after SIGHUP: {home_status!r}"
        )

        # (b) worktree integration branch has a commit matching the pattern.
        log = _git(
            worktree, "log",
            "--pretty=%s",
            "test-integration-branch", "--", "backlog/",
        ).stdout
        commit_re = re.compile(
            rf"Overnight session {re.escape(session_id)}: record followup"
        )
        if not commit_re.search(log):
            # Dump diagnostics for post-mortem
            stderr_text = stderr_capture.read_text(errors="replace") \
                if stderr_capture.exists() else "<no stderr>"
            backlog_contents = list((worktree / "backlog").iterdir())
            home_backlog_contents = list((repo / "backlog").iterdir()) \
                if (repo / "backlog").exists() else []
            pytest.fail(
                "no followup commit on integration branch.\n"
                f"log={log!r}\n"
                f"worktree/backlog contents={backlog_contents!r}\n"
                f"home/backlog contents={home_backlog_contents!r}\n"
                f"--- runner stderr tail ---\n{stderr_text[-4000:]}"
            )

        # (c) the followup file under worktree/backlog/ exists with session_id.
        followups = [
            p for p in (worktree / "backlog").glob("*-broken-feature.md")
        ]
        assert followups, "no followup backlog item created in worktree"
        (followup,) = followups
        fm = followup.read_text()
        assert f"session_id: {session_id}" in fm, (
            f"followup missing session_id={session_id!r}; frontmatter:\n{fm}"
        )
        assert "session_id: null" not in fm
        assert "session_id: manual" not in fm

    finally:
        if proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            proc.wait(timeout=5)
