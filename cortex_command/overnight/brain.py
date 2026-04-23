"""Brain agent layer for post-retry triage decisions.

Replaces judgment.py with a unified SKIP/DEFER/PAUSE decision model.
The brain operates post-retry-exhaustion — there is no RETRY action.

Data model: BrainAction enum, BrainDecision and BrainContext dataclasses,
_default_decision() heuristic fallback, _parse_brain_response() for JSON
extraction, and request_brain_decision() async entry point.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from cortex_command.pipeline.dispatch import DispatchResult, dispatch_task
from cortex_command.pipeline.state import log_event as pipeline_log_event

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Decision types
# ---------------------------------------------------------------------------

class BrainAction(Enum):
    """Possible actions from the brain agent layer."""

    SKIP = "skip"
    DEFER = "defer"
    PAUSE = "pause"


@dataclass
class BrainDecision:
    """Structured decision from the brain agent.

    Fields:
        action: The decided action (skip, defer, or pause).
        reasoning: 1-2 sentence explanation for the decision.
        question: Human-directed question (populated only for DEFER).
        severity: Deferral severity — one of blocking/non-blocking/informational
                  (only for DEFER).
        confidence: Confidence score 0.0-1.0.
    """

    action: BrainAction
    reasoning: str
    question: Optional[str] = None
    severity: Optional[str] = None
    confidence: float = 0.5


@dataclass
class BrainContext:
    """Context provided to the brain agent for decision-making.

    Fields:
        feature: Feature name being worked on.
        task_description: Description of the failed task.
        retry_count: Number of retries already attempted.
        learnings: Full progress.txt content.
        spec_excerpt: Relevant section of the feature spec.
        last_attempt_output: Output from the most recent failed attempt.
        has_dependents: Whether other tasks depend on this one.
    """

    feature: str
    task_description: str
    retry_count: int
    learnings: str
    spec_excerpt: str
    last_attempt_output: str
    has_dependents: bool


# ---------------------------------------------------------------------------
# Fallback heuristic
# ---------------------------------------------------------------------------

def _default_decision() -> BrainDecision:
    """Return a fallback decision when the brain agent call fails.

    Always returns PAUSE so the feature surfaces as paused/failed
    without generating phantom deferred questions.
    """
    return BrainDecision(
        action=BrainAction.PAUSE,
        reasoning="Brain agent unavailable; pausing for investigation",
        confidence=0.3,
    )


# ---------------------------------------------------------------------------
# Prompt rendering helper
# ---------------------------------------------------------------------------

_BRAIN_TEMPLATE = Path(__file__).resolve().parent / "prompts/batch-brain.md"


def _render_template(template_path: Path, variables: dict[str, str]) -> str:
    """Read a prompt template and fill in {placeholders}."""
    template = template_path.read_text(encoding="utf-8")
    for key, value in variables.items():
        template = template.replace(f"{{{key}}}", value)
    return template


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------

_VALID_ACTIONS = {a.value for a in BrainAction}


def _parse_brain_response(output: str) -> BrainDecision | None:
    """Parse a brain agent response into a BrainDecision.

    Handles both raw JSON (``{...}``) and code-fenced JSON
    (``\u0060\u0060\u0060json\\n{...}\\n\u0060\u0060\u0060``). Strips fences before parsing
    if present. Uses ``re.DOTALL`` to match multi-line JSON blocks with
    quoted values containing newlines.

    Returns None on any parse failure, unknown action, or missing required
    field.
    """
    text = output.strip()

    # Strip code fences if present
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)
    else:
        # Find raw JSON block
        json_match = re.search(r"\{.*\}", text, re.DOTALL)
        if json_match:
            text = json_match.group(0)
        else:
            return None

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None

    # Validate required fields
    action_str = data.get("action")
    reasoning = data.get("reasoning")
    if not action_str or not reasoning:
        return None

    action_str = action_str.lower()
    if action_str not in _VALID_ACTIONS:
        return None

    action = BrainAction(action_str)

    # Extract optional fields
    question = data.get("question")
    severity = data.get("severity")
    confidence = data.get("confidence", 0.5)

    # Ensure confidence is a float
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.5

    return BrainDecision(
        action=action,
        reasoning=reasoning,
        question=question,
        severity=severity,
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# Async entry point
# ---------------------------------------------------------------------------

async def request_brain_decision(
    context: BrainContext,
    manager: "ConcurrencyManager | None",
    log_path: Path,
) -> BrainDecision:
    """Render the brain prompt, dispatch the brain agent, and return a decision.

    Calls ``dispatch_task`` directly (not ``throttled_dispatch``) because the
    caller already holds the semaphore slot — re-acquiring via
    ``throttled_dispatch`` would deadlock at MAX_5.

    On any failure (dispatch error, parse failure, exception), falls back to
    ``_default_decision`` and logs a ``brain_unavailable`` event. Always
    returns a ``BrainDecision`` — never raises.

    Args:
        context: Full context for the brain agent decision.
        manager: Optional ConcurrencyManager for rate limit reporting.
        log_path: Path to the JSONL event log for logging failures.

    Returns:
        A BrainDecision (always; never raises).
    """
    # Lazy import to avoid circular dependency at module level
    from cortex_command.overnight.throttle import ConcurrencyManager as _CM

    try:
        rendered_prompt = _render_template(_BRAIN_TEMPLATE, {
            "feature": context.feature,
            "task_description": context.task_description,
            "retry_count": str(context.retry_count),
            "learnings": context.learnings,
            "spec_excerpt": context.spec_excerpt,
            "has_dependents": str(context.has_dependents),
            "last_attempt_output": context.last_attempt_output,
        })

        result: DispatchResult = await dispatch_task(
            feature=context.feature,
            task="brain-triage",
            worktree_path=Path("."),
            complexity="simple",
            system_prompt=rendered_prompt,
            log_path=log_path,
            criticality="medium",
        )

        # Report rate limits without acquiring the semaphore
        if result.error_type == "infrastructure_failure" and manager is not None:
            manager.report_rate_limit()

        if result.success:
            decision = _parse_brain_response(result.output)
            if decision is not None:
                return decision
            # Parse returned None — fall back
            pipeline_log_event(log_path, {
                "event": "brain_unavailable",
                "feature": context.feature,
                "error_type": "parse_failure",
                "retry_count": context.retry_count,
            })
            return _default_decision()

        # Dispatch failed — log and fall back
        pipeline_log_event(log_path, {
            "event": "brain_unavailable",
            "feature": context.feature,
            "error_type": result.error_type,
            "retry_count": context.retry_count,
        })
        return _default_decision()

    except Exception as exc:
        pipeline_log_event(log_path, {
            "event": "brain_unavailable",
            "feature": context.feature,
            "error_type": "exception",
            "retry_count": context.retry_count,
        })
        return _default_decision()
