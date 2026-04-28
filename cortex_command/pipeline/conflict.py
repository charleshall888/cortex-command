"""Merge conflict classification and repair agent dispatch for pipeline features.

Inspects git's unmerged file list and scans for conflict markers after a
failed merge. Always aborts the in-progress merge via try/finally before
returning, so callers do not need to call ``git merge --abort`` themselves.

Also provides ``dispatch_repair_agent()`` for dispatching a Claude agent to
resolve complex merge conflicts on an isolated repair worktree.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from cortex_command.pipeline.merge import TestResult
    from cortex_command.overnight.orchestrator import BatchConfig

from cortex_command.pipeline.dispatch import dispatch_task
from cortex_command.pipeline.merge_recovery import write_recovery_log_entry
from cortex_command.pipeline.state import log_event as pipeline_log_event

_REPAIR_TEMPLATE = Path(__file__).resolve().parents[1] / "overnight/prompts/repair-agent.md"


@dataclass
class ConflictClassification:
    """Classification of a merge conflict state in the working tree."""

    conflicted_files: list[str]
    conflict_summary: str


@dataclass
class RepairResult:
    """Result of a repair agent dispatch attempt.

    Returned by ``dispatch_repair_agent()`` and consumed by
    ``execute_feature()`` in batch_runner.py.
    """

    success: bool
    feature: str
    strategy: str = "repair_agent"
    repair_branch: Optional[str] = None
    resolved_files: list[str] = field(default_factory=list)
    resolution_rationale: str = ""
    test_result: Optional["TestResult"] = None
    error: Optional[str] = None
    model_used: Optional[str] = None
    cost_usd: Optional[float] = None


@dataclass
class ConflictResolutionResult:
    """Result of a trivial fast-path conflict resolution attempt.

    Returned by ``resolve_trivial_conflict()`` and consumed by
    ``execute_feature()`` in batch_runner.py.
    """

    success: bool
    strategy: str  # always "trivial_fast_path"
    resolved_files: list[str]
    repair_branch: Optional[str]
    error: Optional[str]


def _create_repair_worktree(
    feature: str,
    round_number: int,
    base_branch: str,
    feature_branch: str,
    repo: Path,
) -> tuple[Path, list[str]]:
    """Create a repair worktree and merge the feature branch into it.

    Creates ``repair/{feature}-{round_number}`` off ``base_branch`` using
    ``git worktree add`` in ``$TMPDIR``, then merges ``feature_branch``
    (expected to conflict).  Returns the worktree path and a fresh list of
    files containing ``<<<<<<<`` conflict markers.

    Args:
        feature: Feature name (used to build branch/path names).
        round_number: Batch round number (used to build branch/path names).
        base_branch: Branch to create the repair branch off of.
        feature_branch: Full branch name to merge (e.g. ``pipeline/{feature}``).
        repo: Path to the repository root.

    Returns:
        ``(worktree_path, actual_conflicted_files)`` where
        ``actual_conflicted_files`` is a list of repo-relative paths
        containing ``<<<<<<<`` markers after the merge.

    Raises:
        ValueError: If ``feature_branch`` does not exist or worktree
            creation fails.
    """
    tmpdir = Path(os.environ.get("TMPDIR", "/tmp"))
    repair_branch = f"repair/{feature}-{round_number}"
    worktree_path = tmpdir / f"repair-{feature}-{round_number}"

    # Guard: verify the source branch exists before attempting the merge.
    verify = subprocess.run(
        ["git", "rev-parse", "--verify", feature_branch],
        cwd=repo,
        capture_output=True,
    )
    if verify.returncode != 0:
        raise ValueError(f"feature_branch_missing: {feature_branch}")

    # Create the worktree + branch.
    add_result = subprocess.run(
        ["git", "worktree", "add", "-b", repair_branch, str(worktree_path), base_branch],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    if add_result.returncode != 0:
        raise ValueError(
            f"worktree_creation_failed: {add_result.stderr.strip()}"
        )

    # Merge the feature branch (expected to conflict — do not check returncode).
    subprocess.run(
        ["git", "merge", "--no-ff", feature_branch],
        cwd=worktree_path,
        capture_output=True,
    )

    # Fresh scan: list unmerged files and check for conflict markers.
    diff_result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=U"],
        cwd=worktree_path,
        capture_output=True,
        text=True,
    )
    unmerged_paths = [
        line.strip()
        for line in diff_result.stdout.splitlines()
        if line.strip()
    ]

    actual_conflicted_files: list[str] = []
    for rel_path in unmerged_paths:
        file_path = worktree_path / rel_path
        try:
            content = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if "<<<<<<<" in content:
            actual_conflicted_files.append(rel_path)

    return worktree_path, actual_conflicted_files


def _cleanup_repair_worktree(
    worktree_path: Path,
    repair_branch: str,
    repo: Path,
    *,
    delete_branch: bool,
) -> None:
    """Remove the repair worktree and optionally delete the repair branch.

    Args:
        worktree_path: Path to the repair worktree directory.
        repair_branch: Name of the repair branch (e.g. ``repair/feature-1``).
        repo: Path to the repository root.
        delete_branch: If ``True``, also delete the repair branch.
    """
    subprocess.run(
        ["git", "worktree", "remove", "--force", str(worktree_path)],
        cwd=repo,
        capture_output=True,
    )
    if delete_branch:
        subprocess.run(
            ["git", "branch", "-d", repair_branch],
            cwd=repo,
            capture_output=True,
        )


async def dispatch_repair_agent(
    feature: str,
    conflict_classification: ConflictClassification,
    base_branch: str,
    spec_path: Optional[str],
    config: "BatchConfig",
    round_number: int,
    repo_root: Optional[Path] = None,
) -> RepairResult:
    """Orchestrate the full repair lifecycle for a complex merge conflict.

    Creates a repair worktree, dispatches a Sonnet agent, reads the exit
    report, verifies no conflict markers remain, optionally escalates to
    Opus on agent quality failure, runs the test gate, and returns a
    RepairResult.

    Escalates to Opus ONLY on agent quality failure (unresolved markers or
    deferral question after a successful SDK dispatch).  Does NOT escalate
    on SDK exceptions or test failures.

    Args:
        feature: Feature name.
        conflict_classification: Classification from the upstream event (used
            for logging context only — a fresh scan is performed after re-merge).
        base_branch: Branch to create the repair branch off of.
        spec_path: Path to the feature spec file (passed to repair agent prompt).
        config: Batch configuration (provides test_command, pipeline_events_path, etc.).
        round_number: Batch round number (used to name the repair branch).
        repo_root: Path to the repository root. Forwarded to ``dispatch_task``
            so repair agents can commit directly to the base branch. Defaults
            to ``None`` (backward-compatible).

    Returns:
        RepairResult with success status, model used, resolved files, and cost.
    """
    from cortex_command.pipeline.merge import run_tests  # lazy: avoid circular import
    from cortex_command.overnight.events import (  # lazy: avoid circular import via overnight.__init__
        REPAIR_AGENT_START,
        REPAIR_AGENT_COMPLETE,
        REPAIR_AGENT_ESCALATED,
        REPAIR_AGENT_FAILED,
    )

    repo = Path.cwd()
    repair_branch = f"repair/{feature}-{round_number}"
    feature_branch = f"pipeline/{feature}"
    costs: list[float] = []

    pipeline_log_event(config.pipeline_events_path, {
        "event": REPAIR_AGENT_START,
        "feature": feature,
        "conflicted_files": conflict_classification.conflicted_files,
        "repair_branch": repair_branch,
        "model": "sonnet",
    })

    # Create repair worktree and merge feature branch.
    try:
        worktree_path, actual_conflicted_files = _create_repair_worktree(
            feature, round_number, base_branch, feature_branch, repo
        )
    except ValueError as exc:
        error = str(exc)
        pipeline_log_event(config.pipeline_events_path, {
            "event": REPAIR_AGENT_FAILED,
            "feature": feature,
            "error": error,
            "repair_branch": repair_branch,
        })
        write_recovery_log_entry(
            feature=feature,
            recovery_type="merge_conflict",
            outcome="paused",
            what_was_tried="(setup failed before agent dispatch)",
            result=error,
        )
        return RepairResult(success=False, feature=feature, error=error)

    # Render prompt template.
    try:
        template = _REPAIR_TEMPLATE.read_text(encoding="utf-8")
    except OSError as exc:
        _cleanup_repair_worktree(worktree_path, repair_branch, repo, delete_branch=True)
        error = f"prompt_template_missing: {exc}"
        pipeline_log_event(config.pipeline_events_path, {
            "event": REPAIR_AGENT_FAILED,
            "feature": feature,
            "error": error,
            "repair_branch": repair_branch,
        })
        write_recovery_log_entry(
            feature=feature,
            recovery_type="merge_conflict",
            outcome="paused",
            what_was_tried="(setup failed: prompt template missing)",
            result=error,
        )
        return RepairResult(success=False, feature=feature, error=error)

    prompt = (
        template
        .replace("{feature}", feature)
        .replace("{spec_path}", spec_path or "")
        .replace("{conflicted_files}", ", ".join(actual_conflicted_files))
        .replace("{repair_branch}", repair_branch)
        .replace("{base_branch}", base_branch)
        .replace("{feature_branch}", feature_branch)
    )

    exit_report_path = (
        worktree_path / "lifecycle" / feature / "exit-reports" / "repair.json"
    )

    def _read_exit_report() -> Optional[dict]:
        try:
            return json.loads(exit_report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def _has_remaining_markers() -> bool:
        for rel_path in actual_conflicted_files:
            try:
                content = (worktree_path / rel_path).read_text(encoding="utf-8")
                if "<<<<<<<" in content:
                    return True
            except (OSError, UnicodeDecodeError):
                pass
        return False

    async def _run_dispatch(model: str) -> tuple[object, Optional[dict], bool]:
        """Dispatch to model. Returns (result, exit_report, is_sdk_exception)."""
        # Remove stale exit report before dispatch.
        try:
            exit_report_path.unlink(missing_ok=True)
        except OSError:
            pass

        result = await dispatch_task(
            feature=feature,
            task=prompt,
            worktree_path=worktree_path,
            complexity="simple",
            system_prompt="",
            log_path=config.pipeline_events_path,
            model_override=model,
            repo_root=repo_root,
            skill="conflict-repair",
        )
        if result.cost_usd is not None:
            costs.append(result.cost_usd)

        if not result.success:
            return result, None, True  # SDK exception

        report = _read_exit_report()
        return result, report, False

    def _is_agent_quality_failure(report: Optional[dict]) -> bool:
        """True if the agent produced a quality failure (missing report, deferral, or remaining markers)."""
        if report is None:
            return True
        if report.get("action") == "question":
            return True
        if _has_remaining_markers():
            return True
        return False

    # --- Sonnet attempt ---
    sonnet_result, sonnet_report, sonnet_sdk_exc = await _run_dispatch("sonnet")

    if sonnet_sdk_exc:
        error = sonnet_result.error_detail or "sonnet dispatch failed"
        _cleanup_repair_worktree(worktree_path, repair_branch, repo, delete_branch=True)
        pipeline_log_event(config.pipeline_events_path, {
            "event": REPAIR_AGENT_FAILED,
            "feature": feature,
            "error": error,
            "repair_branch": repair_branch,
        })
        total_cost = sum(costs) if costs else None
        write_recovery_log_entry(
            feature=feature,
            recovery_type="merge_conflict",
            outcome="paused",
            what_was_tried="(SDK exception during Sonnet dispatch)",
            result=error,
        )
        return RepairResult(success=False, feature=feature, error=error, cost_usd=total_cost)

    if _is_agent_quality_failure(sonnet_report):
        # --- Opus escalation ---
        pipeline_log_event(config.pipeline_events_path, {
            "event": REPAIR_AGENT_ESCALATED,
            "feature": feature,
            "from_model": "sonnet",
            "to_model": "opus",
        })

        opus_result, opus_report, opus_sdk_exc = await _run_dispatch("opus")
        model_used = "opus"
        total_cost = sum(costs) if costs else None

        if opus_sdk_exc:
            error = opus_result.error_detail or "opus dispatch failed"
            _cleanup_repair_worktree(worktree_path, repair_branch, repo, delete_branch=True)
            pipeline_log_event(config.pipeline_events_path, {
                "event": REPAIR_AGENT_FAILED,
                "feature": feature,
                "error": error,
                "repair_branch": repair_branch,
            })
            write_recovery_log_entry(
                feature=feature,
                recovery_type="merge_conflict",
                outcome="paused",
                what_was_tried="(SDK exception during Opus dispatch after Sonnet quality failure)",
                result=error,
            )
            return RepairResult(
                success=False, feature=feature, error=error,
                model_used=model_used, cost_usd=total_cost,
            )

        if _is_agent_quality_failure(opus_report):
            if opus_report and opus_report.get("action") == "question":
                error = f"deferral: {opus_report.get('question', '')}"
            else:
                error = "agent_quality_failure: markers remain after Opus"
            _cleanup_repair_worktree(worktree_path, repair_branch, repo, delete_branch=True)
            pipeline_log_event(config.pipeline_events_path, {
                "event": REPAIR_AGENT_FAILED,
                "feature": feature,
                "error": error,
                "repair_branch": repair_branch,
            })
            _rationale = json.dumps((opus_report or {}).get("rationale", {}))
            write_recovery_log_entry(
                feature=feature,
                recovery_type="merge_conflict",
                outcome="paused",
                what_was_tried=_rationale if _rationale != "{}" else "(no rationale in exit report)",
                result=error,
            )
            return RepairResult(
                success=False, feature=feature, error=error,
                model_used=model_used, cost_usd=total_cost,
            )

        final_report = opus_report
    else:
        model_used = "sonnet"
        final_report = sonnet_report
        total_cost = sum(costs) if costs else None

    # --- Clean resolution: run test gate ---
    resolved_files = (final_report or {}).get("resolved_files", [])
    resolution_rationale = json.dumps((final_report or {}).get("rationale", {}))

    test_result = await asyncio.to_thread(
        run_tests, config.test_command, cwd=str(worktree_path)
    )

    _rationale_display = resolution_rationale if resolution_rationale != "{}" else "(no rationale in exit report)"

    if not test_result.passed:
        error = f"test_failure: {test_result.output}"
        _cleanup_repair_worktree(worktree_path, repair_branch, repo, delete_branch=True)
        pipeline_log_event(config.pipeline_events_path, {
            "event": REPAIR_AGENT_FAILED,
            "feature": feature,
            "error": error,
            "repair_branch": repair_branch,
        })
        write_recovery_log_entry(
            feature=feature,
            recovery_type="merge_conflict",
            outcome="failed",
            what_was_tried=_rationale_display,
            result=test_result.output[:300],
        )
        return RepairResult(
            success=False,
            feature=feature,
            error=error,
            model_used=model_used,
            resolved_files=resolved_files,
            resolution_rationale=resolution_rationale,
            test_result=test_result,
            cost_usd=total_cost,
        )

    # --- Success: remove worktree, leave repair branch for caller to ff-merge ---
    _cleanup_repair_worktree(worktree_path, repair_branch, repo, delete_branch=False)
    pipeline_log_event(config.pipeline_events_path, {
        "event": REPAIR_AGENT_COMPLETE,
        "feature": feature,
        "model_used": model_used,
        "resolved_files": resolved_files,
        "cost_usd": total_cost,
    })
    write_recovery_log_entry(
        feature=feature,
        recovery_type="merge_conflict",
        outcome="success",
        what_was_tried=_rationale_display,
        result=f"resolved: {', '.join(resolved_files)}" if resolved_files else "conflict resolved (no files listed)",
    )
    return RepairResult(
        success=True,
        feature=feature,
        repair_branch=repair_branch,
        resolved_files=resolved_files,
        resolution_rationale=resolution_rationale,
        test_result=test_result,
        model_used=model_used,
        cost_usd=total_cost,
    )


async def resolve_trivial_conflict(
    feature: str,
    branch: str,
    base_branch: str,
    conflicted_files: list[str],
    config: "BatchConfig",
    round_number: int,
) -> ConflictResolutionResult:
    """Resolve a trivial merge conflict using the ``--theirs`` strategy.

    Creates a repair worktree, applies ``git checkout --theirs`` for every
    conflicted file, runs ``git merge --continue``, then runs the test gate.
    On success the repair branch is left intact for the caller to ff-merge.
    On any failure the branch and worktree are cleaned up.

    ``actual_conflicted_files`` from the fresh re-merge is used instead of
    the ``conflicted_files`` parameter because the base branch may have
    advanced since the conflict was originally classified.

    Args:
        feature: Feature name.
        branch: Full pipeline branch name (e.g. ``pipeline/{feature}``).
        base_branch: Branch to create the repair branch off of.
        conflicted_files: Stored conflicted files from the classified event
            (used only as a fallback — fresh scan takes precedence).
        config: Batch configuration (provides ``test_command``).
        round_number: Batch round number (used to name the repair branch).

    Returns:
        ConflictResolutionResult with success status, resolved files, and
        repair branch name on success, or error string on failure.
    """
    from cortex_command.pipeline.merge import run_tests  # lazy: avoid circular import

    repo = Path.cwd()
    repair_branch = f"repair/{feature}-{round_number}"

    # Pre-clean stale repair branch (may exist from a prior interrupted run).
    subprocess.run(
        ["git", "branch", "-d", repair_branch],
        cwd=repo,
        capture_output=True,
    )

    # Create repair worktree and initiate the (expected-to-conflict) merge.
    try:
        worktree_path, actual_conflicted_files = _create_repair_worktree(
            feature, round_number, base_branch, branch, repo
        )
    except ValueError as exc:
        write_recovery_log_entry(
            feature=feature,
            recovery_type="trivial_conflict",
            outcome="paused",
            what_was_tried="(setup failed before trivial resolution)",
            result=str(exc),
        )
        return ConflictResolutionResult(
            success=False,
            strategy="trivial_fast_path",
            resolved_files=[],
            repair_branch=None,
            error=str(exc),
        )

    # Apply --theirs for each conflicted file.
    for rel_path in actual_conflicted_files:
        checkout_result = subprocess.run(
            ["git", "checkout", "--theirs", rel_path],
            cwd=worktree_path,
            capture_output=True,
            text=True,
        )
        if checkout_result.returncode != 0:
            _cleanup_repair_worktree(worktree_path, repair_branch, repo, delete_branch=True)
            error = f"checkout_theirs_failed: {checkout_result.stderr.strip()}"
            write_recovery_log_entry(
                feature=feature,
                recovery_type="trivial_conflict",
                outcome="failed",
                what_was_tried="git checkout --theirs strategy",
                result=error,
            )
            return ConflictResolutionResult(
                success=False,
                strategy="trivial_fast_path",
                resolved_files=[],
                repair_branch=None,
                error=error,
            )
        add_result = subprocess.run(
            ["git", "add", rel_path],
            cwd=worktree_path,
            capture_output=True,
            text=True,
        )
        if add_result.returncode != 0:
            _cleanup_repair_worktree(worktree_path, repair_branch, repo, delete_branch=True)
            error = f"git_add_failed: {add_result.stderr.strip()}"
            write_recovery_log_entry(
                feature=feature,
                recovery_type="trivial_conflict",
                outcome="failed",
                what_was_tried="git checkout --theirs strategy",
                result=error,
            )
            return ConflictResolutionResult(
                success=False,
                strategy="trivial_fast_path",
                resolved_files=[],
                repair_branch=None,
                error=error,
            )

    # Complete the merge.
    continue_result = subprocess.run(
        ["git", "merge", "--continue", "--no-edit"],
        cwd=worktree_path,
        capture_output=True,
        text=True,
    )
    if continue_result.returncode != 0:
        _cleanup_repair_worktree(worktree_path, repair_branch, repo, delete_branch=True)
        error = f"merge_continue_failed: {continue_result.stderr.strip()}"
        write_recovery_log_entry(
            feature=feature,
            recovery_type="trivial_conflict",
            outcome="failed",
            what_was_tried="git checkout --theirs strategy",
            result=error,
        )
        return ConflictResolutionResult(
            success=False,
            strategy="trivial_fast_path",
            resolved_files=[],
            repair_branch=None,
            error=error,
        )

    # Test gate.
    test_result = await asyncio.to_thread(
        run_tests, config.test_command, cwd=str(worktree_path)
    )
    if not test_result.passed:
        _cleanup_repair_worktree(worktree_path, repair_branch, repo, delete_branch=True)
        write_recovery_log_entry(
            feature=feature,
            recovery_type="trivial_conflict",
            outcome="failed",
            what_was_tried="git checkout --theirs strategy",
            result=test_result.output[:300],
        )
        return ConflictResolutionResult(
            success=False,
            strategy="trivial_fast_path",
            resolved_files=[],
            repair_branch=None,
            error=f"test_failure: {test_result.output}",
        )

    # Success: leave repair branch for ff-merge, remove worktree only.
    _cleanup_repair_worktree(worktree_path, repair_branch, repo, delete_branch=False)
    write_recovery_log_entry(
        feature=feature,
        recovery_type="trivial_conflict",
        outcome="success",
        what_was_tried="git checkout --theirs strategy",
        result=f"resolved: {', '.join(actual_conflicted_files)}" if actual_conflicted_files else "conflict resolved",
    )
    return ConflictResolutionResult(
        success=True,
        strategy="trivial_fast_path",
        resolved_files=actual_conflicted_files,
        repair_branch=repair_branch,
        error=None,
    )


def classify_conflict(repo_path: Path) -> ConflictClassification:
    """Inspect a failed merge and classify the conflict.

    Queries git for the list of unmerged (conflicted) files, then scans each
    file for ``<<<<<<<`` markers to confirm text conflict presence. Non-UTF-8
    (binary) files are skipped and noted in the summary.

    The ``git merge --abort`` command is always run in a ``finally`` block,
    ensuring the repository is left in a clean state regardless of how this
    function exits.

    Args:
        repo_path: Path to the repository root.

    Returns:
        ConflictClassification with ``conflicted_files`` (paths that contain
        text conflict markers) and a human-readable ``conflict_summary``.
        On exception returns an empty ``conflicted_files`` list with summary
        ``"classification failed"``.
    """
    try:
        # Get the list of unmerged files from git
        diff_result = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=U"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        unmerged_paths = [
            line.strip()
            for line in diff_result.stdout.splitlines()
            if line.strip()
        ]

        conflicted_files: list[str] = []
        binary_notes: list[str] = []

        for rel_path in unmerged_paths:
            file_path = repo_path / rel_path
            try:
                content = file_path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                # Binary or unreadable file — skip but note it
                binary_notes.append(f"binary conflict in {rel_path}")
                continue

            if "<<<<<<<" in content:
                conflicted_files.append(rel_path)

        # Build the summary
        if conflicted_files:
            summary = f"{len(conflicted_files)} file(s) conflicted: {', '.join(conflicted_files)}"
            if binary_notes:
                summary += "; " + "; ".join(binary_notes)
        elif binary_notes:
            summary = "; ".join(binary_notes)
        else:
            summary = "no conflict markers found"

        return ConflictClassification(
            conflicted_files=conflicted_files,
            conflict_summary=summary,
        )

    except Exception:
        return ConflictClassification(
            conflicted_files=[],
            conflict_summary="classification failed",
        )

    finally:
        subprocess.run(
            ["git", "merge", "--abort"],
            cwd=repo_path,
            capture_output=True,
        )
