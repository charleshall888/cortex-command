"""FastMCP server factory for the Cortex overnight control plane.

This module exposes :func:`build_server`, the single entry point used by
``cortex mcp-server`` to launch the stdio MCP server. The factory:

1. Configures Python ``logging`` to write to ``sys.stderr`` only (R2 —
   stdout is the JSON-RPC stream and must stay clean for the MCP
   transport).
2. Builds a :class:`~mcp.server.fastmcp.FastMCP` instance named
   ``"cortex-overnight"``.
3. Registers the five tool handlers defined in
   :mod:`cortex_command.mcp_server.tools` via ``@server.tool``.

The tool handler bodies are stubs at this point — they are filled in by
Tasks 12–15. The factory can register them by name now so the wiring is
in place and subsequent tasks only modify handler bodies.

Import this module lazily from the CLI dispatcher so ``cortex --help``
does not pay the ``mcp`` import cost.
"""

from __future__ import annotations

import logging
import sys

from mcp.server.fastmcp import FastMCP

from cortex_command.mcp_server import tools
from cortex_command.mcp_server.schema import (
    CancelInput,
    CancelOutput,
    ListSessionsInput,
    ListSessionsOutput,
    LogsInput,
    LogsOutput,
    StartRunInput,
    StartRunOutput,
    StatusInput,
    StatusOutput,
)

__all__ = ["build_server"]


_LOGGING_CONFIGURED = False


def _configure_stderr_logging() -> None:
    """Route all logging to stderr (R2).

    The MCP stdio transport writes JSON-RPC frames on stdout — any stray
    log output on stdout corrupts the stream. We call ``basicConfig``
    once with ``stream=sys.stderr`` so every logger in the process
    defaults to stderr.
    """

    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    _LOGGING_CONFIGURED = True


# Verbatim warning sentence reused by the tool description and — per R3 —
# the validation-error body in the handler (filled in by Task 15). Kept
# here as a module constant so both call sites share the exact string.
_START_RUN_WARNING = (
    "This tool spawns a multi-hour autonomous agent that bypasses "
    "permission prompts and consumes Opus tokens. Only call when the "
    "user has explicitly asked to start an overnight run."
)


def build_server() -> FastMCP:
    """Construct the ``cortex-overnight`` FastMCP server.

    The returned instance has the five overnight tools registered and is
    ready for ``server.run(transport="stdio")``. Logging is configured
    for stderr-only output before any tool registration happens.
    """

    _configure_stderr_logging()

    server: FastMCP = FastMCP(name="cortex-overnight")

    @server.tool(
        name="overnight_start_run",
        description=_START_RUN_WARNING,
    )
    async def _overnight_start_run(payload: StartRunInput) -> StartRunOutput:
        return await tools.overnight_start_run(payload)

    @server.tool(
        name="overnight_status",
        description=(
            "Return the current overnight session status (phase, round, "
            "feature counts, integration branch)."
        ),
    )
    async def _overnight_status(payload: StatusInput) -> StatusOutput:
        return await tools.overnight_status(payload)

    @server.tool(
        name="overnight_logs",
        description=(
            "Return paginated log lines for events / agent-activity / "
            "escalations using opaque cursor tokens."
        ),
    )
    async def _overnight_logs(payload: LogsInput) -> LogsOutput:
        return await tools.overnight_logs(payload)

    @server.tool(
        name="overnight_cancel",
        description=(
            "Cancel the active overnight runner via SIGTERM-then-SIGKILL "
            "against its process group."
        ),
    )
    async def _overnight_cancel(payload: CancelInput) -> CancelOutput:
        return await tools.overnight_cancel(payload)

    @server.tool(
        name="overnight_list_sessions",
        description=(
            "List active and recent overnight sessions with optional "
            "status / since filters and cursor pagination."
        ),
    )
    async def _overnight_list_sessions(
        payload: ListSessionsInput,
    ) -> ListSessionsOutput:
        return await tools.overnight_list_sessions(payload)

    return server
