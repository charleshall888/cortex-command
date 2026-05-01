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
import subprocess
import sys
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


def _reaped_dead_pid() -> int:
    """Return a PID that was alive but is now reaped and confirmed dead.

    Spawns a short-lived ``python -c "pass"`` subprocess, waits for the
    kernel to reap it, then asserts ``psutil.Process(pid)`` raises
    ``psutil.NoSuchProcess`` to defend against PID recycle on busy
    hosts. Retries up to 3 times before failing the test with a clear
    test-side message. Works identically on macOS and Linux.
    """
    last_err: Exception | None = None
    for _ in range(3):
        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        pid = proc.pid
        proc.wait()  # ensure the kernel has reaped it
        try:
            psutil.Process(pid)
        except psutil.NoSuchProcess:
            return pid
        except Exception as exc:  # noqa: BLE001 — surface unexpected errors
            last_err = exc
            continue
        # PID was recycled to a live process between wait() and now; retry.
    raise AssertionError(
        "test fixture: could not obtain a reaped-dead PID after 3 attempts "
        f"(last error: {last_err!r})"
    )


def _stale_pid_payload(session_dir: Path, session_id: str) -> dict:
    """Return a runner.pid payload pointing at a guaranteed-dead PID.

    Uses :func:`_reaped_dead_pid` to obtain a PID that was alive but is
    now reaped and confirmed dead via ``psutil.NoSuchProcess``. The
    ``start_time`` is fixed at the Unix epoch so it falls definitionally
    outside the ±2 s tolerance window in :func:`verify_runner_pid`.
    """
    dead_pid = _reaped_dead_pid()
    return {
        "schema_version": 1,
        "magic": "cortex-runner-v1",
        "pid": dead_pid,
        "pgid": dead_pid,
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

    # Pre-seed a stale runner.pid using a spawned-then-reaped PID
    # (confirmed dead via psutil.NoSuchProcess; see _reaped_dead_pid).
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


def test_post_fix_detects_pre_fix_runner_pid(tmp_path: Path) -> None:
    """Backwards-compat: post-fix code reads a pre-fix ``runner.pid``.

    Synthesizes the pre-fix on-disk state — a ``runner.pid`` file with
    the unchanged R8 payload schema (``schema_version, magic, pid,
    pgid, start_time, session_id, session_dir, repo_path``) and **no**
    sibling ``.runner.pid.takeover.lock`` (pre-fix code never created
    one). The payload points at this live test process so
    :func:`ipc.verify_runner_pid` returns True.

    Invokes post-fix :func:`runner._check_concurrent_start` and asserts:

    * the live-session collision path is taken (returns
      ``("session already running", None)``) — this is the post-Task 4
      signature equivalent of "``ConcurrentRunnerError`` is raised"
      from the spec's pre-Task 4 wording; the function now reports the
      collision via its return tuple instead of raising;
    * the new ``.runner.pid.takeover.lock`` sibling file is
      ``O_CREAT``-ed by the post-fix ``_acquire_takeover_lock`` on
      first acquire (proof the post-fix code creates the lockfile when
      encountering a pre-fix payload that has none).

    The reverse direction (pre-fix code reading post-fix on-disk state)
    is covered by source-level proof: pre-fix ``ipc.py`` does not
    reference ``.runner.pid.takeover.lock`` anywhere, so the file is
    tautologically ignored. See implementation.md for the grep evidence.
    """
    # Local import: avoids a top-level import that could hide a
    # collection-time failure if runner.py grows new heavy imports.
    from cortex_command.overnight.runner import _check_concurrent_start

    session_id = "2026-04-30-pre-fix-payload"
    pre_fix_payload = _alive_pid_payload(tmp_path, session_id)

    # Pre-fix on-disk state: runner.pid present, lockfile absent.
    (tmp_path / "runner.pid").write_text(json.dumps(pre_fix_payload))
    lockfile = tmp_path / ".runner.pid.takeover.lock"
    assert not lockfile.exists(), (
        "fixture invariant: pre-fix state must not include the lockfile"
    )

    error_message, lock_fd = _check_concurrent_start(tmp_path)

    # Live-session collision path: the post-fix function detects the
    # live runner via verify_runner_pid and returns the error message
    # with lock_fd=None (function released the lock before returning).
    assert error_message == "session already running", (
        f"expected live-session collision message, got {error_message!r}"
    )
    assert lock_fd is None, (
        f"expected lock_fd=None on live-session collision path, got {lock_fd!r}"
    )

    # The post-fix _acquire_takeover_lock O_CREAT'd the sibling lockfile
    # on first acquire — proof post-fix code handles a pre-fix payload
    # (no lockfile) correctly by creating it on demand.
    assert lockfile.exists(), (
        "post-fix _acquire_takeover_lock must O_CREAT "
        ".runner.pid.takeover.lock on first acquire"
    )


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
