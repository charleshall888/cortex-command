"""Security tests for ``cortex overnight`` — R17 + R18.

Covers:

* R17 — session-id regex rejection (shell metachars, path traversal,
  oversized input, non-ASCII) and realpath path-containment enforcement
  via :mod:`cortex_command.overnight.session_validation`.
* R18 — stale PID rejection via
  :func:`cortex_command.overnight.ipc.verify_runner_pid` and an end-to-
  end ``cortex overnight cancel`` subprocess invocation that asserts
  ``os.killpg`` is never called when the PID file's ``start_time`` does
  not match the recorded process.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import psutil
import pytest

from cortex_command.overnight import ipc, session_validation


REPO_ROOT = Path(__file__).resolve().parent.parent
CORTEX_CLI_ARGS = [sys.executable, "-m", "cortex_command.cli"]


# ---------------------------------------------------------------------------
# R17 — session-id regex rejection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_id",
    ["; rm -rf ~", "& echo pwn", "$(whoami)"],
)
def test_validate_session_id_rejects_shell_metachars(bad_id: str) -> None:
    """Shell metacharacters must not slip through the R17 regex."""
    with pytest.raises(ValueError, match="invalid session id"):
        session_validation.validate_session_id(bad_id)


@pytest.mark.parametrize(
    "bad_id",
    ["../../../etc", "..%2F..%2Fetc"],
)
def test_validate_session_id_rejects_path_traversal(bad_id: str) -> None:
    """Path-traversal segments must be rejected by the regex."""
    with pytest.raises(ValueError, match="invalid session id"):
        session_validation.validate_session_id(bad_id)


def test_validate_session_id_rejects_oversized() -> None:
    """Strings longer than 128 characters must be rejected."""
    with pytest.raises(ValueError, match="invalid session id"):
        session_validation.validate_session_id("a" * 129)


@pytest.mark.parametrize("bad_id", ["ñ", "日本"])
def test_validate_session_id_rejects_unicode(bad_id: str) -> None:
    """Non-ASCII characters must be rejected by the regex."""
    with pytest.raises(ValueError, match="invalid session id"):
        session_validation.validate_session_id(bad_id)


@pytest.mark.parametrize(
    "good_id",
    ["2026-04-23-18-00-00", "session.1", "a_b-c.1"],
)
def test_validate_session_id_accepts_canonical(good_id: str) -> None:
    """Canonical session-ids must pass without raising."""
    # Must not raise.
    session_validation.validate_session_id(good_id)


# ---------------------------------------------------------------------------
# R17 — path containment (realpath-based)
# ---------------------------------------------------------------------------


def test_resolve_session_dir_rejects_symlink_escape(tmp_path: Path) -> None:
    """A session-id that is a symlink pointing outside the sessions root must
    be rejected by :func:`session_validation.resolve_session_dir`."""
    sessions_root = tmp_path / "lifecycle" / "sessions"
    sessions_root.mkdir(parents=True)

    # Target outside the sessions root.
    outside_target = tmp_path / "outside"
    outside_target.mkdir()

    # Symlink lifecycle/sessions/evil -> outside_target (escapes root).
    evil_link = sessions_root / "evil"
    os.symlink(outside_target, evil_link)

    with pytest.raises(ValueError, match="invalid session id"):
        session_validation.resolve_session_dir("evil", sessions_root)


# ---------------------------------------------------------------------------
# R18 — stale PID rejection (unit tests against ipc.verify_runner_pid)
# ---------------------------------------------------------------------------


def _live_start_time_iso() -> str:
    """Return the current process's ``create_time`` as an ISO-8601 string."""
    epoch = psutil.Process(os.getpid()).create_time()
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def _write_runner_pid(session_dir: Path, payload: dict) -> None:
    """Write a ``runner.pid`` JSON file into ``session_dir``."""
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "runner.pid").write_text(json.dumps(payload))


