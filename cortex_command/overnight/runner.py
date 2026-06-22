"""Pure-Python overnight round-dispatch loop.

Replaces the round-dispatch core of ``runner.sh`` with a Python
orchestration layer that imports peer overnight modules directly rather
than spawning inline-Python heredocs or module-dispatch subprocesses
for in-process logic. External-process spawns are limited to the
``claude -p`` orchestrator agent and the ``cortex-batch-runner``
console-script shim (per R5).

Coordination primitives (R7), signal handling (R14), watchdog-based
stall detection (R13), per-session ``runner.pid`` writes (R8), and the
active-session pointer (R9) are shared with peer modules via
:mod:`cortex_command.overnight.runner_primitives` and
:mod:`cortex_command.overnight.ipc`.

All user-repo paths are received as ``run()`` arguments — no
``REPO_ROOT`` env var, no ``Path(__file__).parent`` traversal for
user-owned state (R20). Prompt templates are loaded once at ``run()``
entry via ``importlib.resources`` (R19).
"""

from __future__ import annotations

import fcntl
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from importlib.resources import files
from pathlib import Path
from typing import Any, Optional

import psutil

from cortex_command.common import read_criticality
from cortex_command.overnight import auth
from cortex_command.overnight import events
from cortex_command.overnight import fill_prompt
from cortex_command.overnight import integration_recovery
from cortex_command.overnight import interrupt
from cortex_command.overnight import ipc
from cortex_command.overnight import map_results
from cortex_command.overnight import plan
from cortex_command.overnight import report
from cortex_command.overnight import sandbox_settings
from cortex_command.overnight import smoke_test
from cortex_command.overnight import state as state_module
from cortex_command.overnight.batch_runner import main as batch_runner_main  # noqa: F401  (R5: in-process import list)
from cortex_command.overnight.constants import CIRCUIT_BREAKER_THRESHOLD
from cortex_command.overnight.orchestrator import run_batch  # noqa: F401  (R5: in-process import list)
from cortex_command.overnight.runner_primitives import (
    DEFAULT_KILL_ESCALATION_SECONDS,
    RunnerCoordination,
    WatchdogContext,
    WatchdogThread,
    deferred_signals,
    install_signal_handlers,
    restore_signal_handlers,
)


# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

#: Main-thread poll interval between ``Popen.wait(timeout=...)`` calls.
#: Short enough that shutdown requests reach the cleanup path quickly,
#: long enough to avoid busy-wait. Selected to sidestep PEP 475's
#: auto-retry of ``os.waitpid`` that would otherwise trap the main
#: thread in an un-interruptable blocking wait when a signal handler
#: sets ``shutdown_event`` without raising.
POLL_INTERVAL_SECONDS: float = 1.0

#: Delay between SIGTERM and SIGKILL escalation when the cleanup path
#: tears down an orphan subprocess. Matches the watchdog's escalation
#: window from :mod:`runner_primitives`.
KILL_ESCALATION_SECONDS: float = DEFAULT_KILL_ESCALATION_SECONDS

#: Stall-watchdog timeout (seconds of event-log silence before a
#: subprocess is considered stalled). Matches ``runner.sh:646``.
STALL_TIMEOUT_SECONDS: float = 1800.0

#: Runner-level heartbeat cadence (spec Req 11, Task 14). A runner-owned
#: daemon thread emits a ``HEARTBEAT`` event every this-many seconds across
#: ALL ``executing`` sub-phases — the planning span (between ``ROUND_START``
#: and the ``batch_runner`` spawn) AND the batch span — so the event log
#: never goes silent during healthy plan generation. Matches the
#: ``_heartbeat_loop`` cadence in ``orchestrator.py:465`` (300s); the runner
#: heartbeat covers the planning blind window where the batch heartbeat does
#: not run, and a slightly redundant emit during the batch span is harmless.
#: This advancing event-log timestamp is the prerequisite that makes
#: event-log staleness a valid liveness signal in every phase (Task 15).
RUNNER_HEARTBEAT_INTERVAL_SECONDS: float = 300.0

#: Orchestrator ``claude -p`` turn cap. Matches ``runner.sh:643``.
ORCHESTRATOR_MAX_TURNS: int = 50

#: Crash-loop resume bound (spec §R9, Task 11). ``cortex overnight start``
#: refuses to auto-resume a session paused with
#: ``paused_reason == "orchestrator_crash"`` once
#: ``crash_recovery_attempts`` exceeds this bound, unless ``--force`` is
#: passed. The #308 trigger class (e.g. a pre-commit gate blocking every
#: commit) is deterministic, so a blind auto-resume would crash-loop; the
#: bound stops it after one recovered attempt. A clean pause
#: (``budget_exhausted``/``signal``) is unaffected.
CRASH_RECOVERY_RESUME_BOUND: int = 1

#: Graceful shutdown budget for the SIGTERM tree-walker (R12 / Task 3).
#: When SIGTERM arrives, the tree-walker enumerates all descendants via
#: ``psutil.Process(os.getpid()).children(recursive=True)``, sends SIGTERM
#: to each, waits up to this many seconds for graceful exit via
#: ``psutil.wait_procs``, then SIGKILLs survivors. Strictly less than
#: ``overnight_cancel``'s outer 12-second SIGKILL budget so the runner's
#: in-handler survivor-SIGKILL phase always completes before any outer
#: SIGKILL hits the runner itself (closes the budget-race surfaced in
#: critical review).
DESCENDANT_GRACEFUL_SHUTDOWN_SECONDS: float = 6.0


# ---------------------------------------------------------------------------
# Idle-sleep assertion bound to the runner's lifetime (R4)
# ---------------------------------------------------------------------------

