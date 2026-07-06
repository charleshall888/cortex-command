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
KEEP THE TWO IN SYNC: the sidecar's pid-liveness coercion and this module's
``_check_overnight_guard`` must accept the same pid shapes (see the comment
at the coercion site below and the matching one in the sidecar).

The guard's default repo root, and the base-branch auto-detection, are both
resolved against the SAME physical repo that ``acquire_lock`` and
``create_worktree`` will actually act on (via
``interactive_lock._resolve_main_repo_root`` and git itself, respectively) —
never against ``common._resolve_user_project_root``, whose ``CORTEX_REPO_ROOT``
handling is verbatim (unresolved) and so can disagree with the canonicalized
path the overnight runner records in its session pointer.

States:
  ok               — worktree ready; ``worktree_path`` set. An optional
                     ``warning`` field carries a stale-runner.pid diagnostic.
  overnight-active — a live overnight run holds this repo; ``message`` is
                     the exact rejection wording to surface verbatim.
  lock-held        — a live same-slug interactive session holds the lock;
                     ``message`` is the exact rejection wording.
  create-failed    — either no trunk branch could be auto-detected (before
                     the lock is touched), or worktree creation failed after
                     the lock was acquired (lock released, if this session
                     owns it, before returning); ``message`` explains which.
  error            — an unexpected exception (e.g. the project root could
                     not be resolved) escaped ``prepare_worktree`` itself;
                     ``main`` catches it here so the CLI always emits a JSON
                     struct and exits 0 rather than a traceback.

Never calls ``EnterWorktree`` or emits the ``interactive_worktree_entered``
event — those still run in skill prose after this resolves.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from cortex_command.backlog import _telemetry
from cortex_command.interactive_lock import (
    _resolve_main_repo_root,
    acquire_lock,
    read_lock,
    rejection_message,
    release_lock_if_owner,
)
from cortex_command.overnight.ipc import read_active_session, read_runner_pid
from cortex_command.pipeline.worktree import create_worktree

KNOWN_STATES = ("ok", "overnight-active", "lock-held", "create-failed", "error")

_OVERNIGHT_REJECTION = (
    "Overnight runner is active for this repo — wait for it to complete "
    "before creating an interactive worktree (`cortex overnight status`)."
)


def _check_overnight_guard(repo_root: Path) -> tuple[bool, Optional[str]]:
    """Return ``(active, warning)``.

    ``active`` True means a live overnight run holds *repo_root* and the
    caller must reject. When not active, an optional ``warning`` carries a
    stale-runner.pid diagnostic — that case still proceeds (warn-and-continue).
    """
    session = read_active_session()
    if session is None:
        return False, None

    session_repo_path = session.get("repo_path")
    if session_repo_path is None:
        return False, None

    # Compare canonicalized physical paths on both sides: the overnight
    # runner records its session repo_path via a resolver that (in at least
    # one precedence branch) applies .resolve(), while a caller-supplied or
    # default-resolved repo_root here may not be — an unresolved vs.
    # resolved form of the same repo must not be treated as different repos
    # (that would fail the guard open).
    try:
        same_repo = Path(session_repo_path).resolve() == repo_root.resolve()
    except (OSError, RuntimeError):
        same_repo = False
    if not same_repo:
        return False, None

    session_dir = session.get("session_dir")
    if not session_dir:
        return False, None

    runner = read_runner_pid(Path(session_dir))
    if runner is None:
        return False, "stale runner.pid detected (session pointer present, runner.pid absent)"

    # Coerce int-like pid values (e.g. a numeric string) before the liveness
    # check so this agrees with the sidecar's `kill -0 "$pid"` semantics,
    # which treats any numeric string as live. KEEP IN SYNC with
    # skills/lifecycle/references/_interactive_overnight_check.sh — a change
    # to one side's pid-shape handling must be mirrored in the other.
    try:
        pid = int(str(runner.get("pid")))
    except (TypeError, ValueError):
        return False, "stale runner.pid detected (runner.pid has no pid field)"

    try:
        os.kill(pid, 0)
    except OSError:
        return False, "stale runner.pid detected (recorded process is not running)"

    return True, None


def _detect_base_branch(repo_root: Path) -> Optional[str]:
    """Detect the trunk branch name for *repo_root*.

    Prefers ``origin/HEAD``'s target (via ``git symbolic-ref``, stripped of
    its ``origin/`` prefix); falls back to whichever of ``main``/``master``
    has a local ref. Returns ``None`` when neither is resolvable — the
    caller surfaces that as ``create-failed`` rather than hardcoding a
    branch name that may not exist (a master-default repo has no ``main``).
    """
    try:
        proc = subprocess.run(
            ["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        proc = None
    if proc is not None and proc.returncode == 0:
        branch = proc.stdout.strip()
        if branch.startswith("origin/"):
            branch = branch[len("origin/"):]
        if branch:
            return branch

    for candidate in ("main", "master"):
        try:
            proc = subprocess.run(
                ["git", "rev-parse", "--verify", f"refs/heads/{candidate}"],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if proc.returncode == 0:
            return candidate

    return None


def prepare_worktree(
    feature: str,
    project_root: Optional[Path] = None,
    base_branch: Optional[str] = None,
) -> dict:
    """Compose the overnight guard, base-branch resolution, lock acquire,
    and worktree creation."""
    root = project_root or _resolve_main_repo_root()

    active, warning = _check_overnight_guard(root)
    if active:
        return {"state": "overnight-active", "message": _OVERNIGHT_REJECTION}

    resolved_base_branch = base_branch or _detect_base_branch(root)
    if resolved_base_branch is None:
        return {
            "state": "create-failed",
            "message": (
                "Could not detect a trunk branch for the interactive worktree "
                "(no origin/HEAD, refs/heads/main, or refs/heads/master) — "
                "pass --base-branch explicitly."
            ),
        }

    if not acquire_lock(feature):
        return {
            "state": "lock-held",
            "message": rejection_message(feature, read_lock(feature)),
        }

    try:
        info = create_worktree(feature=f"interactive-{feature}", base_branch=resolved_base_branch)
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
            "Compose the Implement §1a overnight guard, base-branch "
            "resolution, interactive-lock acquisition, and worktree "
            "creation into a single {state, ...} struct on stdout "
            "(always exit 0)."
        ),
    )
    parser.add_argument("--feature", required=True, help="Lifecycle feature slug.")
    parser.add_argument(
        "--base-branch",
        default=None,
        help=(
            "Base branch for the interactive worktree. Defaults to "
            "auto-detection (origin/HEAD, then refs/heads/main, then "
            "refs/heads/master)."
        ),
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    _telemetry.log_invocation("cortex-lifecycle-prepare-worktree")
    args = _build_parser().parse_args(argv)
    try:
        result = prepare_worktree(args.feature, base_branch=args.base_branch)
    except Exception as exc:  # noqa: BLE001 — always emit a JSON struct, never a traceback
        result = {"state": "error", "message": repr(exc)}
    sys.stdout.write(json.dumps(result) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
