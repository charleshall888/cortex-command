"""cortex-lifecycle-prepare-worktree — composes the Implement §1a interactive
worktree setup (overnight guard, lock acquire, worktree creation) into one call.

Before the harness-token-efficiency-trim follow-up, ``implement.md`` §1a
narrated this as three separate steps run back-to-back in prose (i. overnight
guard, ii. interactive lock acquire, iii. worktree creation). This verb
composes them and returns ONE JSON struct whose ``state`` discriminates the
outcome — mirroring how ``cortex-lifecycle-branch-decision`` composed the §1
branch/dispatch reads.

Runs unconditionally for BOTH the ``selected`` and ``suppressed`` entry modes:
the worktree is created either way; only the downstream auto-enter mechanism
(``EnterWorktree`` vs. the cd-shim) differs, and that stays in skill prose
since ``EnterWorktree`` is an Agent-SDK tool call this verb cannot make.

The overnight-guard check here intentionally RE-IMPLEMENTS (does not
subprocess into) the sidecar at
``skills/lifecycle/references/_interactive_overnight_check.sh``: the sidecar
is a skill-tree asset installed via the Claude Code plugin channel, while this
module ships in the separately-installed cortex-command wheel — the two
channels are not guaranteed co-located on disk at runtime, so this verb
cannot depend on the sidecar's file path. The sidecar itself is unchanged and
still guards Implement §1 Step A directly; the liveness check below
intentionally matches its crude ``kill -0`` semantics (not
``cortex_command.overnight.ipc.verify_runner_pid``'s stricter start_time
comparison) so the two independent checks agree on what counts as "active".

States:
  ok               — worktree ready; ``worktree_path`` set. An optional
                     ``warning`` field carries a stale-runner.pid diagnostic.
  overnight-active — a live overnight run holds this repo; ``message`` is
                     the exact rejection wording to surface verbatim.
  lock-held        — a live same-slug interactive session holds the lock;
                     ``message`` is the exact rejection wording.
  create-failed    — worktree creation failed after the lock was acquired;
                     the lock is released (if this session owns it) before
                     returning, and ``message`` carries ``repr(exc)``.

Never calls ``EnterWorktree`` or emits the ``interactive_worktree_entered``
event — those still run in skill prose after this resolves.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Optional

from cortex_command.backlog import _telemetry
from cortex_command.common import _resolve_user_project_root
from cortex_command.interactive_lock import (
    acquire_lock,
    read_lock,
    release_lock_if_owner,
)
from cortex_command.overnight.ipc import read_active_session, read_runner_pid
from cortex_command.pipeline.worktree import create_worktree

KNOWN_STATES = ("ok", "overnight-active", "lock-held", "create-failed")

_OVERNIGHT_REJECTION = (
    "Overnight runner is active for this repo — wait for it to complete "
    "before creating an interactive worktree (`cortex overnight status`)."
)


def _check_overnight_guard(repo_root: Path) -> tuple:
    """Return ``(state, warning)``; ``state`` is one of 'clear'/'active'/'stale'.

    'stale' still proceeds (warn-and-continue) — ``warning`` carries the
    diagnostic. 'active' rejects; 'clear' proceeds with no warning.
    """
    session = read_active_session()
    if session is None:
        return "clear", None
    if session.get("repo_path") != str(repo_root):
        return "clear", None
    session_dir = session.get("session_dir")
    if not session_dir:
        return "clear", None

    runner = read_runner_pid(Path(session_dir))
    if runner is None:
        return "stale", "stale runner.pid detected (session pointer present, runner.pid absent)"

    pid = runner.get("pid")
    if not isinstance(pid, int):
        return "stale", "stale runner.pid detected (runner.pid has no pid field)"

    try:
        os.kill(pid, 0)
    except OSError:
        return "stale", "stale runner.pid detected (recorded process is not running)"

    return "active", None


def _lock_rejection_message(feature: str) -> str:
    """Mirror ``cortex-interactive-lock acquire``'s stderr wording on rejection."""
    lock = read_lock(feature)
    session_id = lock.get("session_id") if lock else "unknown"
    acquired_at = lock.get("acquired_at") if lock else "unknown"
    return (
        f"Interactive session already active on this feature "
        f"(session {session_id}, acquired {acquired_at}). "
        f"Wait for it to exit, or work on a different feature, "
        f"or run `cortex-interactive-lock inspect {feature}` for details."
    )


def prepare_worktree(feature: str, project_root: Optional[Path] = None) -> dict:
    """Compose the overnight guard, lock acquire, and worktree creation."""
    root = project_root or _resolve_user_project_root()

    guard_state, warning = _check_overnight_guard(root)
    if guard_state == "active":
        return {"state": "overnight-active", "message": _OVERNIGHT_REJECTION}

    if not acquire_lock(feature):
        return {"state": "lock-held", "message": _lock_rejection_message(feature)}

    try:
        info = create_worktree(feature=f"interactive-{feature}", base_branch="main")
    except Exception as exc:  # noqa: BLE001 — surfaced verbatim via repr(exc)
        release_lock_if_owner(feature)
        return {"state": "create-failed", "message": repr(exc)}

    result: dict = {"state": "ok", "worktree_path": str(info.path)}
    if warning:
        result["warning"] = warning
    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cortex-lifecycle-prepare-worktree",
        description=(
            "Compose the Implement §1a overnight guard, interactive-lock "
            "acquisition, and worktree creation into a single {state, ...} "
            "struct on stdout (always exit 0)."
        ),
    )
    parser.add_argument("--feature", required=True, help="Lifecycle feature slug.")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    _telemetry.log_invocation("cortex-lifecycle-prepare-worktree")
    args = _build_parser().parse_args(argv)
    sys.stdout.write(json.dumps(prepare_worktree(args.feature)) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
