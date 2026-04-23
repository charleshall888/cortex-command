"""Session orchestration module for overnight batch execution.

Manages a batch of features through the overnight lifecycle: parses
per-feature plans, dispatches tasks via the pipeline's dispatch/retry
infrastructure, handles deferrals, enforces a batch circuit breaker,
and auto-merges completed features to main.

This module contains the session-layer logic extracted from
``batch_runner.py``.  ``batch_runner.py`` is a thin CLI wrapper that
imports from this module.  ``orchestrator.py`` must not import from
``claude.overnight.batch_runner``.
"""

from __future__ import annotations

import asyncio
import logging
import os
from asyncio import create_task
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from cortex_command.pipeline.parser import parse_master_plan
from cortex_command.pipeline.state import log_event as pipeline_log_event
from cortex_command.pipeline.worktree import create_worktree

from cortex_command.overnight.throttle import (
    ConcurrencyManager,
    load_throttle_config,
)
from cortex_command.overnight.state import (
    load_state,
    save_batch_result,
    save_state,
    transition,
    OvernightFeatureStatus,
)
from cortex_command.overnight.events import (
    BATCH_ASSIGNED,
    BATCH_BUDGET_EXHAUSTED,
    BATCH_COMPLETE,
    FEATURE_START,
    HEARTBEAT,
    SESSION_BUDGET_EXHAUSTED,
    log_event as overnight_log_event,
)
from cortex_command.overnight.types import CircuitBreakerState, FeatureResult
from cortex_command.overnight.feature_executor import execute_feature
from cortex_command.overnight import outcome_router
from cortex_command.overnight.outcome_router import OutcomeContext

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
        if overnight_state.worktree_path:
            outcome_router.set_backlog_dir(Path(overnight_state.worktree_path) / "backlog")
        for name in feature_names:
            fs = overnight_state.features.get(name, OvernightFeatureStatus())
            spec_paths[name] = fs.spec_path if fs else None
            backlog_ids[name] = fs.backlog_id if fs else None
            recovery_attempts_map[name] = fs.recovery_attempts
            repo_path_map[name] = Path(fs.repo_path).expanduser() if fs.repo_path else None
    except Exception as exc:
        try:
            pipeline_log_event(
                config.pipeline_events_path,
                {
                    "event": "state_load_failed",
                    "exception_type": type(exc).__name__,
                    "exception_message": str(exc),
                    "state_path": str(config.overnight_state_path),
                    "subsequent_writes_target": str(
                        outcome_router._PROJECT_ROOT / "backlog"
                    ),
                },
            )
        except Exception:
            pass
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
    cb_state = CircuitBreakerState()

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
                cb_state=cb_state,
                repo_path=repo_path_map.get(name),
                integration_branches=integration_branches,
            )
        finally:
            manager.release()

        # Inline budget exhaustion check (replaces the old
        # ``_accumulate_result`` helper).  If the feature result reports a
        # budget-exhausted pause, write state, emit the batch-level event,
        # set the global abort signal, and return without calling the
        # outcome router.
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

        ctx = OutcomeContext(
            batch_result=batch_result,
            lock=lock,
            cb_state=cb_state,
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

    heartbeat_task = create_task(_heartbeat_loop())

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
            # Inline the same budget-exhaustion guard + outcome-router
            # delegation used in ``_run_one`` so that late exceptions still
            # reach the outcome router.
            if (
                failed_result.status == "paused"
                and failed_result.error == "budget_exhausted"
                and not batch_result.global_abort_signal
            ):
                batch_result.global_abort_signal = True
                batch_result.abort_reason = "budget_exhausted"
                overnight_log_event(
                    BATCH_BUDGET_EXHAUSTED,
                    config.batch_id,
                    feature=n,
                    details={"abort_reason": "budget_exhausted"},
                    log_path=config.overnight_events_path,
                )
                continue
            ctx = OutcomeContext(
                batch_result=batch_result,
                lock=lock,
                cb_state=cb_state,
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
            await outcome_router.apply_feature_result(n, failed_result, ctx)

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
