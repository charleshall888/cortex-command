"""Post-merge test-failure recovery loop.

When a freshly merged feature causes test failures, this module orchestrates
recovery: first a flaky guard (re-merge with no changes to check for
transient failures), then up to two code-repair attempts via dispatched
agents with model escalation (sonnet -> opus).  A SHA-based circuit breaker
detects when the repair agent produces no commits, pausing before wasting
further budget.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class MergeRecoveryResult:
    """Structured result from the merge recovery loop.

    Attributes:
        success: Whether recovery succeeded (tests now pass after merge).
        attempts: Number of repair-cycle attempts made (0 if flaky or error).
        paused: True if the feature should be paused for human triage.
        flaky: True if the re-merge passed without any code changes.
        error: Description of what went wrong, or None on success.
    """

    success: bool
    attempts: int
    paused: bool
    flaky: bool
    error: Optional[str]


# ---------------------------------------------------------------------------
# Agent prompt template
# ---------------------------------------------------------------------------

RECOVERY_PROMPT_TEMPLATE = """\
## Post-Merge Test Failure Recovery

Feature: {feature}

The feature branch was merged into the base branch but tests now fail.
Your job is to fix the code so that the tests pass.

### Test output
```
{test_output}
```

### Merged diff (base..HEAD)
```
{merged_diff}
```

### Previous recovery learnings
{learnings}

### Hard constraints
- You may only modify a test file if the test was introduced by the feature's \
own commits AND you write an explicit deferral with reason in your exit report \
explaining why the test itself needs changing rather than the implementation.
- Focus on fixing the implementation code to make the existing tests pass.
- Commit all changes before finishing.
"""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_branch_sha(worktree_path: Path) -> str:
    """Return HEAD SHA in *worktree_path*, or empty string on failure."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=worktree_path,
            timeout=15,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except (subprocess.TimeoutExpired, OSError):
        return ""


def _get_merged_diff(worktree_path: Path, base_branch: str) -> str:
    """Return ``git diff base_branch..HEAD`` in *worktree_path*, truncated to 4000 chars."""
    try:
        result = subprocess.run(
            ["git", "diff", f"{base_branch}..HEAD"],
            capture_output=True,
            text=True,
            cwd=worktree_path,
            timeout=30,
        )
        output = result.stdout if result.returncode == 0 else ""
    except (subprocess.TimeoutExpired, OSError):
        output = ""
    return output[:4000]


def write_recovery_log_entry(
    feature: str,
    recovery_type: str,
    outcome: str,
    what_was_tried: str,
    result: str,
    *,
    _log_path: Optional[Path] = None,
) -> None:
    """Append a structured recovery attempt entry to recovery-log.md.

    Args:
        feature: Feature name (used to derive the log path when _log_path is None).
        recovery_type: One of "test_failure", "merge_conflict", "trivial_conflict".
        outcome: One of "success", "failed", "paused".
        what_was_tried: Brief description of what the agent or strategy attempted.
        result: Outcome summary — test output excerpt, resolved files, or error.
        _log_path: Optional override for the log path (for testing only).
    """
    log_path = _log_path or Path(f"lifecycle/{feature}/learnings/recovery-log.md")
    log_path.parent.mkdir(parents=True, exist_ok=True)

    n = 1
    if log_path.exists():
        content = log_path.read_text(encoding="utf-8")
        n = content.count("## Recovery attempt ") + 1

    timestamp = datetime.now(timezone.utc).isoformat()
    entry = (
        f"\n## Recovery attempt {n} — {timestamp}\n"
        f"Type: {recovery_type}\n"
        f"Outcome: {outcome}\n"
        f"What was tried: {what_was_tried}\n"
        f"Result: {result}\n"
    )
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(entry)


