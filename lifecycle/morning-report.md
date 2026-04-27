# Morning Report: 2026-04-21

## Executive Summary

**Verdict**: Significant issues
- Features completed: 0/3
- Features deferred: 0 (questions need answers)
- Features failed: 3 (paused, need investigation)
- Rounds completed: 1
- Duration: 0h 5m

## Completed Features

No features completed in this run.

## Requirements Drift Flags

### add-hook-based-preprocessing-for-test-build-output

- The output filter hook introduces a new global behavior (PreToolUse command rewriting for test runners) and a new per-project convention (`.claude/output-filters.conf`) that are not reflected in `requirements/project.md`. The project requirements mention "defense-in-depth for permissions" and hooks generally but do not describe output/context efficiency optimization as a stated goal or architectural pattern.

### add-overnight-session-observability-from-within-claude-code-sandbox

- The `bin/overnight-status` script and `/overnight status` subcommand add a new observability tool for overnight sessions (file-based status reporting from within the sandbox). This capability is not reflected in `requirements/observability.md`, which covers the statusline, dashboard, and notification subsystems but does not mention a CLI-based session status tool.
- The `setup-tmux-socket` recipe adds tmux socket allowlisting to enable sandboxed sessions to access tmux. This sandbox configuration capability is not captured in any requirements document.

### build-daytime-pipeline-module-and-cli

- The `requirements/pipeline.md` Deferral System section (line 87-92) specifies deferral files at `lifecycle/deferred/{feature}-q{NNN}.md` (repo-root-level `deferred/` directory). The new per-feature deferral path (`lifecycle/{feature}/deferred/`) introduced by this implementation is an intentional behavioral change — per-feature deferral isolation — but `requirements/pipeline.md` still describes the old repo-root path. The Outputs field reads: "Deferral file at `lifecycle/deferred/{feature}-q{NNN}.md`".
- The `requirements/pipeline.md` Dependencies section (line 144) lists `lifecycle/deferred/` as a dependency, which is now superceded for daytime runs by `lifecycle/{feature}/deferred/`.
- Neither `requirements/project.md` nor `requirements/multi-agent.md` requires updating — the daytime pipeline is additive and consistent with the existing autonomy/worktree model.

### close-exfiltration-channels-in-sandbox-excluded-commands

- The implementation introduces security hardening for the permission allow/deny list (exfiltration channel closure). The project requirements (`requirements/project.md`) describe the project scope ("Global agent configuration (settings, hooks, reference docs)") but contain no mention of security posture, permission management, or sandbox hardening as a quality attribute or architectural concern. This is a new behavioral domain not yet reflected in requirements.

### define-evaluator-rubric-for-software-features-spike

- The research.md investigation documents that `batch_runner.py` never dispatches the post-implementation review phase, and that the morning review skill (`walkthrough.md` §2b) unconditionally writes synthetic `review_verdict: APPROVED` events at `cycle: 0` for all merged features. Neither the review-dispatch gap nor the synthetic-approval behavior is described in `requirements/pipeline.md`. The pipeline requirements describe feature execution succeeding at merge + test gate passage — they do not mention a review phase dispatch step, a gating matrix, or the condition under which review_verdict events are written. The spike's backlog ticket (043) targets correcting this behavior, but the requirements doc does not yet reflect the intended future behavior either.
- `requirements/pipeline.md`'s "Metrics and Cost Tracking" section lists `review verdicts` as a per-feature metric (`lifecycle/*/events.log` → `lifecycle/metrics.json`), which implies reviews happen — but the pipeline requirements contain no requirement for when or whether the review phase is dispatched. This is an implicit assumption not stated as a requirement.

### define-output-floors-for-interactive-approval-and-overnight-compaction

- The output floors reference document introduces a new "rationale" field convention for orchestrator events.log entries. This convention (orchestrator decision rationale captured in a `rationale` field on events.log entries when resolving escalations or making non-obvious feature selection decisions) is not reflected in `requirements/pipeline.md`, which defines the pipeline event log format and orchestrator behavior. The pipeline requirements doc's "Session Orchestration" section describes outputs including `pipeline-events.log` and the "Deferral System" section covers escalation handling, but neither mentions the rationale field convention.

### fix-overnight-runner-silent-crash-signal-handling-unregistered-events-and-batch-plan-path-mismatch

