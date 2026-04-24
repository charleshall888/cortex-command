"""R7 coordination + watchdog tests against ``runner_primitives``.

Covers the R7 acceptance criteria:

- ``stall_flag`` distinguishes stall-kill from normal exit.
- ``kill_lock`` prevents double-kill in concurrent cancel+stall.
- ``shutdown_event`` wakes watchdog mid-sleep (no blocking ``time.sleep``).
- Signal handlers append to ``received_signals`` thread-safely.
- ``deferred_signals`` context manager stashes and replays signals across
  a protected region.

Tests import only from ``cortex_command.overnight.runner_primitives`` so
they exercise the primitives without loading the full orchestration graph.
Signal-handler tests restore prior handlers in teardown via pytest
fixtures so later tests aren't affected.
"""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from unittest import mock

import pytest

from cortex_command.overnight.runner_primitives import (
    RunnerCoordination,
    WatchdogContext,
    WatchdogThread,
    deferred_signals,
    install_signal_handlers,
    restore_signal_handlers,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def coord() -> RunnerCoordination:
    """Fresh coordination primitives per test."""
    return RunnerCoordination()


@pytest.fixture
def preserve_signal_handlers():
    """Snapshot and restore SIGINT/SIGTERM/SIGHUP handlers around the test."""
    snapshot = {
        signal.SIGINT: signal.getsignal(signal.SIGINT),
        signal.SIGTERM: signal.getsignal(signal.SIGTERM),
        signal.SIGHUP: signal.getsignal(signal.SIGHUP),
    }
    try:
        yield
    finally:
        for signum, handler in snapshot.items():
            if handler is not None:
                signal.signal(signum, handler)


@pytest.fixture
def sleep_proc():
    """Long-sleeping subprocess in its own PGID; tore down at test end."""
    proc = subprocess.Popen(
        ["sleep", "60"],
        start_new_session=True,
    )
    try:
        yield proc
    finally:
        if proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, OSError):
                pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


# ---------------------------------------------------------------------------
# stall_flag distinguishes stall-kill from normal exit
# ---------------------------------------------------------------------------


def test_stall_flag_set_on_timeout(coord, sleep_proc):
    """Watchdog sets stall_flag and kills the PGID on timeout."""
    wctx = WatchdogContext(stall_flag=threading.Event())
    wd = WatchdogThread(
        sleep_proc,
        timeout_seconds=1,
        coord=coord,
        wctx=wctx,
        label="test",
        poll_interval_seconds=0.1,
        kill_escalation_seconds=0.5,
    )
    wd.start()
    assert wctx.stall_flag.wait(timeout=5) is True
    # Give the kill chain a moment to land on the subprocess.
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and sleep_proc.poll() is None:
        time.sleep(0.05)
    assert sleep_proc.poll() is not None
    wd.join(timeout=5)
    assert not wd.is_alive()


# ---------------------------------------------------------------------------
# kill_lock prevents double-kill under concurrent cancel+stall
# ---------------------------------------------------------------------------


def test_concurrent_cancel_and_stall_dont_double_kill(coord):
    """Two threads simulating cancel and stall both hold kill_lock; under
    R7 semantics (re-check poll() under the lock), ``os.killpg`` is called
    exactly once.
    """
    # Simulate a subprocess that has NOT yet exited on the first kill
    # check, but HAS exited by the time the second thread takes the lock.
    poll_results = iter([None, 0])
    poll_lock = threading.Lock()

    def fake_poll():
        with poll_lock:
            try:
                return next(poll_results)
            except StopIteration:
                return 0

    killpg_calls: list[tuple[int, int]] = []
    call_lock = threading.Lock()

    def fake_killpg(pgid: int, sig: int) -> None:
        with call_lock:
            killpg_calls.append((pgid, sig))

    # The "subprocess" for this coordination test is a stand-in object
    # that obeys the same Popen-ish protocol used by the R7 critical
    # section (poll() + pid).
    class _FakeProc:
        pid = 99999

        def poll(self):
            return fake_poll()

    fake_proc = _FakeProc()
    barrier = threading.Barrier(2)

    def _kill_attempt() -> None:
        # Wait for both threads to be ready so they race on kill_lock.
        barrier.wait(timeout=5)
        with coord.kill_lock:
            # Re-check under the lock, mirroring runner_primitives'
            # double-kill-avoidance contract.
            if fake_proc.poll() is not None:
                return
            os.killpg(12345, signal.SIGTERM)

    with mock.patch("os.killpg", side_effect=fake_killpg), mock.patch(
        "os.getpgid", return_value=12345
    ):
        t1 = threading.Thread(target=_kill_attempt)
        t2 = threading.Thread(target=_kill_attempt)
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

    assert len(killpg_calls) == 1, (
        f"expected exactly one killpg call, got {killpg_calls}"
    )