def _spawn_caffeinate_bound_to_runner() -> Optional[subprocess.Popen]:
    """Spawn ``caffeinate -i -w <runner_pid>`` bound to this runner's life.

    Holds the macOS no-idle-sleep assertion (``-i``) for exactly as long as
    the runner runs by binding caffeinate's lifetime to the runner's pid
    (``-w <pid>`` makes caffeinate exit when ``<pid>`` exits). This is the
    R4 process-tree contract:

    * The **runner** remains the ``start_new_session=True`` session leader
      (R2) — caffeinate is a child of the runner, NOT the ``Popen`` target
      / session leader, so it cannot break the detach.
    * caffeinate is spawned **by the runner**, NOT by the ~5s
      ``_spawn_runner_async`` shim — the shim returns at the handshake and
      a shim-owned assertion would drop there (the F3 bug). Binding to the
      runner pid makes the assertion outlive the handshake window and last
      for the runner's full lifetime.

    Called as the earliest action in :func:`run` — before ``load_state``
    and the takeover-lock acquisition — so the unasserted window is the
    sub-second ``Popen``→entry gap rather than the slow post-wake / cold-
    cache state-load + lock span. ``-i`` is the assertion; a bare ``-w``
    would hold NO assertion and is wrong.

    Best-effort: a missing ``caffeinate`` binary (non-macOS, stripped
    environments) must not crash the runner. Returns the ``Popen`` handle
    on success (so callers/tests can observe the child), or ``None`` if
    the binary is absent or the spawn fails. The child is left
    unsupervised — it self-exits when the runner pid exits via ``-w``.
    """
    try:
        return subprocess.Popen(
            ["caffeinate", "-i", "-w", str(os.getpid())],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
    except (OSError, ValueError):
        # Missing binary / spawn failure — idle-sleep prevention is
        # best-effort and must never crash the runner.
        return None


# ---------------------------------------------------------------------------
# SIGTERM descendant tree-walk (R12 / Task 3)
# ---------------------------------------------------------------------------

def _terminate_descendant_tree(
    graceful_timeout: float = DESCENDANT_GRACEFUL_SHUTDOWN_SECONDS,
) -> None:
    """Walk the runner's descendant tree on SIGTERM and reap each process.

    Enumerates all descendants via
    ``psutil.Process(os.getpid()).children(recursive=True)`` — this reaches
    grandchildren spawned with ``start_new_session=True`` (whose PGID
    diverges from the runner's), which ``os.killpg`` cannot signal. SIGTERMs
    each descendant via ``proc.terminate()``, waits up to ``graceful_timeout``
    seconds collectively for graceful exit via ``psutil.wait_procs``, then
    SIGKILLs survivors via ``proc.kill()``.

    The walk is at signal-receipt time (not at runner startup), so workers
    spawned later by ``batch_runner`` and their grandchildren are reached
    regardless of which spawn site set ``start_new_session=True``. The
    recorded-child-PGID approach is rejected (spec R12) because the runner
    does not know in advance which PGIDs ``batch_runner`` workers will use.

    All ``psutil`` exceptions during enumeration / signal / wait are
    swallowed: a failure to reap one descendant must not prevent the
    handler from continuing on to the next, and the handler itself must
    return cleanly so the chained shutdown handler runs.
    """
    try:
        descendants = psutil.Process(os.getpid()).children(recursive=True)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return

    if not descendants:
        return

    # Phase 1: SIGTERM each descendant for graceful exit.
    for proc in descendants:
        try:
            proc.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    # Phase 2: collective wait for graceful exit (up to graceful_timeout).
    try:
        _gone, alive = psutil.wait_procs(descendants, timeout=graceful_timeout)
    except Exception:
        alive = descendants

    # Phase 3: SIGKILL any survivors.
    for proc in alive:
        try:
            proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue


def _install_sigterm_tree_walker(prior_handler: Any) -> Any:
    """Install a SIGTERM handler that reaps descendants then chains to prior.

    Replaces whatever SIGTERM handler is currently installed (typically
    the shutdown-event-setter from
    :func:`runner_primitives.install_signal_handlers`) with a wrapper that:

      1. Walks the descendant tree via :func:`_terminate_descendant_tree`,
         SIGTERM-then-SIGKILL with a ``DESCENDANT_GRACEFUL_SHUTDOWN_SECONDS``
         graceful budget.
      2. Chains to ``prior_handler`` so the runner's main-thread cleanup
         (state-paused write, circuit_breaker event, signal replay) still
         runs on the next poll-loop tick.

    Returns the handler that was previously installed (i.e., what was
    passed in as ``prior_handler``, modulo signal-module-internal sentinel
    values), so callers can restore at cleanup end.
    """

    def _handle_sigterm(signum: int, frame: Any) -> None:
        try:
            _terminate_descendant_tree()
        finally:
            # Chain to the prior handler so the existing shutdown
            # bookkeeping (set shutdown_event, append signum) still runs.
            if callable(prior_handler):
                prior_handler(signum, frame)

    signal.signal(signal.SIGTERM, _handle_sigterm)
    return prior_handler


# ---------------------------------------------------------------------------
# Dry-run mode (R15)
# ---------------------------------------------------------------------------

def dry_run_echo(label: str, *args: object) -> None:
    """Echo a ``DRY-RUN`` line matching ``runner.sh``'s dry_run_echo output.

    Format: ``" ".join(["DRY-RUN", label, *non_empty_args])``. The empty-
    arg filter is load-bearing: bash unquoted ``$DRAFT_FLAG`` word-splits
    to zero tokens when empty; Python must filter empties rather than
    emit an empty-string token so output stays byte-identical with the
    bash reference captured at ``tests/fixtures/dry_run_reference.txt``.

    Writes to stdout (not stderr) because the bash reference prints
    ``DRY-RUN`` lines on stdout.
    """
    parts: list[str] = ["DRY-RUN", label]
    for arg in args:
        if arg is None or arg == "":
            continue
        parts.append(str(arg))
    print(" ".join(parts), flush=True)


# ---------------------------------------------------------------------------
# Notify fallback (R22)
# ---------------------------------------------------------------------------

def _notify(
    message: str,
    notify_path: Optional[Path] = None,
) -> None:
    """Send a notification via ~/.claude/notify.sh with stderr fallback.

    When ``notify_path`` (default ``~/.claude/notify.sh``) is missing,
    the message is printed to **stderr** (not stdout) with a
    ``NOTIFY: `` prefix — stdout is the orchestrator agent's input
    channel and must not be polluted.
    """
    if notify_path is None:
        notify_path = Path.home() / ".claude" / "notify.sh"
    if notify_path.exists():
        try:
            subprocess.run([str(notify_path), message], check=False)
        except (OSError, subprocess.SubprocessError):
            pass
    else:
        print(f"NOTIFY: {message}", file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# Subprocess helpers
# ---------------------------------------------------------------------------

def _poll_subprocess(
    proc: subprocess.Popen,
    coord: RunnerCoordination,
) -> Optional[int]:
    """Block until ``proc`` exits or shutdown is requested.

    Polls via ``proc.wait(timeout=POLL_INTERVAL_SECONDS)`` to sidestep
    PEP 475's ``os.waitpid`` auto-retry that would otherwise prevent the
    main thread from noticing a signal-handler-set
    ``shutdown_event``. When ``shutdown_event`` fires, acquires
    ``kill_lock`` and tears down ``proc``'s PGID (SIGTERM → SIGKILL
    after :data:`KILL_ESCALATION_SECONDS`), then returns ``None``.

    Returns the subprocess exit code on a normal exit; ``None`` when
    shutdown intercepted the wait.
    """
    while True:
        try:
            return proc.wait(timeout=POLL_INTERVAL_SECONDS)
        except subprocess.TimeoutExpired:
            if coord.shutdown_event.is_set():
                _kill_subprocess_group(proc, coord)
                return None


def _kill_subprocess_group(
    proc: subprocess.Popen,
    coord: RunnerCoordination,
) -> None:
    """Terminate ``proc``'s PGID under ``kill_lock``, escalating to SIGKILL."""
    with coord.kill_lock:
        if proc.poll() is not None:
            return
        try:
            pgid = os.getpgid(proc.pid)
        except ProcessLookupError:
            return
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            return
        # Escalate to SIGKILL if SIGTERM didn't land.
        deadline = time.monotonic() + KILL_ESCALATION_SECONDS
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                return
            time.sleep(0.1)
        if proc.poll() is None:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                return


# ---------------------------------------------------------------------------
# Runner-level heartbeat (spec Req 11, Task 14)
# ---------------------------------------------------------------------------

def _emit_runner_heartbeat(
    events_path: Path,
    session_id: str,
    round_num: int,
) -> None:
    """Append a single ``HEARTBEAT`` event for the runner's executing span.

    Reuses :data:`events.HEARTBEAT` (already in the event registry — no new
    event literal is introduced) and the same ``events.log_event`` path the
    runner uses for its other events. The ``source`` detail marks it as the
    runner-owned heartbeat to distinguish it from the batch_runner's
    ``_heartbeat_loop`` emit, which carries the per-feature pending/running
    counters this runner-level emit deliberately omits (those counts are not
    known to the runner during the planning sub-phase).

    Best-effort: any failure is swallowed so a transient log-write error can
    never crash the runner. The point of the heartbeat is liveness, not
    durability — a missed beat self-corrects on the next cadence tick.
    """
    try:
        events.log_event(
            events.HEARTBEAT,
            round=round_num,
            details={"session_id": session_id, "source": "runner"},
            log_path=events_path,
        )
    except Exception:
        pass


class RunnerHeartbeatThread(threading.Thread):
    """Runner-owned daemon that emits ``HEARTBEAT`` across executing sub-phases.

    Closes the planning-phase blind window (spec Req 11): today ``HEARTBEAT``
    is emitted only by ``_heartbeat_loop`` inside ``run_batch`` (the
    batch_runner subprocess), so during the planning sub-phase — between
    ``ROUND_START`` and the batch_runner spawn — the runner emits nothing and
    ``overnight-events.log`` can be silent >30 min during healthy plan
    generation. This thread emits a runner-level heartbeat on a fixed cadence
    (:data:`RUNNER_HEARTBEAT_INTERVAL_SECONDS`) for the entire planning→batch
    span, advancing the last-event timestamp in every ``executing`` sub-phase
    so event-log staleness becomes a valid liveness signal (Task 15's
    prerequisite).

    Sleeps in ``coord.shutdown_event.wait(timeout=interval)`` — never a
    blocking stdlib sleep — so a SIGTERM/SIGHUP handler (which sets
    ``shutdown_event``) wakes the thread immediately for a prompt stop. Daemon
    thread: never prevents interpreter shutdown. Additive — it does NOT touch
    the existing batch ``_heartbeat_loop``; a slightly redundant beat during
    the batch span is harmless.
    """

    def __init__(
        self,
        coord: RunnerCoordination,
        events_path: Path,
        session_id: str,
        round_num: int,
        *,
        interval_seconds: float = RUNNER_HEARTBEAT_INTERVAL_SECONDS,
    ) -> None:
        super().__init__(name="runner-heartbeat", daemon=True)
        self._coord = coord
        self._events_path = events_path
        self._session_id = session_id
        self._round_num = round_num
        self._interval_seconds = interval_seconds
        self._stop_event = threading.Event()

    def set_round(self, round_num: int) -> None:
        """Update the round number stamped on subsequent heartbeats.

        Called by the main loop as it advances rounds so the runner-level
        heartbeat carries the round it is currently executing. A plain field
        write is safe: int assignment is atomic under the GIL and a stale read
        on a cadence tick is immaterial to liveness.
        """
        self._round_num = round_num

    def stop(self) -> None:
        """Signal the thread to exit before its next cadence tick.

        Sets the thread's own stop event so a clean (non-signal) loop exit
        wakes the ``wait`` immediately rather than blocking ``join`` for up to
        a full cadence interval. The signal path reaches the same exit via
        ``coord.shutdown_event`` (checked each tick), but the explicit stop is
        what wakes the thread promptly on the clean path.
        """
        self._stop_event.set()

    def run(self) -> None:
        while True:
            # Block for the cadence interval, waking immediately on an
            # explicit ``stop()``. ``wait`` returns True when ``_stop_event``
            # is set (clean-exit stop) and False on timeout (time to beat).
            if self._stop_event.wait(timeout=self._interval_seconds):
                return
            # A SIGTERM/SIGHUP handler sets ``shutdown_event`` but not
            # ``_stop_event``; honor it as an exit trigger on the next tick so
            # the heartbeat stops once shutdown is in progress.
            if self._coord.shutdown_event.is_set():
                return
            _emit_runner_heartbeat(
                self._events_path,
                self._session_id,
                self._round_num,
            )


# ---------------------------------------------------------------------------
# Round-loop helpers
# ---------------------------------------------------------------------------

def _count_pending(state: state_module.OvernightState) -> int:
    """Count features whose status blocks round completion."""
    return sum(
        1
        for fs in state.features.values()
        if fs.status in ("pending", "running", "paused")
    )


def _count_merged(state: state_module.OvernightState) -> int:
    """Count merged features (terminal success status)."""
    return sum(1 for fs in state.features.values() if fs.status == "merged")


def _count_synthesizer_deferred(events_path: Path, session_id: str) -> int:
    """Count ``PLAN_SYNTHESIS_DEFERRED`` events for the given session.

    Reads the JSONL events log at ``events_path`` and returns the number
    of entries whose ``event`` field matches
    :data:`events.PLAN_SYNTHESIS_DEFERRED` AND whose ``session_id`` field
    matches the provided ``session_id``. The per-session events log path
    is the file the runner already writes to; the ``session_id`` filter
    is defensive because ``read_events`` reads the file directly and the
    file is per-session by construction, but the filter shields against
    archived entries from a re-used path.

    Returns 0 when the log does not exist or contains no matching
    entries. The helper is extracted (not inline) so the circuit-breaker
    test can call it directly with a synthetic events log.
    """
    matched = 0
    for evt in events.read_events(events_path):
        if evt.get("event") != events.PLAN_SYNTHESIS_DEFERRED:
            continue
        if evt.get("session_id") != session_id:
            continue
        matched += 1
    return matched


def _save_state_locked(
    state: state_module.OvernightState,
    state_path: Path,
    coord: RunnerCoordination,
) -> None:
    """Persist ``state`` under ``state_lock`` with signal-deferral shielding.

    The ``deferred_signals`` context manager stashes SIGINT/SIGTERM/SIGHUP
    across the atomic ``os.replace`` site inside ``state.save_state`` so
    a signal cannot interrupt the rename. Signals that arrive during the
    critical section are replayed after the write completes; the normal
    shutdown path then takes over at the main loop's next
    ``shutdown_event`` check.
    """
    with coord.state_lock, deferred_signals(coord):
        state_module.save_state(state, state_path)


def _transition_paused(
    state_path: Path,
    events_path: Path,
    coord: RunnerCoordination,
    reason: str,
    round_num: int,
) -> None:
    """Transition session to ``paused`` with ``paused_reason`` set.

    Idempotent — skips the transition when the session is already in
    ``paused`` or ``complete`` phase. Emits a ``circuit_breaker`` event
    with the given reason when the transition is applied.
    """
    state = state_module.load_state(state_path)
    if state.phase in ("paused", "complete"):
        return
    state = state_module.transition(state, "paused")
    state.paused_reason = reason
    _save_state_locked(state, state_path, coord)
    events.log_event(
        events.CIRCUIT_BREAKER,
        round=round_num,
        details={"reason": reason},
        log_path=events_path,
    )


# ---------------------------------------------------------------------------
# Shared morning-report helper (signal + clean-shutdown paths, R14 step 3)
# ---------------------------------------------------------------------------

def _generate_morning_report(
    state_path: Path,
    session_dir: Path,
    repo_path: Path,
    events_path: Path,
) -> None:
    """Collect report data + emit followup backlog items + write morning-report.md.

    Shared by the signal-driven cleanup path and the clean-shutdown
    post-loop path. When ``state.worktree_path`` is set the followup
    backlog items land inside the worktree so the post-session commit
    pushes them onto the integration branch (lifecycle 130 Task 7);
    otherwise they fall back to ``repo_path / "cortex" / "backlog"``.

    All exceptions are swallowed — morning-report generation is best-effort
    and must not abort the cleanup sequence.
    """
    try:
        data = report.collect_report_data(
            state_path=state_path,
            events_path=events_path,
        )
        try:
            state = state_module.load_state(state_path)
            worktree_path = state.worktree_path
        except Exception:
            worktree_path = None
        if worktree_path:
            backlog_dir = Path(worktree_path) / "cortex" / "backlog"
        else:
            backlog_dir = repo_path / "cortex" / "backlog"
        data.new_backlog_items = report.create_followup_backlog_items(
            data, backlog_dir=backlog_dir
        )
        report_md = report.generate_report(data)
        report.write_report(
            report_md,
            path=session_dir / "morning-report.md",
        )
    except Exception:
        pass


def _commit_followup_in_worktree(
    worktree_path: Path,
    session_id: str,
    events_path: Path,
) -> None:
    """Commit follow-up backlog items under ``worktree_path/cortex/backlog/``.

    Mirrors the bash runner's post-SIGHUP/post-loop commit (`runner.sh`
    Task 7 block): ``git add cortex/backlog/ && git commit -m "Overnight
    session <id>: record followup"`` inside the worktree so the follow-ups
    land on the integration branch, not the home repo. Silently no-ops when
    the worktree directory does not exist or has nothing staged.

    On non-zero ``git commit`` exit (e.g. rejected by the Phase 0 hook
    guard), emits a stderr line and a structured ``followup_commit_failed``
    event to ``events_path`` so morning review can debug the rejection.
    """
    if not worktree_path.is_dir():
        return
    env = {k: v for k, v in os.environ.items() if k != "GIT_DIR"}
    try:
        subprocess.run(
            ["git", "add", "cortex/backlog/"],
            cwd=str(worktree_path),
            env=env,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        diff = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=str(worktree_path),
            env=env,
            check=False,
        )
        if diff.returncode == 0:
            return
        commit_result = subprocess.run(
            [
                "git",
                "commit",
                "-m",
                f"Overnight session {session_id}: record followup",
            ],
            cwd=str(worktree_path),
            env=env,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        if commit_result.returncode != 0:
            try:
                branch_result = subprocess.run(
                    ["git", "symbolic-ref", "--quiet", "HEAD"],
                    cwd=str(worktree_path),
                    env=env,
                    check=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                )
                branch = (
                    branch_result.stdout.strip()
                    if branch_result.returncode == 0
                    else "unknown"
                )
            except (OSError, subprocess.SubprocessError):
                branch = "unknown"
            print(
                f"runner: followup commit failed for session={session_id} "
                f"branch={branch} rc={commit_result.returncode}",
                file=sys.stderr,
                flush=True,
            )
            try:
                events.log_event(
                    events.FOLLOWUP_COMMIT_FAILED,
                    round=0,
                    details={
                        "session_id": session_id,
                        "worktree_path": str(worktree_path),
                        "branch": branch,
                        "returncode": commit_result.returncode,
                        "hook_stderr": commit_result.stderr,
                    },
                    log_path=events_path,
                )
            except Exception:
                pass
    except (OSError, subprocess.SubprocessError):
        pass


def _resolve_feature_integration_worktree(
    state: "state_module.OvernightState",
    fs: "state_module.OvernightFeatureStatus",
) -> Optional[Path]:
    """Resolve the integration worktree a feature's plan commit lands in.

    The home repo's integration worktree lives in ``state.worktree_path``
    (``plan.py`` skips the home repo when populating
    ``state.integration_worktrees``), while ``state.integration_worktrees``
    holds only the *cross-repo* worktrees. A feature targets the home repo
    when its ``repo_path`` is ``None`` (the project default); otherwise it
    targets the cross-repo worktree keyed by its resolved ``repo_path``.

    Returns ``None`` when no worktree is recorded for the feature's repo so
    the caller can skip it without crashing.
    """
    if fs.repo_path is None:
        return Path(state.worktree_path) if state.worktree_path else None
    repo_key = str(Path(fs.repo_path).expanduser().resolve())
    wt = state.integration_worktrees.get(repo_key)
    if wt is None:
        # Fall back to the raw (un-normalized) key in case the state was
        # written without resolving the path.
        wt = state.integration_worktrees.get(fs.repo_path)
    return Path(wt) if wt else None


def _commit_round_plans_in_worktree(
    state: "state_module.OvernightState",
    home_repo_path: Path,
    session_id: str,
    events_path: Path,
) -> None:
    """Commit this round's generated ``plan.md`` files in their integration worktrees.

    Replaces the orchestrator agent's prose ``/commit`` step (which ran in
    the home-repo CWD on ``main``). For each feature, the orchestrator wrote
    ``plan.md`` into the home working tree; this helper copies that file into
    the feature's integration worktree and runs ``git add``/``git commit``
    there (``cwd`` = the worktree, ``env`` without ``GIT_DIR``) so the plan
    commit lands on ``overnight/{session_id}`` rather than home ``main``.

    The home-tree copy is intentionally left in place (and uncommitted): the
    dispatch path root-resolves its ``plan.md`` read to the home tree, so
    removing it would starve the next pipeline stage.

    Worktree resolution is per-feature (``_resolve_feature_integration_worktree``):
    home-repo features land in ``state.worktree_path``; cross-repo features
    land in their ``state.integration_worktrees`` entry. Features whose
    worktree is absent/torn-down are skipped (the helper never crashes and
    never emits the ticket's ``followup_commit_failed`` rc=128 against a
    removed worktree).
    """
    env = {k: v for k, v in os.environ.items() if k != "GIT_DIR"}
    # Group the round's relative plan paths by their target worktree so each
    # worktree gets a single staged commit.
    by_worktree: dict[Path, list[str]] = {}
    for name, fs in state.features.items():
        rel_plan = f"cortex/lifecycle/{name}/plan.md"
        src = home_repo_path / rel_plan
        if not src.is_file():
            continue
        worktree_path = _resolve_feature_integration_worktree(state, fs)
        # Edge: integration worktree absent/torn-down — fail safe, surface,
        # never crash and never the ticket's followup_commit_failed rc=128.
        if worktree_path is None or not worktree_path.is_dir():
            if worktree_path is not None:
                try:
                    events.log_event(
                        events.INTEGRATION_WORKTREE_MISSING,
                        round=0,
                        details={
                            "session_id": session_id,
                            "feature": name,
                            "worktree_path": str(worktree_path),
                            "context": "plan_commit",
                        },
                        log_path=events_path,
                    )
                except Exception:
                    pass
            continue
        try:
            dst = worktree_path / rel_plan
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        except OSError:
            continue
        by_worktree.setdefault(worktree_path, []).append(rel_plan)

    for worktree_path, rel_plans in by_worktree.items():
        try:
            subprocess.run(
                ["git", "add", *rel_plans],
                cwd=str(worktree_path),
                env=env,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            diff = subprocess.run(
                ["git", "diff", "--cached", "--quiet"],
                cwd=str(worktree_path),
                env=env,
                check=False,
            )
            if diff.returncode == 0:
                continue
            commit_result = subprocess.run(
                [
                    "git",
                    "commit",
                    "-m",
                    f"Overnight session {session_id}: commit generated plans",
                ],
                cwd=str(worktree_path),
                env=env,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            if commit_result.returncode != 0:
                print(
                    f"runner: plan commit failed for session={session_id} "
                    f"worktree={worktree_path} rc={commit_result.returncode}",
                    file=sys.stderr,
                    flush=True,
                )
        except (OSError, subprocess.SubprocessError):
            continue


def _commit_morning_report_in_repo(
    project_root: Path,
    session_id: str,
    events_path: Path,
) -> None:
    """Commit ``cortex/lifecycle/morning-report.md`` to local main from the runner.

    Ports the morning-report runner-side commit step from the legacy
    ``runner.sh`` (Req 9 of the
    install-pre-commit-hook-rejecting-main-commits-during-overnight-sessions
    spec). The function runs in the runner process — not in any spawned
    child — so the subprocess inherits the runner's ``os.environ`` which
    contains no ``CORTEX_RUNNER_CHILD``. Phase 0 therefore does not fire
    and the legitimate runner-direct commit is allowed to land on local
    ``main``.

    Stages only the tracked top-level copy ``cortex/lifecycle/morning-report.md``
    (the load-bearing path per ticket 129's relocation). The per-session
    path ``cortex/lifecycle/sessions/<session_id>/morning-report.md`` is
    intentionally skipped: it is gitignored by the ``lifecycle/sessions/``
    rule in the umbrella ``cortex/.gitignore`` by design as a session-archive
    artifact, so attempting to ``git add`` it would be a no-op without ``-f``
    and the archive is not meant to land in history.

    On non-zero ``git commit`` exit, emits a structured
    ``morning_report_commit_failed`` event to ``events_path``; on success
    emits ``morning_report_commit_result``. All exceptions are swallowed
    to preserve the same best-effort contract as ``_generate_morning_report``.
    """
    env = {k: v for k, v in os.environ.items() if k != "GIT_DIR"}
    try:
        subprocess.run(
            ["git", "add", "cortex/lifecycle/morning-report.md"],
            cwd=str(project_root),
            env=env,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        diff = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=str(project_root),
            env=env,
            check=False,
        )
        if diff.returncode == 0:
            return
        commit_result = subprocess.run(
            [
                "git",
                "commit",
                "-m",
                f"Overnight session {session_id}: morning report",
            ],
            cwd=str(project_root),
            env=env,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        if commit_result.returncode == 0:
            try:
                events.log_event(
                    events.MORNING_REPORT_COMMIT_RESULT,
                    round=0,
                    details={
                        "session_id": session_id,
                        "project_root": str(project_root),
                        "outcome": "committed",
                    },
                    log_path=events_path,
                )
            except Exception:
                pass
        else:
            try:
                events.log_event(
                    events.MORNING_REPORT_COMMIT_FAILED,
                    round=0,
                    details={
                        "session_id": session_id,
                        "project_root": str(project_root),
                        "returncode": commit_result.returncode,
                        "stderr": commit_result.stderr,
                    },
                    log_path=events_path,
                )
            except Exception:
                pass
    except (OSError, subprocess.SubprocessError):
        pass


# ---------------------------------------------------------------------------
# Cleanup (R14)
# ---------------------------------------------------------------------------

def _cleanup(
    coord: RunnerCoordination,
    spawned_procs: list[tuple[subprocess.Popen, str]],
    state_path: Path,
    session_dir: Path,
    repo_path: Path,
    events_path: Path,
    session_id: str,
    round_num: int,
    prior_handlers: dict,
) -> int:
    """Run cleanup on the main thread when ``shutdown_event`` is set.

    Ordered per R14:

    1. Log a ``circuit_breaker`` event with ``reason: signal``.
    2. Update the active-session pointer to ``phase: paused`` (do NOT
       clear — R14 preserves paused-session visibility for the dashboard).
    3. Invoke the 4-call report sequence on partial state.
    4. Terminate any live spawned PGIDs under ``kill_lock``.
    5. Clear the per-session ``runner.pid`` file (R8 clean-shutdown
       contract: signal-handled exit is a clean shutdown).
    6. Restore prior signal handlers.
    7. Re-raise the original signal with the default handler so the
       process dies with the canonical signal-death exit code (130 for
       SIGINT, 143 for SIGTERM, 129 for SIGHUP).

    Never returns — always terminates via ``os.kill``. The ``int`` return
    type is nominal.
    """
    # (1) circuit_breaker event — R14 step 1.
    try:
        events.log_event(
            events.CIRCUIT_BREAKER,
            round=round_num,
            details={"reason": "signal"},
            log_path=events_path,
        )
    except Exception:
        pass

    # Transition state to paused under the same signal-deferral shielding
    # as the mid-round writes so a second signal can't corrupt the file.
    try:
        state = state_module.load_state(state_path)
        if state.phase not in ("paused", "complete"):
            state = state_module.transition(state, "paused")
            state.paused_reason = "signal"
            _save_state_locked(state, state_path, coord)
    except Exception:
        pass

    # (2) Mark active-session pointer as paused — do NOT clear (R14).
    try:
        ipc.update_active_session_phase(session_id, "paused")
    except Exception:
        pass

    # (3) Partial morning-report sequence — shared helper routes followups
    # to $WORKTREE_PATH/backlog when set (lifecycle 130 Task 7).
    _generate_morning_report(
        state_path=state_path,
        session_dir=session_dir,
        repo_path=repo_path,
        events_path=events_path,
    )

    # (3b) Commit follow-up backlog items inside the worktree so they
    # land on the integration branch instead of the home repo.
    try:
        state = state_module.load_state(state_path)
        if state.worktree_path:
            wt_path = Path(state.worktree_path)
            _commit_followup_in_worktree(wt_path, session_id, events_path)
    except Exception:
        pass

    # (4) Tear down spawned subprocess groups.
    for proc, _label in spawned_procs:
        if proc.poll() is None:
            _kill_subprocess_group(proc, coord)

    # (5) Clear per-session runner.pid — R8 clean-shutdown contract.
    # CAS on session_id so a displaced-owner cleanup cannot clobber a
    # successor's just-written claim during a takeover transition.
    try:
        ipc.clear_runner_pid(session_dir, expected_session_id=session_id)
    except Exception:
        pass

    # (6) Restore prior signal handlers so the replay below runs with
    # the system default.
    restore_signal_handlers(prior_handlers)

    # (7) Replay the received signal so exit code matches canonical
    # signal-death semantics (130 / 143 / 129).
    signum = (
        coord.received_signals[-1]
        if coord.received_signals
        else signal.SIGINT
    )
    os.kill(os.getpid(), signum)

    # Defense-in-depth: os.kill with default handler should exit the
    # process; if for some reason it doesn't, fall through with 130.
    return 130


# ---------------------------------------------------------------------------
# Session startup
# ---------------------------------------------------------------------------

def _check_concurrent_start(
    session_dir: Path,
    lock_fd: Optional[int] = None,
) -> tuple[Optional[str], Optional[int]]:
    """Check for a live session via ``runner.pid`` + ``verify_runner_pid``.

    Acquires the per-session takeover lock at the start of the function
    so the read-verify-clear sequence runs serialized against any other
    runner starter. The lock is held across the read of ``runner.pid``,
    the ``verify_runner_pid`` decision, and (when stale) the
    ``clear_runner_pid`` self-heal. The caller propagates the held FD
    into the subsequent :func:`ipc.write_runner_pid` call so the entire
    read-verify-claim critical section runs under one lock.

    When ``lock_fd`` is provided, the caller already holds the takeover
    lock (the resume path acquires it at the top to serialize the
    crash-loop guard + ``handle_interrupted_features`` against a
    concurrent recovery writer). This function then reuses that held FD
    rather than acquiring the lock a second time, and on the
    live-collision path it does NOT close the caller-owned FD — the
    caller is responsible for releasing the FD it acquired.

    Returns a ``(error_message, lock_fd)`` tuple:

    * On a live-session collision: ``(error_message, None)`` when this
      function acquired the lock (it releases the lock before returning so
      the caller does not need to); ``(error_message, lock_fd)`` when the
      caller passed in a held FD (the caller owns release).
    * On the no-PID-file path or successful stale self-heal:
      ``(None, lock_fd)``. The caller MUST release via the nested
      ``try: LOCK_UN ... finally: os.close(fd)`` pattern after
      :func:`ipc.write_runner_pid` returns.
    """
    caller_owns_lock = lock_fd is not None
    if lock_fd is None:
        lock_fd = ipc._acquire_takeover_lock(session_dir)
    try:
        pid_data = ipc.read_runner_pid(session_dir)
        if pid_data is None:
            return None, lock_fd
        if ipc.verify_runner_pid(pid_data):
            # Live runner. Only release the lock here when this function
            # acquired it; when the caller passed in a held FD it owns
            # release and we return the FD so the caller can clean up.
            if caller_owns_lock:
                return "session already running", lock_fd
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            finally:
                os.close(lock_fd)
            return "session already running", None
        # Stale — self-heal under the held lock. Pass the stale claim's
        # session_id for defense-in-depth CAS even though the takeover
        # lock serializes the read-verify-claim critical section.
        stale_session_id = pid_data.get("session_id")
        ipc.clear_runner_pid(session_dir, expected_session_id=stale_session_id)
        ipc.clear_active_session()
        return None, lock_fd
    except BaseException:
        # Only tear down the FD when this function acquired it; a
        # caller-owned FD is released by the caller's own finally.
        if not caller_owns_lock:
            try:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                finally:
                    os.close(lock_fd)
            except OSError:
                pass
        raise


def _crash_loop_resume_declined(
    session_dir: Path,
    state: state_module.OvernightState,
    *,
    force: bool,
) -> Optional[str]:
    """Return a decline message if the crash-loop resume guard trips (spec §R9).

    Refuses to auto-resume a session paused by out-of-process crash
    recovery once it has exhausted the crash-loop bound, because the #308
    trigger class (e.g. a pre-commit gate blocking every commit) is
    deterministic — a blind auto-resume would crash, get recovered, and
    crash again. The decline condition (ALL of):

      * the recovery-complete sidecar (``recovery-complete.json``) is
        present — the race-authoritative marker that recovery actually
        ran on this session (a separate file a concurrent resume's
        ``save_state`` cannot clobber), AND
      * ``paused_reason == "orchestrator_crash"`` — a crash-recovery
        pause specifically (a clean ``budget_exhausted``/``signal`` pause
        is never declined), AND
      * ``crash_recovery_attempts`` exceeds
        :data:`CRASH_RECOVERY_RESUME_BOUND` (default 1), AND
      * ``--force`` was not passed.

    Returns the operator-facing decline message when the guard trips, or
    ``None`` to proceed with the resume. Pure: reads disk + state only,
    mutates nothing. The caller MUST run this UNDER the takeover lock and
    BEFORE :func:`interrupt.handle_interrupted_features`, so the read of
    the sidecar + counter is serialized against a concurrent recovery
    writer and no feature-status reset runs ahead of a declined resume.
    """
    if force:
        return None
    # Lazy import: ``recovery`` imports from this module at module load
    # (``DESCENDANT_GRACEFUL_SHUTDOWN_SECONDS``), so a top-level import
    # here would be circular. The constants are read inside the function.
    from cortex_command.overnight import recovery

    paused_reason = getattr(state, "paused_reason", None)
    if paused_reason != recovery.ORCHESTRATOR_CRASH_PAUSED_REASON:
        return None
    attempts = getattr(state, "crash_recovery_attempts", 0)
    if attempts <= CRASH_RECOVERY_RESUME_BOUND:
        return None
    sidecar = session_dir / recovery.RECOVERY_COMPLETE_SIDECAR
    if not sidecar.exists():
        return None
    return (
        f"refusing to auto-resume session paused by orchestrator-crash "
        f"recovery: crash_recovery_attempts={attempts} exceeds the "
        f"crash-loop bound ({CRASH_RECOVERY_RESUME_BOUND}). The crash "
        f"trigger is likely deterministic (it crashed and re-crashed). "
        f"Diagnose the underlying failure, or pass --force to resume "
        f"anyway."
    )


def _start_session(
    state_path: Path,
    session_dir: Path,
    repo_path: Path,
    events_path: Path,
    coord: RunnerCoordination,
    force: bool = False,
) -> tuple[Optional[state_module.OvernightState], Optional[dict], Optional[str]]:
    """Run R8/R9/R14 session startup: interrupt recovery, PID + pointer writes.

    Returns the loaded state, the pid_data payload used to write
    ``runner.pid`` (reused for pointer updates), and the ``start_time``
    string used for PID-reuse detection. Returns ``(None, None, None)``
    when the locked concurrent-start guard detects a live runner already
    owns the session, OR when the crash-loop resume guard (spec §R9)
    declines an auto-resume of a crash-recovered session past the bound —
    the caller MUST treat either as a refused-start exit path (the
    message is already printed to stderr by this function) and return a
    nonzero exit code.

    **Lock ordering (spec §R9 / Overview "Recovery↔resume ordering").**
    The takeover lock is acquired at the TOP of the resume path — before
    the crash-loop guard reads the ``recovery-complete.json`` sidecar +
    ``crash_recovery_attempts`` and before
    :func:`interrupt.handle_interrupted_features` mutates feature status —
    so both the guard read and the interrupt-recovery write are
    serialized against a concurrent out-of-process recovery writer (the
    takeover lock does NOT serialize ``save_state`` cross-process, so the
    guard would otherwise act on unserialized state). The SAME held FD is
    threaded into :func:`_check_concurrent_start` and
    :func:`ipc.write_runner_pid` (the lock is acquired ONCE, not twice).

    ``force`` (from ``cortex overnight start --force``) bypasses the
    crash-loop resume guard; it does not affect the concurrent-start
    protection or the ``runner.pid`` claim.
    """
    pid = os.getpid()
    try:
        pgid = os.getpgid(pid)
    except ProcessLookupError:
        pgid = pid

    # The takeover-lock acquire and release live inside the
    # ``deferred_signals`` block so SIGTERM that arrives during the
    # ``_acquire_takeover_lock`` polling loop is stashed by the context
    # manager and replayed on exit. PEP 475 means ``time.sleep(0.05)``
    # retries to completion across signals — the 50 ms cadence (not
    # EINTR) is what bounds signal-response latency. The lock is acquired
    # at the TOP of the resume path (spec §R9 reorder) so the crash-loop
    # guard read AND ``handle_interrupted_features``'s feature-status
    # write run under it, serialized against a concurrent recovery
    # writer; the SAME held FD is then threaded into
    # ``_check_concurrent_start`` (read-verify-clear) AND the subsequent
    # ``write_runner_pid`` claim so the entire read-verify-claim critical
    # section runs under one held lock (the re-verify under the held lock
    # inside ``write_runner_pid``'s retry path is the load-bearing CAS
    # that closes the documented unlink-then-recreate TOCTOU). The lock
    # is acquired ONCE; the held FD is reused, never re-acquired.
    with deferred_signals(coord):
        lock_fd = ipc._acquire_takeover_lock(session_dir)
        try:
            # Crash-loop resume guard (spec §R9): read the
            # recovery-complete sidecar + crash_recovery_attempts UNDER
            # the lock and BEFORE handle_interrupted_features mutates
            # feature status, so the decision is serialized against a
            # concurrent recovery writer and no feature-status reset runs
            # ahead of a declined resume.
            guard_state = state_module.load_state(state_path)
            decline = _crash_loop_resume_declined(
                session_dir, guard_state, force=force
            )
            if decline is not None:
                print(decline, file=sys.stderr, flush=True)
                return None, None, None

            # R14 interrupt recovery for features stuck in "running",
            # under the held lock (spec §R9 reorder).
            interrupt.handle_interrupted_features(state_path)

            state = state_module.load_state(state_path)
            session_id = state.session_id
            if not session_id:
                raise RuntimeError(
                    f"state file {state_path} has empty session_id"
                )

            start_time = datetime.now(timezone.utc).isoformat()
            pid_data = {
                "schema_version": 1,
                "magic": "cortex-runner-v1",
                "pid": pid,
                "pgid": pgid,
                "start_time": start_time,
                "session_id": session_id,
                "session_dir": str(session_dir),
                "repo_path": str(repo_path),
            }

            concurrent_err, _lock_fd = _check_concurrent_start(
                session_dir, lock_fd=lock_fd
            )
            if concurrent_err is not None:
                print(concurrent_err, file=sys.stderr, flush=True)
                return None, None, None
            ipc.write_runner_pid(
                session_dir=session_dir,
                pid=pid,
                pgid=pgid,
                start_time=start_time,
                session_id=session_id,
                repo_path=repo_path,
                lock_fd=lock_fd,
            )
            ipc.write_active_session(pid_data, phase="executing")
        finally:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            finally:
                os.close(lock_fd)

    # Async-spawn handshake (Task 6 / spec R18): the parent CLI (or the
    # launchd launcher) wrote ``runner.spawn-pending`` before forking
    # this runner. Delete it AFTER ``runner.pid`` is durable so a
    # ``cortex overnight status`` query never observes both files
    # absent during a live spawn — the only valid intermediate state
    # is sentinel-present-and-pid-absent ("phase: starting").
    try:
        (session_dir / "runner.spawn-pending").unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass

    # R13: clear ``scheduled_start`` now that this runner has fired. A plain
    # field write (NOT a phase transition) persisted via the atomic
    # ``save_state`` (tempfile + ``os.replace``), reading/writing the explicit
    # per-session ``state_path`` rather than the no-arg ``load_state`` —
    # keeping R13 decoupled from R19's top-level symlink. Without this, the
    # read-time scheduled-dormant predicate (R12) could false-positive on a
    # live, completed, or crashed run whose ``scheduled_start`` still points at
    # the (now past) fire time.
    if state.scheduled_start is not None:
        state.scheduled_start = None
        state_module.save_state(state, state_path)

    events.log_event(
        events.SESSION_START,
        round=state.current_round,
        details={"session_id": session_id, "start_time": start_time},
        log_path=events_path,
    )
    return state, pid_data, start_time


# ---------------------------------------------------------------------------
# Map results (in-process; no subprocess — R5)
# ---------------------------------------------------------------------------

def _apply_batch_results(
    batch_plan_path: Path,
    batch_id: int,
    state_path: Path,
    strategy_path: Path,
    coord: RunnerCoordination,
) -> None:
    """Update state + strategy from a round's batch-results JSON.

    Calls the internal map_results helpers directly — no ``python3 -m``
    subprocess dispatch. When the results file is absent, invokes the
    missing-results fallback (marks features as failed).
    """
    results_path = batch_plan_path.parent / f"batch-{batch_id}-results.json"
    if results_path.exists():
        try:
            results = json.loads(results_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            with coord.state_lock, deferred_signals(coord):
                map_results._handle_missing_results(batch_plan_path, state_path)
            return
        with coord.state_lock, deferred_signals(coord):
            map_results._map_results_to_state(results, state_path, batch_id)
            map_results._update_strategy(results, batch_id, strategy_path)
    else:
        with coord.state_lock, deferred_signals(coord):
            map_results._handle_missing_results(batch_plan_path, state_path)


# ---------------------------------------------------------------------------
# Orchestrator + batch_runner spawn helpers
# ---------------------------------------------------------------------------

def _write_sandbox_deny_list_sidecar(
    session_dir: Path,
    spawn_id: str,
    spawn_kind: str,
    deny_paths: list[str],
) -> None:
    """Write a per-spawn schema-v2 sandbox deny-list sidecar (spec R2).

    Sidecar lives at
    ``<session_dir>/sandbox-deny-lists/<spawn-id>.json``. Files are NEVER
    overwritten — each spawn writes a new file keyed by ``<spawn-id>``.
    Writes are atomic via tempfile + ``os.replace`` (POSIX ``rename`` is
    atomic on the same filesystem).

    Caller is responsible for the structural guard asserting
    ``deny_paths`` is a flat ``list[str]`` — see the spawn-site comment
    explaining the fail-fast rationale relative to #163's contract.
    """
    sidecar_dir = session_dir / "sandbox-deny-lists"
    sidecar_dir.mkdir(parents=True, exist_ok=True)
    final_path = sidecar_dir / f"{spawn_id}.json"
    tmp_path = sidecar_dir / f".{spawn_id}.json.tmp"
    envelope = {
        "schema_version": 2,
        "written_at": datetime.now(timezone.utc).isoformat(),
        "spawn_kind": spawn_kind,
        "spawn_id": spawn_id,
        "deny_paths": deny_paths,
    }
    tmp_path.write_text(json.dumps(envelope, indent=2))
    os.replace(tmp_path, final_path)


def _spawn_orchestrator(
    filled_prompt: str,
    coord: RunnerCoordination,
    spawned_procs: list[tuple[subprocess.Popen, str]],
    stdout_path: Path,
    state: state_module.OvernightState,
    session_dir: Path,
    round_num: int,
) -> tuple[subprocess.Popen, WatchdogContext, WatchdogThread]:
    """Spawn the per-round ``claude -p`` orchestrator with a watchdog.

    ``stdout_path`` receives the subprocess stdout (``--output-format=json``
    envelope). The file handle is held by ``Popen.stdout`` so the caller
    can close it after ``_poll_subprocess`` returns; redirecting to a
    file (not an OS pipe) sidesteps the buffer-fill deadlock on long
    sessions whose envelope exceeds ~64 KB.

    Per-spawn sandbox enforcement (spec Req 1, Req 2): construct the
    documented ``sandbox.filesystem.{denyWrite,allowWrite}`` JSON shape via
    the ``sandbox_settings`` layer, write it to a per-spawn tempfile under
    ``<session_dir>/sandbox-settings/``, register an atexit cleanup, and
    pass ``--settings <tempfile-path>`` in the orchestrator argv. The
    ``CORTEX_SANDBOX_SOFT_FAIL`` env var (Req 4) is read at this call;
    when truthy, ``failIfUnavailable`` downgrades to ``false`` and a
    ``sandbox_soft_fail_active`` event is recorded on the session
    events.log.
    """
    sandbox_settings.emit_linux_warning_if_needed()

    home_repo = (
        Path(state.project_root) if state.project_root else Path.cwd()
    )
    deny_paths = sandbox_settings.build_orchestrator_deny_paths(
        home_repo=home_repo,
        integration_worktrees=state.integration_worktrees,
    )
    # Spec R2: write per-spawn sidecar JSON immediately after constructing
    # the deny-list so the morning-report classifier (T6) has authoritative
    # deny-list context for membership tests. Pre-write structural guard
    # asserts the deny-list value matches the contract — fails fast at
    # write time rather than producing a sidecar whose ``deny_paths`` value
    # silently breaks the classifier's membership tests downstream.
    assert isinstance(deny_paths, list) and all(
        isinstance(p, str) for p in deny_paths
    )
    _write_sandbox_deny_list_sidecar(
        session_dir=session_dir,
        spawn_id=f"orchestrator-{round_num}",
        spawn_kind="orchestrator",
        deny_paths=deny_paths,
    )
    soft_fail = sandbox_settings.read_soft_fail_env()
    # Exclude git from the sandbox so orchestrator-level commits (plan, defer
    # events, morning-report follow-ups) sign cleanly via the host gpg-agent.
    # Matches the user-facing `~/.claude/settings.json` excludedCommands entry
    # so signing semantics are consistent between the user's interactive
    # session and the spawned orchestrator.
    settings = sandbox_settings.build_sandbox_settings_dict(
        deny_paths=deny_paths,
        allow_paths=[],
        soft_fail=soft_fail,
        excluded_commands=["git:*"],
    )
    tempfile_path = sandbox_settings.write_settings_tempfile(
        session_dir, settings
    )
    sandbox_settings.register_atexit_cleanup(tempfile_path)
    if soft_fail:
        sandbox_settings.record_soft_fail_event(session_dir)

    claude_path = "claude"
    stdout_handle = open(stdout_path, "wb")
    proc = subprocess.Popen(
        [
            claude_path,
            "-p",
            filled_prompt,
            "--settings",
            str(tempfile_path),
            "--dangerously-skip-permissions",
            "--max-turns",
            str(ORCHESTRATOR_MAX_TURNS),
            "--output-format=json",
        ],
        stdin=subprocess.DEVNULL,
        stdout=stdout_handle,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        # R28: mark this child as runner-spawned so the install guard
        # carve-out (b) fires on any cortex-package import inside it.
        env={**os.environ, "CORTEX_RUNNER_CHILD": "1"},
    )
    spawned_procs.append((proc, "orchestrator"))
    wctx = WatchdogContext(stall_flag=threading.Event())
    watchdog = WatchdogThread(
        proc=proc,
        timeout_seconds=STALL_TIMEOUT_SECONDS,
        coord=coord,
        wctx=wctx,
        label="orchestrator",
        # Phase 1: the orchestrator/planning site is left with NO activity
        # probe (Req 2 default None ⇒ the inactivity tier never resets ⇒
        # blind 1800s timer, unchanged-from-today). A child-driven signal
        # is wired in Phase 2 after the Req 12 de-risk gate. The absolute
        # ceiling still applies as the orchestrator's only backstop here.
        activity_probe=None,
    )
    watchdog.start()
    return proc, wctx, watchdog


def _emit_orchestrator_round_telemetry(
    envelope_text: str | None,
    exit_code: int | None,
    round_num: int,
    log_path: Path,
) -> None:
    """Parse the orchestrator stdout envelope and emit dispatch telemetry.

    Fire-and-forget per ``docs/overnight-operations.md``: any exception
    during parse or ``pipeline_log_event`` is swallowed with a
    ``[telemetry]``-prefixed stderr breadcrumb; never re-raises.

    Branch decision: emit ``dispatch_complete`` iff ``exit_code == 0``
    AND the envelope is a dict AND not error-shaped (``is_error`` falsy
    AND ``subtype`` does not start with ``"error_"``). Otherwise emit
    ``dispatch_error`` covering non-zero exit, error envelope, parse
    failure, and shape drift.
    """
    feature = f"<orchestrator-round-{round_num}>"
    try:
        from cortex_command.pipeline.state import (
            log_event as pipeline_log_event,
        )

        envelope: Any = None
        parse_reason: str | None = None
        top_level_type: str | None = None
        if envelope_text is None:
            parse_reason = "parse_failure"
        else:
            try:
                envelope = json.loads(envelope_text)
            except Exception:
                parse_reason = "parse_failure"
                envelope = None

        if envelope is not None and not isinstance(envelope, dict):
            top_level_type = type(envelope).__name__
            print(
                f"[telemetry] envelope-shape-drift "
                f"top_level_type={top_level_type}",
                file=sys.stderr,
                flush=True,
            )

        if isinstance(envelope, dict):
            usage = envelope.get("usage", {}) or {}
            cost_usd = envelope.get("total_cost_usd")
            duration_ms = envelope.get("duration_ms")
            num_turns = envelope.get("num_turns")
            model = envelope.get("model") or envelope.get("model_id")
            input_tokens = usage.get("input_tokens")
            output_tokens = usage.get("output_tokens")
            cache_creation_input_tokens = usage.get(
                "cache_creation_input_tokens"
            )
            cache_read_input_tokens = usage.get("cache_read_input_tokens")
            is_error = bool(envelope.get("is_error", False))
            subtype = str(envelope.get("subtype", ""))
            stop_reason = envelope.get("stop_reason")
            effort = envelope.get("effort")
        else:
            cost_usd = None
            duration_ms = None
            num_turns = None
            model = None
            input_tokens = None
            output_tokens = None
            cache_creation_input_tokens = None
            cache_read_input_tokens = None
            is_error = False
            subtype = ""
            stop_reason = None
            effort = None

        success_shaped = (
            exit_code == 0
            and isinstance(envelope, dict)
            and not is_error
            and not subtype.startswith("error_")
        )

        if success_shaped:
            # Truncation allow-list is intentionally a LOCAL set literal (per
            # spec Edge Cases) so future stop_reason values pass through to
            # dispatch_complete unchanged but do not generate spurious
            # truncation events.
            _truncation_reasons = {
                "max_tokens",
                "model_context_window_exceeded",
            }
            if stop_reason in _truncation_reasons:
                pipeline_log_event(
                    log_path,
                    {
                        "event": "dispatch_truncation",
                        "feature": feature,
                        "stop_reason": stop_reason,
                        "model": model,
                        "effort": effort,
                    },
                )
            event_dict: dict[str, Any] = {
                "event": "dispatch_complete",
                "feature": feature,
                "cost_usd": cost_usd,
                "duration_ms": duration_ms,
                "num_turns": num_turns,
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_creation_input_tokens": cache_creation_input_tokens,
                "cache_read_input_tokens": cache_read_input_tokens,
                "stop_reason": stop_reason,
            }
        else:
            if parse_reason == "parse_failure":
                reason = "parse_failure"
            elif top_level_type is not None:
                reason = "envelope_shape_drift"
            elif isinstance(envelope, dict) and (
                is_error or subtype.startswith("error_")
            ):
                reason = "is_error"
            else:
                reason = "non_zero_exit"
            details: dict[str, Any] = {"reason": reason}
            if top_level_type is not None:
                details["top_level_type"] = top_level_type
            event_dict = {
                "event": "dispatch_error",
                "feature": feature,
                "cost_usd": cost_usd,
                "duration_ms": duration_ms,
                "num_turns": num_turns,
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_creation_input_tokens": cache_creation_input_tokens,
                "cache_read_input_tokens": cache_read_input_tokens,
                "details": details,
            }

        pipeline_log_event(log_path, event_dict)
    except Exception as exc:
        print(
            f"[telemetry] orchestrator-round telemetry emission failed: "
            f"{exc!r}",
            file=sys.stderr,
            flush=True,
        )


def _stat_activity(path: Path) -> tuple[int, int] | None:
    """Stat-only activity probe over a child-written file.

    Returns ``(size, mtime_ns)`` for the watchdog's inactivity tier, or
    ``None`` when the file is absent ("no activity yet"). Mirrors the
    ``(exists, st_mtime_ns, st_size)`` safe-stat shape from
    ``cortex_command.common._stat_key``; only ``FileNotFoundError`` is
    caught here (a transient ``OSError`` is broadened to no-reset inside
    ``WatchdogThread.run``'s probe call).
    """
    try:
        s = path.stat()
    except FileNotFoundError:
        return None
    return (s.st_size, s.st_mtime_ns)


def _spawn_batch_runner(
    batch_plan_path: Path,
    batch_id: int,
    tier: str,
    integration_branch: str,
    state_path: Path,
    events_path: Path,
    test_command: Optional[str],
    coord: RunnerCoordination,
    spawned_procs: list[tuple[subprocess.Popen, str]],
    pipeline_events_path: Path,
) -> tuple[subprocess.Popen, WatchdogContext, WatchdogThread]:
    """Spawn ``cortex-batch-runner`` console-script shim with a watchdog.

    Per R5: the console-script shim is the only allowed external
    invocation for batch_runner — the module-dispatch form is banned,
    as is ``[sys.executable, "-m", "..."]`` (same intent via runtime
    argv).

    The watchdog's inactivity tier is wired to ``pipeline_events_path`` —
    the session ``pipeline-events.log`` the batch child writes (the child
    receives ``--plan <session_dir>/batch-plan-round-N.md`` ⇒ its
    ``result_dir`` is that ``session_dir`` ⇒ its
    ``pipeline_events_path = result_dir / "pipeline-events.log"``, the
    same file passed here). Growth of that worker-written log resets the
    inactivity timer so a productively-working batch survives past the
    blind 30-minute timer; genuine silence still trips (Req 9).
    """
    cmd = [
        "cortex-batch-runner",
        "--plan",
        str(batch_plan_path),
        "--batch-id",
        str(batch_id),
        "--tier",
        tier,
        "--base-branch",
        integration_branch,
        "--state-path",
        str(state_path),
        "--events-path",
        str(events_path),
        "--test-command",
        test_command if test_command else "none",
    ]
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
        # R28: mark this child as runner-spawned so the install guard
        # carve-out (b) fires on any cortex-package import inside it.
        env={**os.environ, "CORTEX_RUNNER_CHILD": "1"},
    )
    spawned_procs.append((proc, "batch_runner"))
    wctx = WatchdogContext(stall_flag=threading.Event())
    watchdog = WatchdogThread(
        proc=proc,
        timeout_seconds=STALL_TIMEOUT_SECONDS,
        coord=coord,
        wctx=wctx,
        label="batch_runner",
        activity_probe=lambda: _stat_activity(pipeline_events_path),
    )
    watchdog.start()
    return proc, wctx, watchdog


# ---------------------------------------------------------------------------
# Dry-run gate (R15)
# ---------------------------------------------------------------------------

def _reject_dry_run_with_pending(
    state: state_module.OvernightState,
) -> bool:
    """Return True when dry-run must be rejected (pending features remain)."""
    return any(fs.status == "pending" for fs in state.features.values())


# ---------------------------------------------------------------------------
# Post-loop (R15, R16): port of runner.sh:851-1694
# ---------------------------------------------------------------------------

def _count_merged_home_repo(state: state_module.OvernightState) -> int:
    """Count merged features whose ``repo_path`` is None (home-repo only).

    Mirrors ``runner.sh`` ``MC_MERGED_COUNT`` computation at line 1151-1159.
    Cross-repo features carry an explicit ``repo_path`` and are counted
    separately in the cross-repo PR-creation loop (not ported here —
    cross-repo path writes to state keys the tests don't exercise).
    """
    return sum(
        1
        for fs in state.features.values()
        if fs.status == "merged" and fs.repo_path is None
    )


def _count_built_merge_blocked_home_repo(state: state_module.OvernightState) -> int:
    """Count home-repo features that are built-but-merge-blocked (recoverable).

    Mirrors ``_count_merged_home_repo`` but keys off ``recoverable_branch``:
    a home-repo feature whose work is built and recoverable on its branch is
    real progress, so a session containing one must not be labeled
    ``[ZERO PROGRESS]`` even though it merged nothing.
    """
    return sum(
        1
        for fs in state.features.values()
        if fs.recoverable_branch is not None and fs.repo_path is None
    )


def _integration_commit_count(
    integration_branch: str, repo_path: Path
) -> int:
    """Run ``git rev-list --count main..<branch>``; return 0 on failure.

    Missing refs / non-existent branch produce a non-zero exit from git;
    preserve ``runner.sh:1171`` semantics of defaulting to 0 so the
    zero-commit pre-check fires cleanly.
    """
    try:
        result = subprocess.run(
            ["git", "rev-list", "--count", f"main..{integration_branch}"],
            cwd=str(repo_path),
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return 0
        return int(result.stdout.strip() or "0")
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0


def _write_state_flipped_once(state_path: Path) -> None:
    """Atomically set ``integration_pr_flipped_once=True`` on disk.

    Mirrors the bash runner's inline `python3 -c` state-write at
    `runner.sh:1282-1300`. Uses the same `.overnight-state-` prefix so the
    atomic-rename pattern is observationally identical.
    """
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["integration_pr_flipped_once"] = True
        d = str(state_path.parent) or "."
        fd, tmp = tempfile.mkstemp(
            prefix=".overnight-state-", suffix=".json", dir=d
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, str(state_path))
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except Exception:
        pass


def _post_loop(
    state: state_module.OvernightState,
    state_path: Path,
    session_dir: Path,
    repo_path: Path,
    events_path: Path,
    round_num: int,
    session_id: str,
    dry_run: bool,
    coord: RunnerCoordination,
) -> None:
    """Run the post-round-loop sequence (PR-gating + morning-report + commit).

    Port of ``cortex_command/overnight/runner.sh:851-1694`` (R15, R16 and
    Edge Cases line 245). Preserves every ``dry_run_echo`` label string
    verbatim, the ``[ZERO PROGRESS]`` title prefix for zero-merge sessions,
    and the ``integration_pr_flipped_once`` marker semantics.

    Only called on clean loop exit (not from the signal-handled
    ``_cleanup`` path — signal exit keeps the session ``paused``, not
    ``complete``). Clears ``runner.pid`` and the active-session pointer
    on completion per R8/R9.
    """
    # -- Session-complete preamble (runner.sh:854-869) -------------------
    # Reload state so any mid-run persistence is reflected in the stats.
    state = state_module.load_state(state_path)
    total_merged = sum(
        1 for fs in state.features.values() if fs.status == "merged"
    )
    total_features = len(state.features)

    print("", flush=True)
    print("=== Overnight Session Complete ===", flush=True)
    print(f"  Features merged: {total_merged}/{total_features}", flush=True)
    # bash prints `$(( ROUND - 1 ))` where ROUND was the next-round index
    # at loop exit; round_num is the same next-round index in Python.
    rounds_executed = max(round_num - 1, 0)
    print(f"  Rounds executed: {rounds_executed}", flush=True)
    print(
        f"  Finished:        "
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        flush=True,
    )

    try:
        events.log_event(
            events.SESSION_COMPLETE,
            round=rounds_executed,
            details={"features_merged": f"{total_merged}/{total_features}"},
            log_path=events_path,
        )
    except Exception:
        pass

    # Transition state to complete when no pending/running remain
    # (runner.sh:872-884).
    try:
        pending = sum(
            1
            for fs in state.features.values()
            if fs.status in ("pending", "running")
        )
        if pending == 0 and state.phase == "executing":
            state = state_module.transition(state, "complete")
            _save_state_locked(state, state_path, coord)
            print("Session marked complete", flush=True)
        else:
            print(
                f"{pending} features still pending — session remains "
                f"in executing phase",
                flush=True,
            )
    except Exception:
        pass

    # Sync active-session pointer with final phase (runner.sh:886-907).
    try:
        state = state_module.load_state(state_path)
        if state.phase == "complete":
            ipc.clear_active_session()
        else:
            ipc.update_active_session_phase(session_id, state.phase)
    except Exception:
        pass

    # -- Integration PR creation (runner.sh:1134-1376) --------------------
    integration_branch = state.integration_branch or ""
    tmpdir = Path(os.environ.get("TMPDIR", "/tmp"))
    pr_body_file = tmpdir / "overnight-pr-body.txt"
    warning_file = tmpdir / "overnight-integration-warning.txt"

    mc_pr_url = ""

    if integration_branch:
        # Push integration branch to remote (runner.sh:1143-1148).
        # No dry_run_echo — bash runner pushes unconditionally. Failures
        # are logged + notified; do not abort the post-loop.
        try:
            push_result = subprocess.run(
                ["git", "push", "-u", "origin", integration_branch],
                cwd=str(repo_path),
                check=False,
                capture_output=True,
                text=True,
            )
            if push_result.returncode == 0:
                # Pass-through stderr/stdout so tests can match the
                # "Pushed <branch> to origin" reference line.
                if push_result.stderr:
                    print(push_result.stderr, end="", flush=True)
                print(f"Pushed {integration_branch} to origin", flush=True)
            else:
                try:
                    events.log_event(
                        events.PUSH_FAILED,
                        round=rounds_executed,
                        details={
                            "session_id": session_id,
                            "branch": integration_branch,
                        },
                        log_path=events_path,
                    )
                except Exception:
                    pass
                if not dry_run:
                    _notify(
                        f"Overnight push failed — {integration_branch} "
                        f"was not pushed to origin. "
                        f"Session: {session_id}"
                    )
        except (OSError, subprocess.SubprocessError):
            pass

        mc_merged_count = _count_merged_home_repo(state)
        mc_recoverable_count = _count_built_merge_blocked_home_repo(state)
        integration_degraded = state.integration_degraded
        commit_count = _integration_commit_count(
            integration_branch, repo_path
        )

        if commit_count == 0:
            # Zero-commit pre-check (runner.sh:1171-1174, spec Req 4):
            # notify and skip PR creation entirely.
            notify_sh = Path.home() / ".claude" / "notify.sh"
            dry_run_echo(
                "notify.sh",
                str(notify_sh),
                (
                    f"Zero-progress session with no branch commits — "
                    f"no PR created. Session: {session_id}"
                ),
            )
            if not dry_run:
                _notify(
                    f"Zero-progress session with no branch commits — "
                    f"no PR created. Session: {session_id}"
                )
            mc_pr_url = ""
        else:
            # Determine DRAFT_FLAG, PR_TITLE, PR body
            # (runner.sh:1177-1194; Edge Cases line 245).
            draft_flag = ""
            if mc_merged_count == 0 and mc_recoverable_count == 0:
                # [ZERO PROGRESS] draft PR — self-enforcing merge block.
                # Built-but-merge-blocked recoverable home work is real
                # progress, so it lifts the inner label even with 0 merges.
                draft_flag = "--draft"
                pr_title = (
                    f"[ZERO PROGRESS] Overnight session: "
                    f"{integration_branch}"
                )
                body_summary = (
                    f"**ZERO PROGRESS** — Overnight session "
                    f"{session_id} merged 0 features. See "
                    f"`cortex/lifecycle/sessions/{session_id}/morning-report.md` "
                    f"for failure analysis."
                )
            else:
                pr_title = f"Overnight session: {integration_branch}"
                body_summary = (
                    f"Overnight session {session_id}: "
                    f"{mc_merged_count} features merged. See "
                    f"morning-report.md for details."
                )

            # Compose PR body: warning (if degraded + file exists) then
            # the summary (runner.sh:1180-1194).
            try:
                if integration_degraded and warning_file.exists():
                    warning_text = warning_file.read_text(encoding="utf-8")
                    pr_body_file.write_text(
                        warning_text + body_summary + "\n",
                        encoding="utf-8",
                    )
                else:
                    pr_body_file.write_text(
                        body_summary + "\n", encoding="utf-8"
                    )
            except OSError:
                pass

            # Emit `gh pr create` via dry_run_echo (label verbatim from
            # runner.sh:1197, 1205).
            dry_run_echo(
                "gh pr create",
                "gh",
                "pr",
                "create",
                draft_flag,
                "--title",
                pr_title,
                "--base",
                "main",
                "--head",
                integration_branch,
                "--body-file",
                str(pr_body_file),
            )

            if dry_run:
                mc_pr_url = ""
                mc_pr_exit = 0
            else:
                # Real invocation of gh pr create.
                gh_args = ["gh", "pr", "create"]
                if draft_flag:
                    gh_args.append(draft_flag)
                gh_args.extend(
                    [
                        "--title",
                        pr_title,
                        "--base",
                        "main",
                        "--head",
                        integration_branch,
                        "--body-file",
                        str(pr_body_file),
                    ]
                )
                try:
                    proc = subprocess.run(
                        gh_args,
                        cwd=str(repo_path),
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    mc_pr_exit = proc.returncode
                    mc_pr_url = proc.stdout.strip()
                except (OSError, subprocess.SubprocessError):
                    mc_pr_exit = 1
                    mc_pr_url = ""

            # Recovery path: PR create failed or output wasn't a URL.
            # Applies to both dry_run and live paths — dry_run always hits
            # this branch since mc_pr_url is empty, which exercises the
            # gh pr view recovery semantics per test fixtures.
            if mc_pr_exit != 0 or not mc_pr_url.startswith("https://"):
                mc_pr_view_json = ""
                try:
                    view_proc = subprocess.run(
                        [
                            "gh",
                            "pr",
                            "view",
                            "--head",
                            integration_branch,
                            "--json",
                            "url,isDraft,state",
                        ],
                        cwd=str(repo_path),
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    if view_proc.returncode == 0:
                        mc_pr_view_json = view_proc.stdout.strip()
                except (OSError, subprocess.SubprocessError):
                    mc_pr_view_json = ""

                if mc_pr_view_json:
                    try:
                        view = json.loads(mc_pr_view_json)
                    except json.JSONDecodeError:
                        view = {}
                else:
                    view = {}

                mc_pr_url = str(view.get("url") or "")
                mc_pr_state = str(view.get("state") or "")
                is_draft_raw = view.get("isDraft")
                if isinstance(is_draft_raw, bool):
                    mc_pr_is_draft = "true" if is_draft_raw else "false"
                else:
                    mc_pr_is_draft = ""

                if not mc_pr_url.startswith("https://"):
                    print(
                        "Warning: PR creation failed (branch may "
                        "already have a PR)",
                        flush=True,
                    )
                    mc_pr_url = ""
                else:
                    print(
                        f"PR already exists for {integration_branch}: "
                        f"{mc_pr_url}",
                        flush=True,
                    )

                    # Decision matrix (runner.sh:1227-1359, spec Req 5).
                    mc_flipped_once = (
                        state.integration_pr_flipped_once
                    )
                    mc_intended_draft = (
                        "true"
                        if mc_merged_count == 0 and mc_recoverable_count == 0
                        else "false"
                    )

                    if mc_flipped_once:
                        print(
                            "PR previously handled by runner — "
                            "deferring to human state",
                            flush=True,
                        )
                    elif mc_pr_state in ("MERGED", "CLOSED"):
                        print(
                            f"PR already {mc_pr_state} — runner "
                            f"yielding to human action",
                            flush=True,
                        )
                    elif (
                        mc_pr_state == "OPEN"
                        and mc_pr_is_draft == mc_intended_draft
                    ):
                        # No action — state already matches intended.
                        pass
                    elif mc_pr_state == "OPEN":
                        # isDraft mismatch — flip via gh pr ready.
                        # Use --undo when converting ready -> draft
                        # (intended == draft). Otherwise promote to ready.
                        if mc_intended_draft == "true":
                            dry_run_echo(
                                "gh pr ready --undo",
                                "gh",
                                "pr",
                                "ready",
                                "--undo",
                                mc_pr_url,
                            )
                            flip_args = [
                                "gh",
                                "pr",
                                "ready",
                                "--undo",
                                mc_pr_url,
                            ]
                        else:
                            dry_run_echo(
                                "gh pr ready",
                                "gh",
                                "pr",
                                "ready",
                                mc_pr_url,
                            )
                            flip_args = [
                                "gh",
                                "pr",
                                "ready",
                                mc_pr_url,
                            ]

                        mc_pr_ready_stderr = ""
                        if dry_run:
                            # Test-only failure simulation hook (runner.sh
                            # :1265-1276). Preserved verbatim per R15.
                            simulate = os.environ.get(
                                "DRY_RUN_GH_READY_SIMULATE", ""
                            )
                            if simulate == "transient":
                                mc_pr_ready_stderr = (
                                    "HTTP 429: rate limit exceeded"
                                )
                                mc_pr_ready_exit = 1
                            elif simulate == "persistent":
                                mc_pr_ready_stderr = (
                                    "HTTP 401: unauthorized"
                                )
                                mc_pr_ready_exit = 1
                            else:
                                mc_pr_ready_exit = 0
                        else:
                            try:
                                ready_proc = subprocess.run(
                                    flip_args,
                                    cwd=str(repo_path),
                                    check=False,
                                    capture_output=True,
                                    text=True,
                                )
                                mc_pr_ready_exit = ready_proc.returncode
                                mc_pr_ready_stderr = ready_proc.stderr
                            except (OSError, subprocess.SubprocessError):
                                mc_pr_ready_exit = 1
                                mc_pr_ready_stderr = ""

                        if mc_pr_ready_exit == 0:
                            # Success — set once-per-PR marker
                            # (runner.sh:1279-1301).
                            if dry_run:
                                print(
                                    "DRY-RUN state-write "
                                    "integration_pr_flipped_once: true",
                                    flush=True,
                                )
                            else:
                                _write_state_flipped_once(state_path)
                        else:
                            # Classify failure: transient (HTTP 429 / rate
                            # limit) vs persistent (runner.sh:1303-1359).
                            stderr_lower = (
                                mc_pr_ready_stderr.lower()
                                if mc_pr_ready_stderr
                                else ""
                            )
                            if (
                                "http 429" in stderr_lower
                                or "rate limit" in stderr_lower
                            ):
                                mc_ready_reason = "transient"
                            else:
                                mc_ready_reason = "persistent"
                            print(
                                f"Warning: gh pr ready failed "
                                f"(reason={mc_ready_reason}): "
                                f"{mc_pr_ready_stderr}",
                                flush=True,
                            )
                            if dry_run:
                                print(
                                    f"DRY-RUN event pr_ready_failed "
                                    f"reason={mc_ready_reason}",
                                    flush=True,
                                )
                            else:
                                try:
                                    from cortex_command.pipeline.state import (
                                        log_event as pipeline_log_event,
                                    )
                                    pipeline_log_event(
                                        repo_path / "cortex" / "lifecycle" / "pipeline-events.log",
                                        {
                                            "event": "pr_ready_failed",
                                            "session_id": session_id,
                                            "reason": mc_ready_reason,
                                            "pr_url": mc_pr_url,
                                            "intended_is_draft": (
                                                mc_intended_draft == "true"
                                            ),
                                        },
                                    )
                                except Exception:
                                    pass
                            if mc_ready_reason == "persistent":
                                if dry_run:
                                    print(
                                        "DRY-RUN state-write "
                                        "integration_pr_flipped_once: true",
                                        flush=True,
                                    )
                                else:
                                    _write_state_flipped_once(state_path)
            else:
                # PR create succeeded — mc_pr_url is a URL.
                print(
                    f"PR created from {integration_branch} to main: "
                    f"{mc_pr_url}",
                    flush=True,
                )

    # -- Morning report generation (runner.sh:1378-1489) -----------------
    # Dry-run skips silently per spec Req 7 (no stdout echo). Real path
    # delegates to the shared helper so the write path matches signal
    # shutdown's partial-report contract.
    if not dry_run:
        _generate_morning_report(
            state_path=state_path,
            session_dir=session_dir,
            repo_path=repo_path,
            events_path=events_path,
        )
        _commit_morning_report_in_repo(repo_path, session_id, events_path)

        # Commit followup backlog items to worktree (runner.sh:1491-1504).
        try:
            state = state_module.load_state(state_path)
            if state.worktree_path:
                wt_path = Path(state.worktree_path)
                _commit_followup_in_worktree(wt_path, session_id, events_path)
        except Exception:
            pass

    # -- Notify (runner.sh:1601-1618) ------------------------------------
    if not dry_run:
        try:
            state = state_module.load_state(state_path)
            total_merged = sum(
                1
                for fs in state.features.values()
                if fs.status == "merged"
            )
            total_features = len(state.features)
            paused_reason = state.paused_reason or ""
            if paused_reason == "budget_exhausted":
                _notify(
                    f"Overnight session paused — API budget exhausted. "
                    f"Resume with /overnight resume when Anthropic limit "
                    f"resets. Session: {session_id}"
                )
            elif paused_reason == "api_rate_limit":
                _notify(
                    f"Overnight session paused — Anthropic API rate limit. "
                    f"Resume with /overnight resume when retry budget "
                    f"recovers (typically minutes). Session: {session_id}"
                )
            else:
                _notify(
                    f"Overnight complete — "
                    f"{total_merged}/{total_features} features merged. "
                    f"Morning report ready. Session: {session_id}"
                )
        except Exception:
            pass

    # -- Clear per-session runner.pid + active-session pointer -----------
    # R8: runner.pid cleared atomically on clean shutdown.
    # R9: active-session pointer cleared only on `complete`.
    try:
        state = state_module.load_state(state_path)
        if state.phase == "complete":
            ipc.update_active_session_phase(session_id, "complete")
            ipc.clear_active_session()
    except Exception:
        pass
    try:
        ipc.clear_runner_pid(session_dir, expected_session_id=session_id)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------

def run(
    state_path: Path,
    session_dir: Path,
    repo_path: Path,
    plan_path: Path,
    events_path: Path,
    time_limit_seconds: Optional[int],
    max_rounds: Optional[int],
    tier: str,
    dry_run: bool = False,
    force: bool = False,
) -> int:
    """Run the overnight round-dispatch loop.

    Single public entry point; returns a process exit code. Paths arrive
    from the CLI — ``runner.py`` itself never derives user-repo paths
    from ``__file__`` or env vars (R20).

    Args:
        state_path: Path to ``overnight-state.json`` for this session.
        session_dir: Directory under ``cortex/lifecycle/sessions/{id}/``.
        repo_path: Absolute path to the home repository root.
        plan_path: Path to ``overnight-plan.md``.
        events_path: Path to ``overnight-events.log``.
        time_limit_seconds: Wall-clock budget; ``None`` disables.
        max_rounds: Round-count budget; ``None`` uses state's
            ``current_round + 10``.
        tier: Throttle tier name passed to both the prompt template and
            ``cortex-batch-runner``.
        dry_run: When True, reject if any feature is ``pending``; skip
            spawns and emit ``DRY-RUN`` echoes instead.
        force: When True, bypass the crash-loop resume guard (spec §R9)
            so a session paused by orchestrator-crash recovery past the
            bound is resumed anyway. Does not affect the concurrent-start
            protection or the ``runner.pid`` claim.

    Returns:
        Process exit code. ``0`` on clean loop exit. Nonzero on
        concurrent-start collision, crash-loop resume refusal, dry-run
        rejection, or propagated signal exit.
    """
    # Earliest action (R4): bind a no-idle-sleep assertion to this runner's
    # lifetime as a child, BEFORE state load and takeover-lock acquisition.
    # Spawning first minimizes the unasserted window to the sub-second
    # Popen→entry gap rather than spanning the slow post-wake / cold-cache
    # state-load + lock window below. The runner stays the session leader
    # (caffeinate is a bound child, not the Popen target); best-effort spawn
    # so a missing ``caffeinate`` binary cannot crash the runner.
    _spawn_caffeinate_bound_to_runner()

    # Load once for concurrent-start guard and startup logging.
    state = state_module.load_state(state_path)
    session_id = state.session_id

    # Per-spawn sandbox tempfile cleanup (spec Req 11): startup-scan removes
    # stale ``cortex-sandbox-*.json`` tempfiles older than runner-start
    # timestamp. Handles SIGKILL / OOM / kernel-panic crash paths that bypass
    # ``atexit``.
    sandbox_settings.cleanup_stale_tempfiles(
        session_dir, runner_start_ts=time.time()
    )

    # Dry-run concurrent-start guard. The non-dry-run path takes the
    # locked, authoritative check inside ``_start_session`` (which
    # propagates the held FD into ``write_runner_pid``). Dry-run skips
    # ``_start_session`` entirely and never claims ``runner.pid``, so it
    # only needs an advisory read-only check to fail fast when a live
    # runner already owns the session.
    if dry_run:
        existing_pid_data = ipc.read_runner_pid(session_dir)
        if (
            existing_pid_data is not None
            and ipc.verify_runner_pid(existing_pid_data)
        ):
            print("session already running", file=sys.stderr, flush=True)
            return 1

    # Dry-run rejection with pending features (R15).
    if dry_run and _reject_dry_run_with_pending(state):
        print(
            "--dry-run requires a state file with all features in "
            "terminal states",
            file=sys.stderr,
            flush=True,
        )
        return 1

    # Load the prompt template once (R19, R20). The template is a
    # package-internal resource; user-repo paths are the CLI's
    # responsibility.
    _ = (
        files("cortex_command.overnight.prompts")
        .joinpath("orchestrator-round.md")
        .read_text(encoding="utf-8")
    )

    # Coordination primitives + signal handlers (R7, R14).
    coord = RunnerCoordination(
        shutdown_event=threading.Event(),
        state_lock=threading.Lock(),
        kill_lock=threading.Lock(),
        received_signals=[],
    )
    prior = install_signal_handlers(coord)

    # R12 / Task 3: install a SIGTERM handler that walks the descendant
    # tree and reaps each process before chaining to the shutdown-event
    # setter installed above. This reaches grandchildren spawned with
    # ``start_new_session=True`` (whose PGID diverges from the runner's)
    # that ``os.killpg`` cannot signal. The 6-second graceful budget is
    # strictly less than ``overnight_cancel``'s 12-second outer SIGKILL
    # budget so the in-handler survivor-SIGKILL phase always completes
    # before any outer SIGKILL.
    _shutdown_sigterm_handler = signal.getsignal(signal.SIGTERM)
    _install_sigterm_tree_walker(_shutdown_sigterm_handler)

    # Export LIFECYCLE_SESSION_ID so spawned children (orchestrator
    # agent and cortex-batch-runner) pick up the per-session events-log
    # suffix expected by peer modules.
    os.environ["LIFECYCLE_SESSION_ID"] = session_id
    # Export CORTEX_REPO_ROOT (#198) so bin/cortex-log-invocation's shim
    # fast path skips the ~6ms git rev-parse fork. Set from runner's own
    # resolved repo_path, not propagated from the operator's parent shell,
    # so a stale shell value cannot misroute telemetry.
    os.environ["CORTEX_REPO_ROOT"] = str(repo_path)

    spawned_procs: list[tuple[subprocess.Popen, str]] = []
    heartbeat_thread: Optional[RunnerHeartbeatThread] = None

    try:
        # Session startup: interrupt recovery, PID + pointer writes.
        # Skipped in dry-run mode so we don't stomp on a live runner.pid.
        if not dry_run:
            state, _pid_data, _start_time = _start_session(
                state_path=state_path,
                session_dir=session_dir,
                repo_path=repo_path,
                events_path=events_path,
                coord=coord,
                force=force,
            )
            if state is None:
                # ``_start_session`` already printed
                # "session already running" to stderr after detecting a
                # live runner under the takeover lock.
                return 1
        else:
            state = state_module.load_state(state_path)

        # Phase A pre-flight: resolve SDK auth vector + Keychain probe (R3).
        # Auth path uses ensure_sdk_auth + probe_keychain_presence (single policy).
        # The runner path has no per-feature slug (feature=None) and writes
        # events to the session-level events_path.
        probe_result = auth.resolve_and_probe(
            feature=None,
            event_log_path=events_path,
        )
        if not probe_result.ok:
            sys.stderr.write(
                f"error: auth probe failed: vector=none, "
                f"keychain={probe_result.keychain} "
                f"— Keychain entry absent; no auth vector available\n"
            )
            return 1

        # Main round loop.
        start_wall = time.monotonic()
        round_num = state.current_round
        effective_max = (
            max_rounds if max_rounds is not None else round_num + 10
        )
        strategy_path = session_dir / "overnight-strategy.json"
        integration_branch = state.integration_branch or "main"

        stall_count = 0

        # Runner-level heartbeat (spec Req 11, Task 14): start a daemon that
        # emits ``HEARTBEAT`` on a fixed cadence across ALL ``executing``
        # sub-phases — including the planning span where only ``_poll_subprocess``
        # runs and the batch_runner's ``_heartbeat_loop`` is not yet alive —
        # so the event log never goes silent during healthy plan generation.
        # Skipped under --dry-run (no real spawns, exits immediately). Stopped
        # in the ``finally`` so it never outlives the runner. Additive: it does
        # NOT alter the existing batch ``_heartbeat_loop``.
        if not dry_run:
            heartbeat_thread = RunnerHeartbeatThread(
                coord=coord,
                events_path=events_path,
                session_id=session_id,
                round_num=round_num,
            )
            heartbeat_thread.start()

        while not coord.shutdown_event.is_set():
            # Time budget check.
            if time_limit_seconds is not None:
                elapsed = time.monotonic() - start_wall
                if elapsed >= time_limit_seconds:
                    events.log_event(
                        events.CIRCUIT_BREAKER,
                        round=round_num,
                        details={
                            "reason": "time_limit",
                            "elapsed_seconds": int(elapsed),
                        },
                        log_path=events_path,
                    )
                    break

            # Round budget check.
            if round_num > effective_max:
                break

            # Stamp the runner-level heartbeat with the round now executing so
            # its planning-span beats carry the correct round (informational;
            # liveness is the load-bearing property).
            if heartbeat_thread is not None:
                heartbeat_thread.set_round(round_num)

            # Reload state to pick up mid-round mutations by peer modules.
            state = state_module.load_state(state_path)
            pending = _count_pending(state)

            # R15 re-check (race: if pending was cleared between the
            # entry check and loop iteration, this no-ops).
            if dry_run and pending > 0:
                print(
                    "--dry-run requires a state file with all features "
                    "in terminal states",
                    file=sys.stderr,
                    flush=True,
                )
                return 1

            if pending == 0:
                print(
                    f"Round {round_num}: No pending features — all done",
                    flush=True,
                )
                break

            # Resume skip: if results file already exists, advance round.
            results_file = session_dir / f"batch-{round_num}-results.json"
            if results_file.exists():
                print(
                    f"Round {round_num}: results file already exists — skipping",
                    flush=True,
                )
                state.current_round = round_num + 1
                _save_state_locked(state, state_path, coord)
                round_num += 1
                continue

            merged_before = _count_merged(state)

            print(
                f"--- Round {round_num} ({pending} features pending) ---",
                flush=True,
            )
            events.log_event(
                events.ROUND_START,
                round=round_num,
                details={"pending": pending},
                log_path=events_path,
            )

            # Fill prompt template.
            filled = fill_prompt.fill_prompt(
                round_number=round_num,
                state_path=state_path,
                plan_path=plan_path,
                events_path=events_path,
                session_dir=session_dir,
                tier=tier,
            )

            # -----------------------------------------------------------
            # Dry-run: no subprocess spawns; just advance state so the
            # loop exits on the next iteration. Real state writes
            # proceed per R15.
            # -----------------------------------------------------------
            if dry_run:
                dry_run_echo("orchestrator", "claude", "-p", "<filled prompt>")
                state.current_round = round_num + 1
                _save_state_locked(state, state_path, coord)
                round_num += 1
                continue

            # -----------------------------------------------------------
            # Spawn orchestrator agent + watchdog, poll to exit.
            # -----------------------------------------------------------
            print(
                f"Spawning orchestrator agent for round {round_num}...",
                flush=True,
            )
            # R2/R8: emit dispatch_start AFTER the dry-run gate and BEFORE
            # _spawn_orchestrator. Per-session pipeline-events.log per
            # feature_executor.py's config.pipeline_events_path
            # convention; auto-discovered by discover_pipeline_event_logs.
            orchestrator_stdout_path = (
                session_dir / f"orchestrator-round-{round_num}.stdout.json"
            )
            pipeline_events_path = session_dir / "pipeline-events.log"
            try:
                from cortex_command.pipeline.state import (
                    log_event as pipeline_log_event,
                )
                from cortex_command.pipeline.dispatch import (
                    resolve_effort,
                )
                # The orchestrator-round dispatch starts with model=None because
                # the actual model is only known after the envelope is parsed.
                # Resolve effort against "sonnet" as a stable fallback so paired
                # records carry a non-None effort axis through pair_dispatch_events
                # and the bucket-by-effort signal fires for orchestrator-round
                # dispatches (Task 5/Task 6 of the xhigh-effort feature).
                _round_effort = resolve_effort(
                    tier, "medium", "orchestrator-round", "sonnet"
                )
                pipeline_log_event(
                    pipeline_events_path,
                    {
                        "event": "dispatch_start",
                        "feature": f"<orchestrator-round-{round_num}>",
                        "skill": "orchestrator-round",
                        "complexity": tier,
                        "criticality": "medium",
                        "model": None,
                        "effort": _round_effort,
                        "attempt": 1,
                    },
                )
            except Exception as exc:
                print(
                    f"[telemetry] orchestrator-round dispatch_start "
                    f"emission failed: {exc!r}",
                    file=sys.stderr,
                    flush=True,
                )
            o_proc = None
            try:
                o_proc, o_wctx, _o_watchdog = _spawn_orchestrator(
                    filled_prompt=filled,
                    coord=coord,
                    spawned_procs=spawned_procs,
                    stdout_path=orchestrator_stdout_path,
                    state=state,
                    session_dir=session_dir,
                    round_num=round_num,
                )
                exit_code = _poll_subprocess(o_proc, coord)

                # R3/R6: read the envelope and emit terminal telemetry
                # before the stall/non-zero branches. Helper is
                # fire-and-forget; failures here never abort the loop.
                envelope_text: str | None = None
                try:
                    envelope_text = orchestrator_stdout_path.read_text()
                except Exception as exc:
                    print(
                        f"[telemetry] orchestrator-round stdout read "
                        f"failed: {exc!r}",
                        file=sys.stderr,
                        flush=True,
                    )
                _emit_orchestrator_round_telemetry(
                    envelope_text,
                    exit_code,
                    round_num,
                    pipeline_events_path,
                )

                if exit_code is None:
                    # Shutdown intercepted; fall through to cleanup.
                    break

                if o_wctx.stall_flag.is_set():
                    # Req 7: thread the kill-reason marker (``inactivity``
                    # vs ``ceiling``) so the morning report can tell a
                    # silent child from a ceiling-kill. In Phase 1 the
                    # orchestrator runs with activity_probe=None, so its
                    # inactivity tier is the blind 1800s timer; the reason
                    # still distinguishes a ceiling-kill from that timer.
                    _o_reason = o_wctx.stall_reason or "inactivity"
                    print(
                        "Warning: watchdog killed orchestrator due to event "
                        f"log silence (stall timeout, reason={_o_reason})",
                        flush=True,
                    )
                    events.log_event(
                        events.ORCHESTRATOR_FAILED,
                        round=round_num,
                        details={
                            "reason": "stall_timeout",
                            "stall_reason": _o_reason,
                        },
                        log_path=events_path,
                    )
                    _transition_paused(
                        state_path=state_path,
                        events_path=events_path,
                        coord=coord,
                        reason="stall_timeout",
                        round_num=round_num,
                    )
                    _notify(
                        f"Overnight session stalled — orchestrator watchdog "
                        f"fired. Session paused. Session: {session_id}"
                    )
                    break
                elif exit_code != 0:
                    print(
                        f"Warning: orchestrator agent exited with code {exit_code}",
                        flush=True,
                    )
                    events.log_event(
                        events.ORCHESTRATOR_FAILED,
                        round=round_num,
                        details={"exit_code": exit_code},
                        log_path=events_path,
                    )
            finally:
                # Close the orchestrator stdout write handle on every exit
                # branch (success, non-zero, stall, shutdown, exception).
                # Fire-and-forget telemetry must not leak fds across
                # rounds in a multi-hour overnight session.
                if (
                    o_proc is not None
                    and o_proc.stdout is not None
                    and not o_proc.stdout.closed
                ):
                    try:
                        o_proc.stdout.close()
                    except Exception:
                        pass

            # -----------------------------------------------------------
            # Commit the round's generated plan.md files inside each
            # feature's integration worktree (replaces the orchestrator
            # agent's prose /commit step, which landed on home main).
            # Reload state to pick up the plans the orchestrator just
            # wrote and the features it marked this round.
            # -----------------------------------------------------------
            try:
                _commit_round_plans_in_worktree(
                    state=state_module.load_state(state_path),
                    home_repo_path=repo_path,
                    session_id=session_id,
                    events_path=events_path,
                )
            except Exception as exc:
                print(
                    f"Warning: plan commit failed: {exc}",
                    flush=True,
                )

            # -----------------------------------------------------------
            # Spawn batch_runner + watchdog (if a batch plan was produced).
            # -----------------------------------------------------------
            batch_plan_path = session_dir / f"batch-plan-round-{round_num}.md"
            if not batch_plan_path.exists():
                events.log_event(
                    events.ORCHESTRATOR_NO_PLAN,
                    round=round_num,
                    details={"round": round_num},
                    log_path=events_path,
                )
                print(
                    f"Round {round_num}: no batch plan produced — skipping batch_runner",
                    flush=True,
                )
            else:
                b_proc, b_wctx, _b_watchdog = _spawn_batch_runner(
                    batch_plan_path=batch_plan_path,
                    batch_id=round_num,
                    tier=tier,
                    integration_branch=integration_branch,
                    state_path=state_path,
                    events_path=events_path,
                    test_command=None,
                    coord=coord,
                    spawned_procs=spawned_procs,
                    # The batch child writes this same session
                    # pipeline-events.log (see _spawn_batch_runner) — wire
                    # the watchdog's inactivity probe to it (Req 9).
                    pipeline_events_path=pipeline_events_path,
                )
                batch_exit = _poll_subprocess(b_proc, coord)
                if batch_exit is None:
                    break

                if b_wctx.stall_flag.is_set():
                    # Req 7: thread the kill-reason marker (``inactivity``
                    # vs ``ceiling``). The batch watchdog has a real
                    # worker-driven probe (pipeline-events.log), so an
                    # ``inactivity`` kill means genuine worker silence and a
                    # ``ceiling`` kill means a loud-but-stuck loop the
                    # inactivity tier is blind to — tune the ceiling.
                    _b_reason = b_wctx.stall_reason or "inactivity"
                    print(
                        "Warning: watchdog killed batch_runner due to "
                        f"event log silence (stall timeout, reason={_b_reason})",
                        flush=True,
                    )
                    events.log_event(
                        events.BATCH_RUNNER_STALLED,
                        round=round_num,
                        details={
                            "round": round_num,
                            "stall_reason": _b_reason,
                        },
                        log_path=events_path,
                    )
                    _transition_paused(
                        state_path=state_path,
                        events_path=events_path,
                        coord=coord,
                        reason="stall_timeout",
                        round_num=round_num,
                    )
                    _notify(
                        f"Overnight batch_runner stalled. Session paused. "
                        f"Session: {session_id}"
                    )
                    break
                elif batch_exit != 0:
                    print(
                        f"Warning: batch_runner exited with code {batch_exit}",
                        flush=True,
                    )
                    events.log_event(
                        events.ORCHESTRATOR_FAILED,
                        round=round_num,
                        details={"exit_code": batch_exit},
                        log_path=events_path,
                    )

                # Session-halt early-out (budget_exhausted or api_rate_limit).
                state = state_module.load_state(state_path)
                if state.paused_reason in ("budget_exhausted", "api_rate_limit"):
                    print(
                        "Session paused — stopping round loop",
                        flush=True,
                    )
                    events.log_event(
                        events.CIRCUIT_BREAKER,
                        round=round_num,
                        details={"reason": state.paused_reason},
                        log_path=events_path,
                    )
                    break

                # In-process map_results (R5: no subprocess dispatch).
                try:
                    _apply_batch_results(
                        batch_plan_path=batch_plan_path,
                        batch_id=round_num,
                        state_path=state_path,
                        strategy_path=strategy_path,
                        coord=coord,
                    )
                except Exception as exc:
                    print(
                        f"Warning: map_results failed: {exc}",
                        flush=True,
                    )

            # End-of-round dependent-failure sweep (R5/R6). Runs every round
            # — including no-batch-plan rounds — at the branch re-convergence
            # point, after results are mapped into state and before the
            # merged/pending evaluation. Fails every non-terminal dependent of
            # a terminally-``failed`` blocker to ``failed`` (``blocker_failed``)
            # to a fixpoint, then persists the mutated state atomically so the
            # next iteration's ``pending == 0`` check (and ``_count_merged``
            # below) read the swept state. The sweep merges nothing, so its
            # round still increments ``stall_count`` via ``merged_delta <= 0``;
            # the stall breaker remains the backstop for genuinely-churning
            # independent work. The clean ``pending == 0`` exit is reached only
            # when the failed subtree is the remaining pending work.
            state = state_module.load_state(state_path)
            state = state_module.sweep_blocker_failed_dependents(state)
            _save_state_locked(state, state_path, coord)

            # Count merged delta for the progress circuit breaker.
            merged_after = _count_merged(state)
            merged_delta = merged_after - merged_before
            print(
                f"Round {round_num} complete: {merged_delta} features merged this round",
                flush=True,
            )
            events.log_event(
                events.ROUND_COMPLETE,
                round=round_num,
                details={
                    "merged_this_round": merged_delta,
                    "merged_total": merged_after,
                },
                log_path=events_path,
            )

            # Synthesizer defer-count circuit breaker. Mirrors the
            # 3-pause batch circuit breaker semantics at
            # orchestrator.py:241,249-253,269-273. When the count of
            # PLAN_SYNTHESIS_DEFERRED events for this session reaches
            # CIRCUIT_BREAKER_THRESHOLD, transition the session to
            # paused with reason "synthesizer_circuit_breaker", mark
            # all remaining critical-tier features as paused so they
            # are not re-dispatched, and break the round loop. The
            # per-session events log already filters by session, but
            # the helper applies the session_id filter defensively.
            synthesizer_deferred_count = _count_synthesizer_deferred(
                events_path, session_id
            )
            if synthesizer_deferred_count >= CIRCUIT_BREAKER_THRESHOLD:
                print(
                    "Circuit breaker: synthesizer deferred "
                    f"{synthesizer_deferred_count} times — stopping",
                    flush=True,
                )
                events.log_event(
                    events.SYNTHESIZER_CIRCUIT_BREAKER_FIRED,
                    round=round_num,
                    details={
                        "session_id": session_id,
                        "deferred_count": synthesizer_deferred_count,
                    },
                    log_path=events_path,
                )
                _transition_paused(
                    state_path=state_path,
                    events_path=events_path,
                    coord=coord,
                    reason="synthesizer_circuit_breaker",
                    round_num=round_num,
                )
                # Mark remaining critical-tier features as paused so
                # the orchestrator's resume path does not re-dispatch
                # them. read_criticality() defaults to "medium" when no
                # cortex/lifecycle/{feature}/events.log carries a criticality
                # entry, so non-critical features are unaffected.
                state = state_module.load_state(state_path)
                for name, fs in list(state.features.items()):
                    if fs.status in ("merged", "failed", "deferred", "paused"):
                        continue
                    try:
                        criticality = read_criticality(name)
                    except Exception:
                        criticality = "medium"
                    if criticality != "critical":
                        continue
                    state = state_module.update_feature_status(
                        state,
                        name,
                        "paused",
                        error="synthesizer_circuit_breaker",
                    )
                _save_state_locked(state, state_path, coord)
                break

            if merged_delta <= 0:
                stall_count += 1
                if stall_count >= 2:
                    print(
                        "Circuit breaker: 2 consecutive rounds with zero progress — stopping",
                        flush=True,
                    )
                    events.log_event(
                        events.CIRCUIT_BREAKER,
                        round=round_num,
                        details={"reason": "stall", "stall_count": stall_count},
                        log_path=events_path,
                    )
                    break
            else:
                stall_count = 0

            # Advance round counter with signal-shielded state write.
            state.current_round = round_num + 1
            _save_state_locked(state, state_path, coord)
            round_num += 1

        # -----------------------------------------------------------------
        # Out of the round loop — decide between cleanup and clean exit.
        # -----------------------------------------------------------------
        if coord.shutdown_event.is_set():
            # Signal-driven exit: invoke cleanup (never returns).
            return _cleanup(
                coord=coord,
                spawned_procs=spawned_procs,
                state_path=state_path,
                session_dir=session_dir,
                repo_path=repo_path,
                events_path=events_path,
                session_id=session_id,
                round_num=round_num,
                prior_handlers=prior,
            )

        # Clean loop exit. Run the post-loop sequence (PR-gating,
        # morning-report, followup commit, notify, worktree cleanup).
        # Ported from ``runner.sh:851-1694`` per Task 6c (R15, R16,
        # Edge Cases line 245). Also runs under --dry-run so the
        # DRY-RUN label contract (R15) is observable end-to-end.
        _post_loop(
            state=state,
            state_path=state_path,
            session_dir=session_dir,
            repo_path=repo_path,
            events_path=events_path,
            round_num=round_num,
            session_id=session_id,
            dry_run=dry_run,
            coord=coord,
        )

        return 0

    finally:
        # Stop the runner-level heartbeat first so it never emits after the
        # session has exited the round loop. ``stop()`` wakes the thread's
        # ``wait`` immediately on the clean path; a short ``join`` reaps it
        # without blocking on the full cadence interval. Daemon status makes
        # this defense-in-depth — the thread cannot outlive the interpreter
        # even on the signal path where ``_cleanup`` re-raises before this
        # ``finally`` completes.
        if heartbeat_thread is not None:
            try:
                heartbeat_thread.stop()
                heartbeat_thread.join(timeout=1.0)
            except Exception:
                pass
        # Tear down any still-live spawned subprocesses before restoring
        # handlers — guarantees no orphan PGIDs survive a crash path.
        for proc, _label in spawned_procs:
            if proc.poll() is None:
                try:
                    _kill_subprocess_group(proc, coord)
                except Exception:
                    pass
        # Best-effort clear of the per-session ``runner.pid`` so a
        # non-signaled crash/exception loop-exit does not leave a stale
        # pid behind while state stays ``executing`` (which would mask the
        # stuck state from observers). The signal path already clears it in
        # ``_cleanup`` and the clean path in ``_post_loop``; the CAS on
        # ``session_id`` makes those prior clears safe no-ops here and stops
        # a displaced owner from clobbering a successor's claim. This is
        # defense-in-depth — the authoritative clear is the out-of-process
        # recovery core; swallow any error so cleanup never masks the
        # original exception.
        try:
            ipc.clear_runner_pid(session_dir, expected_session_id=session_id)
        except Exception:
            pass
        restore_signal_handlers(prior)


# smoke_test + integration_recovery + plan are imported at module load
# so R5's in-process-import contract is satisfied even for code paths
# that only enter via post-loop integration. Reference them in __all__
# to keep static analysers from flagging them as unused.
_ = smoke_test  # noqa: F841  (R5 import satisfaction)
_ = integration_recovery  # noqa: F841  (R5 import satisfaction)
_ = plan  # noqa: F841  (R5 import satisfaction)


__all__ = [
    "KILL_ESCALATION_SECONDS",
    "ORCHESTRATOR_MAX_TURNS",
    "POLL_INTERVAL_SECONDS",
    "RUNNER_HEARTBEAT_INTERVAL_SECONDS",
    "RunnerHeartbeatThread",
    "STALL_TIMEOUT_SECONDS",
    "dry_run_echo",
    "run",
]
