---
schema_version: "1"
uuid: 925f1d1f-6ba3-4daa-b4b1-037aa0785457
title: "Extract outcome_router module from batch_runner"
status: complete
priority: high
type: feature
created: 2026-04-13
updated: 2026-04-14
parent: "074"
blocked-by: ["075"]
tags: [overnight-runner, refactor, modularization]
areas: [overnight-runner]
discovery_source: research/implement-in-autonomous-worktree-overnight-component-reuse/research.md
session_id: null
lifecycle_phase: plan
lifecycle_slug: extract-outcome-router-module-from-batch-runner
complexity: complex
criticality: high
---

## Scope

Extract feature-result routing and policy from `batch_runner.py` into a
new module `claude/overnight/outcome_router.py` (~900–1000 LOC target).
Phase 2 of the three-phase batch_runner decomposition.

## What moves

Outcome routing today is split across `_apply_feature_result`
(lines 1203–1532) AND the inline body of `_accumulate_result`
(lines 1598–1984). Both must move:

- `_apply_feature_result` central dispatch and all status-routing
  branches (merged, paused, deferred, failed, repair_completed)
- From `_accumulate_result` (in-place inline outcome routing, not a
  "one-line call"): `merge_feature` invocation and merged-path
  handling (~1676–1778), CI deferral (~1780–1825), and the entire
  post-merge test-recovery path (~1842–1983)
- Review gating: `dispatch_review` invocation, verdict routing, rework
  cycle handling
- Backlog write-back: `_write_back_to_backlog`,
  `_find_backlog_item_path`
- Circuit-breaker detection and firing (consumes
  `consecutive_pauses_ref`)
- Event logging for outcome transitions

## Shared helpers (stay in orchestrator layer)

The following helpers are used by both `execute_feature`-side
(feature_executor, #075) and outcome-routing-side logic. They stay in
batch_runner.py (renamed orchestrator.py in #077) and both new modules
import them:

- `_next_escalation_n`, `_get_changed_files`, `_classify_no_commit`
- `_effective_base_branch`, `_effective_merge_repo_path`
- `cleanup_worktree` call patterns (direct re-imports from state.py)

## What stays in batch_runner (now orchestrator)

- `_run_one` remains; its body collapses from calling
  `execute_feature` + large inline `_accumulate_result` into calling
  `feature_executor.execute_feature` + `outcome_router.apply_feature_result`
- `_run_one` is edited by #075 (import swap) and further simplified by
  #076 (remove inline outcome logic); relocated by #077 (file rename).
  Each ticket touches the same function but in non-overlapping ways

## Shared state plumbing

`consecutive_pauses_ref` (circuit breaker) and `recovery_attempts_map`
(post-merge recovery) continue as mutable arguments passed across the
executor → router seam. Research acknowledged this is a tangle
(research.md "Open Questions"); clean-up into a small
`CircuitBreakerState` / recovery-state dataclass happens
opportunistically during #077 or deferred to a follow-up. Out of scope
for this ticket.

## FeatureResult contract

`FeatureResult` is treated as a frozen API between feature_executor and
outcome_router for this ticket. Any restructuring (typed variants per
status, validation, field-owner documentation) is a prerequisite
landing before #075 — not part of #076.

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
