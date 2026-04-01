"""Ralph Loop retry logic for pipeline task execution.

Wraps dispatch_task with structured retry behavior: each retry spawns a
fresh agent process with accumulated learnings from previous attempts,
preventing context degradation. A circuit breaker detects when consecutive
retries produce identical diffs (no progress) and pauses the task.

Failure classification drives retry strategy (via ERROR_RECOVERY in dispatch):
- agent_timeout:          immediate retry with learnings           (retry)
- agent_test_failure:     escalate to next model tier, or pause    (escalate)
- agent_refusal:          pause immediately for human triage       (pause_human)
- agent_confused:         escalate to next model tier, or pause    (escalate)
- task_failure:           immediate retry with learnings           (retry)
- infrastructure_failure: pause immediately for human triage       (pause_human)
- unknown:                immediate retry with learnings           (retry)
"""

from __future__ import annotations

import asyncio
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from claude.pipeline.dispatch import (
    dispatch_task,
    ERROR_RECOVERY,
    MODEL_ESCALATION_LADDER,
    resolve_model,
)
from claude.pipeline.state import log_event
from claude.pipeline.worktree import cleanup_stale_lock


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class RetryResult:
    """Structured result from the retry loop.

    Attributes:
        success: Whether the task ultimately succeeded.
        attempts: Total number of attempts made (first attempt + retries).
        final_output: Output text from the last dispatch attempt.
        learnings_path: Path to the progress.txt learnings file, or None
            if no learnings were written (success on first attempt).
        paused: True if the circuit breaker tripped or all retries were
            exhausted without success.
        total_cost_usd: Sum of cost_usd across all dispatch attempts.
        idempotency_skipped: True if the task was skipped because an
            idempotency token confirmed it already completed in a prior
            session. All normal code paths leave this False.
    """

    success: bool
    attempts: int
    final_output: str
    learnings_path: Optional[Path] = None
    paused: bool = False
    total_cost_usd: float = 0.0
    idempotency_skipped: bool = False
    error_type: Optional[str] = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _append_learnings(
    learnings_dir: Path,
    attempt: int,
    task: str,
    error: str,
    output: str,
) -> Path:
    """Append a structured learnings entry to progress.txt.

    Each entry records what was tried, what went wrong, and any relevant
    output so the next retry can incorporate these discoveries.

    Args:
        learnings_dir: Directory containing (or that will contain)
            progress.txt.
        attempt: The attempt number (1-based).
        task: The task description that was attempted.
        error: Error type and detail from the failed dispatch.
        output: Relevant output from the agent (truncated if very long).

    Returns:
        Path to the progress.txt file.
    """
    learnings_dir.mkdir(parents=True, exist_ok=True)
    progress_path = learnings_dir / "progress.txt"

    timestamp = datetime.now(timezone.utc).isoformat()

    # Truncate output to a reasonable size for prompt inclusion
    max_output_len = 2000
    truncated_output = output
    if len(output) > max_output_len:
        truncated_output = output[:max_output_len] + "\n... (truncated)"

    entry = (
        f"\n{'=' * 60}\n"
        f"Attempt {attempt} | {timestamp}\n"
        f"{'=' * 60}\n"
        f"Task: {task}\n"
        f"Error: {error}\n"
        f"Output:\n{truncated_output}\n"
    )

    with open(progress_path, "a", encoding="utf-8") as f:
        f.write(entry)

    return progress_path


def _get_worktree_diff(worktree_path: Path) -> str:
    """Run git diff HEAD in the worktree and return the diff string.

    Used by the circuit breaker to detect whether a retry made any
    changes compared to the previous state.

    Args:
        worktree_path: Path to the git worktree directory.

    Returns:
        The diff output as a string. Empty string if the diff command
        fails or there are no changes.
    """
    try:
        result = subprocess.run(
            ["git", "diff", "HEAD"],
            capture_output=True,
            text=True,
            cwd=worktree_path,
            timeout=30,
        )
        return result.stdout if result.returncode == 0 else ""
    except (subprocess.TimeoutExpired, OSError):
        return ""


