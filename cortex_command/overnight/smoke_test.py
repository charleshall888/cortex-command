"""Smoke test for the overnight batch orchestration system.

Creates a minimal 1-task lifecycle plan, runs run_batch directly, asserts
the feature branch has a new commit, and cleans up in a finally block.

Usage:
    uv run python3 -m claude.overnight.smoke_test
"""

from __future__ import annotations

import asyncio
import datetime
import json
import shutil
import subprocess
import sys
from pathlib import Path

from cortex_command.overnight.orchestrator import BatchConfig, run_batch
from cortex_command.pipeline.worktree import cleanup_worktree, create_worktree

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FEATURE_NAME = "overnight-smoke-test-tmp"
BRANCH_NAME = f"pipeline/{FEATURE_NAME}"
LIFECYCLE_DIR = Path("lifecycle/overnight-smoke-test-tmp")
BATCH_PLAN_PATH = Path("lifecycle/smoke-batch-plan.md")
PIPELINE_EVENTS_PATH = Path("lifecycle/pipeline-events.log")

# Unique ID for this run so the agent always has fresh content to write.
RUN_ID = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")

# ---------------------------------------------------------------------------
# Setup helpers
# ---------------------------------------------------------------------------

BATCH_PLAN_CONTENT = """\
# Master Plan: smoke-test

## Features

| Priority | Name | Complexity | Tasks | Summary |
|----------|------|------------|-------|---------|
| 1 | overnight-smoke-test-tmp | simple | 1 | smoke test |

## Configuration

| Key | Value |
|-----|-------|
"""


def _make_feature_plan(run_id: str) -> str:
    """Build the feature plan with a unique run ID embedded in the task content."""
    return f"""\
# Plan: overnight-smoke-test-tmp

## Overview

Minimal smoke test feature to verify the overnight batch orchestration system.

## Tasks

### Task 1: Write smoke test result

- **Files**: lifecycle/overnight-smoke-test-tmp/result.txt
- **Depends on**: None
- **Complexity**: simple
- **Status**: [ ]

Write the file `lifecycle/overnight-smoke-test-tmp/result.txt` with exactly this
content (one line):

    smoke-test-ok-{run_id}

The file may already exist from a previous run with stale content — overwrite it
unconditionally. Commit the result with message "Add smoke test result".
"""


def _remove_tracked_lifecycle_dir() -> None:
    """Ensure LIFECYCLE_DIR is absent from the git index and HEAD.

    Uses --ignore-unmatch so it is safe to call when nothing is tracked.
    Also handles the edge case where a previous git rm staged the deletion but
    the commit never ran (leaving the index ahead of HEAD).
    """
    subprocess.run(
        ["git", "rm", "-r", "--force", "--ignore-unmatch", str(LIFECYCLE_DIR)],
        capture_output=True,
        check=False,
    )
    result = subprocess.run(
        ["git", "commit", "-m", "chore: remove smoke test artifacts"],
        capture_output=True,
        text=True,
        check=False,
    )
    # These messages mean nothing was tracked — both are normal/expected.
    benign = ("nothing to commit", "no changes added to commit")
    if result.returncode != 0 and not any(msg in (result.stdout + result.stderr) for msg in benign):
        print(f"[setup] WARN: cleanup commit failed: {result.stderr.strip() or result.stdout.strip()}")


def _setup_artifacts() -> None:
    """Create the lifecycle directory, feature plan, and batch master plan."""
    # Remove any stale artifacts from a previous run that were merged to main,
    # so the new worktree starts from a clean branch.
    _remove_tracked_lifecycle_dir()

    LIFECYCLE_DIR.mkdir(parents=True, exist_ok=True)

    plan_path = LIFECYCLE_DIR / "plan.md"
    plan_path.write_text(_make_feature_plan(RUN_ID), encoding="utf-8")

    BATCH_PLAN_PATH.write_text(BATCH_PLAN_CONTENT, encoding="utf-8")


def _cleanup_artifacts() -> None:
    """Remove all artifacts created by the smoke test."""
    cleanup_worktree(FEATURE_NAME)

    subprocess.run(
        ["git", "branch", "-D", BRANCH_NAME],
        capture_output=True,
        text=True,
        check=False,
    )

    # Remove lifecycle dir from main (tracked after a merge) or locally.
    _remove_tracked_lifecycle_dir()
    shutil.rmtree(str(LIFECYCLE_DIR), ignore_errors=True)

    BATCH_PLAN_PATH.unlink(missing_ok=True)

    BATCH_RESULTS_PATH.unlink(missing_ok=True)


BATCH_RESULTS_PATH = Path("lifecycle/batch-99-results.json")


