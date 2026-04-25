"""Async handlers for the five Cortex MCP overnight tools.

This module is the stub scaffolding created by Task 11. The handler bodies
are filled in by Tasks 12–15:

* Task 12 — ``overnight_status`` and ``overnight_list_sessions``
* Task 13 — ``overnight_logs`` and the ``MAX_TOOL_FILE_READ_BYTES`` cap
* Task 14 — ``overnight_cancel``
* Task 15 — ``overnight_start_run``

Each handler is an ``async def`` (R29) and takes a Pydantic input model
from :mod:`cortex_command.mcp_server.schema`, returning the matching
output model. The ``build_server()`` factory in
:mod:`cortex_command.mcp_server.server` registers these by name.

No ``print()`` calls are permitted outside ``if __name__ == "__main__"``
guards — stdout is the JSON-RPC stream.
"""

from __future__ import annotations

import asyncio
import glob as _glob
import json
import os
import signal as _signal
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import psutil as _psutil
from mcp.server.fastmcp.exceptions import ToolError

from cortex_command.mcp_server.schema import (
    CancelInput,
    CancelOutput,
    FeatureCounts,
    ListSessionsInput,
    ListSessionsOutput,
    LogsInput,
    LogsOutput,
    SessionSummary,
    StartRunInput,
    StartRunOutput,
    StatusInput,
    StatusOutput,
)
from cortex_command.overnight import cli_handler as _cli_handler
from cortex_command.overnight import ipc as _ipc
from cortex_command.overnight import logs as _logs


_NOT_IMPLEMENTED_MSG = "handler not yet implemented — filled in by Task 12–15"


# ---------------------------------------------------------------------------
# R14: MAX_TOOL_FILE_READ_BYTES cap on file-touching tools
# ---------------------------------------------------------------------------

# Default 256 MiB — the cap defends against (a) accidental whole-file reads
# and (b) a single oversized log line blowing out the tool's output budget.
# Overridable via ``CORTEX_MCP_MAX_FILE_READ_BYTES`` (parsed as int) so
# operators can dial it down in resource-constrained environments.
_DEFAULT_MAX_TOOL_FILE_READ_BYTES = 256 * 1024 * 1024


def _resolve_max_tool_file_read_bytes() -> int:
    """Return the configured max-bytes cap, preferring the env override."""
    raw = os.environ.get("CORTEX_MCP_MAX_FILE_READ_BYTES")
    if raw is None:
        return _DEFAULT_MAX_TOOL_FILE_READ_BYTES
    try:
        return int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_MAX_TOOL_FILE_READ_BYTES


MAX_TOOL_FILE_READ_BYTES = _resolve_max_tool_file_read_bytes()


# Server-side cap for ``overnight_logs``' ``limit`` (spec R5).
_LOGS_LIMIT_SERVER_CAP = 200

# Phases that count as "active" (i.e. not terminated) for
# ``overnight_list_sessions``. ``complete`` is the only terminal phase.
_ACTIVE_PHASES = {"planning", "executing", "paused"}


# ---------------------------------------------------------------------------
# Cancel-tool constants (R6 / Task 14)
# ---------------------------------------------------------------------------

#: Outer SIGTERM-to-SIGKILL window for ``overnight_cancel``. Strictly
#: greater than the runner's in-handler 6 s descendant-tree-walk budget
#: (``runner.DESCENDANT_GRACEFUL_SHUTDOWN_SECONDS``) so the runner's own
#: SIGTERM handler completes its descendant-cleanup phase before any
#: outer SIGKILL escalates against the runner itself.
_CANCEL_GRACEFUL_TIMEOUT_SECONDS: float = 12.0

#: Polling interval for the runner-exit watcher between SIGTERM and the
#: SIGKILL escalation. The poll loop is preferred over a fixed sleep so
#: the common path (runner exits cleanly within a fraction of the
#: budget) does not pay the full timeout.
_CANCEL_POLL_INTERVAL_SECONDS: float = 0.25

