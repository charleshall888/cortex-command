# Requirements: pipeline

> Last gathered: 2026-04-03

**Parent doc**: [requirements/project.md](project.md)

## Overview

The pipeline area covers the overnight execution framework: how sessions are orchestrated, how features are dispatched and tracked, how failures are recovered, how ambiguities are deferred to the morning report, and how execution metrics are collected. The pipeline is the backbone of autonomous multi-hour development — it must complete as much work as possible without human intervention while surfacing blockers clearly in the morning.

## Functional Requirements

### Session Orchestration

- **Description**: The overnight runner (`orchestrator.py`) manages session-level state, schedules features into rounds, dispatches them concurrently, and transitions the session through completion.
- **Inputs**: `cortex/lifecycle/overnight-state.json` (session phase, feature statuses), `cortex/lifecycle/master-plan.md` (round assignments), per-feature `cortex/lifecycle/{feature}/plan.md`
- **Outputs**: Updated `overnight-state.json`, `pipeline-events.log` (JSONL append log), per-feature commits on integration branch `overnight/{session_id}`
- **Acceptance criteria**:
  - Session phases transition forward-only: `planning → executing → complete`; any phase may transition to `paused`
  - Paused sessions resume to the phase they paused from
  - All state writes are atomic (tempfile + `os.replace()`) — partial-write corruption is not possible
  - Integration branches (`overnight/{session_id}`) persist after session completion (see `## Architectural Constraints` → "Integration branch persistence")
  - Artifact commits (lifecycle files, backlog status updates, session data) land on the integration branch, not local `main` — they travel with the PR
  - The morning report is written to two paths: `cortex/lifecycle/sessions/{session_id}/morning-report.md` (gitignored per-session archive) and `cortex/lifecycle/morning-report.md` (tracked latest copy); the latter is committed to local `main` directly by the runner process.
  - Budget exhaustion transitions the session to `paused` without aborting in-flight features
  - Home-repo integration PR is always created (home-repo is an always-participant); cross-repo PRs are opt-in per-feature and skip when the repo contributed zero merges. On zero-merge home-repo sessions the PR is opened as a draft with a `[ZERO PROGRESS]` title prefix to block accidental merge; `integration_pr_flipped_once` (session-scoped marker in `overnight-state.json`) gates the resume-flow state-flip so the runner defers to human action after the first flip or a persistent `gh pr ready` failure
  - `cortex overnight start --dry-run` is a supported test-affordance mode that echoes (instead of executing) PR-side-effect calls (`gh pr create`, `gh pr ready`, `git push`, `notify.sh`) and assertable state writes; it rejects invocation when any feature is still pending. Regression coverage (including a byte-identical stdout snapshot) lives in `tests/test_runner_pr_gating.py`.
  - The overnight runner ships as a `cortex overnight {start|status|cancel|logs|schedule|list-sessions}` Python CLI; the legacy `runner.sh` bash entry and `bin/overnight-{start,status,schedule}` shims are retired. The `schedule` verb is macOS-only (LaunchAgent backend; non-darwin invocations exit with a "scheduling requires macOS" error). `cortex overnight cancel` validates session-ids against `^[a-zA-Z0-9._-]{1,128}$` + realpath containment before any filesystem access, and verifies the per-session `runner.pid` (magic + `1 ≤ schema_version ≤ MAX_KNOWN_RUNNER_PID_SCHEMA_VERSION`; start_time cross-check detail in `docs/overnight-operations.md` "Runner concurrency guard") before signalling. When `~/.claude/notify.sh` is absent, notifications fall back to stderr with a `NOTIFY:` prefix so stdout remains clean as the orchestrator agent's input channel.
- **Priority**: must-have

### Feature Execution and Failure Handling