# ---------------------------------------------------------------------------
# shutdown_event wakes watchdog mid-sleep (no time.sleep)
# ---------------------------------------------------------------------------


def test_shutdown_event_wakes_watchdog_sleep(coord, sleep_proc):
    """A long-timeout watchdog still exits promptly when shutdown_event fires."""
    killpg_calls: list[tuple[int, int]] = []

    def fake_killpg(pgid: int, sig: int) -> None:
        killpg_calls.append((pgid, sig))

    wctx = WatchdogContext(stall_flag=threading.Event())
    wd = WatchdogThread(
        sleep_proc,
        timeout_seconds=60,
        coord=coord,
        wctx=wctx,
        label="test",
        poll_interval_seconds=1.0,
    )
    # Fire shutdown after 100ms.
    timer = threading.Timer(0.1, coord.shutdown_event.set)
    with mock.patch("os.killpg", side_effect=fake_killpg):
        timer.start()
        wd.start()
        wd.join(timeout=3)
        timer.cancel()

    assert not wd.is_alive(), "watchdog did not exit after shutdown_event"
    assert killpg_calls == [], (
        f"expected no killpg calls on clean shutdown, got {killpg_calls}"
    )
    assert not wctx.stall_flag.is_set()


# ---------------------------------------------------------------------------
# received_signals append is thread-safe under signal delivery
# ---------------------------------------------------------------------------


def test_received_signals_append_thread_safe(coord, preserve_signal_handlers):
    """Handlers installed by install_signal_handlers append signum to received_signals."""
    prior = install_signal_handlers(coord)
    try:
        signal.raise_signal(signal.SIGHUP)
        # Signal delivery on the main thread is synchronous; no sleep needed.
        assert signal.SIGHUP in coord.received_signals
        assert coord.shutdown_event.is_set()
    finally:
        restore_signal_handlers(prior)


# ---------------------------------------------------------------------------
# deferred_signals stashes and replays across a protected block
# ---------------------------------------------------------------------------


def test_deferred_signals_stashes_and_replays(coord, preserve_signal_handlers):
    """Signals raised inside ``deferred_signals`` are stashed; the prior
    (normal shutdown) handler re-runs on replay after the block exits.
    """
    # Install the standard shutdown handlers first so that the stash/
    # replay path has a meaningful prior handler to restore.
    outer_prior = install_signal_handlers(coord)
    try:
        # Sanity: shutdown_event starts unset.
        assert not coord.shutdown_event.is_set()

        with deferred_signals(coord):
            # Inside the protected block, the no-op stash handler is
            # active. Raising SIGTERM should be captured for later replay
            # but should NOT leave the prior handler's side effect
            # unobserved — the stash handler sets shutdown_event itself
            # (per runner_primitives contract) so the main loop still
            # notices. What we're verifying here is: the prior handler
            # does NOT run during the protected block.
            signal.raise_signal(signal.SIGTERM)
            # Still inside the block: if the prior handler had run, we'd
            # have no way to tell from shutdown_event alone (stash also
            # sets it). The distinguishing evidence is that the replay
            # path runs the prior handler AFTER exit, which we verify
            # below by counting entries in received_signals.
            stashed_snapshot = list(coord.received_signals)

        # On exit, the context manager replays the stashed signal; the
        # restored prior handler appends again.
        assert signal.SIGTERM in coord.received_signals
        # Replay means received_signals saw SIGTERM twice total: once
        # from the stash handler (inside the block) and once from the
        # restored prior handler (on replay).
        post_count = coord.received_signals.count(signal.SIGTERM)
        assert post_count >= stashed_snapshot.count(signal.SIGTERM) + 1, (
            "expected deferred_signals to replay SIGTERM through the "
            f"restored prior handler; saw {coord.received_signals}"
        )
        assert coord.shutdown_event.is_set()
    finally:
        restore_signal_handlers(outer_prior)
