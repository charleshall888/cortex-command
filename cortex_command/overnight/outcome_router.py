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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from cortex_command.overnight.orchestrator import BatchResult, BatchConfig

from cortex_command.common import (
    _resolve_user_project_root,
    read_criticality,
    read_tier,
    reduce_lifecycle_state,
    requires_review,
)
from cortex_command.overnight.constants import (
    CIRCUIT_BREAKER_THRESHOLD,
    REVIEW_DISPATCH_CRASH,
    REVIEW_NO_ARTIFACT,
    SYSTEMIC_FAILURE_THRESHOLD,
    _SYSTEMIC_ERROR_TYPES,
)
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
    PIPELINE_SYSTEMIC_FAILURE,
    REPAIR_AGENT_RESOLVED,
    TRIVIAL_CONFLICT_RESOLVED,
    log_event as overnight_log_event,
)
from cortex_command.overnight.state import _normalize_repo_key, load_state, save_state
from cortex_command.overnight.types import CircuitBreakerState, FeatureResult
from cortex_command.pipeline.merge import merge_feature, revert_merge
from cortex_command.pipeline.merge_recovery import recover_test_failure
from cortex_command.pipeline.review_dispatch import dispatch_review
from cortex_command.pipeline.worktree import cleanup_worktree


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
    home_worktree_path: Path | None = None


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