- **Description**: Features within a session have their own status lifecycle. The pipeline dispatches features in rounds, handles individual failures without aborting the batch, and distinguishes recoverable pauses from permanent deferrals.
- **Inputs**: Feature task plans, round assignments, tier-based concurrency limit (from `ConcurrencyManager`)
- **Outputs**: Feature status transitions; recovery attempt logs; deferral files
- **Acceptance criteria**:
  - Feature statuses: `pending → running → merged` (success path); `running → paused` (recoverable failure); `running → deferred` (ambiguous intent, human decision required); `running → failed` (unrecoverable)
  - `paused` means a recoverable error (merge conflict, test failure, agent timeout) — paused features auto-retry when the session resumes
  - `deferred` means awaiting explicit human decision — deferred features do not auto-retry. Sources: ambiguous intent (exit report `action: "question"`), CI gate block, or non-APPROVED post-merge review verdict after rework exhaustion
  - A `deferred` feature with a `recoverable_branch` field set is the built-but-merge-blocked recoverable sub-case: its work is built and recoverable on that branch (a genuine merge conflict exhausted repair), distinct from the question-deferral sources above — it is not awaiting a human answer, and is surfaced positively (not as failed/zero-progress) keyed off `recoverable_branch`
  - One feature's failure does not block other features in the same round (fail-forward model)
  - Intra-feature task ordering is preserved: the runner derives batch ordering via `compute_dependency_batches`, keyed on each task's canonical `task_id`, from per-task `Depends on` metadata, so a task never dispatches before its declared prerequisites (`task_id` grammar and `### Task Na` sub-task parseability are owned by `cortex_command/pipeline/parser.py` and `cortex/adr/0010-task-id-is-task-identity-not-number.md`). Genuinely-unparseable ordering metadata still fails the feature loudly rather than degrading silently — an unparseable plan raises `parse_error`, and a dependency reference that resolves to no declared task is a counted feature `failed` naming the offending id. The fail-forward model governs whole-feature units, not silent mis-dispatch of tasks within a feature
  - Per-feature recovery metadata is tracked: `recovery_attempts` and `recovery_depth` counters
  - When a feature reaches terminal `failed`, an end-of-round sweep transitions every not-yet-terminal feature whose `intra_session_blocked_by` lists it to `failed` with reason `blocker_failed`, re-applying to a fixpoint so transitive chains resolve. A `paused` blocker (recoverable) does not cascade; only terminal `failed` triggers it.
- **Priority**: must-have

### Overnight Runner Supervision

- **Description**: Each spawned child subprocess (orchestrator, batch_runner) is guarded by an in-process stall watchdog that resets on child progress (see the Acceptance criteria below for how this relates to the out-of-process guardian).
- **Acceptance criteria**:
  - In-process stall watchdog: per spawned child (orchestrator, batch_runner), a monotonic
    inactivity timer (`STALL_TIMEOUT_SECONDS`, 1800s) that RESETS on each child-progress write
    to the watched child signal (batch → `pipeline-events.log`; orchestrator → its stream-json
    stdout, which requires `--output-format=stream-json --verbose --include-partial-messages`),
    plus a never-reset `ABSOLUTE_CEILING_SECONDS` (14400s) backstop for a loud-but-stuck child.
    This is distinct from and strictly inside the guardian's `WEDGED_STALENESS_SECONDS` (2700s)
    parent-staleness window; the watchdog owns child silence, the guardian owns parent/host wedge.
- **Priority**: must-have

### Conflict Resolution

- **Description**: When a feature branch produces a merge conflict, the pipeline classifies the conflict and applies the appropriate resolution strategy before the human reviews the session.
- **Inputs**: Conflicted merge; list of conflicted files
- **Outputs**: Resolved merge or feature paused/deferred; repair agent commit (if applicable)
- **Acceptance criteria**:
  - Conflicts with ≤3 affected files and no "hot files" (critical shared files) use the trivial fast path: `git checkout --theirs` per file, complete merge, run test gate
  - Complex conflicts dispatch a Sonnet repair agent on an isolated worktree
  - If Sonnet fails (unresolved markers or deferral in exit report), escalate once to Opus
  - Repair attempt cap applies: single escalation (Sonnet → Opus) for merge conflicts (see `## Architectural Constraints` → "Repair attempt cap")
  - If repair fails after escalation on a genuine merge conflict, the in-progress merge is aborted before returning and the feature is routed to recoverable `deferred` with its `recoverable_branch` set (built-but-merge-blocked: not re-queued, not auto-retried, surfaced positively); non-conflict / systemic merge failures remain `paused` and feed the systemic circuit breaker
  - Test gate runs after any resolution; on gate failure, repair branch is cleaned up
- **Priority**: must-have

### Post-Merge Review