def _append_recovery_learnings(
    learnings_dir: Path,
    attempt: int,
    test_output: str,
    agent_output: str,
) -> None:
    """Append a structured block to ``progress.txt``.

    Uses the same format as ``retry.py``'s ``_append_learnings()``:
    separator line, attempt header with timestamp, task description,
    error, and output.
    """
    learnings_dir.mkdir(parents=True, exist_ok=True)
    progress_path = learnings_dir / "progress.txt"

    timestamp = datetime.now(timezone.utc).isoformat()

    # Truncate outputs to a reasonable size for prompt inclusion
    max_len = 2000
    truncated_test = test_output[:max_len] + "\n... (truncated)" if len(test_output) > max_len else test_output
    truncated_agent = agent_output[:max_len] + "\n... (truncated)" if len(agent_output) > max_len else agent_output

    entry = (
        f"\n{'=' * 60}\n"
        f"Attempt {attempt} | {timestamp}\n"
        f"{'=' * 60}\n"
        f"Task: post-merge test failure recovery\n"
        f"Error: tests still failing after repair attempt\n"
        f"Test output:\n{truncated_test}\n"
        f"Agent output:\n{truncated_agent}\n"
    )

    with open(progress_path, "a", encoding="utf-8") as f:
        f.write(entry)


# ---------------------------------------------------------------------------
# Main recovery function
# ---------------------------------------------------------------------------

