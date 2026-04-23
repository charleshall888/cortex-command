# Requirements: pipeline

> Last gathered: 2026-04-03

**Parent doc**: [requirements/project.md](project.md)

## Overview

The pipeline area covers the overnight execution framework: how sessions are orchestrated, how features are dispatched and tracked, how failures are recovered, how ambiguities are deferred to the morning report, and how execution metrics are collected. The pipeline is the backbone of autonomous multi-hour development — it must complete as much work as possible without human intervention while surfacing blockers clearly in the morning.

## Functional Requirements

### Session Orchestration

- **Description**: The overnight runner (`orchestrator.py`) manages session-level state, schedules features into rounds, dispatches them concurrently, and transitions the session through completion.
- **Inputs**: `lifecycle/overnight-state.json` (session phase, feature statuses), `lifecycle/master-plan.md` (round assignments), per-feature `lifecycle/{feature}/plan.md`
- **Outputs**: Updated `overnight-state.json`, `pipeline-events.log` (JSONL append log), per-feature commits on integration branch `overnight/{session_id}`
- **Acceptance criteria**:
  - Session phases transition forward-only: `planning → executing → complete`; any phase may transition to `paused`
  - Paused sessions resume to the phase they paused from
  - All state writes are atomic (tempfile + `os.replace()`) — partial-write corruption is not possible
  - Integration branches (`overnight/{session_id}`) persist after session completion and are not auto-deleted — they are left for PR creation to main
  - Artifact commits (lifecycle files, backlog status updates, session data) land on the integration branch, not local `main` — they travel with the PR
  - The morning report commit is the only runner commit that stays on local `main` (needed before PR merge for morning review to read)
  - Budget exhaustion transitions the session to `paused` without aborting in-flight features
  - Home-repo integration PR is always created (home-repo is an always-participant); cross-repo PRs are opt-in per-feature and skip when the repo contributed zero merges. On zero-merge home-repo sessions the PR is opened as a draft with a `[ZERO PROGRESS]` title prefix to block accidental merge; `integration_pr_flipped_once` (session-scoped marker in `overnight-state.json`) gates the resume-flow state-flip so the runner defers to human action after the first flip or a persistent `gh pr ready` failure
  - `runner.sh --dry-run` is a supported test-affordance mode that echoes (instead of executing) PR-side-effect calls (`gh pr create`, `gh pr ready`, `git push`, `notify.sh`) and assertable state writes; it rejects invocation when any feature is still pending. Regression coverage lives in `tests/test_runner_pr_gating.py`
- **Priority**: must-have

### Feature Execution and Failure Handling

- **Description**: Features within a session have their own status lifecycle. The pipeline dispatches features in rounds, handles individual failures without aborting the batch, and distinguishes recoverable pauses from permanent deferrals.
- **Inputs**: Feature task plans, round assignments, tier-based concurrency limit (from `ConcurrencyManager`)
- **Outputs**: Feature status transitions; recovery attempt logs; deferral files
- **Acceptance criteria**:
  - Feature statuses: `pending → running → merged` (success path); `running → paused` (recoverable failure); `running → deferred` (ambiguous intent, human decision required); `running → failed` (unrecoverable)
  - `paused` means a recoverable error (merge conflict, test failure, agent timeout) — paused features auto-retry when the session resumes
  - `deferred` means awaiting explicit human decision — deferred features do not auto-retry. Sources: ambiguous intent (exit report `action: "question"`), CI gate block, or non-APPROVED post-merge review verdict after rework exhaustion
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

### Post-Merge Review

- **Description**: After a feature merges successfully, the pipeline checks whether it qualifies for spec-compliance review per the tier/criticality gating matrix. Qualifying features are reviewed by a fresh agent; non-qualifying features skip directly to completion.
- **Inputs**: Merged feature; `lifecycle/{feature}/events.log` (tier and criticality); `lifecycle/{feature}/spec.md` (review benchmark); gating matrix
- **Outputs**: `lifecycle/{feature}/review.md` (review artifact with verdict JSON); `review_verdict` event in per-feature events.log; deferral file if non-APPROVED after rework
- **Acceptance criteria**:
  - Gating matrix: complex tier at any criticality → review; simple tier at high/critical → review; simple tier at low/medium → skip
  - Review agent dispatched via `dispatch_review()` in `claude/pipeline/review_dispatch.py`; batch_runner owns all `events.log` writes; review agent writes only `review.md`
  - 2-cycle rework loop: CHANGES_REQUESTED cycle 1 → write feedback to `orchestrator-note.md` → dispatch fix agent → SHA circuit breaker → re-merge (`ci_check=False`) → cycle 2 review
  - Non-APPROVED after cycle 2, REJECTED at any cycle, or review agent failure → feature status `deferred`; deferral file written for morning triage
  - APPROVED at any cycle → `review_verdict`, `phase_transition`, and `feature_complete` events written to per-feature events.log; feature proceeds to merged flow
  - Morning review synthetic events (`review_verdict: APPROVED, cycle: 0`) gated on the same matrix — only written for features that legitimately skip review
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

