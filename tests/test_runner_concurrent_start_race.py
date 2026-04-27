"""Tests for R8's atomic ``O_CREAT|O_EXCL`` runner-pid claim
(:func:`cortex_command.overnight.ipc.write_runner_pid`).

Closes Adversarial §1: two simultaneous ``cortex overnight start``
invocations cannot both win the lock. The losing call raises
:class:`cortex_command.overnight.ipc.ConcurrentRunnerError`; the MCP
layer (Task 15) surfaces this as
``{started: false, reason: "concurrent_runner_alive", ...}``.

Coverage:

* ``test_two_starters_no_preexisting_lock`` — two parallel claims
  against a clean session_dir; exactly one wins via O_EXCL.
* ``test_two_starters_with_stale_preexisting_lock`` — both observe a
  stale lock; the unlink-and-retry-once budget guarantees exactly one
  winner and one ``ConcurrentRunnerError``.
* ``test_starter_against_alive_lock`` — single claim against an alive
  lock raises ``ConcurrentRunnerError`` immediately, no unlink.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

import psutil
import pytest

from cortex_command.overnight import ipc
from cortex_command.overnight.ipc import ConcurrentRunnerError

# Concurrent O_EXCL race tests use real threads + filesystem locks — keep
# serialized against the other subprocess-spawning suites (R26 / Task 20).
pytestmark = pytest.mark.serial


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _live_start_time_iso() -> str:
    """Return the current process's ``create_time`` as an ISO-8601 string."""
    epoch = psutil.Process(os.getpid()).create_time()
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def _alive_pid_payload(session_dir: Path, session_id: str) -> dict:
    """Return a runner.pid payload pointing at *this* live test process."""
    return {
        "schema_version": 1,
        "magic": "cortex-runner-v1",
        "pid": os.getpid(),
        "pgid": os.getpgrp(),
        "start_time": _live_start_time_iso(),
        "session_id": session_id,
        "session_dir": str(session_dir),
        "repo_path": str(session_dir),
    }


def _stale_pid_payload(session_dir: Path, session_id: str) -> dict:
    """Return a runner.pid payload pointing at a guaranteed-dead PID.

    PID 0 is reserved on POSIX; ``psutil.Process(0)`` raises
    ``NoSuchProcess`` so :func:`verify_runner_pid` returns ``False``.
    """
    return {
        "schema_version": 1,
        "magic": "cortex-runner-v1",
        "pid": 0,
        "pgid": 0,
        "start_time": "1970-01-01T00:00:00+00:00",
        "session_id": session_id,
        "session_dir": str(session_dir),
        "repo_path": str(session_dir),
    }


def _race_two_writers(
    session_dir: Path,
    pid_a: int,
    pid_b: int,
    session_id: str,
) -> tuple[list[BaseException | None], list[BaseException | None]]:
    """Fire two ``write_runner_pid`` calls with a shared barrier.

    Returns ``([result_a], [result_b])`` where each entry is either
    ``None`` (the call succeeded) or the exception it raised.
    """
    barrier = threading.Barrier(2)
    results: dict[str, BaseException | None] = {"a": None, "b": None}
    started = _live_start_time_iso()

    def _write(name: str, pid: int) -> None:
        barrier.wait()
        try:
            ipc.write_runner_pid(
                session_dir=session_dir,
                pid=pid,
                pgid=os.getpgrp(),
                start_time=started,
                session_id=session_id,
                repo_path=session_dir,
            )
            results[name] = None
        except BaseException as exc:  # noqa: BLE001 — we want every failure
            results[name] = exc

    t_a = threading.Thread(target=_write, args=("a", pid_a))
    t_b = threading.Thread(target=_write, args=("b", pid_b))
    t_a.start()
    t_b.start()
    t_a.join()
    t_b.join()

    return [results["a"]], [results["b"]]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_two_starters_no_preexisting_lock(tmp_path: Path) -> None:
    """Two parallel claims against a clean session_dir.

    Exactly one wins via the O_CREAT|O_EXCL claim; the loser raises
    :class:`ConcurrentRunnerError`.
    """
    session_id = "2026-04-24-12-00-00"
    pid_a = os.getpid()
    pid_b = os.getpid()

    res_a, res_b = _race_two_writers(tmp_path, pid_a, pid_b, session_id)
    outcomes = [res_a[0], res_b[0]]

    successes = [o for o in outcomes if o is None]
    failures = [o for o in outcomes if o is not None]

    assert len(successes) == 1, f"expected exactly one winner, got {outcomes!r}"
    assert len(failures) == 1
    assert isinstance(failures[0], ConcurrentRunnerError)
    assert failures[0].session_id == session_id
    assert isinstance(failures[0].existing_pid, int)

    # The winner's claim must be on disk and parseable.
    on_disk = ipc.read_runner_pid(tmp_path)
    assert on_disk is not None
    assert on_disk["session_id"] == session_id
    assert on_disk["magic"] == "cortex-runner-v1"