- The pipeline requirements (`requirements/pipeline.md`) describe graceful degradation ("Budget exhaustion and rate limits pause the session rather than crashing it") and audit trail, but do not explicitly mention signal handling (SIGHUP/SIGTERM/SIGINT) as a graceful degradation trigger. The implementation now treats SIGHUP as a first-class signal that triggers cleanup, state transition to paused, and partial morning report generation -- this behavior is not captured in the requirements.
- The pipeline requirements do not mention the event type registration allowlist (`EVENT_TYPES`) as an architectural constraint, despite it being load-bearing for data quality validation. The spec's non-requirements section explicitly states "Do NOT remove the EVENT_TYPES allowlist -- it provides data quality validation for the events log."

### investigate-overnight-morning-review-git-sync-gaps

- The post-merge sync step (Section 6a) and the `git-sync-rebase.sh` script introduce new pipeline behavior -- local/remote main synchronization after PR merge with pattern-based conflict resolution -- that is not reflected in `requirements/pipeline.md`. The pipeline requirements document session orchestration, feature execution, conflict resolution (during overnight execution), and metrics, but do not mention the morning review sync flow or the allowlist-based rebase resolution.
- The sync-allowlist.conf introduces a new shared configuration artifact for the pipeline that is not listed in the Dependencies section of `requirements/pipeline.md`.

### schedule-overnight-runs

- The `scheduled_start` field and scheduling capability are new behaviors not reflected in `requirements/project.md` or any area requirements. The project requirements mention "Overnight execution framework, session management, and morning reporting" (In Scope) but do not specifically mention scheduling or delayed launch.

### wire-requirements-drift-check-into-lifecycle-review

- The `render_pending_drift()` function (lines 598-659 of report.py) introduces a new top-level morning report section `## Requirements Drift Flags` that is not described in `requirements/project.md`. This is new morning reporting behavior (scanning non-completed features for drift) that extends the overnight execution framework's reporting capabilities beyond what project requirements currently document.

### wire-review-phase-into-overnight-runner

- The pipeline requirements (`requirements/pipeline.md`) document the feature execution lifecycle as `pending -> running -> merged/paused/failed/deferred` but do not mention a review phase, review gating matrix, or post-merge review dispatch. The new behavior where qualifying features go through a review cycle (with potential rework loop) between merge and completion is not reflected.
- The pipeline requirements list per-feature metrics including "review verdicts" in the Metrics section, suggesting review was anticipated, but the actual gating mechanism and dispatch flow are not described as functional requirements.
- The deferral system requirements do not mention review-originated deferrals as a deferral source.

## Deferred Questions (0)

No questions were deferred — all ambiguities were resolved by the pipeline.

## Failed Features (3)

### add-uncommitted-changes-guard-to-lifecycle-implement-phase-pre-flight: Plan parse error: [Errno 2] No such file or directory: 'lifecycle/archive/add-uncommitted-changes-guard-to-lifecycle-implement-phase-pre-flight/plan.md'
- Retry attempts: 0
- Circuit breaker: not triggered
- Learnings: `lifecycle/archive/add-uncommitted-changes-guard-to-lifecycle-implement-phase-pre-flight/learnings/progress.txt`
- **Suggested next step**: Review learnings, retry or investigate

### fix-daytime-pipeline-worktree-atomicity-and-stderr-logging: Plan parse error: [Errno 2] No such file or directory: 'lifecycle/fix-daytime-pipeline-worktree-atomicity-and-stderr-logging/plan.md'
- Retry attempts: 0
- Circuit breaker: not triggered
- Learnings: `lifecycle/fix-daytime-pipeline-worktree-atomicity-and-stderr-logging/learnings/progress.txt`
- **Suggested next step**: Review learnings, retry or investigate

### replace-daytime-log-sentinel-classification-with-structured-result-file: Plan parse error: [Errno 2] No such file or directory: 'lifecycle/archive/replace-daytime-log-sentinel-classification-with-structured-result-file/plan.md'
- Retry attempts: 0
- Circuit breaker: not triggered
- Learnings: `lifecycle/archive/replace-daytime-log-sentinel-classification-with-structured-result-file/learnings/progress.txt`
- **Suggested next step**: Review learnings, retry or investigate

## New Backlog Items

- **#101** [chore] Follow up: add-uncommitted-changes-guard-to-lifecycle-implement-phase-pre-flight — failed
- **#102** [chore] Follow up: fix-daytime-pipeline-worktree-atomicity-and-stderr-logging — failed
- **#103** [chore] Follow up: replace-daytime-log-sentinel-classification-with-structured-result-file — failed

## What to Do Next

1. [ ] Investigate 3 failed features
2. [ ] Run integration tests

## Run Statistics

- Rounds completed: 1
- Per-round timing: Round 1: 5m
- Circuit breaker activations: 0
- Total features processed: 3
