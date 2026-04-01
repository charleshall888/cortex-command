"""Merge orchestration for completed pipeline features.

Handles sequential merge of completed features to the base branch with
per-merge testing, automatic revert on test failure, and merge conflict
detection. Designed to be conservative: conflicts and test failures
cause pauses rather than automatic resolution.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import state as state_mod
from .conflict import classify_conflict, ConflictClassification


@dataclass
class TestResult:
    """Result of running a test command."""

    passed: bool
    output: str
    return_code: int


@dataclass
class MergeResult:
    """Result of attempting to merge a feature branch."""

    success: bool
    feature: str
    conflict: bool
    test_result: Optional[TestResult] = None
    error: Optional[str] = None
    classification: Optional[ConflictClassification] = None


def _repo_root() -> Path:
    """Get the repository root via git rev-parse."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(result.stdout.strip())


def run_tests(test_command: str = None, cwd: str = None) -> TestResult:
    """Run the test command and return the result.

    Args:
        test_command: Shell command to run. If None or empty, returns
            a passing TestResult (no tests configured).
        cwd: Working directory for the test command. Defaults to the
            repository root.

    Returns:
        TestResult with pass/fail status, captured output, and return code.
    """
    if not test_command or str(test_command).lower() == "none":
        return TestResult(passed=True, output="", return_code=0)

    if cwd is None:
        cwd = str(_repo_root())

    result = subprocess.run(
        test_command,
        shell=True,
        capture_output=True,
        text=True,
        cwd=cwd,
    )

    combined_output = result.stdout
    if result.stderr:
        combined_output += "\n" + result.stderr if combined_output else result.stderr

    return TestResult(
        passed=result.returncode == 0,
        output=combined_output,
        return_code=result.returncode,
    )


