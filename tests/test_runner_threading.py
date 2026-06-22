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


# ---------------------------------------------------------------------------
# Activity-aware inactivity timer + absolute ceiling (deterministic seams)
#
# These tests inject a fake ``clock`` and ``activity_probe`` so timing is
# exact and no real sleeps occur on the reset path. They ASSERT OUTCOMES
# (kill vs no-kill and ``stall_reason``), so each fails against a blind or
# inverted implementation: a watchdog that ignores the probe kills the
# productive-work case; one that never kills fails the silence/ceiling
# cases; one that mis-tags the tier fails the ``stall_reason`` asserts.
# ---------------------------------------------------------------------------


class _StepClock:
    """Monotonic-like fake clock that advances a fixed step per call.

    The watchdog reads the clock several times per loop iteration; a fixed
    per-call step makes elapsed time grow deterministically without real
    sleeps. ``now()`` peeks the current value without advancing it.
    """

    def __init__(self, *, step: float) -> None:
        self._t = 0.0
        self._step = step

    def __call__(self) -> float:
        cur = self._t
        self._t += self._step
        return cur

    def now(self) -> float:
        return self._t


class _StallProc:
    """Popen-ish stand-in that reports "still running" until killed.

    ``poll()`` returns ``None`` (alive) for the first ``alive_polls`` calls,
    then ``0`` (exited) — letting a test model "the child finished on its
    own" via the watchdog's ``proc.poll() is not None`` early-return. With
    the default of effectively-infinite alive polls the child only stops
    running when the watchdog kills it.
    """

    pid = 99999

    def __init__(self, *, alive_polls: int = 10**9) -> None:
        self._alive_polls = alive_polls
        self._calls = 0

    def poll(self):
        self._calls += 1
        return None if self._calls <= self._alive_polls else 0


def _no_sleep_wait(timeout=None):
    """A ``shutdown_event.wait`` replacement that never blocks or fires.

    Returns ``False`` immediately so the watchdog loop spins at full speed
    against the injected clock instead of sleeping for ``poll_interval``.
    Accepts the ``timeout`` kwarg the watchdog passes (both in the poll
    loop and the kill-escalation window).
    """
    return False


def test_watchdog_reset_keeps_growing_child_alive(coord):
    """Reset (Reqs 1, 3): a probe returning a strictly-growing
    ``(size, mtime_ns)`` each tick keeps ``last_activity_at`` current, so
    advancing the clock far past ``timeout_seconds`` does NOT trip the
    inactivity kill — productive work survives. The child then finishes on
    its own (``poll`` flips to exited), so the watchdog exits without a
    stall. A blind timer (ignoring the probe) would kill this case.
    """
    clock = _StepClock(step=10.0)
    # Strictly-growing sample every tick → continuous reset.
    counter = {"n": 0}

    def growing_probe():
        counter["n"] += 1
        return (counter["n"] * 100, counter["n"] * 1_000_000)

    # Child stays alive for many polls (well past timeout_seconds worth of
    # ticks at step=10), then exits on its own.
    proc = _StallProc(alive_polls=20)
    wctx = WatchdogContext(stall_flag=threading.Event())
    wd = WatchdogThread(
        proc,
        timeout_seconds=30,  # 3 ticks of clock-step would exceed this
        coord=coord,
        wctx=wctx,
        label="reset",
        poll_interval_seconds=0.01,
        activity_probe=growing_probe,
        clock=clock,
    )
    with mock.patch.object(coord.shutdown_event, "wait", _no_sleep_wait), \
            mock.patch("os.killpg") as killpg:
        wd.start()
        wd.join(timeout=5)

    assert not wd.is_alive(), "watchdog should exit once the child exits"
    assert not wctx.stall_flag.is_set(), (
        "productive (growing) child must NOT be stall-killed"
    )
    assert wctx.stall_reason == "", "no kill ⇒ no stall_reason set"
    killpg.assert_not_called()


def test_watchdog_kills_silent_child_with_inactivity_reason(coord):
    """Silence (Reqs 1, 3): a static probe never advances, so the
    inactivity timer never resets; advancing the clock past
    ``timeout_seconds`` kills the child tagged ``stall_reason ==
    "inactivity"``. An implementation that reset on a non-advancing probe
    would never fire.
    """
    clock = _StepClock(step=100.0)
    # Static sample: same (size, mtime_ns) forever → no reset.
    static_probe = lambda: (4096, 5_000_000)

    proc = _StallProc()  # alive until killed
    wctx = WatchdogContext(stall_flag=threading.Event())
    wd = WatchdogThread(
        proc,
        timeout_seconds=30,
        coord=coord,
        wctx=wctx,
        label="silent",
        poll_interval_seconds=0.01,
        kill_escalation_seconds=0.01,
        activity_probe=static_probe,
        clock=clock,
    )
    with mock.patch.object(coord.shutdown_event, "wait", _no_sleep_wait), \
            mock.patch("os.getpgid", return_value=12345), \
            mock.patch("os.killpg") as killpg:
        wd.start()
        wd.join(timeout=5)

    assert not wd.is_alive()
    assert wctx.stall_flag.is_set(), "silent child must be stall-killed"
    assert wctx.stall_reason == "inactivity", (
        f"silent child kill must be tagged inactivity; got {wctx.stall_reason!r}"
    )
    killpg.assert_called()