### Post-Session Sync

- **Description**: After morning review merges the overnight PR, local `main` diverges from remote (local has the morning report commit and review artifacts; remote has the PR merge commit). A post-merge sync step rebases local onto remote, resolves conflicts in overnight-managed files automatically, and pushes.
- **Inputs**: `claude/overnight/sync-allowlist.conf` (glob patterns for auto-resolvable files), local `main` branch state, remote `origin/main` after PR merge
- **Outputs**: Local `main` synced and pushed to `origin/main`; conflicts in allowlist files auto-resolved with `--theirs` (remote wins)
- **Acceptance criteria**:
  - After sync completes successfully, `git rev-list HEAD..origin/main --count` = 0 and `git rev-list origin/main..HEAD --count` = 0 (local and remote identical)
  - Conflicts in files matching `sync-allowlist.conf` patterns are auto-resolved with `--theirs` (remote/overnight version is authoritative)
  - Non-allowlist conflicts are surfaced to the user; if >3 non-allowlist files conflict or conflicts are unresolvable, the rebase is aborted
  - Multi-pass resolution handles sequential conflicts from replaying multiple local-only commits
  - Dirty rebase state (`.git/rebase-merge/` or `.git/rebase-apply/` from a prior crash) is detected and cleaned up before sync
  - The `--merge` PR merge strategy is a load-bearing dependency — `--theirs` semantics during rebase depend on it
- **Priority**: must-have

## Non-Functional Requirements

- **Atomicity**: All session state writes use tempfile + `os.replace()` — no partial-write corruption
- **Concurrency safety**: State file reads are not protected by locks; the forward-only phase transition model ensures re-reading a new state is safe (idempotent transitions)
- **Graceful degradation**: Budget exhaustion and rate limits pause the session rather than crashing it
- **Audit trail**: `lifecycle/pipeline-events.log` provides an append-only JSONL record of all dispatch and merge events
- **Orchestrator rationale convention**: When the orchestrator resolves an escalation or makes a non-obvious feature selection decision (e.g., skipping a feature, reordering rounds), the relevant events.log entry should include a `rationale` field explaining the reasoning. Routine forward-progress decisions do not require this field. (Convention defined in `claude/reference/output-floors.md`; enforcement requires orchestrator prompt changes.)

## Architectural Constraints

- **State file locking**: State file reads are not protected by locks by design. Writers use atomic `os.replace()`; readers may observe a state mid-mutation, but forward-only transitions make this safe. This is a permanent architectural constraint.
- **Repair attempt cap**: The repair attempt limit (max 2 attempts for test failures; single Sonnet → Opus escalation for merge conflicts) is a fixed architectural constraint. It is cost-bounded and circuit-breaker backed; unlimited retries would be cost-prohibitive for autonomous overnight sessions.
- **Integration branch persistence**: Integration branches (`overnight/{session_id}`) are not auto-deleted after session completion. They persist for manual PR creation and review.
- **Dashboard access**: The web dashboard is unauthenticated and accessible to any host on the local network (binds to `0.0.0.0`) by design (see `requirements/observability.md`).

## Dependencies

- `lifecycle/overnight-state.json` — session state (atomic writes)
- `lifecycle/master-plan.md` — batch session plan
- `lifecycle/{feature}/plan.md` — per-feature task plans
- `lifecycle/pipeline-events.log` — JSONL event audit log
- `lifecycle/deferred/` — deferral question files
- `lifecycle/escalations.jsonl` — escalation audit log
- `claude/overnight/sync-allowlist.conf` — glob patterns for auto-resolvable files during post-merge sync
- `bin/git-sync-rebase.sh` — post-merge sync script (deployed to `~/.local/bin/`)
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
