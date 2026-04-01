"""Shared SDK stubs for all test packages under claude/.

This module provides a minimal claude_agent_sdk stub that can be installed
before any production code is imported. Import _install_sdk_stub() from here
in conftest.py files rather than duplicating the implementation.
"""

from __future__ import annotations

import asyncio  # noqa: F401 — available for test use
import sys
import types
from dataclasses import dataclass
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Minimal SDK stubs
# ---------------------------------------------------------------------------

@dataclass
class TextBlock:
    text: str


@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class ToolResultBlock:
    tool_use_id: str
    content: str | None = None
    is_error: bool | None = None


@dataclass
class AssistantMessage:
    content: list
    model: str
    parent_tool_use_id: str | None = None
    error: Any = None


@dataclass
class UserMessage:
    content: Any
    uuid: str | None = None
    parent_tool_use_id: str | None = None
    tool_use_result: Any = None


@dataclass
class ResultMessage:
    subtype: str
    duration_ms: int
    duration_api_ms: int
    is_error: bool
    num_turns: int
    session_id: str
    total_cost_usd: float | None = None
    usage: dict | None = None
    result: str | None = None
    structured_output: Any = None


@dataclass
class ClaudeAgentOptions:
    model: str = "sonnet"
    max_turns: int = 20
    max_budget_usd: float = 25.0
    cwd: str = "."
    permission_mode: str = "bypassPermissions"
    allowed_tools: list | None = None
    system_prompt: str = ""
    env: dict | None = None
    settings: str | None = None
    effort: str | None = None
    stderr: Callable[[str], None] | None = None


class CLIConnectionError(Exception):
    pass


class ProcessError(Exception):
    pass


async def _placeholder_query(**kwargs):
    """Placeholder — replaced per-test via patch.object."""
    return
    yield


def _install_sdk_stub() -> None:
    """Install a minimal claude_agent_sdk stub, then reload dispatch."""
    # Only install once per interpreter session to avoid double-import issues.
    if "claude_agent_sdk" in sys.modules:
        existing = sys.modules["claude_agent_sdk"]
        if getattr(existing, "_is_test_stub", False):
            return  # already installed by a previous conftest exec

    mod = types.ModuleType("claude_agent_sdk")
    mod._is_test_stub = True  # type: ignore[attr-defined]
    mod.query = _placeholder_query
    mod.ClaudeAgentOptions = ClaudeAgentOptions
    mod.AssistantMessage = AssistantMessage
    mod.ResultMessage = ResultMessage
    mod.TextBlock = TextBlock
    mod.ToolUseBlock = ToolUseBlock
    mod.ToolResultBlock = ToolResultBlock
    mod.UserMessage = UserMessage
    mod.CLIConnectionError = CLIConnectionError
    mod.ProcessError = ProcessError
    sys.modules["claude_agent_sdk"] = mod

    # Force a fresh import of dispatch so it binds to our stubs.
    for key in list(sys.modules):
        if key == "claude.pipeline.dispatch" or key.endswith(".dispatch"):
            if "pipeline" in key and "dispatch" in key:
                del sys.modules[key]
