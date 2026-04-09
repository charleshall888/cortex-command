"""Review dispatch types and verdict parsing for overnight review gating.

Provides the ReviewResult dataclass for structured review outcomes,
parse_verdict() for extracting the JSON verdict block from review.md files
written by review agents, and dispatch_review() for orchestrating a single
review cycle with verdict handling.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from claude.overnight.deferral import DeferralQuestion, write_deferral
from claude.pipeline.dispatch import dispatch_task
from claude.pipeline.merge import merge_feature
from claude.pipeline.state import log_event

logger = logging.getLogger(__name__)


@dataclass
class ReviewResult:
    """Structured result of a review dispatch cycle.

    Fields:
        approved: Whether the review verdict was APPROVED.
        deferred: Whether the feature was deferred (non-APPROVED after
            rework exhausted, or review failure).
        verdict: Raw verdict string (APPROVED, CHANGES_REQUESTED,
            REJECTED, or ERROR).
        cycle: Review cycle number (0 for errors, 1-2 for real reviews).
        issues: List of issue descriptions from the review agent.
    """

    approved: bool
    deferred: bool
    verdict: str
    cycle: int
    issues: list[str] = field(default_factory=list)


_ERROR_RESULT: dict = {"verdict": "ERROR", "cycle": 0, "issues": []}


def parse_verdict(review_path: Path) -> dict:
    """Extract the JSON verdict block from a review.md file.

    Reads the file at *review_path*, searches for a fenced JSON code block
    (````` ```json ... ``` `````) containing the verdict object, and returns
    the parsed dict.

    Args:
        review_path: Path to the review.md file (e.g.
            ``lifecycle/{feature}/review.md``).

    Returns:
        Parsed verdict dict with at least ``verdict``, ``cycle``, and
        ``issues`` keys.  Returns ``{"verdict": "ERROR", "cycle": 0,
        "issues": []}`` if the file does not exist or the JSON block is
        malformed.
    """
    try:
        content = review_path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return dict(_ERROR_RESULT)

    match = re.search(r"```json\s*(\{.*?\})\s*```", content, re.DOTALL)
    if not match:
        return dict(_ERROR_RESULT)

    try:
        return json.loads(match.group(1))
    except (json.JSONDecodeError, ValueError):
        return dict(_ERROR_RESULT)


# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

_PROMPT_TEMPLATE_PATH = Path(__file__).resolve().parent / "prompts" / "review.md"


def _load_review_prompt(
    feature: str,
    spec_excerpt: str,
    worktree_path: Path,
    branch_name: str,
) -> str:
    """Load the review prompt template and substitute placeholders.

    Args:
        feature: Feature name for the review.
        spec_excerpt: Specification text excerpt.
        worktree_path: Path to the git worktree.
        branch_name: Git branch name.

    Returns:
        Formatted prompt string.
    """
    template = _PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
    return template.format(
        feature=feature,
        spec_excerpt=spec_excerpt,
        worktree_path=worktree_path,
        branch_name=branch_name,
    )


# ---------------------------------------------------------------------------
# Dispatch review
# ---------------------------------------------------------------------------

async def dispatch_review(
    feature: str,
    worktree_path: Path,
    branch: str,
    spec_path: Path,
    complexity: str,
    criticality: str,
    lifecycle_base: Path = Path("lifecycle"),
    deferred_dir: Path = Path("lifecycle/deferred"),
    integration_branch: str = "",
    base_branch: str = "main",
    test_command: str | None = None,
    repo_path: Path | None = None,
    log_path: Path | None = None,
) -> ReviewResult:
    """Dispatch a review agent and handle its verdict.

    Orchestrates a single review cycle: writes the phase transition from
    implement to review, dispatches a review agent via ``dispatch_task()``,
    then parses and handles the verdict from the review.md artifact the
    agent writes.

    Verdict handling:
        - **APPROVED**: writes review_verdict, phase_transition
          review->complete, and feature_complete events; returns
          ``ReviewResult(approved=True)``.
        - **ERROR** (agent failure or unparseable verdict): writes
          review_verdict ERROR event; returns
          ``ReviewResult(deferred=True)``.
        - **REJECTED** (any cycle): writes deferral file; returns
          ``ReviewResult(deferred=True)``.
        - **CHANGES_REQUESTED** (cycle 1): writes review feedback to
          ``learnings/orchestrator-note.md``, dispatches a fix agent,
          checks SHA circuit breaker, re-merges via ``merge_feature()``,
          dispatches cycle 2 review, and handles the cycle 2 verdict.
          Any failure along the rework path writes a deferral and returns
          ``ReviewResult(deferred=True)``.
        - **CHANGES_REQUESTED** (cycle 2+): writes deferral file; returns
          ``ReviewResult(deferred=True)``.

    Args:
        feature: Feature name.
        worktree_path: Path to the git worktree containing the feature.
        branch: Git branch name (e.g. ``pipeline/my-feature``).
        spec_path: Path to the feature's spec.md file.
        complexity: Complexity tier (``trivial``, ``simple``, ``complex``).
        criticality: Criticality level (``low``, ``medium``, ``high``,
            ``critical``).
        lifecycle_base: Base directory for lifecycle data.
        deferred_dir: Directory for deferral files.
        integration_branch: Name of the integration branch (unused in
            single-cycle dispatch; reserved for rework loop).
        base_branch: Name of the base branch (default ``main``).
        test_command: Optional test command (unused in review dispatch;
            reserved for rework loop).
        repo_path: Pre-computed effective merge repo path from the
            caller (passed to ``dispatch_task`` as ``repo_root``).
        log_path: Pipeline events log path for merge event logging
            (passed to ``dispatch_task``).

    Returns:
        A ``ReviewResult`` describing the outcome.
    """
    feature_events_log = lifecycle_base / feature / "events.log"
    review_md_path = lifecycle_base / feature / "review.md"

    # (1) Write phase_transition implement -> review
    log_event(feature_events_log, {
        "event": "phase_transition",
        "feature": feature,
        "from": "implement",
        "to": "review",
    })

    # (2) Read spec for excerpt
    try:
        spec_excerpt = spec_path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as exc:
        logger.warning(
            "Cannot read spec for review of %s: %s — skipping review",
            feature, exc,
        )
        log_event(feature_events_log, {
            "event": "review_verdict",
            "feature": feature,
            "verdict": "ERROR",
            "cycle": 0,
            "issues": [f"spec not readable: {exc}"],
        })
        return ReviewResult(
            approved=False,
            deferred=True,
            verdict="ERROR",
            cycle=0,
            issues=[f"spec not readable: {exc}"],
        )

    # (3) Load prompt template and substitute placeholders
    try:
        prompt = _load_review_prompt(
            feature=feature,
            spec_excerpt=spec_excerpt,
            worktree_path=worktree_path,
            branch_name=branch,
        )
    except (FileNotFoundError, OSError) as exc:
        logger.error(
            "Cannot load review prompt template: %s", exc,
        )
        log_event(feature_events_log, {
            "event": "review_verdict",
            "feature": feature,
            "verdict": "ERROR",
            "cycle": 0,
            "issues": [f"prompt template not readable: {exc}"],
        })
        return ReviewResult(
            approved=False,
            deferred=True,
            verdict="ERROR",
            cycle=0,
            issues=[f"prompt template not readable: {exc}"],
        )

    # (4) Dispatch review agent
    system_prompt = (
        "You are a code reviewer. Read the feature implementation in the "
        "worktree and write your review to disk as instructed. Do NOT "
        "modify any source files — this is a read-only review."
    )

    result = await dispatch_task(
        feature=feature,
        task=prompt,
        worktree_path=worktree_path,
        complexity=complexity,
        system_prompt=system_prompt,
        log_path=log_path,
        criticality=criticality,
        repo_root=repo_path,
    )

    # (5) Parse verdict from review.md
    verdict_dict = parse_verdict(review_md_path)
    verdict_str = verdict_dict.get("verdict", "ERROR")
    cycle = verdict_dict.get("cycle", 0)
    issues = verdict_dict.get("issues", [])

    # (6) Handle APPROVED
    if verdict_str == "APPROVED":
        log_event(feature_events_log, {
            "event": "review_verdict",
            "feature": feature,
            "verdict": "APPROVED",
            "cycle": cycle,
            "issues": issues,
        })
        log_event(feature_events_log, {
            "event": "phase_transition",
            "feature": feature,
            "from": "review",
            "to": "complete",
        })
        log_event(feature_events_log, {
            "event": "feature_complete",
            "feature": feature,
        })
        return ReviewResult(
            approved=True,
            deferred=False,
            verdict="APPROVED",
            cycle=cycle,
            issues=issues,
        )

    # (7) Handle ERROR (agent failure or unparseable verdict)
    if verdict_str == "ERROR":
        log_event(feature_events_log, {
            "event": "review_verdict",
            "feature": feature,
            "verdict": "ERROR",
            "cycle": cycle,
            "issues": issues,
        })
        return ReviewResult(
            approved=False,
            deferred=True,
            verdict="ERROR",
            cycle=cycle,
            issues=issues,
        )

    # (8) Handle REJECTED at any cycle — write deferral file
    if verdict_str == "REJECTED":
        log_event(feature_events_log, {
            "event": "review_verdict",
            "feature": feature,
            "verdict": "REJECTED",
            "cycle": cycle,
            "issues": issues,
        })
        _write_review_deferral(feature, verdict_str, cycle, issues, deferred_dir)
        return ReviewResult(
            approved=False,
            deferred=True,
            verdict="REJECTED",
            cycle=cycle,
            issues=issues,
        )

    # (9) Handle CHANGES_REQUESTED — rework loop (cycle 1 only)
    if verdict_str == "CHANGES_REQUESTED":
        log_event(feature_events_log, {
            "event": "review_verdict",
            "feature": feature,
            "verdict": "CHANGES_REQUESTED",
            "cycle": cycle,
            "issues": issues,
        })

        # Only attempt rework for cycle 1; later cycles fall through to deferral
        if cycle != 1:
            _write_review_deferral(feature, verdict_str, cycle, issues, deferred_dir)
            return ReviewResult(
                approved=False,
                deferred=True,
                verdict="CHANGES_REQUESTED",
                cycle=cycle,
                issues=issues,
            )

        # (9a) Write review feedback to orchestrator-note.md
        learnings_dir = lifecycle_base / feature / "learnings"
        learnings_dir.mkdir(parents=True, exist_ok=True)
        orchestrator_note_path = learnings_dir / "orchestrator-note.md"
        issues_text = "\n".join(f"- {issue}" for issue in issues) if issues else "- (no issues listed)"
        orchestrator_note_path.write_text(
            f"# Review Feedback (Cycle 1)\n\n{issues_text}\n",
            encoding="utf-8",
        )

        # (9b) Capture SHA before fix agent dispatch
        before_sha_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=worktree_path,
        )
        before_sha = before_sha_result.stdout.strip()

        # (9c) Dispatch fix agent with review findings + spec excerpt
        fix_prompt = (
            f"## Review Feedback\n{issues_text}\n\n"
            f"## Spec\n{spec_excerpt}\n\n"
            f"Fix only the flagged issues in the worktree at {worktree_path}."
        )
        fix_system_prompt = (
            "You are a code fixer. Read the review feedback and fix only "
            "the flagged issues. Do NOT introduce new features or refactor "
            "beyond what is needed to address the review."
        )

        fix_result = await dispatch_task(
            feature=feature,
            task=fix_prompt,
            worktree_path=worktree_path,
            complexity=complexity,
            system_prompt=fix_system_prompt,
            log_path=log_path,
            criticality=criticality,
            repo_root=repo_path,
        )

        # Handle fix agent failure — defer with cycle 1 feedback + failure reason
        if not fix_result.success:
            logger.warning(
                "Fix agent failed for %s: %s", feature, fix_result.error_detail,
            )
            _write_review_deferral(
                feature, "CHANGES_REQUESTED", cycle,
                issues + [f"Fix agent failed: {fix_result.error_detail}"],
                deferred_dir,
            )
            return ReviewResult(
                approved=False,
                deferred=True,
                verdict="CHANGES_REQUESTED",
                cycle=cycle,
                issues=issues + [f"Fix agent failed: {fix_result.error_detail}"],
            )

        # (9d) SHA circuit breaker — if before_sha == after_sha, defer immediately
        after_sha_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=worktree_path,
        )
        after_sha = after_sha_result.stdout.strip()

        if before_sha == after_sha:
            logger.warning(
                "Fix agent made no commits for %s (SHA unchanged: %s)",
                feature, before_sha,
            )
            _write_review_deferral(
                feature, "CHANGES_REQUESTED", cycle,
                issues + ["Fix agent made no changes (SHA unchanged)"],
                deferred_dir,
            )
            return ReviewResult(
                approved=False,
                deferred=True,
                verdict="CHANGES_REQUESTED",
                cycle=cycle,
                issues=issues + ["Fix agent made no changes (SHA unchanged)"],
            )

        # (9e) Re-merge via merge_feature (ci_check=False for post-rework merge)
        remerge_result = merge_feature(
            feature,
            base_branch=base_branch,
            test_command=test_command,
            log_path=log_path,
            ci_check=False,
            branch=branch,
            repo_path=repo_path,
        )

        if not remerge_result.success:
            logger.warning(
                "Re-merge failed for %s after rework: %s",
                feature, remerge_result.error,
            )
            _write_review_deferral(
                feature, "CHANGES_REQUESTED", cycle,
                issues + [f"Re-merge failed: {remerge_result.error}"],
                deferred_dir,
            )
            return ReviewResult(
                approved=False,
                deferred=True,
                verdict="CHANGES_REQUESTED",
                cycle=cycle,
                issues=issues + [f"Re-merge failed: {remerge_result.error}"],
            )

        # (9f) Dispatch cycle 2 review
        try:
            cycle2_prompt = _load_review_prompt(
                feature=feature,
                spec_excerpt=spec_excerpt,
                worktree_path=worktree_path,
                branch_name=branch,
            )
            cycle2_prompt += (
                "\n\nNote: This is review cycle 2. A previous review returned "
                "CHANGES_REQUESTED and a fix agent has addressed the feedback. "
                "Focus on whether the flagged issues were resolved."
            )
        except (FileNotFoundError, OSError) as exc:
            logger.error("Cannot load review prompt for cycle 2: %s", exc)
            _write_review_deferral(
                feature, "CHANGES_REQUESTED", cycle,
                issues + [f"Cycle 2 prompt template not readable: {exc}"],
                deferred_dir,
            )
            return ReviewResult(
                approved=False,
                deferred=True,
                verdict="CHANGES_REQUESTED",
                cycle=cycle,
                issues=issues + [f"Cycle 2 prompt template not readable: {exc}"],
            )

        cycle2_result = await dispatch_task(
            feature=feature,
            task=cycle2_prompt,
            worktree_path=worktree_path,
            complexity=complexity,
            system_prompt=system_prompt,
            log_path=log_path,
            criticality=criticality,
            repo_root=repo_path,
        )

        # (9g) Parse cycle 2 verdict
        cycle2_verdict_dict = parse_verdict(review_md_path)
        cycle2_verdict_str = cycle2_verdict_dict.get("verdict", "ERROR")
        cycle2_cycle = cycle2_verdict_dict.get("cycle", 0)
        cycle2_issues = cycle2_verdict_dict.get("issues", [])

        # (9h) If APPROVED, return success
        if cycle2_verdict_str == "APPROVED":
            log_event(feature_events_log, {
                "event": "review_verdict",
                "feature": feature,
                "verdict": "APPROVED",
                "cycle": cycle2_cycle,
                "issues": cycle2_issues,
            })
            log_event(feature_events_log, {
                "event": "phase_transition",
                "feature": feature,
                "from": "review",
                "to": "complete",
            })
            log_event(feature_events_log, {
                "event": "feature_complete",
                "feature": feature,
            })
            return ReviewResult(
                approved=True,
                deferred=False,
                verdict="APPROVED",
                cycle=cycle2_cycle,
                issues=cycle2_issues,
            )

        # (9i) Non-APPROVED cycle 2 — write deferral and return deferred
        log_event(feature_events_log, {
            "event": "review_verdict",
            "feature": feature,
            "verdict": cycle2_verdict_str,
            "cycle": cycle2_cycle,
            "issues": cycle2_issues,
        })
        _write_review_deferral(
            feature, cycle2_verdict_str, cycle2_cycle, cycle2_issues, deferred_dir,
        )
        return ReviewResult(
            approved=False,
            deferred=True,
            verdict=cycle2_verdict_str,
            cycle=cycle2_cycle,
            issues=cycle2_issues,
        )

    # Unexpected verdict value — treat as ERROR
    logger.warning(
        "Unexpected review verdict %r for %s — treating as ERROR",
        verdict_str, feature,
    )
    log_event(feature_events_log, {
        "event": "review_verdict",
        "feature": feature,
        "verdict": "ERROR",
        "cycle": cycle,
        "issues": issues + [f"unexpected verdict value: {verdict_str}"],
    })
    return ReviewResult(
        approved=False,
        deferred=True,
        verdict="ERROR",
        cycle=cycle,
        issues=issues + [f"unexpected verdict value: {verdict_str}"],
    )


def _write_review_deferral(
    feature: str,
    verdict: str,
    cycle: int,
    issues: list[str],
    deferred_dir: Path,
) -> Path:
    """Write a deferral file for a non-APPROVED review verdict.

    Args:
        feature: Feature name.
        verdict: The review verdict (REJECTED or CHANGES_REQUESTED).
        cycle: Review cycle number.
        issues: List of issue descriptions from the review.
        deferred_dir: Directory for deferral files.

    Returns:
        Path to the written deferral file.
    """
    issues_text = "\n".join(f"- {issue}" for issue in issues) if issues else "- (no issues listed)"
    question = DeferralQuestion(
        feature=feature,
        question_id=0,
        severity="blocking",
        context=f"Review cycle {cycle} returned verdict: {verdict}",
        question=f"Feature {feature} received {verdict} during overnight review. Issues need human triage.",
        options_considered=[
            "Address review feedback and re-submit",
            "Override review verdict and mark complete",
            "Revise specification and re-implement",
        ],
        pipeline_attempted=f"Overnight review agent returned {verdict} at cycle {cycle}.\n\nIssues:\n{issues_text}",
    )
    return write_deferral(question, deferred_dir)