def test_verify_runner_pid_rejects_stale_start_time(tmp_path: Path) -> None:
    """A PID file with a 1000-second-old ``start_time`` for the live test
    process PID must be rejected."""
    stale_start = (
        datetime.now(timezone.utc) - timedelta(seconds=1000)
    ).isoformat()
    payload = {
        "schema_version": 1,
        "magic": "cortex-runner-v1",
        "pid": os.getpid(),
        "pgid": os.getpgid(0),
        "start_time": stale_start,
        "session_id": "stale-session",
        "session_dir": str(tmp_path),
        "repo_path": str(tmp_path),
    }
    _write_runner_pid(tmp_path, payload)

    data = ipc.read_runner_pid(tmp_path)
    assert data is not None
    assert ipc.verify_runner_pid(data) is False


def test_verify_runner_pid_rejects_dead_pid(tmp_path: Path) -> None:
    """A PID file referencing a PID that does not exist must be rejected."""
    payload = {
        "schema_version": 1,
        "magic": "cortex-runner-v1",
        "pid": 999_999,
        "pgid": 999_999,
        "start_time": datetime.now(timezone.utc).isoformat(),
        "session_id": "dead-session",
        "session_dir": str(tmp_path),
        "repo_path": str(tmp_path),
    }
    _write_runner_pid(tmp_path, payload)

    data = ipc.read_runner_pid(tmp_path)
    assert data is not None
    assert ipc.verify_runner_pid(data) is False


def test_verify_runner_pid_accepts_live_pid(tmp_path: Path) -> None:
    """A PID file matching the live test process (PID + ``create_time``
    within ±2s) must be accepted."""
    payload = {
        "schema_version": 1,
        "magic": "cortex-runner-v1",
        "pid": os.getpid(),
        "pgid": os.getpgid(0),
        "start_time": _live_start_time_iso(),
        "session_id": "live-session",
        "session_dir": str(tmp_path),
        "repo_path": str(tmp_path),
    }
    _write_runner_pid(tmp_path, payload)

    data = ipc.read_runner_pid(tmp_path)
    assert data is not None
    assert ipc.verify_runner_pid(data) is True


# ---------------------------------------------------------------------------
# R18 — end-to-end cancel subprocess test
# ---------------------------------------------------------------------------


def test_cancel_rejects_stale_pid_end_to_end(tmp_path: Path) -> None:
    """``cortex overnight cancel`` with a stale ``runner.pid`` must exit
    nonzero and must not send SIGTERM.

    The CLI is launched as a subprocess, so ``unittest.mock.patch`` cannot
    directly patch the child's ``os.killpg``. Instead this test uses
    ``mock.patch`` to prove the assertion in-process (protecting the test
    runner's own PID from stray signals) and relies on the ``stale lock
    cleared — session was not running`` stderr line to prove the CLI took
    the R18 self-heal path (where ``os.killpg`` is unreachable by
    construction).
    """
    session_id = "stale-e2e-session"
    session_dir = tmp_path / "lifecycle" / "sessions" / session_id
    session_dir.mkdir(parents=True)

    stale_start = (
        datetime.now(timezone.utc) - timedelta(seconds=1000)
    ).isoformat()
    payload = {
        "schema_version": 1,
        "magic": "cortex-runner-v1",
        "pid": os.getpid(),
        "pgid": os.getpgid(0),
        "start_time": stale_start,
        "session_id": session_id,
        "session_dir": str(session_dir),
        "repo_path": str(tmp_path),
    }
    (session_dir / "runner.pid").write_text(json.dumps(payload))

    with mock.patch("os.killpg") as killpg_mock:
        result = subprocess.run(
            [
                *CORTEX_CLI_ARGS,
                "overnight",
                "cancel",
                "--session-dir",
                str(session_dir),
            ],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        # Subprocess child cannot see the in-process patch, but the
        # in-process patch also guarantees that if the test runner itself
        # (or any shared helper) ever calls killpg it is intercepted.
        killpg_mock.assert_not_called()

    assert result.returncode != 0, (
        f"cancel should exit nonzero on stale PID; got stdout={result.stdout!r} "
        f"stderr={result.stderr!r}"
    )
    assert "stale lock cleared" in result.stderr, (
        "expected R18 self-heal stderr message; got "
        f"stderr={result.stderr!r}"
    )
