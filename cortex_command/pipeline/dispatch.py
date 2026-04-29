"""Agent SDK dispatch wrapper for pipeline task execution.

Wraps claude_agent_sdk.query() to provide model/budget tier selection based
on task complexity, progress streaming via state event logging, and structured
error classification for the retry module.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Optional, get_args

try:
    from claude_agent_sdk import (
        query,
        ClaudeAgentOptions,
        AssistantMessage,
        ResultMessage,
        TextBlock,
        ToolUseBlock,
        ToolResultBlock,
        UserMessage,
        CLIConnectionError,
        ProcessError,
    )

    _SDK_AVAILABLE = True
except ImportError:
    _SDK_AVAILABLE = False

from cortex_command.pipeline.state import log_event

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_input_summary(tool_name: str, input_dict: dict[str, Any]) -> str:
    """Return the first 80 characters of the primary input field for a tool call.

    Args:
        tool_name: Name of the tool being called (e.g. "Bash", "Read").
        input_dict: The tool's input parameters.

    Returns:
        A string of at most 80 characters representing the primary input.
    """
    if tool_name in ("Read", "Write", "Edit"):
        value = input_dict.get("file_path", "")
    elif tool_name == "Bash":
        value = input_dict.get("command", "")
    elif tool_name in ("Glob", "Grep"):
        value = input_dict.get("pattern", "")
    else:
        value = next(iter(input_dict.values()), "") if input_dict else ""
    return str(value)[:80]


def _deep_merge(base: dict, overlay: dict) -> None:
    """Recursively merge overlay into base in-place.

    For dict values, recurse.  For all other values, overlay wins.

    Args:
        base: The dict to merge into (mutated in-place).
        overlay: The dict whose values take precedence.
    """
    for key, value in overlay.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def _load_project_settings(repo_root: Path) -> dict:
    """Load and merge .claude/settings.json and .claude/settings.local.json.

    Iterates the two filenames in order; for each: skips silently if missing;
    parses JSON and deep-merges into the accumulator; on JSONDecodeError prints
    to stderr and skips.

    Args:
        repo_root: Path to the repository root.

    Returns:
        Accumulated settings dict (may be empty if no files found).
    """
    import sys

    result: dict = {}
    for filename in ("settings.json", "settings.local.json"):
        path = repo_root / ".claude" / filename
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            continue
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            print(f"dispatch: failed to parse {path}: {e}", file=sys.stderr)
            continue
        _deep_merge(result, data)
    return result


# ---------------------------------------------------------------------------
# Tier configuration
# ---------------------------------------------------------------------------

TIER_CONFIG: dict[str, dict] = {
    "trivial": {"model": "haiku", "max_turns": 15, "max_budget_usd": 5.00},
    "simple": {"model": "sonnet", "max_turns": 20, "max_budget_usd": 25.00},
    "complex": {"model": "opus", "max_turns": 30, "max_budget_usd": 50.00},
}

# Maps complexity tier to effort level for ClaudeAgentOptions.
# Trivial mechanical tasks get low effort; complex reasoning tasks get high effort.
EFFORT_MAP: dict[str, str] = {
    "trivial": "low",
    "simple":  "medium",
    "complex": "high",
}

# 2D model matrix: (complexity, criticality) -> model name
# Criticality levels: low, medium, high, critical
_MODEL_MATRIX: dict[tuple[str, str], str] = {
    ("trivial", "low"):      "haiku",
    ("trivial", "medium"):   "haiku",
    ("trivial", "high"):     "sonnet",
    ("trivial", "critical"): "sonnet",
    ("simple",  "low"):      "sonnet",
    ("simple",  "medium"):   "sonnet",
    ("simple",  "high"):     "sonnet",
    ("simple",  "critical"): "sonnet",
    ("complex", "low"):      "sonnet",
    ("complex", "medium"):   "sonnet",
    ("complex", "high"):     "opus",
    ("complex", "critical"): "opus",
}

_VALID_CRITICALITY = {"low", "medium", "high", "critical"}

# Closed vocabulary of dispatch-call sites, emitted on dispatch_start so
# downstream aggregators can group by skill (Req: per-skill pipeline aggregates).
# Add new skills here only after wiring the corresponding caller; runtime guard
# in dispatch_task rejects values not in this set.
Skill = Literal[
    "implement",
    "review",
    "review-fix",
    "conflict-repair",
    "merge-test-repair",
    "integration-recovery",
    "brain",
    "orchestrator-round",  # documentation-only: never passed to dispatch_task; runner.py emits via pipeline.state.log_event
]

# Model escalation ladder used by the retry loop (Req 8).
# Maps each model name to the next higher tier, or None when already at max.
MODEL_ESCALATION_LADDER: dict[str, Optional[str]] = {
    "haiku":  "sonnet",
    "sonnet": "opus",
    "opus":   None,
}


def resolve_model(complexity: str, criticality: str = "medium") -> str:
    """Resolve a model name from a complexity tier and criticality level.

    Args:
        complexity: Complexity tier key ("trivial", "simple", or "complex").
        criticality: Criticality level ("low", "medium", "high", or "critical").
            Defaults to "medium".

    Returns:
        Model name string ("haiku", "sonnet", or "opus").

    Raises:
        ValueError: If complexity or criticality is not a recognized value.
    """
    if complexity not in TIER_CONFIG:
        raise ValueError(
            f"Unknown complexity tier {complexity!r}; "
            f"must be one of {sorted(TIER_CONFIG)}"
        )
    if criticality not in _VALID_CRITICALITY:
        raise ValueError(
            f"Unknown criticality {criticality!r}; "
            f"must be one of {sorted(_VALID_CRITICALITY)}"
        )
    return _MODEL_MATRIX[(complexity, criticality)]


# Tools available to all dispatched agents
_ALLOWED_TOOLS = ["Read", "Write", "Edit", "Bash", "Glob", "Grep"]


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class DispatchResult:
    """Structured result from a dispatched agent task.

    Attributes:
        success: Whether the task completed without error.
        output: Collected text output from the agent.
        error_type: Classification string if the task failed, else None.
            One of: agent_timeout, agent_test_failure, agent_refusal,
            agent_confused, task_failure, infrastructure_failure,
            budget_exhausted, api_rate_limit, unknown.
        error_detail: Human-readable error detail string, else None.
        cost_usd: Total cost reported by the SDK, else None.
    """

    success: bool
    output: str
    error_type: Optional[str] = None
    error_detail: Optional[str] = None
    cost_usd: Optional[float] = None


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------

# Recovery path for each error type.  Consumed by retry logic and morning report.
ERROR_RECOVERY: dict[str, str] = {
    "agent_timeout":          "retry",
    "agent_test_failure":     "escalate",
    "agent_refusal":          "pause_human",
    "agent_confused":         "escalate",
    "task_failure":           "retry",
    "infrastructure_failure": "pause_human",
    "budget_exhausted":       "pause_session",
    "api_rate_limit":         "pause_session",
    "unknown":                "retry",
}

# Keyword patterns used for content-based subtype detection.
# Checked against lowercased combined text of (error message + agent output).
_TIMEOUT_PATTERNS = ("timeout", "timed out", "time out")
_TEST_FAILURE_PATTERNS = (
    "test failed", "tests failed", "test failure", "assertion error",
    "assertionerror", "pytest", "failing tests", "failing test",
)
_REFUSAL_PATTERNS = (
    "i cannot", "i can't", "i'm unable", "i am unable",
    "i'm not able", "i am not able", "cannot help", "not able to help",
    "i must refuse", "i will not", "i won't",
)
_CONFUSED_PATTERNS = (
    "i'm not sure", "i am not sure", "i don't understand", "i do not understand",
    "unclear to me", "i'm confused", "i am confused", "don't know how to",
    "do not know how to", "i'm lost", "i am lost",
)
_RATE_LIMIT_PATTERNS = ("rate_limit_error", "rate limit", "too many requests")
_MAX_STDERR_LINES = 100


def classify_error(error: Exception, output: str = "") -> str:
    """Classify an exception into a dispatch error type.

    Performs two-pass detection: first checks the exception type, then
    falls back to keyword scanning of the combined error message and agent
    output for finer-grained subtypes within ProcessError.

    Args:
        error: The exception raised during dispatch.
        output: Optional accumulated agent output text.  Used for
            content-based subtype detection (agent_refusal, agent_confused,
            agent_test_failure).  Defaults to empty string.

    Returns:
        A string error type for DispatchResult.error_type:

        - "agent_timeout"      — wall-clock timeout; recovery: retry
        - "agent_test_failure" — agent hit a test failure; recovery: escalate
        - "agent_refusal"      — agent refused the task; recovery: pause_human
        - "agent_confused"     — agent appears lost/confused; recovery: escalate
        - "api_rate_limit"     — API rate limit hit; recovery: pause_session
        - "task_failure"       — other ProcessError; recovery: retry
        - "infrastructure_failure" — CLI unavailable; recovery: pause_human
        - "unknown"            — anything else; recovery: retry

    See also:
        ERROR_RECOVERY: maps each error type to a recovery path string.
    """
    # Hard-typed exceptions take precedence over content scanning.
    if isinstance(error, asyncio.TimeoutError):
        return "agent_timeout"

    if _SDK_AVAILABLE and isinstance(error, CLIConnectionError):
        return "infrastructure_failure"

    if _SDK_AVAILABLE and isinstance(error, ProcessError):
        # Build a single lowercase search corpus from exception text + output.
        corpus = f"{error}".lower()
        if output:
            corpus = corpus + " " + output.lower()

        if any(p in corpus for p in _TIMEOUT_PATTERNS):
            return "agent_timeout"
        if any(p in corpus for p in _TEST_FAILURE_PATTERNS):
            return "agent_test_failure"
        if any(p in corpus for p in _REFUSAL_PATTERNS):
            return "agent_refusal"
        if any(p in corpus for p in _CONFUSED_PATTERNS):
            return "agent_confused"
        if any(p in corpus for p in _RATE_LIMIT_PATTERNS):
            return "api_rate_limit"

        return "task_failure"

    return "unknown"


# ---------------------------------------------------------------------------
# Activity log helper
# ---------------------------------------------------------------------------

async def _write_activity_event(path: Path, event_dict: dict) -> None:
    """Write an activity event to the given JSONL path in a background thread.

    Swallows all exceptions so that activity logging never interrupts the
    main dispatch loop.
    """
    try:
        await asyncio.to_thread(log_event, path, event_dict)
    except Exception as exc:
        logger.warning("activity log write failed: %s", exc)


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

async def dispatch_task(
    feature: str,
    task: str,
    worktree_path: Path,
    complexity: str,
    system_prompt: str,
    log_path: Optional[Path] = None,
    criticality: str = "medium",
    activity_log_path: Optional[Path] = None,
    model_override: Optional[str] = None,
    effort_override: Optional[str] = None,
    integration_base_path: Optional[Path] = None,
    repo_root: Optional[Path] = None,
    *,
    skill: Skill,
    attempt: int = 1,
    escalated: bool = False,
    escalation_event: bool = False,
    cycle: int | None = None,
) -> DispatchResult:
    """Dispatch a task to a Claude agent via the Agent SDK.

    Selects model, budget, and turn limits based on the task's complexity
    tier and criticality level. Streams progress events to the event log
    and collects output text from assistant messages.

    Args:
        feature: Feature name (for logging context).
        task: The prompt/task description to send to the agent.
        worktree_path: Working directory for the agent (git worktree).
        complexity: Complexity tier key ("trivial", "simple", or "complex").
        system_prompt: System prompt to configure the agent's behavior.
        log_path: Optional path to JSONL event log. If provided, progress
            events are appended via state.log_event.
        criticality: Criticality level ("low", "medium", "high", or
            "critical"). Defaults to "medium" for backward compatibility.
        activity_log_path: Optional path to per-agent activity JSONL log.
            If provided, tool use and result events are appended via
            _write_activity_event (non-blocking).
        model_override: If provided, use this model name directly instead of
            resolving from complexity/criticality.  Used by the retry loop to
            implement model-tier escalation (Haiku → Sonnet → Opus).
        effort_override: If provided, use this effort level directly instead of
            resolving from the complexity tier via EFFORT_MAP.  Accepts any
            value accepted by ClaudeAgentOptions ("low", "medium", "high",
            "max").
        skill: Closed-vocabulary identifier for the dispatch-call site (one of
            the values in the ``Skill`` Literal). Required keyword-only
            argument; emitted on ``dispatch_start`` so downstream aggregators
            can group dispatches by ``(skill, tier)``. New skills must be
            added to the ``Skill`` Literal at module scope before use.
        attempt: 1-based retry attempt number for this dispatch. Defaults to
            ``1`` for the first attempt.
        escalated: True when this dispatch is running on an escalated model
            tier (e.g. Sonnet → Opus) relative to the original tier choice.
        escalation_event: True when this dispatch represents the boundary
            event where the escalation actually occurred (distinct from
            subsequent attempts that merely run on the escalated tier).
        cycle: Review cycle number for ``review-fix`` dispatches only.
            Must be ``None`` for every other skill; passing a non-None value
            with any other ``skill`` raises ``ValueError``.

    Returns:
        DispatchResult with success status, collected output, error info,
        and cost.

    Raises:
        RuntimeError: If claude_agent_sdk is not installed.
        ValueError: If complexity or criticality is not a recognized value,
            if ``skill`` is not in the ``Skill`` Literal vocabulary, or if
            ``cycle`` is non-None for any skill other than ``review-fix``.
    """
    if not _SDK_AVAILABLE:
        raise RuntimeError(
            "claude_agent_sdk is not installed. "
            "Install it with: pip install claude-agent-sdk"
        )

    tier = TIER_CONFIG[complexity] if complexity in TIER_CONFIG else None
    if tier is None:
        raise ValueError(
            f"Unknown complexity tier {complexity!r}; "
            f"must be one of {sorted(TIER_CONFIG)}"
        )

    if skill not in get_args(Skill):
        raise ValueError(f"unregistered skill {skill!r}; must be one of {sorted(get_args(Skill))}")
    if cycle is not None and skill != "review-fix":
        raise ValueError(f"cycle is only valid for skill='review-fix'; got skill={skill!r} with cycle={cycle!r}")

    model = model_override if model_override is not None else resolve_model(complexity, criticality)
    effort = effort_override if effort_override is not None else EFFORT_MAP[complexity]

    # Clear CLAUDECODE so the sub-agent doesn't hit the nested-session guard.
    # The SDK merges options.env on top of os.environ (proven by existing CLAUDECODE
    # override behavior). Forward ANTHROPIC_API_KEY if present so SDK subprocesses
    # use API-key billing rather than falling back to subscription.
    _env: dict[str, str] = {"CLAUDECODE": ""}
    if _api_key := os.environ.get("ANTHROPIC_API_KEY"):
        _env["ANTHROPIC_API_KEY"] = _api_key
    if _oauth_token := os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        _env["CLAUDE_CODE_OAUTH_TOKEN"] = _oauth_token

    _allowlist_entries = [
        str(worktree_path),
        os.path.realpath(str(worktree_path)),  # canonical form (handles /tmp → /private/tmp)
    ]
    if integration_base_path is not None:
        _allowlist_entries.append(str(integration_base_path))
        _allowlist_entries.append(os.path.realpath(str(integration_base_path)))
    _write_allowlist = list(dict.fromkeys(_allowlist_entries))
    if repo_root is not None:
        base_settings = _load_project_settings(repo_root)
        _deep_merge(base_settings, {"sandbox": {"write": {"allowOnly": _write_allowlist}}})
        _worktree_settings = json.dumps(base_settings)
    else:
        _worktree_settings = json.dumps({"sandbox": {"write": {"allowOnly": _write_allowlist}}})

    _stderr_lines: list[str] = []

    def _on_stderr(line: str) -> None:
        line = re.sub(r'sk-ant-[a-zA-Z0-9_-]+', 'sk-ant-<redacted>', line)
        if len(_stderr_lines) < _MAX_STDERR_LINES:
            _stderr_lines.append(line)

    options = ClaudeAgentOptions(
        model=model,
        max_turns=tier["max_turns"],
        max_budget_usd=tier["max_budget_usd"],
        cwd=str(worktree_path),
        permission_mode="bypassPermissions",
        allowed_tools=_ALLOWED_TOOLS,
        system_prompt=system_prompt,
        env=_env,
        settings=_worktree_settings,
        effort=effort,
        stderr=_on_stderr,
    )

    if log_path:
        event_dict: dict[str, Any] = {
            "event": "dispatch_start",
            "feature": feature,
            "skill": skill,
            "attempt": attempt,
            "escalated": escalated,
            "escalation_event": escalation_event,
        }
        if cycle is not None:
            event_dict["cycle"] = cycle
        event_dict["complexity"] = complexity
        event_dict["criticality"] = criticality
        event_dict["model"] = model
        event_dict["effort"] = effort
        event_dict["max_turns"] = tier["max_turns"]
        event_dict["max_budget_usd"] = tier["max_budget_usd"]
        log_event(log_path, event_dict)

    output_parts: list[str] = []
    cost_usd: float | None = None
    _tool_name_map: dict[str, str] = {}
    _budget_exhausted: bool = False
    _budget_subtype: str = ""

    try:
        async for message in query(prompt=task, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        output_parts.append(block.text)

                if log_path:
                    progress_event: dict = {
                        "event": "dispatch_progress",
                        "feature": feature,
                        "message_type": "assistant",
                    }
                    first_text = next(
                        (block.text for block in message.content if isinstance(block, TextBlock)),
                        None,
                    )
                    if first_text:
                        progress_event["content_preview"] = first_text[:200]
                    log_event(log_path, progress_event)

                if activity_log_path is not None:
                    for block in message.content:
                        if isinstance(block, ToolUseBlock):
                            _tool_name_map[block.id] = block.name
                            await _write_activity_event(activity_log_path, {
                                "event": "tool_call",
                                "tool": block.name,
                                "input_summary": _extract_input_summary(block.name, block.input),
                            })

            elif isinstance(message, UserMessage):
                if activity_log_path is not None:
                    for block in message.content:
                        if isinstance(block, ToolResultBlock):
                            tool_name = _tool_name_map.get(block.tool_use_id, "")
                            await _write_activity_event(activity_log_path, {
                                "event": "tool_result",
                                "tool": tool_name,
                                "success": not (block.is_error or False),
                            })

            elif isinstance(message, ResultMessage):
                cost_usd = message.total_cost_usd
                if message.is_error:
                    _budget_exhausted = True
                    _budget_subtype = message.subtype or ""
                    output_parts.append(f"[budget_exhausted: subtype={message.subtype}]")

                if log_path:
                    log_event(log_path, {
                        "event": "dispatch_complete",
                        "feature": feature,
                        "cost_usd": cost_usd,
                        "duration_ms": message.duration_ms,
                        "num_turns": message.num_turns,
                    })

                if activity_log_path is not None:
                    await _write_activity_event(activity_log_path, {
                        "event": "turn_complete",
                        "turn": message.num_turns,
                        "cost_usd": cost_usd,
                    })

        if _budget_exhausted:
            error_detail = f"ResultMessage.is_error=True subtype={_budget_subtype}"
            if log_path:
                log_event(log_path, {
                    "event": "dispatch_error",
                    "feature": feature,
                    "error_type": "budget_exhausted",
                    "error_detail": error_detail,
                })
            return DispatchResult(
                success=False,
                output="\n".join(output_parts),
                error_type="budget_exhausted",
                error_detail=error_detail,
                cost_usd=cost_usd,
            )

        return DispatchResult(
            success=True,
            output="\n".join(output_parts),
            cost_usd=cost_usd,
        )

    except (ProcessError, CLIConnectionError, asyncio.TimeoutError) as exc:
        error_type = classify_error(exc, "\n".join(output_parts) + ("\n" + "\n".join(_stderr_lines) if _stderr_lines else ""))
        error_detail = f"{type(exc).__name__}: {exc}"

        if log_path:
            log_event(log_path, {
                "event": "dispatch_error",
                "feature": feature,
                "error_type": error_type,
                "error_detail": error_detail,
            })

        return DispatchResult(
            success=False,
            output="\n".join(output_parts),
            error_type=error_type,
            error_detail=error_detail,
            cost_usd=cost_usd,
        )

    except Exception as exc:
        error_detail = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"

        if log_path:
            log_event(log_path, {
                "event": "dispatch_error",
                "feature": feature,
                "error_type": "unknown",
                "error_detail": error_detail,
            })

        return DispatchResult(
            success=False,
            output="\n".join(output_parts),
            error_type="unknown",
            error_detail=error_detail,
            cost_usd=cost_usd,
        )