def _check_feature_merged() -> bool:
    """Return True if the feature was merged in batch results."""
    if not BATCH_RESULTS_PATH.exists():
        return False
    try:
        data = json.loads(BATCH_RESULTS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    return FEATURE_NAME in data.get("features_merged", [])


def _get_repo_root() -> Path:
    """Return the repository root path."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(result.stdout.strip())


def _check_auth_pre_flight(repo: Path) -> None:
    """Print auth configuration status before the run (warning only, not a failure).

    An empty-string apiKeyHelper overrides the global API key and lets Claude
    Code fall through to subscription auth.
    """
    if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        print("[auth] OK: CLAUDE_CODE_OAUTH_TOKEN is set — OAuth token mode")
        return
    local_settings = repo / ".claude" / "settings.local.json"
    if not local_settings.exists():
        print("[auth] WARN: .claude/settings.local.json not found — subscription auth not configured")
        return
    try:
        data = json.loads(local_settings.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[auth] WARN: could not parse settings.local.json: {exc}")
        return
    key_helper = data.get("apiKeyHelper")
    if key_helper == "":
        print("[auth] OK: apiKeyHelper is empty string — subscription mode (API key override disabled)")
    elif key_helper is not None:
        print("[auth] OK: apiKeyHelper is set — API key provided via helper script")
    else:
        print("[auth] WARN: apiKeyHelper not in settings.local.json — global API key may be used instead of subscription")


def _check_worktree_auth(repo: Path) -> bool:
    """Verify settings.local.json was copied to the feature worktree.

    Returns True if the check passes (including when there is nothing to copy).
    Returns False if the source exists but the copy is missing.
    """
    source = repo / ".claude" / "settings.local.json"
    if not source.exists():
        return True  # nothing to copy — not a failure
    dest = repo / ".claude" / "worktrees" / FEATURE_NAME / ".claude" / "settings.local.json"
    if dest.exists():
        print("[auth] OK: settings.local.json was copied to worktree")
        return True
    print(f"[auth] FAIL: settings.local.json exists in repo but was NOT copied to worktree ({dest})")
    return False


def _print_diagnostic_events() -> None:
    """Print task_output and task_git_state events for the smoke test feature."""
    if not PIPELINE_EVENTS_PATH.exists():
        print(f"[diagnostic] {PIPELINE_EVENTS_PATH} does not exist")
        return

    lines = PIPELINE_EVENTS_PATH.read_text(encoding="utf-8").splitlines()
    relevant_events = ["task_output", "task_git_state"]

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue

        if (
            record.get("event") in relevant_events
            and record.get("feature") == FEATURE_NAME
        ):
            print(json.dumps(record, indent=2))


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def _run_smoke_test() -> None:
    """Run the smoke test and exit with appropriate status code."""
    _setup_artifacts()

    repo = _get_repo_root()
    _check_auth_pre_flight(repo)

    try:
        # Create the worktree now so we can verify auth before spending pipeline
        # budget. run_batch will reuse the existing worktree (idempotent).
        create_worktree(FEATURE_NAME, base_branch="main")
        auth_ok = _check_worktree_auth(repo)
        if not auth_ok:
            if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
                print("WARN: settings.local.json was not copied to worktree, but CLAUDE_CODE_OAUTH_TOKEN is set — OAuth auth propagates via env vars, continuing")
            else:
                print("FAIL: settings.local.json was not copied to worktree — subscription auth misconfigured")
                sys.exit(1)

        config = BatchConfig(
            batch_id=99,
            plan_path=BATCH_PLAN_PATH,
            base_branch="main",
        )

        await run_batch(config)

        if not _check_feature_merged():
            print("FAIL: feature was not merged — check batch results and logs")
            print()
            print("--- Diagnostic events from pipeline-events.log ---")
            _print_diagnostic_events()
            if BATCH_RESULTS_PATH.exists():
                print()
                print("--- batch-99-results.json ---")
                print(BATCH_RESULTS_PATH.read_text(encoding="utf-8"))
            sys.exit(1)

        # Soft assertions: verify worker wrote a valid exit report.
        # These never call sys.exit(1) — all failures increment warnings only.
        warnings = 0
        exit_report_path = LIFECYCLE_DIR / "exit-reports" / "1.json"
        if not exit_report_path.is_file():
            print(f"WARN: exit report not found: {exit_report_path}")
            warnings += 1
        else:
            try:
                report_data = json.loads(
                    exit_report_path.read_text(encoding="utf-8")
                )
            except (json.JSONDecodeError, OSError) as exc:
                print(f"WARN: exit report is not valid JSON: {exc}")
                warnings += 1
                report_data = None
            if report_data is not None:
                action = report_data.get("action") if isinstance(report_data, dict) else None
                if action not in {"complete", "question"}:
                    print(f"WARN: exit report action invalid: {action!r}")
                    warnings += 1
                else:
                    print(f'OK: exit report action="{action}"')

        print(f"PASS ({warnings} warnings)")
        sys.exit(0)

    finally:
        _cleanup_artifacts()


def main() -> None:
    asyncio.run(_run_smoke_test())


if __name__ == "__main__":
    main()
