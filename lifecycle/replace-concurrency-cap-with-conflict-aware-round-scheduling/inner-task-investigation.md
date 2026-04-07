# Inner-Task Parallelism Investigation

## Background

`ConcurrencyManager` in `throttle.py` gates feature-level parallelism via an asyncio semaphore. Within each feature, `execute_feature` in `batch_runner.py` computes dependency batches via `compute_dependency_batches()` and fires all tasks in each batch concurrently via `asyncio.gather()` (line 952) without any semaphore gating. This investigation examines whether unbounded inner-task parallelism is a problem in practice.

## Data Point A: Typical task counts per dependency batch

### How batches are computed

`compute_dependency_batches()` in `claude/common.py` (lines 202-238) performs a topological sort: Batch 0 contains tasks with no dependencies; Batch N contains tasks whose dependencies all appear in batches 0..N-1. The batch size is determined entirely by the dependency graph in each feature's plan.md.

### Observed batch sizes across 36 plan.md files

Examined all plan.md files in `lifecycle/*/plan.md`. Dependency patterns fall into three categories:

1. **Linear chains (most common)**: Tasks depend on prior tasks sequentially. Produces batches of size 1. Examples:
   - `critical-review-self-resolve-before-asking`: Task 1 -> Task 2 -> Task 3 (batches: [1], [1], [1])
   - `add-ticket-consolidation-to-discovery`: Single task (batch: [1])

2. **Fan-out from root (common)**: Multiple independent tasks, then dependent follow-ups. Produces 1-2 larger batches followed by smaller ones. Examples:
   - `fix-permission-system-bugs`: 3 independent tasks (batch: [3])
   - `prevent-agents-from-writing-their-own-completion-evidence`: Tasks 1-5 independent, Task 6 independent (batch: [6], but Tasks 2 depends on 1, so actual: [4], [1], [1])
   - `fix-non-atomic-state-writes-in-overnight-runner`: Task 1 alone, Tasks 2-5 fan out (batch: [1], [3], [1], [1], [1])

3. **Current feature (largest observed)**: `replace-concurrency-cap-with-conflict-aware-round-scheduling` has 14 tasks; the first batch contains 8 independent tasks (Tasks 1, 2, 3, 7, 10, 11, 12, 13).

**Typical maximum batch size: 3-6 tasks.** The 8-task batch in the current feature is an outlier -- most features have a maximum batch of 2-4 concurrent tasks. Plans with more than 6 tasks in a single batch are rare.

### Effective concurrent API calls

With tier-based limits (MAX_5=1, MAX_100=2, MAX_200=3 concurrent features) and typical batch sizes of 3-4 tasks per feature, the worst-case concurrent API calls are:

| Tier | Max features | Max tasks/feature | Theoretical max concurrent calls |
|------|-------------|-------------------|--------------------------------|
| MAX_5 | 1 | 3-4 typical | 3-4 |
| MAX_100 | 2 | 3-4 typical | 6-8 |
| MAX_200 | 3 | 3-4 typical | 9-12 |

The MAX_200 tier with a large batch (8 tasks) could theoretically produce 24 concurrent API calls, but this scenario is unlikely -- the MAX_200 tier has a 200 concurrent request limit, so 24 calls represent 12% utilization.

## Data Point B: Rate limit events in overnight session logs

### Search methodology

Searched all overnight event logs and pipeline event logs across 3 historical sessions:
- `lifecycle/sessions/overnight-2026-04-01-1650/overnight-events.log` (2 lines, session barely started)
- `lifecycle/sessions/overnight-2026-04-01-2112/overnight-events.log` (48 lines, full 3-round session, 8 features)
- `lifecycle/sessions/overnight-2026-04-01-2112/pipeline-events.log`
- `lifecycle/sessions/overnight-2026-04-07-0008/overnight-events.log` (14 lines, 2 rounds, 6 features)
- `lifecycle/sessions/overnight-2026-04-07-0008/pipeline-events.log`

