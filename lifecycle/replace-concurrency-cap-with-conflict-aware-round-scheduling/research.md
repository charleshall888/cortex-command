# Research: Investigate whether the static concurrency cap is redundant given area-separation

## Codebase Analysis

### Core Finding: `BatchConfig.concurrency` Is Dead Code

The `concurrency: int = 3` field in `BatchConfig` (`batch_runner.py:113`) is **never used for actual execution control**. It appears in exactly one place at runtime: a log event at line 1521 (`details={"features": feature_names, "concurrency": config.concurrency}`). The `--concurrency` CLI argument (`batch_runner.py:2053`) writes to this field, but its value has no effect on behavior.

**Actual concurrency control** is handled by `ConcurrencyManager` from `claude/overnight/throttle.py`, which wraps an `asyncio.Semaphore` initialized from the subscription tier via `ThrottleConfig.max_concurrent_workers`:
- MAX_5 tier: 1 worker
- MAX_100 tier: 2 workers
- MAX_200 tier: 3 workers

The semaphore is adaptive — it reduces the limit on rate-limit errors and restores after 10 consecutive successes.

### Two Dead Concurrency Fields

There is a second dead field in the chain:
1. `generate_batch_plan(concurrency=...)` in `batch_plan.py` writes `concurrency_limit` into batch plan markdown
2. `parse_master_plan` in `parser.py:223-225` parses it into `MasterPlanConfig.concurrency_limit`
3. `MasterPlanConfig.concurrency_limit` is **never read by anything**

Both `BatchConfig.concurrency` and `MasterPlanConfig.concurrency_limit` are vestigial.

### Two Mechanisms, Two Purposes

| Mechanism | Location | Purpose | Enforcement |
|-----------|----------|---------|-------------|
| Area-separation in `group_into_batches()` | `backlog.py:946-954` | **Conflict avoidance** — items sharing areas forced into separate rounds | Hard constraint at scheduling time |
| `ConcurrencyManager` semaphore | `throttle.py:107-200` | **Resource protection** — limits parallel features based on API tier | Runtime enforcement via `asyncio.Semaphore`, adaptive |
| `BatchConfig.concurrency` | `batch_runner.py:113` | **Dead code** — formerly the static cap | Only used in a log message |

### Semaphore Scope: Feature-Level Only

The `ConcurrencyManager` semaphore in `_run_one()` (line 1901) gates **feature-level** parallelism only. Within each feature, dependency batch tasks fire via `asyncio.gather()` without any semaphore. If 2 features run concurrently with 3 parallel tasks each, that is 6 concurrent API calls — potentially exceeding tier limits. The `throttled_dispatch` wrapper in `throttle.py` exists but is **unused** in the primary execution path (`batch_runner.py`). Inner-task parallelism is architecturally unbounded.

### Files Affected by Cleanup

1. `claude/overnight/batch_runner.py` — remove `concurrency` field from `BatchConfig`, `--concurrency` CLI arg, log reference
2. `claude/overnight/batch_plan.py` — remove `concurrency` parameter from `generate_batch_plan()`
3. `claude/pipeline/parser.py` — remove dead `MasterPlanConfig.concurrency_limit` field and parsing
4. `claude/overnight/smoke_test.py` — update `BatchConfig(concurrency=1)` constructor call
5. `claude/overnight/tests/test_batch_plan.py` — 7 test calls pass `concurrency=` to `generate_batch_plan`
6. `claude/overnight/prompts/orchestrator-round.md` — remove `concurrency=2` from example
7. `skills/overnight/SKILL.md` — remove `concurrency` references (lines 7, 37, 92, 99, 203, 322)
8. `docs/overnight.md` — remove/update `--concurrency` documentation

### Documentation Discrepancy

`docs/overnight.md:385` says "Keep --concurrency 2 (the default)" but the argparse default is 3. The orchestrator prompt also uses `concurrency=2`. Code, docs, and prompts all disagree on the default value.

## Web Research

### Industry Precedent: Conflict Avoidance and Resource Caps Are Orthogonal

Every major workflow orchestration system maintains these as independent, composable layers:

- **GitHub Actions**: Concurrency groups (conflict avoidance) are orthogonal to runner concurrency limits (resource protection). You can run at maximum runner capacity while respecting concurrency groups.
- **GitLab**: `resource_group` keyword provides per-resource mutual exclusion separate from runner limits.
- **Apache Airflow**: Three independent knobs: `depends_on_past` (logical dependencies), `max_active_tasks` (per-DAG resource cap), `max_active_runs` (parallelism cap).
- **Kubernetes**: Pod anti-affinity (conflict avoidance) + resource quotas (resource protection) + node capacity (infrastructure ceiling) — applied sequentially but independently.

### When Is a Concurrency Cap Still Useful With Conflict-Aware Scheduling?

