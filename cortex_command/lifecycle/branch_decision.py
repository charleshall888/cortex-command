"""cortex-lifecycle-branch-decision — one read-only call that resolves the
Implement §1 branch/dispatch decision.

Composes the four reads the Implement reference used to narrate step-by-step —
current-branch check, plan-time ``dispatch_choice``, per-repo ``branch-mode``
config, and the ``should_fire_picker`` gate — plus the two picker-rendering
guards (dirty tree, worktree-CLI availability). Returns ONE struct whose
``state`` discriminates the outcome:

  skip      — not on main/master; proceed on the current branch.
  resolved  — a branch mode was determined without prompting (from the
              plan-time dispatch_choice, or a suppressing branch-mode config).
              Carries ``branch_mode`` and, for worktree-interactive, ``entry_mode``.
  prompt    — the picker fires; carries ``uncommitted_changes`` and
              ``worktree_option_available`` so the skill can render the options.

Read-only by contract: it never creates a worktree, acquires a lock, or writes.
Those actions stay in the Implement reference and run after this resolves.
Emits one JSON object on stdout, always exit 0.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from cortex_command.backlog import _telemetry
from cortex_command.lifecycle_config import read_branch_mode
from cortex_command.lifecycle_implement import (
    _is_dirty_tree,
    read_dispatch_choice,
    should_fire_picker,
)

KNOWN_STATES = ("skip", "resolved", "prompt")

_VALID_MODES = ("trunk", "worktree-interactive", "feature-branch")


def _current_branch(repo_root: Path) -> Optional[str]:
    """Current branch name, or None if git is unavailable / detached."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def _entry_mode(branch_mode: Optional[str], source: str) -> Optional[str]:
    """Worktree entry mode: 'selected' from a plan-time choice, 'suppressed'
    from a branch-mode config that bypassed the picker. None for non-worktree."""
    if branch_mode != "worktree-interactive":
        return None
    return "selected" if source == "dispatch_choice" else "suppressed"


def _next_for_mode(branch_mode: Optional[str], entry_mode: Optional[str]) -> str:
    if branch_mode == "trunk":
        return "Proceed on the current branch to §2 Task Dispatch."
    if branch_mode == "feature-branch":
        return "Create and check out feature/{lifecycle-slug}, then §2 Task Dispatch."
    if branch_mode == "worktree-interactive":
        return (
            f"Record entry mode '{entry_mode}' and proceed to §1a Interactive "
            "Worktree Creation."
        )
    return "Proceed to §2 Task Dispatch."


def resolve_branch_decision(feature: str, project_root: Optional[Path] = None) -> dict:
    root = project_root or Path.cwd()

    branch = _current_branch(root)
    if branch not in ("main", "master"):
        return {
            "state": "skip",
            "branch": branch,
            "next": "Not on main/master — proceed on the current branch; skip the picker.",
        }

    # Primary path: a branch mode recorded at plan approval time.
    events_path = root / "cortex" / "lifecycle" / feature / "events.log"
    choice = read_dispatch_choice(events_path)
    if choice in _VALID_MODES:
        entry = _entry_mode(choice, "dispatch_choice")
        return {
            "state": "resolved",
            "source": "dispatch_choice",
            "branch_mode": choice,
            "entry_mode": entry,
            "next": _next_for_mode(choice, entry),
        }

    # Fallback: per-repo branch-mode config + the picker-fire gate.
    mode = read_branch_mode(root)
    fire, reason = should_fire_picker(root, feature, mode)
    if not fire:
        entry = _entry_mode(mode, "branch_mode")
        return {
            "state": "resolved",
            "source": "branch_mode",
            "branch_mode": mode,
            "entry_mode": entry,
            "reason": reason,
            "next": _next_for_mode(mode, entry),
        }

    # Picker fires — carry the rendering guards.
    return {
        "state": "prompt",
        "reason": reason,
        "uncommitted_changes": _is_dirty_tree(root),
        "worktree_option_available": shutil.which("cortex-worktree-create") is not None,
        "next": (
            "Render the branch picker. uncommitted_changes=true demotes the "
            "current-branch option with the warning; worktree_option_available=false "
            "drops the worktree option."
        ),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex-lifecycle-branch-decision",
        description=(
            "Resolve the Implement §1 branch/dispatch decision to a single "
            "{state, ...} struct on stdout (always exit 0)."
        ),
    )
    parser.add_argument("--feature", required=True, help="Lifecycle feature slug.")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    _telemetry.log_invocation("cortex-lifecycle-branch-decision")
    args = _build_parser().parse_args(argv)
    sys.stdout.write(json.dumps(resolve_branch_decision(args.feature)) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
