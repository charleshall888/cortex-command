# Requirements: pipeline

> Last gathered: 2026-04-03

**Parent doc**: [requirements/project.md](project.md)

## Overview

The pipeline area covers the overnight execution framework: how sessions are orchestrated, how features are dispatched and tracked, how failures are recovered, how ambiguities are deferred to the morning report, and how execution metrics are collected. The pipeline is the backbone of autonomous multi-hour development — it must complete as much work as possible without human intervention while surfacing blockers clearly in the morning.

## Functional Requirements

### Session Orchestration

- **Description**: The overnight runner (`batch_runner.py`) manages session-level state, schedules features into rounds, dispatches them concurrently, and transitions the session through completion.
- **Inputs**: `lifecycle/overnight-state.json` (session phase, feature statuses), `lifecycle/master-plan.md` (round assignments), per-feature `lifecycle/{feature}/plan.md`
- **Outputs**: Updated `overnight-state.json`, `pipeline-events.log` (JSONL append log), per-feature commits on integration branch `overnight/{session_id}`
- **Acceptance criteria**:
  - Session phases transition forward-only: `planning → executing → complete`; any phase may transition to `paused`
  - Paused sessions resume to the phase they paused from
  - All state writes are atomic (tempfile + `os.replace()`) — partial-write corruption is not possible
  - Integration branches (`overnight/{session_id}`) persist after session completion and are not auto-deleted — they are left for manual PR creation to main
  - Budget exhaustion transitions the session to `paused` without aborting in-flight features
- **Priority**: must-have

### Feature Execution and Failure Handling

- **Description**: Features within a session have their own status lifecycle. The pipeline dispatches features in rounds, handles individual failures without aborting the batch, and distinguishes recoverable pauses from permanent deferrals.
- **Inputs**: Feature task plans, round assignments, concurrency configuration
- **Outputs**: Feature status transitions; recovery attempt logs; deferral files
- **Acceptance criteria**:
  - Feature statuses: `pending → running → merged` (success path); `running → paused` (recoverable failure); `running → deferred` (ambiguous intent, human decision required); `running → failed` (unrecoverable)
  - `paused` means a recoverable error (merge conflict, test failure, agent timeout) — paused features auto-retry when the session resumes
  - `deferred` means awaiting explicit human decision — deferred features do not auto-retry
  - One feature's failure does not block other features in the same round (fail-forward model)
  - Per-feature recovery metadata is tracked: `recovery_attempts` and `recovery_depth` counters
- **Priority**: must-have

### Conflict Resolution

- **Description**: When a feature branch produces a merge conflict, the pipeline classifies the conflict and applies the appropriate resolution strategy before the human reviews the session.
- **Inputs**: Conflicted merge; list of conflicted files
- **Outputs**: Resolved merge or feature paused/deferred; repair agent commit (if applicable)
- **Acceptance criteria**:
  - Conflicts with ≤3 affected files and no "hot files" (critical shared files) use the trivial fast path: `git checkout --theirs` per file, complete merge, run test gate
  - Complex conflicts dispatch a Sonnet repair agent on an isolated worktree
  - If Sonnet fails (unresolved markers or deferral in exit report), escalate once to Opus
  - Repair attempt cap is a fixed architectural constraint: single escalation (Sonnet → Opus) for merge conflicts
  - If repair fails after escalation, feature is paused; in-progress merge is aborted before returning
  - Test gate runs after any resolution; on gate failure, repair branch is cleaned up
- **Priority**: must-have

### Post-Merge Test Failure Recovery

- **Description**: When a feature merges successfully but breaks the test suite, the pipeline attempts automated recovery before surfacing to the human.
- **Inputs**: Post-merge test failure; learnings from prior attempts; integrated branch state
- **Outputs**: Tests passing (recovered) or feature paused with recovery log
- **Acceptance criteria**:
  - Flaky guard runs first: re-merge with no feature changes; if tests pass, feature is marked `merged` with `flaky=True` recorded
  - If flaky guard fails, dispatch repair agent (Sonnet); escalate to Opus on failure
  - Repair attempt cap is a fixed architectural constraint: max 2 attempts (Sonnet + Opus)
  - Circuit breaker: if repair agent produces no new commits (before_sha == after_sha), feature pauses immediately
  - Each attempt appends learnings to `lifecycle/{feature}/learnings/progress.txt`
  - Recovery outcome is recorded in `lifecycle/{feature}/recovery-log.md`