#: Post-SIGKILL settle window — SIGKILL cannot be caught, so a runner
#: that is still alive after this brief poll is necessarily SIGSTOP'd
#: or otherwise unkillable from this process's perspective. Distinct
#: from the 12 s graceful budget so the cumulative cancel time stays
#: bounded for the SIGSTOP'd-runner test cases.
_CANCEL_POST_SIGKILL_SETTLE_SECONDS: float = 1.0


# ---------------------------------------------------------------------------
# Blocking helpers — wrapped in ``asyncio.to_thread`` by the async handlers
# ---------------------------------------------------------------------------


def _read_state_file(state_path: Path) -> Optional[dict]:
    """Read and parse ``overnight-state.json``; return ``None`` on error.

    Pure blocking I/O — wrap in ``asyncio.to_thread`` at the call site
    (R29). Returns ``None`` rather than raising so callers can surface a
    structured tool response instead of an exception.
    """
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _discover_active_state_path() -> Optional[Path]:
    """Return the active session's state-file path, or ``None``.

    Reads ``~/.local/share/overnight-sessions/active-session.json`` via
    :func:`cortex_command.overnight.ipc.read_active_session` and joins
    its ``session_dir`` with ``overnight-state.json``.
    """
    active = _ipc.read_active_session()
    if active is None:
        return None
    session_dir_str = active.get("session_dir")
    if not isinstance(session_dir_str, str):
        return None
    return Path(session_dir_str) / "overnight-state.json"


def _resolve_state_path_for_session(session_id: str) -> Path:
    """Return ``lifecycle/sessions/{session_id}/overnight-state.json``.

    Resolves the user's repo via the CLI handler's path resolver so the
    MCP tool and the CLI share a single path-resolution site (R20).
    """
    repo_path = _cli_handler._resolve_repo_path()
    return (
        repo_path
        / "lifecycle"
        / "sessions"
        / session_id
        / "overnight-state.json"
    )


def _feature_counts_from_state(data: dict) -> FeatureCounts:
    """Collapse the features map into the per-status integer totals."""
    counts = {
        "pending": 0,
        "running": 0,
        "merged": 0,
        "paused": 0,
        "deferred": 0,
        "failed": 0,
    }
    features = data.get("features") or {}
    if isinstance(features, dict):
        for entry in features.values():
            if not isinstance(entry, dict):
                continue
            status = entry.get("status")
            if status in counts:
                counts[status] += 1
    return FeatureCounts(**counts)


def _state_to_status_output(data: dict) -> StatusOutput:
    """Build a :class:`StatusOutput` from a parsed state-file dict."""
    return StatusOutput(
        session_id=data.get("session_id"),
        phase=str(data.get("phase", "")),
        current_round=data.get("current_round"),
        started_at=data.get("started_at"),
        updated_at=data.get("updated_at"),
        features=_feature_counts_from_state(data),
        integration_branch=data.get("integration_branch"),
        paused_reason=data.get("paused_reason"),
    )


def _state_to_summary(data: dict) -> SessionSummary:
    """Build a :class:`SessionSummary` from a parsed state-file dict."""
    return SessionSummary(
        session_id=str(data.get("session_id", "")),
        phase=str(data.get("phase", "")),
        started_at=data.get("started_at"),
        updated_at=data.get("updated_at"),
        integration_branch=data.get("integration_branch"),
    )


def _glob_state_paths(sessions_root: Path) -> list[str]:
    """Return all ``lifecycle/sessions/*/overnight-state.json`` paths.

    Uses ``glob.glob`` per R29's wording (the task explicitly calls out
    ``glob.glob`` as one of the blocking sites to wrap). Results are
    returned sorted by mtime descending for stable "most recent first"
    ordering.
    """
    pattern = str(sessions_root / "*" / "overnight-state.json")
    paths = _glob.glob(pattern)
    # Skip sessions whose parent is a symlink (e.g. `latest-overnight`)
    # so we don't double-count the target session.
    filtered = [p for p in paths if not Path(p).parent.is_symlink()]
    try:
        filtered.sort(
            key=lambda p: Path(p).stat().st_mtime, reverse=True
        )
    except OSError:
        pass
    return filtered


