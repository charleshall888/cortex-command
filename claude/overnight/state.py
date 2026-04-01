"""Overnight orchestration state schema and persistence.

Defines the core data structures for overnight session state: session-level
state (OvernightState), per-feature status tracking (OvernightFeatureStatus),
and per-round summaries (RoundSummary). All structures use dataclasses with
__post_init__ validation to enforce invariants.

Persistence functions (save_state / load_state) use atomic writes via
tempfile + os.replace to prevent corruption on crash.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Lifecycle root (resolved from this file's location)
_LIFECYCLE_ROOT = Path(__file__).resolve().parents[2] / "lifecycle"

# Valid overnight feature statuses
FEATURE_STATUSES = (
    "pending", "running", "merged", "paused", "failed", "deferred",
)

# Valid overnight phases
PHASES = ("planning", "executing", "complete", "paused")

# Valid forward transitions (source -> set of allowed targets)
_FORWARD_TRANSITIONS: dict[str, set[str]] = {
    "planning": {"executing"},
    "executing": {"complete"},
}


def _now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _normalize_repo_key(path_str: str) -> str:
    """Normalize a filesystem path string for use as a dictionary key.

    Applies ``expanduser()`` and ``resolve()`` to ensure consistent keys
    regardless of whether the caller already resolved symlinks or not.
    This matches the key format used by ``plan.py`` when writing
    ``integration_branches`` and ``integration_worktrees``.
    """
    return str(Path(path_str).expanduser().resolve())


@dataclass
class OvernightFeatureStatus:
    """Tracks the status of a single feature within an overnight session.

    Fields:
        status: Current feature status.
        round_assigned: Round number in which this feature was assigned.
        started_at: ISO 8601 timestamp when work began on the feature.
        completed_at: ISO 8601 timestamp when the feature reached a
            terminal status (merged, failed, deferred).
        error: Most recent error message, if any.
        deferred_questions: Count of questions deferred for human review.
        spec_path: Path to the spec artifact (may be a batch spec shared
            across multiple features).
        plan_path: Path to the implementation plan for this feature.
        backlog_id: Numeric backlog item ID (e.g. 56 for backlog/056-*.md).
            Used to identify the item's section within a batch spec.
            None for features not sourced from numbered backlog files.
        repo_path: Filesystem path to the target repository for this feature.
            None for features targeting the default (current) repository.
        intra_session_blocked_by: Slugs of other in-session features that must
            reach status "merged" before this feature can be dispatched.
            Empty list means no intra-session blockers.
    """

    status: str = "pending"
    round_assigned: Optional[int] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    deferred_questions: int = 0
    spec_path: Optional[str] = None
    plan_path: Optional[str] = None
    backlog_id: Optional[int] = None
    recovery_attempts: int = 0
    recovery_depth: int = 0
    repo_path: Optional[str] = None
    intra_session_blocked_by: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.status not in FEATURE_STATUSES:
            raise ValueError(
                f"Invalid feature status {self.status!r}; "
                f"must be one of {FEATURE_STATUSES}"
            )
        if not isinstance(self.deferred_questions, int) or self.deferred_questions < 0:
            raise ValueError(
                f"deferred_questions must be a non-negative integer, "
                f"got {self.deferred_questions!r}"
            )
        if not isinstance(self.recovery_attempts, int) or self.recovery_attempts < 0:
            raise ValueError(
                f"recovery_attempts must be a non-negative integer, "
                f"got {self.recovery_attempts!r}"
            )
        if not isinstance(self.recovery_depth, int) or self.recovery_depth < 0:
            raise ValueError(
                f"recovery_depth must be a non-negative integer, "
                f"got {self.recovery_depth!r}"
            )


@dataclass
class RoundSummary:
    """Summary of a single execution round within an overnight session.

    Fields:
        round_number: 1-based round index.
        features_attempted: List of feature names attempted in this round.
        features_merged: List of feature names successfully merged.
        features_paused: List of feature names paused during this round.
        features_deferred: List of feature names deferred during this round.
        started_at: ISO 8601 timestamp when the round began.
        completed_at: ISO 8601 timestamp when the round finished.
    """

    round_number: int = 1
    features_attempted: list[str] = field(default_factory=list)
    features_merged: list[str] = field(default_factory=list)
    features_paused: list[str] = field(default_factory=list)
    features_deferred: list[str] = field(default_factory=list)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.round_number, int) or self.round_number < 1:
            raise ValueError(
                f"round_number must be a positive integer, "
                f"got {self.round_number!r}"
            )


@dataclass
class OvernightState:
    """Top-level overnight session state.

    Fields:
        session_id: Unique identifier for this overnight session.
        plan_ref: Path or reference to the plan being executed.
        plan_hash: SHA-256 hex digest of the plan content, frozen at session
            start. Used as the stable component in per-task idempotency
            tokens so that resumed sessions can detect already-dispatched
            tasks without re-hashing a potentially mutated plan file.
            None when the session was created before plan-hashing was
            introduced (backwards-compatible).
        current_round: Current round number (1-based).
        phase: Current session phase.
        features: Mapping of feature name to its status.
        round_history: List of completed round summaries.
        started_at: ISO 8601 timestamp when the session was created.
        updated_at: ISO 8601 timestamp of last state mutation.
        paused_from: Phase the session was in before entering 'paused'.
            Only set when phase is 'paused'; None otherwise.
        paused_reason: Free-form string describing why the session was paused
            (e.g. "signal", "stall_timeout", "budget_exhausted", "user_abort").
            None for sessions paused before this field was introduced or when
            no reason was recorded. Not reset when the session resumes.
        integration_branch: Git branch created for this session. All feature
            branches merge here; a PR to main is opened at session end.
        integration_branches: Mapping of absolute repo path (string) to
            integration branch name. Empty for pre-existing sessions; use
            integration_branch as fallback when empty.
        worktree_path: Absolute path to the git worktree created for this
            session (e.g. ``$TMPDIR/overnight-worktrees/{session_id}/``).
            None when the session was created before worktree isolation was
            introduced (backwards-compatible).
        project_root: Absolute path to the project repository root for this
            session. None when the session targets the default (home)
            repository or was created before multi-repo support.
        integration_worktrees: Keys are absolute repo paths (strings); values
            are absolute worktree paths checked out on that repo's integration
            branch. Empty for sessions created before this field existed.
    """

    session_id: str = ""
    plan_ref: str = ""
    plan_hash: Optional[str] = None
    current_round: int = 1
    phase: str = "planning"
    features: dict[str, OvernightFeatureStatus] = field(default_factory=dict)
    round_history: list[RoundSummary] = field(default_factory=list)
    started_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    paused_from: Optional[str] = None
    paused_reason: Optional[str] = None
    integration_branch: Optional[str] = None
    integration_branches: dict[str, str] = field(default_factory=dict)
    worktree_path: Optional[str] = None
    project_root: Optional[str] = None
    integration_worktrees: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.phase not in PHASES:
            raise ValueError(
                f"Invalid phase {self.phase!r}; must be one of {PHASES}"
            )
        if not isinstance(self.current_round, int) or self.current_round < 1:
            raise ValueError(
                f"current_round must be a positive integer, "
                f"got {self.current_round!r}"
            )


# ---------------------------------------------------------------------------
# Default state path
# ---------------------------------------------------------------------------

DEFAULT_STATE_PATH = _LIFECYCLE_ROOT / "overnight-state.json"


# ---------------------------------------------------------------------------
# Session path builders
# ---------------------------------------------------------------------------

def session_dir(
    session_id: str,
    lifecycle_root: Path = _LIFECYCLE_ROOT,
) -> Path:
    """Return the canonical directory for a session's artifacts.

    Pure path computation — performs no I/O.

    Args:
        session_id: Unique session identifier (e.g. "overnight-2026-03-02-2200").
        lifecycle_root: Root of the lifecycle directory tree.

    Returns:
        ``lifecycle_root / "sessions" / session_id``
    """
    return lifecycle_root / "sessions" / session_id


def latest_symlink_path(
    session_type: str,
    lifecycle_root: Path = _LIFECYCLE_ROOT,
) -> Path:
    """Return the canonical path for a latest-session symlink.

    Pure path computation — performs no I/O.

    Args:
        session_type: Session type label, e.g. ``"overnight"`` or ``"pipeline"``.
        lifecycle_root: Root of the lifecycle directory tree.

    Returns:
        ``lifecycle_root / "sessions" / f"latest-{session_type}"``
    """
    return lifecycle_root / "sessions" / f"latest-{session_type}"


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def load_state(state_path: Path = DEFAULT_STATE_PATH) -> OvernightState:
    """Read overnight state from a JSON file.

    Args:
        state_path: Path to the overnight-state.json file.

    Returns:
        Deserialized OvernightState with nested dataclass instances.

    Raises:
        FileNotFoundError: If the state file does not exist.
        json.JSONDecodeError: If the file is not valid JSON.
    """
    raw = json.loads(state_path.read_text(encoding="utf-8"))

    # Rehydrate nested OvernightFeatureStatus dicts
    features: dict[str, OvernightFeatureStatus] = {}
    for name, fs_dict in raw.get("features", {}).items():
        features[name] = OvernightFeatureStatus(**fs_dict)

    # Rehydrate nested RoundSummary dicts.
    # The orchestrator agent may write a simplified format with:
    #   - 'round' instead of 'round_number'
    #   - integer counts instead of list[str] for features_* fields
    #   - extra keys like 'features_failed' not present in the dataclass
    # Normalise before constructing.
    round_history: list[RoundSummary] = []
    list_fields = {"features_attempted", "features_merged", "features_paused", "features_deferred"}
    valid_fields = {f.name for f in RoundSummary.__dataclass_fields__.values()}
    for rs_raw in raw.get("round_history", []):
        rs_dict: dict = {}
        for k, v in rs_raw.items():
            # Map legacy 'round' key to 'round_number'
            if k == "round":
                rs_dict["round_number"] = v
                continue
            # Drop unknown keys (e.g. 'features_failed')
            if k not in valid_fields:
                continue
            # Convert integer counts to empty lists for list[str] fields
            if k in list_fields and isinstance(v, int):
                rs_dict[k] = []
            else:
                rs_dict[k] = v
        round_history.append(RoundSummary(**rs_dict))

    return OvernightState(
        session_id=raw["session_id"],
        plan_ref=raw["plan_ref"],
        plan_hash=raw.get("plan_hash"),
        current_round=raw["current_round"],
        phase=raw["phase"],
        features=features,
        round_history=round_history,
        started_at=raw["started_at"],
        updated_at=raw["updated_at"],
        paused_from=raw.get("paused_from"),
        paused_reason=raw.get("paused_reason"),
        integration_branch=raw.get("integration_branch"),
        integration_branches=raw.get("integration_branches", {}),
        worktree_path=raw.get("worktree_path"),
        project_root=raw.get("project_root"),
        integration_worktrees=raw.get("integration_worktrees") or {},
    )


def save_state(
    state: OvernightState,
    state_path: Path = DEFAULT_STATE_PATH,
) -> None:
    """Atomically write overnight state to a JSON file.

    Writes to a temporary file in the same directory, then renames via
    os.replace. This prevents readers from seeing a partially-written file.

    Args:
        state: The OvernightState to persist.
        state_path: Destination path for the JSON file.
    """
    state_path.parent.mkdir(parents=True, exist_ok=True)

    data = asdict(state)
    payload = json.dumps(data, indent=2, sort_keys=False) + "\n"

    # Write to a temp file in the same directory so os.replace is atomic
    fd, tmp_path = tempfile.mkstemp(
        dir=state_path.parent,
        prefix=".overnight-state-",
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

def transition(state: OvernightState, new_phase: str) -> OvernightState:
    """Validate and apply an overnight session phase transition.

    Valid transitions:
        planning -> executing -> complete
        (any non-complete phase) -> paused
        paused -> (the phase it was paused from)

    Args:
        state: Current overnight state (mutated in place and returned).
        new_phase: Target phase.

    Returns:
        The updated OvernightState.

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
            raise ValueError("Cannot pause a completed session")
        if current == "paused":
            raise ValueError("Session is already paused")
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
    state: OvernightState,
    feature: str,
    status: str,
    *,
    error: Optional[str] = None,
    round_number: Optional[int] = None,
) -> OvernightState:
    """Update a feature's status within the overnight session state.

    Tracks round_assigned when a feature first moves to 'running'.
    Sets completed_at on terminal statuses (merged, failed, deferred).
    Deferred is terminal for the current session round — work has stopped
    pending human answers and will not be retried without intervention.

    Args:
        state: Current overnight state (mutated in place and returned).
        feature: Feature name (must exist in state.features).
        status: New status string.
        error: Optional error message (sets error on the feature).
        round_number: Round number to record as round_assigned when the
            feature first transitions to 'running'. Defaults to
            state.current_round if not provided.

    Returns:
        The updated OvernightState.

    Raises:
        KeyError: If the feature is not in the overnight state.
        ValueError: If the status is not valid.
    """
    if status not in FEATURE_STATUSES:
        raise ValueError(
            f"Invalid feature status {status!r}; "
            f"must be one of {FEATURE_STATUSES}"
        )

    if feature not in state.features:
        raise KeyError(f"Feature {feature!r} not found in overnight state")

    fs = state.features[feature]

    # Track round_assigned when first moving to running
    if status == "running" and fs.round_assigned is None:
        fs.round_assigned = round_number if round_number is not None else state.current_round

    # Set started_at on first transition away from pending
    if fs.status == "pending" and status != "pending" and fs.started_at is None:
        fs.started_at = _now_iso()

    # Set completed_at on terminal statuses
    if status in ("merged", "failed", "deferred"):
        fs.completed_at = _now_iso()

    fs.status = status

    if error is not None:
        fs.error = error

    state.updated_at = _now_iso()
    return state