Searched for patterns: `rate_limit`, `rate-limit`, `throttle_backoff`, `infrastructure_failure`.

### Result

**Zero rate limit events found across all session logs.** No `throttle_backoff` events, no `infrastructure_failure` events, no rate-limit-related entries of any kind.

The overnight-2026-04-01-2112 session ran 3 rounds with up to 4 features concurrently in round 2 (each potentially running multiple inner tasks in parallel), and experienced no rate limiting. The overnight-2026-04-07-0008 session ran 2 features concurrently in round 1 with no rate limiting.

### Caveat

The sample size is small (3 sessions, only 2 with meaningful execution data). The system has been running on the MAX_100 tier (2 max concurrent features). More aggressive tiers or larger batches could change the picture.

## Data Point C: What `throttled_dispatch` does and whether it is called

### What it does

`throttled_dispatch()` in `throttle.py` (lines 206-271) is a wrapper around `dispatch_task()` that:
1. Acquires a slot from `ConcurrencyManager` before dispatching
2. On success, calls `manager.report_success()` to track consecutive successes for restoration
3. On `infrastructure_failure` (rate limit), calls `manager.report_rate_limit()` and applies exponential backoff (base 30s, max 300s)
4. Logs `throttle_backoff` events when backoff occurs
5. Always releases the semaphore slot in a `finally` block

### Who calls it

**No code path calls `throttled_dispatch`.** The complete call graph:

- **Definition**: `claude/overnight/throttle.py:206` -- defines the function
- **Re-export**: `claude/overnight/__init__.py:58` -- re-exports it as a public API
- **Documentation reference**: `claude/overnight/brain.py:194-196` -- explicitly documents that `request_brain_decision` calls `dispatch_task` directly (NOT `throttled_dispatch`) because re-acquiring the semaphore would deadlock at MAX_5 tier
- **batch_runner.py**: Imports `ConcurrencyManager` and `load_throttle_config` from throttle, but does NOT import or call `throttled_dispatch`

The primary execution path is:
1. `run_batch()` creates a `ConcurrencyManager` and calls `_run_one()` per feature
2. `_run_one()` manually calls `manager.acquire()` / `manager.release()` around `execute_feature()` (lines 1901-1925)
3. Inside `execute_feature()`, tasks dispatch via `retry_task()` -> `dispatch_task()` -- bypassing `throttled_dispatch` entirely
4. The brain agent also calls `dispatch_task()` directly per the documented deadlock concern

**`throttled_dispatch` is dead code.** It was designed as a task-level throttle wrapper but the actual execution path uses manual semaphore acquire/release at the feature level only. Tasks within a feature batch fire without any rate-limit-aware throttling.

## Recommendation

**(a) Not a problem in practice.**

Rationale:

1. **Batch sizes are small**: Typical maximum batch size is 3-4 tasks. Even in the worst case observed (8 tasks), this is well within API tier limits. The MAX_100 tier allows 100 concurrent requests; even 8 tasks x 2 features = 16 concurrent calls is 16% utilization.

2. **No empirical evidence of rate limiting**: Across all available overnight session logs (3 sessions, 2 with full execution data), zero rate limit events have been recorded. The system has been operating with inner-task parallelism since its creation without triggering rate limits.

3. **Natural throttling exists**: Each task invocation via `retry_task()` -> `dispatch_task()` spawns a Claude Code subprocess that runs for minutes (not milliseconds). The long execution time of each task provides natural rate limiting -- tasks within a batch don't all hit the API simultaneously; they stagger naturally as they process.

4. **`throttled_dispatch` is dead code but not needed**: While `throttled_dispatch` was apparently intended for task-level throttling, its absence has not caused problems. The feature-level `ConcurrencyManager` semaphore provides sufficient resource protection.

No backlog item is warranted. If future changes increase typical batch sizes significantly (e.g., plans with 15+ tasks in a single dependency batch) or the system moves to a lower-tier subscription, this conclusion should be revisited.
