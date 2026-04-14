"""Daytime pipeline driver — single-feature async CLI.

Thin async CLI driver for daytime (foreground) execution of a single
feature via the existing overnight execution pipeline
(``execute_feature`` -> ``apply_feature_result`` -> ``cleanup_worktree``).

This module (Task 3 of the build-daytime-pipeline-module-and-cli feature)
provides startup-layer helpers only: a CWD guard, PID file I/O and
liveness check, a SIGKILL recovery sequence, and a ``build_config``
factory that constructs a ``BatchConfig`` pointing at per-feature paths
and writes the initial ``daytime-state.json``. The async execution
driver (``run_daytime``) and CLI entry point are added in Task 4.
"""

from __future__ import annotations

import errno
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from claude.overnight.batch_runner import BatchConfig
from claude.overnight.state import (
    OvernightFeatureStatus,
    OvernightState,
    save_state,
)


def _check_cwd() -> None:
    """Abort if the CLI is not launched from the repo root.

    All path construction in ``feature_executor`` and ``outcome_router``
    is CWD-relative, so running from the wrong directory would silently
    write artifacts to the wrong locations.
    """
    if not Path("lifecycle").is_dir():
        sys.stderr.write(
            "error: must be run from the repo root "
            "(lifecycle/ directory not found)\n"
        )
        sys.exit(1)


def _pid_path(feature: str) -> Path:
    """Return the PID file path for a given feature."""
    return Path(f"lifecycle/{feature}/daytime.pid")


def _read_pid(pid_path: Path) -> Optional[int]:
    """Read a PID file and return the integer PID, or None on missing/parse error."""
    try:
        text = pid_path.read_text(encoding="utf-8").strip()
    except (FileNotFoundError, OSError):
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _is_alive(pid: int) -> bool:
    """Return True if a process with ``pid`` exists.

    Uses the canonical ``os.kill(pid, 0)`` liveness probe:
        - Returns True on success (signal delivered; process exists).
        - Returns True on PermissionError (process exists but owned
          by a different user).
        - Returns False on OSError with errno.ESRCH (no such process).
    """
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except OSError as exc:
        if exc.errno == errno.ESRCH:
            return False
        # Unknown errno — default to "alive" to be conservative.
        return True


def _write_pid(pid_path: Path) -> None:
    """Write the current process's PID to ``pid_path``.

    Ensures the parent directory exists (creating it recursively if needed).
    """
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text(str(os.getpid()), encoding="utf-8")


def _worktree_path(feature: str) -> Path:
    """Return the worktree path for a given feature."""
    return Path(".claude") / "worktrees" / feature


def _recover_stale(feature: str, worktree_path: Path) -> None:
    """Recover from a SIGKILLed prior daytime run.

    Ordering (matches research.md SIGKILL recovery sequence):
        1. Abort any in-progress merge in the worktree (if MERGE_HEAD exists).
        2. Remove all ``*.lock`` files under the worktree.
        3. Force-remove the worktree (``git worktree remove --force --force``).
        4. Prune the worktree list (``git worktree prune``).

    All git subprocess calls pass ``cwd=worktree_path`` rather than ``-C``
    (per project sandbox rules — see claude/rules/sandbox-behaviors.md).
    """
    del feature  # unused — worktree_path is the canonical location

    # 1. Abort any in-progress merge in the worktree.
    merge_head = worktree_path / ".git" / "MERGE_HEAD"
    if merge_head.exists():
        subprocess.run(
            ["git", "merge", "--abort"],
            cwd=worktree_path,
            check=False,
        )

    # 2. Remove all .lock files under the worktree.
    if worktree_path.exists():
        for lock in worktree_path.rglob("*.lock"):
            try:
                lock.unlink()
            except FileNotFoundError:
                pass

    # 3. Force-remove the worktree (double-force removes locked worktrees).
    subprocess.run(
        ["git", "worktree", "remove", "--force", "--force", str(worktree_path)],
        cwd=worktree_path if worktree_path.exists() else None,
        check=False,
    )

    # 4. Prune the worktree list.
    subprocess.run(
        ["git", "worktree", "prune"],
        cwd=worktree_path if worktree_path.exists() else None,
        check=False,
    )


def _read_test_command(cwd: Path) -> str:
    """Read ``test-command`` from ``lifecycle.config.md`` frontmatter.

    Returns ``"just test"`` if the file is missing, has no frontmatter
    key, or cannot be parsed.
    """
    config_path = cwd / "lifecycle.config.md"
    try:
        text = config_path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return "just test"

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("test-command:"):
            value = stripped[len("test-command:"):].strip()
            # Strip surrounding quotes if present.
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            if value:
                return value
    return "just test"


def build_config(feature: str, cwd: Path, session_id: str) -> BatchConfig:
    """Construct a single-feature ``BatchConfig`` and initial state file.

    Builds per-feature paths under ``lifecycle/{feature}/``, writes an
    initial ``daytime-state.json`` (minimal ``OvernightState`` for a
    single feature), and pre-creates the per-feature deferred directory.

    Args:
        feature: Feature slug (used as directory name under lifecycle/).
        cwd: Absolute path to the repo root; used as the base for all
            per-feature paths. The CLI enforces ``cwd`` is the repo root
            via ``_check_cwd()``.
        session_id: Unique identifier for this daytime session.

    Returns:
        A ``BatchConfig`` pointing at per-feature artifact paths.
    """
    test_command = _read_test_command(cwd)

    config = BatchConfig(
        batch_id=1,
        plan_path=cwd / f"lifecycle/{feature}/plan.md",
        test_command=test_command,
        base_branch="main",
        overnight_state_path=cwd / f"lifecycle/{feature}/daytime-state.json",
        overnight_events_path=cwd / f"lifecycle/{feature}/events.log",
        result_dir=cwd / f"lifecycle/{feature}",
        pipeline_events_path=cwd / f"lifecycle/{feature}/pipeline-events.log",
    )

    state = OvernightState(
        session_id=session_id,
        plan_ref=str(config.plan_path),
        current_round=1,
        phase="executing",
        features={
            feature: OvernightFeatureStatus(
                status="running",
                round_assigned=1,
            ),
        },
    )
    save_state(state, config.overnight_state_path)

    (cwd / f"lifecycle/{feature}/deferred").mkdir(parents=True, exist_ok=True)

    return config
