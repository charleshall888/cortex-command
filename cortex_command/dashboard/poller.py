"""In-memory cache and background polling loop for the dashboard.

Defines DashboardState (a dataclass holding all cached data and file offsets)
and run_polling (an async coroutine that starts three asyncio tasks running at
different intervals).

Polling intervals:
    _poll_state_files  -- every 2 seconds (overnight state, pipeline state, feature states)
    _poll_jsonl_events -- every 1 second  (overnight-events.log tail)
    _poll_slow         -- every 30 seconds (backlog counts)
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from cortex_command.dashboard.alerts import evaluate_alerts, fire_notifications
from cortex_command.dashboard.data import (
    _read_all_jsonl,
    compute_slow_flags,
    parse_backlog_counts,
    parse_backlog_titles,
    parse_feature_cost_delta,
    parse_feature_events,
    parse_feature_timestamps,
    parse_fleet_cards,
    parse_metrics,
    parse_overnight_state,
    parse_pipeline_dispatch,
    parse_pipeline_state,
    parse_round_timestamps,
    tail_jsonl,
)

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class DashboardState:
    """In-memory cache for all dashboard data.

    Fields:
        overnight: Parsed overnight-state.json dict, or None if absent.
        pipeline: Parsed pipeline-state.json dict, or None if absent.
        overnight_events: Accumulated events from overnight-events.log.
        overnight_events_offset: Byte offset for incremental JSONL tailing.
        feature_states: Per-feature parsed data keyed by feature slug.
            Each value is a dict from parse_feature_events with an
            additional ``plan_progress`` key — a ``(checked, total)``
            tuple sourced from the canonical detector when ``plan.md``
            exists, else ``None``.
        backlog_counts: Status -> count mapping from backlog/ directory.
        last_updated: ISO 8601 timestamp of the most recent successful poll.
    """

    overnight: dict | None = None
    pipeline: dict | None = None
    overnight_events: list = field(default_factory=list)
    overnight_events_offset: int = 0
    feature_states: dict = field(default_factory=dict)
    agent_activity_offsets: dict = field(default_factory=dict)
    agent_fleet: list = field(default_factory=list)
    alerts: dict = field(default_factory=dict)
    circuit_breaker_active: bool = False
    circuit_breaker_notified: bool = False
    backlog_counts: dict = field(default_factory=dict)
    backlog_titles: dict = field(default_factory=dict)
    feature_cost_totals: dict = field(default_factory=dict)
    feature_cost_offsets: dict = field(default_factory=dict)
    session_cost_total: float | None = None
    pipeline_dispatch: dict = field(default_factory=dict)
    metrics: dict | None = None
    slow_flags: dict = field(default_factory=dict)
    feature_timestamps: dict = field(default_factory=dict)
    round_timestamps: dict = field(default_factory=dict)
    worker_exit_issues: int = 0
    feature_display_order: list = field(default_factory=list)
    feature_models: dict = field(default_factory=dict)
    feature_complexities: dict = field(default_factory=dict)
    last_updated: str = ""
    _active_session_id: str = ""


def _resolve_session_path(root: Path) -> tuple[Path, Path]:
    """Return (overnight_state_path, events_log_path) for the active session.

    Reads ~/.local/share/overnight-sessions/active-session.json. If the
    pointer's phase is 'executing' and state_path is accessible, returns
    the pointer's paths. Otherwise falls back to the hardcoded
    latest-overnight paths.

    All exceptions are swallowed and the fallback is returned.
    """
    fallback_state = root / "cortex" / "lifecycle" / "sessions" / "latest-overnight" / "overnight-state.json"
    fallback_events = root / "cortex" / "lifecycle" / "sessions" / "latest-overnight" / "overnight-events.log"

    try:
        pointer_path = Path.home() / ".local" / "share" / "overnight-sessions" / "active-session.json"
        pointer = json.loads(pointer_path.read_text())
        if pointer.get("phase") == "executing":
            state_path = Path(pointer["state_path"])
            if state_path.exists():
                events_path = state_path.parent / "overnight-events.log"
                return state_path, events_path
    except Exception:  # noqa: BLE001
        pass

    return fallback_state, fallback_events


async def _poll_state_files(state: DashboardState, root: Path) -> None:
    """Poll overnight-state.json, pipeline-state.json, and per-feature files every 2 seconds.

    Retains the last-good value on error (i.e. does not overwrite a valid
    cached value with None on a transient read failure).
    """
    lifecycle_dir = root / "cortex" / "lifecycle"
    pipeline_path = lifecycle_dir / "sessions" / "latest-pipeline" / "pipeline-state.json"

    while True:
        try:
            overnight_path, _events_path = _resolve_session_path(root)

            # Detect session change and reset events offset if needed
            session_id = str(overnight_path.parent)
            if session_id != state._active_session_id:
                state._active_session_id = session_id
                state.overnight_events_offset = 0
                state.overnight_events = []

            overnight = parse_overnight_state(overnight_path)
            if overnight is not None:
                state.overnight = overnight

            pipeline = parse_pipeline_state(pipeline_path)
            # pipeline-state.json being absent is a normal "no active pipeline"
            # signal, so we always update (including to None).
            state.pipeline = pipeline

            # Update per-feature states from the feature slugs in overnight state.
            if state.overnight is not None:
                # Determine the lifecycle dir for per-feature data.
                # Overnight state may reference a different project via
                # project_root; fall back through integration_branches keys,
                # then to the local lifecycle_dir.
                project_lifecycle_dir = lifecycle_dir  # default fallback
                project_root = state.overnight.get("project_root")
                if project_root:
                    try:
                        pr_path = Path(project_root)
                        if pr_path.exists():
                            project_lifecycle_dir = pr_path / "cortex" / "lifecycle"
                    except OSError:
                        pass  # degrade gracefully to default
                if project_lifecycle_dir is lifecycle_dir and not project_root:
                    integration_branches = state.overnight.get(
                        "integration_branches", {}
                    )
                    if integration_branches:
                        first_key = next(iter(integration_branches))
                        candidate = Path(first_key) / "cortex" / "lifecycle"
                        if candidate.exists():
                            project_lifecycle_dir = candidate

                features_raw = state.overnight.get("features", {})
                for slug in features_raw:
                    fe = parse_feature_events(slug, project_lifecycle_dir)
                    # Preserve the prior contract: plan_progress is None
                    # when plan.md is absent, else (checked, total).
                    plan_md = project_lifecycle_dir / slug / "plan.md"
                    pp = (fe["checked"], fe["total"]) if plan_md.is_file() else None
                    state.feature_states[slug] = {
                        **fe,
                        "plan_progress": pp,
                    }

                fleet_cards, new_offsets = parse_fleet_cards(
                    state.overnight,
                    state.overnight_events,
                    state.feature_states,
                    project_lifecycle_dir,
                    state.agent_activity_offsets,
                )
                state.agent_fleet = fleet_cards
                state.agent_activity_offsets = new_offsets

                # Incremental cost tracking for each feature
                for slug in state.overnight.get("features", {}):
                    path = project_lifecycle_dir / slug / "agent-activity.jsonl"
                    delta, new_offset = parse_feature_cost_delta(
                        path, state.feature_cost_offsets.get(slug, 0)
                    )
                    if delta > 0 or slug not in state.feature_cost_totals:
                        state.feature_cost_totals[slug] = (
                            state.feature_cost_totals.get(slug, 0.0) + delta
                        )
                        state.feature_cost_offsets[slug] = new_offset

                # Recompute session cost total
                totals = state.feature_cost_totals
                state.session_cost_total = sum(totals.values()) if totals else None

                # Compute slow flags
                state.slow_flags = compute_slow_flags(
                    state.feature_states,
                    state.overnight,
                    state.metrics,
                    state.pipeline_dispatch,
                )

                # Build feature_models lookup with normalized keys
                normalize = lambda k: re.sub(r"^\d+-", "", k)
                state.feature_models = {
                    normalize(k): v["model"]
                    for k, v in state.pipeline_dispatch.items()
                }
                state.feature_complexities = {
                    normalize(k): v["complexity"]
                    for k, v in state.pipeline_dispatch.items()
                }

                state.feature_timestamps = parse_feature_timestamps(state.overnight_events)
                state.round_timestamps = parse_round_timestamps(state.overnight_events)
                state.worker_exit_issues = sum(
                    1
                    for e in state.overnight_events
                    if e.get("event") in ("worker_no_exit_report", "worker_malformed_exit_report")
                )

                # Build feature_display_order: slugs with a started_at sorted by
                # that timestamp (ISO string sort); slugs without go at the end in
                # original iteration order from features_raw.
                started = []
                unstarted = []
                for slug in features_raw:
                    ts = state.feature_timestamps.get(slug, {}).get("started_at")
                    if ts:
                        started.append((ts, slug))
                    else:
                        unstarted.append(slug)
                started.sort(key=lambda pair: pair[0])
                state.feature_display_order = [slug for _, slug in started] + unstarted

            state.last_updated = _now_iso()
        except Exception as exc:  # noqa: BLE001
            logger.warning("_poll_state_files error: %s", exc)

        await asyncio.sleep(2)


async def _poll_jsonl_events(state: DashboardState, root: Path) -> None:
    """Poll overnight-events.log for new JSONL events every 1 second.

    Uses byte-offset tracking so already-seen events are never re-emitted.
    """
    while True:
        try:
            _state_path, log_path = _resolve_session_path(root)
            if state.overnight_events_offset == 0:
                events, new_offset = _read_all_jsonl(log_path)
            else:
                events, new_offset = tail_jsonl(log_path, offset=state.overnight_events_offset)
            if events:
                state.overnight_events.extend(events)
            state.overnight_events_offset = new_offset
        except Exception as exc:  # noqa: BLE001
            logger.warning("_poll_jsonl_events error: %s", exc)

        await asyncio.sleep(1)


async def _poll_slow(state: DashboardState, root: Path) -> None:
    """Poll backlog counts every 30 seconds."""
    backlog_dir = root / "cortex" / "backlog"
    lifecycle_dir = root / "cortex" / "lifecycle"

    while True:
        try:
            counts = parse_backlog_counts(backlog_dir)
            state.backlog_counts = counts
            state.backlog_titles = parse_backlog_titles(backlog_dir)

            state.pipeline_dispatch = parse_pipeline_dispatch(lifecycle_dir)

            metrics = parse_metrics(lifecycle_dir)
            if metrics is not None:
                state.metrics = metrics
        except Exception as exc:  # noqa: BLE001
            logger.warning("_poll_slow error: %s", exc)

        await asyncio.sleep(30)


async def _poll_alerts(state: DashboardState, root: Path) -> None:
    """Evaluate alert conditions and fire notifications every 5 seconds."""
    lifecycle_dir = root / "cortex" / "lifecycle"

    while True:
        try:
            evaluate_alerts(state, root, lifecycle_dir)
            await fire_notifications(state, root)
        except Exception as exc:  # noqa: BLE001
            logger.warning("_poll_alerts error: %s", exc)

        await asyncio.sleep(5)


async def run_polling(state: DashboardState, root: Path) -> None:
    """Start the four background polling tasks.

    Creates four asyncio tasks:
        1. _poll_state_files  — every 2 seconds
        2. _poll_jsonl_events — every 1 second
        3. _poll_slow         — every 30 seconds
        4. _poll_alerts       — every 5 seconds

    Args:
        state: Shared DashboardState instance that all tasks update in place.
        root: Project root path (the directory containing lifecycle/ and backlog/).
    """
    asyncio.create_task(_poll_state_files(state, root))
    asyncio.create_task(_poll_jsonl_events(state, root))
    asyncio.create_task(_poll_slow(state, root))
    asyncio.create_task(_poll_alerts(state, root))