# ---------------------------------------------------------------------------
# Resume capability
# ---------------------------------------------------------------------------

@dataclass
class ResumeInfo:
    """Read-only analysis of what work remains in an overnight session.

    Produced by determine_resume_point() and consumed by the orchestrator
    on restart to skip already-completed work.

    Fields:
        completed_features: Feature names that have been merged.
        current_round: The round number recorded in the session state.
        pending_features: Feature names still needing work (any status
            other than 'merged').
        phase: The current session phase.
    """

    completed_features: list[str] = field(default_factory=list)
    current_round: int = 1
    pending_features: list[str] = field(default_factory=list)
    phase: str = "planning"


def determine_resume_point(state: OvernightState) -> ResumeInfo:
    """Analyze overnight state and return what work remains.

    This is a read-only function — it does not mutate state. The
    orchestrator calls it after load_state() to decide which features
    to skip and where to continue.

    A feature is considered completed only when its status is 'merged'.
    All other statuses (pending, running, paused, failed, deferred) are
    treated as pending work that still needs attention.

    Args:
        state: The loaded OvernightState to analyze.

    Returns:
        A ResumeInfo summarizing completed vs. pending features, the
        current round, and the session phase.
    """
    completed: list[str] = []
    pending: list[str] = []

    for name, fs in state.features.items():
        if fs.status == "merged":
            completed.append(name)
        else:
            pending.append(name)

    return ResumeInfo(
        completed_features=completed,
        current_round=state.current_round,
        pending_features=pending,
        phase=state.phase,
    )