1. **API rate limits are hard external constraints.** Claude API enforces RPM, ITPM, and OTPM limits. Three parallel Opus agents can hit the 50 RPM / 30,000 ITPM limits on Tier 1.
2. **Token budgets are a resource dimension.** Conflict avoidance says nothing about aggregate token consumption.
3. **Local resource exhaustion.** Each parallel agent consumes memory, CPU, and file handles regardless of file conflicts.
4. **Defense in depth.** The scheduling algorithm itself can have bugs — a resource cap provides a safety net.

### Anti-Pattern: Removing the Cap Because Scheduling "Handles It"

The Temporal community specifically warned against this: users who removed concurrency caps because scheduling was conflict-free needed "custom dispatcher workflows or external distributed locks" to handle resource exhaustion.

## Requirements & Constraints

### Explicit Semaphore Requirement

`requirements/multi-agent.md:44-45`: "Features execute concurrently via `asyncio.gather()` with semaphore-based slot enforcement. Concurrency limit is 1–3 agents, adaptive: reduces by 1 after 3 rate-limit errors within 5 minutes, restores after 10 consecutive successes."

`requirements/multi-agent.md:73`: "The concurrency cap (1–3) is a hard limit enforced by semaphore; it is not overridable at runtime by agents." — classified as a **hard architectural constraint**.

### Two Separate Layers in Requirements

The requirements explicitly describe:
1. **Round-planning time** (pipeline.md:15, multi-agent.md:48): Features grouped into rounds, dependencies filtered, area separation determines co-execution — **conflict avoidance**
2. **Dispatch time** (multi-agent.md:44-45, 73): Semaphore caps parallel features based on tier — **resource protection**

### Graceful Degradation

`requirements/pipeline.md:95`: "Budget exhaustion and rate limits pause the session rather than crashing it." The adaptive semaphore is part of this broader strategy.

### Complexity Constraint

`requirements/project.md:19`: "Complexity: Must earn its place by solving a real problem that exists now."

## Tradeoffs & Alternatives

### A: Remove the semaphore entirely

Let all features in a round run in parallel.

- **Pros**: Simplest code, maximizes throughput
- **Cons**: Ignores API rate limits (the real constraint), loses adaptive backoff, violates hard architectural constraint in requirements
- **Verdict**: Not viable

### B: Keep the semaphore, remove dead code (Recommended)

No behavioral changes. Clean up vestigial `BatchConfig.concurrency` and `MasterPlanConfig.concurrency_limit`.

- **Pros**: Zero risk, eliminates the confusion that prompted this investigation, the tier-based system already works
- **Cons**: Area-separation remains coarse-grained (two features in the same area touching different files are unnecessarily serialized)
- **Verdict**: Strongest option — addresses the root confusion with minimal blast radius

### C: Make the semaphore dynamic

Compute concurrency from batch size, API response times, or remaining budget.

- **Pros**: Could optimize throughput for small batches
- **Cons**: `ConcurrencyManager` already does adaptive concurrency; marginal improvement with added complexity
- **Verdict**: Marginal — existing adaptive mechanism already provides runtime dynamism

### D: Add file-level overlap analysis to round assignment

Enhance `group_into_batches()` to use file overlap from specs/plans instead of just area labels.

- **Pros**: Higher parallelism for same-area features touching different files
- **Cons**: High implementation complexity, requires structured `touched-files` data that doesn't consistently exist, false negatives cause merge conflicts, doesn't replace the semaphore (still need it for rate limits)
- **Verdict**: High cost, moderate benefit — could be a future enhancement but not justified now

## Adversarial Review

### Blast Radius Underestimated

Removing `BatchConfig.concurrency` touches ~8 files across 4 directories, including tests and prompts. Not just "delete the field" — it requires cleaning up the entire dead concurrency pipeline through `batch_plan.py`, `parser.py`, `smoke_test.py`, and `test_batch_plan.py`.

### Inner-Task Parallelism Is Unbounded

The `ConcurrencyManager` semaphore only gates feature-level parallelism. Within each feature, dependency batch tasks fire via `asyncio.gather()` without any semaphore. If 2 features run concurrently with 3 parallel tasks each, that produces 6 concurrent API calls — potentially exceeding tier limits. The `throttled_dispatch` wrapper in `throttle.py` exists but is unused by `batch_runner.py`.

### Documentation/Code/Prompt Disagreement

Three sources state three different concurrency defaults:
- `batch_runner.py:2053` argparse default: **3**
- `docs/overnight.md:385`: "Keep --concurrency **2** (the default)"
- `orchestrator-round.md:275`: `concurrency=**2**`

This should be resolved during cleanup.

### `smoke_test.py` Explicit Dependency

`smoke_test.py:256` constructs `BatchConfig(concurrency=1)`. Removing the field without updating this file would break the smoke test.

## Open Questions

- Should the documentation discrepancy (default 2 vs 3 vs 2) be resolved as part of this cleanup, or filed separately?
- Is inner-task parallelism being unbounded a concern worth addressing now, or is it acceptable given typical task counts (1-3 per batch)?