- **Description**: After a feature merges successfully, the pipeline checks whether it qualifies for spec-compliance review per the tier/criticality gating matrix. Qualifying features are reviewed by a fresh agent; non-qualifying features skip directly to completion.
- **Inputs**: Merged feature; `cortex/lifecycle/{feature}/events.log` (tier and criticality); `cortex/lifecycle/{feature}/spec.md` (review benchmark); gating matrix
- **Outputs**: `cortex/lifecycle/{feature}/review.md` (review artifact with verdict JSON); `review_verdict` event in per-feature events.log; deferral file if non-APPROVED after rework
- **Acceptance criteria**:
  - Gating matrix: complex tier at any criticality → review; simple tier at high/critical → review; simple tier at low/medium → skip
  - Review agent dispatched via `dispatch_review()` in `cortex_command/pipeline/review_dispatch.py`; batch_runner owns all `events.log` writes; review agent writes only `review.md`
  - 2-cycle rework loop: CHANGES_REQUESTED cycle 1 → write feedback to `orchestrator-note.md` → dispatch fix agent → SHA circuit breaker → re-merge (`ci_check=False`) → cycle 2 review
  - Non-APPROVED after cycle 2, REJECTED at any cycle, or review agent failure → feature status `deferred`; deferral file written for morning triage
  - APPROVED at any cycle → `review_verdict`, `phase_transition`, and `feature_complete` events written to per-feature events.log; feature proceeds to merged flow
  - Morning review synthetic events (`review_verdict: APPROVED, cycle: 0`) gated on the same matrix — only written for features that legitimately skip review
  - On a substantive non-APPROVED outcome (REJECTED, or CHANGES_REQUESTED after rework), the feature's live merge commit is reverted SHA-anchored under `ctx.lock` before deferring; the one exception is a dependent-conflict revert that aborts and surfaces as a blocking deferral naming the dependent feature. The verdict-ERROR outcome splits on whether the review *agent* itself ran: a **genuine dispatch crash** (`DispatchResult.success == False` or a raised exception) reverts the merge, feeding the systemic breaker under the `review_dispatch_crash` cause class; a **could-not-run review** (the agent completed but produced no parseable verdict) **preserves** the merge on the integration branch (`merge_reverted=False`, the positive `could_not_run` discriminator), surfaces it on the morning report and integration PR for human re-review, and feeds the systemic breaker under the distinct `review_no_artifact` cause class. Review gating applies uniformly at every merge-to-`merged` site (primary, post-recovery re-merge, and the repair_completed ff-merge). The systemic breaker counts crash + no-artifact failures in **aggregate** against `SYSTEMIC_FAILURE_THRESHOLD` (a mixed batch still trips). Rationale, the full could-not-run/crash split, and the safety-boundary relocation are recorded in `cortex/adr/0015-review-could-not-run-vs-dispatch-crash-split.md`; the module-internals view is in `docs/internals/pipeline.md`.
- **Priority**: must-have

### Post-Merge Test Failure Recovery

- **Description**: When a feature merges successfully but breaks the test suite, the pipeline attempts automated recovery before surfacing to the human.
- **Inputs**: Post-merge test failure; learnings from prior attempts; integrated branch state
- **Outputs**: Tests passing (recovered) or feature paused with recovery log
- **Acceptance criteria**:
  - Flaky guard runs first: re-merge with no feature changes; if tests pass, feature is marked `merged` with `flaky=True` recorded
  - If flaky guard fails, dispatch repair agent (Sonnet); escalate to Opus on failure
  - Repair attempt cap applies: max 2 attempts (Sonnet + Opus) (see `## Architectural Constraints` → "Repair attempt cap")
  - Circuit breaker: if repair agent produces no new commits (before_sha == after_sha), feature pauses immediately
  - Each attempt appends learnings to `cortex/lifecycle/{feature}/learnings/progress.txt`
  - Recovery outcome is recorded in `cortex/lifecycle/{feature}/recovery-log.md`
- **Priority**: must-have

### Deferral System

