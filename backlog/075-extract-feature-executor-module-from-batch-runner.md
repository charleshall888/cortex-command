---
schema_version: "1"
uuid: 6d1b3bfb-cec8-4cc9-9788-03052b97249d
title: "Extract feature_executor module from batch_runner"
status: backlog
priority: high
type: feature
created: 2026-04-13
updated: 2026-04-13
parent: "074"
blocked-by: ["080"]
tags: [overnight-runner, refactor, modularization]
areas: [overnight-runner]
discovery_source: research/implement-in-autonomous-worktree-overnight-component-reuse/research.md
---

## Scope

Extract per-feature execution from `claude/overnight/batch_runner.py` into
a new module `claude/overnight/feature_executor.py` (~600 LOC target).
Phase 1 of the three-phase batch_runner decomposition.

## What moves

- `execute_feature()` and its helpers
- Per-feature context loading: `_read_spec_content`, `_read_learnings`,
  `_render_template`, `_get_spec_path`
- Idempotency management: `_compute_plan_hash`,
  `_make_idempotency_token`, `_check_task_completed`,
  `_write_completion_token`
- Exit-report validation: `_read_exit_report`
- Brain-agent triage: `_handle_failed_task`
- Conflict recovery policy (trivial fast-path, repair agent dispatch,
  budget gate)
- Git state inspection: `_get_changed_files`, `_classify_no_commit`

## What stays in batch_runner

- Session-level orchestration (`run_batch`, `_run_one`, heartbeat, final
  state write-back)
- Result dispatch (`_apply_feature_result` AND the outcome-routing
  portions of `_accumulate_result`) — that's Phase 2 (#076)
- Concurrency management, circuit breaker
- Shared helpers (`_next_escalation_n`, `_get_changed_files`,
  `_classify_no_commit`, `_effective_base_branch`,
  `_effective_merge_repo_path`) — used by both #075 and #076; both
  import from orchestrator layer

## `_run_one` editing protocol

`_run_one` is touched by #075 (signature adaptation when
`execute_feature` is imported from the new module), #076 (collapse
inline outcome routing), and #077 (relocate to orchestrator.py). Each
ticket edits it in non-overlapping ways; document the expected post-
#075 shape in the PR to reduce merge-conflict risk with #076.

## FeatureResult contract

`FeatureResult` today is a data bag with 10+ conditional fields whose
meaning depends on `status` (e.g., `repair_branch`, `trivial_resolved`,
`resolved_files`, `repair_agent_used`, `deferred_question_count`,
`parse_error`, `error_type`). Before extraction, this ticket freezes
the field inventory and documents the status-to-field mapping in
`feature_executor.py` (or a small shared types module). Any subsequent
restructuring is a follow-up.

## Repair-branch coordination

The `status="repair_completed"` flow spans both #075 (conflict recovery
produces the repair branch in execute_feature) and #076 (outcome
router fast-forward-merges the repair branch via
`_apply_feature_result`). Field contract (see above) is the
coordination boundary; any change to repair-path fields requires
matching updates in both tickets.

## Acceptance

- `feature_executor.execute_feature()` has a clean public signature;
  no imports from batch_runner into feature_executor
- Existing overnight run completes successfully end-to-end (regression
  gate)
- Unit tests for the pure helpers: idempotency token generation, plan
  hash computation, exit-report parsing, context loading
- Existing pipeline/overnight test suites continue to pass

## Research Context

See `research/implement-in-autonomous-worktree-overnight-component-reuse/research.md`
for the full responsibility map of `batch_runner.py` (15 conceptual
buckets) and the rationale for the 3-way decomposition (Candidate A).
Prior art: `claude/pipeline/review_dispatch.py` was successfully
extracted along this same pattern.
