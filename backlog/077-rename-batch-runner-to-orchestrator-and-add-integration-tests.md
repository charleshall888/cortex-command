---
schema_version: "1"
uuid: 077bf623-337c-476a-88c9-30a625fa86a3
title: "Rename batch_runner to orchestrator and add integration tests"
status: complete
priority: high
type: feature
created: 2026-04-13
updated: 2026-04-14
parent: "074"
blocked-by: []
tags: [overnight-runner, refactor, modularization]
areas: [overnight-runner]
discovery_source: research/implement-in-autonomous-worktree-overnight-component-reuse/research.md
session_id: null
lifecycle_phase: complete
lifecycle_slug: rename-batch-runner-to-orchestrator-and-add-integration-tests
complexity: complex
criticality: high
---

## Scope

Complete the three-phase batch_runner decomposition. Move the remaining
session-layer logic into `claude/overnight/orchestrator.py` and retain
`batch_runner.py` as a thin CLI wrapper preserving the
`python3 -m cortex_command.overnight.batch_runner` contract. Add integration
tests for `orchestrator.run_batch`.

## What moves into orchestrator.py

- `run_batch()` top-level async loop
- `_run_one()` (thin: feature_executor → outcome_router)
- `_accumulate_result()` (collapsed to single call into outcome_router)
- Heartbeat background task
- Session state initialization (spec_paths, backlog_ids,
  recovery_attempts, repo_paths, integration branches/worktrees)
- Worktree creation for all features
- Final persistence (recovery_attempts write-back, budget-exhausted
  pause, session phase transitions)
- Global constraints (circuit breaker check gate, abort signal
  propagation)

## What batch_runner.py becomes

- ~30 LOC: argparse parser, `BatchConfig` construction,
  `asyncio.run(run_batch(config))`
- `build_parser()` and `_run()` preserved for CLI contract

## Parallelism note

#077 does not block #078. The daytime pipeline (#078) consumes
`feature_executor.execute_feature` and `outcome_router.apply_feature_result`
directly — it does not import from `orchestrator.py` or `batch_runner.py`.
After #076 lands, #077 (rename + integration tests) and #078 (daytime
CLI) can run in parallel.

## `consecutive_pauses_ref` / `recovery_attempts_map` cleanup

If #076 left the shared-mutable plumbing as-is, #077 may opportunistically
convert `consecutive_pauses_ref` into a small `CircuitBreakerState`
dataclass and `recovery_attempts_map` into a named object passed through
the orchestrator seam. Not mandatory; decide during spec.

## Acceptance

- CLI invocation (`python3 -m cortex_command.overnight.batch_runner --plan …
  --batch-id …`) works unchanged
- Full overnight run completes end-to-end (final regression gate for the
  three-phase refactor)
- Integration tests for `orchestrator.run_batch` covering: multi-feature
  batch with mocked feature_executor + outcome_router; concurrency
  semaphore; circuit-breaker firing; budget exhaustion; heartbeat events
- `consecutive_pauses_ref` plumbing cleaned up opportunistically (small
  dataclass or kept as list — decide during spec)

## Research Context

See `research/implement-in-autonomous-worktree-overnight-component-reuse/research.md`,
"Implementation phasing" section. Consider sequencing with #073
(overnight docs) — landing #073 first lets its architectural diagrams
reference the target shape.
