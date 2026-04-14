"""Batch runner execution module for overnight batch orchestration.

Manages a batch of features through the overnight lifecycle: parses
per-feature plans, dispatches tasks via the pipeline's dispatch/retry
infrastructure, handles deferrals, enforces a batch circuit breaker,
and auto-merges completed features to main.

Invoked by the orchestrator round agent:
    python3 -m claude.overnight.batch_runner --plan <path> --batch-id <N> ...
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from claude.common import (
    compute_dependency_batches,
    mark_task_done_in_plan,
    read_criticality,
    read_tier,
    requires_review,
)
from claude.pipeline.dispatch import dispatch_task
from claude.pipeline.conflict import ConflictClassification, dispatch_repair_agent, resolve_trivial_conflict
from claude.pipeline.merge import merge_feature
from claude.pipeline.parser import FeatureTask, parse_feature_plan, parse_master_plan
from claude.pipeline.retry import RetryResult, retry_task
from claude.pipeline.state import log_event as pipeline_log_event
from claude.pipeline.worktree import WorktreeInfo, cleanup_worktree, create_worktree
from claude.pipeline.merge_recovery import recover_test_failure

from claude.overnight.brain import (
    BrainAction,
    BrainContext,
    request_brain_decision,
)
from claude.overnight.deferral import (
    SEVERITY_BLOCKING,
    DeferralQuestion,
    EscalationEntry,
    _next_escalation_n,
    write_deferral,
    write_escalation,
)
from claude.overnight.throttle import (
    ConcurrencyManager,
    load_throttle_config,
)
from claude.overnight.state import load_state, save_batch_result, save_state, transition, OvernightFeatureStatus, _normalize_repo_key
from claude.overnight.events import (
    BACKLOG_WRITE_FAILED,
    BATCH_ASSIGNED,
    BATCH_BUDGET_EXHAUSTED,
    BRAIN_DECISION,
    CIRCUIT_BREAKER,
    FEATURE_COMPLETE,
    FEATURE_DEFERRED,
    FEATURE_FAILED,
    FEATURE_MERGED,
    FEATURE_PAUSED,
    FEATURE_START,
    HEARTBEAT,
    BATCH_COMPLETE,
    WORKER_MALFORMED_EXIT_REPORT,
    WORKER_NO_EXIT_REPORT,
    MERGE_CONFLICT_CLASSIFIED,
    MERGE_RECOVERY_START,
    MERGE_RECOVERY_FLAKY,
    MERGE_RECOVERY_SUCCESS,
    MERGE_RECOVERY_FAILED,
    REPAIR_AGENT_RESOLVED,
    SESSION_BUDGET_EXHAUSTED,
    TRIVIAL_CONFLICT_RESOLVED,
    log_event as overnight_log_event,
    read_events,
)
from claude.overnight.types import FeatureResult
from claude.overnight.constants import CIRCUIT_BREAKER_THRESHOLD
from claude.overnight.feature_executor import execute_feature

_LIFECYCLE_ROOT = Path(__file__).resolve().parents[2] / "lifecycle"

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config and result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class BatchConfig:
    """Configuration for a batch runner execution run.

    Fields:
        batch_id: Round/batch number (1-based).
        plan_path: Path to the per-batch master plan markdown.
        test_command: Shell command for post-merge tests, or None.
        base_branch: Branch to merge into.
        overnight_state_path: Path to overnight-state.json.
        overnight_events_path: Path to overnight-events.log.
        result_dir: Directory to write batch-{N}-results.json into.
        pipeline_events_path: Path to pipeline-events.log for worker logs.
    """

    batch_id: int
    plan_path: Path
    test_command: Optional[str] = None
    base_branch: str = "main"
    overnight_state_path: Path = _LIFECYCLE_ROOT / "overnight-state.json"
    overnight_events_path: Path = _LIFECYCLE_ROOT / "overnight-events.log"
    result_dir: Path = _LIFECYCLE_ROOT
    pipeline_events_path: Path = _LIFECYCLE_ROOT / "pipeline-events.log"
    throttle_tier: Optional[str] = None


@dataclass
class BatchResult:
    """Aggregated result of a batch runner execution.

    Fields:
        batch_id: Round/batch number.
        features_merged: Names of successfully merged features.
        features_paused: Dicts with name + error for paused features.
        features_deferred: Dicts with name + question_count for deferred.
        features_failed: Dicts with name + error for failed features.
        circuit_breaker_fired: Whether the batch circuit breaker triggered.
        key_files_changed: Mapping of feature -> list of changed file paths.
    """

    batch_id: int
    features_merged: list[str] = field(default_factory=list)
    features_paused: list[dict] = field(default_factory=list)
    features_deferred: list[dict] = field(default_factory=list)
    features_failed: list[dict] = field(default_factory=list)
    circuit_breaker_fired: bool = False
    global_abort_signal: bool = False
    abort_reason: Optional[str] = None
    key_files_changed: dict[str, list[str]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Per-repo integration branch routing
# ---------------------------------------------------------------------------


def _effective_base_branch(
    repo_path: Path | None,
    integration_branches: dict[str, str],
    default: str,
) -> str:
    """Return the integration branch name for a given repo.

    If ``repo_path`` is not None and its string form is a key in
    ``integration_branches``, returns that mapped branch name.
    Otherwise returns ``default``.

    Args:
        repo_path: Absolute path to the target repository, or None for the
            default (current) repository.
        integration_branches: Mapping of absolute repo path string to
            integration branch name (from OvernightState.integration_branches).
        default: Fallback branch name — typically config.base_branch, which
            is always set to the home repo's integration branch by the
            orchestrator.

    Returns:
        The effective integration branch name for this repo.
    """
    if repo_path is not None and _normalize_repo_key(str(repo_path)) in integration_branches:
        return integration_branches[_normalize_repo_key(str(repo_path))]
    return default


def _effective_merge_repo_path(
    repo_path: Path | None,
    integration_worktrees: dict[str, str],
    integration_branches: dict[str, str],
    session_id: str,
) -> Path | None:
    """Return the integration worktree path for a given repo.

    Resolves the worktree that merge operations should target so merges
    run against an isolated integration worktree instead of the user's
    live working tree.

    Resolution order:
      1. ``repo_path is None`` → return ``None`` (default-repo case).
      2. Cached hit: key already in ``integration_worktrees`` and the
         path exists on disk → return it.
      3. Lazy creation: ``integration_branches`` must contain the key so
         we know which branch to check out.  Creates a new git worktree
         under ``$TMPDIR/overnight-worktrees/``.
      4. Handles ``git worktree add`` edge cases: "already exists" path
         collisions and stale tracking left after a TMPDIR wipe.

    Args:
        repo_path: Absolute path to the target repository, or None for
            the default (current) repository.
        integration_worktrees: Mutable mapping of normalized repo-path
            string to worktree path string (from
            ``OvernightState.integration_worktrees``).  May be mutated
            on lazy creation.
        integration_branches: Mapping of normalized repo-path string to
            integration branch name.
        session_id: Current overnight session identifier, used to
            namespace the worktree directory.

    Returns:
        Path to the integration worktree for this repo, or None.

    Raises:
        RuntimeError: If the repo has no configured integration branch
            or worktree creation fails.
    """
    if repo_path is None:
        return None

    key = _normalize_repo_key(str(repo_path))

    # Cached hit — worktree already exists on disk.
    if key in integration_worktrees and Path(integration_worktrees[key]).exists():
        return Path(integration_worktrees[key])

    # Need lazy creation — require an integration branch.
    if key not in integration_branches:
        raise RuntimeError(
            f"No integration branch configured for repo {repo_path!s} "
            f"(normalized key: {key}); cannot create worktree"
        )

    branch = integration_branches[key]
    tmpdir = os.environ.get("TMPDIR", "/tmp")
    repo_dir_name = Path(repo_path).name
    worktree_path = Path(tmpdir) / "overnight-worktrees" / f"{session_id}-lazy-{repo_dir_name}"

    # Build env without GIT_DIR to prevent git from inheriting an override.
    env = {k: v for k, v in os.environ.items() if k != "GIT_DIR"}

    result = subprocess.run(
        ["git", "worktree", "add", str(worktree_path), branch],
        cwd=str(repo_path),
        capture_output=True,
        text=True,
        env=env,
    )

    if result.returncode == 0:
        logger.warning(
            "Lazily created integration worktree for %s at %s",
            repo_path,
            worktree_path,
        )
        integration_worktrees[key] = str(worktree_path)
        return Path(worktree_path)

    stderr = result.stderr

    # Path collision — concurrent creation already placed a worktree here.
    if "already exists" in stderr:
        cached = integration_worktrees.get(key)
        if cached:
            return Path(cached)
        if worktree_path.exists():
            return worktree_path
        raise RuntimeError(
            f"Worktree path collision for {repo_path!s} but path "
            f"{worktree_path} does not exist: {stderr}"
        )

    # Stale git tracking — branch registered to a now-deleted path after
    # TMPDIR was cleared.  Prune and retry once.
    if "already checked out at" in stderr:
        prune_result = subprocess.run(
            ["git", "worktree", "prune"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            env=env,
        )
        retry = subprocess.run(
            ["git", "worktree", "add", str(worktree_path), branch],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            env=env,
        )
        if retry.returncode == 0:
            logger.warning(
                "Lazily created integration worktree for %s at %s "
                "(after pruning stale tracking)",
                repo_path,
                worktree_path,
            )
            integration_worktrees[key] = str(worktree_path)
            return Path(worktree_path)
        raise RuntimeError(
            f"Failed to create worktree for {repo_path!s} after pruning: "
            f"{retry.stderr}"
        )

    # Unknown failure.
    raise RuntimeError(
        f"Failed to create integration worktree for {repo_path!s}: {stderr}"
    )


# ---------------------------------------------------------------------------
# Shared helpers (called from _apply_feature_result and run_batch)
# ---------------------------------------------------------------------------


def _get_changed_files(feature: str, base_branch: str, branch: str | None = None) -> list[str]:
    """Get list of files changed between base branch and feature branch.

    ``branch`` is the fully-qualified branch name (e.g. ``pipeline/feat-2``).
    When omitted, falls back to the unsuffixed ``pipeline/{feature}`` construction.
    """
    actual_branch = branch if branch is not None else f"pipeline/{feature}"
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{base_branch}...{actual_branch}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return [f for f in result.stdout.strip().splitlines() if f]
    except (subprocess.TimeoutExpired, OSError):
        pass
    return []


def _classify_no_commit(feature: str, branch: str, base_branch: str) -> str:
    """Classify why a feature completed with no new commits.

    Inspects git state to determine whether the branch is stale (base has
    moved past it) or the agent simply produced no changes.  Always returns
    a non-empty human-readable string suitable for the morning report.
    """
    fallback = f"completed with no new commits (branch: {branch})"
    try:
        result = subprocess.run(
            ["git", "rev-list", f"{branch}..{base_branch}", "--count"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return fallback
        count = int(result.stdout.strip())
        if count > 0:
            return (
                f"branch appears stale — base branch ({base_branch}) has "
                f"{count} commit(s) already merged or ahead of {branch}"
            )
        return f"no changes produced — {branch} is at {base_branch} HEAD with no agent commits"
    except (subprocess.TimeoutExpired, OSError, Exception):
        return fallback


# ---------------------------------------------------------------------------
# Backlog write-back (R13)
# ---------------------------------------------------------------------------

# Ensure project root is importable for backlog/update_item.py
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Runtime backlog directory — set from overnight state so write-backs find items
# in external repos. Falls back to _PROJECT_ROOT / "backlog" when unset.
_backlog_dir: Optional[Path] = None


def set_backlog_dir(path: Path) -> None:
    """Set the backlog directory used by write-back helpers at runtime."""
    global _backlog_dir
    _backlog_dir = path


from backlog.update_item import update_item as _backlog_update_item  # noqa: E402
from backlog.update_item import _find_item as _backlog_find_item  # noqa: E402

# Mapping from overnight internal status to canonical backlog fields (R13).
# Keys: overnight status; Values: dict of backlog fields to write.
# "session_id" is a sentinel — "_CURRENT_" is replaced at call time.
_OVERNIGHT_TO_BACKLOG: dict[str, dict[str, Any]] = {
    "running": {
        "status": "implementing",
        "session_id": "_CURRENT_",
    },
    "merged": {
        "status": "complete",
        "session_id": None,
    },
    "paused": {
        "status": "in_progress",
        "session_id": None,
    },
    "failed": {
        "status": "refined",
        "session_id": None,
    },
    "deferred": {
        "status": "backlog",
        "session_id": None,
    },
}


def _find_backlog_item_path(feature: str, backlog_id: Optional[int] = None) -> Optional[Path]:
    """Locate the backlog item file for *feature*.

    Strategy:
      1. Exact match: ``backlog/NNN-{feature}.md``
      2. If *backlog_id* is provided, match ``backlog/{NNN}-*.md``
      3. Substring match via ``_find_item(feature)``
    """
    backlog_dir = _backlog_dir if _backlog_dir is not None else _PROJECT_ROOT / "backlog"

    # 1. Exact slug match
    for p in sorted(backlog_dir.glob("[0-9]*-*.md")):
        # p.stem is e.g. "056-my-feature"
        # Extract slug portion after NNN-
        slug_part = p.stem.split("-", 1)[1] if "-" in p.stem else p.stem
        if slug_part == feature:
            return p

    # 2. Match by backlog_id
    if backlog_id is not None:
        padded = str(backlog_id).zfill(3)
        candidates = sorted(backlog_dir.glob(f"{padded}-*.md"))
        if candidates:
            return candidates[0]

    # 3. Fallback: substring match via update_item's finder
    result = _backlog_find_item(feature)
    return result


def _write_back_to_backlog(
    feature: str,
    overnight_status: str,
    round_number: int,
    log_path: Path,
    backlog_id: Optional[int] = None,
) -> None:
    """Best-effort write of canonical status back to the backlog item.

    Maps *overnight_status* to the canonical backlog fields defined in R13
    and calls ``update_item()`` from ``backlog/update_item.py``. All
    exceptions are caught, logged to the overnight events log, and silently
    swallowed so the overnight session never aborts on a backlog write failure.
    """
    mapping = _OVERNIGHT_TO_BACKLOG.get(overnight_status)
    if mapping is None:
        return  # No write-back defined for this status (e.g. "pending")

    try:
        item_path = _find_backlog_item_path(feature, backlog_id)
        if item_path is None:
            raise FileNotFoundError(
                f"Backlog item not found for feature {feature!r}"
                + (f" (backlog_id={backlog_id})" if backlog_id else "")
            )

        # Build the fields dict, replacing the session_id sentinel
        session_id = os.environ.get("LIFECYCLE_SESSION_ID", "manual")
        fields: dict[str, Any] = {}
        for key, value in mapping.items():
            if value == "_CURRENT_":
                fields[key] = session_id
            else:
                fields[key] = value

        _backlog_update_item(item_path, fields, session_id=session_id)

    except Exception as exc:
        overnight_log_event(
            BACKLOG_WRITE_FAILED,
            round_number,
            feature=feature,
            details={"error": str(exc)},
            log_path=log_path,
        )


# ---------------------------------------------------------------------------
# Batch execution loop
# ---------------------------------------------------------------------------

def _apply_feature_result(
    name: str,
    result: FeatureResult,
    batch_result: BatchResult,
    consecutive_pauses_ref: list[int],
    config: BatchConfig,
    backlog_ids: dict[str, Optional[int]],
    feature_names: list[str],
    worktree_branches: dict[str, str] | None = None,
    repo_path: Path | None = None,
    worktree_path: Path | None = None,
    integration_branches: dict[str, str] | None = None,
    integration_worktrees: dict[str, str] | None = None,
    session_id: str = "",
    review_result: ReviewResult | None = None,
) -> None:
    """Sync status-dispatch and circuit-breaker logic extracted from _accumulate_result.

    Called inside ``_accumulate_result``'s ``async with lock:`` block so that
    the counter/status branching is directly unit-testable without driving the
    full async ``run_batch()`` call chain (see batch runner).

    ``worktree_branches`` maps feature name to the actual pipeline branch used
    by the worker (e.g. ``pipeline/feat-2``). When provided, the no-commit
    guard and merge both target the correct suffixed branch.
    """
    integration_branches = integration_branches or {}
    integration_worktrees = integration_worktrees or {}
    if result.status == "repair_completed":
        # Fast-forward merge the repair branch into base_branch.
        repo = Path.cwd()
        subprocess.run(
            ["git", "checkout", config.base_branch],
            cwd=repo,
            capture_output=True,
        )
        ff_result = subprocess.run(
            ["git", "merge", "--ff-only", result.repair_branch],
            cwd=repo,
            capture_output=True,
            text=True,
        )
        if ff_result.returncode == 0:
            batch_result.features_merged.append(name)
            consecutive_pauses_ref[0] = 0
            if result.trivial_resolved:
                overnight_log_event(
                    TRIVIAL_CONFLICT_RESOLVED,
                    config.batch_id,
                    feature=name,
                    details={
                        "resolved_files": result.resolved_files,
                        "strategy": "trivial_fast_path",
                    },
                    log_path=config.overnight_events_path,
                )
            else:
                overnight_log_event(
                    REPAIR_AGENT_RESOLVED,
                    config.batch_id,
                    feature=name,
                    details={"repair_branch": result.repair_branch},
                    log_path=config.overnight_events_path,
                )
            _write_back_to_backlog(
                name, "merged", config.batch_id,
                config.overnight_events_path,
                backlog_id=backlog_ids.get(name),
            )
            # Delete repair branch.
            subprocess.run(
                ["git", "branch", "-d", result.repair_branch],
                cwd=repo,
                capture_output=True,
            )
            # Clean up the stale prior-round worktree (failed merge left it intact).
            try:
                cleanup_worktree(name, repo_path=repo_path, worktree_path=worktree_path)
            except Exception:
                pass
        else:
            error = f"repair_ff_merge_failed: {ff_result.stderr.strip()}"
            batch_result.features_paused.append({"name": name, "error": error})
            consecutive_pauses_ref[0] += 1
            overnight_log_event(
                FEATURE_PAUSED,
                config.batch_id,
                feature=name,
                details={"error": error},
                log_path=config.overnight_events_path,
            )
            _write_back_to_backlog(
                name, "paused", config.batch_id,
                config.overnight_events_path,
                backlog_id=backlog_ids.get(name),
            )

    elif result.status == "completed":
        actual_branch = (worktree_branches or {}).get(name)
        # Collect changed files before merge
        changed_files = _get_changed_files(name, config.base_branch, branch=actual_branch)
        batch_result.key_files_changed[name] = changed_files

        # Guard: skip merge if feature completed with no new commits
        if not changed_files:
            branch_label = actual_branch or f"pipeline/{name}"
            error = _classify_no_commit(name, branch_label, config.base_branch)
            if not error:
                error = f"completed with no new commits (branch: {branch_label})"
            batch_result.features_paused.append({"name": name, "error": error})
            consecutive_pauses_ref[0] += 1
            overnight_log_event(
                FEATURE_PAUSED,
                config.batch_id,
                feature=name,
                details={"error": error, "no_commit_guard": True},
                log_path=config.overnight_events_path,
            )
            _write_back_to_backlog(
                name, "paused", config.batch_id,
                config.overnight_events_path,
                backlog_id=backlog_ids.get(name),
            )
            return

        # Auto-merge to main
        effective_branch = _effective_base_branch(repo_path, integration_branches, config.base_branch)
        merge_result = merge_feature(
            feature=name,
            base_branch=effective_branch,
            test_command=config.test_command,
            log_path=config.pipeline_events_path,
            branch=actual_branch,
            repo_path=_effective_merge_repo_path(repo_path, integration_worktrees, integration_branches, session_id),
        )

        if merge_result.success:
            # Review gating: if review was required and deferred, handle early return
            if review_result is not None and review_result.deferred:
                batch_result.features_deferred.append({
                    "name": name,
                    "question_count": 1,
                })
                overnight_log_event(
                    FEATURE_DEFERRED,
                    config.batch_id,
                    feature=name,
                    details={"review_verdict": review_result.verdict, "review_cycle": review_result.cycle},
                    log_path=config.overnight_events_path,
                )
                _write_back_to_backlog(
                    name, "in_progress", config.batch_id,
                    config.overnight_events_path,
                    backlog_id=backlog_ids.get(name),
                )
                try:
                    cleanup_worktree(name, repo_path=repo_path, worktree_path=worktree_path)
                except Exception:
                    pass
                return

            # review_result is None (no review needed) or approved — continue to FEATURE_COMPLETE
            batch_result.features_merged.append(name)
            consecutive_pauses_ref[0] = 0
            overnight_log_event(
                FEATURE_COMPLETE,
                config.batch_id,
                feature=name,
                details={"files_changed": changed_files},
                log_path=config.overnight_events_path,
            )
            _write_back_to_backlog(
                name, "merged", config.batch_id,
                config.overnight_events_path,
                backlog_id=backlog_ids.get(name),
            )
            # Clean up worktree
            try:
                cleanup_worktree(name, repo_path=repo_path, worktree_path=worktree_path)
            except Exception:
                pass
        elif merge_result.error in ("ci_pending", "ci_failing"):
            # CI gate blocked the merge — write a deferral question so the
            # human reviewer can decide whether to force-merge in the morning.
            ci_error = merge_result.error
            if ci_error == "ci_pending":
                question_text = (
                    f"Feature '{name}' has a CI run in progress or queued. "
                    "Should this feature be force-merged once CI completes, "
                    "or should it remain deferred for manual review?"
                )
                context_text = "Merge blocked: CI run is pending (in_progress or queued)."
            else:
                question_text = (
                    f"Feature '{name}' has a failing CI run. "
                    "Should this feature be force-merged despite CI failures, "
                    "or should it remain deferred for manual review?"
                )
                context_text = "Merge blocked: CI run has a non-success conclusion (failure, cancelled, timed_out, or action_required)."

            escalations_path = Path("lifecycle/escalations.jsonl")
            deferral = DeferralQuestion(
                feature=name,
                question_id=_next_escalation_n(name, config.batch_id, escalations_path),
                severity=SEVERITY_BLOCKING,
                context=context_text,
                question=question_text,
                options_considered=["force-merge after CI resolves", "leave deferred for manual review"],
                pipeline_attempted="ci_check in merge_feature()",
            )
            write_deferral(deferral)
            batch_result.features_deferred.append({
                "name": name,
                "question_count": 1,
            })
            overnight_log_event(
                FEATURE_DEFERRED,
                config.batch_id,
                feature=name,
                details={"error": ci_error, "question_count": 1},
                log_path=config.overnight_events_path,
            )
            _write_back_to_backlog(
                name, "deferred", config.batch_id,
                config.overnight_events_path,
                backlog_id=backlog_ids.get(name),
            )
        else:
            error = merge_result.error or "merge failed"
            batch_result.features_paused.append({"name": name, "error": error})
            consecutive_pauses_ref[0] += 1
            if merge_result.conflict and merge_result.classification is not None:
                overnight_log_event(
                    "merge_conflict_classified",
                    config.batch_id,
                    feature=name,
                    details={
                        "conflicted_files": merge_result.classification.conflicted_files,
                        "conflict_summary": merge_result.classification.conflict_summary,
                    },
                    log_path=config.overnight_events_path,
                )
            overnight_log_event(
                FEATURE_PAUSED,
                config.batch_id,
                feature=name,
                details={"error": error, "conflict": merge_result.conflict},
                log_path=config.overnight_events_path,
            )
            _write_back_to_backlog(
                name, "paused", config.batch_id,
                config.overnight_events_path,
                backlog_id=backlog_ids.get(name),
            )

    elif result.status == "deferred":
        batch_result.features_deferred.append({
            "name": name,
            "question_count": result.deferred_question_count,
        })
        overnight_log_event(
            FEATURE_DEFERRED,
            config.batch_id,
            feature=name,
            details={"question_count": result.deferred_question_count},
            log_path=config.overnight_events_path,
        )
        _write_back_to_backlog(
            name, "deferred", config.batch_id,
            config.overnight_events_path,
            backlog_id=backlog_ids.get(name),
        )

    elif result.status == "failed":
        batch_result.features_failed.append({
            "name": name,
            "error": result.error or "unknown failure",
        })
        if not result.parse_error:
            consecutive_pauses_ref[0] += 1
        overnight_log_event(
            FEATURE_FAILED,
            config.batch_id,
            feature=name,
            details={"error": result.error},
            log_path=config.overnight_events_path,
        )
        _write_back_to_backlog(
            name, "failed", config.batch_id,
            config.overnight_events_path,
            backlog_id=backlog_ids.get(name),
        )

    else:  # paused
        batch_result.features_paused.append({
            "name": name,
            "error": result.error or "task paused",
        })
        consecutive_pauses_ref[0] += 1
        overnight_log_event(
            FEATURE_PAUSED,
            config.batch_id,
            feature=name,
            details={"error": result.error},
            log_path=config.overnight_events_path,
        )
        _write_back_to_backlog(
            name, "paused", config.batch_id,
            config.overnight_events_path,
            backlog_id=backlog_ids.get(name),
        )

    if consecutive_pauses_ref[0] >= CIRCUIT_BREAKER_THRESHOLD:
        batch_result.circuit_breaker_fired = True
        overnight_log_event(
            CIRCUIT_BREAKER,
            config.batch_id,
            feature=name,
            details={
                "reason": "batch circuit breaker: 3 consecutive pauses",
                "remaining_features": [
                    n for n in feature_names
                    if n not in batch_result.features_merged
                    and not any(d["name"] == n for d in batch_result.features_paused)
                    and not any(d["name"] == n for d in batch_result.features_deferred)
                    and not any(d["name"] == n for d in batch_result.features_failed)
                ],
            },
            log_path=config.overnight_events_path,
        )


async def run_batch(config: BatchConfig) -> BatchResult:
    """Execute a batch of features with concurrency and circuit breaker.

    Parses the batch master plan, creates worktrees, executes features
    with a semaphore-limited concurrency, handles auto-merge on success,
    and enforces the batch circuit breaker (3 consecutive pauses).
    """
    master_plan = parse_master_plan(config.plan_path)
    feature_names = [f.name for f in master_plan.features]

    overnight_log_event(
        BATCH_ASSIGNED,
        config.batch_id,
        details={"features": feature_names},
        log_path=config.overnight_events_path,
    )

    # Load spec_path, backlog_id, recovery_attempts, repo_path, and integration_branches per feature from overnight state
    spec_paths: dict[str, Optional[str]] = {}
    backlog_ids: dict[str, Optional[int]] = {}
    recovery_attempts_map: dict[str, int] = {}
    repo_path_map: dict[str, Path | None] = {}
    integration_branches: dict[str, str] = {}
    integration_worktrees: dict[str, str] = {}
    session_id: str = os.environ.get("LIFECYCLE_SESSION_ID", "manual")
    try:
        overnight_state = load_state(config.overnight_state_path)
        session_id = overnight_state.session_id
        integration_branches = overnight_state.integration_branches
        integration_worktrees = overnight_state.integration_worktrees
        if integration_branches:
            set_backlog_dir(Path(next(iter(integration_branches))) / "backlog")
        for name in feature_names:
            fs = overnight_state.features.get(name, OvernightFeatureStatus())
            spec_paths[name] = fs.spec_path if fs else None
            backlog_ids[name] = fs.backlog_id if fs else None
            recovery_attempts_map[name] = fs.recovery_attempts
            repo_path_map[name] = Path(fs.repo_path).expanduser() if fs.repo_path else None
    except Exception:
        spec_paths = {name: None for name in feature_names}
        backlog_ids = {name: None for name in feature_names}
        recovery_attempts_map = {name: 0 for name in feature_names}
        repo_path_map = {name: None for name in feature_names}
        integration_branches = {}
        integration_worktrees = {}

    # Create worktrees; capture actual branch names (may include -2/-N suffixes)
    worktree_paths: dict[str, Path] = {}
    worktree_branches: dict[str, str] = {}
    for name in feature_names:
        info = create_worktree(name, config.base_branch, repo_path=repo_path_map.get(name), session_id=session_id)
        worktree_paths[name] = info.path
        worktree_branches[name] = info.branch

    batch_result = BatchResult(batch_id=config.batch_id)

    # Set up throttle-aware concurrency manager
    throttle_config = load_throttle_config(config.throttle_tier)
    manager = ConcurrencyManager(throttle_config)

    lock = asyncio.Lock()
    consecutive_pauses_ref = [0]

    async def _accumulate_result(name: str, result: FeatureResult) -> None:
        """Accumulate a feature result into batch_result under the shared lock.

        For completed features with test failures (not conflicts, not CI errors),
        attempts recovery via ``recover_test_failure()`` if the gate passes
        (``recovery_attempts_map[name] < 1``).  The lock is released during
        recovery (which spawns an agent) and re-acquired afterwards.
        """
        need_recovery = False
        actual_branch: str | None = None
        merge_result = None

        async with lock:
            if result.status != "completed":
                # Non-completed: delegate entirely to _apply_feature_result
                _apply_feature_result(
                    name, result, batch_result, consecutive_pauses_ref,
                    config, backlog_ids, feature_names,
                    worktree_branches=worktree_branches,
                    repo_path=repo_path_map.get(name),
                    worktree_path=worktree_paths.get(name),
                    integration_branches=integration_branches,
                    integration_worktrees=integration_worktrees,
                    session_id=session_id,
                    review_result=None,
                )
                if result.repair_agent_used:
                    recovery_attempts_map[name] = recovery_attempts_map.get(name, 0) + 1

                # Detect budget_exhausted and set global abort signal
                if (
                    result.status == "paused"
                    and result.error == "budget_exhausted"
                    and not batch_result.global_abort_signal
                ):
                    batch_result.global_abort_signal = True
                    batch_result.abort_reason = "budget_exhausted"
                    try:
                        _state = load_state(config.overnight_state_path)
                        _fs = _state.features.get(name)
                        if _fs is not None:
                            _fs.status = "paused"
                            _fs.error = "budget_exhausted"
                            save_state(_state, config.overnight_state_path)
                    except Exception:
                        pass  # Don't let state-write failure abort the batch
                    overnight_log_event(
                        BATCH_BUDGET_EXHAUSTED,
                        config.batch_id,
                        feature=name,
                        details={"abort_reason": "budget_exhausted"},
                        log_path=config.overnight_events_path,
                    )

                return

            # --- Completed feature: intercept merge to check for test failures ---
            actual_branch = (worktree_branches or {}).get(name)
            changed_files = _get_changed_files(name, config.base_branch, branch=actual_branch)
            batch_result.key_files_changed[name] = changed_files

            if not changed_files:
                # No commits — fall through to _apply_feature_result (no-commit guard)
                _apply_feature_result(
                    name, result, batch_result, consecutive_pauses_ref,
                    config, backlog_ids, feature_names,
                    worktree_branches=worktree_branches,
                    repo_path=repo_path_map.get(name),
                    worktree_path=worktree_paths.get(name),
                    integration_branches=integration_branches,
                    integration_worktrees=integration_worktrees,
                    session_id=session_id,
                    review_result=None,
                )
                return

            # Attempt merge
            effective_branch = _effective_base_branch(repo_path_map.get(name), integration_branches, config.base_branch)
            merge_result = merge_feature(
                feature=name,
                base_branch=effective_branch,
                test_command=config.test_command,
                log_path=config.pipeline_events_path,
                branch=actual_branch,
                repo_path=_effective_merge_repo_path(repo_path_map.get(name), integration_worktrees, integration_branches, session_id),
            )

            if merge_result.success:
                overnight_log_event(FEATURE_MERGED, config.batch_id, feature=name, details={"integration_branch": effective_branch}, log_path=config.overnight_events_path)
                # Review gating: check if post-merge review is required
                tier = read_tier(name)
                criticality = read_criticality(name)
                if requires_review(tier, criticality):
                    from claude.pipeline.review_dispatch import dispatch_review  # noqa: E402 — lazy to avoid circular import

                    try:
                        rr = await dispatch_review(
                            feature=name,
                            worktree_path=worktree_paths.get(name, Path(f"worktrees/{name}")),
                            branch=actual_branch or f"pipeline/{name}",
                            spec_path=Path(f"lifecycle/{name}/spec.md"),
                            complexity=tier,
                            criticality=criticality,
                            base_branch=_effective_base_branch(
                                repo_path_map.get(name), integration_branches, config.base_branch,
                            ),
                            repo_path=_effective_merge_repo_path(repo_path_map.get(name), integration_worktrees, integration_branches, session_id),
                            log_path=config.pipeline_events_path,
                        )
                        if rr.deferred:
                            batch_result.features_deferred.append({
                                "name": name,
                                "question_count": 1,
                            })
                            overnight_log_event(
                                FEATURE_DEFERRED,
                                config.batch_id,
                                feature=name,
                                details={"review_verdict": rr.verdict, "review_cycle": rr.cycle},
                                log_path=config.overnight_events_path,
                            )
                            _write_back_to_backlog(
                                name, "in_progress", config.batch_id,
                                config.overnight_events_path,
                                backlog_id=backlog_ids.get(name),
                            )
                            try:
                                cleanup_worktree(name, repo_path=repo_path_map.get(name), worktree_path=worktree_paths.get(name))
                            except Exception:
                                pass
                            return
                    except Exception as exc:
                        overnight_log_event(
                            FEATURE_DEFERRED,
                            config.batch_id,
                            feature=name,
                            details={"error": f"dispatch_review raised {type(exc).__name__}: {exc}", "review_dispatch_crashed": True},
                            log_path=config.overnight_events_path,
                        )
                        escalations_path = Path("lifecycle/escalations.jsonl")
                        deferral = DeferralQuestion(
                            feature=name,
                            question_id=_next_escalation_n(name, config.batch_id, escalations_path),
                            severity=SEVERITY_BLOCKING,
                            context=f"Feature merged successfully but post-merge review dispatch raised an unexpected exception: {type(exc).__name__}: {exc}",
                            question=f"Feature '{name}' merged but the review dispatch crashed. Should this feature be marked complete (skipping review) or held for manual review?",
                            options_considered=["mark complete (skip review)", "hold for manual review"],
                            pipeline_attempted="dispatch_review() in _accumulate_result()",
                        )
                        write_deferral(deferral)
                        batch_result.features_deferred.append({
                            "name": name,
                            "question_count": 1,
                        })
                        _write_back_to_backlog(
                            name, "in_progress", config.batch_id,
                            config.overnight_events_path,
                            backlog_id=backlog_ids.get(name),
                        )
                        return

                # Standard merged path (no review needed, or review approved)
                batch_result.features_merged.append(name)
                consecutive_pauses_ref[0] = 0
                overnight_log_event(
                    FEATURE_COMPLETE,
                    config.batch_id,
                    feature=name,
                    details={"files_changed": changed_files},
                    log_path=config.overnight_events_path,
                )
                _write_back_to_backlog(
                    name, "merged", config.batch_id,
                    config.overnight_events_path,
                    backlog_id=backlog_ids.get(name),
                )
                try:
                    cleanup_worktree(name, repo_path=repo_path_map.get(name), worktree_path=worktree_paths.get(name))
                except Exception:
                    pass
                return

            if merge_result.error in ("ci_pending", "ci_failing"):
                # Standard CI deferral path
                ci_error = merge_result.error
                if ci_error == "ci_pending":
                    question_text = (
                        f"Feature '{name}' has a CI run in progress or queued. "
                        "Should this feature be force-merged once CI completes, "
                        "or should it remain deferred for manual review?"
                    )
                    context_text = "Merge blocked: CI run is pending (in_progress or queued)."
                else:
                    question_text = (
                        f"Feature '{name}' has a failing CI run. "
                        "Should this feature be force-merged despite CI failures, "
                        "or should it remain deferred for manual review?"
                    )
                    context_text = "Merge blocked: CI run has a non-success conclusion (failure, cancelled, timed_out, or action_required)."

                escalations_path = Path("lifecycle/escalations.jsonl")
                deferral = DeferralQuestion(
                    feature=name,
                    question_id=_next_escalation_n(name, config.batch_id, escalations_path),
                    severity=SEVERITY_BLOCKING,
                    context=context_text,
                    question=question_text,
                    options_considered=["force-merge after CI resolves", "leave deferred for manual review"],
                    pipeline_attempted="ci_check in merge_feature()",
                )
                write_deferral(deferral)
                batch_result.features_deferred.append({
                    "name": name,
                    "question_count": 1,
                })
                overnight_log_event(
                    FEATURE_DEFERRED,
                    config.batch_id,
                    feature=name,
                    details={"error": ci_error, "question_count": 1},
                    log_path=config.overnight_events_path,
                )
                _write_back_to_backlog(
                    name, "deferred", config.batch_id,
                    config.overnight_events_path,
                    backlog_id=backlog_ids.get(name),
                )
                return

            if merge_result.conflict:
                # Conflict — fall through to _apply_feature_result
                _apply_feature_result(
                    name, result, batch_result, consecutive_pauses_ref,
                    config, backlog_ids, feature_names,
                    worktree_branches=worktree_branches,
                    repo_path=repo_path_map.get(name),
                    worktree_path=worktree_paths.get(name),
                    integration_branches=integration_branches,
                    integration_worktrees=integration_worktrees,
                    session_id=session_id,
                    review_result=None,
                )
                return

            # --- Test failure (not success, not conflict, not CI error) ---
            if recovery_attempts_map.get(name, 0) >= 1:
                # Gate does not pass — fall through to standard paused path
                _apply_feature_result(
                    name, result, batch_result, consecutive_pauses_ref,
                    config, backlog_ids, feature_names,
                    worktree_branches=worktree_branches,
                    repo_path=repo_path_map.get(name),
                    worktree_path=worktree_paths.get(name),
                    integration_branches=integration_branches,
                    integration_worktrees=integration_worktrees,
                    session_id=session_id,
                    review_result=None,
                )
                return

            # Gate passes — prepare for recovery
            overnight_log_event(
                MERGE_RECOVERY_START,
                config.batch_id,
                feature=name,
                details={
                    "test_output": (merge_result.test_result.output[:500]
                                    if merge_result.test_result else ""),
                },
                log_path=config.overnight_events_path,
            )
            recovery_attempts_map[name] = recovery_attempts_map.get(name, 0) + 1
            # Persist recovery_attempts immediately so a mid-batch kill
            # doesn't lose the increment (Bug 4).  save_state() is
            # synchronous I/O inside an async lock; this serializes
            # concurrent feature result accumulation but is an accepted
            # tradeoff for typical batch sizes of ~3 features.
            try:
                _ra_state = load_state(config.overnight_state_path)
                _ra_fs = _ra_state.features.get(name)
                if _ra_fs is not None:
                    _ra_fs.recovery_attempts = recovery_attempts_map[name]
                    save_state(_ra_state, config.overnight_state_path)
            except Exception:
                pass  # Don't let state-write failure block recovery
            need_recovery = True
            # Lock will be released when we exit `async with lock:`

        # --- Recovery (outside the lock) ---
        if need_recovery:
            recovery_result = await recover_test_failure(
                feature=name,
                base_branch=config.base_branch,
                test_output=(merge_result.test_result.output
                             if merge_result and merge_result.test_result else ""),
                branch=actual_branch or f"pipeline/{name}",
                worktree_path=worktree_paths.get(name),
                learnings_dir=Path(f"lifecycle/{name}/learnings"),
                test_command=config.test_command,
                pipeline_log_path=config.pipeline_events_path,
                repo_path=_effective_merge_repo_path(repo_path_map.get(name), integration_worktrees, integration_branches, session_id),
            )

            # Re-acquire the lock to route the recovery result
            async with lock:
                if recovery_result.success and recovery_result.flaky:
                    overnight_log_event(
                        MERGE_RECOVERY_FLAKY,
                        config.batch_id,
                        feature=name,
                        details={"attempts": recovery_result.attempts},
                        log_path=config.overnight_events_path,
                    )
                    batch_result.features_merged.append(name)
                    consecutive_pauses_ref[0] = 0
                    _write_back_to_backlog(
                        name, "merged", config.batch_id,
                        config.overnight_events_path,
                        backlog_id=backlog_ids.get(name),
                    )
                    try:
                        cleanup_worktree(name, repo_path=repo_path_map.get(name), worktree_path=worktree_paths.get(name))
                    except Exception:
                        pass
                elif recovery_result.success and not recovery_result.flaky:
                    overnight_log_event(
                        MERGE_RECOVERY_SUCCESS,
                        config.batch_id,
                        feature=name,
                        details={"attempts": recovery_result.attempts},
                        log_path=config.overnight_events_path,
                    )
                    batch_result.features_merged.append(name)
                    consecutive_pauses_ref[0] = 0
                    _write_back_to_backlog(
                        name, "merged", config.batch_id,
                        config.overnight_events_path,
                        backlog_id=backlog_ids.get(name),
                    )
                    try:
                        cleanup_worktree(name, repo_path=repo_path_map.get(name), worktree_path=worktree_paths.get(name))
                    except Exception:
                        pass
                else:
                    # Recovery failed — pause the feature
                    error = recovery_result.error or "recovery failed"
                    overnight_log_event(
                        MERGE_RECOVERY_FAILED,
                        config.batch_id,
                        feature=name,
                        details={
                            "attempts": recovery_result.attempts,
                            "error": error,
                        },
                        log_path=config.overnight_events_path,
                    )
                    batch_result.features_paused.append({
                        "name": name,
                        "error": f"merge recovery failed: {error}",
                    })
                    consecutive_pauses_ref[0] += 1
                    _write_back_to_backlog(
                        name, "paused", config.batch_id,
                        config.overnight_events_path,
                        backlog_id=backlog_ids.get(name),
                    )

                    # Check circuit breaker after pause
                    if consecutive_pauses_ref[0] >= CIRCUIT_BREAKER_THRESHOLD:
                        batch_result.circuit_breaker_fired = True
                        overnight_log_event(
                            CIRCUIT_BREAKER,
                            config.batch_id,
                            feature=name,
                            details={
                                "reason": "batch circuit breaker: 3 consecutive pauses",
                                "remaining_features": [
                                    n for n in feature_names
                                    if n not in batch_result.features_merged
                                    and not any(d["name"] == n for d in batch_result.features_paused)
                                    and not any(d["name"] == n for d in batch_result.features_deferred)
                                    and not any(d["name"] == n for d in batch_result.features_failed)
                                ],
                            },
                            log_path=config.overnight_events_path,
                        )

    async def _run_one(name: str) -> None:
        """Execute a single feature with circuit breaker checks and semaphore."""
        # Pre-check circuit breaker / global abort before doing any work
        async with lock:
            if batch_result.global_abort_signal:
                return
            if batch_result.circuit_breaker_fired:
                batch_result.features_paused.append({
                    "name": name,
                    "error": "batch circuit breaker: 3 consecutive pauses",
                })
                return

        overnight_log_event(
            FEATURE_START,
            config.batch_id,
            feature=name,
            log_path=config.overnight_events_path,
        )

        await manager.acquire()
        try:
            # Re-check circuit breaker / global abort after acquiring semaphore
            async with lock:
                if batch_result.global_abort_signal:
                    return
                if batch_result.circuit_breaker_fired:
                    batch_result.features_paused.append({
                        "name": name,
                        "error": "batch circuit breaker: 3 consecutive pauses",
                    })
                    return

            result = await execute_feature(
                feature=name,
                worktree_path=worktree_paths[name],
                config=config,
                spec_path=spec_paths.get(name),
                manager=manager,
                consecutive_pauses_ref=consecutive_pauses_ref,
                repo_path=repo_path_map.get(name),
                integration_branches=integration_branches,
            )
        finally:
            manager.release()

        await _accumulate_result(name, result)

    # -----------------------------------------------------------------------
    # Heartbeat background task: fires every 5 minutes to prevent watchdog
    # from falsely timing out during legitimate long-running batches.
    # -----------------------------------------------------------------------

    def _derive_session_id(events_path: Path) -> Optional[str]:
        """Derive session_id from the per-session events log path."""
        stem = events_path.stem  # e.g. "overnight-events-overnight-2025-01-15-2200"
        prefix = "overnight-events-"
        if stem.startswith(prefix):
            return stem[len(prefix):]
        return None

    async def _heartbeat_loop() -> None:
        """Write a heartbeat event every 5 minutes while run_batch() executes."""
        while True:
            await asyncio.sleep(300)
            async with lock:
                features_pending = len([
                    n for n in feature_names
                    if n not in batch_result.features_merged
                    and not any(d["name"] == n for d in batch_result.features_paused)
                    and not any(d["name"] == n for d in batch_result.features_deferred)
                    and not any(d["name"] == n for d in batch_result.features_failed)
                ])
                features_running = features_pending  # approximation: pending == not yet done
            overnight_log_event(
                HEARTBEAT,
                0,
                details={
                    "session_id": _derive_session_id(config.overnight_events_path),
                    "features_pending": features_pending,
                    "features_running": features_running,
                },
                log_path=config.overnight_events_path,
            )

    heartbeat_task = asyncio.create_task(_heartbeat_loop())

    gather_results = await asyncio.gather(
        *[_run_one(n) for n in feature_names],
        return_exceptions=True,
    )

    heartbeat_task.cancel()
    try:
        await heartbeat_task
    except asyncio.CancelledError:
        pass
    for n, exc in zip(feature_names, gather_results):
        if isinstance(exc, Exception):
            failed_result = FeatureResult(
                name=n,
                status="failed",
                error=f"unexpected exception: {exc}",
            )
            await _accumulate_result(n, failed_result)

    # Write back recovery_attempts to overnight state if any changed
    try:
        state_for_writeback = load_state(config.overnight_state_path)
        any_changed = False
        for feat_name, attempts in recovery_attempts_map.items():
            if attempts > 0:
                fs = state_for_writeback.features.get(feat_name)
                if fs is not None and fs.recovery_attempts != attempts:
                    fs.recovery_attempts = attempts
                    any_changed = True
        if any_changed:
            save_state(state_for_writeback, config.overnight_state_path)
    except Exception:
        pass  # Don't let state-write failure abort the batch

    # Transition session to paused if budget was exhausted
    if batch_result.global_abort_signal:
        try:
            state_for_pause = load_state(config.overnight_state_path)
            if state_for_pause.phase not in ("paused", "complete"):
                transition(state_for_pause, "paused")
                state_for_pause.paused_reason = "budget_exhausted"
                save_state(state_for_pause, config.overnight_state_path)
                overnight_log_event(
                    SESSION_BUDGET_EXHAUSTED,
                    config.batch_id,
                    details={
                        "reason": batch_result.abort_reason,
                        "features_paused": len(batch_result.features_paused),
                    },
                    log_path=config.overnight_events_path,
                )
        except Exception:
            pass  # Don't let state-write failure block the batch result JSON

    # Write batch result (include throttle stats)
    result_path = config.result_dir / f"batch-{config.batch_id}-results.json"
    save_batch_result(batch_result, result_path, extra_fields={"throttle_stats": manager.stats})

    overnight_log_event(
        BATCH_COMPLETE,
        config.batch_id,
        details={
            "merged": len(batch_result.features_merged),
            "paused": len(batch_result.features_paused),
            "deferred": len(batch_result.features_deferred),
            "failed": len(batch_result.features_failed),
            "circuit_breaker": batch_result.circuit_breaker_fired,
        },
        log_path=config.overnight_events_path,
    )

    return batch_result


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python3 -m claude.overnight.batch_runner",
        description="Batch runner execution for overnight orchestration.",
    )
    p.add_argument("--plan", required=True, help="Path to batch master plan")
    p.add_argument("--batch-id", type=int, required=True, help="Batch/round number")
    p.add_argument("--test-command", default=None, help="Post-merge test command")
    p.add_argument("--base-branch", default="main", help="Base branch for merges")
    p.add_argument(
        "--state-path",
        default="lifecycle/sessions/latest-overnight/overnight-state.json",
        help="Overnight state file path",
    )
    p.add_argument(
        "--events-path",
        default="lifecycle/sessions/latest-overnight/overnight-events.log",
        help="Overnight events log path",
    )
    p.add_argument(
        "--tier",
        default=None,
        help="Subscription tier (max_5, max_100, max_200)",
    )
    return p


def _run() -> None:
    args = build_parser().parse_args()
    result_dir = Path(args.plan).parent
    test_command = args.test_command
    if test_command and str(test_command).lower() == "none":
        test_command = None
    config = BatchConfig(
        batch_id=args.batch_id,
        plan_path=Path(args.plan),
        test_command=test_command,
        base_branch=args.base_branch,
        overnight_state_path=Path(args.state_path),
        overnight_events_path=Path(args.events_path),
        result_dir=result_dir,
        pipeline_events_path=result_dir / "pipeline-events.log",
        throttle_tier=args.tier,
    )
    asyncio.run(run_batch(config))


if __name__ == "__main__":
    _run()
