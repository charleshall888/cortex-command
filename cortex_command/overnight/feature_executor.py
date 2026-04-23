"""Per-feature execution layer extracted from batch_runner.py.

This module contains the per-feature execution layer extracted from
batch_runner.py. This module must not import from
`claude.overnight.batch_runner` or `claude.overnight.orchestrator`.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from claude.overnight.orchestrator import BatchConfig

from claude.common import (
    compute_dependency_batches,
    mark_task_done_in_plan,
    read_criticality,
)
from claude.pipeline.conflict import (
    ConflictClassification,
    dispatch_repair_agent,
    resolve_trivial_conflict,
)
from claude.pipeline.parser import FeatureTask, parse_feature_plan
from claude.pipeline.retry import RetryResult, retry_task
from claude.pipeline.state import log_event as pipeline_log_event

from claude.overnight.brain import BrainAction, BrainContext, request_brain_decision
from claude.overnight.deferral import (
    DEFAULT_DEFERRED_DIR,
    SEVERITY_BLOCKING,
    DeferralQuestion,
    EscalationEntry,
    _next_escalation_n,
    write_deferral,
    write_escalation,
)
from claude.overnight.events import (
    BRAIN_DECISION,
    FEATURE_DEFERRED,
    MERGE_CONFLICT_CLASSIFIED,
    WORKER_MALFORMED_EXIT_REPORT,
    WORKER_NO_EXIT_REPORT,
    log_event as overnight_log_event,
    read_events,
)
from claude.overnight.state import load_state, save_state
from claude.overnight.throttle import ConcurrencyManager
from claude.overnight.types import CircuitBreakerState, FeatureResult
from claude.overnight.constants import CIRCUIT_BREAKER_THRESHOLD

logger = logging.getLogger(__name__)

IMPLEMENT_TEMPLATE = Path(__file__).resolve().parents[1] / "pipeline/prompts/implement.md"


# ---------------------------------------------------------------------------
# Internal: prompt rendering
# ---------------------------------------------------------------------------


def _render_template(template_path: Path, variables: dict[str, str]) -> str:
    """Read a prompt template and fill in {placeholders}."""
    template = template_path.read_text(encoding="utf-8")
    for key, value in variables.items():
        template = template.replace(f"{{{key}}}", value)
    return template


def _get_spec_path(feature: str, spec_path: Optional[str] = None) -> str:
    """Return an absolute path to the spec file for a feature.

    Resolution order: explicit *spec_path* first, then the per-feature
    lifecycle spec.  Always returns an absolute path string (even when the
    underlying file might not exist).
    """
    if spec_path:
        p = Path(spec_path)
        if p.exists():
            return str(p.resolve())
    lifecycle_path = Path(f"lifecycle/{feature}/spec.md")
    return str(lifecycle_path.resolve())


def _read_spec_content(feature: str, spec_path: Optional[str] = None) -> str:
    """Read and return the full text of the spec file for a feature.

    Uses `_get_spec_path` for resolution, then reads the file.  Returns a
    fallback string when the resolved path does not exist on disk.
    """
    resolved = _get_spec_path(feature, spec_path)
    p = Path(resolved)
    if p.exists():
        return p.read_text(encoding="utf-8")
    return "(No specification file found.)"


def _read_learnings(feature: str) -> str:
    parts: list[str] = []
    progress_path = Path(f"lifecycle/{feature}/learnings/progress.txt")
    if progress_path.exists():
        content = progress_path.read_text(encoding="utf-8")
        if content.strip():
            parts.append(content)
    note_path = Path(f"lifecycle/{feature}/learnings/orchestrator-note.md")
    if note_path.exists():
        content = note_path.read_text(encoding="utf-8")
        if content.strip():
            parts.append(f"## Orchestrator Note\n{content}")
    if not parts:
        return "(No prior learnings.)"
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Exit-report reader
# ---------------------------------------------------------------------------

# Recognised worker-declared actions (R3 soft action registry).
_EXIT_REPORT_ACTIONS = {"complete", "question"}


def _read_exit_report(
    feature: str,
    task_number: int,
    worktree_path: Optional[Path] = None,
) -> tuple[str | None, str | None, str | None]:
    """Read a worker exit report for a single task.

    Returns ``(action, reason, question)`` extracted from
    ``lifecycle/{feature}/exit-reports/{task_number}.json``.

    Checks two locations in order:
    1. Primary: ``lifecycle/{feature}/exit-reports/{task_number}.json``
       relative to the batch runner's CWD (the integration worktree in overnight
       sessions).
    2. Fallback: ``worktree_path / "lifecycle" / feature / "exit-reports" /
       "{task_number}.json"`` — the absolute path inside the feature worktree,
       used when the worker wrote artifacts to its own CWD rather than the
       integration worktree.

    Returns ``(None, None, None)`` if neither file exists, or if the file
    contains malformed JSON, is missing the ``action`` key, or declares an
    unrecognised action string.
    """
    report_path = Path(f"lifecycle/{feature}/exit-reports/{task_number}.json")
    if not report_path.is_file():
        if worktree_path is not None:
            fallback_path = worktree_path / "lifecycle" / feature / "exit-reports" / f"{task_number}.json"
            if fallback_path.is_file():
                report_path = fallback_path
            else:
                return None, None, None
        else:
            return None, None, None
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None, None, None
    if not isinstance(data, dict):
        return None, None, None
    action = data.get("action")
    if action is None or action not in _EXIT_REPORT_ACTIONS:
        return None, None, None
    return action, data.get("reason"), data.get("question")


# ---------------------------------------------------------------------------
# Brain-agent triage for failed tasks
# ---------------------------------------------------------------------------

async def _handle_failed_task(
    feature: str,
    task: FeatureTask,
    all_tasks: list[FeatureTask],
    spec_excerpt: str,
    retry_result: object,
    cb_state: CircuitBreakerState,
    manager: Optional[ConcurrencyManager] = None,
    round: int = 0,
    log_path: Path = Path("lifecycle/overnight-events.log"),
    *,
    deferred_dir: Path = DEFAULT_DEFERRED_DIR,
) -> Optional[FeatureResult]:
    """Handle a failed task via brain agent triage.

    Makes a single brain agent call that unifies triage and deferral
    detection into one SKIP/DEFER/PAUSE decision. Returns a FeatureResult
    if the task should be deferred, or None for SKIP/PAUSE outcomes
    (caller uses its default paused behavior for PAUSE).
    """
    # R5: Pre-dispatch circuit breaker soft check — skip brain call if
    # we're one pause away from tripping the circuit breaker.
    if cb_state.consecutive_pauses >= CIRCUIT_BREAKER_THRESHOLD - 1:
        return None  # PAUSE outcome — caller handles as paused

    # Compute has_dependents: any task whose depends_on contains this task
    has_dependents = any(task.number in t.depends_on for t in all_tasks)

    ctx = BrainContext(
        feature=feature,
        task_description=task.description,
        retry_count=getattr(retry_result, 'attempts', 0),
        learnings=_read_learnings(feature),
        spec_excerpt=spec_excerpt,
        last_attempt_output=getattr(retry_result, 'final_output', '') or '',
        has_dependents=has_dependents,
    )

    decision = await request_brain_decision(ctx, manager, log_path)

    # Log the brain decision (R6)
    overnight_log_event(
        BRAIN_DECISION,
        round,
        feature=feature,
        details={
            "task": task.description,
            "action": decision.action.value,
            "reasoning": decision.reasoning,
            "retry_count": getattr(retry_result, 'attempts', 0),
            "confidence": decision.confidence,
        },
        log_path=log_path,
    )

    # Map BrainDecision to return values
    if decision.action == BrainAction.SKIP:
        mark_task_done_in_plan(Path(f"lifecycle/{feature}/plan.md"), task.number)
        return None  # Continue to next task

    if decision.action == BrainAction.DEFER:
        severity = decision.severity or SEVERITY_BLOCKING
        question_text = decision.question or f"Task {task.number} failed: {task.description}"
        deferral = DeferralQuestion(
            feature=feature,
            question_id=0,
            severity=severity,
            context=f"Task {task.number}: {task.description}",
            question=question_text,
            options_considered=[],
            pipeline_attempted="brain agent triage",
        )
        write_deferral(deferral, deferred_dir=deferred_dir)
        return FeatureResult(
            name=feature,
            status="deferred",
            error=f"Task {task.number} deferred: {question_text}",
            deferred_question_count=1,
        )

    # BrainAction.PAUSE — return None, caller handles as paused
    return None


# ---------------------------------------------------------------------------
# Idempotency helpers
# ---------------------------------------------------------------------------


def _compute_plan_hash(plan_path: Path) -> str:
    """Return the SHA-256 hex digest of the plan file's content.

    Falls back to the hash of an empty byte string if the file does not exist.
    """
    try:
        content = plan_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        content = ""
    return hashlib.sha256(content.encode()).hexdigest()


def _make_idempotency_token(feature: str, task_number: int, plan_hash: str) -> str:
    """Return the first 32 hex chars of SHA-256 of the canonical key.

    The key is ``<feature>:<task_number>:<plan_hash>``.  Changing any input
    component produces a different token, so a plan edit automatically
    invalidates all previously-written tokens.
    """
    key = f"{feature}:{task_number}:{plan_hash}"
    return hashlib.sha256(key.encode()).hexdigest()[:32]


def _check_task_completed(log_path: Path, token: str) -> bool:
    """Return True if a completion record for *token* exists in *log_path*.

    Scans the file line by line.  Blank lines and lines that are not valid JSON
    are skipped silently.  Returns False if the file does not exist.
    """
    try:
        fh = log_path.open(encoding="utf-8")
    except FileNotFoundError:
        return False
    with fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (
                record.get("event") == "task_idempotency_complete"
                and record.get("idempotency_token") == token
            ):
                return True
    return False


def _write_completion_token(
    log_path: Path, feature: str, task_number: int, token: str
) -> None:
    """Append a completion record to *log_path*.

    Creates the file (and any missing parent directories) if absent.  Failures
    are silently swallowed — idempotency writes are best-effort.
    """
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "event": "task_idempotency_complete",
            "feature": feature,
            "task_number": task_number,
            "idempotency_token": token,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Per-feature execution
# ---------------------------------------------------------------------------


async def execute_feature(
    feature: str,
    worktree_path: Path,
    config: BatchConfig,
    spec_path: Optional[str] = None,
    manager: Optional[ConcurrencyManager] = None,
    cb_state: Optional[CircuitBreakerState] = None,
    repo_path: Path | None = None,
    integration_branches: dict[str, str] | None = None,
    *,
    deferred_dir: Path = DEFAULT_DEFERRED_DIR,
) -> FeatureResult:
    """Execute all tasks for a single feature through its plan.

    Parses the feature plan, computes dependency batches, dispatches
    tasks concurrently within each batch, and handles deferrals.
    Uses ConcurrencyManager for throttle-aware dispatch if provided.
    """
    integration_branches = integration_branches or {}
    # --- Conflict recovery policy (ticket 157) ---
    # At batch entry, check whether a merge_conflict_classified event exists for
    # this feature.  If so, apply the tiered decision: trivial fast-path first,
    # repair agent if non-trivial or trivial failed, deferral if budget exhausted.
    _skip_repair = False
    _overnight_state = None
    try:
        _overnight_state = load_state(config.overnight_state_path)
    except Exception:
        _skip_repair = True

    if not _skip_repair and _overnight_state is not None:
        _conflict_event = None
        try:
            for _evt in read_events(config.overnight_events_path):
                if (
                    _evt.get("event") == MERGE_CONFLICT_CLASSIFIED
                    and _evt.get("feature") == feature
                ):
                    _conflict_event = _evt  # use the last matching event
        except OSError:
            pass

        if _conflict_event is not None:
            _fs = _overnight_state.features.get(feature)
            if _fs is not None and _fs.recovery_depth < 1:
                _conflicted_files = _conflict_event.get("details", {}).get(
                    "conflicted_files", []
                )

                # Load hot files from overnight-strategy.json (absent = []).
                _hot_files: list[str] = []
                try:
                    _strategy_path = (
                        Path(config.overnight_state_path).parent
                        / "overnight-strategy.json"
                    )
                    _strategy_data = json.loads(
                        _strategy_path.read_text(encoding="utf-8")
                    )
                    _hot_files = _strategy_data.get("hot_files", [])
                except (OSError, json.JSONDecodeError):
                    pass

                # Decision: trivial eligible?
                _trivial_eligible = len(_conflicted_files) <= 3 and not any(
                    f in _hot_files for f in _conflicted_files
                )

                if _trivial_eligible:
                    _trivial_result = await resolve_trivial_conflict(
                        feature=feature,
                        branch=f"pipeline/{feature}",
                        base_branch=config.base_branch,
                        conflicted_files=_conflicted_files,
                        config=config,
                        round_number=config.batch_id,
                    )
                    if _trivial_result.success:
                        return FeatureResult(
                            name=feature,
                            status="repair_completed",
                            trivial_resolved=True,
                            repair_branch=_trivial_result.repair_branch,
                            resolved_files=_trivial_result.resolved_files,
                        )
                    # Trivial failed — fall through to repair agent path.

                # Repair agent path.
                if _fs.recovery_attempts >= 1:
                    escalations_path = Path("lifecycle/escalations.jsonl")
                    _deferral = DeferralQuestion(
                        feature=feature,
                        question_id=_next_escalation_n(feature, config.batch_id, escalations_path),
                        severity=SEVERITY_BLOCKING,
                        context=f"Conflict recovery budget exhausted for {feature} — repair agent already attempted once",
                        question=f"Conflict recovery budget exhausted for {feature} — repair agent already attempted once",
                        options_considered=["resolve manually", "skip feature"],
                        pipeline_attempted="conflict_recovery_policy",
                    )
                    write_deferral(_deferral, deferred_dir=deferred_dir)
                    return FeatureResult(
                        name=feature,
                        status="deferred",
                        deferred_question_count=1,
                    )

                # Dispatch repair agent.
                _fs.recovery_depth = 1
                _save_ok = True
                # Concurrency hazard (pre-existing): two concurrent features on the
                # repair path may race on overnight-state.json. The _save_ok guard
                # is the existing mitigation — do not remove it.
                try:
                    await asyncio.to_thread(
                        save_state, _overnight_state, config.overnight_state_path
                    )
                except Exception:
                    _save_ok = False  # do not dispatch with unpersisted recovery_depth

                if _save_ok:
                    _cc = ConflictClassification(
                        conflicted_files=_conflicted_files,
                        conflict_summary=_conflict_event.get("details", {}).get(
                            "conflict_summary", ""
                        ),
                    )
                    _repair_result = await dispatch_repair_agent(
                        feature=feature,
                        conflict_classification=_cc,
                        base_branch=config.base_branch,
                        spec_path=spec_path,
                        config=config,
                        round_number=config.batch_id,
                        repo_root=repo_path,
                    )
                    if _repair_result.success:
                        return FeatureResult(
                            name=feature,
                            status="repair_completed",
                            repair_branch=_repair_result.repair_branch,
                            repair_agent_used=True,
                        )
                    elif _repair_result.error and _repair_result.error.startswith("deferral:"):
                        _question_text = _repair_result.error[len("deferral:"):].strip()
                        escalations_path = Path("lifecycle/escalations.jsonl")
                        _deferral = DeferralQuestion(
                            feature=feature,
                            question_id=_next_escalation_n(feature, config.batch_id, escalations_path),
                            severity=SEVERITY_BLOCKING,
                            context=f"Repair agent for {feature} could not determine intent",
                            question=_question_text,
                            options_considered=["resolve manually", "skip feature"],
                            pipeline_attempted="dispatch_repair_agent()",
                        )
                        write_deferral(_deferral, deferred_dir=deferred_dir)
                        return FeatureResult(
                            name=feature,
                            status="deferred",
                            deferred_question_count=1,
                            repair_agent_used=True,
                        )
                    else:
                        return FeatureResult(
                            name=feature,
                            status="paused",
                            error=_repair_result.error,
                            repair_agent_used=True,
                        )
    # --- End conflict recovery policy ---

    plan_path = Path(f"lifecycle/{feature}/plan.md")
    plan_hash = _compute_plan_hash(plan_path)
    try:
        feature_plan = parse_feature_plan(plan_path)
    except (FileNotFoundError, ValueError) as exc:
        return FeatureResult(
            name=feature,
            status="failed",
            error=f"Plan parse error: {exc}",
            parse_error=True,
        )

    spec_path_resolved = _get_spec_path(feature, spec_path)
    spec_content = _read_spec_content(feature, spec_path)
    learnings_dir = Path(f"lifecycle/{feature}/learnings")

    try:
        batches = compute_dependency_batches(feature_plan.tasks)
    except ValueError as exc:
        return FeatureResult(
            name=feature,
            status="failed",
            error=f"Dependency error: {exc}",
        )

    for batch in batches:
        async def _run_task(task: FeatureTask) -> tuple[FeatureTask, object, int]:
            plan_task_lines = [
                f"- **Files**: {', '.join(task.files) if task.files else 'N/A'}",
                f"- **Depends on**: {task.depends_on if task.depends_on else 'None'}",
                f"- **Complexity**: {task.complexity}",
            ]
            plan_task = "\n".join(plan_task_lines)
            progress_path = Path(f"lifecycle/{feature}/learnings/progress.txt")
            note_path = Path(f"lifecycle/{feature}/learnings/orchestrator-note.md")
            has_progress = progress_path.exists() and progress_path.read_text(encoding="utf-8").strip()
            has_note = note_path.exists() and note_path.read_text(encoding="utf-8").strip()
            if has_progress or has_note:
                learnings = _read_learnings(feature)
            else:
                learnings = "(No prior learnings.)"

            system_prompt = _render_template(IMPLEMENT_TEMPLATE, {
                "feature": feature,
                "task_number": str(task.number),
                "task_description": task.description,
                "plan_task": plan_task,
                "spec_path": spec_path_resolved,
                "worktree_path": str(worktree_path),
                "learnings": learnings,
                "integration_worktree_path": str(Path.cwd()),
            })

            activity_log_path = Path(f"lifecycle/{feature}/agent-activity.jsonl")

            token = _make_idempotency_token(feature, task.number, plan_hash)
            if _check_task_completed(config.pipeline_events_path, token):
                try:
                    pipeline_log_event(config.pipeline_events_path, {
                        "event": "task_idempotency_skip",
                        "feature": feature,
                        "task_number": task.number,
                        "idempotency_token": token,
                    })
                except Exception:
                    pass
                return task, RetryResult(success=True, attempts=0, final_output="idempotency: already complete", paused=False, idempotency_skipped=True), 0

            result = await retry_task(
                feature=feature,
                task=task.description,
                worktree_path=worktree_path,
                complexity=task.complexity,
                criticality=read_criticality(feature),
                system_prompt=system_prompt,
                learnings_dir=learnings_dir,
                log_path=config.pipeline_events_path,
                activity_log_path=activity_log_path,
                integration_base_path=Path.cwd(),
                repo_path=repo_path,
            )

            if result.success and not result.paused:
                _write_completion_token(config.pipeline_events_path, feature, task.number, token)

            pipeline_log_event(config.pipeline_events_path, {
                "event": "task_output",
                "feature": feature,
                "task_number": task.number,
                "task_description": task.description,
                "output": (result.final_output or "")[:2000],
            })

            try:
                status_proc = subprocess.run(
                    ["git", "status", "--short"],
                    cwd=worktree_path,
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                count_proc = subprocess.run(
                    ["git", "rev-list", "--count", f"{config.base_branch}..HEAD"],
                    cwd=worktree_path,
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if status_proc.returncode != 0 or count_proc.returncode != 0:
                    raise OSError("git command returned non-zero exit code")
                git_status = status_proc.stdout
                new_commit_count = int(count_proc.stdout.strip())
            except (subprocess.TimeoutExpired, OSError, ValueError):
                git_status = "(error)"
                new_commit_count = -1

            pipeline_log_event(config.pipeline_events_path, {
                "event": "task_git_state",
                "feature": feature,
                "task_number": task.number,
                "git_status": git_status,
                "new_commit_count": new_commit_count,
            })

            return task, result, new_commit_count

        results = await asyncio.gather(
            *[_run_task(t) for t in batch],
            return_exceptions=True,
        )

        for item in results:
            if isinstance(item, BaseException):
                return FeatureResult(
                    name=feature,
                    status="failed",
                    error=f"Unexpected error: {item}",
                )

            task, result, task_commit_count = item
            if not result.success or result.paused:
                # Budget exhaustion bypasses brain triage entirely
                if getattr(result, "error_type", None) == "budget_exhausted":
                    return FeatureResult(
                        name=feature,
                        status="paused",
                        error="budget_exhausted",
                    )

                # Brain agent triage for failed/paused tasks
                cb_state_eff = cb_state if cb_state is not None else CircuitBreakerState()
                brain_result = await _handle_failed_task(
                    feature, task, feature_plan.tasks,
                    spec_content, result, cb_state_eff, manager,
                    round=config.batch_id,
                    log_path=config.overnight_events_path,
                    deferred_dir=deferred_dir,
                )
                if brain_result:
                    return brain_result

                return FeatureResult(
                    name=feature,
                    status="paused",
                    error=f"Task {task.number} failed after {result.attempts} attempts",
                )

            if result.idempotency_skipped:
                mark_task_done_in_plan(Path(f"lifecycle/{feature}/plan.md"), task.number)
                continue

            # --- Exit-report validation (R1, R2, R3) ---
            report_action, report_reason, report_question = _read_exit_report(
                feature, task.number, worktree_path=worktree_path,
            )

            if report_action == "question" and report_question:
                # Worker declared a question — escalate and defer
                escalations_path = Path("lifecycle/escalations.jsonl")
                esc_n = _next_escalation_n(
                    feature, config.batch_id, escalations_path,
                )
                esc_id = f"{feature}-{config.batch_id}-q{esc_n}"
                write_escalation(
                    EscalationEntry(
                        escalation_id=esc_id,
                        feature=feature,
                        round=config.batch_id,
                        question=report_question,
                        context=report_reason or "",
                    ),
                    escalations_path=escalations_path,
                )
                overnight_log_event(
                    FEATURE_DEFERRED,
                    config.batch_id,
                    feature=feature,
                    details={
                        "source": "exit_report",
                        "task_number": task.number,
                        "question": report_question,
                    },
                    log_path=config.overnight_events_path,
                )
                return FeatureResult(
                    name=feature,
                    status="deferred",
                    deferred_question_count=1,
                )

            # Cases: missing file (action is None, file absent),
            # malformed (action is None, file present), or
            # action=="question" without a question field.
            if report_action is None or (
                report_action == "question" and not report_question
            ):
                report_path = Path(
                    f"lifecycle/{feature}/exit-reports/{task.number}.json"
                )
                if report_path.is_file():
                    overnight_log_event(
                        WORKER_MALFORMED_EXIT_REPORT,
                        config.batch_id,
                        feature=feature,
                        details={"task_number": task.number},
                        log_path=config.overnight_events_path,
                    )
                else:
                    overnight_log_event(
                        WORKER_NO_EXIT_REPORT,
                        config.batch_id,
                        feature=feature,
                        details={"task_number": task.number},
                        log_path=config.overnight_events_path,
                    )

            # action == "complete", missing, or malformed — fall through
            mark_task_done_in_plan(Path(f"lifecycle/{feature}/plan.md"), task.number)

    # All tasks passed — feature complete
    return FeatureResult(name=feature, status="completed")
