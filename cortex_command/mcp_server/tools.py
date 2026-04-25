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


_NOT_IMPLEMENTED_MSG = "handler not yet implemented — filled in by Task 12–15"


async def overnight_start_run(payload: StartRunInput) -> StartRunOutput:
    """Spawn the overnight runner. Filled in by Task 15."""

    raise NotImplementedError(_NOT_IMPLEMENTED_MSG)


async def overnight_status(payload: StatusInput) -> StatusOutput:
    """Return overnight session status. Filled in by Task 12."""

    raise NotImplementedError(_NOT_IMPLEMENTED_MSG)


async def overnight_logs(payload: LogsInput) -> LogsOutput:
    """Return paginated log lines. Filled in by Task 13."""

    raise NotImplementedError(_NOT_IMPLEMENTED_MSG)


async def overnight_cancel(payload: CancelInput) -> CancelOutput:
    """Cancel the active overnight runner. Filled in by Task 14."""

    raise NotImplementedError(_NOT_IMPLEMENTED_MSG)


async def overnight_list_sessions(payload: ListSessionsInput) -> ListSessionsOutput:
    """List active + recent overnight sessions. Filled in by Task 12."""

    raise NotImplementedError(_NOT_IMPLEMENTED_MSG)
