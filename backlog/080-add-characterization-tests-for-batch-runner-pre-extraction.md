---
schema_version: "1"
uuid: efce9b8c-daca-4f01-b15c-929825d64a91
title: "Add characterization tests for batch_runner pre-extraction"
status: backlog
priority: high
type: chore
created: 2026-04-13
updated: 2026-04-13
parent: "074"
tags: [overnight-runner, refactor, modularization, tests]
areas: [overnight-runner]
discovery_source: research/implement-in-autonomous-worktree-overnight-component-reuse/research.md
---

## Scope

Capture current behavior of `batch_runner.py` as golden-master /
characterization tests **before** the three-phase extraction (#075,
#076, #077) begins. These tests are the regression oracle that lets
each extraction PR prove "before == after" programmatically rather
than relying on stochastic multi-hour overnight runs as the only gate.

## What to pin

Characterization tests should capture input/output fixtures for the
highest-risk surfaces of `batch_runner.py` — the functions being moved
by #075 and #076. Minimum targets:

- **`execute_feature`** (lines 662–1066): Given representative plan +
  spec + worktree state + mock `dispatch_task`/`retry_task`/
  `dispatch_repair_agent` outputs, assert the returned `FeatureResult`
  (status + all conditional fields) and the sequence of events written
  to the events.log.
- **`_handle_failed_task`** (lines 496–576): Given brain-decision
  fixtures (SKIP / DEFER / PAUSE), assert the returned `FeatureResult`
  (or None), any deferral files written, and `consecutive_pauses_ref`
  mutations.
- **`_apply_feature_result`** (lines 1203–1532): Given each
  `FeatureResult.status` variant (merged, paused, deferred, failed,
  repair_completed), assert `batch_result` mutations, backlog
  write-back calls, event-log entries, and `consecutive_pauses_ref`
  increments. Mock `merge_feature`, `dispatch_review`, backlog
  `update_item`.
- **`_accumulate_result`** inline outcome routing (1598–1984): Given
  representative merge / review / test-recovery outcomes, assert the
  same surfaces (batch_result, backlog, events, circuit breaker).
- **Conflict-recovery branching** (lines 679–825): Given each conflict
  fixture (trivial-eligible vs. not, recovery_attempts budget
  exhausted vs. available), assert `FeatureResult` outcomes.

## Fixtures

Fixtures live under `claude/overnight/tests/fixtures/batch_runner/`
and consist of:

- Representative feature/plan/spec markdown
- Representative `BatchConfig` dataclasses
- Representative `FeatureResult` instances (one per status variant)
- Representative dispatch/retry/review mock return values
- Expected events.log output sequences (JSONL)

## Acceptance

- Tests run in under 60 seconds (fixtures mock all agent calls and
  subprocess git operations)
- Pin behavior for every `FeatureResult.status` variant currently
  produced by `execute_feature` and consumed by `_apply_feature_result`
- Pin behavior for the conflict-recovery branching (trivial /
  repair-agent / budget-exhausted)
- Pin `consecutive_pauses_ref` and `recovery_attempts_map` mutation
  sequences across a representative multi-feature batch
- Tests pass against current `batch_runner.py`; will remain the
  regression gate across #075, #076, #077 PRs

## Why this blocks #075

`batch_runner.py` has no dedicated unit tests today (research.md
"Test coverage" section). The extraction chain #075 → #076 → #077
refactors ~1500 LOC of untested, side-effectful, stochastic code. The
existing test suites cover adjacent modules but do not exercise
`execute_feature` or `_apply_feature_result` as SUT. Without
characterization fixtures, the only regression oracle is a
multi-hour overnight run per PR — not a PR-reviewable gate.

This ticket closes the oracle gap before the first extraction lands.

## Scope excludes

- Any extraction or renaming (that's #075/#076/#077)
- Full end-to-end overnight-session tests (fixtures mock at the
  agent-dispatch boundary, not the CLI boundary)
- Characterization of session-layer concerns (ConcurrencyManager,
  round loop, heartbeat) — those are covered by #077's integration
  tests