def _merge_target_repo_path(ctx: OutcomeContext, name: str) -> Path | None:
    """Resolve the merge/recovery/review target worktree for a feature.

    Home-repo features (``repo_path is None``) target the home integration
    worktree recorded in ``ctx.home_worktree_path`` so merges run against the
    long-lived integration worktree that already owns
    ``overnight/<session_id>`` instead of the user's live working tree.
    Cross-repo features delegate byte-for-byte to
    ``_effective_merge_repo_path``.
    """
    if ctx.repo_path_map.get(name) is None:
        return ctx.home_worktree_path
    return _effective_merge_repo_path(
        ctx.repo_path_map.get(name),
        ctx.integration_worktrees,
        ctx.integration_branches,
        ctx.session_id,
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


def _overlapping_features(
    feature: str,
    changed_files: list[str],
    key_files_changed: dict[str, list[str]],
) -> list[str]:
    """Return in-batch features (other than *feature*) whose changed files
    overlap *changed_files*.

    Used to name the dependent feature(s) Y in the dependent-conflict R-edge
    deferral: when reverting *feature*'s merge conflicts, the conflicting code
    is shared with whichever later-merged feature touched the same files. A
    file-set intersection is a deterministic, git-output-independent way to
    surface that dependency to morning triage.
    """
    own = set(changed_files)
    if not own:
        return []
    dependents = [
        other
        for other, files in key_files_changed.items()
        if other != feature and own.intersection(files or [])
    ]
    return sorted(dependents)


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

# Runtime backlog directory — set from overnight state so write-backs find items
# in external repos. Falls back to ``_resolve_user_project_root() / "cortex" / "backlog"``
# (resolved at call time) when unset, which anchors the lookup at the user's
# project root via the CORTEX_REPO_ROOT env var or CWD probe rather than at a
# module-anchored path.
_backlog_dir: Optional[Path] = None


def set_backlog_dir(path: Path) -> None:
    """Set the backlog directory used by write-back helpers at runtime."""
    global _backlog_dir
    _backlog_dir = path


from cortex_command.backlog.update_item import update_item as _backlog_update_item  # noqa: E402
from cortex_command.backlog.update_item import _find_item as _backlog_find_item  # noqa: E402

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
      1. Exact match: ``cortex/backlog/NNN-{feature}.md``
      2. If *backlog_id* is provided, match ``cortex/backlog/{NNN}-*.md``
      3. Canonical resolution via ``_find_item`` → ``resolve_item.resolve``,
         which matches ``uuid``/``backlog_id``/``lifecycle_slug`` frontmatter —
         covering the common case where the lifecycle slug differs from the
         backlog filename stem. Returns ``None`` on a no-match or ambiguous
         result so the caller's best-effort swallow applies.
    """
    backlog_dir = _backlog_dir if _backlog_dir is not None else _resolve_user_project_root() / "cortex" / "backlog"

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

    # 3. Canonical resolution via update_item's finder, which delegates to
    #    resolve_item.resolve — matches uuid/backlog_id/lifecycle_slug frontmatter,
    #    covering the common case where the lifecycle slug differs from the
    #    filename stem. Returns None on a no-match/ambiguous result so the
    #    caller's best-effort swallow applies.
    return _backlog_find_item(feature, backlog_dir=backlog_dir)


def _write_back_to_backlog(
    feature: str,
    overnight_status: str,
    round_number: int,
    log_path: Path,
    backlog_id: Optional[int] = None,
    *,
    recoverable_branch: Optional[str] = None,
) -> None:
    """Best-effort write of canonical status back to the backlog item.

    Maps *overnight_status* to the canonical backlog fields defined in R13
    and calls ``update_item()`` from ``cortex/backlog/update_item.py``. All
    exceptions are caught, logged to the overnight events log, and silently
    swallowed so the overnight session never aborts on a backlog write failure.

    When *recoverable_branch* is set (the built-but-merge-blocked recoverable
    sub-case), the ``_OVERNIGHT_TO_BACKLOG`` mapping is bypassed: the item is
    written ``status: in_progress`` and records the recovery branch, keeping it
    out of the from-scratch-rebuild pool the ``deferred → backlog`` mapping
    would otherwise re-queue it into.
    """
    mapping = _OVERNIGHT_TO_BACKLOG.get(overnight_status)
    if mapping is None and not recoverable_branch:
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
        fields: dict[str, Any]
        if recoverable_branch:
            fields = {
                "status": "in_progress",
                "session_id": None,
                "recoverable_branch": recoverable_branch,
            }
        else:
            fields = {}
            for key, value in mapping.items():
                if value == "_CURRENT_":
                    fields[key] = session_id
                else:
                    fields[key] = value

        backlog_dir = _backlog_dir if _backlog_dir is not None else _resolve_user_project_root() / "cortex" / "backlog"
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
    if result.status == "repair_completed":
        # Fast-forward merge the repair branch into base_branch.
        repo = _merge_target_repo_path(ctx, name)
        if ctx.repo_path_map.get(name) is None and repo is None:
            # Home feature whose integration worktree could not be resolved
            # (degraded path: TMPDIR wiped / resumed session). Pause and surface
            # rather than falling back to Path.cwd() / the home working tree,
            # whose git checkout overnight/<id> would collide with the
            # integration worktree that already owns that branch.
            error = "integration worktree unresolved"
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
            return
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
            # R12 runtime guard: this sync ff-merge success arm is provably
            # unreachable for a review-qualifying feature — apply_feature_result
            # intercepts repair_completed and routes it through
            # _repair_completed_review_gate before it can delegate here. Fail
            # loudly if that invariant is ever violated (a review-qualifying
            # feature must never be marked `merged` here un-reviewed).
            _guard_no_review_qualifying_sync_merge(name, "repair_completed ff-merge")
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
                cleanup_worktree(name, branch=f"pipeline/{name}", repo_path=repo_path, worktree_path=worktree_path)
            except Exception:
                pass
        else:
            error = f"repair_ff_merge_failed: {ff_result.stderr.strip()}"
            ctx.batch_result.features_paused.append({"name": name, "error": error})
            ctx.cb_state.consecutive_pauses += 1
            if error in _SYSTEMIC_ERROR_TYPES:
                ctx.cb_state.systemic_pauses_in_batch += 1
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
            if error in _SYSTEMIC_ERROR_TYPES:
                ctx.cb_state.systemic_pauses_in_batch += 1
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
        merge_target = _merge_target_repo_path(ctx, name)
        if ctx.repo_path_map.get(name) is None and merge_target is None:
            # Home feature whose integration worktree could not be resolved
            # (degraded path: TMPDIR wiped / resumed session). Pause and surface
            # rather than passing repo_path=None onward and falling back to the
            # home working tree, which would re-create the worktree collision.
            error = "integration worktree unresolved"
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
            return
        merge_result = merge_feature(
            feature=name,
            base_branch=effective_branch,
            test_command=ctx.config.test_command,
            log_path=ctx.config.pipeline_events_path,
            branch=actual_branch,
            repo_path=merge_target,
        )

        if merge_result.success:
            # R12 runtime guard: this sync ``completed`` merge-success arm is
            # provably unreachable for a review-qualifying feature. Every
            # delegation into this branch from apply_feature_result has already
            # proven the merge non-successful for this feature — the no-commit
            # guard (empty changed_files), a merge conflict, or a test failure
            # with recovery exhausted — so a re-attempted merge_feature() here
            # cannot succeed for a review-qualifying feature whose async merge
            # already failed. The review gate lives in the async layer; this
            # sync function never dispatches review, so a review-qualifying
            # feature reaching `merged` here would ship un-reviewed. Fail loudly
            # if that invariant is ever violated.
            _guard_no_review_qualifying_sync_merge(name, "completed merge-success")
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
                cleanup_worktree(name, branch=f"pipeline/{name}", repo_path=repo_path, worktree_path=worktree_path)
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

            deferral = DeferralQuestion(
                feature=name,
                question_id=_next_escalation_n(
                    name, ctx.config.batch_id, ctx.config.session_dir,
                ),
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
        elif merge_result.conflict:
            # Genuine merge conflict that exhausted automated repair: the
            # feature is BUILT but merge-blocked. Route to a recoverable
            # `deferred` disposition carrying its actual branch rather than
            # `paused` — it must not auto-retry, must not feed the systemic
            # circuit-breaker, and must not be counted as a pause. The branch
            # is `actual_branch` when known (suffix-correct, e.g.
            # pipeline/<name>-2) and None otherwise — never a bare
            # f"pipeline/{name}" reconstruction. Safe without a has-commits
            # assertion *only while* this terminus stays gated on
            # conflict=True: an empty pipeline/<name>-N branch merges cleanly
            # (conflict=False) and never reaches here.
            error = merge_result.error or "merge failed"
            recoverable_branch = actual_branch or None
            if merge_result.classification is not None:
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
            ctx.batch_result.features_deferred.append({
                "name": name,
                "question_count": 0,
                "recoverable_branch": recoverable_branch,
            })
            overnight_log_event(
                FEATURE_DEFERRED,
                ctx.config.batch_id,
                feature=name,
                details={
                    "error": error,
                    "conflict": True,
                    "recoverable_branch": recoverable_branch,
                },
                log_path=ctx.config.overnight_events_path,
            )
            _write_back_to_backlog(
                name, "deferred", ctx.config.batch_id,
                ctx.config.overnight_events_path,
                backlog_id=ctx.backlog_ids.get(name),
                recoverable_branch=recoverable_branch,
            )
        else:
            error = merge_result.error or "merge failed"
            ctx.batch_result.features_paused.append({"name": name, "error": error})
            ctx.cb_state.consecutive_pauses += 1
            if error in _SYSTEMIC_ERROR_TYPES:
                ctx.cb_state.systemic_pauses_in_batch += 1
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
            if result.error in _SYSTEMIC_ERROR_TYPES:
                ctx.cb_state.systemic_pauses_in_batch += 1
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
        if result.error in _SYSTEMIC_ERROR_TYPES:
            ctx.cb_state.systemic_pauses_in_batch += 1
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
    if (
        ctx.cb_state.systemic_pauses_in_batch >= SYSTEMIC_FAILURE_THRESHOLD
        and not ctx.batch_result.global_abort_signal
    ):
        trailing = ctx.batch_result.features_paused[-SYSTEMIC_FAILURE_THRESHOLD:]
        cause_class = [
            entry["error"] for entry in trailing
            if entry["error"] in _SYSTEMIC_ERROR_TYPES
        ]
        overnight_log_event(
            PIPELINE_SYSTEMIC_FAILURE,
            ctx.config.batch_id,
            feature=name,
            details={"cause_class": cause_class, "threshold": SYSTEMIC_FAILURE_THRESHOLD},
            log_path=ctx.config.overnight_events_path,
        )
        ctx.batch_result.global_abort_signal = True


# ---------------------------------------------------------------------------
# Systemic review-crash circuit breaker (R11)
# ---------------------------------------------------------------------------


def _record_review_crash_systemic(
    name: str,
    ctx: OutcomeContext,
    cause_class: str = REVIEW_DISPATCH_CRASH,
) -> None:
    """Feed a systemic review-failure deferral into the circuit breaker.

    A single systemic review failure mode can affect multiple features
    byte-identically (the observed bug). Such a deferral routes the feature to
    ``features_deferred`` — invisible to the paused-path systemic blocks, which
    read ``features_paused`` — so this records it where the threshold derivation
    can see it:

      1. Increment ``cb_state.systemic_pauses_in_batch`` (the threshold counter).
      2. Append *cause_class* to ``cb_state.review_crash_classes`` (the structure
         the threshold block reads to compute a ``cause_class`` attributable to
         the review failures, not an unrelated paused feature).

    *cause_class* distinguishes the two systemic review-failure kinds in the
    emitted event WITHOUT splitting the counter: ``REVIEW_DISPATCH_CRASH`` for a
    genuine dispatch crash (``success == False`` / a raised exception, from the
    crash-``except`` blocks) and ``REVIEW_NO_ARTIFACT`` for a could-not-run
    review (the agent completed but produced no usable verdict, from the in-band
    ``verdict == "ERROR"`` sites). Both must be members of
    ``_SYSTEMIC_ERROR_TYPES`` so the threshold derivation recognizes them. The
    threshold is on the AGGREGATE count, so a mixed crash + no-artifact batch
    trips at ``SYSTEMIC_FAILURE_THRESHOLD`` carrying both labels (R7).

    When the threshold is reached it emits ``PIPELINE_SYSTEMIC_FAILURE`` with a
    non-empty ``cause_class`` and sets ``global_abort_signal`` — coherently,
    because the derived cause is the review-failure class, never a flag flipped
    with an empty cause. Call this on every systemic review-failure deferral path
    (verdict ``ERROR`` could-not-run, or a raised dispatch exception crash); a
    review that ran and said no (REJECTED / CHANGES_REQUESTED) is substantive
    feedback, not a failure, and does NOT feed this breaker.
    """
    ctx.cb_state.systemic_pauses_in_batch += 1
    ctx.cb_state.review_crash_classes.append(cause_class)
    if (
        ctx.cb_state.systemic_pauses_in_batch >= SYSTEMIC_FAILURE_THRESHOLD
        and not ctx.batch_result.global_abort_signal
    ):
        # Derive the trailing cause_class from the combined arrival of systemic
        # paused errors and review-failure classes, taking the trailing window.
        # The review-failure classes are appended last so an all-review-failure
        # batch yields a cause_class of the genuine review classes
        # (REVIEW_DISPATCH_CRASH and/or REVIEW_NO_ARTIFACT) — the classes
        # genuinely attributable to the review failures (R11 coherence
        # requirement), never one accidentally derived from an unrelated paused
        # feature. A mixed crash + no-artifact batch surfaces BOTH labels for
        # diagnosis (R7); the threshold itself is on the aggregate count.
        paused_systemic = [
            entry["error"]
            for entry in ctx.batch_result.features_paused
            if entry["error"] in _SYSTEMIC_ERROR_TYPES
        ]
        combined = paused_systemic + list(ctx.cb_state.review_crash_classes)
        cause_class = combined[-SYSTEMIC_FAILURE_THRESHOLD:]
        overnight_log_event(
            PIPELINE_SYSTEMIC_FAILURE,
            ctx.config.batch_id,
            feature=name,
            details={"cause_class": cause_class, "threshold": SYSTEMIC_FAILURE_THRESHOLD},
            log_path=ctx.config.overnight_events_path,
        )
        ctx.batch_result.global_abort_signal = True


def _review_required(name: str) -> bool:
    """Whether a feature must go through post-merge review.

    A single ``reduce_lifecycle_state`` pass gives the OR's two legs snapshot
    coherence: ``requires_review(tier, criticality)`` on the matrix axes, OR the
    corruption signal when a torn or out-of-vocabulary events.log left the gate
    input unknowable (spec R8a — fail safe toward review). Separate
    read_tier / read_criticality / predicate calls would take up to three
    independent stat+reads of the same file, and a write landing between them
    could invert the fail-safe.
    """
    reduction = reduce_lifecycle_state(Path(f"cortex/lifecycle/{name}/events.log"))
    tier = reduction.state.get("tier", "simple")
    criticality = reduction.state.get("criticality", "medium")
    return requires_review(tier, criticality) or reduction.corrupted


def _set_review_error_detail_flags(details: dict, *, merge_reverted: bool) -> None:
    """Set the verdict-ERROR deferral-detail flags coherently across all three
    review gate sites.

    A could-not-run review (resolved verdict ``ERROR`` with the agent having
    completed) carries the positive ``could_not_run`` discriminator that the
    morning report and integration PR key on; it is never inferred from
    ``merge_reverted == False`` (a genuine crash with a failed revert, or a
    repair-path ``_reset_ff_merge`` returning False, also yields
    ``merge_reverted == False``). This helper is invoked ONLY from the three
    in-band ``if rr.verdict == "ERROR":`` sites — i.e. the could-not-run path
    where the review agent completed (``success == True``) but produced no
    usable verdict. It therefore sets ``could_not_run`` and does NOT set
    ``review_dispatch_crashed`` (spec R6): ``review_dispatch_crashed`` denotes
    only a genuine dispatch crash (``success == False`` / a raised exception),
    which the crash-``except`` blocks tag inline, never via this helper.

    Sets ``merge_reverted`` to the authoritative value passed by the caller so
    a preserved (not-reverted) could-not-run merge records ``merge_reverted ==
    False``. The revert-skip itself is a per-site guard on each site's own
    ``revert_merge`` / ``_reset_ff_merge`` call — this helper only unifies the
    detail-flag setting, which is identical across the three path-divergent
    reverts.
    """
    details["merge_reverted"] = merge_reverted
    details["could_not_run"] = True


# ---------------------------------------------------------------------------
# Recovery-path review gate (R10)
# ---------------------------------------------------------------------------


async def _recovery_review_gate(
    name: str,
    ctx: OutcomeContext,
    *,
    recovery_merge_sha: Optional[str],
    actual_branch: Optional[str],
    repo_path: Path | None,
    merge_target: Path | None,
    deferred_dir: Path,
) -> bool:
    """Route a test-recovery success through review before marking ``merged``.

    Called from both recovery success branches (flaky and recovered) while the
    re-acquired ``ctx.lock`` is held, so the recovery re-merge that produced
    ``recovery_merge_sha`` (R2), this review, and any R3 revert all execute
    serialized against sibling features' in-lock checkout/merge/revert on the
    shared integration worktree.

    For a feature where ``requires_review(tier, criticality)`` is True, dispatch
    review. On a non-APPROVED (``rr.deferred``) verdict OR a dispatch crash, the
    recovery re-merge is reverted SHA-anchored (R3) and the feature is deferred
    (a blocking deferral file + ``deferred`` backlog status), mirroring the
    primary-merge path. A feature for which ``requires_review`` is already False
    skips review as a legitimate non-review (logged), never a blanket escape.

    Returns:
        ``True`` when the feature was deferred on this path (the caller must NOT
        mark it ``merged``); ``False`` when it may proceed to ``merged`` (review
        approved, or review was legitimately not required).
    """
    tier = read_tier(name)
    criticality = read_criticality(name)
    if not _review_required(name):
        # Legitimate non-review: this feature does not qualify for the gate, so
        # the recovery merge proceeds to `merged`. Logged as a deliberate skip,
        # not a blanket escape. Corrupted state ORs in via _review_required so
        # an unknowable gate input fails safe toward review (spec R8a).
        overnight_log_event(
            FEATURE_MERGED,
            ctx.config.batch_id,
            feature=name,
            details={
                "review_skipped": True,
                "review_required": False,
                "path": "test_recovery",
            },
            log_path=ctx.config.overnight_events_path,
        )
        return False

    # Bind ``rr`` before the try so the crash-``except`` can tell a resolved
    # could-not-run review (preserve the merge) from a raised dispatch crash
    # (revert): when the in-band preserve path raises after a could-not-run
    # verdict resolved, control falls into the ``except`` and must NOT revert
    # the merge it was preserving. ``rr is None`` means the dispatch itself
    # crashed before resolving — the revert correctly still fires there.
    rr = None
    try:
        rr = await dispatch_review(
            feature=name,
            worktree_path=ctx.worktree_paths.get(name, Path(f"worktrees/{name}")),
            branch=actual_branch or f"pipeline/{name}",
            spec_path=Path(f"cortex/lifecycle/{name}/spec.md"),
            complexity=tier,
            criticality=criticality,
            base_branch=_effective_base_branch(
                repo_path, ctx.integration_branches, ctx.config.base_branch,
            ),
            repo_path=merge_target,
            log_path=ctx.config.pipeline_events_path,
        )
        if not rr.deferred:
            # Review approved — the recovery merge may proceed to `merged`.
            return False

        # Could-not-run preserve (spec R3): the review agent completed but
        # produced no usable verdict — PRESERVE the recovery merge rather than
        # reverting verified, hook-passing work. The merge stays on the
        # integration branch and is flagged for human re-review.
        if rr.could_not_run:
            revert_aborted = False
            merge_reverted = False
        else:
            # Fail-safe rollback: revert the recovery re-merge's LIVE merge commit
            # (SHA-anchored, under the held ctx.lock). Prefer a cycle-1 re-merge SHA
            # threaded onto the ReviewResult when present, else the recovery merge
            # SHA captured by recover_test_failure (R2).
            live_merge_sha = getattr(rr, "merge_sha", None) or recovery_merge_sha
            revert_aborted = False
            merge_reverted = False
            if live_merge_sha is not None:
                revert_outcome = revert_merge(
                    live_merge_sha,
                    repo_path=merge_target,
                    log_path=ctx.config.pipeline_events_path,
                    feature=name,
                )
                revert_aborted = revert_outcome.aborted
                merge_reverted = revert_outcome.success
        if revert_aborted:
            # Dependent-conflict R-edge: the revert conflicted and was aborted,
            # so the recovery merge genuinely REMAINS on the integration branch.
            dependents = _overlapping_features(
                name,
                ctx.batch_result.key_files_changed.get(name, []),
                ctx.batch_result.key_files_changed,
            )
            if dependents:
                dependent_clause = (
                    "Dependent feature(s) referencing the reverted code: "
                    + ", ".join(f"'{d}'" for d in dependents) + ". "
                )
            else:
                dependent_clause = "A later feature likely depends on it. "
            conflict_deferral = DeferralQuestion(
                feature=name,
                question_id=_next_escalation_n(
                    name, ctx.config.batch_id, ctx.config.session_dir,
                ),
                severity=SEVERITY_BLOCKING,
                context=(
                    f"Review deferred (verdict {rr.verdict!r}) after test recovery; "
                    f"the rollback of recovery merge {live_merge_sha} conflicted and "
                    "was aborted. The merge is still on the integration branch — do "
                    f"NOT re-run; manual rollback needed. {dependent_clause}"
                ),
                question=(
                    f"Feature '{name}' was deferred at post-recovery review but its "
                    "merge could not be reverted (revert conflict — a later feature "
                    f"depends on it). {dependent_clause}How should this be manually "
                    "rolled back?"
                ),
                options_considered=["manual revert + re-review", "keep merged and re-review in place"],
                pipeline_attempted="revert_merge() in _recovery_review_gate() (recovery path)",
            )
            write_deferral(conflict_deferral, deferred_dir=deferred_dir)

        ctx.batch_result.features_deferred.append({
            "name": name,
            "question_count": 1,
        })
        deferred_details: dict = {
            "review_verdict": rr.verdict,
            "review_cycle": rr.cycle,
            "merge_reverted": merge_reverted,
            "path": "test_recovery",
        }
        if rr.verdict == "ERROR":
            _set_review_error_detail_flags(
                deferred_details, merge_reverted=merge_reverted
            )
        overnight_log_event(
            FEATURE_DEFERRED,
            ctx.config.batch_id,
            feature=name,
            details=deferred_details,
            log_path=ctx.config.overnight_events_path,
        )
        # R7/R11: a could-not-run review (verdict ERROR, agent completed) on the
        # recovery path is a no-artifact systemic review failure — feed it into
        # the systemic circuit breaker tagged REVIEW_NO_ARTIFACT (distinct from
        # a genuine dispatch crash, tagged in the except block below).
        if rr.verdict == "ERROR":
            _record_review_crash_systemic(name, ctx, REVIEW_NO_ARTIFACT)
        _write_back_to_backlog(
            name, "deferred", ctx.config.batch_id,
            ctx.config.overnight_events_path,
            backlog_id=ctx.backlog_ids.get(name),
        )
        return True

    except Exception as exc:
        # Exception-safety guard (spec R3, load-bearing): if the resolved
        # review was could-not-run, the in-band preserve path was supposed to
        # keep the merge — an exception thrown anywhere in that path (the
        # flag-helper, the deferral write, overnight_log_event, the backlog
        # write-back) must NOT fall through here and revert-as-crash the very
        # merge it preserved. Skip the revert + tag could_not_run in that case.
        # When ``rr is None`` the dispatch itself crashed before resolving, so
        # the revert correctly still fires (a genuine crash).
        preserved = rr is not None and rr.could_not_run
        if not preserved and recovery_merge_sha is not None:
            # Fail-safe rollback on a genuine review-dispatch crash: revert the
            # recovery re-merge's LIVE merge commit (SHA-anchored, under the
            # held ctx.lock) before surfacing the deferral.
            revert_merge(
                recovery_merge_sha,
                repo_path=merge_target,
                log_path=ctx.config.pipeline_events_path,
                feature=name,
            )
        crash_details: dict = {
            "error": f"dispatch_review raised {type(exc).__name__}: {exc}",
            "path": "test_recovery",
        }
        if preserved:
            crash_details["could_not_run"] = True
            crash_details["merge_reverted"] = False
        else:
            crash_details["review_dispatch_crashed"] = True
        overnight_log_event(
            FEATURE_DEFERRED,
            ctx.config.batch_id,
            feature=name,
            details=crash_details,
            log_path=ctx.config.overnight_events_path,
        )
        deferral = DeferralQuestion(
            feature=name,
            question_id=0,
            severity=SEVERITY_BLOCKING,
            context=(
                "Feature merged successfully after test recovery but post-merge "
                "review dispatch raised an unexpected exception: "
                f"{type(exc).__name__}: {exc}"
            ),
            question=(
                f"Feature '{name}' merged after test recovery but the review "
                "dispatch crashed. Should this feature be marked complete "
                "(skipping review) or held for manual review?"
            ),
            options_considered=["mark complete (skip review)", "hold for manual review"],
            pipeline_attempted="dispatch_review() in _recovery_review_gate()",
        )
        write_deferral(deferral, deferred_dir=deferred_dir, idempotent=True)
        ctx.batch_result.features_deferred.append({
            "name": name,
            "question_count": 1,
        })
        # R7/R11: a raised dispatch exception on the recovery path is a genuine
        # review-dispatch crash — feed it into the systemic circuit breaker
        # tagged REVIEW_DISPATCH_CRASH (the helper's default).
        _record_review_crash_systemic(name, ctx, REVIEW_DISPATCH_CRASH)
        _write_back_to_backlog(
            name, "deferred", ctx.config.batch_id,
            ctx.config.overnight_events_path,
            backlog_id=ctx.backlog_ids.get(name),
        )
        return True


# ---------------------------------------------------------------------------
# Repair-completed review gate (R12)
# ---------------------------------------------------------------------------


# Sentinel error used when a review-qualifying feature reaches a sync
# merge-to-`merged` write site that the async layer is supposed to have
# intercepted. The two sync merge-success sites (the ``repair_completed``
# ff-merge and the ``completed`` merge-success branch in
# ``_apply_feature_result``) are provably unreachable for a feature where
# ``requires_review(tier, criticality)`` is True: ``apply_feature_result``
# intercepts ``repair_completed`` (routing it through
# ``_repair_completed_review_gate``) before it can delegate to the sync
# function, and every delegation into the sync ``completed`` branch has
# already proven the merge non-successful (no-commit guard, conflict, or a
# test failure with recovery exhausted), so its ``merge_result.success``
# arm never fires for a review-qualifying feature. These are LIVE code
# paths, not dead branches, so per R12 they carry a runtime guard that
# RAISES loudly if a review-qualifying feature ever reaches them — closing
# the un-reviewed-merge invariant by assertion rather than by annotation.
_REVIEW_QUALIFYING_SYNC_MERGE_MSG = (
    "review-qualifying feature {feature!r} reached the sync {site} "
    "merge-to-`merged` write site un-reviewed; the async layer must route "
    "review-qualifying features through review before this site is reached "
    "(R12 invariant: no review-qualifying feature reaches `merged` "
    "un-reviewed via any path)"
)


def _guard_no_review_qualifying_sync_merge(name: str, site: str) -> None:
    """Raise if a review-qualifying feature reaches a sync merge-success site.

    The runtime guard for the two LIVE sync merge-to-``merged`` write sites
    (R12). It fails loudly rather than silently marking a review-qualifying
    feature ``merged`` without a review, preserving the invariant that no
    review-qualifying feature reaches ``merged`` un-reviewed via any path.
    A feature for which ``requires_review`` is already False passes through
    silently (it never qualified for the gate).
    """
    if requires_review(read_tier(name), read_criticality(name)):
        raise RuntimeError(
            _REVIEW_QUALIFYING_SYNC_MERGE_MSG.format(feature=name, site=site)
        )


async def _repair_completed_review_gate(
    name: str,
    result: FeatureResult,
    ctx: OutcomeContext,
    *,
    deferred_dir: Path,
) -> None:
    """Fast-forward merge a ``repair_completed`` feature, gating on review (R12).

    This is the async owner of the ``repair_completed`` ff-merge: it performs
    the ``git merge --ff-only`` of the resolved-conflict repair branch and,
    for a feature where ``requires_review(tier, criticality)`` is True,
    dispatches review before marking ``merged``. On a non-APPROVED
    (``rr.deferred``) verdict OR a dispatch crash, the ff-merge is rolled back
    (``git reset --hard`` to the pre-ff base tip — the ff-merge produces no
    merge commit, so ``revert_merge -m 1`` does not apply) and the feature is
    deferred with a blocking deferral, mirroring the primary-merge and
    recovery gates. A feature for which ``requires_review`` is False skips
    review as a legitimate non-review (logged), never a blanket escape.

    The caller (``apply_feature_result``) holds ``ctx.lock`` across this whole
    call, so the ff-merge, the review, and any reset run serialized against
    sibling features' in-lock checkout/merge/revert on the shared integration
    worktree (spec Technical Constraints).
    """
    repo_path = ctx.repo_path_map.get(name)
    worktree_path = ctx.worktree_paths.get(name)
    repo = _merge_target_repo_path(ctx, name)
    if ctx.repo_path_map.get(name) is None and repo is None:
        # Home feature whose integration worktree could not be resolved
        # (degraded path: TMPDIR wiped / resumed session). Pause and surface
        # rather than falling back to Path.cwd() / the home working tree,
        # whose git checkout overnight/<id> would collide with the
        # integration worktree that already owns that branch.
        error = "integration worktree unresolved"
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
        return

    subprocess.run(
        ["git", "checkout", ctx.config.base_branch],
        cwd=repo,
        capture_output=True,
    )
    # Capture the pre-ff base tip so a review-defer can roll the ff-merge back
    # (a fast-forward leaves no merge commit, so the rollback is a `git reset
    # --hard <pre_ff_base>` rather than `git revert -m 1`).
    pre_ff_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    pre_ff_base_sha = pre_ff_head.stdout.strip() if pre_ff_head.returncode == 0 else None
    ff_result = subprocess.run(
        ["git", "merge", "--ff-only", result.repair_branch],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    if ff_result.returncode != 0:
        error = f"repair_ff_merge_failed: {ff_result.stderr.strip()}"
        ctx.batch_result.features_paused.append({"name": name, "error": error})
        ctx.cb_state.consecutive_pauses += 1
        if error in _SYSTEMIC_ERROR_TYPES:
            ctx.cb_state.systemic_pauses_in_batch += 1
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
        return

    # ff-merge landed. Gate on review before marking `merged` (R12/R10 gate).
    # Corrupted state ORs in via _review_required → fail safe toward review (R8a).
    if _review_required(name):
        deferred = await _repair_review_or_revert(
            name,
            ctx,
            repo=repo,
            pre_ff_base_sha=pre_ff_base_sha,
            actual_branch=(ctx.worktree_branches or {}).get(name),
            repo_path=repo_path,
            deferred_dir=deferred_dir,
        )
        if deferred:
            # Rolled back + surfaced: do NOT mark merged, do NOT delete the
            # repair branch (the work is no longer merged and triage may need it).
            try:
                cleanup_worktree(name, branch=f"pipeline/{name}", repo_path=repo_path, worktree_path=worktree_path)
            except Exception:
                pass
            return

    # Review approved, or review not required (legitimate non-review) — finalize.
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
        cleanup_worktree(name, branch=f"pipeline/{name}", repo_path=repo_path, worktree_path=worktree_path)
    except Exception:
        pass


async def _repair_review_or_revert(
    name: str,
    ctx: OutcomeContext,
    *,
    repo: Path | None,
    pre_ff_base_sha: Optional[str],
    actual_branch: Optional[str],
    repo_path: Path | None,
    deferred_dir: Path,
) -> bool:
    """Dispatch review for a freshly ff-merged repair feature; revert on defer.

    Mirrors the recovery/primary gate but rolls the ff-merge back with a
    ``git reset --hard <pre_ff_base_sha>`` (the ff-merge has no merge commit).
    Returns ``True`` when the feature was deferred (caller must NOT mark it
    ``merged``); ``False`` when review approved and it may proceed.
    """
    tier = read_tier(name)
    criticality = read_criticality(name)
    # Bind ``rr`` before the try so the crash-``except`` can tell a resolved
    # could-not-run review (preserve the ff-merge) from a raised dispatch crash
    # (reset): an exception thrown in the in-band preserve path after a
    # could-not-run verdict resolved must NOT fall into the ``except`` and
    # ``git reset --hard`` away the very ff-merge it was preserving.
    rr = None
    try:
        rr = await dispatch_review(
            feature=name,
            worktree_path=ctx.worktree_paths.get(name, Path(f"worktrees/{name}")),
            branch=actual_branch or f"pipeline/{name}",
            spec_path=Path(f"cortex/lifecycle/{name}/spec.md"),
            complexity=tier,
            criticality=criticality,
            base_branch=_effective_base_branch(
                repo_path, ctx.integration_branches, ctx.config.base_branch,
            ),
            repo_path=repo,
            log_path=ctx.config.pipeline_events_path,
        )
        if not rr.deferred:
            return False

        if rr.could_not_run:
            # Could-not-run preserve (spec R3): the review agent completed but
            # produced no usable verdict — PRESERVE the ff-merged repair work
            # rather than `git reset --hard`-ing it off the integration branch.
            # The ff-merge stays put and is flagged for human re-review.
            merge_reverted = False
        else:
            # Fail-safe rollback of the ff-merge: reset the base branch back to
            # its pre-ff tip so the unreviewed repair work is no longer on the
            # integration branch.
            merge_reverted = _reset_ff_merge(repo, pre_ff_base_sha)
        ctx.batch_result.features_deferred.append({
            "name": name,
            "question_count": 1,
        })
        deferred_details: dict = {
            "review_verdict": rr.verdict,
            "review_cycle": rr.cycle,
            "merge_reverted": merge_reverted,
            "path": "repair_completed",
        }
        if rr.verdict == "ERROR":
            _set_review_error_detail_flags(
                deferred_details, merge_reverted=merge_reverted
            )
        overnight_log_event(
            FEATURE_DEFERRED,
            ctx.config.batch_id,
            feature=name,
            details=deferred_details,
            log_path=ctx.config.overnight_events_path,
        )
        # R7/R11: a could-not-run review (verdict ERROR, agent completed) on the
        # repair_completed path is a no-artifact systemic review failure — feed
        # it into the systemic breaker tagged REVIEW_NO_ARTIFACT (distinct from
        # a genuine dispatch crash, tagged in the except block below).
        if rr.verdict == "ERROR":
            _record_review_crash_systemic(name, ctx, REVIEW_NO_ARTIFACT)
        if rr.could_not_run:
            context_clause = (
                "review could not run (agent completed, no usable verdict) — "
                "the ff-merge is PRESERVED on the integration branch for human "
                "re-review (intentional, not an error); do NOT re-run."
            )
        elif merge_reverted:
            context_clause = "ff-merge was rolled back — safe to re-review/re-run."
        else:
            context_clause = (
                "ff-merge could NOT be rolled back — manual rollback needed; do NOT re-run."
            )
        deferral = DeferralQuestion(
            feature=name,
            question_id=0,
            severity=SEVERITY_BLOCKING,
            context=(
                f"Feature '{name}' resolved a merge conflict and was ff-merged, "
                f"but post-merge review deferred (verdict {rr.verdict!r}). The "
                + context_clause
            ),
            question=(
                f"Feature '{name}' was deferred at post-repair review. How "
                "should it be handled?"
            ),
            options_considered=["re-review after fixes", "discard the repair branch"],
            pipeline_attempted="dispatch_review() in _repair_completed_review_gate()",
        )
        write_deferral(deferral, deferred_dir=deferred_dir, idempotent=True)
        _write_back_to_backlog(
            name, "deferred", ctx.config.batch_id,
            ctx.config.overnight_events_path,
            backlog_id=ctx.backlog_ids.get(name),
        )
        return True

    except Exception as exc:
        # Exception-safety guard (spec R3, load-bearing): if the resolved
        # review was could-not-run, the in-band preserve path was supposed to
        # keep the ff-merge — an exception thrown anywhere in that path must
        # NOT fall through here and `git reset --hard` away the very ff-merge it
        # preserved. Skip the reset + tag could_not_run in that case. When
        # ``rr is None`` the dispatch itself crashed before resolving, so the
        # reset correctly still fires (a genuine crash).
        preserved = rr is not None and rr.could_not_run
        if preserved:
            merge_reverted = False
        else:
            # Fail-safe rollback on a genuine review-dispatch crash.
            merge_reverted = _reset_ff_merge(repo, pre_ff_base_sha)
        crash_details: dict = {
            "error": f"dispatch_review raised {type(exc).__name__}: {exc}",
            "merge_reverted": merge_reverted,
            "path": "repair_completed",
        }
        if preserved:
            crash_details["could_not_run"] = True
        else:
            crash_details["review_dispatch_crashed"] = True
        overnight_log_event(
            FEATURE_DEFERRED,
            ctx.config.batch_id,
            feature=name,
            details=crash_details,
            log_path=ctx.config.overnight_events_path,
        )
        if preserved:
            crash_context_clause = (
                "review could not run (agent completed, no usable verdict) — "
                "the ff-merge is PRESERVED on the integration branch for human "
                "re-review; do NOT re-run."
            )
        elif merge_reverted:
            crash_context_clause = "The ff-merge was rolled back — safe to re-review/re-run."
        else:
            crash_context_clause = (
                "The ff-merge could NOT be rolled back — manual rollback needed."
            )
        deferral = DeferralQuestion(
            feature=name,
            question_id=0,
            severity=SEVERITY_BLOCKING,
            context=(
                f"Feature '{name}' was ff-merged after conflict repair but the "
                f"post-merge review dispatch crashed: {type(exc).__name__}: {exc}. "
                + crash_context_clause
            ),
            question=(
                f"Feature '{name}' was ff-merged after repair but the review "
                "dispatch crashed. Should it be marked complete (skipping "
                "review) or held for manual review?"
            ),
            options_considered=["mark complete (skip review)", "hold for manual review"],
            pipeline_attempted="dispatch_review() in _repair_completed_review_gate()",
        )
        write_deferral(deferral, deferred_dir=deferred_dir, idempotent=True)
        ctx.batch_result.features_deferred.append({
            "name": name,
            "question_count": 1,
        })
        # R7/R11: a raised dispatch exception on the repair_completed path is a
        # genuine review-dispatch crash — feed it into the systemic circuit
        # breaker tagged REVIEW_DISPATCH_CRASH (the helper's default).
        _record_review_crash_systemic(name, ctx, REVIEW_DISPATCH_CRASH)
        _write_back_to_backlog(
            name, "deferred", ctx.config.batch_id,
            ctx.config.overnight_events_path,
            backlog_id=ctx.backlog_ids.get(name),
        )
        return True


def _reset_ff_merge(repo: Path | None, pre_ff_base_sha: Optional[str]) -> bool:
    """Roll a ``repair_completed`` ff-merge back to its pre-ff base tip.

    A fast-forward leaves no merge commit, so the rollback is a ``git reset
    --hard <pre_ff_base_sha>`` rather than ``git revert -m 1``. Runs under the
    caller's held ``ctx.lock``. Returns True when the reset succeeded (the
    unreviewed repair work is no longer on the integration branch), False when
    the pre-ff SHA was unavailable or the reset failed (the merge genuinely
    remains — surfaced as a manual-rollback deferral).
    """
    if not pre_ff_base_sha:
        return False
    reset_result = subprocess.run(
        ["git", "reset", "--hard", pre_ff_base_sha],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    return reset_result.returncode == 0


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
    completed features), and if test recovery is needed the lock is released
    between the two blocks but RE-ACQUIRED to cover the recovery re-merge
    itself — the ``recover_test_failure()`` call, the R2 recovery-SHA capture,
    the R10 review, and the R3 revert all run under that re-acquired lock,
    because the recovery merge mutates the one shared physical integration
    checkout and an unlocked merge would race sibling features' in-lock
    checkout/merge/revert and corrupt the index.

    Callers must NOT hold ``ctx.lock`` when invoking this function.
    """
    need_recovery = False
    actual_branch: str | None = None
    merge_result = None
    repo_path = ctx.repo_path_map.get(name)
    worktree_path = ctx.worktree_paths.get(name)

    async with ctx.lock:
        if result.status == "repair_completed":
            # R12: the repair_completed ff-merge is a LIVE merge-to-`merged`
            # write site that can carry a review-qualifying feature (a
            # conflict-resolved complex/high feature). Route it through the
            # async review-or-revert gate here — the async layer owns review
            # dispatch — so the sync _apply_feature_result never reaches its
            # repair_completed merge-success arm for a review-qualifying
            # feature (that arm now carries a runtime guard).
            await _repair_completed_review_gate(
                name, result, ctx, deferred_dir=deferred_dir,
            )
            if result.repair_agent_used:
                ctx.recovery_attempts_map[name] = ctx.recovery_attempts_map.get(name, 0) + 1
            return
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
        merge_target = _merge_target_repo_path(ctx, name)
        if ctx.repo_path_map.get(name) is None and merge_target is None:
            # Home feature whose integration worktree could not be resolved
            # (degraded path: TMPDIR wiped / resumed session). Pause and surface
            # rather than passing repo_path=None onward and falling back to the
            # home working tree, which would re-create the worktree collision.
            error = "integration worktree unresolved"
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
            return
        merge_result = merge_feature(
            feature=name,
            base_branch=effective_branch,
            test_command=ctx.config.test_command,
            log_path=ctx.config.pipeline_events_path,
            branch=actual_branch,
            repo_path=merge_target,
        )

        if merge_result.success:
            overnight_log_event(
                FEATURE_MERGED,
                ctx.config.batch_id,
                feature=name,
                details={"integration_branch": effective_branch},
                log_path=ctx.config.overnight_events_path,
            )
            # Review gating: check if post-merge review is required. Corrupted
            # state ORs in via _review_required → fail safe toward review (R8a).
            tier = read_tier(name)
            criticality = read_criticality(name)
            if _review_required(name):
                # Bind ``rr`` before the try so the crash-``except`` below can
                # tell a resolved could-not-run review (preserve the merge) from
                # a raised dispatch crash (revert): an exception thrown anywhere
                # in the in-band preserve path after a could-not-run verdict
                # resolved must NOT fall into the ``except`` and revert-as-crash
                # the very merge it was preserving (spec R3 exception-safety).
                # When ``rr is None`` the dispatch itself crashed before
                # resolving, so the except's revert correctly still fires.
                rr = None
                try:
                    rr = await dispatch_review(
                        feature=name,
                        worktree_path=ctx.worktree_paths.get(name, Path(f"worktrees/{name}")),
                        branch=actual_branch or f"pipeline/{name}",
                        spec_path=Path(f"cortex/lifecycle/{name}/spec.md"),
                        complexity=tier,
                        criticality=criticality,
                        base_branch=_effective_base_branch(
                            repo_path, ctx.integration_branches, ctx.config.base_branch,
                        ),
                        repo_path=merge_target,
                        log_path=ctx.config.pipeline_events_path,
                    )
                    if rr.deferred:
                        revert_aborted = False
                        # Track whether the live merge was actually reverted off
                        # the integration branch so the morning report can
                        # reconcile its surface: a successful revert means the
                        # feature is no longer on the branch ("safe to
                        # re-review"), whereas an aborted revert (the R-edge)
                        # leaves it merged ("do NOT re-run").
                        merge_reverted = False
                        if rr.could_not_run:
                            # Could-not-run preserve (spec R3): the review agent
                            # completed but produced no usable verdict — PRESERVE
                            # the already-merged, hook-passing feature rather
                            # than reverting it. The merge stays on the
                            # integration branch and is flagged for human
                            # re-review (rendered on the morning report + the
                            # integration PR by later tasks).
                            live_merge_sha = None
                        else:
                            # Fail-safe rollback: revert the feature's LIVE merge
                            # commit (SHA-anchored, under the held ctx.lock)
                            # before worktree cleanup so unreviewed code does not
                            # ship on the integration branch. Prefer the cycle-1
                            # re-merge SHA when present (it is the most recent
                            # merge of this feature), else the primary merge SHA.
                            live_merge_sha = (
                                getattr(rr, "merge_sha", None) or merge_result.merge_sha
                            )
                            if live_merge_sha is not None:
                                revert_outcome = revert_merge(
                                    live_merge_sha,
                                    repo_path=merge_target,
                                    log_path=ctx.config.pipeline_events_path,
                                    feature=name,
                                )
                                revert_aborted = revert_outcome.aborted
                                merge_reverted = revert_outcome.success
                        if revert_aborted:
                            # Dependent-conflict R-edge: the revert conflicted
                            # (a later feature merged code depending on this
                            # one), so `git revert --abort` ran and the merge
                            # genuinely REMAINS on the integration branch.
                            # Escalate a blocking deferral with the legacy
                            # "do NOT re-run" annotation (accurate in this
                            # one case). Name the dependent feature(s) Y — any
                            # other in-batch feature whose changed files overlap
                            # this one's — so triage can see what now references
                            # the code that would have been reverted.
                            dependents = _overlapping_features(
                                name, changed_files, ctx.batch_result.key_files_changed,
                            )
                            if dependents:
                                dependent_clause = (
                                    "Dependent feature(s) referencing the reverted code: "
                                    + ", ".join(f"'{d}'" for d in dependents) + ". "
                                )
                            else:
                                dependent_clause = "A later feature likely depends on it. "
                            conflict_deferral = DeferralQuestion(
                                feature=name,
                                question_id=_next_escalation_n(
                                    name, ctx.config.batch_id, ctx.config.session_dir,
                                ),
                                severity=SEVERITY_BLOCKING,
                                context=(
                                    f"Review deferred (verdict {rr.verdict!r}); the rollback "
                                    f"of merge {live_merge_sha} conflicted and was aborted. The "
                                    "merge is still on the integration branch — do NOT re-run; "
                                    f"manual rollback needed. {dependent_clause}"
                                ),
                                question=(
                                    f"Feature '{name}' was deferred at review but its merge could "
                                    "not be reverted (revert conflict — a later feature depends "
                                    f"on it). {dependent_clause}How should this be manually rolled back?"
                                ),
                                options_considered=["manual revert + re-review", "keep merged and re-review in place"],
                                pipeline_attempted="revert_merge() in apply_feature_result() (deferred path)",
                            )
                            write_deferral(conflict_deferral, deferred_dir=deferred_dir)
                        ctx.batch_result.features_deferred.append({
                            "name": name,
                            "question_count": 1,
                        })
                        # Distinguish a could-not-run review (verdict STRING
                        # "ERROR" — the crash/error path) from a review that ran
                        # and said no (REJECTED / CHANGES_REQUESTED), so morning
                        # triage can separate an infra crash from substantive
                        # review feedback (R9). Detection keys off the verdict
                        # string, never `cycle` (the cycle:0 value is cosmetic).
                        deferred_details: dict = {
                            "review_verdict": rr.verdict,
                            "review_cycle": rr.cycle,
                            # Reconciliation signal for the morning report: when
                            # the merge was successfully reverted the surface
                            # must NOT carry the "still on the integration
                            # branch — do NOT re-run" annotation (it is false
                            # post-revert); that annotation is reserved for the
                            # R-edge where the revert aborted and the merge
                            # genuinely remains.
                            "merge_reverted": merge_reverted,
                        }
                        if rr.verdict == "ERROR":
                            _set_review_error_detail_flags(
                                deferred_details, merge_reverted=merge_reverted
                            )
                        overnight_log_event(
                            FEATURE_DEFERRED,
                            ctx.config.batch_id,
                            feature=name,
                            details=deferred_details,
                            log_path=ctx.config.overnight_events_path,
                        )
                        # R7/R11: a could-not-run review (verdict ERROR, agent
                        # completed) is a no-artifact systemic review failure —
                        # feed it into the systemic circuit breaker tagged
                        # REVIEW_NO_ARTIFACT so SYSTEMIC_FAILURE_THRESHOLD
                        # no-artifact reviews in a batch trip it coherently
                        # (distinct from a genuine dispatch crash, tagged in the
                        # except block below). A review that ran and said no
                        # (REJECTED / CHANGES_REQUESTED) is substantive feedback,
                        # not a failure, and is excluded.
                        if rr.verdict == "ERROR":
                            _record_review_crash_systemic(name, ctx, REVIEW_NO_ARTIFACT)
                        # Use the valid OvernightState status `deferred` (R8) —
                        # `in_progress` is not a valid status and reads as
                        # ordinary active work.
                        _write_back_to_backlog(
                            name, "deferred", ctx.config.batch_id,
                            ctx.config.overnight_events_path,
                            backlog_id=ctx.backlog_ids.get(name),
                        )
                        try:
                            cleanup_worktree(name, branch=f"pipeline/{name}", repo_path=repo_path, worktree_path=worktree_path)
                        except Exception:
                            pass
                        return
                except Exception as exc:
                    # Exception-safety guard (spec R3, load-bearing): if the
                    # resolved review was could-not-run, the in-band preserve
                    # path was supposed to keep the already-merged feature — an
                    # exception thrown anywhere in that path (the flag-helper,
                    # _record_review_crash_systemic, the backlog write-back,
                    # overnight_log_event, cleanup_worktree) must NOT fall
                    # through here and revert-as-crash the very merge it
                    # preserved. Skip the revert + tag could_not_run in that
                    # case. When ``rr is None`` the dispatch itself crashed
                    # before resolving, so the revert correctly still fires
                    # (a genuine crash).
                    preserved = rr is not None and rr.could_not_run
                    if not preserved:
                        # Fail-safe rollback on a genuine review-dispatch crash:
                        # revert the feature's LIVE merge commit (SHA-anchored,
                        # under the held ctx.lock) before surfacing the deferral,
                        # so a crashed review never leaves unreviewed code on the
                        # integration branch.
                        live_merge_sha = merge_result.merge_sha
                        if live_merge_sha is not None:
                            revert_merge(
                                live_merge_sha,
                                repo_path=merge_target,
                                log_path=ctx.config.pipeline_events_path,
                                feature=name,
                            )
                    crash_details: dict = {
                        "error": f"dispatch_review raised {type(exc).__name__}: {exc}",
                    }
                    if preserved:
                        crash_details["could_not_run"] = True
                        crash_details["merge_reverted"] = False
                    else:
                        crash_details["review_dispatch_crashed"] = True
                    overnight_log_event(
                        FEATURE_DEFERRED,
                        ctx.config.batch_id,
                        feature=name,
                        details=crash_details,
                        log_path=ctx.config.overnight_events_path,
                    )
                    # Single reconciled question-id source: question_id=0 lets
                    # write_deferral's deferred-dir scan assign the ID (the same
                    # source as the review-defer path), instead of the
                    # escalations.jsonl counter (_next_escalation_n) used
                    # elsewhere. idempotent=True makes the write resume-safe:
                    # if this feature was already deferred (e.g. the review-defer
                    # path ran before the crash, or on session resume), no
                    # duplicate -q00N.md is minted.
                    deferral = DeferralQuestion(
                        feature=name,
                        question_id=0,
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
                    write_deferral(deferral, deferred_dir=deferred_dir, idempotent=True)
                    ctx.batch_result.features_deferred.append({
                        "name": name,
                        "question_count": 1,
                    })
                    # R7/R11: a raised dispatch exception is a genuine
                    # review-dispatch crash — feed it into the systemic circuit
                    # breaker tagged REVIEW_DISPATCH_CRASH (the helper's default).
                    _record_review_crash_systemic(name, ctx, REVIEW_DISPATCH_CRASH)
                    # Mirror the review-deferred path (R8): a crashed review
                    # defers the feature (FEATURE_DEFERRED emitted, blocking
                    # deferral written, feature in features_deferred), so the
                    # backlog status is `deferred` — not `in_progress`, which
                    # reads as ordinary active work despite the deferral.
                    _write_back_to_backlog(
                        name, "deferred", ctx.config.batch_id,
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
                cleanup_worktree(name, branch=f"pipeline/{name}", repo_path=repo_path, worktree_path=worktree_path)
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

            deferral = DeferralQuestion(
                feature=name,
                question_id=_next_escalation_n(
                    name, ctx.config.batch_id, ctx.config.session_dir,
                ),
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
        merge_target = _merge_target_repo_path(ctx, name)
        if ctx.repo_path_map.get(name) is None and merge_target is None:
            # Home feature whose integration worktree could not be resolved
            # (degraded path: TMPDIR wiped / resumed session). Pause and surface
            # rather than passing repo_path=None onward to the recovery precheck
            # (cwd=None falls back to the home working tree).
            error = "integration worktree unresolved"
            async with ctx.lock:
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
            return
        # Re-acquire the lock to cover the recovery re-merge ITSELF (the
        # `git checkout` + `git merge --no-ff` inside recover_test_failure that
        # mutates the one shared physical integration checkout), the R2
        # recovery-SHA capture, the R10 review, AND the R3 revert. Holding the
        # lock across the merge — not only the post-merge steps — prevents a
        # sibling feature's in-lock checkout/merge/revert from racing this
        # recovery merge and corrupting the shared index (spec Technical
        # Constraints).
        async with ctx.lock:
            recovery_result = await recover_test_failure(
                feature=name,
                base_branch=ctx.config.base_branch,
                test_output=(
                    merge_result.test_result.output
                    if merge_result and merge_result.test_result else ""
                ),
                branch=actual_branch or f"pipeline/{name}",
                worktree_path=ctx.worktree_paths.get(name),
                learnings_dir=Path(f"cortex/lifecycle/{name}/learnings"),
                test_command=ctx.config.test_command,
                pipeline_log_path=ctx.config.pipeline_events_path,
                repo_path=merge_target,
            )

            if recovery_result.success and recovery_result.flaky:
                overnight_log_event(
                    MERGE_RECOVERY_FLAKY,
                    ctx.config.batch_id,
                    feature=name,
                    details={"attempts": recovery_result.attempts},
                    log_path=ctx.config.overnight_events_path,
                )
                # R10: route a review-qualifying feature through review before
                # marking merged; defer (revert + surface) on a non-APPROVED or
                # crashed review. The re-merge, this review, and any revert all
                # run under the lock re-acquired above.
                deferred = await _recovery_review_gate(
                    name,
                    ctx,
                    recovery_merge_sha=recovery_result.merge_sha,
                    actual_branch=actual_branch,
                    repo_path=repo_path,
                    merge_target=merge_target,
                    deferred_dir=deferred_dir,
                )
                if deferred:
                    try:
                        cleanup_worktree(name, branch=f"pipeline/{name}", repo_path=repo_path, worktree_path=worktree_path)
                    except Exception:
                        pass
                    return
                ctx.batch_result.features_merged.append(name)
                ctx.cb_state.consecutive_pauses = 0
                _write_back_to_backlog(
                    name, "merged", ctx.config.batch_id,
                    ctx.config.overnight_events_path,
                    backlog_id=ctx.backlog_ids.get(name),
                )
                try:
                    cleanup_worktree(name, branch=f"pipeline/{name}", repo_path=repo_path, worktree_path=worktree_path)
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
                # R10: route a review-qualifying feature through review before
                # marking merged; defer (revert + surface) on a non-APPROVED or
                # crashed review. The re-merge, this review, and any revert all
                # run under the lock re-acquired above.
                deferred = await _recovery_review_gate(
                    name,
                    ctx,
                    recovery_merge_sha=recovery_result.merge_sha,
                    actual_branch=actual_branch,
                    repo_path=repo_path,
                    merge_target=merge_target,
                    deferred_dir=deferred_dir,
                )
                if deferred:
                    try:
                        cleanup_worktree(name, branch=f"pipeline/{name}", repo_path=repo_path, worktree_path=worktree_path)
                    except Exception:
                        pass
                    return
                ctx.batch_result.features_merged.append(name)
                ctx.cb_state.consecutive_pauses = 0
                _write_back_to_backlog(
                    name, "merged", ctx.config.batch_id,
                    ctx.config.overnight_events_path,
                    backlog_id=ctx.backlog_ids.get(name),
                )
                try:
                    cleanup_worktree(name, branch=f"pipeline/{name}", repo_path=repo_path, worktree_path=worktree_path)
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
                if f"merge recovery failed: {error}" in _SYSTEMIC_ERROR_TYPES:
                    ctx.cb_state.systemic_pauses_in_batch += 1
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
                if (
                    ctx.cb_state.systemic_pauses_in_batch >= SYSTEMIC_FAILURE_THRESHOLD
                    and not ctx.batch_result.global_abort_signal
                ):
                    trailing = ctx.batch_result.features_paused[-SYSTEMIC_FAILURE_THRESHOLD:]
                    cause_class = [
                        entry["error"] for entry in trailing
                        if entry["error"] in _SYSTEMIC_ERROR_TYPES
                    ]
                    overnight_log_event(
                        PIPELINE_SYSTEMIC_FAILURE,
                        ctx.config.batch_id,
                        feature=name,
                        details={"cause_class": cause_class, "threshold": SYSTEMIC_FAILURE_THRESHOLD},
                        log_path=ctx.config.overnight_events_path,
                    )
                    ctx.batch_result.global_abort_signal = True
