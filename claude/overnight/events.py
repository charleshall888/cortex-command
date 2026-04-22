"""Append-only JSONL event logger for overnight orchestration sessions.

Provides forensic logging of all significant events during an overnight
session. Each event is written as a single JSON line to a per-session
log file at lifecycle/overnight-events-{session_id}.log. The canonical
path lifecycle/overnight-events.log is a symlink maintained by runner.sh.
Timestamps are auto-generated in UTC ISO 8601 format.

Includes reader utilities (read_events, read_events_for_round) used by
the morning report generator and resume logic.

Follows the pattern established by claude/pipeline/state.py:log_event()
and claude/pipeline/metrics.py:parse_events().
"""

from __future__ import annotations

import json
import os
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_LIFECYCLE_ROOT = Path(__file__).resolve().parents[2] / "lifecycle"


# ---------------------------------------------------------------------------
# Event type constants
# ---------------------------------------------------------------------------

SESSION_START = "session_start"
ROUND_START = "round_start"
BATCH_ASSIGNED = "batch_assigned"
FEATURE_START = "feature_start"
FEATURE_COMPLETE = "feature_complete"
FEATURE_PAUSED = "feature_paused"
FEATURE_FAILED = "feature_failed"
FEATURE_DEFERRED = "feature_deferred"
ROUND_COMPLETE = "round_complete"
ROUND_SETUP_START = "round_setup_start"
ROUND_SETUP_COMPLETE = "round_setup_complete"
BATCH_COMPLETE = "batch_complete"
CIRCUIT_BREAKER = "circuit_breaker"
SESSION_COMPLETE = "session_complete"
HEARTBEAT = "heartbeat"
STALL_TIMEOUT = "stall_timeout"
ORCHESTRATOR_FAILED = "orchestrator_failed"
INTERRUPTED = "interrupted"
BACKLOG_WRITE_FAILED = "backlog_write_failed"
BRAIN_DECISION = "brain_decision"
BRAIN_UNAVAILABLE = "brain_unavailable"
WORKER_NO_EXIT_REPORT = "worker_no_exit_report"
WORKER_MALFORMED_EXIT_REPORT = "worker_malformed_exit_report"
MERGE_RECOVERY_START = "merge_recovery_start"
MERGE_RECOVERY_FLAKY = "merge_recovery_flaky"
MERGE_RECOVERY_SUCCESS = "merge_recovery_success"
MERGE_RECOVERY_FAILED = "merge_recovery_failed"
MERGE_CONFLICT_CLASSIFIED = "merge_conflict_classified"
REPAIR_AGENT_START = "repair_agent_start"
REPAIR_AGENT_COMPLETE = "repair_agent_complete"
REPAIR_AGENT_ESCALATED = "repair_agent_escalated"
REPAIR_AGENT_FAILED = "repair_agent_failed"
REPAIR_AGENT_RESOLVED = "repair_agent_resolved"
TRIVIAL_CONFLICT_RESOLVED = "trivial_conflict_resolved"
INTEGRATION_RECOVERY_START = "integration_recovery_start"
INTEGRATION_RECOVERY_SUCCESS = "integration_recovery_success"
INTEGRATION_RECOVERY_FAILED = "integration_recovery_failed"
BATCH_BUDGET_EXHAUSTED = "batch_budget_exhausted"
SESSION_BUDGET_EXHAUSTED = "session_budget_exhausted"
INTEGRATION_WORKTREE_MISSING = "integration_worktree_missing"
ORCHESTRATOR_NO_PLAN = "orchestrator_no_plan"
BATCH_RUNNER_STALLED = "batch_runner_stalled"
ARTIFACT_COMMIT_FAILED = "artifact_commit_failed"
PUSH_FAILED = "push_failed"
MORNING_REPORT_COMMIT_FAILED = "morning_report_commit_failed"
MORNING_REPORT_GENERATE_RESULT = "morning_report_generate_result"
MORNING_REPORT_COMMIT_RESULT = "morning_report_commit_result"
PLAN_GEN_DISPATCHED = "plan_gen_dispatched"
FEATURE_MERGED = "feature_merged"
FOLLOWUP_COMMIT_SKIPPED = "followup_commit_skipped"

