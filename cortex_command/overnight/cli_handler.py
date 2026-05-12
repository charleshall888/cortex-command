"""CLI dispatch handlers for ``cortex overnight`` subcommands.

This module implements R1/R2/R3/R4 user-facing behavior for the
``cortex overnight start|status|cancel|logs`` command surface. Per R20,
the CLI is the single site that resolves user-repo paths (``repo_path``,
``session_dir``, ``state_path``, ``plan_path``, ``events_path``) — those
paths flow from here as typed parameters into :mod:`runner.run`,
:mod:`ipc`, :mod:`logs.read_log`, and :mod:`status`.

Each handler function returns an ``int`` process exit code. They never
raise ``SystemExit`` directly; ``cortex_command.cli.main`` is the top-
level entry and performs the final ``sys.exit``.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Optional

from cortex_command.overnight import fail_markers as fail_markers_module
from cortex_command.overnight import ipc
from cortex_command.overnight import logs as logs_module
from cortex_command.overnight import runner as runner_module
from cortex_command.overnight import session_validation
from cortex_command.overnight import status as status_module
from cortex_command.overnight.scheduler.spawn import wait_for_pid_file


# Sentinel filename written by the parent CLI between ``runner.spawn-pending``
# write and the runner's own ``runner.pid`` claim. Surfaces phase
# ``starting`` to ``cortex overnight status`` for the brief async-spawn
# handshake window (Task 6, spec R18).
_SPAWN_PENDING_SENTINEL = "runner.spawn-pending"

# Async-spawn handshake budget. Spec R18: caller returns within 5 seconds
# with the runner's PID once verified live, or with
# ``error_class: spawn_timeout`` / ``spawn_died`` if the handshake fails.
_SPAWN_HANDSHAKE_TIMEOUT_SECONDS: float = 5.0

# Grace window after ``SIGTERM`` before escalating to ``SIGKILL`` when
# tearing down an orphan runner that did not write ``runner.pid`` within
# the handshake budget.
_ORPHAN_KILL_GRACE_SECONDS: float = 1.0


# ---------------------------------------------------------------------------
# Synthesizer kill-switch gate (Spec R7)
# ---------------------------------------------------------------------------

def read_synthesizer_gate(config_path: Path) -> bool:
    """Read ``synthesizer_overnight_enabled`` from lifecycle.config.md frontmatter.

    Mirrors the read pattern in
    :func:`cortex_command.overnight.daytime_pipeline._read_test_command`:
    open the file, scan frontmatter lines (between ``---`` delimiters)
    for the ``synthesizer_overnight_enabled:`` prefix, and parse the
    trailing value case-insensitively (``true``/``True``/``TRUE`` → True;
    everything else → False).

    Fail-closed semantics per Spec Requirement 7: returns ``False`` when
    the file is absent, the frontmatter is malformed, or the field is
    missing. The orchestrator's parallel-variant dispatch branch (T6)
    grep-checks for this function name and uses the boolean to gate the
    overnight synthesizer path until operator validation flips the flag.
    """
    try:
        text = config_path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return False

    in_frontmatter = False
    seen_opening_delim = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "---":
            if not seen_opening_delim:
                seen_opening_delim = True
                in_frontmatter = True
                continue
            # Closing delimiter — frontmatter complete.
            break
        if not in_frontmatter:
            continue
        if stripped.startswith("synthesizer_overnight_enabled:"):
            value = stripped[len("synthesizer_overnight_enabled:"):].strip()
            # Strip surrounding quotes if present.
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            return value.lower() == "true"
    return False


# ---------------------------------------------------------------------------
# JSON-output helpers (R4, R5, R15)
# ---------------------------------------------------------------------------

# Schema-floor version stamped on every JSON payload emitted by the CLI for
# MCP consumption. Major.minor per Terraform's ``format_version`` convention
# (R15): consumers reject mismatched majors; minor bumps are additive.
_JSON_SCHEMA_VERSION = "1.0"


def _emit_json(payload: dict) -> None:
    """Print ``payload`` as a one-line JSON object stamped with the schema version.

    Always prefixes ``"version": _JSON_SCHEMA_VERSION`` so the consumer can
    enforce the schema-floor check without reaching past the first field.
    """
    versioned = {"version": _JSON_SCHEMA_VERSION, **payload}
    print(json.dumps(versioned))


# ---------------------------------------------------------------------------
# Path resolution helpers (R20)
# ---------------------------------------------------------------------------

def _resolve_repo_path() -> Path:
    """Return the home repository root, preferring ``git rev-parse``.

    Falls back to ``Path.cwd()`` when the current directory is not a git
    working tree (or ``git`` is unavailable). The CLI is the single site
    that resolves user-repo paths (R20).
    """
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return Path(out.strip())
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return Path.cwd()


def _auto_discover_state(lifecycle_sessions_root: Path) -> Optional[Path]:
    """Return the most relevant ``overnight-state.json`` path or ``None``.

    Port of ``runner.sh:122-163``: prefers the ``latest-overnight``
    symlink when present, falling back to scanning
    ``*/overnight-state.json`` for the most-recent-mtime file whose
    state has ``phase == "executing"``. Falls back to the
    most-recent-mtime state file if no executing session is found.
    """
    if not lifecycle_sessions_root.exists():
        return None

    # Check for latest-overnight symlink first.
    symlink = lifecycle_sessions_root / "latest-overnight"
    if symlink.is_symlink():
        try:
            target = symlink.resolve()
        except OSError:
            target = None
        if target is not None:
            candidate = target / "overnight-state.json"
            if candidate.exists():
                return candidate

    # Fall back to per-session state files, skipping the symlink entry.
    candidates = sorted(
        (
            p
            for p in lifecycle_sessions_root.glob("*/overnight-state.json")
            if not p.parent.is_symlink()
        ),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    # Prefer executing sessions.
    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("phase") == "executing":
            return path

    return candidates[0] if candidates else None


# ---------------------------------------------------------------------------
# start (R1)
# ---------------------------------------------------------------------------

def _run_runner_inline(
    *,
    state_path: Path,
    session_dir: Path,
    repo_path: Path,
    plan_path: Path,
    events_path: Path,
    args: argparse.Namespace,
) -> int:
    """Invoke the blocking runner in-process (dry-run / launchd paths).

    Renamed from the original blocking ``handle_start`` body; the only
    callers are:
      - the ``--dry-run`` short-circuit (preserves the inline DRY-RUN
        echoes that ``test_runner_pr_gating.py`` asserts on stdout);
      - the ``--launchd`` internal flag, which signals "you ARE the
        runner now — skip the spawn-handshake fork".

    The async-spawn fork in :func:`_spawn_runner_async` does NOT call
    this helper; it execs ``cortex overnight start --launchd`` in the
    child so the returning shim and the runner are distinct processes.
    """
    return runner_module.run(
        state_path=state_path,
        session_dir=session_dir,
        repo_path=repo_path,
        plan_path=plan_path,
        events_path=events_path,
        time_limit_seconds=args.time_limit,
        max_rounds=args.max_rounds,
        tier=args.tier,
        dry_run=args.dry_run,
    )


def _build_async_spawn_argv(args: argparse.Namespace, state_path: Path) -> list[str]:
    """Build the child ``argv`` for the async-spawn fork.

    Re-invokes the same ``cortex overnight start`` entry with the
    internal ``--launchd`` flag set, which signals to the child that it
    is the runner itself and must skip the spawn-handshake step. The
    state file path is forwarded explicitly so the child does not need
    to re-run auto-discovery against a possibly-different cwd.
    """
    argv: list[str] = [
        sys.executable,
        "-m",
        "cortex_command.cli",
        "overnight",
        "start",
        "--launchd",
        "--state",
        str(state_path),
        "--tier",
        str(getattr(args, "tier", "simple")),
    ]
    time_limit = getattr(args, "time_limit", None)
    if isinstance(time_limit, int):
        argv.extend(["--time-limit", str(time_limit)])
    max_rounds = getattr(args, "max_rounds", None)
    if isinstance(max_rounds, int):
        argv.extend(["--max-rounds", str(max_rounds)])
    return argv


def _terminate_orphan_child(child: subprocess.Popen) -> None:
    """Tear down an orphan async-spawn child whose handshake timed out.

    The child was spawned with ``start_new_session=True``, which made it
    the leader of its own process group. ``os.killpg(pgid, SIGTERM)``
    delivers the signal to the entire group so any subprocesses the
    child already spawned receive the same shutdown intent. Escalates
    to ``SIGKILL`` after :data:`_ORPHAN_KILL_GRACE_SECONDS` if the child
    has not exited.

    All ``ProcessLookupError`` / ``OSError`` exceptions from the kill
    path are swallowed — the goal is best-effort cleanup before the
    parent CLI returns ``started: false``; a failure to signal a
    process that is already dead is not actionable.
    """
    try:
        pgid = os.getpgid(child.pid)
    except (ProcessLookupError, OSError):
        pgid = None

    if pgid is not None:
        try:
            os.killpg(pgid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            pass

    try:
        child.wait(timeout=_ORPHAN_KILL_GRACE_SECONDS)
        return
    except subprocess.TimeoutExpired:
        pass

    if pgid is not None:
        try:
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass
    try:
        child.wait(timeout=_ORPHAN_KILL_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        pass


def _cleanup_spawn_sentinel(session_dir: Path) -> None:
    """Best-effort unlink of the spawn-pending sentinel.

    The runner deletes this on its own startup path after writing
    ``runner.pid``, but the parent shim is responsible for cleanup on
    every error branch (timeout, runner-died) so a status query never
    sees a stale sentinel.
    """
    try:
        (session_dir / _SPAWN_PENDING_SENTINEL).unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass


def _spawn_runner_async(
    *,
    state_path: Path,
    session_dir: Path,
    repo_path: Path,
    args: argparse.Namespace,
) -> dict:
    """Fork the runner and return after the liveness-checked handshake.

    Implements the spec R2 / R18 async-spawn contract:

    1. Write ``<session_dir>/runner.spawn-pending`` so a concurrent
       ``cortex overnight status`` call can report ``phase: starting``.
    2. ``subprocess.Popen`` the runner with ``start_new_session=True``,
       ``stdin=DEVNULL``, and stdout/stderr redirected to per-session
       log files. The child re-invokes the CLI with ``--launchd`` so it
       skips the handshake fork.
    3. Poll for ``<session_dir>/runner.pid`` appearance up to
       :data:`_SPAWN_HANDSHAKE_TIMEOUT_SECONDS` via
       :func:`wait_for_pid_file`, which performs the
       ``os.kill(pid, 0)`` liveness probe before returning.

    Returns a dict matching the JSON envelope shape:
      - on success: ``{"started": True, "session_id": ..., "pid": ...}``;
      - on liveness-probe failure: ``{"started": False, "error_class":
        "spawn_died", "session_id": ...}``;
      - on timeout: ``{"started": False, "error_class":
        "spawn_timeout", "session_id": ...}``.
    """
    session_id = state_path.parent.name
    sentinel_path = session_dir / _SPAWN_PENDING_SENTINEL
    pid_path = session_dir / "runner.pid"
    stdout_log = session_dir / "runner-stdout.log"
    stderr_log = session_dir / "runner-stderr.log"

    session_dir.mkdir(parents=True, exist_ok=True)

    # (3) Write the spawn-pending sentinel BEFORE Popen so the status
    # surface can attribute the gap to "starting" if a query lands
    # within the handshake window.
    try:
        sentinel_path.write_text("", encoding="utf-8")
    except OSError as exc:
        return {
            "started": False,
            "error_class": "spawn_sentinel_write_failed",
            "session_id": session_id,
            "message": str(exc),
        }

    argv = _build_async_spawn_argv(args, state_path)

    # (4) Fork the runner detached. ``start_new_session=True`` makes the
    # child the leader of its own process group + session, so SIGINT
    # delivered to the parent's TTY does NOT propagate to the runner.
    # That is the intended behavior under async-spawn — the parent shim
    # exits within 5s and is no longer the right signal target.
    stdout_fd = open(stdout_log, "ab")
    stderr_fd = open(stderr_log, "ab")
    try:
        child = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=stdout_fd,
            stderr=stderr_fd,
            start_new_session=True,
            close_fds=True,
        )
    except (OSError, ValueError) as exc:
        try:
            stdout_fd.close()
        finally:
            stderr_fd.close()
        _cleanup_spawn_sentinel(session_dir)
        return {
            "started": False,
            "error_class": "spawn_failed",
            "session_id": session_id,
            "message": str(exc),
        }
    finally:
        # The child has inherited the FDs; the parent does not need to
        # keep them open. Closing the parent's handles avoids an FD
        # leak across handshake retries.
        try:
            stdout_fd.close()
        except OSError:
            pass
        try:
            stderr_fd.close()
        except OSError:
            pass

    # (5) Poll for runner.pid + liveness.
    pid = wait_for_pid_file(
        pid_path,
        timeout=_SPAWN_HANDSHAKE_TIMEOUT_SECONDS,
    )

    if pid is not None:
        # Verified-live: clean up the sentinel (the runner SHOULD also
        # delete it, but the parent's cleanup is the authoritative one
        # the spec contract guarantees) and return started: true.
        _cleanup_spawn_sentinel(session_dir)
        return {
            "started": True,
            "session_id": session_id,
            "pid": pid,
        }

    # (6) Distinguish runner-died vs timeout. If runner.pid exists at
    # this point, wait_for_pid_file returned None because the liveness
    # probe raised ProcessLookupError — the runner crashed in the first
    # second after writing its PID. Otherwise the file never appeared:
    # terminate the orphan child before returning so a late
    # runner.pid write cannot contradict our started: false answer.
    if pid_path.exists():
        # Runner died. Reap the dead Popen handle so we do not leak a
        # zombie. ``poll()`` is sufficient since the child has exited.
        try:
            child.poll()
        except OSError:
            pass
        # The child also died, but its process-group leader status may
        # have left grandchildren alive. Best-effort group-kill anyway.
        _terminate_orphan_child(child)
        _cleanup_spawn_sentinel(session_dir)
        return {
            "started": False,
            "error_class": "spawn_died",
            "session_id": session_id,
        }

    # Timeout-with-orphan-kill (spec R18 step 7).
    _terminate_orphan_child(child)
    _cleanup_spawn_sentinel(session_dir)
    return {
        "started": False,
        "error_class": "spawn_timeout",
        "session_id": session_id,
    }


def handle_start(args: argparse.Namespace) -> int:
    """Implement ``cortex overnight start``.

    Resolves the home repo, auto-discovers the session state file when
    ``--state`` is absent, derives session-relative paths, and routes
    to one of three branches:

      - ``--dry-run`` PINNED INLINE: takes the existing blocking inline
        path that writes ``DRY-RUN`` lines to the parent's stdout. Tests
        in ``test_runner_pr_gating.py`` (11 assertions on
        ``result.stdout``) depend on the dry-run echoes streaming back
        through the parent process.
      - ``--launchd`` internal flag: takes the inline path because the
        caller IS the runner (a child of the async-spawn fork or
        launcher script) and there is no further fork to perform.
      - default (run-now path): runs the async-spawn handshake and
        returns within :data:`_SPAWN_HANDSHAKE_TIMEOUT_SECONDS`.

    The pre-flight concurrent-runner JSON refusal (R4) runs BEFORE the
    async-spawn fork so a JSON-format consumer always sees a
    ``concurrent_runner`` envelope rather than racing the fork.

    When ``--format json`` is set and the atomic-claim collides with an
    already-alive runner, emits a versioned ``{"error":
    "concurrent_runner", "session_id": "<existing>", ...}`` payload to
    stdout and returns non-zero (R4 / R15). Other failure paths still
    print to stderr; the JSON contract is scoped to the
    concurrent-runner refusal that the MCP plugin needs to discriminate.
    """
    fmt = getattr(args, "format", "human")
    repo_path = _resolve_repo_path()

    if args.state is not None:
        state_path = Path(args.state).expanduser().resolve()
    else:
        sessions_root = repo_path / "cortex/lifecycle" / "sessions"
        discovered = _auto_discover_state(sessions_root)
        if discovered is None:
            print(
                "no overnight session found — create a state file or "
                "pass --state <path>",
                file=sys.stderr,
                flush=True,
            )
            return 1
        state_path = discovered

    if not state_path.exists():
        print(
            f"state file not found: {state_path}",
            file=sys.stderr,
            flush=True,
        )
        return 1

    session_dir = state_path.parent
    plan_path = session_dir / "overnight-plan.md"
    events_path = session_dir / "overnight-events.log"

    # Cross-cancel guard (R14): refuse to start when a scheduled
    # launch is pending for this session, unless ``--force`` is set.
    # The dry-run path is exempt (mirrors the historical contract that
    # dry-run never touches scheduling). The launchd-internal flag is
    # also exempt: by the time the LaunchAgent fires, its own sidecar
    # entry is the schedule that just ran — the runner must NOT
    # cross-cancel-guard itself.
    session_id_for_guard = session_dir.name
    if (
        not getattr(args, "dry_run", False)
        and not getattr(args, "launchd", False)
        and not getattr(args, "force", False)
    ):
        from cortex_command.overnight.scheduler import sidecar as _sidecar

        pending_handle = _sidecar.find_by_session_id(session_id_for_guard)
        if pending_handle is not None:
            message = (
                f"pending schedule for session_id={session_id_for_guard} "
                f"(label={pending_handle.label}, "
                f"scheduled_for_iso={pending_handle.scheduled_for_iso}); "
                f"cancel pending schedule(s) first or use --force"
            )
            if fmt == "json":
                _emit_json(
                    {
                        "error": "pending_schedule",
                        "session_id": session_id_for_guard,
                        "label": pending_handle.label,
                        "scheduled_for_iso": pending_handle.scheduled_for_iso,
                        "message": message,
                    }
                )
            else:
                print(message, file=sys.stderr, flush=True)
            return 1

    # (1) PINNED: the dry-run short-circuit takes the existing inline
    # path. The 11 ``test_runner_pr_gating.py`` assertions depend on
    # ``DRY-RUN`` lines streaming to ``result.stdout`` from the parent
    # subprocess — the async-spawn fork would redirect them into the
    # child's per-session stdout log instead.
    if getattr(args, "dry_run", False):
        return _run_runner_inline(
            state_path=state_path,
            session_dir=session_dir,
            repo_path=repo_path,
            plan_path=plan_path,
            events_path=events_path,
            args=args,
        )

    # (2) PINNED: the JSON-format concurrent-runner refusal MUST run
    # before the async-spawn fork. ``test_cli_overnight_format_json.py``
    # prepopulates a live runner.pid to trigger this branch and depends
    # on ordering. The check mirrors
    # :func:`runner._check_concurrent_start` semantics: only treat
    # verifiably-alive PIDs as a collision; stale PIDs fall through and
    # let runner.run self-heal in the spawned child.
    if fmt == "json":
        existing_pid_data = ipc.read_runner_pid(session_dir)
        if (
            existing_pid_data is not None
            and ipc.verify_runner_pid(existing_pid_data)
        ):
            existing_session_id = existing_pid_data.get("session_id", "")
            existing_pid = existing_pid_data.get("pid")
            payload: dict = {
                "error": "concurrent_runner",
                "session_id": (
                    existing_session_id
                    if isinstance(existing_session_id, str)
                    else ""
                ),
            }
            if isinstance(existing_pid, int):
                payload["existing_pid"] = existing_pid
            _emit_json(payload)
            return 1

    # (8) ``--launchd``: the caller IS the runner. The async-spawn fork
    # in :func:`_spawn_runner_async` re-invokes the CLI with this flag
    # set so the child takes the inline path without performing yet
    # another fork. The launcher script (Task 3) sets this flag too.
    if getattr(args, "launchd", False):
        return _run_runner_inline(
            state_path=state_path,
            session_dir=session_dir,
            repo_path=repo_path,
            plan_path=plan_path,
            events_path=events_path,
            args=args,
        )

    # Default run-now path: async-spawn with liveness handshake.
    result = _spawn_runner_async(
        state_path=state_path,
        session_dir=session_dir,
        repo_path=repo_path,
        args=args,
    )

    if fmt == "json":
        _emit_json(result)
    else:
        if result.get("started"):
            print(
                f"overnight session started: {result.get('session_id')} "
                f"(pid={result.get('pid')})"
            )
        else:
            print(
                f"overnight session start failed: "
                f"{result.get('error_class', 'unknown')}",
                file=sys.stderr,
                flush=True,
            )

    return 0 if result.get("started") else 1


# ---------------------------------------------------------------------------
# status (R2)
# ---------------------------------------------------------------------------

def _latest_state_path(lifecycle_sessions_root: Path) -> Optional[Path]:
    """Return the most-recently-modified ``overnight-state.json`` path."""
    if not lifecycle_sessions_root.exists():
        return None
    candidates = sorted(
        (
            p
            for p in lifecycle_sessions_root.glob("*/overnight-state.json")
            if not p.parent.is_symlink()
        ),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def handle_status(args: argparse.Namespace) -> int:
    """Implement ``cortex overnight status``.

    Reads the active-session pointer; falls back to the most-recent
    session under ``cortex/lifecycle/sessions/`` when the pointer is absent or
    points at a completed session. For human format, delegates to
    :func:`status_module.render_status`; for JSON format, emits an
    object with ``session_id``, ``phase``, ``current_round``, ``features``.

    When ``runner.spawn-pending`` exists in the resolved session_dir
    AND ``runner.pid`` does not, the phase is reported as ``starting``
    (Task 6 / spec R18) — covers the brief async-spawn handshake window
    between the CLI sentinel write and the runner's own PID claim.
    """
    fmt = args.format

    # Check the active-session pointer first.
    active = ipc.read_active_session()
    active_usable = (
        active is not None
        and active.get("phase") != "complete"
        and active.get("session_dir")
    )

    if active_usable:
        session_dir = Path(str(active["session_dir"]))
        state_path = session_dir / "overnight-state.json"
        if not state_path.exists():
            active_usable = False

    if not active_usable:
        # Fall back to most-recent session, using either override or CWD.
        if args.session_dir is not None:
            override_dir = Path(args.session_dir).expanduser().resolve()
            state_path = override_dir / "overnight-state.json"
            if not state_path.exists():
                if fmt == "json":
                    print(json.dumps({"active": False}))
                else:
                    print("No active session")
                return 0
        else:
            repo_path = _resolve_repo_path()
            sessions_root = repo_path / "cortex/lifecycle" / "sessions"
            latest = _latest_state_path(sessions_root)
            if latest is None:
                if fmt == "json":
                    print(json.dumps({"active": False}))
                else:
                    print("No active session")
                return 0
            state_path = latest

    # Detect the async-spawn handshake window: spawn-pending sentinel
    # written by the parent CLI is still present and runner.pid has
    # not yet appeared. ``cortex overnight status`` reports
    # ``phase: starting`` so consumers (the MCP plugin, operators) can
    # distinguish "runner has not yet acked the spawn" from a
    # genuinely stuck or failed session.
    resolved_session_dir = state_path.parent
    starting_window = (
        (resolved_session_dir / _SPAWN_PENDING_SENTINEL).exists()
        and not (resolved_session_dir / "runner.pid").exists()
    )

    # Scan sibling session dirs for scheduled-fire-failed.json markers
    # (Task 12, spec §R13). The lifecycle root is the parent of the
    # sessions root; resolve it from the current state_path's grandparent
    # (state_path is always <state_root>/sessions/<session_id>/overnight-state.json).
    state_root_for_scan = resolved_session_dir.parent.parent
    fire_failures = fail_markers_module.scan_session_dirs(state_root_for_scan)

    # Emit status.
    if fmt == "json":
        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            print(json.dumps({"active": False}))
            return 0
        phase_value = "starting" if starting_window else data.get("phase", "")
        scheduled_start = data.get("scheduled_start")
        payload = {
            "session_id": data.get("session_id", ""),
            "phase": phase_value,
            "current_round": data.get("current_round", 0),
            "features": data.get("features", {}),
            "scheduled_start": (
                scheduled_start if isinstance(scheduled_start, str) else None
            ),
            "fire_failures": [f.to_dict() for f in fire_failures],
        }
        print(json.dumps(payload))
        return 0

    # Human format: delegate to status_module for the display logic.
    # Also surface scheduled_start (Task 7): this is the observability
    # hook the schedule path now writes; without rendering it here the
    # field is invisible to operators.
    try:
        status_module.render_status()
    except Exception as exc:
        print(f"Error reading status: {exc}", file=sys.stderr, flush=True)
        return 1

    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    scheduled_start = data.get("scheduled_start")
    if isinstance(scheduled_start, str) and scheduled_start:
        print(f"Scheduled fire: {scheduled_start}")

    # Surface scheduled-fire failures (Task 12, spec §R13). One-line
    # summary pointing the user at the full marker via `cortex overnight
    # logs` or the absolute marker path on disk.
    if fire_failures:
        n = len(fire_failures)
        latest_marker = (
            Path(fire_failures[-1].session_dir) / "scheduled-fire-failed.json"
        )
        print(
            f"⚠ Recent scheduled-fire failures: {n} "
            f"(run `cortex overnight logs` or see `{latest_marker}` for details)"
        )
    return 0


# ---------------------------------------------------------------------------
# cancel (R3)
# ---------------------------------------------------------------------------

def _resolve_cancel_target(
    args: argparse.Namespace,
    repo_path: Path,
) -> tuple[Optional[Path], Optional[str]]:
    """Resolve the session directory for a cancel/logs invocation.

    Precedence:
        1. ``--session-dir`` override — treated as a full path; the
           basename is validated as a session-id for containment.
        2. Positional ``session_id`` — resolved against
           ``repo_path / "cortex/lifecycle" / "sessions"`` with R17 regex +
           realpath containment via
           :func:`session_validation.resolve_session_dir`.
        3. Active-session pointer.

    Returns ``(session_dir, error_message)``. ``error_message`` is
    ``None`` when resolution succeeded.
    """
    if args.session_dir is not None:
        override = Path(args.session_dir).expanduser().resolve()
        session_id = override.name
        try:
            session_validation.validate_session_id(session_id)
        except ValueError:
            return (None, "invalid session id")
        return (override, None)

    positional_id = getattr(args, "session_id", None)
    if positional_id is not None:
        lifecycle_sessions_root = repo_path / "cortex/lifecycle" / "sessions"
        try:
            session_dir = session_validation.resolve_session_dir(
                positional_id, lifecycle_sessions_root
            )
        except ValueError:
            return (None, "invalid session id")
        return (session_dir, None)

    # Fall back to active-session pointer.
    active = ipc.read_active_session()
    if active is None:
        return (None, "no active session")
    session_dir_str = active.get("session_dir")
    session_id = active.get("session_id")
    if not isinstance(session_dir_str, str) or not isinstance(session_id, str):
        return (None, "no active session")

    try:
        session_validation.validate_session_id(session_id)
    except ValueError:
        return (None, "invalid session id")

    session_dir = Path(session_dir_str)
    return (session_dir, None)


def _cancel_error(fmt: str, code: str, message: str) -> int:
    """Emit a cancel-error per the requested format and return exit code 1.

    For ``human``, prints ``message`` to stderr (preserves the existing
    stderr text contract). For ``json``, emits a versioned ``{"error":
    code, ...}`` payload to stdout per R5/R15.
    """
    if fmt == "json":
        _emit_json({"error": code, "message": message})
    else:
        print(message, file=sys.stderr, flush=True)
    return 1


def _cancel_scheduled_launch(
    fmt: str,
    session_id: str,
    session_dir: Path,
) -> int:
    """Cancel a pending scheduled launch for ``session_id``.

    Resolution: looks up the sidecar entry via
    :func:`sidecar.find_by_session_id`. If found, invokes the macOS
    backend's :meth:`cancel` (which performs ``launchctl bootout``,
    sidecar entry removal, plist + launcher unlink under the schedule
    lock), then clears ``scheduled_start`` from the session state file
    via the existing atomic :func:`state.save_state` helper.

    Returns 0 on successful cancel; non-zero with an error envelope
    when no sidecar entry matches.
    """
    from cortex_command.overnight import state as state_module
    from cortex_command.overnight.scheduler import get_backend
    from cortex_command.overnight.scheduler import sidecar as _sidecar

    handle = _sidecar.find_by_session_id(session_id)
    if handle is None:
        return _cancel_error(
            fmt,
            "no_active_session",
            "no active session",
        )

    backend = get_backend()
    if not backend.is_supported():
        return _cancel_error(
            fmt,
            "unsupported_platform",
            "cortex overnight scheduling requires macOS",
        )

    try:
        result = backend.cancel(handle.label)
    except Exception as exc:  # noqa: BLE001 — surface uniformly
        return _cancel_error(fmt, "cancel_failed", f"cancel failed: {exc}")

    # Clear scheduled_start in the session state file (best-effort).
    state_path = session_dir / "overnight-state.json"
    if state_path.exists():
        try:
            st = state_module.load_state(state_path)
            st.scheduled_start = None
            state_module.save_state(st, state_path)
        except (OSError, json.JSONDecodeError, KeyError) as exc:
            print(
                f"warning: scheduled_start state clear failed: {exc}",
                file=sys.stderr,
                flush=True,
            )

    if fmt == "json":
        _emit_json(
            {
                "cancelled": True,
                "session_id": session_id,
                "label": result.label,
                "bootout_exit_code": result.bootout_exit_code,
                "sidecar_removed": result.sidecar_removed,
                "plist_removed": result.plist_removed,
                "launcher_removed": result.launcher_removed,
                "kind": "scheduled",
            }
        )
    else:
        print(f"cancelled scheduled launch: {session_id} (label={result.label})")
    return 0


def _list_active_and_scheduled(fmt: str) -> int:
    """Implement ``cortex overnight cancel --list``.

    Reads the sidecar for pending schedules and the active-session
    pointer for the running runner (if any), prints both, and returns
    0. Never cancels.
    """
    from cortex_command.overnight.scheduler import sidecar as _sidecar

    schedules = _sidecar.read_sidecar()

    active_runner: Optional[dict] = None
    active_pointer = ipc.read_active_session()
    if active_pointer is not None:
        sd_str = active_pointer.get("session_dir")
        if isinstance(sd_str, str):
            sd = Path(sd_str)
            pid_data = ipc.read_runner_pid(sd)
            if pid_data is not None and ipc.verify_runner_pid(pid_data):
                active_runner = {
                    "session_id": (
                        pid_data.get("session_id")
                        if isinstance(pid_data.get("session_id"), str)
                        else ""
                    ),
                    "pid": pid_data.get("pid"),
                    "session_dir": sd_str,
                }

    if fmt == "json":
        _emit_json(
            {
                "active_runner": active_runner,
                "scheduled": [
                    {
                        "label": h.label,
                        "session_id": h.session_id,
                        "scheduled_for_iso": h.scheduled_for_iso,
                        "created_at_iso": h.created_at_iso,
                        "plist_path": str(h.plist_path),
                    }
                    for h in schedules
                ],
            }
        )
        return 0

    if active_runner is not None:
        print("Active runner:")
        print(
            f"  session_id={active_runner['session_id']} "
            f"pid={active_runner['pid']}"
        )
    else:
        print("Active runner: (none)")

    if schedules:
        print("Scheduled launches:")
        for h in schedules:
            print(
                f"  session_id={h.session_id}  label={h.label}  "
                f"scheduled_for_iso={h.scheduled_for_iso}"
            )
    else:
        print("Scheduled launches: (none)")
    return 0


def handle_cancel(args: argparse.Namespace) -> int:
    """Implement ``cortex overnight cancel``.

    Resolves the session dir, validates the session-id, reads the
    per-session ``runner.pid`` file, verifies ``magic`` + ``start_time``
    before signalling, and sends SIGTERM to the recorded process group.
    Stale PIDs trigger a self-heal (clear pid + pointer) and exit
    nonzero with ``stale lock cleared — session was not running`` on
    stderr, per the R3/R18 + edge-case-line-234 contract.

    Task 7 extension: also handles pending scheduled launches. When the
    resolved session has no active runner-pid but DOES have a sidecar
    entry, cancels the schedule via the macOS backend (``launchctl
    bootout`` + plist/launcher/sidecar removal) and clears
    ``scheduled_start`` from the state file. With ``--list``, prints
    both active runners and pending schedules without canceling
    anything.

    When ``args.session_dir`` is provided, the session-id is the
    directory's ``name`` and containment is asserted against the parent.

    When ``--format json`` is set (R5), every result emits a versioned
    JSON payload to stdout: success is ``{"version": "1.0", "cancelled":
    true, "session_id": ...}``; failures emit ``{"version": "1.0",
    "error": <code>, "message": ...}`` with non-zero exit.
    """
    fmt = getattr(args, "format", "human")

    # ``--list`` short-circuits before any session-id resolution.
    if getattr(args, "list_only", False):
        return _list_active_and_scheduled(fmt)

    # Validate positional session-id up-front so R3 acceptance tests
    # (`cortex overnight cancel "; rm -rf ~"` and
    # `cortex overnight cancel "../../../etc"`) exit with the expected
    # stderr message before any filesystem work.
    positional_id = getattr(args, "session_id", None)
    if positional_id is not None:
        try:
            session_validation.validate_session_id(positional_id)
        except ValueError:
            return _cancel_error(fmt, "invalid_session_id", "invalid session id")

    if args.session_dir is not None:
        # Basename must pass the session-id regex for path-containment
        # confidence; full realpath containment is checked below when we
        # resolve through session_validation.resolve_session_dir.
        candidate_id = Path(str(args.session_dir)).name
        try:
            session_validation.validate_session_id(candidate_id)
        except ValueError:
            return _cancel_error(fmt, "invalid_session_id", "invalid session id")

    repo_path = _resolve_repo_path()
    session_dir, err = _resolve_cancel_target(args, repo_path)
    if err is not None:
        # If no active runner could be located via the takeover-target
        # resolver but the caller passed a positional session_id, fall
        # through to the sidecar lookup — the user may be canceling a
        # pending scheduled launch on a session that has never had a
        # live runner.
        if (
            err == "no active session"
            and getattr(args, "session_id", None) is not None
        ):
            sched_session_id = str(args.session_id)
            sched_dir = (
                repo_path / "cortex/lifecycle" / "sessions" / sched_session_id
            )
            return _cancel_scheduled_launch(fmt, sched_session_id, sched_dir)
        code = "invalid_session_id" if err == "invalid session id" else "no_active_session"
        return _cancel_error(fmt, code, err)

    assert session_dir is not None  # for type-checkers

    # Serialize the read-verify-act critical section against concurrent
    # starters/takers via the per-session takeover lock. The --force
    # escape hatch skips the acquire for wedged-holder scenarios. Tests
    # construct argparse.Namespace directly and may omit ``force``, so
    # default-via-hasattr before reading ``args.force`` literally.
    if not hasattr(args, "force"):
        args.force = False
    try:
        lock_fd = None if args.force else ipc._acquire_takeover_lock(session_dir)
    except ipc.ConcurrentRunnerLockTimeoutError as exc:
        return _cancel_error(fmt, "lock_timeout", str(exc))

    try:
        pid_data = ipc.read_runner_pid(session_dir)
        if pid_data is None:
            # No live runner-pid — fall through to the sidecar path so
            # we can cancel a pending scheduled launch for this session.
            session_id_for_sched = session_dir.name
            return _cancel_scheduled_launch(
                fmt, session_id_for_sched, session_dir
            )

        if not ipc.verify_runner_pid(pid_data):
            # Self-heal stale state (spec Edge Cases line 234).
            # Pass the verified-stale session_id so a takeover that wrote a
            # new claim between our verify and clear is rejected by CAS.
            stale_session_id = pid_data.get("session_id")
            try:
                ipc.clear_runner_pid(session_dir, expected_session_id=stale_session_id)
            except OSError:
                pass
            try:
                ipc.clear_active_session()
            except OSError:
                pass
            return _cancel_error(
                fmt,
                "stale_lock_cleared",
                "stale lock cleared — session was not running",
            )

        pgid = pid_data.get("pgid")
        if not isinstance(pgid, int):
            return _cancel_error(fmt, "no_active_session", "no active session")

        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            # Race: the PGID died between verify and signal. Self-heal.
            # Pass the verified session_id so CAS rejects if a takeover
            # wrote a new claim between our verify and clear.
            verified_session_id = pid_data.get("session_id")
            try:
                ipc.clear_runner_pid(session_dir, expected_session_id=verified_session_id)
            except OSError:
                pass
            try:
                ipc.clear_active_session()
            except OSError:
                pass
            return _cancel_error(
                fmt,
                "stale_lock_cleared",
                "stale lock cleared — session was not running",
            )
        except PermissionError as exc:
            return _cancel_error(fmt, "cancel_failed", f"cancel failed: {exc}")

        if fmt == "json":
            session_id = pid_data.get("session_id") if isinstance(pid_data, dict) else None
            payload: dict = {
                "cancelled": True,
                "session_id": session_id if isinstance(session_id, str) else "",
                "pgid": pgid,
            }
            _emit_json(payload)
        return 0
    finally:
        if lock_fd is not None:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            finally:
                os.close(lock_fd)


# ---------------------------------------------------------------------------
# logs (R4)
# ---------------------------------------------------------------------------

def _logs_error(fmt: str, code: str, message: str) -> int:
    """Emit a logs-error per the requested format and return exit code 1.

    For ``human``, prints ``message`` to stderr (preserves the existing
    stderr text contract). For ``json``, emits a versioned ``{"error":
    code, ...}`` payload to stdout per R5/R15.
    """
    if fmt == "json":
        _emit_json({"error": code, "message": message})
    else:
        print(message, file=sys.stderr, flush=True)
    return 1


def handle_logs(args: argparse.Namespace) -> int:
    """Implement ``cortex overnight logs``.

    Resolves the session dir, computes the log path via
    :data:`logs_module.LOG_FILES` (all streams — events, agent-activity,
    and escalations — are per-session), dispatches to
    :func:`logs_module.read_log`, prints lines to stdout, and emits a
    ``next_cursor: @<int>`` trailer on stderr.

    When ``--format json`` is set (R5), the entire result becomes a
    single versioned JSON object on stdout: ``{"version": "1.0",
    "lines": [...], "next_cursor": "@<int>", "files": ...}``. Failures
    emit ``{"version": "1.0", "error": <code>, "message": ...}`` with
    non-zero exit.
    """
    fmt = getattr(args, "format", "human")

    # Validate positional session-id up-front.
    positional_id = getattr(args, "session_id", None)
    if positional_id is not None:
        try:
            session_validation.validate_session_id(positional_id)
        except ValueError:
            return _logs_error(fmt, "invalid_session_id", "invalid session id")

    # Session-id validation / containment when --session-dir is passed.
    if args.session_dir is not None:
        candidate_id = Path(str(args.session_dir)).name
        try:
            session_validation.validate_session_id(candidate_id)
        except ValueError:
            return _logs_error(fmt, "invalid_session_id", "invalid session id")

    # Resolve session directory: --session-dir override > positional
    # session_id > active-session pointer.
    if args.session_dir is not None:
        session_dir = Path(args.session_dir).expanduser().resolve()
    elif positional_id is not None:
        repo_path = _resolve_repo_path()
        lifecycle_sessions_root = repo_path / "cortex/lifecycle" / "sessions"
        try:
            session_dir = session_validation.resolve_session_dir(
                positional_id, lifecycle_sessions_root
            )
        except ValueError:
            return _logs_error(fmt, "invalid_session_id", "invalid session id")
    else:
        active = ipc.read_active_session()
        if active is None or not isinstance(
            active.get("session_dir"), str
        ):
            return _logs_error(fmt, "no_active_session", "no active session")
        session_dir = Path(str(active["session_dir"]))

    # Compute log path. All streams — events, agent-activity, and
    # escalations — are per-session (R19).
    log_path = session_dir / logs_module.LOG_FILES[args.files]

    try:
        lines, next_offset = logs_module.read_log(
            log_path=log_path,
            since=args.since,
            tail=args.tail,
            limit=args.limit,
        )
    except ValueError as exc:
        return _logs_error(fmt, "invalid_cursor", f"invalid cursor: {exc}")

    if fmt == "json":
        _emit_json(
            {
                "lines": lines,
                "next_cursor": f"@{next_offset}",
                "files": args.files,
            }
        )
        return 0

    for line in lines:
        print(line)

    # Emit next_cursor trailer on stderr per R11.
    print(f"next_cursor: @{next_offset}", file=sys.stderr, flush=True)
    return 0


# ---------------------------------------------------------------------------
# list-sessions (MCP support verb)
# ---------------------------------------------------------------------------

# Phases that count as "active" (i.e. not terminated).
_ACTIVE_PHASES = frozenset({"planning", "executing", "paused"})


def _list_sessions_state_paths(sessions_root: Path) -> list[Path]:
    """Return all per-session ``overnight-state.json`` paths sorted by mtime desc.

    Skips paths whose parent directory is a symlink (e.g.
    ``latest-overnight``) so the linked target is not double-counted.
    """
    if not sessions_root.exists():
        return []
    candidates = [
        p
        for p in sessions_root.glob("*/overnight-state.json")
        if not p.parent.is_symlink()
    ]
    try:
        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        pass
    return candidates


def _summarize_state(data: dict) -> dict:
    """Return the compact session-summary dict used in list-sessions output."""
    return {
        "session_id": str(data.get("session_id", "")),
        "phase": str(data.get("phase", "")),
        "started_at": data.get("started_at"),
        "updated_at": data.get("updated_at"),
        "integration_branch": data.get("integration_branch"),
    }


def _parse_iso8601(value: Optional[str]):
    """Best-effort ISO-8601 parse; returns ``None`` on failure."""
    from datetime import datetime as _dt

    if not isinstance(value, str):
        return None
    try:
        return _dt.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def handle_list_sessions(args: argparse.Namespace) -> int:
    """Implement ``cortex overnight list-sessions``.

    Globs ``cortex/lifecycle/sessions/*/overnight-state.json``, partitions
    results into active (``planning`` / ``executing`` / ``paused``) and
    recent (``complete``), and applies optional ``status`` / ``since`` /
    ``limit`` filters. Pagination cursors are reserved for a future
    expansion — v1 returns ``next_cursor: null`` and relies on
    ``--limit`` for the default 10-item recent slice.

    When ``--format json`` is set, emits a versioned envelope:

        {"version": "1.0", "active": [...], "recent": [...],
         "total_count": N, "next_cursor": null}
    """
    fmt = getattr(args, "format", "human")
    repo_path = _resolve_repo_path()
    sessions_root = repo_path / "cortex/lifecycle" / "sessions"

    paths = _list_sessions_state_paths(sessions_root)

    status_filter = (
        set(args.status) if getattr(args, "status", None) else None
    )
    since_dt = _parse_iso8601(getattr(args, "since", None))

    active: list[dict] = []
    recent: list[dict] = []

    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue

        phase = data.get("phase")
        if status_filter is not None and phase not in status_filter:
            continue
        if since_dt is not None:
            updated_dt = _parse_iso8601(data.get("updated_at"))
            if updated_dt is None or updated_dt < since_dt:
                continue

        summary = _summarize_state(data)
        if phase in _ACTIVE_PHASES:
            active.append(summary)
        else:
            recent.append(summary)

    limit = getattr(args, "limit", 10)
    if not isinstance(limit, int) or limit < 0:
        limit = 0
    total_count = len(active) + len(recent)
    recent_limited = recent[:limit]

    if fmt == "json":
        _emit_json(
            {
                "active": active,
                "recent": recent_limited,
                "total_count": total_count,
                "next_cursor": None,
            }
        )
        return 0

    # Human format: simple summary.
    if not active and not recent_limited:
        print("No overnight sessions found")
        return 0
    if active:
        print("Active sessions:")
        for entry in active:
            print(
                f"  {entry['session_id']}  phase={entry['phase']}  "
                f"updated_at={entry.get('updated_at')}"
            )
    if recent_limited:
        print("Recent sessions:")
        for entry in recent_limited:
            print(
                f"  {entry['session_id']}  phase={entry['phase']}  "
                f"updated_at={entry.get('updated_at')}"
            )
    print(f"total: {total_count}")
    return 0


# ---------------------------------------------------------------------------
# schedule (R1) — macOS LaunchAgent-backed scheduling
# ---------------------------------------------------------------------------

# Maximum age of the ``runner.spawn-pending`` sentinel file before it is
# treated as stale. The async-spawn handshake budget is 5 seconds (see
# :data:`_SPAWN_HANDSHAKE_TIMEOUT_SECONDS`); we allow a generous 30-second
# window so brief clock skew or filesystem latency cannot turn a fresh
# sentinel into a false-stale read.
_SPAWN_PENDING_SENTINEL_MAX_AGE_SECONDS: float = 30.0


def _check_no_active_runner(session_dir: Path) -> bool:
    """Return True if no runner is active and no spawn is pending (R14).

    Performs two checks in sequence:

      1. ``runner.pid`` exists AND :func:`ipc.verify_runner_pid` confirms
         the recorded process is alive — the canonical "runner active"
         signal.
      2. ``runner.spawn-pending`` sentinel exists AND its mtime is within
         :data:`_SPAWN_PENDING_SENTINEL_MAX_AGE_SECONDS` — closes the
         5-second handshake gap between the parent CLI's sentinel write
         and the runner's own ``runner.pid`` claim. Sentinels older than
         the threshold are ignored (treated as orphan from a crashed
         spawn) so a stale file does not block scheduling forever.

    Returns:
        ``True`` when neither signal fires (safe to schedule); ``False``
        when a live runner OR a fresh spawn-pending sentinel is detected.
    """
    pid_data = ipc.read_runner_pid(session_dir)
    if pid_data is not None and ipc.verify_runner_pid(pid_data):
        return False

    sentinel_path = session_dir / _SPAWN_PENDING_SENTINEL
    try:
        mtime = sentinel_path.stat().st_mtime
    except FileNotFoundError:
        return True
    except OSError:
        # Conservative: any other stat failure (permission, device error)
        # is treated as "sentinel present" so we do not race past a
        # genuinely-active spawn during transient filesystem hiccups.
        return False

    import time as _time

    age = _time.time() - mtime
    if age <= _SPAWN_PENDING_SENTINEL_MAX_AGE_SECONDS:
        # Fresh spawn-pending — handshake window still in progress.
        return False
    # Sentinel exists but is older than the threshold; treat as orphan.
    return True


def handle_schedule(args: argparse.Namespace) -> int:
    """Implement ``cortex overnight schedule``.

    Sequence (per spec R1, R5, R7, R10):

      1. Validate target time via :func:`scheduler.macos.parse_target_time`
         — emits the spec's exact error phrasings for invalid format,
         past times, Feb-29-in-non-leap-year, and the 7-day ceiling.
      2. Gate on macOS support via ``backend.is_supported()`` —
         non-darwin platforms exit non-zero with
         ``"cortex overnight scheduling requires macOS"``.
      3. Cross-cancel runner-active check via
         :func:`_check_no_active_runner` — Task 7 fills the seam.
      4. Resolve the session_id from the (auto-discovered or
         ``--state``-overridden) state file path; the directory name IS
         the session_id (mirrors :func:`handle_start`).
      5. ``--dry-run`` short-circuits AFTER target-time validation +
         macOS gate but BEFORE the backend ``schedule()`` call: prints
         the would-be label and resolved target ISO, then returns 0.
      6. Otherwise calls ``backend.schedule(...)``, which under the
         hood: GC-passes orphan plists, mints the label, installs the
         launcher script, writes+validates the plist, runs
         ``launchctl bootstrap``, verifies via ``launchctl print``, and
         persists the sidecar entry — all under the schedule-lock from
         Task 4.
      7. ONLY after the backend's ``_write_sidecar_entry`` succeeded
         (which happens inside ``schedule()``), this handler writes
         ``scheduled_start = handle.scheduled_for_iso`` to the session
         state file via the existing atomic
         :func:`state.save_state` helper. This is the observability
         hook ``handle_status`` (Task 7) and the cancel-side clear
         (Task 7) both depend on.
      8. Prints ``session_id``, ``label``, ``scheduled_for_iso`` to
         stdout (or a versioned JSON envelope when ``--format json``).
    """
    fmt = getattr(args, "format", "human")
    target_time_str: str = args.target_time
    dry_run: bool = bool(getattr(args, "dry_run", False))

    # Lazy imports to keep cli.py --help fast (mirrors handle_start).
    from cortex_command.overnight import state as state_module
    from cortex_command.overnight.scheduler import get_backend
    from cortex_command.overnight.scheduler.labels import mint_label
    from cortex_command.overnight.scheduler.macos import parse_target_time

    # (1) Validate target time first. Errors are spec-exact strings.
    try:
        resolved_target = parse_target_time(target_time_str)
    except ValueError as exc:
        message = str(exc)
        if fmt == "json":
            _emit_json({"error": "invalid_target_time", "message": message})
        else:
            print(message, file=sys.stderr, flush=True)
        return 1

    # (2) macOS gate — non-darwin exits with the spec's exact message.
    backend = get_backend()
    if not backend.is_supported():
        message = "cortex overnight scheduling requires macOS"
        if fmt == "json":
            _emit_json({"error": "unsupported_platform", "message": message})
        else:
            print(message, file=sys.stderr, flush=True)
        return 1

    # (3) Resolve repo root + state path so we can derive the session_id.
    repo_path = _resolve_repo_path()

    if args.state is not None:
        state_path = Path(args.state).expanduser().resolve()
    else:
        sessions_root = repo_path / "cortex/lifecycle" / "sessions"
        discovered = _auto_discover_state(sessions_root)
        if discovered is None:
            message = (
                "no overnight session found — create a state file or "
                "pass --state <path>"
            )
            if fmt == "json":
                _emit_json({"error": "no_session", "message": message})
            else:
                print(message, file=sys.stderr, flush=True)
            return 1
        state_path = discovered

    if not state_path.exists():
        message = f"state file not found: {state_path}"
        if fmt == "json":
            _emit_json({"error": "state_not_found", "message": message})
        else:
            print(message, file=sys.stderr, flush=True)
        return 1

    session_dir = state_path.parent
    session_id = session_dir.name

    # (4) Cross-cancel runner-active check (Task 7 fills this seam).
    if not _check_no_active_runner(session_dir):
        message = (
            f"active runner present (session_id={session_id}); "
            f"cancel it first"
        )
        if fmt == "json":
            _emit_json({"error": "active_runner_present", "message": message})
        else:
            print(message, file=sys.stderr, flush=True)
        return 1

    # (5) --dry-run short-circuits before the backend call.
    if dry_run:
        # Mint a would-be label deterministically against the validated
        # session_id. The epoch defaults to ``int(time.time())`` so two
        # sequential dry-runs may differ by a second; this is fine for a
        # preview — the real ``schedule()`` mints its own label.
        try:
            preview_label = mint_label(session_id)
        except ValueError as exc:
            message = f"invalid session id for label: {exc}"
            if fmt == "json":
                _emit_json({"error": "invalid_session_id", "message": message})
            else:
                print(message, file=sys.stderr, flush=True)
            return 1
        scheduled_for_iso = resolved_target.isoformat()
        if fmt == "json":
            _emit_json(
                {
                    "dry_run": True,
                    "session_id": session_id,
                    "label": preview_label,
                    "scheduled_for_iso": scheduled_for_iso,
                }
            )
        else:
            print(f"session_id: {session_id}")
            print(f"label: {preview_label}")
            print(f"scheduled_for_iso: {scheduled_for_iso}")
            print("(dry-run — no LaunchAgent was bootstrapped)")
        return 0

    # (6) Real schedule path. The backend's schedule() does GC + plist
    # render + bootstrap + verify + sidecar write under schedule_lock.
    try:
        handle = backend.schedule(
            target=resolved_target,
            session_id=session_id,
            env=dict(os.environ),
            repo_root=repo_path,
        )
    except Exception as exc:  # noqa: BLE001 — surface backend errors uniformly
        message = f"schedule failed: {exc}"
        if fmt == "json":
            _emit_json({"error": "schedule_failed", "message": message})
        else:
            print(message, file=sys.stderr, flush=True)
        return 1

    # (7) Write scheduled_start to the session state file via the
    # existing atomic helper. Per spec R7, this happens AFTER the
    # backend's _write_sidecar_entry has succeeded — by the time
    # backend.schedule() has returned, the sidecar entry is persisted.
    try:
        st = state_module.load_state(state_path)
        st.scheduled_start = handle.scheduled_for_iso
        state_module.save_state(st, state_path)
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        # Non-fatal: the LaunchAgent is bootstrapped; the observability
        # hook is degraded but the run will still fire. Surface a
        # warning to stderr and continue with the success envelope.
        print(
            f"warning: scheduled_start state write failed: {exc}",
            file=sys.stderr,
            flush=True,
        )

    # (8) Emit the success envelope.
    if fmt == "json":
        _emit_json(
            {
                "scheduled": True,
                "session_id": handle.session_id,
                "label": handle.label,
                "scheduled_for_iso": handle.scheduled_for_iso,
            }
        )
    else:
        print(f"session_id: {handle.session_id}")
        print(f"label: {handle.label}")
        print(f"scheduled_for_iso: {handle.scheduled_for_iso}")
    return 0