async def recover_test_failure(
    feature: str,
    base_branch: str,
    test_output: str,
    branch: str,
    worktree_path: Optional[Path],
    learnings_dir: Path,
    test_command: Optional[str],
    pipeline_log_path: Optional[Path] = None,
    repo_path: Path | None = None,
) -> MergeRecoveryResult:
    """Attempt to recover from a post-merge test failure.

    Steps:
    1. Dirty-base check — ensure the repo root is clean after the revert.
    2. Flaky guard — re-merge without any code changes. If tests pass, the
       original failure was transient.
    3. Repair cycle — up to 2 attempts: dispatch a repair agent, then
       re-merge and re-test. Model escalation: sonnet on attempt 1,
       opus on attempt 2.

    Args:
        feature: Feature name.
        base_branch: Branch that was merged into (e.g. "main").
        test_output: Captured output from the failed test run.
        branch: Fully-qualified branch name (e.g. "pipeline/feat-2").
        worktree_path: Path to the feature's git worktree, or None.
        learnings_dir: Directory for progress.txt.
        test_command: Shell command for running tests.
        pipeline_log_path: Optional JSONL event log path.
        repo_path: Explicit repo root for cross-repo features (None = cwd).

    Returns:
        MergeRecoveryResult with recovery outcome details.
    """
    try:
        from cortex_command.pipeline.merge import merge_feature
        from cortex_command.pipeline.dispatch import dispatch_task

        # --- Dirty-base check ---
        try:
            repo_root_result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                check=True,
                timeout=15,
                cwd=str(repo_path) if repo_path else None,
            )
            repo_root = repo_root_result.stdout.strip()
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
            return MergeRecoveryResult(
                success=False,
                attempts=0,
                paused=True,
                flaky=False,
                error="failed to determine repo root",
            )

        status_result = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            capture_output=True,
            text=True,
            cwd=repo_root,
            timeout=15,
        )
        if status_result.stdout.strip():
            return MergeRecoveryResult(
                success=False,
                attempts=0,
                paused=True,
                flaky=False,
                error="dirty base branch after revert",
            )

        # --- Flaky guard: re-merge with no feature changes ---
        flaky_result = merge_feature(
            feature,
            base_branch,
            test_command,
            log_path=pipeline_log_path,
            ci_check=False,
            branch=branch,
            repo_path=repo_path,
        )
        if flaky_result.success:
            write_recovery_log_entry(
                feature=feature,
                recovery_type="test_failure",
                outcome="success",
                what_was_tried="flaky guard re-merge (no agent)",
                result="tests passed on re-merge without code changes",
            )
            return MergeRecoveryResult(
                success=True,
                attempts=0,
                paused=False,
                flaky=True,
                error=None,
            )

        # --- Repair cycle (up to 2 attempts) ---
        # Model escalation: sonnet for attempt 1, opus for attempt 2
        model_sequence = ["sonnet", "opus"]
        agent_output = "(no agent output)"

        for attempt in range(1, 3):
            if worktree_path is None:
                write_recovery_log_entry(
                    feature=feature,
                    recovery_type="test_failure",
                    outcome="paused",
                    what_was_tried="(no worktree available for repair agent)",
                    result="recovery could not start: no worktree_path provided",
                )
                return MergeRecoveryResult(
                    success=False,
                    attempts=attempt - 1,
                    paused=True,
                    flaky=False,
                    error="no worktree_path provided for repair cycle",
                )

            # 1. Capture SHA before repair
            before_sha = _get_branch_sha(worktree_path)

            # 2. Build prompt
            merged_diff = _get_merged_diff(worktree_path, base_branch)

            recovery_progress_path = learnings_dir / "progress.txt"
            learnings_text = ""
            if recovery_progress_path.exists():
                learnings_text = recovery_progress_path.read_text(encoding="utf-8")
            if not learnings_text:
                learnings_text = "(none yet)"

            prompt = RECOVERY_PROMPT_TEMPLATE.format(
                feature=feature,
                test_output=test_output,
                merged_diff=merged_diff,
                learnings=learnings_text,
            )

            # 3. Dispatch repair agent
            model = model_sequence[attempt - 1]
            dispatch_result = await dispatch_task(
                feature=feature,
                task=prompt,
                worktree_path=worktree_path,
                complexity="simple",
                system_prompt=prompt,
                log_path=pipeline_log_path,
                model_override=model,
                repo_root=repo_path,
            )
            agent_output = (dispatch_result.output or "")[:500] or "(no agent output captured)"

            # 4. Capture SHA after repair
            after_sha = _get_branch_sha(worktree_path)

            # 5. Circuit breaker: no commits produced
            if before_sha == after_sha:
                write_recovery_log_entry(
                    feature=feature,
                    recovery_type="test_failure",
                    outcome="paused",
                    what_was_tried=agent_output,
                    result="no commits produced by repair agent (circuit breaker)",
                )
                return MergeRecoveryResult(
                    success=False,
                    attempts=attempt,
                    paused=True,
                    flaky=False,
                    error="circuit_breaker: no commits produced",
                )

            # 6. Re-merge and test
            merge_result = merge_feature(
                feature,
                base_branch,
                test_command,
                log_path=pipeline_log_path,
                ci_check=False,
                branch=branch,
                repo_path=repo_path,
            )

            # 7. Success check
            if merge_result.success:
                write_recovery_log_entry(
                    feature=feature,
                    recovery_type="test_failure",
                    outcome="success",
                    what_was_tried=agent_output,
                    result=f"tests passed after repair attempt {attempt}",
                )
                return MergeRecoveryResult(
                    success=True,
                    attempts=attempt,
                    paused=False,
                    flaky=False,
                    error=None,
                )

            # 8. Write learnings
            merge_test_output = ""
            if merge_result.test_result:
                merge_test_output = merge_result.test_result.output
            _append_recovery_learnings(
                learnings_dir=learnings_dir,
                attempt=attempt,
                test_output=merge_test_output or test_output,
                agent_output="",
            )
            write_recovery_log_entry(
                feature=feature,
                recovery_type="test_failure",
                outcome="failed",
                what_was_tried=agent_output,
                result=(merge_test_output or test_output)[:300],
            )

        # --- Exhausted ---
        write_recovery_log_entry(
            feature=feature,
            recovery_type="test_failure",
            outcome="paused",
            what_was_tried=agent_output,
            result="recovery exhausted after 2 attempts",
        )
        return MergeRecoveryResult(
            success=False,
            attempts=2,
            paused=True,
            flaky=False,
            error="recovery exhausted",
        )

    except Exception as exc:
        return MergeRecoveryResult(
            success=False,
            attempts=0,
            paused=True,
            flaky=False,
            error=str(exc),
        )
