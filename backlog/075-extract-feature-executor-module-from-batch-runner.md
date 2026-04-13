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
- Result dispatch (`_apply_feature_result`) — that's Phase 2
- Concurrency management, circuit breaker

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
