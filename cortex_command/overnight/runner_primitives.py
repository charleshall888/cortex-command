"""Threading, signal, and watchdog primitives for the overnight runner.

Isolates the R7 coordination primitives (``shutdown_event``, per-watchdog
``stall_flag``, ``state_lock``, ``kill_lock``), R14 signal-handler
installation, and the :class:`WatchdogThread` class in a standalone,
stdlib-only leaf module. ``runner.py`` imports from here, and the
threading test suite exercises these primitives without loading the full
orchestration graph.

The module never imports from ``cortex_command.overnight.*`` — keep it
leaf-level so tests remain lightweight.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Any, Iterator


# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

#: Default poll interval for the watchdog's ``shutdown_event.wait`` loop.
#: Chosen to balance shutdown responsiveness against wakeup churn.
DEFAULT_WATCHDOG_POLL_INTERVAL_SECONDS: float = 1.0

#: Default delay between SIGTERM and the SIGKILL escalation in
#: :meth:`WatchdogThread._kill_pgid`. Keep short enough that a truly
#: stalled subprocess cannot linger indefinitely.
DEFAULT_KILL_ESCALATION_SECONDS: float = 5.0

#: Signals whose handlers trigger clean shutdown (R14).
_SHUTDOWN_SIGNALS: tuple[int, ...] = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)


# ---------------------------------------------------------------------------
# Coordination primitives (R7)
# ---------------------------------------------------------------------------

@dataclass
class RunnerCoordination:
    """Process-wide coordination primitives shared by main + watchdog threads.

    Fields are intentionally mutable and populated with fresh instances
    at each runner invocation. ``received_signals`` is a plain ``list`` —
    writes from signal handlers rely on the GIL-atomic guarantee of
    ``list.append`` (CPython implementation detail, but the only option
    that remains async-signal-safe in pure Python).
    """

    shutdown_event: threading.Event = field(default_factory=threading.Event)
    state_lock: threading.Lock = field(default_factory=threading.Lock)
    kill_lock: threading.Lock = field(default_factory=threading.Lock)
    received_signals: list[int] = field(default_factory=list)


@dataclass
class WatchdogContext:
    """Per-subprocess watchdog context.

    One instance is created per spawned subprocess (orchestrator,
    batch_runner). ``stall_flag`` is set by the watchdog when it decides
    to kill its subprocess; the main thread checks this after
    ``Popen.wait()`` returns to distinguish stall-kill from normal exit.
    """

    stall_flag: threading.Event = field(default_factory=threading.Event)


# ---------------------------------------------------------------------------
# Watchdog thread
# ---------------------------------------------------------------------------

class WatchdogThread(threading.Thread):
    """Stall-detection watchdog for a spawned subprocess.

    Sleeps in ``coord.shutdown_event.wait(timeout=poll_interval)`` — never
    via stdlib blocking sleep — so SIGHUP/SIGTERM handlers (which set
    ``shutdown_event``) wake the watchdog immediately.

    On elapsed > ``timeout_seconds``, sets ``wctx.stall_flag``, acquires
    ``coord.kill_lock``, terminates the subprocess's process group with
    ``SIGTERM`` (escalating to ``SIGKILL`` after
    ``kill_escalation_seconds``), releases the lock, and exits.

    Daemon thread: does not prevent interpreter shutdown.
    """

    def __init__(
        self,
        proc: subprocess.Popen,
        timeout_seconds: float,
        coord: RunnerCoordination,
        wctx: WatchdogContext,
        label: str,
        *,
        poll_interval_seconds: float = DEFAULT_WATCHDOG_POLL_INTERVAL_SECONDS,
        kill_escalation_seconds: float = DEFAULT_KILL_ESCALATION_SECONDS,
    ) -> None:
        super().__init__(name=f"watchdog-{label}", daemon=True)
        self._proc = proc
        self._timeout_seconds = timeout_seconds
        self._coord = coord
        self._wctx = wctx
        self._label = label
        self._poll_interval_seconds = poll_interval_seconds
        self._kill_escalation_seconds = kill_escalation_seconds

    def run(self) -> None:
        elapsed = 0.0
        while True:
            # Sleep via the shared shutdown_event — SIGHUP sets this and
            # wakes us immediately. Never call a blocking stdlib sleep.
            woke_for_shutdown = self._coord.shutdown_event.wait(
                timeout=self._poll_interval_seconds
            )
            if woke_for_shutdown:
                return

            # Subprocess already exited on its own — nothing to watch.
            if self._proc.poll() is not None:
                return

            elapsed += self._poll_interval_seconds
            if elapsed > self._timeout_seconds:
                self._kill_for_stall()
                return

    def _kill_for_stall(self) -> None:
        """Signal the process group for stall + escalate to SIGKILL."""
        self._wctx.stall_flag.set()
        with self._coord.kill_lock:
            # Re-check under the lock: the main thread's cleanup path
            # may have already torn the subprocess down.
            if self._proc.poll() is not None:
                return
            try:
                pgid = os.getpgid(self._proc.pid)
            except ProcessLookupError:
                return
            try:
                os.killpg(pgid, signal.SIGTERM)
            except ProcessLookupError:
                return

            # Escalate to SIGKILL if SIGTERM didn't land.
            if self._coord.shutdown_event.wait(
                timeout=self._kill_escalation_seconds
            ):
                # Shutdown requested during escalation window — still
                # force-kill so the PGID doesn't linger.
                pass
            if self._proc.poll() is None:
                try:
                    os.killpg(pgid, signal.SIGKILL)
                except ProcessLookupError:
                    return


# ---------------------------------------------------------------------------
# Signal handlers (R14)
# ---------------------------------------------------------------------------

def install_signal_handlers(coord: RunnerCoordination) -> dict[int, Any]:
    """Install minimum-safe shutdown handlers for SIGINT/SIGTERM/SIGHUP.

    Each handler sets ``coord.shutdown_event``, appends the signal
    number to ``coord.received_signals`` (GIL-atomic), and returns.
    Returns the prior handler map so callers can restore at cleanup end
    via :func:`restore_signal_handlers`.
    """

    def _handler(signum: int, _frame: Any) -> None:
        coord.received_signals.append(signum)
        coord.shutdown_event.set()

    prior: dict[int, Any] = {}
    for signum in _SHUTDOWN_SIGNALS:
        prior[signum] = signal.signal(signum, _handler)
    return prior


def restore_signal_handlers(prior_handlers: dict[int, Any]) -> None:
    """Restore the original signal handlers captured by :func:`install_signal_handlers`."""
    for signum, handler in prior_handlers.items():
        if handler is None:
            continue
        signal.signal(signum, handler)


@contextlib.contextmanager
def deferred_signals(coord: RunnerCoordination) -> Iterator[None]:
    """Defer SIGINT/SIGTERM/SIGHUP delivery across a critical section.

    Used by callers to wrap individual ``os.replace`` sites inside
    ``state.save_state`` and ``events.log_event``: on enter, swaps in
    no-op handlers that stash pending signals into a local list; on
    exit, restores the prior handlers and replays the stashed signals
    via :func:`signal.raise_signal` so the normal shutdown path still
    runs.

    Only the narrow atomic-write region is shielded — cleanup itself
    runs on the main thread after the poll loop, so async-signal-safety
    is not a concern there.
    """
    pending: list[int] = []

    def _stash(signum: int, _frame: Any) -> None:
        pending.append(signum)
        # Still mark shutdown requested so the main loop notices at
        # its next safe point even if the replay path is skipped.
        coord.received_signals.append(signum)
        coord.shutdown_event.set()

    prior: dict[int, Any] = {}
    for signum in _SHUTDOWN_SIGNALS:
        prior[signum] = signal.signal(signum, _stash)

    try:
        yield
    finally:
        for signum, handler in prior.items():
            if handler is None:
                continue
            signal.signal(signum, handler)
        for signum in pending:
            signal.raise_signal(signum)