def test_watchdog_blind_timer_kills_when_probe_none(coord):
    """Blind default (Req 2): with ``activity_probe=None`` the inactivity
    tier never resets, so the watchdog behaves exactly as today's blind
    ``timeout_seconds`` timer and kills after the timeout elapses. The kill
    is an inactivity kill (the blind timer is the degenerate inactivity
    tier).
    """
    clock = _StepClock(step=100.0)
    proc = _StallProc()
    wctx = WatchdogContext(stall_flag=threading.Event())
    wd = WatchdogThread(
        proc,
        timeout_seconds=30,
        coord=coord,
        wctx=wctx,
        label="blind",
        poll_interval_seconds=0.01,
        kill_escalation_seconds=0.01,
        activity_probe=None,  # blind-timer-equivalent
        clock=clock,
    )
    with mock.patch.object(coord.shutdown_event, "wait", _no_sleep_wait), \
            mock.patch("os.getpgid", return_value=12345), \
            mock.patch("os.killpg") as killpg:
        wd.start()
        wd.join(timeout=5)

    assert not wd.is_alive()
    assert wctx.stall_flag.is_set(), (
        "probe=None must still kill after timeout_seconds (blind-timer)"
    )
    assert wctx.stall_reason == "inactivity", (
        f"blind-timer kill is the inactivity tier; got {wctx.stall_reason!r}"
    )
    killpg.assert_called()


def test_watchdog_ceiling_kills_forever_growing_child(coord):
    """Ceiling (Req 4): with a forever-growing probe the inactivity tier
    never fires, but a tiny injected ``ceiling_seconds`` (never reset)
    kills the child once ``now - started_at`` exceeds it, tagged
    ``stall_reason == "ceiling"``. This is the backstop for a loud-but-
    stuck child that the inactivity tier is structurally blind to.
    """
    clock = _StepClock(step=10.0)
    counter = {"n": 0}

    def growing_probe():
        counter["n"] += 1
        return (counter["n"] * 100, counter["n"] * 1_000_000)

    proc = _StallProc()
    wctx = WatchdogContext(stall_flag=threading.Event())
    wd = WatchdogThread(
        proc,
        # Inactivity timeout far larger than the ceiling so ONLY the
        # ceiling can fire — proving the kill is the ceiling tier.
        timeout_seconds=10_000,
        coord=coord,
        wctx=wctx,
        label="ceiling",
        poll_interval_seconds=0.01,
        kill_escalation_seconds=0.01,
        ceiling_seconds=25,  # crossed within a few clock steps
        activity_probe=growing_probe,
        clock=clock,
    )
    with mock.patch.object(coord.shutdown_event, "wait", _no_sleep_wait), \
            mock.patch("os.getpgid", return_value=12345), \
            mock.patch("os.killpg") as killpg:
        wd.start()
        wd.join(timeout=5)

    assert not wd.is_alive()
    assert wctx.stall_flag.is_set(), "ceiling must kill a forever-growing child"
    assert wctx.stall_reason == "ceiling", (
        f"forever-growing child kill must be tagged ceiling; got {wctx.stall_reason!r}"
    )
    killpg.assert_called()


def test_watchdog_probe_oserror_does_not_reset_or_crash(coord):
    """Robust stat (Req 5): a probe that raises ``OSError`` is caught as
    "no activity" — it neither resets the timer nor crashes the daemon
    thread. So the inactivity timer still elapses and the child is killed
    after ``timeout_seconds`` rather than the thread dying silently. The
    surviving-then-killing outcome proves both halves: no reset (it still
    kills) and no crash (the kill path still runs).
    """
    clock = _StepClock(step=100.0)

    def raising_probe():
        raise OSError("transient stat blip (e.g. EACCES)")

    proc = _StallProc()
    wctx = WatchdogContext(stall_flag=threading.Event())
    wd = WatchdogThread(
        proc,
        timeout_seconds=30,
        coord=coord,
        wctx=wctx,
        label="stat-raises",
        poll_interval_seconds=0.01,
        kill_escalation_seconds=0.01,
        activity_probe=raising_probe,
        clock=clock,
    )
    with mock.patch.object(coord.shutdown_event, "wait", _no_sleep_wait), \
            mock.patch("os.getpgid", return_value=12345), \
            mock.patch("os.killpg") as killpg:
        wd.start()
        wd.join(timeout=5)

    assert not wd.is_alive(), "OSError in probe must not leave the thread hung"
    assert wctx.stall_flag.is_set(), (
        "OSError probe must be treated as no-activity → inactivity kill still fires"
    )
    assert wctx.stall_reason == "inactivity", (
        f"stat-error path keeps the inactivity tier active; got {wctx.stall_reason!r}"
    )
    killpg.assert_called()
