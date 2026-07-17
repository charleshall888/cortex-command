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
from importlib.resources import files
from pathlib import Path
from typing import Optional

# 374 Phase-4 fold (R15 write path): this module no longer DECIDES or appends
# lifecycle transition rows itself. The implement→review entry transition and the
# review→complete completion transition are routed through the shared ``advance``
# body (``cortex_command.lifecycle.advance.advance``), which owns the decision +
# emission (the legacy vocabulary, gate-checked and idempotent — #397 retired
# the claim/commit machine rows). This module's review.md/verdict
# reads are demoted to *input-gathering* — the gathered verdict/cycle/detected-
# phase are passed as arguments. It emits NO transition-vocabulary rows of its own
# (the positive fold-completion discriminator in tests/test_fold_completion.py
# fails if a log_event/log_event_at transition emission is re-introduced here).
from cortex_command.common import detect_lifecycle_phase
from cortex_command.lifecycle.advance import advance
from cortex_command.overnight.deferral import DeferralQuestion, write_deferral
from cortex_command.pipeline.dispatch import dispatch_task
from cortex_command.pipeline.merge import merge_feature

logger = logging.getLogger(__name__)


def _current_phase(feature_events_log: Path) -> str:
    """Return the feature's artifact-detected phase — the value the claim/commit
    primitive's from_state gate compares against (``common.detect_lifecycle_phase``).

    Passing this as ``advance``'s ``from_state`` makes the gate a tautology for
    these forced overnight transitions (the feature IS at its detected phase),
    so ``advance`` records the arm's transition rather than refusing on a
    gate-mismatch. Defaults to ``"implement"`` when the phase cannot be read.
    """
    return str(detect_lifecycle_phase(feature_events_log.parent).get("phase") or "implement")


def _advance_to_review(feature: str, feature_events_log: Path) -> None:
    """Route the implement→review entry transition through the shared advance body.

    ``dispatch_review`` is only reached for review-required features (the
    ``outcome_router`` gate is ``requires_review(tier, criticality) or corrupted``
    — the same matrix ``implement_transition._resolve_route`` applies), so the
    implement-transition arm routes to ``review`` and emits ``phase_transition``
    implement→review. Best-effort: a gate-mismatch/refusal is a benign no-op (the
    feature is already at/past review); the returned envelope is ignored."""
    advance(
        verb="implement-transition",
        feature=feature,
        mode="transition",
        from_state=_current_phase(feature_events_log),
        log_path=feature_events_log,
    )


def _advance_review_complete(feature: str, cycle: int, feature_events_log: Path) -> None:
    """Route the review→complete completion through the shared advance body.

    Composes the review.approved arm (``review_verdict`` → ``phase_transition``
    review→complete) — the events-first completion signal (ADR-0025). The legacy
    ``feature_complete`` telemetry row (with ``merge_anchor: "review"``) the
    pre-fold path hand-appended is NOT emitted by the advance/B1 bodies; downstream
    metrics (``cortex_command/pipeline/metrics.py:extract_feature_metrics``) instead
    detect completion off the ``phase_transition→complete`` row and default the
    absent ``merge_anchor`` to ``"review"``. Best-effort; envelope ignored."""
    advance(
        verb="review-verdict",
        feature=feature,
        verdict="APPROVED",
        cycle=cycle,
        drift="none",
        from_state=_current_phase(feature_events_log),
        log_path=feature_events_log,
    )


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
        merge_sha: The live integration-branch merge commit from the
            cycle-1 rework re-merge, threaded from the re-merge's
            ``MergeResult.merge_sha`` so a later rollback reverts the
            re-merge SHA rather than the original first-merge SHA. It is
            ``None`` on every path that did not perform a successful
            rework re-merge (no rework, fix-agent failure, or the re-merge
            itself failed).
        could_not_run: Orthogonal positive discriminator for the
            *could-not-run review* case — the review agent completed
            (``DispatchResult.success == True``) but produced no usable
            verdict, so the resolved verdict is the synthetic ``ERROR``
            sentinel. Distinguished from a genuine dispatch crash
            (``success == False``), which also resolves to ``ERROR`` but
            leaves this flag ``False``. Downstream outcome routing keys on
            this flag to preserve the merge and flag for human re-review
            rather than reverting a clean integration. It is orthogonal to
            ``verdict``: the verdict vocabulary is unchanged.
    """

    approved: bool
    deferred: bool
    verdict: str
    cycle: int
    issues: list[str] = field(default_factory=list)
    merge_sha: Optional[str] = None
    could_not_run: bool = False


_ERROR_RESULT: dict = {"verdict": "ERROR", "cycle": 0, "issues": []}


def parse_verdict(review_path: Path) -> dict:
    """Extract the JSON verdict block from a review.md file.

    Reads the file at *review_path*, searches for a fenced JSON code block
    (````` ```json ... ``` `````) containing the verdict object, and returns
    the parsed dict.

    Args:
        review_path: Path to the review.md file (e.g.
            ``cortex/lifecycle/{feature}/review.md``).

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

