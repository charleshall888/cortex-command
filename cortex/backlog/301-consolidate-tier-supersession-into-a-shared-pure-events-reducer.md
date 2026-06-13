---
schema_version: "1"
uuid: caa4a81c-97ae-490a-8716-302d4bbd81bc
title: Consolidate tier supersession into a shared pure-events reducer
status: complete
priority: low
type: chore
created: 2026-06-10
updated: 2026-06-13
complexity: complex
criticality: high
spec: cortex/lifecycle/consolidate-tier-supersession-into-a-shared/spec.md
areas: ['lifecycle']
---
## Why

`extract_feature_metrics` in `cortex_command/pipeline/metrics.py` folds tier supersession inline (PR #20: lifecycle_start seeds the tier, the most recent complexity_override's `to` supersedes). That is a second implementation of the canonical rule in `cortex_command/common.py`'s `reduce_lifecycle_state` — duplicated deliberately because the metrics fix avoided opening common.py (lifecycle-protected; #287's reducer consolidation had just landed in a concurrent session). Drift is bounded by a parity test asserting the fold agrees with `read_tier` on a shared fixture, but agreement is by-test, not by-construction.

## Role

Extract the event-fold body of `reduce_lifecycle_state` into a pure `reduce_lifecycle_events(records)` operating on parsed dicts; have the Path-based `reduce_lifecycle_state` delegate to it; replace metrics.py's inline fold with a call to the shared reducer. One source of truth for every tier reader, including the in-memory case.

## Integration

This is Option C from `cortex/lifecycle/harness-token-efficiency-trim/evidence.json` → `metricsFix` (full consumer analysis there). **Trigger: execute when common.py is next opened for other work** — standalone value is low (the rule has near-zero historical churn and the parity test catches divergence); as a rider it is nearly free and durable.

## Edges

- common.py is on CLAUDE.md's lifecycle-protected list — requires a lifecycle; commit with explicit pathspecs if another session shares the checkout.
- Vocabulary enforcement is a deliberate decision point: the canonical reducer gates values by TIER_VOCABULARY, so out-of-vocab historical tiers would become None and drop from aggregates — a silent behavior change vs the inline fold (no such data exists today; preserve or document explicitly).
- The pure reducer must keep `LifecycleStateReduction` semantics (skipped_lines, corrupted) intact for existing consumers; the Path version's tolerant-read contract must not change.
- `initial_tier` (first lifecycle_start seed, added by PR #20) is NOT part of the canonical rule — keep its extraction local to `extract_feature_metrics` or extend the reducer deliberately.

## Touch-points

- cortex_command/common.py (`reduce_lifecycle_state` → delegate to new `reduce_lifecycle_events`)
- cortex_command/pipeline/metrics.py (`extract_feature_metrics` inline fold → shared call)
- cortex_command/pipeline/tests/test_metrics.py (parity test stays as regression guard)
- tests/test_reduce_lifecycle_state.py (thin coverage for the pure-events entry point)