- **Priority**: must-have

### Deferral System

- **Description**: When the pipeline encounters an ambiguous decision that cannot be resolved autonomously, it writes a structured deferral question and surfaces it in the morning report.
- **Inputs**: Worker exit report declaring `action: "question"`; CI gate block; repair agent declaring deferral
- **Outputs**: Deferral file at `lifecycle/deferred/{feature}-q{NNN}.md`; feature status transitions to `deferred` (blocking) or continues (non-blocking); escalation entry in `lifecycle/escalations.jsonl`
- **Acceptance criteria**:
  - Deferral files are written atomically
  - Blocking deferrals pause the feature; non-blocking deferrals allow the feature to continue using the recorded `default_choice`
  - Deferral files include: severity (blocking / non-blocking / informational), context, question, options considered, pipeline action attempted, and optional default choice
- **Priority**: must-have

### Metrics and Cost Tracking

- **Description**: The pipeline collects execution metrics from lifecycle event logs for post-session review and calibration.
- **Inputs**: `lifecycle/*/events.log` (JSONL event streams per feature)
- **Outputs**: `lifecycle/metrics.json` with per-feature metrics, tier aggregates, and calibration summaries
- **Acceptance criteria**:
  - Metrics are computed by parsing `feature_complete` events; in-progress features are excluded
  - Per-feature metrics: complexity tier, task count, batch count, rework cycles, review verdicts, phase durations, total duration
  - Tier aggregates: mean duration, task count, batch count, rework cycles, and approval rate per tier (simple / complex)
  - Backfilled synthetic timestamps (T00:0X:00Z pattern) are detected; phase durations involving them are marked `null`
  - Duplicate `feature_complete` events: last one per feature is canonical
- **Priority**: should-have

## Non-Functional Requirements

- **Atomicity**: All session state writes use tempfile + `os.replace()` — no partial-write corruption
- **Concurrency safety**: State file reads are not protected by locks; the forward-only phase transition model ensures re-reading a new state is safe (idempotent transitions)
- **Graceful degradation**: Budget exhaustion and rate limits pause the session rather than crashing it
- **Audit trail**: `lifecycle/pipeline-events.log` provides an append-only JSONL record of all dispatch and merge events

## Architectural Constraints

- **State file locking**: State file reads are not protected by locks by design. Writers use atomic `os.replace()`; readers may observe a state mid-mutation, but forward-only transitions make this safe. This is a permanent architectural constraint.
- **Repair attempt cap**: The repair attempt limit (max 2 attempts for test failures; single Sonnet → Opus escalation for merge conflicts) is a fixed architectural constraint. It is cost-bounded and circuit-breaker backed; unlimited retries would be cost-prohibitive for autonomous overnight sessions.
- **Integration branch persistence**: Integration branches (`overnight/{session_id}`) are not auto-deleted after session completion. They persist for manual PR creation and review.
- **Dashboard access**: The web dashboard is unauthenticated and localhost-only by design (see `requirements/observability.md`).

## Dependencies

- `lifecycle/overnight-state.json` — session state (atomic writes)
- `lifecycle/master-plan.md` — batch session plan
- `lifecycle/{feature}/plan.md` — per-feature task plans
- `lifecycle/pipeline-events.log` — JSONL event audit log
- `lifecycle/deferred/` — deferral question files
- `lifecycle/escalations.jsonl` — escalation audit log
- Multi-agent orchestration (see `requirements/multi-agent.md`) — agent spawning, worktrees, model selection
- Smoke test gate (`claude/overnight/smoke_test.py`) — post-merge verification

## Edge Cases

- **Resumed session**: Features already at `merged` are skipped via idempotency tokens; `paused` features re-enter the execution queue
- **Plan hash mismatch on resume**: Session detects change and logs a warning; continues with current plan
- **TMPDIR cleared between sessions**: Stale integration worktree paths are re-created on next access; git tracking is pruned and retried
- **All features pause in a round**: Circuit breaker fires; no further features dispatched; morning report surfaces reason
- **Feature paused with no recovery attempts remaining**: Status transitions to `paused` permanently until human intervenes

## Open Questions

- None
