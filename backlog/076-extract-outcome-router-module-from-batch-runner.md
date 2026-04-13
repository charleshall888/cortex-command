---
schema_version: "1"
uuid: 925f1d1f-6ba3-4daa-b4b1-037aa0785457
title: "Extract outcome_router module from batch_runner"
status: backlog
priority: high
type: feature
created: 2026-04-13
updated: 2026-04-13
parent: "074"
blocked-by: ["075"]
tags: [overnight-runner, refactor, modularization]
areas: [overnight-runner]
discovery_source: research/implement-in-autonomous-worktree-overnight-component-reuse/research.md
---

## Scope

Extract feature-result routing and policy from `batch_runner.py` into a
new module `claude/overnight/outcome_router.py` (~700 LOC target).
Phase 2 of the three-phase batch_runner decomposition.

## What moves

- `_apply_feature_result` central dispatch and all status-routing
  branches (merged, paused, deferred, failed, repair_completed)
- Merge orchestration: successful merge paths, CI-gated paths, conflict
  paths, test-failure paths
- Post-merge test-failure recovery (`recover_test_failure` integration,
  gate on `recovery_attempts`)
- Review gating: `dispatch_review` invocation, verdict routing, rework
  cycle handling
- Backlog write-back: `_write_back_to_backlog`,
  `_find_backlog_item_path`
- Circuit-breaker detection and firing (consumes
  `consecutive_pauses_ref`)
- Event logging for outcome transitions

## What stays in batch_runner (now orchestrator)

- `_run_one` becomes a thin caller that invokes
  `feature_executor.execute_feature` then
  `outcome_router.apply_feature_result`
- `_accumulate_result` collapses to a one-line call

## Acceptance

- `outcome_router.apply_feature_result()` has a clean signature; policy
  decisions (is review needed? is conflict trivial? is recovery budget
  exhausted?) are centralized inside this module
- Existing overnight run completes end-to-end (regression gate)
- Unit tests for outcome routing with mocked `merge_feature` and
  `dispatch_review`; assert status transitions, backlog write-back calls,
  circuit-breaker firing at threshold
- No regressions in existing pipeline/overnight test suites

## Research Context

See `research/implement-in-autonomous-worktree-overnight-component-reuse/research.md`
— the "policy/mechanism separation opportunities" section enumerates the
specific tangles this extraction resolves (brain triage, merge
orchestration, conflict recovery, backlog write-back scatter).