EVENT_TYPES = (
    SESSION_START,
    ROUND_START,
    BATCH_ASSIGNED,
    FEATURE_START,
    FEATURE_COMPLETE,
    FEATURE_PAUSED,
    FEATURE_FAILED,
    FEATURE_DEFERRED,
    ROUND_COMPLETE,
    ROUND_SETUP_START,
    ROUND_SETUP_COMPLETE,
    BATCH_COMPLETE,
    CIRCUIT_BREAKER,
    SESSION_COMPLETE,
    HEARTBEAT,
    STALL_TIMEOUT,
    ORCHESTRATOR_FAILED,
    INTERRUPTED,
    BACKLOG_WRITE_FAILED,
    BRAIN_DECISION,
    BRAIN_UNAVAILABLE,
    WORKER_NO_EXIT_REPORT,
    WORKER_MALFORMED_EXIT_REPORT,
    MERGE_RECOVERY_START,
    MERGE_RECOVERY_FLAKY,
    MERGE_RECOVERY_SUCCESS,
    MERGE_RECOVERY_FAILED,
    MERGE_CONFLICT_CLASSIFIED,
    REPAIR_AGENT_START,
    REPAIR_AGENT_COMPLETE,
    REPAIR_AGENT_ESCALATED,
    REPAIR_AGENT_FAILED,
    REPAIR_AGENT_RESOLVED,
    TRIVIAL_CONFLICT_RESOLVED,
    INTEGRATION_RECOVERY_START,
    INTEGRATION_RECOVERY_SUCCESS,
    INTEGRATION_RECOVERY_FAILED,
    BATCH_BUDGET_EXHAUSTED,
    SESSION_BUDGET_EXHAUSTED,
    INTEGRATION_WORKTREE_MISSING,
    ORCHESTRATOR_NO_PLAN,
    BATCH_RUNNER_STALLED,
    ARTIFACT_COMMIT_FAILED,
    PUSH_FAILED,
    MORNING_REPORT_COMMIT_FAILED,
    MORNING_REPORT_GENERATE_RESULT,
    MORNING_REPORT_COMMIT_RESULT,
    PLAN_GEN_DISPATCHED,
    FEATURE_MERGED,
    FOLLOWUP_COMMIT_SKIPPED,
)


# ---------------------------------------------------------------------------
# Default log path
# ---------------------------------------------------------------------------

DEFAULT_LOG_PATH = _LIFECYCLE_ROOT / "overnight-events.log"


def events_log_path(
    session_id: str,
    lifecycle_root: Path = _LIFECYCLE_ROOT,
) -> Path:
    """Return the per-session events log path for the given session ID.

    The canonical path (DEFAULT_LOG_PATH) is a symlink maintained by
    runner.sh; this function returns the real per-session file.

    Args:
        session_id: Session ID from OvernightState (e.g. overnight-2025-01-15-2200).
        lifecycle_root: Root lifecycle directory (defaults to the home repo's lifecycle/).

    Returns:
        Path to lifecycle/overnight-events-{session_id}.log.
    """
    return lifecycle_root / f"overnight-events-{session_id}.log"


# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def log_event(
    event: str,
    round: int,
    feature: Optional[str] = None,
    details: Optional[dict] = None,
    log_path: Path = DEFAULT_LOG_PATH,
) -> None:
    """Append a JSONL event line to the overnight events log.

    Automatically adds a "ts" field with the current UTC time in ISO 8601
    format. The timestamp is placed first in the output for readability.

    Args:
        event: Event type string (should be one of the EVENT_TYPES constants).
        round: Round number (1-based) this event is associated with.
        feature: Feature ID, if the event is feature-specific (optional).
        details: Additional event data as a dict (optional).
        log_path: Path to the events log file (created if missing).

    Raises:
        ValueError: If event is not a recognized event type.
    """
    if event not in EVENT_TYPES:
        raise ValueError(
            f"Unknown event type {event!r}; must be one of {EVENT_TYPES}"
        )

    log_path.parent.mkdir(parents=True, exist_ok=True)

    session_id = os.environ.get("LIFECYCLE_SESSION_ID", "manual")

    entry: dict = {
        "v": 1,
        "ts": _now_iso(),
        "event": event,
        "session_id": session_id,
        "round": round,
    }

    if feature is not None:
        entry["feature"] = feature

    if details is not None:
        entry["details"] = details

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


# ---------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------

def read_events(log_path: Path = DEFAULT_LOG_PATH) -> list[dict[str, Any]]:
    """Read the JSONL events log and return parsed event dicts.

    Follows the pattern from ``claude/pipeline/metrics.py:parse_events()``:
    iterate lines, skip blank and malformed entries, return a list of dicts.

    Args:
        log_path: Path to the overnight events log file.

    Returns:
        List of event dicts. Returns an empty list if the file does not
        exist.
    """
    if not log_path.exists():
        return []

    events: list[dict[str, Any]] = []
    for lineno, line in enumerate(
        log_path.read_text(encoding="utf-8").splitlines(), 1
    ):
        line = line.strip()
        if not line:
            continue
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            warnings.warn(f"{log_path}:{lineno}: skipping malformed JSON line")
            continue
        if not isinstance(evt, dict) or "event" not in evt:
            warnings.warn(
                f"{log_path}:{lineno}: skipping line missing required fields"
            )
            continue
        # Normalize event names to lowercase for backward compat with
        # archived logs that used UPPERCASE event names.
        evt["event"] = evt.get("event", "").lower()
        events.append(evt)
    return events


def read_events_for_round(
    round_number: int,
    log_path: Path = DEFAULT_LOG_PATH,
) -> list[dict[str, Any]]:
    """Read events and return only those for a specific round.

    Args:
        round_number: The round number to filter on.
        log_path: Path to the overnight events log file.

    Returns:
        List of event dicts whose ``round`` field matches *round_number*.
        Returns an empty list if the file does not exist or no events
        match.
    """
    return [
        evt for evt in read_events(log_path)
        if evt.get("round") == round_number
    ]
