"""Outcome routing layer extracted from batch_runner.py.

This module contains the outcome routing layer extracted from
batch_runner.py. This module must not import from
`cortex_command.overnight.batch_runner` or `cortex_command.overnight.orchestrator`.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from cortex_command.overnight.orchestrator import BatchResult, BatchConfig

from cortex_command.common import (
    read_criticality,
    read_tier,
    requires_review,
)
from cortex_command.overnight.constants import CIRCUIT_BREAKER_THRESHOLD
from cortex_command.overnight.deferral import (
    DEFAULT_DEFERRED_DIR,
    SEVERITY_BLOCKING,
    DeferralQuestion,
    _next_escalation_n,
    write_deferral,
)
from cortex_command.overnight.events import (
    BACKLOG_WRITE_FAILED,
    CIRCUIT_BREAKER,
    FEATURE_COMPLETE,
    FEATURE_DEFERRED,
    FEATURE_FAILED,
    FEATURE_MERGED,
    FEATURE_PAUSED,
    MERGE_RECOVERY_FAILED,
    MERGE_RECOVERY_FLAKY,
    MERGE_RECOVERY_START,
    MERGE_RECOVERY_SUCCESS,
    REPAIR_AGENT_RESOLVED,
    TRIVIAL_CONFLICT_RESOLVED,
    log_event as overnight_log_event,
)
from cortex_command.overnight.state import _normalize_repo_key, load_state, save_state
from cortex_command.overnight.types import CircuitBreakerState, FeatureResult
from cortex_command.pipeline.merge import merge_feature
from cortex_command.pipeline.merge_recovery import recover_test_failure
from cortex_command.pipeline.review_dispatch import dispatch_review
from cortex_command.pipeline.worktree import cleanup_worktree

if TYPE_CHECKING:
    from cortex_command.pipeline.review_dispatch import ReviewResult  # noqa: F401


logger = logging.getLogger(__name__)


@dataclass
class OutcomeContext:
    batch_result: BatchResult
    lock: asyncio.Lock
    cb_state: CircuitBreakerState
    recovery_attempts_map: dict[str, int]
    worktree_paths: dict[str, Path]
    worktree_branches: dict[str, str]
    repo_path_map: dict[str, Path | None]
    integration_worktrees: dict[str, Path]
    integration_branches: dict[str, str]
    session_id: str
    backlog_ids: dict[str, int | None]
    feature_names: list[str]
    config: BatchConfig


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
    result = _backlog_find_item(feature, backlog_dir=backlog_dir)
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

        backlog_dir = _backlog_dir if _backlog_dir is not None else _PROJECT_ROOT / "backlog"
        _backlog_update_item(
            item_path, fields, backlog_dir=backlog_dir, session_id=session_id
        )

    except Exception as exc:
        overnight_log_event(
            BACKLOG_WRITE_FAILED,
            round_number,
            feature=feature,
            details={"error": str(exc)},
            log_path=log_path,
        )


# ---------------------------------------------------------------------------
# Sync outcome dispatcher: _apply_feature_result
# ---------------------------------------------------------------------------


def _apply_feature_result(
    name: str,
    result: FeatureResult,
    ctx: OutcomeContext,
    deferred_dir: Path = DEFAULT_DEFERRED_DIR,
) -> None:
    """Sync status-dispatch and circuit-breaker logic extracted from _accumulate_result.

    Called inside ``_accumulate_result``'s ``async with lock:`` block so that
    the counter/status branching is directly unit-testable without driving the
    full async ``run_batch()`` call chain (see batch runner).

    ``ctx.worktree_branches`` maps feature name to the actual pipeline branch used
    by the worker (e.g. ``pipeline/feat-2``). When provided, the no-commit
    guard and merge both target the correct suffixed branch.
    """
    repo_path = ctx.repo_path_map.get(name)
    worktree_path = ctx.worktree_paths.get(name)
    review_result: "ReviewResult | None" = None
    if result.status == "repair_completed":
        # Fast-forward merge the repair branch into base_branch.
        repo = Path.cwd()
        subprocess.run(
            ["git", "checkout", ctx.config.base_branch],
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
            ctx.batch_result.features_merged.append(name)
            ctx.cb_state.consecutive_pauses = 0
            if result.trivial_resolved:
                overnight_log_event(
                    TRIVIAL_CONFLICT_RESOLVED,
                    ctx.config.batch_id,
                    feature=name,
                    details={
                        "resolved_files": result.resolved_files,
                        "strategy": "trivial_fast_path",
                    },
                    log_path=ctx.config.overnight_events_path,
                )
            else:
                overnight_log_event(
                    REPAIR_AGENT_RESOLVED,
                    ctx.config.batch_id,
                    feature=name,
                    details={"repair_branch": result.repair_branch},
                    log_path=ctx.config.overnight_events_path,
                )
            _write_back_to_backlog(
                name, "merged", ctx.config.batch_id,
                ctx.config.overnight_events_path,
                backlog_id=ctx.backlog_ids.get(name),
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
            ctx.batch_result.features_paused.append({"name": name, "error": error})
            ctx.cb_state.consecutive_pauses += 1
            overnight_log_event(
                FEATURE_PAUSED,
                ctx.config.batch_id,
                feature=name,
                details={"error": error},
                log_path=ctx.config.overnight_events_path,
            )
            _write_back_to_backlog(
                name, "paused", ctx.config.batch_id,
                ctx.config.overnight_events_path,
                backlog_id=ctx.backlog_ids.get(name),
            )

    elif result.status == "completed":
        actual_branch = (ctx.worktree_branches or {}).get(name)
        # Collect changed files before merge
        changed_files = _get_changed_files(name, ctx.config.base_branch, branch=actual_branch)
        ctx.batch_result.key_files_changed[name] = changed_files

        # Guard: skip merge if feature completed with no new commits
        if not changed_files:
            branch_label = actual_branch or f"pipeline/{name}"
            error = _classify_no_commit(name, branch_label, ctx.config.base_branch)
            if not error:
                error = f"completed with no new commits (branch: {branch_label})"
            ctx.batch_result.features_paused.append({"name": name, "error": error})
            ctx.cb_state.consecutive_pauses += 1
            overnight_log_event(
                FEATURE_PAUSED,
                ctx.config.batch_id,
                feature=name,
                details={"error": error, "no_commit_guard": True},
                log_path=ctx.config.overnight_events_path,
            )
            _write_back_to_backlog(
                name, "paused", ctx.config.batch_id,
                ctx.config.overnight_events_path,
                backlog_id=ctx.backlog_ids.get(name),
            )
            return

        # Auto-merge to main
        effective_branch = _effective_base_branch(repo_path, ctx.integration_branches, ctx.config.base_branch)
        merge_result = merge_feature(
            feature=name,
            base_branch=effective_branch,
            test_command=ctx.config.test_command,
            log_path=ctx.config.pipeline_events_path,
            branch=actual_branch,
            repo_path=_effective_merge_repo_path(repo_path, ctx.integration_worktrees, ctx.integration_branches, ctx.session_id),
        )

        if merge_result.success:
            # Review gating: if review was required and deferred, handle early return
            if review_result is not None and review_result.deferred:
                ctx.batch_result.features_deferred.append({
                    "name": name,
                    "question_count": 1,
                })
                overnight_log_event(
                    FEATURE_DEFERRED,
                    ctx.config.batch_id,
                    feature=name,
                    details={"review_verdict": review_result.verdict, "review_cycle": review_result.cycle},
                    log_path=ctx.config.overnight_events_path,
                )
                _write_back_to_backlog(
                    name, "in_progress", ctx.config.batch_id,
                    ctx.config.overnight_events_path,
                    backlog_id=ctx.backlog_ids.get(name),
                )
                try:
                    cleanup_worktree(name, repo_path=repo_path, worktree_path=worktree_path)
                except Exception:
                    pass
                return

            # review_result is None (no review needed) or approved — continue to FEATURE_COMPLETE
            ctx.batch_result.features_merged.append(name)
            ctx.cb_state.consecutive_pauses = 0
            overnight_log_event(
                FEATURE_COMPLETE,
                ctx.config.batch_id,
                feature=name,
                details={"files_changed": changed_files},
                log_path=ctx.config.overnight_events_path,
            )
            _write_back_to_backlog(
                name, "merged", ctx.config.batch_id,
                ctx.config.overnight_events_path,
                backlog_id=ctx.backlog_ids.get(name),
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
                question_id=_next_escalation_n(name, ctx.config.batch_id, escalations_path),
                severity=SEVERITY_BLOCKING,
                context=context_text,
                question=question_text,
                options_considered=["force-merge after CI resolves", "leave deferred for manual review"],
                pipeline_attempted="ci_check in merge_feature()",
            )
            write_deferral(deferral, deferred_dir=deferred_dir)
            ctx.batch_result.features_deferred.append({
                "name": name,
                "question_count": 1,
            })
            overnight_log_event(
                FEATURE_DEFERRED,
                ctx.config.batch_id,
                feature=name,
                details={"error": ci_error, "question_count": 1},
                log_path=ctx.config.overnight_events_path,
            )
            _write_back_to_backlog(
                name, "deferred", ctx.config.batch_id,
                ctx.config.overnight_events_path,
                backlog_id=ctx.backlog_ids.get(name),
            )
        else:
            error = merge_result.error or "merge failed"
            ctx.batch_result.features_paused.append({"name": name, "error": error})
            ctx.cb_state.consecutive_pauses += 1
            if merge_result.conflict and merge_result.classification is not None:
                overnight_log_event(
                    "merge_conflict_classified",
                    ctx.config.batch_id,
                    feature=name,
                    details={
                        "conflicted_files": merge_result.classification.conflicted_files,
                        "conflict_summary": merge_result.classification.conflict_summary,
                    },
                    log_path=ctx.config.overnight_events_path,
                )
            overnight_log_event(
                FEATURE_PAUSED,
                ctx.config.batch_id,
                feature=name,
                details={"error": error, "conflict": merge_result.conflict},
                log_path=ctx.config.overnight_events_path,
            )
            _write_back_to_backlog(
                name, "paused", ctx.config.batch_id,
                ctx.config.overnight_events_path,
                backlog_id=ctx.backlog_ids.get(name),
            )

    elif result.status == "deferred":
        ctx.batch_result.features_deferred.append({
            "name": name,
            "question_count": result.deferred_question_count,
        })
        overnight_log_event(
            FEATURE_DEFERRED,
            ctx.config.batch_id,
            feature=name,
            details={"question_count": result.deferred_question_count},
            log_path=ctx.config.overnight_events_path,
        )
        _write_back_to_backlog(
            name, "deferred", ctx.config.batch_id,
            ctx.config.overnight_events_path,
            backlog_id=ctx.backlog_ids.get(name),
        )

    elif result.status == "failed":
        ctx.batch_result.features_failed.append({
            "name": name,
            "error": result.error or "unknown failure",
        })
        if not result.parse_error:
            ctx.cb_state.consecutive_pauses += 1
        overnight_log_event(
            FEATURE_FAILED,
            ctx.config.batch_id,
            feature=name,
            details={"error": result.error},
            log_path=ctx.config.overnight_events_path,
        )
        _write_back_to_backlog(
            name, "failed", ctx.config.batch_id,
            ctx.config.overnight_events_path,
            backlog_id=ctx.backlog_ids.get(name),
        )

    else:  # paused
        ctx.batch_result.features_paused.append({
            "name": name,
            "error": result.error or "task paused",
        })
        ctx.cb_state.consecutive_pauses += 1
        overnight_log_event(
            FEATURE_PAUSED,
            ctx.config.batch_id,
            feature=name,
            details={"error": result.error},
            log_path=ctx.config.overnight_events_path,
        )
        _write_back_to_backlog(
            name, "paused", ctx.config.batch_id,
            ctx.config.overnight_events_path,
            backlog_id=ctx.backlog_ids.get(name),
        )

    if ctx.cb_state.consecutive_pauses >= CIRCUIT_BREAKER_THRESHOLD:
        ctx.batch_result.circuit_breaker_fired = True
        overnight_log_event(
            CIRCUIT_BREAKER,
            ctx.config.batch_id,
            feature=name,
            details={
                "reason": "batch circuit breaker: 3 consecutive pauses",
                "remaining_features": [
                    n for n in ctx.feature_names
                    if n not in ctx.batch_result.features_merged
                    and not any(d["name"] == n for d in ctx.batch_result.features_paused)
                    and not any(d["name"] == n for d in ctx.batch_result.features_deferred)
                    and not any(d["name"] == n for d in ctx.batch_result.features_failed)
                ],
            },
            log_path=ctx.config.overnight_events_path,
        )


# ---------------------------------------------------------------------------
# Async public entry point: apply_feature_result
# ---------------------------------------------------------------------------


async def apply_feature_result(
    name: str,
    result: FeatureResult,
    ctx: OutcomeContext,
    *,
    deferred_dir: Path = DEFAULT_DEFERRED_DIR,
) -> None:
    """Async public entry point for routing a feature result.

    Owns the lock acquisition and the two-phase lock structure: the first
    lock block dispatches the outcome (including merge + review gating for
    completed features), and if test recovery is needed the lock is
    released for the ``recover_test_failure()`` call and re-acquired to
    route the recovery result.

    Callers must NOT hold ``ctx.lock`` when invoking this function.
    """
    need_recovery = False
    actual_branch: str | None = None
    merge_result = None
    repo_path = ctx.repo_path_map.get(name)
    worktree_path = ctx.worktree_paths.get(name)

    async with ctx.lock:
        if result.status != "completed":
            # Non-completed: delegate entirely to _apply_feature_result
            _apply_feature_result(name, result, ctx, deferred_dir=deferred_dir)
            if result.repair_agent_used:
                ctx.recovery_attempts_map[name] = ctx.recovery_attempts_map.get(name, 0) + 1

            return

        # --- Completed feature: intercept merge to check for test failures ---
        actual_branch = (ctx.worktree_branches or {}).get(name)
        changed_files = _get_changed_files(name, ctx.config.base_branch, branch=actual_branch)
        ctx.batch_result.key_files_changed[name] = changed_files

        if not changed_files:
            # No commits — fall through to _apply_feature_result (no-commit guard)
            _apply_feature_result(name, result, ctx, deferred_dir=deferred_dir)
            return

        # Attempt merge
        effective_branch = _effective_base_branch(
            repo_path, ctx.integration_branches, ctx.config.base_branch,
        )
        merge_result = merge_feature(
            feature=name,
            base_branch=effective_branch,
            test_command=ctx.config.test_command,
            log_path=ctx.config.pipeline_events_path,
            branch=actual_branch,
            repo_path=_effective_merge_repo_path(
                repo_path, ctx.integration_worktrees, ctx.integration_branches, ctx.session_id,
            ),
        )

        if merge_result.success:
            overnight_log_event(
                FEATURE_MERGED,
                ctx.config.batch_id,
                feature=name,
                details={"integration_branch": effective_branch},
                log_path=ctx.config.overnight_events_path,
            )
            # Review gating: check if post-merge review is required
            tier = read_tier(name)
            criticality = read_criticality(name)
            if requires_review(tier, criticality):
                try:
                    rr = await dispatch_review(
                        feature=name,
                        worktree_path=ctx.worktree_paths.get(name, Path(f"worktrees/{name}")),
                        branch=actual_branch or f"pipeline/{name}",
                        spec_path=Path(f"lifecycle/{name}/spec.md"),
                        complexity=tier,
                        criticality=criticality,
                        base_branch=_effective_base_branch(
                            repo_path, ctx.integration_branches, ctx.config.base_branch,
                        ),
                        repo_path=_effective_merge_repo_path(
                            repo_path, ctx.integration_worktrees, ctx.integration_branches, ctx.session_id,
                        ),
                        log_path=ctx.config.pipeline_events_path,
                    )
                    if rr.deferred:
                        ctx.batch_result.features_deferred.append({
                            "name": name,
                            "question_count": 1,
                        })
                        overnight_log_event(
                            FEATURE_DEFERRED,
                            ctx.config.batch_id,
                            feature=name,
                            details={"review_verdict": rr.verdict, "review_cycle": rr.cycle},
                            log_path=ctx.config.overnight_events_path,
                        )
                        _write_back_to_backlog(
                            name, "in_progress", ctx.config.batch_id,
                            ctx.config.overnight_events_path,
                            backlog_id=ctx.backlog_ids.get(name),
                        )
                        try:
                            cleanup_worktree(name, repo_path=repo_path, worktree_path=worktree_path)
                        except Exception:
                            pass
                        return
                except Exception as exc:
                    overnight_log_event(
                        FEATURE_DEFERRED,
                        ctx.config.batch_id,
                        feature=name,
                        details={
                            "error": f"dispatch_review raised {type(exc).__name__}: {exc}",
                            "review_dispatch_crashed": True,
                        },
                        log_path=ctx.config.overnight_events_path,
                    )
                    escalations_path = Path("lifecycle/escalations.jsonl")
                    deferral = DeferralQuestion(
                        feature=name,
                        question_id=_next_escalation_n(name, ctx.config.batch_id, escalations_path),
                        severity=SEVERITY_BLOCKING,
                        context=(
                            "Feature merged successfully but post-merge review dispatch "
                            f"raised an unexpected exception: {type(exc).__name__}: {exc}"
                        ),
                        question=(
                            f"Feature '{name}' merged but the review dispatch crashed. "
                            "Should this feature be marked complete (skipping review) or held "
                            "for manual review?"
                        ),
                        options_considered=["mark complete (skip review)", "hold for manual review"],
                        pipeline_attempted="dispatch_review() in apply_feature_result()",
                    )
                    write_deferral(deferral, deferred_dir=deferred_dir)
                    ctx.batch_result.features_deferred.append({
                        "name": name,
                        "question_count": 1,
                    })
                    _write_back_to_backlog(
                        name, "in_progress", ctx.config.batch_id,
                        ctx.config.overnight_events_path,
                        backlog_id=ctx.backlog_ids.get(name),
                    )
                    return

            # Standard merged path (no review needed, or review approved)
            ctx.batch_result.features_merged.append(name)
            ctx.cb_state.consecutive_pauses = 0
            overnight_log_event(
                FEATURE_COMPLETE,
                ctx.config.batch_id,
                feature=name,
                details={"files_changed": changed_files},
                log_path=ctx.config.overnight_events_path,
            )
            _write_back_to_backlog(
                name, "merged", ctx.config.batch_id,
                ctx.config.overnight_events_path,
                backlog_id=ctx.backlog_ids.get(name),
            )
            try:
                cleanup_worktree(name, repo_path=repo_path, worktree_path=worktree_path)
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
                context_text = (
                    "Merge blocked: CI run has a non-success conclusion "
                    "(failure, cancelled, timed_out, or action_required)."
                )

            escalations_path = Path("lifecycle/escalations.jsonl")
            deferral = DeferralQuestion(
                feature=name,
                question_id=_next_escalation_n(name, ctx.config.batch_id, escalations_path),
                severity=SEVERITY_BLOCKING,
                context=context_text,
                question=question_text,
                options_considered=["force-merge after CI resolves", "leave deferred for manual review"],
                pipeline_attempted="ci_check in merge_feature()",
            )
            write_deferral(deferral, deferred_dir=deferred_dir)
            ctx.batch_result.features_deferred.append({
                "name": name,
                "question_count": 1,
            })
            overnight_log_event(
                FEATURE_DEFERRED,
                ctx.config.batch_id,
                feature=name,
                details={"error": ci_error, "question_count": 1},
                log_path=ctx.config.overnight_events_path,
            )
            _write_back_to_backlog(
                name, "deferred", ctx.config.batch_id,
                ctx.config.overnight_events_path,
                backlog_id=ctx.backlog_ids.get(name),
            )
            return

        if merge_result.conflict:
            # Conflict — fall through to _apply_feature_result
            _apply_feature_result(name, result, ctx, deferred_dir=deferred_dir)
            return

        # --- Test failure (not success, not conflict, not CI error) ---
        if ctx.recovery_attempts_map.get(name, 0) >= 1:
            # Gate does not pass — fall through to standard paused path
            _apply_feature_result(name, result, ctx, deferred_dir=deferred_dir)
            return

        # Gate passes — prepare for recovery
        overnight_log_event(
            MERGE_RECOVERY_START,
            ctx.config.batch_id,
            feature=name,
            details={
                "test_output": (
                    merge_result.test_result.output[:500]
                    if merge_result.test_result else ""
                ),
            },
            log_path=ctx.config.overnight_events_path,
        )
        ctx.recovery_attempts_map[name] = ctx.recovery_attempts_map.get(name, 0) + 1
        # Persist recovery_attempts immediately so a mid-batch kill doesn't
        # lose the increment.
        try:
            _ra_state = load_state(ctx.config.overnight_state_path)
            _ra_fs = _ra_state.features.get(name)
            if _ra_fs is not None:
                _ra_fs.recovery_attempts = ctx.recovery_attempts_map[name]
                save_state(_ra_state, ctx.config.overnight_state_path)
        except Exception:
            pass  # Don't let state-write failure block recovery
        need_recovery = True
        # Lock will be released when we exit `async with ctx.lock:`

    # --- Recovery (outside the lock) ---
    if need_recovery:
        recovery_result = await recover_test_failure(
            feature=name,
            base_branch=ctx.config.base_branch,
            test_output=(
                merge_result.test_result.output
                if merge_result and merge_result.test_result else ""
            ),
            branch=actual_branch or f"pipeline/{name}",
            worktree_path=ctx.worktree_paths.get(name),
            learnings_dir=Path(f"lifecycle/{name}/learnings"),
            test_command=ctx.config.test_command,
            pipeline_log_path=ctx.config.pipeline_events_path,
            repo_path=_effective_merge_repo_path(
                repo_path, ctx.integration_worktrees, ctx.integration_branches, ctx.session_id,
            ),
        )

        # Re-acquire the lock to route the recovery result
        async with ctx.lock:
            if recovery_result.success and recovery_result.flaky:
                overnight_log_event(
                    MERGE_RECOVERY_FLAKY,
                    ctx.config.batch_id,
                    feature=name,
                    details={"attempts": recovery_result.attempts},
                    log_path=ctx.config.overnight_events_path,
                )
                ctx.batch_result.features_merged.append(name)
                ctx.cb_state.consecutive_pauses = 0
                _write_back_to_backlog(
                    name, "merged", ctx.config.batch_id,
                    ctx.config.overnight_events_path,
                    backlog_id=ctx.backlog_ids.get(name),
                )
                try:
                    cleanup_worktree(name, repo_path=repo_path, worktree_path=worktree_path)
                except Exception:
                    pass
            elif recovery_result.success and not recovery_result.flaky:
                overnight_log_event(
                    MERGE_RECOVERY_SUCCESS,
                    ctx.config.batch_id,
                    feature=name,
                    details={"attempts": recovery_result.attempts},
                    log_path=ctx.config.overnight_events_path,
                )
                ctx.batch_result.features_merged.append(name)
                ctx.cb_state.consecutive_pauses = 0
                _write_back_to_backlog(
                    name, "merged", ctx.config.batch_id,
                    ctx.config.overnight_events_path,
                    backlog_id=ctx.backlog_ids.get(name),
                )
                try:
                    cleanup_worktree(name, repo_path=repo_path, worktree_path=worktree_path)
                except Exception:
                    pass
            else:
                # Recovery failed — pause the feature
                error = recovery_result.error or "recovery failed"
                overnight_log_event(
                    MERGE_RECOVERY_FAILED,
                    ctx.config.batch_id,
                    feature=name,
                    details={
                        "attempts": recovery_result.attempts,
                        "error": error,
                    },
                    log_path=ctx.config.overnight_events_path,
                )
                ctx.batch_result.features_paused.append({
                    "name": name,
                    "error": f"merge recovery failed: {error}",
                })
                ctx.cb_state.consecutive_pauses += 1
                _write_back_to_backlog(
                    name, "paused", ctx.config.batch_id,
                    ctx.config.overnight_events_path,
                    backlog_id=ctx.backlog_ids.get(name),
                )

                # Check circuit breaker after pause (site 2 of 2)
                if ctx.cb_state.consecutive_pauses >= CIRCUIT_BREAKER_THRESHOLD:
                    ctx.batch_result.circuit_breaker_fired = True
                    overnight_log_event(
                        CIRCUIT_BREAKER,
                        ctx.config.batch_id,
                        feature=name,
                        details={
                            "reason": "batch circuit breaker: 3 consecutive pauses",
                            "remaining_features": [
                                n for n in ctx.feature_names
                                if n not in ctx.batch_result.features_merged
                                and not any(d["name"] == n for d in ctx.batch_result.features_paused)
                                and not any(d["name"] == n for d in ctx.batch_result.features_deferred)
                                and not any(d["name"] == n for d in ctx.batch_result.features_failed)
                            ],
                        },
                        log_path=ctx.config.overnight_events_path,
                    )