- **Description**: When the pipeline encounters an ambiguous decision that cannot be resolved autonomously, it writes a structured deferral question and surfaces it in the morning report.
- **Inputs**: Worker exit report declaring `action: "question"`; CI gate block; repair agent declaring deferral
- **Outputs**: Deferral file at `lifecycle/deferred/{feature}-q{NNN}.md`; feature status transitions to `deferred` (blocking) or continues (non-blocking); escalation entry in `cortex/lifecycle/sessions/{session_id}/escalations.jsonl`
- **Acceptance criteria**:
  - Deferral files are written atomically
  - Blocking deferrals pause the feature; non-blocking deferrals allow the feature to continue using the recorded `default_choice`
  - Deferral files include: severity (blocking / non-blocking / informational), context, question, options considered, pipeline action attempted, and optional default choice
- **Priority**: must-have

### Metrics and Cost Tracking

- **Description**: The pipeline collects execution metrics from lifecycle event logs for post-session review and calibration.
- **Inputs**: `cortex/lifecycle/*/events.log` (JSONL event streams per feature)
- **Outputs**: `cortex/lifecycle/metrics.json` with per-feature metrics, tier aggregates, and calibration summaries
- **Acceptance criteria**:
  - Metrics are computed by parsing `feature_complete` events; in-progress features are excluded
  - Per-feature metrics: complexity tier, task count, batch count, rework cycles, review verdicts, phase durations, total duration
  - Tier aggregates: mean duration, task count, batch count, rework cycles, and approval rate per tier (simple / complex)
  - Backfilled synthetic timestamps (T00:0X:00Z pattern) are detected; phase durations involving them are marked `null`
  - Duplicate `feature_complete` events: last one per feature is canonical
- **Priority**: should-have

### Post-Session Sync

- **Description**: After morning review merges the overnight PR, local `main` diverges from remote (local has the morning report commit and review artifacts; remote has the PR merge commit). A post-merge sync step rebases local onto remote, resolves conflicts in overnight-managed files automatically, and pushes.
- **Inputs**: `cortex_command/overnight/sync-allowlist.conf` (glob patterns for auto-resolvable files), local `main` branch state, remote `origin/main` after PR merge
- **Outputs**: Local `main` synced and pushed to `origin/main`; conflicts in allowlist files auto-resolved with `--theirs`, which during a rebase keeps the local/replayed revision
- **Acceptance criteria**:
  - After sync completes successfully, `git rev-list HEAD..origin/main --count` = 0 and `git rev-list origin/main..HEAD --count` = 0 (local and remote identical)
  - Conflicts in files matching `sync-allowlist.conf` patterns are auto-resolved with `--theirs`. Git swaps the ours/theirs nomenclature during a rebase — the remote commits are checked out first and the local commits replayed on top — so `--theirs` names the replayed side and the **local** version survives, not the remote/overnight one. Whether local is the side that should win is an open question tracked separately; this criterion records the behavior rather than endorsing it
  - Any conflict outside the allowlist aborts the rebase and exits non-zero, leaving no partial resolution behind; every unresolved path is named so the user can finish the sync by hand
  - Multi-pass resolution handles sequential conflicts from replaying multiple local-only commits
  - Dirty rebase state (`.git/rebase-merge/` or `.git/rebase-apply/` from a prior crash) is detected and cleaned up before sync
  - The `--merge` PR merge strategy is a load-bearing dependency — `--theirs` semantics during rebase depend on it
- **Priority**: must-have

## Non-Functional Requirements

- **Atomicity**: All session state writes use tempfile + `os.replace()` — no partial-write corruption
- **Concurrency safety**: see `## Architectural Constraints` → "State file locking" for the no-lock design and its safety rationale
- **Graceful degradation**: Budget exhaustion and rate limits pause the session rather than crashing it
- **Audit trail**: `cortex/lifecycle/pipeline-events.log` provides an append-only JSONL record of all dispatch and merge events
- **Orchestrator rationale convention**: When the orchestrator resolves an escalation or makes a non-obvious feature selection decision (e.g., skipping a feature, reordering rounds), the relevant events.log entry should include a `rationale` field explaining the reasoning. Routine forward-progress decisions do not require this field.

## Architectural Constraints

