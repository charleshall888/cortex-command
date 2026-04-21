---
schema_version: "1"
uuid: 4337b723-4a50-4d3e-811f-ef2709f4a26e
title: "Remove dead throttled_dispatch wrapper; keep ConcurrencyManager acquire/release"
status: backlog
priority: low
type: feature
created: 2026-04-20
updated: 2026-04-20
tags: [cleanup, overnight, throttle]
areas: [overnight-runner]
---

# Remove dead throttled_dispatch wrapper; keep ConcurrencyManager acquire/release

Delete the adaptive-rate-limit-backoff wrapper `throttled_dispatch()` and its supporting rate-limit-reactive concurrency shrinkage logic. Keep `ConcurrencyManager.acquire()` / `release()` — those are load-bearing for enforcing the tier-based subscription concurrency cap. Split out of epic #082 / ticket #087 after a critical review found the wrapper was being instrumented despite having zero call sites.

## Motivation

Surfaced while scoping #087 (baseline metrics for turns/cost). The #087 spec initially included rate-limit aggregation over `throttle_backoff` events. Critical review found:

- `throttled_dispatch()` at `claude/overnight/throttle.py:206` has **zero call sites** in production code. `grep 'throttled_dispatch\(' claude/` returns only the definition.
- `claude/overnight/brain.py:194-196` explicitly comments: *"Calls `dispatch_task` directly (not `throttled_dispatch`) because the `throttled_dispatch` would deadlock at MAX_5."* The wrapper was tried, broke things, and was swapped out for the simpler path.
- Zero `throttle_backoff` events exist across all session pipeline-events.log files. Zero `infrastructure_failure` error_type events either.
- Prior investigation at `lifecycle/replace-concurrency-cap-with-conflict-aware-round-scheduling/inner-task-investigation.md:57,91` independently reached the same conclusion.

`ConcurrencyManager` itself is live and necessary — `orchestrator.py:170` creates it; `feature_executor.py:188` uses `acquire()`/`release()` to enforce the tier-bound concurrency cap (1–3 workers depending on subscription). The dead part is the adaptive-rate-limit-shrinkage layered on top.

## Scope

**Remove:**
- `throttled_dispatch()` function (throttle.py:206 onward)
- `ConcurrencyManager.report_rate_limit()` method
- `ConcurrencyManager.report_success()` method
- The `_effective_concurrency` / `_total_rate_limits` internal state and the logic that shrinks and recovers the semaphore on 429s
- The `throttle_backoff` event type (no emitters after the wrapper is removed)
- `backoff_base_seconds` / `backoff_max_seconds` config knobs
- Related tests for the removed surfaces

**Keep:**
- `ConcurrencyManager` class with `acquire()` and `release()` (the tier-bound semaphore)
- `SubscriptionTier` enum and concurrency limits
- `load_throttle_config()` if it still has non-backoff-related knobs worth keeping
- Callers of `acquire()`/`release()` untouched

## Dependencies

- None. Can run anytime after #087.

## Not blocked

Pure cleanup. SDK-level retry already handles 429s for the plain `dispatch_task` path that production actually uses.
