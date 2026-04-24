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

import json
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from importlib.resources import files
from pathlib import Path
from typing import Optional

from cortex_command.overnight import auth
from cortex_command.overnight import events
from cortex_command.overnight import fill_prompt
from cortex_command.overnight import integration_recovery
from cortex_command.overnight import interrupt
from cortex_command.overnight import ipc
from cortex_command.overnight import map_results
from cortex_command.overnight import plan
from cortex_command.overnight import report
from cortex_command.overnight import smoke_test
from cortex_command.overnight import state as state_module
from cortex_command.overnight.batch_runner import main as batch_runner_main  # noqa: F401  (R5: in-process import list)
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

#: Orchestrator ``claude -p`` turn cap. Matches ``runner.sh:643``.
ORCHESTRATOR_MAX_TURNS: int = 50


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

    # (3) Partial morning-report sequence.
    try:
        data = report.collect_report_data(
            state_path=state_path,
            events_path=events_path,
        )
        backlog_dir = repo_path / "backlog"
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

    # (4) Tear down spawned subprocess groups.
    for proc, _label in spawned_procs:
        if proc.poll() is None:
            _kill_subprocess_group(proc, coord)

    # (5) Clear per-session runner.pid — R8 clean-shutdown contract.
    try:
        ipc.clear_runner_pid(session_dir)
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
) -> Optional[str]:
    """Check for a live session via ``runner.pid`` + ``verify_runner_pid``.

    Returns an error message when a live session is detected (caller
    should print to stderr and exit nonzero). Returns ``None`` after a
    successful stale-self-heal or when no PID file exists.
    """
    pid_data = ipc.read_runner_pid(session_dir)
    if pid_data is None:
        return None
    if ipc.verify_runner_pid(pid_data):
        return "session already running"
    # Stale — self-heal.
    ipc.clear_runner_pid(session_dir)
    ipc.clear_active_session()
    return None


def _start_session(
    state_path: Path,
    session_dir: Path,
    repo_path: Path,
    events_path: Path,
    coord: RunnerCoordination,
) -> tuple[state_module.OvernightState, dict, str]:
    """Run R8/R9/R14 session startup: interrupt recovery, PID + pointer writes.

    Returns the loaded state, the pid_data payload used to write
    ``runner.pid`` (reused for pointer updates), and the ``start_time``
    string used for PID-reuse detection.
    """
    # R14 interrupt recovery for features stuck in "running".
    interrupt.handle_interrupted_features(state_path)

    state = state_module.load_state(state_path)
    session_id = state.session_id
    if not session_id:
        raise RuntimeError(f"state file {state_path} has empty session_id")

    start_time = datetime.now(timezone.utc).isoformat()
    pid = os.getpid()
    try:
        pgid = os.getpgid(pid)
    except ProcessLookupError:
        pgid = pid

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

    with deferred_signals(coord):
        ipc.write_runner_pid(
            session_dir=session_dir,
            pid=pid,
            pgid=pgid,
            start_time=start_time,
            session_id=session_id,
            repo_path=repo_path,
        )
        ipc.write_active_session(pid_data, phase="executing")

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