def _check_circuit_breaker(current_diff: str, previous_diff: str) -> bool:
    """Check whether two consecutive diffs indicate no progress.

    Args:
        current_diff: Diff output from the current retry.
        previous_diff: Diff output from the previous retry.

    Returns:
        True if the diffs are identical (no progress), False otherwise.
    """
    return current_diff == previous_diff


# ---------------------------------------------------------------------------
# Main retry loop
# ---------------------------------------------------------------------------

async def retry_task(
    feature: str,
    task: str,
    worktree_path: Path,
    complexity: str,
    system_prompt: str,
    learnings_dir: Path,
    log_path: Optional[Path] = None,
    max_retries: int = 3,
    criticality: Optional[str] = None,
    activity_log_path: Optional[Path] = None,
    integration_base_path: Optional[Path] = None,
    repo_path: Path | None = None,
) -> RetryResult:
    """Execute a task with Ralph Loop retry logic.

    Makes up to max_retries + 1 total attempts (the initial attempt plus
    retries). Each retry spawns a fresh agent process with accumulated
    learnings from previous attempts appended to the system prompt.

    Circuit breaker: if two consecutive retries produce identical git
    diffs (or both produce no diff), the task is paused.

    Args:
        feature: Feature name (for logging and lock cleanup).
        task: The task description/prompt to send to the agent.
        worktree_path: Git worktree directory for the agent.
        complexity: Complexity tier ("trivial", "simple", "complex").
        system_prompt: Base system prompt for the agent.
        learnings_dir: Directory for progress.txt learnings file.
        log_path: Optional path to JSONL event log.
        max_retries: Maximum number of retries after the first attempt.
            Defaults to 3.

    Returns:
        RetryResult with final status, attempt count, learnings info,
        and total cost.
    """
    total_cost = 0.0
    previous_diff: Optional[str] = None
    consecutive_identical_diffs = 0
    learnings_path: Optional[Path] = None
    total_attempts = max_retries + 1

    # Resolve and track the active model so the escalation ladder can
    # upgrade it on each "escalate" recovery path (Req 8).
    _criticality_val = criticality if criticality is not None else "medium"
    current_model: str = resolve_model(complexity, _criticality_val)

    for attempt in range(1, total_attempts + 1):
        # Build the prompt for this attempt, including learnings
        effective_prompt = system_prompt
        progress_path = learnings_dir / "progress.txt"
        if progress_path.exists():
            learnings_content = progress_path.read_text(encoding="utf-8")
            effective_prompt = (
                f"{system_prompt}\n\n"
                f"## Previous Attempt Learnings\n"
                f"The following is a log of previous attempts at this task. "
                f"Use these learnings to avoid repeating the same mistakes "
                f"and to build on what was discovered.\n\n"
                f"{learnings_content}"
            )

        if log_path:
            log_event(log_path, {
                "event": "retry_attempt",
                "feature": feature,
                "attempt": attempt,
                "max_attempts": total_attempts,
                "model": current_model,
            })

        # Dispatch the task, forwarding the active model so that escalation
        # overrides take effect even if complexity/criticality stay constant.
        result = await dispatch_task(
            feature=feature,
            task=task,
            worktree_path=worktree_path,
            complexity=complexity,
            system_prompt=effective_prompt,
            log_path=log_path,
            criticality=criticality,
            activity_log_path=activity_log_path,
            model_override=current_model,
            integration_base_path=integration_base_path,
            repo_root=repo_path,
        )

        total_cost += result.cost_usd or 0.0

        # Success — return immediately
        if result.success:
            if log_path:
                log_event(log_path, {
                    "event": "retry_success",
                    "feature": feature,
                    "attempt": attempt,
                    "total_cost_usd": total_cost,
                })

            return RetryResult(
                success=True,
                attempts=attempt,
                final_output=result.output,
                learnings_path=learnings_path,
                paused=False,
                total_cost_usd=total_cost,
            )

        # Failure — record learnings
        error_info = f"{result.error_type}: {result.error_detail or 'no detail'}"
        learnings_path = _append_learnings(
            learnings_dir=learnings_dir,
            attempt=attempt,
            task=task,
            error=error_info,
            output=result.output,
        )

        if log_path:
            log_event(log_path, {
                "event": "retry_failure",
                "feature": feature,
                "attempt": attempt,
                "error_type": result.error_type,
                "error_detail": result.error_detail,
            })

        # If this was the last attempt, don't bother with circuit breaker
        # or backoff — just break and return exhausted result
        if attempt == total_attempts:
            break

        # Circuit breaker: compare git diffs between retries
        current_diff = _get_worktree_diff(worktree_path)
        if previous_diff is not None and _check_circuit_breaker(current_diff, previous_diff):
            consecutive_identical_diffs += 1
        else:
            consecutive_identical_diffs = 0
        previous_diff = current_diff

        if consecutive_identical_diffs >= 1:
            if log_path:
                log_event(log_path, {
                    "event": "retry_circuit_breaker",
                    "feature": feature,
                    "attempt": attempt,
                    "reason": "identical diffs for 2 consecutive retries",
                })

            return RetryResult(
                success=False,
                attempts=attempt,
                final_output=result.output,
                learnings_path=learnings_path,
                paused=True,
                total_cost_usd=total_cost,
            )

        # Clean up stale locks before deciding on retry strategy.
        cleanup_stale_lock(feature, repo_path=repo_path)

        # Apply retry strategy using the ERROR_RECOVERY table from dispatch.
        error_type = result.error_type or "unknown"
        recovery_path = ERROR_RECOVERY.get(error_type, "retry")

        if recovery_path == "pause_human":
            # agent_refusal or infrastructure_failure: no point retrying.
            # Surface to a human for triage.
            if log_path:
                log_event(log_path, {
                    "event": "retry_paused_for_human",
                    "feature": feature,
                    "attempt": attempt,
                    "error_type": error_type,
                    "recovery": recovery_path,
                })

            return RetryResult(
                success=False,
                attempts=attempt,
                final_output=result.output,
                learnings_path=learnings_path,
                paused=True,
                total_cost_usd=total_cost,
            )

        elif recovery_path == "pause_session":
            # budget_exhausted: session-wide condition — zero retries.
            # Pause immediately so the runner can stop new dispatches.
            if log_path:
                log_event(log_path, {
                    "event": "retry_paused_budget_exhausted",
                    "feature": feature,
                    "attempt": attempt,
                    "error_type": error_type,
                    "recovery": recovery_path,
                })

            return RetryResult(
                success=False,
                attempts=attempt,
                final_output=result.output,
                learnings_path=learnings_path,
                paused=True,
                total_cost_usd=total_cost,
                error_type="budget_exhausted",
            )

        elif recovery_path == "escalate":
            # Model-tier escalation ladder: Haiku → Sonnet → Opus (Req 8).
            # Upgrade the model for the next attempt on every escalate failure.
            # If already at Opus, the ladder is exhausted — pause for human.
            next_model = MODEL_ESCALATION_LADDER.get(current_model)

            if next_model is None:
                # Already at max tier (opus); surface to human for triage.
                if log_path:
                    log_event(log_path, {
                        "event": "retry_paused_for_human",
                        "feature": feature,
                        "attempt": attempt,
                        "error_type": error_type,
                        "model": current_model,
                        "reason": "escalation ladder exhausted at opus",
                    })

                return RetryResult(
                    success=False,
                    attempts=attempt,
                    final_output=result.output,
                    learnings_path=learnings_path,
                    paused=True,
                    total_cost_usd=total_cost,
                )

            if log_path:
                log_event(log_path, {
                    "event": "retry_escalate",
                    "feature": feature,
                    "attempt": attempt,
                    "error_type": error_type,
                    "from_model": current_model,
                    "to_model": next_model,
                })

            current_model = next_model

        # recovery_path == "retry": agent_timeout, task_failure, unknown
        # → immediate retry with accumulated learnings (fresh process)

    # All retries exhausted
    if log_path:
        log_event(log_path, {
            "event": "retry_exhausted",
            "feature": feature,
            "total_attempts": total_attempts,
            "total_cost_usd": total_cost,
        })

    return RetryResult(
        success=False,
        attempts=total_attempts,
        final_output=result.output,
        learnings_path=learnings_path,
        paused=True,
        total_cost_usd=total_cost,
    )
