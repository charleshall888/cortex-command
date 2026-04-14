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
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from claude.common import (
    compute_dependency_batches,
    mark_task_done_in_plan,
)
from claude.pipeline.dispatch import dispatch_task
from claude.pipeline.parser import FeatureTask, parse_feature_plan, parse_master_plan
from claude.pipeline.retry import RetryResult, retry_task
from claude.pipeline.state import log_event as pipeline_log_event
from claude.pipeline.worktree import WorktreeInfo, create_worktree

from claude.overnight.brain import (
    BrainAction,
    BrainContext,
    request_brain_decision,
)
from claude.overnight.deferral import (
    EscalationEntry,
    write_escalation,
)
from claude.overnight.throttle import (
    ConcurrencyManager,
    load_throttle_config,
)
from claude.overnight.state import load_state, save_batch_result, save_state, transition, OvernightFeatureStatus, _normalize_repo_key
from claude.overnight.events import (
    BATCH_ASSIGNED,
    BATCH_BUDGET_EXHAUSTED,
    BRAIN_DECISION,
    FEATURE_START,
    HEARTBEAT,
    BATCH_COMPLETE,
    WORKER_MALFORMED_EXIT_REPORT,
    WORKER_NO_EXIT_REPORT,
    SESSION_BUDGET_EXHAUSTED,
    log_event as overnight_log_event,
    read_events,
)
from claude.overnight.types import FeatureResult
from claude.overnight.constants import CIRCUIT_BREAKER_THRESHOLD
from claude.overnight.feature_executor import execute_feature
from claude.overnight import outcome_router
from claude.overnight.outcome_router import OutcomeContext

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
            outcome_router.set_backlog_dir(Path(next(iter(integration_branches))) / "backlog")
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
        """Accumulate a feature result into batch_result.

        Thin shim around ``outcome_router.apply_feature_result``.  Detects
        ``budget_exhausted`` paused results early (before the lock) so the
        global abort signal is set even when the outcome router is not the
        one marking it, then constructs ``OutcomeContext`` and delegates.
        """
        # Detect budget_exhausted and set global abort signal (lifted from
        # the pre-extraction _accumulate_result; runs outside the lock
        # because outcome_router.apply_feature_result owns the lock).
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

        ctx = OutcomeContext(
            batch_result=batch_result,
            lock=lock,
            consecutive_pauses_ref=consecutive_pauses_ref,
            recovery_attempts_map=recovery_attempts_map,
            worktree_paths=worktree_paths,
            worktree_branches=worktree_branches,
            repo_path_map=repo_path_map,
            integration_worktrees=integration_worktrees,
            integration_branches=integration_branches,
            session_id=session_id,
            backlog_ids=backlog_ids,
            feature_names=feature_names,
            config=config,
        )
        await outcome_router.apply_feature_result(name, result, ctx)

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
