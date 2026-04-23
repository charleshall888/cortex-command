"""Evidence-based interrupt handling for overnight orchestration.

When runner.sh starts and finds features stuck in 'running' status, this
module checks each feature's worktree state, logs an 'interrupted' event
with a reason field, and resets the feature to 'pending'.

Callable as:
    python3 -m claude.overnight.interrupt [state_path]

The state_path argument defaults to lifecycle/overnight-state.json.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from cortex_command.overnight.events import INTERRUPTED, events_log_path, log_event
from cortex_command.overnight.state import load_state, save_state, update_feature_status


def _worktree_path(feature: str) -> Path:
    """Return the expected worktree path for a feature."""
    return Path(f"worktrees/{feature}")


def _worktree_exists(feature: str) -> bool:
    """Return True if a git worktree is registered at worktrees/{feature}/."""
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
    )
    worktree_dir = str(_worktree_path(feature).resolve())
    # Each worktree block starts with "worktree <path>"
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            registered_path = line[len("worktree "):].strip()
            if registered_path == worktree_dir:
                return True
    return False


def _count_commits_in_worktree(feature: str) -> int:
    """Count commits in the worktree branch that are not in repo HEAD.

    Gets the worktree HEAD SHA, compares to main repo HEAD, and counts
    commits reachable from the worktree HEAD but not from the repo HEAD.
    """
    wt_path = _worktree_path(feature)

    # Get the worktree current HEAD SHA
    result = subprocess.run(
        ["git", "-C", str(wt_path), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return 0
    worktree_head = result.stdout.strip()

    # Get the main repo HEAD SHA
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return 0
    repo_head = result.stdout.strip()

    if worktree_head == repo_head:
        return 0

    # Count commits in worktree not reachable from repo HEAD
    result = subprocess.run(
        ["git", "log", "--oneline", f"{repo_head}..{worktree_head}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return 0

    lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
    return len(lines)


def _reason_for(feature: str) -> str:
    """Determine the interrupt reason for a stuck feature."""
    if not _worktree_exists(feature):
        return "no_worktree"

    commit_count = _count_commits_in_worktree(feature)
    if commit_count == 0:
        return "empty_worktree"

    return f"worktree_with_{commit_count}_commits"


def handle_interrupted_features(state_path: Path) -> None:
    """Find features stuck in 'running', log interrupts, reset to 'pending'.

    For each feature with status == 'running':
    1. Determine the worktree reason (no_worktree, empty_worktree, or
       worktree_with_N_commits).
    2. Log an 'interrupted' event with the reason to the per-session log.
    3. Reset the feature to 'pending' and clear started_at in state.

    Note: recovery_attempts, recovery_depth, and paused_reason are intentionally
    preserved — do not reset them here. They persist across restarts so a feature
    that exhausted its recovery budget before an interruption retains that history,
    and the session-level paused_reason remains readable after a restart.

    Args:
        state_path: Path to overnight-state.json.
    """
    state = load_state(state_path)

    running_features = [
        name for name, fs in state.features.items()
        if fs.status == "running"
    ]

    if not running_features:
        return

    log_path = events_log_path(state.session_id)

    for feature in running_features:
        reason = _reason_for(feature)

        log_event(
            INTERRUPTED,
            round=0,
            feature=feature,
            details={"reason": reason},
            log_path=log_path,
        )

        # Reset to pending and clear started_at
        update_feature_status(state, feature, "pending")
        state.features[feature].started_at = None

    save_state(state, state_path)

    print(
        f"interrupt.py: reset {len(running_features)} interrupted feature(s) "
        f"to pending: {', '.join(running_features)}"
    )


def main() -> None:
    """Entry point for python3 -m claude.overnight.interrupt."""
    if len(sys.argv) > 1:
        state_path = Path(sys.argv[1])
    else:
        state_path = Path("lifecycle/overnight-state.json")

    handle_interrupted_features(state_path)


if __name__ == "__main__":
    main()