def _parse_since(since: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 ``since`` filter; return ``None`` if unparsable."""
    if since is None:
        return None
    try:
        return datetime.fromisoformat(since.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _updated_at_dt(data: dict) -> Optional[datetime]:
    """Best-effort parse of the ``updated_at`` field as a datetime."""
    updated = data.get("updated_at")
    if not isinstance(updated, str):
        return None
    try:
        return datetime.fromisoformat(updated.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _list_sessions_sync(payload: ListSessionsInput) -> ListSessionsOutput:
    """Blocking implementation of :func:`overnight_list_sessions`.

    Globs per-session state files, filters by ``status`` / ``since``,
    partitions into ``active`` / ``recent``, and applies ``limit``. All
    I/O (``glob.glob``, ``open``) runs on the worker thread.
    """
    repo_path = _cli_handler._resolve_repo_path()
    sessions_root = repo_path / "lifecycle" / "sessions"

    paths = _glob_state_paths(sessions_root)
    since_dt = _parse_since(payload.since)
    status_filter = (
        set(payload.status) if payload.status else None
    )

    active: list[SessionSummary] = []
    recent: list[SessionSummary] = []

    for path_str in paths:
        data = _read_state_file(Path(path_str))
        if data is None:
            continue
        phase = data.get("phase")
        if status_filter is not None and phase not in status_filter:
            continue
        if since_dt is not None:
            ts = _updated_at_dt(data)
            if ts is None or ts < since_dt:
                continue
        summary = _state_to_summary(data)
        if phase in _ACTIVE_PHASES:
            active.append(summary)
        else:
            recent.append(summary)

    # Apply limit to the ``recent`` list only (active is always returned
    # in full — the runner-concurrency invariant means there's at most
    # one active session per repo anyway).
    limit = payload.limit if payload.limit is not None else 10
    if limit < 0:
        limit = 0
    total_count = len(active) + len(recent)
    recent_limited = recent[:limit]

    return ListSessionsOutput(
        active=active,
        recent=recent_limited,
        total_count=total_count,
        next_cursor=None,
    )


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------


async def overnight_start_run(payload: StartRunInput) -> StartRunOutput:
    """Spawn the overnight runner. Filled in by Task 15."""

    raise NotImplementedError(_NOT_IMPLEMENTED_MSG)


async def overnight_status(payload: StatusInput) -> StatusOutput:
    """Return overnight session status.

    When ``session_id`` is provided, read the per-session state file
    under ``lifecycle/sessions/{session_id}/overnight-state.json``.
    When it is omitted, fall back to the active-session pointer at
    ``~/.local/share/overnight-sessions/active-session.json``. If neither
    path yields a readable state file, return a
    ``phase="no_active_session"`` sentinel response so the caller sees a
    structured outcome rather than a tool-execution exception.

    All blocking I/O (``open()`` and the active-session read) runs via
    ``asyncio.to_thread`` per R29 so the stdio server stays responsive
    while this coroutine is in flight.
    """

    if payload.session_id is not None:
        state_path = _resolve_state_path_for_session(payload.session_id)
    else:
        state_path = await asyncio.to_thread(_discover_active_state_path)
        if state_path is None:
            return StatusOutput(session_id=None, phase="no_active_session")

    data = await asyncio.to_thread(_read_state_file, state_path)
    if data is None:
        return StatusOutput(
            session_id=payload.session_id, phase="no_active_session"
        )

    return _state_to_status_output(data)


def _parse_log_line(line: str) -> dict[str, Any]:
    """Parse a log line as JSON; fall back to ``{"raw": line}`` on failure.

    Events / agent-activity / escalations are all JSONL — a failed parse
    means a malformed or partial line. Surface the raw text under a
    ``raw`` key so the client still sees *something* and a grep for
    ``"raw"`` in the response reveals a parse problem.
    """
    try:
        obj = json.loads(line)
    except (ValueError, TypeError):
        return {"raw": line}
    if not isinstance(obj, dict):
        return {"raw": line}
    return obj


def _read_log_for_session(
    session_dir: Path,
    file_key: str,
    cursor: Optional[str],
    tail: Optional[int],
    limit: int,
    max_bytes: int,
) -> dict:
    """Blocking wrapper around :func:`logs.read_log_structured`.

    Maps ``file_key`` (one of ``events`` / ``agent-activity`` /
    ``escalations``) to its per-session filename via
    :data:`logs.LOG_FILES`.
    """
    log_path = session_dir / _logs.LOG_FILES[file_key]
    return _logs.read_log_structured(
        log_path=log_path,
        cursor=cursor,
        tail=tail,
        limit=limit,
        max_bytes=max_bytes,
    )


async def overnight_logs(payload: LogsInput) -> LogsOutput:
    """Return paginated log lines for one or more per-session log streams.

    Reads ``lifecycle/sessions/{session_id}/<file>`` for each file in
    ``payload.files`` (events / agent-activity / escalations) using the
    opaque cursor codec from :mod:`cortex_command.overnight.cursor` and
    the ``MAX_TOOL_FILE_READ_BYTES`` cap (R14). Surfaces
    ``cursor_invalid`` / ``oversized_line`` / ``truncated`` /
    ``original_line_bytes`` flags directly from
    :func:`logs.read_log_structured`.

    Edge cases:
    * ``session_id`` not found → raises :class:`ToolError` with a
      structured-JSON body ``{error: "session_not_found", session_id}``
      so the MCP client receives an ``isError: true`` Tool Execution
      Error per SEP-1303 (spec Edge Cases).
    * Invalid cursor → ``ValueError`` from the codec propagates as a
      :class:`ToolError` with the reason embedded.

    R29: all blocking I/O (``Path.exists``, ``Path.stat``, file reads)
    runs on a worker thread via :func:`asyncio.to_thread`.
    """

    repo_path = _cli_handler._resolve_repo_path()
    session_dir = (
        repo_path / "lifecycle" / "sessions" / payload.session_id
    )

    # R5 Edge Case: session_not_found surfaces as a Tool Execution Error
    # (``isError: true``) rather than a JSON-RPC protocol error.
    if not await asyncio.to_thread(session_dir.is_dir):
        raise ToolError(
            json.dumps(
                {
                    "error": "session_not_found",
                    "session_id": payload.session_id,
                }
            )
        )

    # Server-cap limit at 200 regardless of request value (R5).
    effective_limit = max(1, min(payload.limit, _LOGS_LIMIT_SERVER_CAP))

    aggregated_lines: list[dict[str, Any]] = []
    next_cursor: Optional[str] = None
    eof_flags: list[bool] = []
    oversized_line_seen = False
    original_line_bytes_seen: Optional[int] = None

    for file_key in payload.files:
        try:
            result = await asyncio.to_thread(
                _read_log_for_session,
                session_dir,
                file_key,
                payload.cursor,
                payload.tail,
                effective_limit,
                MAX_TOOL_FILE_READ_BYTES,
            )
        except ValueError as exc:
            # Malformed cursor — surface as Tool Execution Error.
            raise ToolError(f"invalid cursor: {exc}") from exc

        # R11: cursor_invalid short-circuits — drop accumulated lines
        # and return the empty-lines + null-cursor signal so the client
        # re-baselines.
        if result.get("cursor_invalid"):
            return LogsOutput(
                lines=[],
                next_cursor=None,
                eof=False,
                cursor_invalid=True,
            )

        for raw_line in result.get("lines", []):
            aggregated_lines.append(_parse_log_line(raw_line))

        if result.get("next_cursor") is not None:
            next_cursor = result["next_cursor"]
        eof_flags.append(bool(result.get("eof")))

        if result.get("oversized_line"):
            oversized_line_seen = True
            original_line_bytes_seen = result.get("original_line_bytes")

    eof = all(eof_flags) if eof_flags else True

    return LogsOutput(
        lines=aggregated_lines,
        next_cursor=next_cursor,
        eof=eof,
        cursor_invalid=None,
        oversized_line=True if oversized_line_seen else None,
        truncated=None,
        original_line_bytes=original_line_bytes_seen,
    )


def _classify_verify_failure(pid_data: dict) -> str:
    """Return the reason a ``runner.pid`` payload failed verification.

    Mirrors the structural checks in
    :func:`cortex_command.overnight.ipc.verify_runner_pid` but, instead
    of collapsing every failure into a single ``False``, distinguishes
    the cancel-tool's contract reasons. Returns one of:

    * ``"magic_mismatch"`` — payload not a dict, missing magic field, or
      schema_version outside the known range.
    * ``"start_time_skew"`` — magic + schema match but the recorded
      start_time does not match the live process create_time within the
      tolerance, the PID has been recycled, or the PID is gone (R6 Edge
      Cases line 234 maps the no-such-process case to the magic-stale
      branch — but our caller checks runner liveness before this is
      reached, so a no-such-process here means PID reuse mid-cancel).

    The cancel handler must have already ruled out ``no_runner_pid``
    before invoking this helper.
    """

    if not isinstance(pid_data, dict):
        return "magic_mismatch"
    if pid_data.get("magic") != _ipc._RUNNER_MAGIC:
        return "magic_mismatch"
    schema_version = pid_data.get("schema_version")
    if (
        not isinstance(schema_version, int)
        or schema_version < 1
        or schema_version > _ipc.MAX_KNOWN_RUNNER_PID_SCHEMA_VERSION
    ):
        return "magic_mismatch"
    # Anything else (bad pid type, bad start_time, no such process,
    # access denied, start_time tolerance miss) is bucketed under
    # ``start_time_skew``: the IPC contract identifies the runner, but
    # the recorded process is no longer the one we expect.
    return "start_time_skew"


def _is_pid_running(pid: int) -> bool:
    """Return ``True`` while the PID resolves to a live, non-zombie process.

    ``psutil.Process(pid).is_running()`` returns ``True`` for zombie
    processes (the PID is still in the kernel's process table even
    though the program has exited and is awaiting reap). For the
    cancel-tool's exit-watcher contract, a zombie has effectively
    "exited" — its work is done, the runner.pid lock can be cleared,
    and a fresh ``overnight_start_run`` can claim the slot. This helper
    therefore treats ``STATUS_ZOMBIE`` as not-running.

    Wrapped (alongside the polling sleep) inside ``asyncio.to_thread``
    by the cancel handler per R29.
    """
    try:
        proc = _psutil.Process(pid)
        if not proc.is_running():
            return False
        try:
            if proc.status() == _psutil.STATUS_ZOMBIE:
                return False
        except (_psutil.NoSuchProcess, _psutil.AccessDenied):
            return False
        return True
    except (_psutil.NoSuchProcess, _psutil.AccessDenied):
        return False
    except Exception:
        return False


async def _wait_for_pid_exit(pid: int, deadline_seconds: float) -> bool:
    """Poll ``psutil.Process(pid).is_running()`` until exit or deadline.

    Returns ``True`` if the process exited within the budget, ``False``
    otherwise. The polling step (``_psutil.Process(...).is_running()``)
    is dispatched via ``asyncio.to_thread`` per R29 so the stdio MCP
    server's event loop is never blocked.
    """
    loop = asyncio.get_running_loop()
    start = loop.time()
    while True:
        running = await asyncio.to_thread(_is_pid_running, pid)
        if not running:
            return True
        elapsed = loop.time() - start
        if elapsed >= deadline_seconds:
            return False
        # Sleep at most the remaining budget so the loop never
        # overshoots the deadline.
        await asyncio.sleep(
            min(_CANCEL_POLL_INTERVAL_SECONDS, deadline_seconds - elapsed)
        )


async def overnight_cancel(payload: CancelInput) -> CancelOutput:
    """Cancel an overnight runner via PG signal escalation (R6 / Task 14).

    Reads ``runner.pid``, calls :func:`ipc.verify_runner_pid` for the
    standard liveness check, then sends ``SIGTERM`` to the recorded
    PGID. Polls the runner PID for up to
    ``_CANCEL_GRACEFUL_TIMEOUT_SECONDS`` (12 s — strictly greater than
    Task 3's in-handler 6 s budget so the runner's tree-walker finishes
    before any outer SIGKILL fires). On timeout, sends ``SIGKILL`` to the
    PGID. If the runner is still alive after the SIGKILL window, the
    return ``reason`` is ``"signal_not_delivered_within_timeout"``;
    when ``payload.force=True``, the tool additionally unlinks
    ``runner.pid`` so a subsequent ``overnight_start_run`` can claim the
    O_EXCL lock (closes the SIGSTOP'd-runner permanent-lockout path).

    The five enumerated reasons (per spec R6) are returned via
    :class:`CancelOutput`:

    * ``"cancelled"`` — runner exited inside the budget.
    * ``"no_runner_pid"`` — no ``runner.pid`` file present.
    * ``"magic_mismatch"`` — ``runner.pid`` magic / schema_version bad.
    * ``"start_time_skew"`` — recorded start_time does not match live
      process (PID reuse).
    * ``"signal_not_delivered_within_timeout"`` — signals were sent but
      the runner did not exit.

    Note: ``os.killpg(pgid, SIGTERM)`` only signals processes in the
    runner's PG. Grandchildren spawned with ``start_new_session=True``
    are out of reach here — termination of those is wholly delegated to
    Task 3's in-runner SIGTERM handler walking the descendant tree.

    R29: ``os.killpg``, ``os.unlink``, and the ``psutil.Process`` polls
    are wrapped in ``asyncio.to_thread`` so this coroutine never blocks
    the stdio MCP server's event loop.
    """

    repo_path = _cli_handler._resolve_repo_path()
    session_dir = (
        repo_path / "lifecycle" / "sessions" / payload.session_id
    )

    pid_data = await asyncio.to_thread(_ipc.read_runner_pid, session_dir)
    pid_file_unlinked = False
    pid_value: Optional[int] = None

    if pid_data is None:
        return CancelOutput(
            cancelled=False,
            signal_sent=[],
            reason="no_runner_pid",
            pid_file_unlinked=False,
            pid=None,
        )

    if isinstance(pid_data, dict):
        recorded_pid = pid_data.get("pid")
        if isinstance(recorded_pid, int):
            pid_value = recorded_pid

    verified = await asyncio.to_thread(_ipc.verify_runner_pid, pid_data)
    if not verified:
        # Self-heal stale state — same behaviour as cli_handler.py:359-372.
        try:
            await asyncio.to_thread(_ipc.clear_runner_pid, session_dir)
            pid_file_unlinked = True
        except OSError:
            pass
        try:
            await asyncio.to_thread(_ipc.clear_active_session)
        except OSError:
            pass
        reason = _classify_verify_failure(pid_data)
        return CancelOutput(
            cancelled=False,
            signal_sent=[],
            reason=reason,
            pid_file_unlinked=pid_file_unlinked,
            pid=pid_value,
        )

    pgid = pid_data.get("pgid") if isinstance(pid_data, dict) else None
    runner_pid = pid_data.get("pid") if isinstance(pid_data, dict) else None
    if not isinstance(pgid, int) or not isinstance(runner_pid, int):
        # Treat structurally-broken pid file as magic_mismatch — the
        # IPC contract was not honoured even though verify happened to
        # accept it. Self-heal so the lock does not leak.
        try:
            await asyncio.to_thread(_ipc.clear_runner_pid, session_dir)
            pid_file_unlinked = True
        except OSError:
            pass
        return CancelOutput(
            cancelled=False,
            signal_sent=[],
            reason="magic_mismatch",
            pid_file_unlinked=pid_file_unlinked,
            pid=pid_value,
        )

    signal_sent: list[str] = []

    # Phase 1: SIGTERM the runner's PG.
    try:
        await asyncio.to_thread(os.killpg, pgid, _signal.SIGTERM)
        signal_sent.append("SIGTERM")
    except (ProcessLookupError, PermissionError):
        # Race: PG vanished between verify and signal. macOS returns
        # EPERM for an empty PG (Linux returns ESRCH); treat both as
        # "the runner is gone" and self-heal the lock.
        try:
            await asyncio.to_thread(_ipc.clear_runner_pid, session_dir)
            pid_file_unlinked = True
        except OSError:
            pass
        try:
            await asyncio.to_thread(_ipc.clear_active_session)
        except OSError:
            pass
        return CancelOutput(
            cancelled=True,
            signal_sent=[],
            reason="cancelled",
            pid_file_unlinked=pid_file_unlinked,
            pid=pid_value,
        )

    # Phase 2: poll for graceful exit within the 12 s budget.
    exited = await _wait_for_pid_exit(
        runner_pid, _CANCEL_GRACEFUL_TIMEOUT_SECONDS
    )

    if exited:
        # Self-heal the now-irrelevant lock so a fresh start can claim
        # the O_EXCL slot.
        try:
            await asyncio.to_thread(_ipc.clear_runner_pid, session_dir)
            pid_file_unlinked = True
        except OSError:
            pass
        try:
            await asyncio.to_thread(_ipc.clear_active_session)
        except OSError:
            pass
        return CancelOutput(
            cancelled=True,
            signal_sent=signal_sent,
            reason="cancelled",
            pid_file_unlinked=pid_file_unlinked,
            pid=pid_value,
        )

    # Phase 3: escalate to SIGKILL on the PG. Runner did not exit
    # within the graceful budget.
    try:
        await asyncio.to_thread(os.killpg, pgid, _signal.SIGKILL)
        signal_sent.append("SIGKILL")
    except (ProcessLookupError, PermissionError):
        # PG vanished between the SIGTERM-budget poll and the escalation
        # — on macOS an empty PG returns EPERM rather than ESRCH, so we
        # bucket both errors as "PG is gone, runner exited" and treat
        # the cancel as cancelled.
        try:
            await asyncio.to_thread(_ipc.clear_runner_pid, session_dir)
            pid_file_unlinked = True
        except OSError:
            pass
        try:
            await asyncio.to_thread(_ipc.clear_active_session)
        except OSError:
            pass
        return CancelOutput(
            cancelled=True,
            signal_sent=signal_sent,
            reason="cancelled",
            pid_file_unlinked=pid_file_unlinked,
            pid=pid_value,
        )

    # Phase 4: brief poll to see if SIGKILL took effect. SIGKILL cannot
    # be caught — the only way a process survives this poll is if it is
    # SIGSTOP'd or otherwise unkillable from this process's perspective.
    exited_after_kill = await _wait_for_pid_exit(
        runner_pid, _CANCEL_POST_SIGKILL_SETTLE_SECONDS
    )

    if exited_after_kill:
        try:
            await asyncio.to_thread(_ipc.clear_runner_pid, session_dir)
            pid_file_unlinked = True
        except OSError:
            pass
        try:
            await asyncio.to_thread(_ipc.clear_active_session)
        except OSError:
            pass
        return CancelOutput(
            cancelled=True,
            signal_sent=signal_sent,
            reason="cancelled",
            pid_file_unlinked=pid_file_unlinked,
            pid=pid_value,
        )

    # SIGSTOP'd / unkillable runner. ``force=True`` unlinks the lock so
    # a subsequent start can claim the slot; the runner process itself
    # is left in whatever signalled state it ended in (per spec R6 —
    # the user is responsible for ``kill -9 <pid>`` if needed).
    if payload.force:
        try:
            await asyncio.to_thread(_ipc.clear_runner_pid, session_dir)
            pid_file_unlinked = True
        except OSError:
            pass

    return CancelOutput(
        cancelled=False,
        signal_sent=signal_sent,
        reason="signal_not_delivered_within_timeout",
        pid_file_unlinked=pid_file_unlinked,
        pid=pid_value,
    )


async def overnight_list_sessions(
    payload: ListSessionsInput,
) -> ListSessionsOutput:
    """List active + recent overnight sessions.

    Globs ``lifecycle/sessions/*/overnight-state.json``, partitions
    results into active (``planning`` / ``executing`` / ``paused``) and
    recent (``complete``), and applies optional ``status`` / ``since`` /
    ``limit`` filters. Pagination cursors are reserved for a future
    expansion — v1 returns ``next_cursor=None`` and relies on ``limit``
    for the default 10-item recent slice (R7).

    All blocking I/O (``glob.glob``, file reads) runs on a worker thread
    via ``asyncio.to_thread`` (R29).
    """

    return await asyncio.to_thread(_list_sessions_sync, payload)
