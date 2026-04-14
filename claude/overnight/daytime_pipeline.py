"""Daytime pipeline driver — single-feature async CLI.

Thin async CLI driver for daytime (foreground) execution of a single
feature via the existing overnight execution pipeline
(``execute_feature`` -> ``apply_feature_result`` -> ``cleanup_worktree``).

Provides startup-layer helpers (CWD guard, PID file I/O and liveness
check, SIGKILL recovery sequence, ``build_config`` factory) and the
async execution driver (``run_daytime``) plus CLI entry point
(``build_parser``, ``_run``).
"""

from __future__ import annotations

import argparse
import asyncio
import errno
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from claude.overnight.batch_runner import BatchConfig
from claude.overnight.deferral import DEFAULT_DEFERRED_DIR
from claude.overnight.feature_executor import execute_feature
from claude.overnight.orchestrator import BatchResult
from claude.overnight.outcome_router import OutcomeContext, apply_feature_result
from claude.overnight.state import (
    OvernightFeatureStatus,
    OvernightState,
    save_state,
)
from claude.overnight.types import CircuitBreakerState
from claude.pipeline.worktree import cleanup_worktree, create_worktree


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


async def _orphan_guard(feature: str, pid_path: Path) -> None:
    """Background guard that cleans up if the process is orphaned.

    Loops indefinitely, sleeping 1 second between iterations. On each
    wake, checks whether the process has been orphaned (parent PID is
    1); if orphaned, calls ``cleanup_worktree(feature)``, removes
    ``pid_path``, then calls ``os._exit(1)``.

    Uses ``os._exit`` — not ``sys.exit`` — because ``sys.exit`` inside a
    coroutine raises ``SystemExit`` only within the task; the main
    coroutine would continue unaffected.
    """
    while True:
        await asyncio.sleep(1)
        if os.getppid() == 1:
            try:
                cleanup_worktree(feature)
            finally:
                pid_path.unlink(missing_ok=True)
                os._exit(1)


async def run_daytime(feature: str) -> int:
    """Orchestrate the full daytime lifecycle for a single feature.

    Steps: startup checks -> PID write -> worktree create -> execute ->
    route -> cleanup. Includes an orphan-prevention background task.

    Returns the process exit code (0 on merge success, 1 otherwise).
    """
    _check_cwd()

    plan_path = Path(f"lifecycle/{feature}/plan.md")
    if not plan_path.exists():
        sys.stderr.write(
            f"error: plan.md not found at `lifecycle/{feature}/plan.md`\n"
        )
        return 1

    cwd = Path.cwd()
    pid_path = _pid_path(feature)

    existing_pid = _read_pid(pid_path)
    if existing_pid is not None:
        if _is_alive(existing_pid):
            sys.stderr.write(
                f"error: daytime already running for {feature} "
                f"(PID {existing_pid})\n"
            )
            return 1
        # Stale PID — recover.
        _recover_stale(feature, _worktree_path(feature))
        pid_path.unlink(missing_ok=True)

    _write_pid(pid_path)

    session_id = os.environ.get("LIFECYCLE_SESSION_ID") or (
        f"daytime-{feature}-{int(time.time())}"
    )
    config = build_config(feature, cwd, session_id)
    deferred_dir = cwd / f"lifecycle/{feature}/deferred"

    worktree_info = create_worktree(feature)

    ctx = OutcomeContext(
        batch_result=BatchResult(batch_id=1),
        lock=asyncio.Lock(),
        cb_state=CircuitBreakerState(),
        recovery_attempts_map={feature: 0},
        worktree_paths={feature: worktree_info.path},
        worktree_branches={feature: worktree_info.branch},
        repo_path_map={feature: None},
        integration_worktrees={},
        integration_branches={},
        session_id=session_id,
        backlog_ids={feature: None},
        feature_names=[feature],
        config=config,
    )

    _orphan_task = asyncio.create_task(_orphan_guard(feature, pid_path))

    try:
        result = await execute_feature(
            feature, worktree_info.path, config, deferred_dir=deferred_dir
        )
        await apply_feature_result(
            feature, result, ctx, deferred_dir=deferred_dir
        )
    except Exception as e:
        sys.stderr.write(f"error: daytime pipeline failed: {e}\n")
        return 1
    finally:
        _orphan_task.cancel()
        cleanup_worktree(feature)
        pid_path.unlink(missing_ok=True)

    br = ctx.batch_result
    if feature in br.features_merged:
        print(f"Feature {feature} merged successfully.")
        return 0
    if any(d.get("name") == feature for d in br.features_deferred):
        deferral_file = next(deferred_dir.glob("*.md"), None)
        if deferral_file is not None:
            print(str(deferral_file))
        else:
            print(
                f"Feature {feature} deferred — check "
                f"lifecycle/{feature}/deferred/ for details."
            )
        return 1
    if any(d.get("name") == feature for d in br.features_paused):
        print(
            f"Feature {feature} paused — worktree cleaned; "
            f"check events.log for details."
        )
        return 1
    # failed or unrecognized
    failed = next(
        (d for d in br.features_failed if d.get("name") == feature),
        None,
    )
    if failed is not None and failed.get("error"):
        print(f"Feature {feature} failed: {failed['error']}")
    else:
        print(f"Feature {feature} did not complete successfully.")
    return 1


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    p = argparse.ArgumentParser(
        prog="python3 -m claude.overnight.daytime_pipeline"
    )
    p.add_argument(
        "--feature",
        required=True,
        help="Feature slug to execute (e.g. my-feature)",
    )
    return p


def _run() -> None:
    args = build_parser().parse_args()
    sys.exit(asyncio.run(run_daytime(args.feature)))


if __name__ == "__main__":
    _run()