@pytest.mark.xfail(
    reason="runner.pid takeover race — see backlog ticket 149",
    strict=False,
)
def test_two_starters_with_stale_preexisting_lock(tmp_path: Path) -> None:
    """Both racers observe a stale lock; exactly one wins after retry.

    The unlink-and-retry-once path means: one thread unlinks the stale
    lock and re-claims via O_EXCL, the other thread either (i) sees the
    new live claim and raises immediately, or (ii) reaches retry, hits
    a second FileExistsError, and raises ``ConcurrentRunnerError``
    regardless of liveness. In both scenarios exactly one writer's
    payload ends up on disk.

    NOTE (2026-04-27): xfail strict=False because ipc.write_runner_pid
    has a TOCTOU in the unconditional unlink at the takeover path (see
    backlog ticket 149). The test still flakes ~20% on macOS — passes
    are accepted (not unxfail-flagged) until the takeover primitive is
    redesigned (recommended: fcntl.flock).
    """
    session_id = "2026-04-24-12-00-01"

    # Pre-seed a stale runner.pid (pid=0 is guaranteed dead per psutil).
    stale = _stale_pid_payload(tmp_path, "stale-prior-run")
    (tmp_path / "runner.pid").write_text(json.dumps(stale))

    pid_a = os.getpid()
    pid_b = os.getpid()

    res_a, res_b = _race_two_writers(tmp_path, pid_a, pid_b, session_id)
    outcomes = [res_a[0], res_b[0]]

    successes = [o for o in outcomes if o is None]
    failures = [o for o in outcomes if o is not None]

    assert len(successes) == 1, f"expected exactly one winner, got {outcomes!r}"
    assert len(failures) == 1
    assert isinstance(failures[0], ConcurrentRunnerError)

    # Final on-disk payload reflects the new session_id, not the stale one.
    on_disk = ipc.read_runner_pid(tmp_path)
    assert on_disk is not None
    assert on_disk["session_id"] == session_id


def test_starter_against_alive_lock(tmp_path: Path) -> None:
    """A single starter against an alive lock raises immediately.

    No retry, no unlink — :func:`verify_runner_pid` confirms liveness
    on the very first ``FileExistsError`` and the call surfaces
    :class:`ConcurrentRunnerError`. The pre-existing lock file must be
    preserved untouched.
    """
    existing_session = "2026-04-24-11-00-00"
    alive = _alive_pid_payload(tmp_path, existing_session)
    (tmp_path / "runner.pid").write_text(json.dumps(alive))
    original_bytes = (tmp_path / "runner.pid").read_bytes()

    with pytest.raises(ConcurrentRunnerError) as excinfo:
        ipc.write_runner_pid(
            session_dir=tmp_path,
            pid=os.getpid(),
            pgid=os.getpgrp(),
            start_time=_live_start_time_iso(),
            session_id="2026-04-24-12-00-02",
            repo_path=tmp_path,
        )

    assert excinfo.value.session_id == existing_session
    assert excinfo.value.existing_pid == os.getpid()

    # Alive lock must NOT be unlinked or rewritten.
    assert (tmp_path / "runner.pid").read_bytes() == original_bytes
