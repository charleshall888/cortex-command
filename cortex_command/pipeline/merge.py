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
    """Result of attempting to merge a feature branch.

    ``merge_sha`` carries the integration-branch ``--no-ff`` merge commit
    (the SHA of ``HEAD`` on the base branch in the integration repo,
    captured immediately after a successful merge). It is populated only
    when a merge actually landed and survived the post-merge test gate;
    it is ``None`` on every non-success path, including the inline
    revert-on-test-failure path where ``merge.py`` already undid the
    merge. The captured value is a merge commit (two parents), so a later
    ``git revert -m 1 <merge_sha>`` is valid.
    """

    success: bool
    feature: str
    conflict: bool
    test_result: Optional[TestResult] = None
    error: Optional[str] = None
    classification: Optional[ConflictClassification] = None
    merge_sha: Optional[str] = None


def _repo_root() -> Path:
    """Get the repository root via git rev-parse."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(result.stdout.strip())


def _revert_in_progress(repo: Path) -> bool:
    """Return True iff a half-applied ``git revert`` is in progress in *repo*.

    Resolves ``REVERT_HEAD`` via ``git rev-parse --git-path`` so the check is
    correct for both a plain repo (``.git/REVERT_HEAD``) and a linked worktree
    (``.git/worktrees/<name>/REVERT_HEAD``). A present ``REVERT_HEAD`` marks a
    genuine conflicting revert mid-flight; its absence after a non-zero
    ``git revert`` means the revert was a no-op (the merge was already
    reverted), not a conflict.
    """
    result = subprocess.run(
        ["git", "rev-parse", "--git-path", "REVERT_HEAD"],
        capture_output=True,
        text=True,
        cwd=repo,
    )
    if result.returncode != 0:
        return False
    revert_head = result.stdout.strip()
    if not revert_head:
        return False
    return (Path(repo) / revert_head).exists()


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
        ["sh", "-c", test_command],
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

    # Capture the live integration-branch merge commit (the --no-ff merge
    # commit on the base branch) so a later rollback can revert this exact
    # SHA under the lock even after concurrent features advance HEAD. Only
    # surfaced on the success return below — never on the test-failure revert
    # path, where the merge is undone before returning.
    merge_sha_result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        cwd=repo,
    )
    merge_sha = merge_sha_result.stdout.strip() if merge_sha_result.returncode == 0 else None

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
        merge_sha=merge_sha,
    )


@dataclass
class RevertResult:
    """Result of attempting to revert a specific merge commit by SHA.

    ``success`` is True when ``git revert -m 1 <merge_sha>`` netted out the
    merge cleanly (a revert commit now sits on the branch) OR when the merge
    was *already* reverted before this call ran — in the latter case
    ``already_reverted`` is also True and no new revert commit was created.
    The already-reverted no-op arises on the rework path: ``merge_feature``
    inline-reverts a cycle-1 re-merge on a post-merge test failure (logging
    ``merge_revert_error``), so a subsequent rollback of that same re-merge
    SHA would otherwise attempt a doomed double-revert. ``revert_merge``
    queries branch state and reports this as success rather than escalating.

    On a genuine conflicting revert — typically because a later feature merged
    code that textually depends on the reverted one (the dependent-conflict
    R-edge) — ``revert_merge`` runs ``git revert --abort`` so no half-applied
    revert is left behind, sets ``aborted=True``, and returns
    ``success=False`` so the caller escalates to a blocking deferral. The merge
    genuinely remains on the branch in that case.
    """

    success: bool
    merge_sha: str
    aborted: bool = False
    already_reverted: bool = False
    error: Optional[str] = None


def revert_merge(
    merge_sha: str,
    repo_path: Path | None = None,
    log_path: Path | None = None,
    feature: str | None = None,
) -> RevertResult:
    """Revert a specific merge commit by SHA (position-independent).

    Runs ``git revert -m 1 --no-edit <merge_sha>``. ``-m 1`` keeps the first
    parent (the integration branch the feature was merged *into*), so the
    revert undoes the feature's changes regardless of where ``<merge_sha>``
    sits in history — later merges stacked on top do not move it. This is the
    fail-safe rollback for a non-APPROVED/crashed post-merge review; the
    caller MUST hold ``ctx.lock`` because the integration worktree is a single
    physical checkout shared across concurrently-running features and a
    concurrent ``git revert`` would corrupt the index.

    The revert is captured, not ``check=True``: on a non-zero exit this query
    inspects actual branch state (``.git/REVERT_HEAD``) to tell two outcomes
    apart, because both exit non-zero:

    - **Already reverted** (no ``REVERT_HEAD``, clean tree, git prints
      "nothing to commit"): the target merge was undone before this call —
      e.g. the rework re-merge that ``merge_feature`` already inline-reverted
      on a post-merge test failure. Returns
      ``RevertResult(success=True, already_reverted=True)`` with no abort and
      no escalation; attempting to revert it again would be a doomed
      double-revert.
    - **Genuine conflict** (``REVERT_HEAD`` present, half-applied revert):
      runs ``git revert --abort`` so nothing half-applied remains, then
      returns ``RevertResult(success=False, aborted=True)`` so the caller
      escalates to a blocking deferral.

    Because the caller holds ``ctx.lock``, no concurrent feature can advance
    ``HEAD`` between the revert attempt and the ``REVERT_HEAD`` state query, so
    this is not a TOCTOU race.

    Args:
        merge_sha: The merge commit SHA to revert (a two-parent ``--no-ff``
            merge commit, e.g. ``MergeResult.merge_sha``).
        repo_path: Explicit repository path for git operations. When None
            (default), falls back to ``_repo_root()`` discovery.
        log_path: Path to JSONL event log. When provided, ``merge_reverted``
            / ``merge_revert_error`` events are logged via state.log_event.
        feature: Feature name, recorded on logged events for identification.

    Returns:
        RevertResult describing whether the revert landed, was a no-op because
        the merge was already reverted, was aborted on conflict, or failed for
        another reason.
    """
    repo = repo_path if repo_path is not None else _repo_root()

    def _log(event_dict: dict) -> None:
        if log_path is not None:
            state_mod.log_event(log_path, event_dict)

    revert_result = subprocess.run(
        ["git", "revert", "-m", "1", "--no-edit", merge_sha],
        capture_output=True,
        text=True,
        cwd=repo,
    )

    if revert_result.returncode != 0:
        revert_error = revert_result.stderr.strip() or revert_result.stdout.strip()

        # Distinguish an already-reverted no-op from a genuine conflict by
        # querying real branch state: a conflicting revert leaves a
        # ``REVERT_HEAD`` (a half-applied revert), whereas reverting an
        # already-reverted merge exits non-zero with a clean tree and no
        # ``REVERT_HEAD`` ("nothing to commit"). Querying state here — rather
        # than blindly aborting + escalating — avoids a failed double-revert
        # escalating to a spurious blocking deferral on the rework path.
        # ``git rev-parse --git-path`` resolves REVERT_HEAD's location for both
        # a plain repo (``.git/REVERT_HEAD``) and a linked worktree (under
        # ``.git/worktrees/<name>/``), so the check is worktree-layout-safe.
        if not _revert_in_progress(repo):
            _log({
                "event": "merge_reverted",
                "feature": feature,
                "merge_sha": merge_sha,
                "already_reverted": True,
            })
            return RevertResult(
                success=True,
                merge_sha=merge_sha,
                already_reverted=True,
            )

        # Genuine conflict: abort so no half-applied revert remains in the
        # shared index.
        subprocess.run(
            ["git", "revert", "--abort"],
            capture_output=True,
            text=True,
            cwd=repo,
        )
        _log({
            "event": "merge_revert_error",
            "feature": feature,
            "merge_sha": merge_sha,
            "error": revert_error,
        })
        return RevertResult(
            success=False,
            merge_sha=merge_sha,
            aborted=True,
            error=revert_error,
        )

    _log({"event": "merge_reverted", "feature": feature, "merge_sha": merge_sha})
    return RevertResult(success=True, merge_sha=merge_sha)
