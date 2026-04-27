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
import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Optional

from cortex_command.overnight import ipc
from cortex_command.overnight import logs as logs_module
from cortex_command.overnight import runner as runner_module
from cortex_command.overnight import session_validation
from cortex_command.overnight import status as status_module


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

def handle_start(args: argparse.Namespace) -> int:
    """Implement ``cortex overnight start``.

    Resolves the home repo, auto-discovers the session state file when
    ``--state`` is absent, derives session-relative paths, and hands off
    to :func:`runner_module.run`. Per R20, this is the single site that
    owns user-repo path resolution.

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
        sessions_root = repo_path / "lifecycle" / "sessions"
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

    # Pre-flight concurrent-runner detection so JSON consumers see a
    # structured ``concurrent_runner`` refusal before runner.run prints
    # its stderr-only "session already running" message (R4). The check
    # mirrors :func:`runner._check_concurrent_start` semantics: only
    # treat verifiably-alive PIDs as a collision; stale PIDs fall
    # through and let runner.run self-heal.
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
    session under ``lifecycle/sessions/`` when the pointer is absent or
    points at a completed session. For human format, delegates to
    :func:`status_module.render_status`; for JSON format, emits an
    object with ``session_id``, ``phase``, ``current_round``, ``features``.
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
            sessions_root = repo_path / "lifecycle" / "sessions"
            latest = _latest_state_path(sessions_root)
            if latest is None:
                if fmt == "json":
                    print(json.dumps({"active": False}))
                else:
                    print("No active session")
                return 0
            state_path = latest

    # Emit status.
    if fmt == "json":
        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            print(json.dumps({"active": False}))
            return 0
        payload = {
            "session_id": data.get("session_id", ""),
            "phase": data.get("phase", ""),
            "current_round": data.get("current_round", 0),
            "features": data.get("features", {}),
        }
        print(json.dumps(payload))
        return 0

    # Human format: delegate to status_module for the display logic.
    try:
        status_module.render_status()
    except Exception as exc:
        print(f"Error reading status: {exc}", file=sys.stderr, flush=True)
        return 1
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
           ``repo_path / "lifecycle" / "sessions"`` with R17 regex +
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
        lifecycle_sessions_root = repo_path / "lifecycle" / "sessions"
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


def handle_cancel(args: argparse.Namespace) -> int:
    """Implement ``cortex overnight cancel``.

    Resolves the session dir, validates the session-id, reads the
    per-session ``runner.pid`` file, verifies ``magic`` + ``start_time``
    before signalling, and sends SIGTERM to the recorded process group.
    Stale PIDs trigger a self-heal (clear pid + pointer) and exit
    nonzero with ``stale lock cleared — session was not running`` on
    stderr, per the R3/R18 + edge-case-line-234 contract.

    When ``args.session_dir`` is provided, the session-id is the
    directory's ``name`` and containment is asserted against the parent.

    When ``--format json`` is set (R5), every result emits a versioned
    JSON payload to stdout: success is ``{"version": "1.0", "cancelled":
    true, "session_id": ...}``; failures emit ``{"version": "1.0",
    "error": <code>, "message": ...}`` with non-zero exit.
    """
    fmt = getattr(args, "format", "human")

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
        code = "invalid_session_id" if err == "invalid session id" else "no_active_session"
        return _cancel_error(fmt, code, err)

    assert session_dir is not None  # for type-checkers

    pid_data = ipc.read_runner_pid(session_dir)
    if pid_data is None:
        return _cancel_error(fmt, "no_active_session", "no active session")

    if not ipc.verify_runner_pid(pid_data):
        # Self-heal stale state (spec Edge Cases line 234).
        try:
            ipc.clear_runner_pid(session_dir)
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
        try:
            ipc.clear_runner_pid(session_dir)
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
        lifecycle_sessions_root = repo_path / "lifecycle" / "sessions"
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