- **State file locking**: State file reads are not protected by locks by design. Writers use atomic `os.replace()`; readers may observe a state mid-mutation, but forward-only transitions make this safe. This is a permanent architectural constraint.
- **Repair attempt cap**: The repair attempt limit (max 2 attempts for test failures; single Sonnet → Opus escalation for merge conflicts) is a fixed architectural constraint. It is cost-bounded and circuit-breaker backed; unlimited retries would be cost-prohibitive for autonomous overnight sessions.
- **Integration branch persistence**: Integration branches (`overnight/{session_id}`) are not auto-deleted after session completion. They persist for manual PR creation and review.
- **Dashboard access**: The web dashboard is unauthenticated and accessible to any host on the local network (binds to `0.0.0.0`) by design (see `requirements/observability.md`).

## Dependencies

- `cortex/lifecycle/overnight-state.json` — session state (atomic writes)
- `cortex/lifecycle/master-plan.md` — batch session plan
- `cortex/lifecycle/{feature}/plan.md` — per-feature task plans
- `cortex/lifecycle/pipeline-events.log` — JSONL event audit log
- `cortex/lifecycle/deferred/` — deferral question files
- `cortex/lifecycle/sessions/{session_id}/escalations.jsonl` — escalation audit log
- `cortex_command/overnight/sync-allowlist.conf` — glob patterns for auto-resolvable files during post-merge sync
- `bin/cortex-git-sync-rebase` — post-merge sync script
- Multi-agent orchestration (see `requirements/multi-agent.md`) — agent spawning, worktrees, model selection
- Smoke test gate (`cortex_command/overnight/smoke_test.py`) — post-merge verification
- `cortex/lifecycle/sessions/{session_id}/runner.pid` — per-session runner IPC contract (JSON schema, mode 0o600, atomic write); see `docs/overnight-operations.md` "Runner concurrency guard" for the schema fields and the magic/start_time verification detail.
- `~/.local/share/overnight-sessions/active-session.json` — host-global active-session pointer sharing the `runner.pid` schema plus a `phase` field; a transient `phase: "starting"` value is observable during the spawn handshake window but is never persisted. See `docs/overnight-operations.md`, `docs/internals/mcp-contract.md`, and `docs/internals/pipeline.md`.
- `cortex mcp-server` exposes the overnight MCP tool surface (`overnight_start_run`, `overnight_status`, `overnight_logs`, `overnight_cancel`, `overnight_list_sessions`) wrapping `cli_handler` boundaries. See `docs/mcp-server.md`.
- Pre-install in-flight guard: `cortex` aborts during an active overnight session; bypassable inline via `CORTEX_ALLOW_INSTALL_DURING_RUN=1` (do NOT export). See `docs/mcp-server.md` for carve-outs and the export-danger note.
- `cortex/lifecycle/sessions/{session_id}/runner-bootstrap.log` — pre-`events.log`-init failure diagnostics on the MCP-spawned start path. See `docs/mcp-server.md`.
- `~/.cache/cortex-command/scheduled-launches.json` — sidecar index of pending LaunchAgent schedules. See `docs/overnight-operations.md` "Scheduled Launch".
- `~/.cache/cortex-command/scheduled-launches.lock` — companion lockfile serializing concurrent `cortex overnight schedule` invocations. See `docs/overnight-operations.md` "Scheduled Launch".
- `cortex/lifecycle/sessions/{session_id}/sandbox-settings/cortex-sandbox-*.json` — per-spawn sandbox settings tempfiles. See `docs/internals/pipeline.md` "Allowed write paths" and `docs/overnight-operations.md` "Per-spawn sandbox enforcement".

## Edge Cases

- **Resumed session**: Features already at `merged` are skipped via idempotency tokens; `paused` features re-enter the execution queue
- **Plan hash mismatch on resume**: Session detects change and logs a warning; continues with current plan
- **TMPDIR cleared between sessions**: Stale integration worktree paths are re-created on next access; git tracking is pruned and retried
- **All features pause in a round**: Circuit breaker fires; no further features dispatched; morning report surfaces reason
- **Feature paused with no recovery attempts remaining**: Status transitions to `paused` permanently until human intervenes
- **Hardcoded `.vscode`/`.idea` sandbox denies**: Claude Code's binary permanently blocks writes to these directories even when the path is in `sandbox.filesystem.allowWrite`; see `docs/overnight-operations.md` "Edge Cases" for workarounds (sparse checkout, `excludedCommands`, or `dangerouslyDisableSandbox`).

## Open Questions

- None
