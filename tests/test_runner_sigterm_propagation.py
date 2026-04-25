"""Unit tests for the runner SIGTERM descendant-tree walker (R12 / Task 3).

The runner installs a SIGTERM handler that walks
``psutil.Process(os.getpid()).children(recursive=True)`` and SIGTERM-then-
SIGKILLs each descendant. This reaches grandchildren spawned with
``start_new_session=True`` (PGID-divergent from the runner's), which
``os.killpg`` cannot signal — production topology per Task 19(b) puts
grandchildren in their own PGIDs, so the unit test must exercise the
PGID-divergent case to actually verify the tree-walk.

Two tests:

  (1) ``test_sigterm_reaps_grandchildren_in_and_out_of_runner_pgid`` —
      a runner-stub subprocess spawns one grandchild WITH
      ``start_new_session=True`` (PGID-divergent) and one WITHOUT (in the
      runner's PGID). SIGTERM is sent to the runner-stub PID; both
      grandchildren must terminate within 8 seconds (6 s graceful + 2 s
      overhead).

  (2) ``test_sigterm_escalates_to_sigkill_for_ignoring_grandchild`` —
      a grandchild spawned with ``start_new_session=True`` AND with its
      own SIGTERM-ignoring handler must be SIGKILL'd by the runner-stub's
      tree-walker; it must terminate within the same 8 s budget.

Tests spawn real subprocesses with ``start_new_session=True``; teardown
defensively kills any leftover children so the test exits cleanly even on
assertion failure. The ``@pytest.mark.serial`` marker is added in Task 20
and intentionally not applied here.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import psutil
import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Fixtures: runner-stub source and grandchild source
# ---------------------------------------------------------------------------

# A long-sleeping grandchild — graceful exit on SIGTERM.
_GRACEFUL_GRANDCHILD_SRC = textwrap.dedent(
    """
    import signal
    import sys
    import time

    # Default SIGTERM handler exits the process cleanly. We rely on
    # the Python default (which raises a KeyboardInterrupt-equivalent
    # for SIGTERM) — but to keep the exit deterministic, install an
    # explicit handler that calls sys.exit(0).
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    while True:
        time.sleep(60)
    """
).strip()


# A SIGTERM-ignoring grandchild — must be SIGKILL'd to terminate.
_SIGTERM_IGNORING_GRANDCHILD_SRC = textwrap.dedent(
    """
    import signal
    import time

    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    while True:
        time.sleep(60)
    """
).strip()


def _build_runner_stub_src(grandchildren_count_with_session: int,
                           grandchildren_count_without_session: int,
                           grandchild_src: str,
                           pid_file: Path,
                           grandchildren_pids_file: Path) -> str:
    """Return Python source for a runner-stub subprocess.

    The stub:
      1. Installs the production SIGTERM tree-walker by importing
         ``cortex_command.overnight.runner._install_sigterm_tree_walker``
         and chaining a no-op prior handler so we exercise only the
         tree-walk phase (no main-thread runner cleanup).
      2. Spawns ``grandchildren_count_with_session`` Popen subprocesses
         with ``start_new_session=True`` (PGID-divergent) and
         ``grandchildren_count_without_session`` without (in the stub's
         PGID).
      3. Writes its own PID to ``pid_file`` and writes each grandchild's
         PID (one per line) to ``grandchildren_pids_file``.
      4. Sleeps in a loop until SIGTERM arrives. The tree-walker reaps
         the grandchildren; the chained no-op prior handler is invoked
         after the walk; then the stub exits.
    """
    return textwrap.dedent(
        f"""
        import os
        import signal
        import subprocess
        import sys
        import time
        from pathlib import Path

        sys.path.insert(0, {str(REPO_ROOT)!r})

        from cortex_command.overnight.runner import (
            _install_sigterm_tree_walker,
        )

        GRANDCHILD_SRC = {grandchild_src!r}
        WITH_SESSION = {grandchildren_count_with_session}
        WITHOUT_SESSION = {grandchildren_count_without_session}
        PID_FILE = Path({str(pid_file)!r})
        GRANDCHILDREN_PIDS_FILE = Path({str(grandchildren_pids_file)!r})

        # Set a no-op prior handler so the tree-walker has something to
        # chain to and the stub exits after the walk completes.
        # We use a flag-set + main-loop-exit pattern instead of sys.exit
        # because sys.exit from a signal handler is unreliable.
        _shutdown = []

        def _prior(signum, frame):
            _shutdown.append(signum)

        signal.signal(signal.SIGTERM, _prior)
        _install_sigterm_tree_walker(_prior)

        # Spawn grandchildren.
        grandchild_pids = []
        for _ in range(WITH_SESSION):
            p = subprocess.Popen(
                [sys.executable, "-c", GRANDCHILD_SRC],
                start_new_session=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            grandchild_pids.append(p.pid)
        for _ in range(WITHOUT_SESSION):
            p = subprocess.Popen(
                [sys.executable, "-c", GRANDCHILD_SRC],
                start_new_session=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            grandchild_pids.append(p.pid)

        # Persist PIDs so the test can poll them.
        GRANDCHILDREN_PIDS_FILE.write_text(
            "\\n".join(str(pid) for pid in grandchild_pids)
        )
        PID_FILE.write_text(str(os.getpid()))

        # Sleep until SIGTERM arrives. The tree-walker handler runs
        # synchronously on receipt; once it returns we drop out of
        # time.sleep via the prior-handler-set flag and exit.
        deadline = time.monotonic() + 60.0
        while time.monotonic() < deadline:
            if _shutdown:
                break
            time.sleep(0.05)

        sys.exit(0)
        """
    ).strip()


def _wait_for_pid_file(path: Path, timeout: float = 10.0) -> int:
    """Poll until the runner-stub writes its PID file."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            try:
                content = path.read_text().strip()
            except OSError:
                content = ""
            if content:
                return int(content)
        time.sleep(0.05)
    raise TimeoutError(f"runner-stub PID file never appeared at {path}")


def _wait_for_grandchildren_pids(path: Path, expected: int,
                                  timeout: float = 10.0) -> list[int]:
    """Poll until the runner-stub writes all grandchild PIDs."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            try:
                content = path.read_text().strip()
            except OSError:
                content = ""
            if content:
                pids = [int(line) for line in content.splitlines() if line.strip()]
                if len(pids) >= expected:
                    return pids
        time.sleep(0.05)
    raise TimeoutError(
        f"grandchildren PID file did not contain {expected} pids at {path}"
    )


def _pid_alive(pid: int) -> bool:
    """Return True if a process with the given PID exists and is not a zombie."""
    try:
        proc = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return False
    try:
        return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


def _wait_for_pids_dead(pids: list[int], timeout: float) -> tuple[bool, list[int]]:
    """Poll until all given PIDs are dead or timeout. Return (all_dead, survivors)."""
    deadline = time.monotonic() + timeout
    survivors: list[int] = list(pids)
    while time.monotonic() < deadline:
        survivors = [pid for pid in pids if _pid_alive(pid)]
        if not survivors:
            return True, []
        time.sleep(0.1)
    return False, survivors


def _force_kill_pids(pids: list[int]) -> None:
    """Best-effort SIGKILL of any surviving PIDs (test-cleanup safety net)."""
    for pid in pids:
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            continue
    # Reap zombies so the test process doesn't leak them.
    for pid in pids:
        try:
            os.waitpid(pid, os.WNOHANG)
        except (ChildProcessError, OSError):
            continue


# ---------------------------------------------------------------------------
# Test 1: SIGTERM reaps grandchildren both inside and outside runner's PGID
# ---------------------------------------------------------------------------

def test_sigterm_reaps_grandchildren_in_and_out_of_runner_pgid(tmp_path: Path):
    """SIGTERM tree-walker reaches grandchildren both PGID-resident and
    PGID-divergent (start_new_session=True).

    The PGID-divergent case is the critical one: ``os.killpg`` against the
    runner's PGID does NOT reach grandchildren spawned with
    ``start_new_session=True``. Only the tree-walker's
    ``psutil.children(recursive=True)`` enumeration reaches them.
    """
    pid_file = tmp_path / "runner_stub.pid"
    grandchildren_pids_file = tmp_path / "grandchildren.pids"

    src = _build_runner_stub_src(
        grandchildren_count_with_session=1,
        grandchildren_count_without_session=1,
        grandchild_src=_GRACEFUL_GRANDCHILD_SRC,
        pid_file=pid_file,
        grandchildren_pids_file=grandchildren_pids_file,
    )

    proc = subprocess.Popen(
        [sys.executable, "-c", src],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    grandchild_pids: list[int] = []
    try:
        runner_pid = _wait_for_pid_file(pid_file)
        assert runner_pid == proc.pid

        grandchild_pids = _wait_for_grandchildren_pids(
            grandchildren_pids_file, expected=2
        )
        assert len(grandchild_pids) == 2
        # Sanity: both grandchildren are alive before signal.
        assert all(_pid_alive(pid) for pid in grandchild_pids), (
            f"Grandchildren not alive before SIGTERM: {grandchild_pids}"
        )

        # Send SIGTERM to the runner-stub.
        os.kill(runner_pid, signal.SIGTERM)

        # Both grandchildren must be reaped within 8 seconds (6 s graceful
        # + 2 s overhead per task spec).
        all_dead, survivors = _wait_for_pids_dead(grandchild_pids, timeout=8.0)
        assert all_dead, (
            f"Grandchildren still alive 8 s after SIGTERM to runner-stub: "
            f"{survivors}"
        )

        # Runner-stub should also exit (cleanly) shortly after.
        try:
            proc.wait(timeout=4.0)
        except subprocess.TimeoutExpired:
            pytest.fail(
                "Runner-stub did not exit within 4 s after the tree-walker "
                "completed; chained shutdown handler may be broken."
            )

    finally:
        # Defensive cleanup: SIGKILL the runner-stub and any surviving
        # grandchildren so a failed assertion does not leak processes.
        if proc.poll() is None:
            try:
                proc.kill()
            except (ProcessLookupError, PermissionError):
                pass
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        _force_kill_pids(grandchild_pids)


# ---------------------------------------------------------------------------
# Test 2: SIGTERM escalates to SIGKILL for SIGTERM-ignoring grandchild
# ---------------------------------------------------------------------------

def test_sigterm_escalates_to_sigkill_for_ignoring_grandchild(tmp_path: Path):
    """A grandchild that ignores SIGTERM AND lives in its own PGID
    (``start_new_session=True``) must be SIGKILL'd by the runner-stub's
    tree-walker within the 6 s graceful + 2 s overhead = 8 s budget.

    SIGKILL cannot be ignored, so this verifies the survivor-SIGKILL phase
    of the tree-walker (psutil ``proc.kill()`` after ``wait_procs`` reports
    survivors).
    """
    pid_file = tmp_path / "runner_stub.pid"
    grandchildren_pids_file = tmp_path / "grandchildren.pids"

    src = _build_runner_stub_src(
        grandchildren_count_with_session=1,
        grandchildren_count_without_session=0,
        grandchild_src=_SIGTERM_IGNORING_GRANDCHILD_SRC,
        pid_file=pid_file,
        grandchildren_pids_file=grandchildren_pids_file,
    )

    proc = subprocess.Popen(
        [sys.executable, "-c", src],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    grandchild_pids: list[int] = []
    try:
        runner_pid = _wait_for_pid_file(pid_file)
        assert runner_pid == proc.pid

        grandchild_pids = _wait_for_grandchildren_pids(
            grandchildren_pids_file, expected=1
        )
        assert len(grandchild_pids) == 1
        assert _pid_alive(grandchild_pids[0]), (
            f"SIGTERM-ignoring grandchild {grandchild_pids[0]} not alive "
            f"before SIGTERM to runner-stub"
        )

        # Send SIGTERM to the runner-stub.
        os.kill(runner_pid, signal.SIGTERM)

        # The grandchild must be SIGKILL'd within the 8 s budget — its
        # SIGTERM handler is SIG_IGN, so only the survivor-SIGKILL phase
        # of the tree-walker can terminate it.
        all_dead, survivors = _wait_for_pids_dead(grandchild_pids, timeout=8.0)
        assert all_dead, (
            f"SIGTERM-ignoring grandchild still alive 8 s after SIGTERM to "
            f"runner-stub; survivor-SIGKILL phase did not fire: {survivors}"
        )

        # Runner-stub should also exit shortly after.
        try:
            proc.wait(timeout=4.0)
        except subprocess.TimeoutExpired:
            pytest.fail(
                "Runner-stub did not exit within 4 s after the tree-walker "
                "completed."
            )

    finally:
        if proc.poll() is None:
            try:
                proc.kill()
            except (ProcessLookupError, PermissionError):
                pass
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        _force_kill_pids(grandchild_pids)