_PROMPT_TEMPLATE_PATH = files("cortex_command.pipeline.prompts").joinpath("review.md")


def _load_review_prompt(
    feature: str,
    spec_excerpt: str,
    worktree_path: Path,
    branch_name: str,
    review_md_path: str,
) -> str:
    """Load the review prompt template and substitute placeholders.

    Args:
        feature: Feature name for the review.
        spec_excerpt: Specification text excerpt.
        worktree_path: Path to the git worktree.
        branch_name: Git branch name.
        review_md_path: Absolute main-repo path the agent must write
            review.md to. Required (no default) so a missed render seam
            fails at the call rather than rendering an unsubstituted
            ``{review_md_path}`` literal that would re-resolve against the
            agent's worktree cwd.

    Returns:
        Formatted prompt string.
    """
    template = _PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
    for key, value in {
        "feature": feature,
        "spec_excerpt": spec_excerpt,
        "worktree_path": str(worktree_path),
        "branch_name": branch_name,
        "review_md_path": review_md_path,
    }.items():
        template = template.replace(f"{{{key}}}", value)
    return template


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
    lifecycle_base: Path = Path("cortex/lifecycle"),
    deferred_dir: Path = Path("cortex/lifecycle/deferred"),
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
        - **ERROR** (agent failure or unparseable verdict — the
          could-not-run path): writes the review_verdict ERROR event AND a
          SEVERITY_BLOCKING deferral file carrying the verdict so the crash
          surfaces in the morning report; returns
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

    # (1) Record phase_transition implement -> review via the shared advance body.
    _advance_to_review(feature, feature_events_log)

    # (2) Read spec for excerpt
    try:
        spec_excerpt = spec_path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as exc:
        logger.warning(
            "Cannot read spec for review of %s: %s — skipping review",
            feature, exc,
        )
        # FOLD (374): an ERROR is not a lifecycle transition (no review ran) and
        # ERROR is not a canonical verdict the advance/B1 review-verdict body
        # admits — so no transition-vocabulary row is emitted here. The
        # SEVERITY-carrying record is the ReviewResult/deferral, not events.log.
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
            review_md_path=str(review_md_path),
        )
    except (FileNotFoundError, OSError) as exc:
        logger.error(
            "Cannot load review prompt template: %s", exc,
        )
        # FOLD (374): ERROR is not a lifecycle transition — no events.log row.
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
        skill="review",
    )

    # (5) Resolve verdict. A failed dispatch (result.success == False) forces
    # the ERROR sentinel WITHOUT parsing review.md, so a stale prior-cycle
    # verdict (e.g. an on-disk APPROVED from an earlier run) can never approve
    # a feature whose fresh review dispatch crashed. Only consult the on-disk
    # review.md when the dispatch itself succeeded.
    if result.success:
        verdict_dict = parse_verdict(review_md_path)
    else:
        verdict_dict = dict(_ERROR_RESULT)
    verdict_str = verdict_dict.get("verdict", "ERROR")
    cycle = verdict_dict.get("cycle", 0)
    issues = verdict_dict.get("issues", [])

    # (6) Handle APPROVED — route the review→complete transition through the
    # shared advance body (review_verdict → phase_transition review→complete).
    if verdict_str == "APPROVED":
        _advance_review_complete(feature, cycle, feature_events_log)
        return ReviewResult(
            approved=True,
            deferred=False,
            verdict="APPROVED",
            cycle=cycle,
            issues=issues,
        )

    # (7) Handle ERROR (agent failure or unparseable verdict) — the
    # could-not-run path. Write a SEVERITY_BLOCKING deferral file carrying
    # the verdict (R6) so a crashed/errored review surfaces in the morning
    # report rather than silently passing as a bare FEATURE_DEFERRED event.
    if verdict_str == "ERROR":
        # could_not_run is the POSITIVE discriminator: True only when the
        # review agent completed (result.success) but produced no usable
        # verdict, False when the dispatch itself crashed (success == False).
        # Both land here because a crashed dispatch resolves to the ERROR
        # sentinel above, so the flag — not the verdict — is what downstream
        # routing keys on to preserve vs. revert the merge.
        could_not_run = result.success
        # FOLD (374): ERROR is not a lifecycle transition — no events.log row.
        _write_review_deferral(
            feature, verdict_str, cycle, issues, deferred_dir,
            could_not_run=could_not_run,
        )
        return ReviewResult(
            approved=False,
            deferred=True,
            verdict="ERROR",
            cycle=cycle,
            issues=issues,
            could_not_run=could_not_run,
        )

    # (8) Handle REJECTED at any cycle — write deferral file
    if verdict_str == "REJECTED":
        # FOLD (374): the pre-fold path recorded a review_verdict-only row (no
        # phase_transition — the feature stayed at "review" for human triage).
        # Routing REJECTED through the advance review-verdict body would emit a
        # phase_transition review→escalated (its routed arm), CHANGING the
        # events-first projection review→escalated. To preserve the projection,
        # no transition-vocabulary row is emitted; the deferral is the record.
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
        # FOLD (374): the pre-fold path recorded a review_verdict-only row (no
        # phase_transition). The rework loop below is driven by verdict_str, not
        # by an events.log emission, so dropping the informational verdict row
        # preserves the events-first projection (the feature stays at "review"
        # through the rework window; a cycle-2 APPROVED then routes review→complete
        # via _advance_review_complete).

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
            skill="review-fix",
            cycle=1,
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
                review_md_path=str(review_md_path),
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
            skill="review-fix",
            cycle=2,
        )

        # (9g) Resolve cycle 2 verdict. As with cycle 1, a failed cycle-2
        # dispatch (cycle2_result.success == False) forces the ERROR sentinel
        # WITHOUT parsing review.md, so a stale verdict on disk cannot approve
        # a feature whose cycle-2 review dispatch crashed.
        if cycle2_result.success:
            cycle2_verdict_dict = parse_verdict(review_md_path)
        else:
            cycle2_verdict_dict = dict(_ERROR_RESULT)
        cycle2_verdict_str = cycle2_verdict_dict.get("verdict", "ERROR")
        cycle2_cycle = cycle2_verdict_dict.get("cycle", 0)
        cycle2_issues = cycle2_verdict_dict.get("issues", [])

        # Normalize any non-canonical cycle-2 verdict to the ERROR sentinel,
        # mirroring the cycle-1 "Unexpected verdict value — treat as ERROR"
        # fall-through. Without this, cycle-2 would special-case only APPROVED
        # and return every other string — including a non-canonical "BLOCKED"
        # or a file-present-unparseable verdict — verbatim, leaving cycle-1 and
        # cycle-2 asymmetric. Canonical non-APPROVED verdicts pass through
        # untouched; a crashed dispatch (success == False) already resolved to
        # ERROR above and stays ERROR here.
        if cycle2_verdict_str not in {"APPROVED", "CHANGES_REQUESTED", "REJECTED", "ERROR"}:
            logger.warning(
                "Unexpected cycle-2 review verdict %r for %s — treating as ERROR",
                cycle2_verdict_str, feature,
            )
            cycle2_issues = cycle2_issues + [
                f"unexpected verdict value: {cycle2_verdict_str}"
            ]
            cycle2_verdict_str = "ERROR"

        # (9h) If APPROVED, return success — route review→complete via advance.
        if cycle2_verdict_str == "APPROVED":
            _advance_review_complete(feature, cycle2_cycle, feature_events_log)
            return ReviewResult(
                approved=True,
                deferred=False,
                verdict="APPROVED",
                cycle=cycle2_cycle,
                issues=cycle2_issues,
                merge_sha=remerge_result.merge_sha,
            )

        # (9i) Non-APPROVED cycle 2 — write deferral and return deferred.
        # could_not_run mirrors cycle 1: True only when the cycle-2 review
        # agent completed (cycle2_result.success) but produced no usable
        # verdict (resolved to the ERROR sentinel, post-normalization above).
        # A canonical CHANGES_REQUESTED/REJECTED (review ran and said no) and a
        # crashed dispatch (success == False) both leave the flag False.
        cycle2_could_not_run = (
            cycle2_result.success and cycle2_verdict_str == "ERROR"
        )
        # FOLD (374): a non-APPROVED cycle-2 verdict is not an advancing
        # transition — no transition-vocabulary row is emitted (the deferral is
        # the record; the events-first projection stays at "review").
        _write_review_deferral(
            feature, cycle2_verdict_str, cycle2_cycle, cycle2_issues, deferred_dir,
            could_not_run=cycle2_could_not_run,
        )
        return ReviewResult(
            approved=False,
            deferred=True,
            verdict=cycle2_verdict_str,
            cycle=cycle2_cycle,
            issues=cycle2_issues,
            merge_sha=remerge_result.merge_sha,
            could_not_run=cycle2_could_not_run,
        )

    # Unexpected verdict value — treat as ERROR. This catch-all is only
    # reachable when parse_verdict() returned a non-canonical verdict string
    # (e.g. "BLOCKED"), which means the dispatch completed and a file was
    # parsed — a crashed dispatch (success == False) resolves to the ERROR
    # sentinel above and is handled by the explicit ERROR branch, never here.
    # So this is always a could-not-run case (review ran, no usable verdict);
    # expressing the flag as result.success keeps it correct by construction.
    could_not_run = result.success
    logger.warning(
        "Unexpected review verdict %r for %s — treating as ERROR",
        verdict_str, feature,
    )
    # FOLD (374): a non-canonical/ERROR verdict is not a lifecycle transition —
    # no events.log row (the ReviewResult/deferral is the record).
    return ReviewResult(
        approved=False,
        deferred=True,
        verdict="ERROR",
        cycle=cycle,
        issues=issues + [f"unexpected verdict value: {verdict_str}"],
        could_not_run=could_not_run,
    )


