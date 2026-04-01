"""Pipeline state machine with persistence and event logging.

Manages pipeline phase transitions, per-feature status tracking, and
JSONL event logging. State is persisted to lifecycle/pipeline-state.json
and read by shell scripts (hooks, statusline), so writes must be atomic.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# Valid pipeline phases
PHASES = ("planning", "executing", "merging", "integration-review", "complete", "paused")

# Valid forward transitions (source -> set of allowed targets)
_FORWARD_TRANSITIONS: dict[str, set[str]] = {
    "planning": {"executing"},
    "executing": {"merging"},
    "merging": {"integration-review"},
    "integration-review": {"complete"},
}

# Valid feature statuses
FEATURE_STATUSES = (
    "pending", "executing", "reviewing", "merging", "merged", "paused", "failed",
)


def _now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class FeatureStatus:
    """Tracks the status of a single feature within the pipeline."""

    status: str = "pending"
    retries: int = 0
    last_error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def __post_init__(self) -> None:
        if self.status not in FEATURE_STATUSES:
            raise ValueError(
                f"Invalid feature status {self.status!r}; "
                f"must be one of {FEATURE_STATUSES}"
            )


@dataclass
class PipelineState:
    """Top-level pipeline state persisted to disk as JSON.

    Fields:
        phase: Current pipeline phase.
        features: Mapping of feature name to its status.
        started_at: ISO 8601 timestamp when the pipeline was created.
        updated_at: ISO 8601 timestamp of last state mutation.
        paused_from: Phase the pipeline was in before entering 'paused'.
            Only set when phase is 'paused'; None otherwise.
    """

    phase: str = "planning"
    features: dict[str, FeatureStatus] = field(default_factory=dict)
    started_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    paused_from: Optional[str] = None

    def __post_init__(self) -> None:
        if self.phase not in PHASES:
            raise ValueError(
                f"Invalid phase {self.phase!r}; must be one of {PHASES}"
            )


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def load_state(state_path: Path) -> PipelineState:
    """Read pipeline state from a JSON file.

    Args:
        state_path: Path to the pipeline-state.json file.

    Returns:
        Deserialized PipelineState.

    Raises:
        FileNotFoundError: If the state file does not exist.
        json.JSONDecodeError: If the file is not valid JSON.
    """
    raw = json.loads(state_path.read_text(encoding="utf-8"))

    # Rehydrate nested FeatureStatus dicts into dataclass instances
    features: dict[str, FeatureStatus] = {}
    for name, fs_dict in raw.get("features", {}).items():
        features[name] = FeatureStatus(**fs_dict)

    return PipelineState(
        phase=raw["phase"],
        features=features,
        started_at=raw["started_at"],
        updated_at=raw["updated_at"],
        paused_from=raw.get("paused_from"),
    )


def save_state(state: PipelineState, state_path: Path) -> None:
    """Atomically write pipeline state to a JSON file.

    Writes to a temporary file in the same directory, then renames.
    This prevents shell scripts from reading a partially-written file.

    Args:
        state: The PipelineState to persist.
        state_path: Destination path for the JSON file.
    """
    state_path.parent.mkdir(parents=True, exist_ok=True)

    data = asdict(state)
    payload = json.dumps(data, indent=2, sort_keys=False) + "\n"

    # Write to a temp file in the same directory so os.replace is atomic
    fd, tmp_path = tempfile.mkstemp(
        dir=state_path.parent,
        prefix=".pipeline-state-",
        suffix=".tmp",
    )
    closed = False
    try:
        os.write(fd, payload.encode("utf-8"))
        os.close(fd)
        closed = True
        os.replace(tmp_path, state_path)
    except BaseException:
        if not closed:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Transitions
# ---------------------------------------------------------------------------

def transition(state: PipelineState, new_phase: str) -> PipelineState:
    """Validate and apply a pipeline phase transition.

    Valid transitions:
        planning -> executing -> merging -> integration-review -> complete
        (any non-complete phase) -> paused
        paused -> (the phase it was paused from)

    Args:
        state: Current pipeline state (mutated in place and returned).
        new_phase: Target phase.

    Returns:
        The updated PipelineState.

    Raises:
        ValueError: If the transition is not allowed.
    """
    if new_phase not in PHASES:
        raise ValueError(
            f"Invalid target phase {new_phase!r}; must be one of {PHASES}"
        )

    current = state.phase

    # Transition: any (non-complete, non-paused) -> paused
    if new_phase == "paused":
        if current == "complete":
            raise ValueError("Cannot pause a completed pipeline")
        if current == "paused":
            raise ValueError("Pipeline is already paused")
        state.paused_from = current
        state.phase = "paused"
        state.updated_at = _now_iso()
        return state

    # Transition: paused -> previous phase (resume)
    if current == "paused":
        if new_phase != state.paused_from:
            raise ValueError(
                f"Can only resume to the phase before pause "
                f"({state.paused_from!r}), not {new_phase!r}"
            )
        state.phase = new_phase
        state.paused_from = None
        state.updated_at = _now_iso()
        return state

    # Forward transition
    allowed = _FORWARD_TRANSITIONS.get(current, set())
    if new_phase not in allowed:
        raise ValueError(
            f"Invalid transition {current!r} -> {new_phase!r}; "
            f"allowed targets from {current!r}: {sorted(allowed) or '(none)'}"
        )

    state.phase = new_phase
    state.paused_from = None
    state.updated_at = _now_iso()
    return state


# ---------------------------------------------------------------------------
# Feature status updates
# ---------------------------------------------------------------------------

def update_feature_status(
    state: PipelineState,
    feature: str,
    status: str,
    error: Optional[str] = None,
) -> PipelineState:
    """Update a feature's status within the pipeline state.

    If the feature transitions to "executing" while already in "executing"
    (a retry), the retry counter is incremented.

    Args:
        state: Current pipeline state (mutated in place and returned).
        feature: Feature name (must exist in state.features).
        status: New status string.
        error: Optional error message (sets last_error on the feature).

    Returns:
        The updated PipelineState.

    Raises:
        KeyError: If the feature is not in the pipeline state.
        ValueError: If the status is not valid.
    """
    if status not in FEATURE_STATUSES:
        raise ValueError(
            f"Invalid feature status {status!r}; "
            f"must be one of {FEATURE_STATUSES}"
        )

    if feature not in state.features:
        raise KeyError(f"Feature {feature!r} not found in pipeline state")

    fs = state.features[feature]

    # Detect retry: executing -> executing
    if status == "executing" and fs.status == "executing":
        fs.retries += 1

    # Set started_at on first transition away from pending
    if fs.status == "pending" and status != "pending" and fs.started_at is None:
        fs.started_at = _now_iso()

    # Set completed_at on terminal statuses
    if status in ("merged", "failed"):
        fs.completed_at = _now_iso()

    fs.status = status

    if error is not None:
        fs.last_error = error

    state.updated_at = _now_iso()
    return state


# ---------------------------------------------------------------------------
# Event logging
# ---------------------------------------------------------------------------

def log_event(log_path: Path, event_dict: dict) -> None:
    """Append a JSONL event line to the log file.

    Automatically adds a "ts" field with the current UTC time in ISO 8601
    format. The timestamp is placed first in the output for readability.

    Args:
        log_path: Path to the events log file (created if missing).
        event_dict: Event data. Should contain at least an "event" key.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)

    entry = {"ts": _now_iso()}
    entry.update(event_dict)

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