def _check_ci_status(branch: str) -> str:
    """Query GitHub CI status for a branch via the gh CLI.

    Runs ``gh run list --branch <branch> --limit 1 --json status,conclusion``
    and interprets the result according to the following rules:

    - ``"pass"``    — most recent run has ``conclusion: success``; safe to merge.
    - ``"pending"`` — most recent run has ``status`` of ``in_progress`` or
                      ``queued``; merge should be deferred.
    - ``"failing"`` — most recent run has a non-success conclusion
                      (``failure``, ``cancelled``, ``timed_out``,
                      ``action_required``); merge should be deferred.
    - ``"skipped"`` — no CI runs exist for the branch, ``gh`` is not installed,
                      exited non-zero, or returned malformed JSON; caller
                      should warn and proceed.

    Args:
        branch: Fully-qualified branch name (e.g. ``pipeline/my-feature``).

    Returns:
        One of ``"pass"``, ``"pending"``, ``"failing"``, or ``"skipped"``.
    """
    try:
        result = subprocess.run(
            ["gh", "run", "list", "--branch", branch, "--limit", "1", "--json", "status,conclusion"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        # gh is not installed
        return "skipped"

    if result.returncode != 0:
        return "skipped"

    try:
        runs = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        return "skipped"

    if not isinstance(runs, list) or len(runs) == 0:
        return "skipped"

    run = runs[0]
    if not isinstance(run, dict):
        return "skipped"

    status = run.get("status", "")
    conclusion = run.get("conclusion", "")

    if status in ("in_progress", "queued"):
        return "pending"

    if conclusion == "success":
        return "pass"

    if conclusion in ("failure", "cancelled", "timed_out", "action_required"):
        return "failing"

    # Unknown status/conclusion (e.g. still queued with empty conclusion)
    if status in ("in_progress", "queued", "waiting", "requested", "pending"):
        return "pending"

    # Fallback: treat anything unrecognised as skipped so we don't block merges
    # on unexpected gh output formats.
    return "skipped"


def merge_feature(
    feature: str,
    base_branch: str = "main",
    test_command: str = None,
    log_path: Path = None,
    ci_check: bool = True,
    branch: str | None = None,
    repo_path: Path | None = None,
) -> MergeResult:
    """Merge a completed feature branch into the base branch.

    Performs a no-fast-forward merge of the feature branch into the base
    branch. If a test command is provided, runs it after merging. On test
    failure, the merge commit is reverted. On merge conflict, the merge
    is aborted without attempting resolution.

    Before merging, queries GitHub CI status via ``gh run list``. If the
    most recent CI run is in-progress/queued the merge is deferred with
    ``error="ci_pending"``. If the run has a non-success conclusion the
    merge is deferred with ``error="ci_failing"``. If ``gh`` is unavailable
    or returns no data the check is skipped and the merge proceeds.

    Args:
        feature: Feature name.
        base_branch: Branch to merge into (default: main).
        test_command: Shell command to run after merge. If None, no tests
            are run.
        log_path: Path to JSONL event log. If provided, merge events are
            logged via state.log_event.
        ci_check: When True (default) query CI status before merging.
            Set to False to skip the CI gate entirely.
        branch: Fully-qualified branch name to merge (e.g.
            ``pipeline/my-feature-2``). When omitted, falls back to
            ``pipeline/{feature}``.
        repo_path: Explicit repository path for git operations. When
            None (default), falls back to ``_repo_root()`` discovery.

    Returns:
        MergeResult indicating success/failure with details.
    """
    repo = repo_path if repo_path is not None else _repo_root()
    branch = branch if branch is not None else f"pipeline/{feature}"

    def _log(event_dict: dict) -> None:
        if log_path is not None:
            state_mod.log_event(log_path, event_dict)

    _log({"event": "merge_start", "feature": feature, "branch": branch})

    # --- CI status gate ---
    if ci_check:
        _log({"event": "ci_check_start", "feature": feature, "branch": branch})
        ci_status = _check_ci_status(branch)

        if ci_status == "pending":
            _log({"event": "ci_check_pending", "feature": feature, "branch": branch})
            return MergeResult(
                success=False,
                feature=feature,
                conflict=False,
                error="ci_pending",
            )

        if ci_status == "failing":
            _log({"event": "ci_check_failed", "feature": feature, "branch": branch})
            return MergeResult(
                success=False,
                feature=feature,
                conflict=False,
                error="ci_failing",
            )

        if ci_status == "skipped":
            _log({
                "event": "ci_check_skipped",
                "feature": feature,
                "branch": branch,
                "reason": "gh unavailable or no CI runs found",
            })
            # warn-and-proceed: fall through to merge

        else:
            # ci_status == "pass"
            _log({"event": "ci_check_passed", "feature": feature, "branch": branch})

    # Checkout base branch
    checkout_result = subprocess.run(
        ["git", "checkout", base_branch],
        capture_output=True,
        text=True,
        cwd=repo,
    )
    if checkout_result.returncode != 0:
        error_msg = f"Failed to checkout {base_branch}: {checkout_result.stderr.strip()}"
        _log({"event": "merge_error", "feature": feature, "error": error_msg})
        return MergeResult(
            success=False,
            feature=feature,
            conflict=False,
            error=error_msg,
        )

    # Attempt merge (no fast-forward to preserve history)
    merge_result = subprocess.run(
        ["git", "merge", "--no-ff", branch, "-m", f"Merge {branch} into {base_branch}"],
        capture_output=True,
        text=True,
        cwd=repo,
    )

    if merge_result.returncode != 0:
        # Merge failed — likely a conflict
        error_output = merge_result.stderr.strip() or merge_result.stdout.strip()

        # classify_conflict handles git merge --abort internally
        classification = classify_conflict(repo)

        _log({
            "event": "merge_conflict_classified",
            "feature": feature,
            "conflicted_files": classification.conflicted_files,
            "conflict_summary": classification.conflict_summary,
        })
        return MergeResult(
            success=False,
            feature=feature,
            conflict=True,
            error=error_output,
            classification=classification,
        )

    _log({"event": "merge_complete", "feature": feature})

    # Run tests after successful merge
    test_result = run_tests(test_command, cwd=str(repo))

    if not test_result.passed:
        _log({
            "event": "merge_test_failure",
            "feature": feature,
            "return_code": test_result.return_code,
        })

        # Revert the merge commit (-m 1 required for merge commits)
        revert_result = subprocess.run(
            ["git", "revert", "-m", "1", "--no-edit", "HEAD"],
            capture_output=True,
            text=True,
            cwd=repo,
        )

        if revert_result.returncode != 0:
            revert_error = revert_result.stderr.strip()
            _log({
                "event": "merge_revert_error",
                "feature": feature,
                "error": revert_error,
            })

        _log({"event": "merge_reverted", "feature": feature})
        return MergeResult(
            success=False,
            feature=feature,
            conflict=False,
            test_result=test_result,
            error=f"Tests failed (exit code {test_result.return_code})",
        )

    _log({"event": "merge_success", "feature": feature})
    return MergeResult(
        success=True,
        feature=feature,
        conflict=False,
        test_result=test_result,
    )


def revert_merge(feature: str, base_branch: str = "main", repo_path: Path | None = None) -> None:
    """Revert the most recent merge commit on the base branch.

    This is a fallback for reverting a merge outside the normal
    merge_feature flow. Checks out the base branch and reverts HEAD,
    which is assumed to be a merge commit (requires -m 1).

    Args:
        feature: Feature name (used for logging/identification only).
        base_branch: Branch to revert on (default: main).
        repo_path: Explicit repository path for git operations. When
            None (default), falls back to ``_repo_root()`` discovery.

    Raises:
        subprocess.CalledProcessError: If checkout or revert fails.
    """
    repo = repo_path if repo_path is not None else _repo_root()

    subprocess.run(
        ["git", "checkout", base_branch],
        capture_output=True,
        text=True,
        check=True,
        cwd=repo,
    )

    subprocess.run(
        ["git", "revert", "-m", "1", "--no-edit", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
        cwd=repo,
    )
