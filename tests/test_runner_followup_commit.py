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
import sys
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
    # cortex/backlog/ — the worktree is on its own branch, safe to mutate.
    (worktree / "cortex" / "backlog").mkdir(parents=True, exist_ok=True)

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
    session_dir = repo / "cortex" / "lifecycle" / "sessions" / session_id
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
            sys.executable, "-m", "cortex_command.cli", "overnight", "start",
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


def _read_runner_pid_from_session(session_dir: Path, timeout: float = 10.0) -> int:
    """Poll ``session_dir/runner.pid`` until it appears and return the recorded pid.

    Mirrors the helper in ``test_runner_signal.py``. Under async-spawn
    (Task 6), the parent shim returned by ``Popen`` exits within ~5s of
    the handshake; the runner runs as a grandchild under a fresh
    process group. Tests that need to signal the runner read this file
    post-handshake instead of using ``proc.pid``.
    """
    pid_path = session_dir / "runner.pid"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pid_path.exists():
            try:
                payload = json.loads(pid_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                time.sleep(0.1)
                continue
            pid = payload.get("pid")
            if isinstance(pid, int):
                return pid
        time.sleep(0.1)
    raise AssertionError(
        f"runner.pid never appeared at {pid_path} within {timeout}s"
    )


def _wait_for_pid_exit_followup(pid: int, timeout: float) -> bool:
    """Poll until the pid is gone (best-effort liveness probe). Used in the
    followup-commit test to await runner cleanup since ``Popen.wait`` no
    longer applies to the runner grandchild under async-spawn.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.1)
    return False


def test_sighup_trap_commits_followup_to_worktree(worktree_runner_env: dict):
    """SIGHUP triggers cleanup; cleanup creates followup backlog item and commits it.

    Behavioral surface change (Task 6 / spec R18): under async-spawn
    ``proc.pid`` is the parent shim and exits within 5s of returning
    from the handshake. The runner runs under a new process group; the
    test reads ``<session_dir>/runner.pid`` post-handshake and signals
    that pid instead. The signal-handler-fired assertion is now the
    on-disk followup commit + backlog file (the runner's signal
    handler fired iff the followup commit landed on the integration
    branch).

    Asserts:
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

    session_dir = Path(worktree_runner_env["state_path"]).parent
    runner_pid: int | None = None

    try:
        found = _poll_for_event(
            worktree_runner_env["events_path"], "session_start", timeout=15.0
        )
        assert found, "session_start event never appeared"

        # Under async-spawn, signal the runner grandchild — not proc.pid.
        runner_pid = _read_runner_pid_from_session(session_dir, timeout=10.0)
        os.kill(runner_pid, signal.SIGHUP)

        # Wait for the runner to exit. ``proc.wait`` no longer applies
        # because proc is the parent shim, which has already exited.
        if not _wait_for_pid_exit_followup(runner_pid, timeout=15.0):
            try:
                os.kill(runner_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            pytest.fail(
                "cortex overnight runner did not exit within 15s after SIGHUP"
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
            "test-integration-branch", "--", "cortex/backlog/",
        ).stdout
        commit_re = re.compile(
            rf"Overnight session {re.escape(session_id)}: record followup"
        )
        if not commit_re.search(log):
            # Dump diagnostics for post-mortem
            stderr_text = stderr_capture.read_text(errors="replace") \
                if stderr_capture.exists() else "<no stderr>"
            cortex_backlog = worktree / "cortex" / "backlog"
            backlog_contents = list(cortex_backlog.iterdir()) if cortex_backlog.exists() else []
            home_cortex_backlog = repo / "cortex" / "backlog"
            home_backlog_contents = list(home_cortex_backlog.iterdir()) \
                if home_cortex_backlog.exists() else []
            pytest.fail(
                "no followup commit on integration branch.\n"
                f"log={log!r}\n"
                f"worktree/cortex/backlog contents={backlog_contents!r}\n"
                f"home/cortex/backlog contents={home_backlog_contents!r}\n"
                f"--- runner stderr tail ---\n{stderr_text[-4000:]}"
            )

        # (c) the followup file under worktree/cortex/backlog/ exists with session_id.
        followups = [
            p for p in (worktree / "cortex" / "backlog").glob("*-broken-feature.md")
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
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        # Best-effort kill of the runner grandchild (the SIGHUP path
        # should have brought it down, but a failed assertion may
        # bypass that).
        if runner_pid is not None:
            try:
                os.kill(runner_pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass


# ---------------------------------------------------------------------------
# Failure-logging tests (lifecycle 130-style ticket Task 5/10):
# Asserts that when the inner ``git commit`` is rejected (e.g., by a
# pre-commit hook), ``_commit_followup_in_worktree`` writes both a
# ``runner: followup commit failed`` stderr line and a structured
# ``followup_commit_failed`` event to ``events_path``.
# ---------------------------------------------------------------------------


@pytest.fixture()
def rejecting_hook_env(tmp_path: Path):
    """Build a worktree configured to always reject commits via pre-commit hook.

    Topology:
      - repo/ (home repo, default branch)
      - worktree/ (worktree on 'integration-branch')
      - repo/.githooks/pre-commit — exits 1 unconditionally
      - core.hooksPath set to .githooks in both repo + worktree configs

    Stages a tracked change under ``worktree/backlog/`` so the
    ``git diff --cached --quiet`` precheck inside
    ``_commit_followup_in_worktree`` returns non-zero and the function
    proceeds to the (rejected) ``git commit`` invocation.
    """
    repo = tmp_path / "repo"
    worktree = tmp_path / "worktree"

    _init_repo(repo)
    _git(repo, "branch", "integration-branch")
    _git(repo, "worktree", "add", str(worktree), "integration-branch")

    for d in (repo, worktree):
        _git(d, "config", "user.email", "t@t")
        _git(d, "config", "user.name", "T")
        _git(d, "config", "commit.gpgsign", "false")

    # Install the rejecting hook. core.hooksPath is repo-relative, so
    # configuring it in the worktree's local config (which shares the
    # gitdir with the home repo) routes hook resolution to repo/.githooks/.
    hooks_dir = repo / ".githooks"
    hooks_dir.mkdir()
    pre_commit = hooks_dir / "pre-commit"
    pre_commit.write_text(
        "#!/bin/bash\n"
        "echo 'pre-commit: rejected by test fixture' >&2\n"
        "exit 1\n"
    )
    pre_commit.chmod(pre_commit.stat().st_mode | stat.S_IEXEC)

    _git(repo, "config", "core.hooksPath", str(hooks_dir))

    # Stage a backlog change so the diff --cached precheck doesn't no-op.
    # Note: _commit_followup_in_worktree uses "git add backlog/" so the
    # fixture file must be at backlog/ (runner.py:458 source-code issue tracked separately).
    (worktree / "backlog").mkdir(exist_ok=True)
    (worktree / "backlog" / "fixture-followup.md").write_text(
        "# fixture followup\n"
    )

    session_id = "overnight-test-followup-fail"
    session_dir = repo / "cortex" / "lifecycle" / "sessions" / session_id
    session_dir.mkdir(parents=True)
    events_path = session_dir / "overnight-events.log"

    yield {
        "repo": repo,
        "worktree": worktree,
        "session_id": session_id,
        "events_path": events_path,
    }


def test_followup_commit_failure_emits_stderr_and_event(
    rejecting_hook_env: dict,
    capsys: pytest.CaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
):
    """Simulated commit rejection produces stderr line + events.log entry.

    Asserts:
      - captured stderr contains ``runner: followup commit failed``.
      - ``events_path`` JSONL contains a line whose ``event`` field equals
        ``events.FOLLOWUP_COMMIT_FAILED``.
    """
    # Import here so the test fails with a clear error if the module path
    # is broken, rather than at collection time.
    from cortex_command.overnight import events
    from cortex_command.overnight.runner import _commit_followup_in_worktree

    # Pin LIFECYCLE_SESSION_ID so events.log_event has a stable session_id
    # field (events_path is explicit, so this is cosmetic but matches the
    # runner's runtime invariant).
    monkeypatch.setenv("LIFECYCLE_SESSION_ID", rejecting_hook_env["session_id"])

    _commit_followup_in_worktree(
        rejecting_hook_env["worktree"],
        rejecting_hook_env["session_id"],
        rejecting_hook_env["events_path"],
    )

    captured = capsys.readouterr()
    assert "runner: followup commit failed" in captured.err, (
        f"expected stderr to contain 'runner: followup commit failed'; got: "
        f"{captured.err!r}"
    )

    events_path = rejecting_hook_env["events_path"]
    assert events_path.exists(), (
        f"events log was never written at {events_path}"
    )

    matched = False
    for line in events_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue
        if evt.get("event") == events.FOLLOWUP_COMMIT_FAILED:
            matched = True
            break
    assert matched, (
        f"no event with type={events.FOLLOWUP_COMMIT_FAILED!r} found in "
        f"{events_path}; contents:\n{events_path.read_text()}"
    )
