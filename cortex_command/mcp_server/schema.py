"""Pydantic input/output models for the Cortex MCP overnight tools.

These schemas define the request/response contract for the five tools
registered by :func:`cortex_command.mcp_server.server.build_server`:

* ``overnight_start_run`` — :class:`StartRunInput` / :class:`StartRunOutput`
* ``overnight_status`` — :class:`StatusInput` / :class:`StatusOutput`
* ``overnight_logs`` — :class:`LogsInput` / :class:`LogsOutput`
* ``overnight_cancel`` — :class:`CancelInput` / :class:`CancelOutput`
* ``overnight_list_sessions`` — :class:`ListSessionsInput` /
  :class:`ListSessionsOutput`

The schemas are authoritative for FastMCP's JSON-RPC validation. Tool
handler bodies live in :mod:`cortex_command.mcp_server.tools` (stubs now,
filled in by subsequent tasks).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# overnight_start_run
# ---------------------------------------------------------------------------


class StartRunInput(BaseModel):
    """Input for the ``overnight_start_run`` tool.

    ``confirm_dangerously_skip_permissions`` is ``Literal[True]`` so models
    must pass the keyword explicitly (R3 confirmation gate). The handler
    intercepts Pydantic validation errors on this field and returns the
    verbatim warning sentence as a Tool Execution Error body so a model
    that omits the parameter sees the warning text rather than a bare
    JSON-RPC schema-validation failure.
    """

    confirm_dangerously_skip_permissions: Literal[True]
    state_path: str | None = None


class StartRunOutput(BaseModel):
    """Output for the ``overnight_start_run`` tool.

    ``started`` is ``True`` on successful spawn. On the
    ``concurrent_runner_alive`` branch (R8), ``started`` is ``False`` and
    ``reason`` / ``existing_session_id`` carry the refusal context while
    ``session_id`` / ``pid`` / ``started_at`` may be ``None``.
    """

    started: bool = True
    session_id: str | None = None
    pid: int | None = None
    started_at: str | None = None
    reason: str | None = None
    existing_session_id: str | None = None


# ---------------------------------------------------------------------------
# overnight_status
# ---------------------------------------------------------------------------


class StatusInput(BaseModel):
    """Input for the ``overnight_status`` tool."""

    session_id: str | None = None


class FeatureCounts(BaseModel):
    """Per-phase feature counts in the ``overnight_status`` response."""

    pending: int = 0
    running: int = 0
    merged: int = 0
    paused: int = 0
    deferred: int = 0
    failed: int = 0


class StatusOutput(BaseModel):
    """Output for the ``overnight_status`` tool.

    The ``phase`` field reports ``"no_active_session"`` when the
    active-session pointer is missing and no ``session_id`` override was
    supplied.
    """

    session_id: str | None = None
    phase: str
    current_round: int | None = None
    started_at: str | None = None
    updated_at: str | None = None
    features: FeatureCounts = Field(default_factory=FeatureCounts)
    integration_branch: str | None = None
    paused_reason: str | None = None


# ---------------------------------------------------------------------------
# overnight_logs
# ---------------------------------------------------------------------------


class LogsInput(BaseModel):
    """Input for the ``overnight_logs`` tool.

    ``cursor`` is an opaque base64-JSON token produced by
    :mod:`cortex_command.overnight.cursor`; clients pass it back verbatim
    from a previous response. ``limit`` is server-capped at 200 by the
    handler regardless of the request value.
    """

    session_id: str
    files: list[Literal["events", "agent-activity", "escalations"]] = Field(
        default_factory=lambda: ["events"]
    )
    cursor: str | None = None
    limit: int = 100
    tail: int | None = None


class LogsOutput(BaseModel):
    """Output for the ``overnight_logs`` tool.

    Optional fields surface R11 / R14 signals:

    * ``cursor_invalid`` — the cursor's ``file_size_at_emit`` exceeds the
      current file size (file was truncated); clients retry without a
      cursor to re-baseline.
    * ``oversized_line`` — a single log line exceeded
      ``MAX_TOOL_FILE_READ_BYTES``; the line is truncated with an explicit
      sentinel and ``next_cursor`` advances past it.
    * ``truncated`` — signals the single-line truncation path.
    * ``original_line_bytes`` — byte length of the oversized line before
      truncation.
    """

    lines: list[dict[str, Any]] = Field(default_factory=list)
    next_cursor: str | None = None
    eof: bool = False
    cursor_invalid: bool | None = None
    oversized_line: bool | None = None
    truncated: bool | None = None
    original_line_bytes: int | None = None


# ---------------------------------------------------------------------------
# overnight_cancel
# ---------------------------------------------------------------------------


class CancelInput(BaseModel):
    """Input for the ``overnight_cancel`` tool."""

    session_id: str
    force: bool = False


class CancelOutput(BaseModel):
    """Output for the ``overnight_cancel`` tool.

    ``reason`` is one of the five enumerated outcomes from R6:

    * ``"cancelled"`` — runner exited within the SIGTERM/SIGKILL window.
    * ``"no_runner_pid"`` — no ``runner.pid`` file present.
    * ``"magic_mismatch"`` — ``runner.pid`` magic does not match expected.
    * ``"start_time_skew"`` — PID reused since the runner recorded it.
    * ``"signal_not_delivered_within_timeout"`` — signal was sent but the
      runner did not exit within the budget (e.g. SIGSTOP'd runner).
    """

    cancelled: bool
    signal_sent: list[str] = Field(default_factory=list)
    reason: Literal[
        "cancelled",
        "no_runner_pid",
        "magic_mismatch",
        "start_time_skew",
        "signal_not_delivered_within_timeout",
    ]
    pid_file_unlinked: bool = False
    pid: int | None = None


# ---------------------------------------------------------------------------
# overnight_list_sessions
# ---------------------------------------------------------------------------


class ListSessionsInput(BaseModel):
    """Input for the ``overnight_list_sessions`` tool."""

    status: list[Literal["planning", "executing", "paused", "complete"]] | None = None
    since: str | None = None
    limit: int | None = 10
    cursor: str | None = None


class SessionSummary(BaseModel):
    """Compact session record used in ``overnight_list_sessions`` output."""

    session_id: str
    phase: str
    started_at: str | None = None
    updated_at: str | None = None
    integration_branch: str | None = None


class ListSessionsOutput(BaseModel):
    """Output for the ``overnight_list_sessions`` tool."""

    active: list[SessionSummary] = Field(default_factory=list)
    recent: list[SessionSummary] = Field(default_factory=list)
    total_count: int = 0
    next_cursor: str | None = None