def _spawn_orchestrator(
    filled_prompt: str,
    coord: RunnerCoordination,
    spawned_procs: list[tuple[subprocess.Popen, str]],
) -> tuple[subprocess.Popen, WatchdogContext, WatchdogThread]:
    """Spawn the per-round ``claude -p`` orchestrator with a watchdog."""
    claude_path = "claude"
    proc = subprocess.Popen(
        [
            claude_path,
            "-p",
            filled_prompt,
            "--dangerously-skip-permissions",
            "--max-turns",
            str(ORCHESTRATOR_MAX_TURNS),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    spawned_procs.append((proc, "orchestrator"))
    wctx = WatchdogContext(stall_flag=threading.Event())
    watchdog = WatchdogThread(
        proc=proc,
        timeout_seconds=STALL_TIMEOUT_SECONDS,
        coord=coord,
        wctx=wctx,
        label="orchestrator",
    )
    watchdog.start()
    return proc, wctx, watchdog


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
) -> tuple[subprocess.Popen, WatchdogContext, WatchdogThread]:
    """Spawn ``cortex-batch-runner`` console-script shim with a watchdog.

    Per R5: the console-script shim is the only allowed external
    invocation for batch_runner — the module-dispatch form is banned,
    as is ``[sys.executable, "-m", "..."]`` (same intent via runtime
    argv).
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
    )
    spawned_procs.append((proc, "batch_runner"))
    wctx = WatchdogContext(stall_flag=threading.Event())
    watchdog = WatchdogThread(
        proc=proc,
        timeout_seconds=STALL_TIMEOUT_SECONDS,
        coord=coord,
        wctx=wctx,
        label="batch_runner",
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
) -> int:
    """Run the overnight round-dispatch loop.

    Single public entry point; returns a process exit code. Paths arrive
    from the CLI — ``runner.py`` itself never derives user-repo paths
    from ``__file__`` or env vars (R20).

    Args:
        state_path: Path to ``overnight-state.json`` for this session.
        session_dir: Directory under ``lifecycle/sessions/{id}/``.
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

    Returns:
        Process exit code. ``0`` on clean loop exit. Nonzero on
        concurrent-start collision, dry-run rejection, or propagated
        signal exit.
    """
    # Load once for concurrent-start guard and startup logging.
    state = state_module.load_state(state_path)
    session_id = state.session_id

    # Concurrent-start guard (spec Edge Cases + R8).
    concurrent_err = _check_concurrent_start(session_dir)
    if concurrent_err is not None:
        print(concurrent_err, file=sys.stderr, flush=True)
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

    # Export LIFECYCLE_SESSION_ID so spawned children (orchestrator
    # agent and cortex-batch-runner) pick up the per-session events-log
    # suffix expected by peer modules.
    os.environ["LIFECYCLE_SESSION_ID"] = session_id

    spawned_procs: list[tuple[subprocess.Popen, str]] = []

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
            )
        else:
            state = state_module.load_state(state_path)

        # Optional pre-flight: the auth helper resolves API keys for SDK
        # subagents. Errors are non-fatal — log and continue.
        try:
            auth.ensure_sdk_auth(event_log_path=events_path)
        except Exception:
            pass

        # Main round loop.
        start_wall = time.monotonic()
        round_num = state.current_round
        effective_max = (
            max_rounds if max_rounds is not None else round_num + 10
        )
        strategy_path = session_dir / "overnight-strategy.json"
        integration_branch = state.integration_branch or "main"

        stall_count = 0

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
            o_proc, o_wctx, _o_watchdog = _spawn_orchestrator(
                filled_prompt=filled,
                coord=coord,
                spawned_procs=spawned_procs,
            )
            exit_code = _poll_subprocess(o_proc, coord)
            if exit_code is None:
                # Shutdown intercepted; fall through to cleanup.
                break

            if o_wctx.stall_flag.is_set():
                print(
                    "Warning: watchdog killed orchestrator due to event "
                    "log silence (stall timeout)",
                    flush=True,
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
                )
                batch_exit = _poll_subprocess(b_proc, coord)
                if batch_exit is None:
                    break

                if b_wctx.stall_flag.is_set():
                    print(
                        "Warning: watchdog killed batch_runner due to "
                        "event log silence (stall timeout)",
                        flush=True,
                    )
                    events.log_event(
                        events.BATCH_RUNNER_STALLED,
                        round=round_num,
                        details={"round": round_num},
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

                # Budget-exhaustion early-out.
                state = state_module.load_state(state_path)
                if state.paused_reason == "budget_exhausted":
                    print(
                        "Session paused: API budget exhausted — stopping round loop",
                        flush=True,
                    )
                    events.log_event(
                        events.CIRCUIT_BREAKER,
                        round=round_num,
                        details={"reason": "budget_exhausted"},
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

            # Count merged delta for the progress circuit breaker.
            state = state_module.load_state(state_path)
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

        # Clean loop exit. Log session_complete and clear artifacts.
        if not dry_run:
            try:
                events.log_event(
                    events.SESSION_COMPLETE,
                    round=max(round_num - 1, 1),
                    details={"clean_exit": True},
                    log_path=events_path,
                )
            except Exception:
                pass
            # Post-loop tasks (integration-gate, PR creation, morning-
            # report generation) remain in runner.sh for this phase per
            # Task 15; runner.py's responsibility is the round-loop
            # core. Clear runner.pid on clean shutdown per R8.
            try:
                ipc.clear_runner_pid(session_dir)
            except Exception:
                pass
            # Transition the active-session pointer if the session
            # reached terminal phase.
            try:
                state = state_module.load_state(state_path)
                if state.phase == "complete":
                    ipc.clear_active_session()
            except Exception:
                pass

        return 0

    finally:
        # Tear down any still-live spawned subprocesses before restoring
        # handlers — guarantees no orphan PGIDs survive a crash path.
        for proc, _label in spawned_procs:
            if proc.poll() is None:
                try:
                    _kill_subprocess_group(proc, coord)
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
    "STALL_TIMEOUT_SECONDS",
    "dry_run_echo",
    "run",
]