def _write_review_deferral(
    feature: str,
    verdict: str,
    cycle: int,
    issues: list[str],
    deferred_dir: Path,
    could_not_run: bool = False,
) -> Path:
    """Write a deferral file for a non-APPROVED review verdict.

    Used for every could-not-run / review-said-no outcome (ERROR, REJECTED,
    or a non-cycle-1 CHANGES_REQUESTED). The deferral does not assert that the
    feature still sits on the integration branch: the caller reverts the live
    merge before surfacing, so the post-revert surface ("reverted — safe to
    re-review") is reconciled by the report, not hard-coded here. The legacy
    "do NOT re-run" annotation is reserved for the dependent-conflict abort
    case, which the caller escalates separately when the revert genuinely fails.

    Args:
        feature: Feature name.
        verdict: The review verdict (ERROR, REJECTED, or CHANGES_REQUESTED).
        cycle: Review cycle number.
        issues: List of issue descriptions from the review.
        could_not_run: Whether this deferral is the *could-not-run review*
            case (review agent completed but produced no usable verdict). The
            flag is recorded in the deferral's Context so the on-disk deferral
            and the caller's FEATURE_DEFERRED event cannot disagree on whether
            the merge should be preserved (could-not-run) vs. reverted.
        deferred_dir: Directory for deferral files.

    Returns:
        Path to the written deferral file.
    """
    issues_text = "\n".join(f"- {issue}" for issue in issues) if issues else "- (no issues listed)"
    could_not_run_note = (
        " (could-not-run: review agent completed but produced no usable "
        "verdict — preserve the merge for human re-review)"
        if could_not_run
        else ""
    )
    question = DeferralQuestion(
        feature=feature,
        question_id=0,
        severity="blocking",
        context=f"Review cycle {cycle} returned verdict: {verdict}{could_not_run_note}",
        question=f"Feature {feature} received {verdict} during overnight review. Issues need human triage.",
        options_considered=[
            "Address review feedback and re-submit",
            "Override review verdict and mark complete",
            "Revise specification and re-implement",
        ],
        pipeline_attempted=f"Overnight review agent returned {verdict} at cycle {cycle}.\n\nIssues:\n{issues_text}",
    )
    # Resume-idempotent: re-running the defer path for an already-deferred
    # feature (e.g. on session resume) returns the existing deferral file rather
    # than minting a duplicate -q00N.md. The deferred-dir scan (question_id=0)
    # is the single reconciled question-id source shared with the except-crash
    # path in outcome_router.
    return write_deferral(question, deferred_dir, idempotent=True)
