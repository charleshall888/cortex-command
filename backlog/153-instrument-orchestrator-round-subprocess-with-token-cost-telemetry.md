---
schema_version: "1"
uuid: 686003ea-c115-4a5c-82c1-9a01619711ee
title: "Instrument orchestrator-round subprocess with token-cost telemetry"
status: in_progress
priority: low
type: feature
blocked-by: []
tags: [overnight, pipeline, observability]
areas: [overnight-runner]
created: 2026-04-29
updated: 2026-04-29
complexity: complex
criticality: high
spec: lifecycle/instrument-orchestrator-round-subprocess-with-token-cost-telemetry/spec.md
session_id: 157138c0-cc98-419b-a987-deaaf056c325
lifecycle_phase: plan
---

# Instrument orchestrator-round subprocess with token-cost telemetry

## Problem

Ticket 104's per-skill pipeline aggregator (`compute_skill_tier_dispatch_aggregates` in `cortex_command/pipeline/metrics.py`) groups dispatch records by `skill` to surface per-skill token costs. Every existing `Skill` value (`implement`, `review`, `review-fix`, `conflict-repair`, `merge-test-repair`, `integration-recovery`, `brain`) is dispatched **inside** an orchestrator session via `dispatch_task`, which captures usage from the SDK return.

The orchestrator-round itself — the top-level `claude -p` subprocess that hosts the orchestrator session — is not instrumented. `runner.py:_spawn_orchestrator` shells out via `subprocess.Popen([claude, "-p", filled_prompt, "--dangerously-skip-permissions", "--max-turns", N])` with no `--output-format json` and no usage capture. As a result, ticket 104's aggregator never produces an `orchestrator-round` bucket, and `claude -p` token costs for the orchestrator are invisible to the per-skill rollup.

This gap was discovered during ticket 111 implementation (Task 4 R11 baseline capture). The R11 baseline fell back to a static measurement from prompt-template + inline-read file sizes (~7,063 tokens) because no live measurement path existed. The post-merge R12 follow-up will hit the same wall: nothing in the rollup will let us compare orchestrator-round token cost before vs. after the aggregator rewrite without re-running the same static estimate.

## Affected files

- `cortex_command/overnight/runner.py` — `_spawn_orchestrator` (around line 682) — add usage capture
- `cortex_command/pipeline/dispatch.py` — `Skill` Literal (line 156) — vocabulary extension
- `cortex_command/pipeline/metrics.py` — confirm aggregator's per-skill bucketing handles a session-scope (no-feature) record

## Out of scope

- Token-cost optimization or model-tier reshuffling of the orchestrator-round itself.
- Instrumentation of the `cortex-batch-runner` subprocess (different code path; if also missing, file separately).
- Backfilling baselines for past sessions — this ticket adds forward-going telemetry only.

## Open questions for refinement

- **Output-format choice**: switch the Popen invocation to `claude -p --output-format=stream-json --include-partial-messages` and parse the streaming JSON inline, or `--output-format=json` and capture a single end-of-run blob? Streaming preserves real-time stdout for `NOTIFY:` and similar, but adds parser complexity.
- **Schema mapping**: `dispatch_task` takes `model`, `tier`, `criticality`, `feature`. Orchestrator-round has model+tier (per the criticality matrix) but no feature — it operates at session scope. Decide whether to extend the dispatch schema, mint a synthetic feature value (e.g., `<session>`), or emit a separate orchestrator-scope event with a parallel aggregator.
- **Emission point**: emit `dispatch_start`/`dispatch_complete` from inside `_spawn_orchestrator` (closest to the subprocess), or from a thin wrapper that dispatch.py exposes? The latter keeps event emission centralized but requires `_spawn_orchestrator` to surface usage back to the wrapper.
- **R11/R12 closure**: once telemetry lands, can ticket 111's verification.md be updated with a real baseline value and the R12 post-merge note resolved? Or has the inline-read prompt already been retired by then, making the comparison moot?
