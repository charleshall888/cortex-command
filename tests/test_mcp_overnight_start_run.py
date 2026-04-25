"""Verification tests for Task 15 — ``overnight_start_run`` MCP tool.

Covers R3 / R13:

* Missing ``confirm_dangerously_skip_permissions`` returns a
  :class:`ToolError` (the FastMCP "Tool Execution Error", surfaced to the
  client as ``isError: true``) whose body contains the verbatim warning
  sentence — so a model that calls the tool without the parameter sees
  the warning text, not a bare JSON-RPC schema-validation failure.
* The ``@server.tool`` description for ``overnight_start_run`` begins
  with the verbatim warning sentence (the model reads this in the tool
  inventory before deciding to call it).
"""

from __future__ import annotations

import asyncio

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from cortex_command.mcp_server import server as mcp_server
from cortex_command.mcp_server import tools


_VERBATIM_WARNING_SENTENCE = (
    "This tool spawns a multi-hour autonomous agent that bypasses "
    "permission prompts and consumes Opus tokens. Only call when the "
    "user has explicitly asked to start an overnight run."
)


def test_missing_confirm_arg_returns_validation_error() -> None:
    """Calling the tool without the confirm field surfaces the warning.

    The handler intercepts Pydantic validation errors on the
    ``confirm_dangerously_skip_permissions`` field and re-includes the
    verbatim warning sentence in the resulting :class:`ToolError`'s body.
    The MCP client receives this as a Tool Execution Error
    (``isError: true``) with the warning text inline.
    """
    with pytest.raises(ToolError) as excinfo:
        # Pass a raw dict with no fields — Pydantic's ``Literal[True]``
        # constraint on ``confirm_dangerously_skip_permissions`` rejects
        # the validation, the handler catches it, and re-raises with
        # the warning sentence embedded.
        asyncio.run(tools.overnight_start_run({}))

    # The verbatim warning sentence must appear in the error body so the
    # model that called the tool sees the explicit warning rather than a
    # bare schema-validation diagnostic (R3).
    assert _VERBATIM_WARNING_SENTENCE in str(excinfo.value)


def test_warning_sentence_present_in_description() -> None:
    """The ``@server.tool`` description starts with the verbatim sentence.

    The tool description is what the model reads in the tool inventory
    before deciding whether to call ``overnight_start_run``. The warning
    must appear at the *start* of the description so a model scanning
    tool listings cannot miss it (R3 / R13).
    """
    fastmcp_server = mcp_server.build_server()

    # ``list_tools`` is async on the FastMCP server.
    tool_list = asyncio.run(fastmcp_server.list_tools())

    by_name = {t.name: t for t in tool_list}
    assert "overnight_start_run" in by_name, (
        "overnight_start_run must be registered on the FastMCP server"
    )

    description = by_name["overnight_start_run"].description or ""
    assert description.startswith(_VERBATIM_WARNING_SENTENCE), (
        "tool description must begin with the verbatim warning sentence; "
        f"got: {description[:200]!r}"
    )


def test_warning_sentence_constant_matches_verbatim() -> None:
    """The exported constant equals the verbatim warning sentence.

    Both call sites (the tool description and the validation-error path)
    rely on :data:`mcp_server.server._START_RUN_WARNING`. If the constant
    drifts, the description and error body silently lose the verbatim
    text. This test pins the constant against the spec's exact wording.
    """
    assert mcp_server._START_RUN_WARNING == _VERBATIM_WARNING_SENTENCE
