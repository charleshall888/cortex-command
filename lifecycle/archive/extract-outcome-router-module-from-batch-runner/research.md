# Research: Extract outcome_router module from batch_runner

> Epic context: [`research/implement-in-autonomous-worktree-overnight-component-reuse/research.md`](../../research/implement-in-autonomous-worktree-overnight-component-reuse/research.md) — the "policy/mechanism separation opportunities" section and the proposed 3-way decomposition (orchestrator / feature_executor / outcome_router) are the primary background reference.

## Epic Reference

This ticket is Phase 2 of the 3-phase batch_runner decomposition described in the epic research. Phase 1 (feature_executor extraction, #075) has already landed. The epic proposed:

```python
# outcome_router.py
def apply_feature_result(
    name: str,
    result: FeatureResult,
    batch_result: BatchResult,
    consecutive_pauses_ref: list[int],
    config: BatchConfig,
    backlog_ids: dict[str, Optional[int]],
    ...
) -> None
```

This research validates and extends that contract based on the post-#075 codebase state.

## Codebase Analysis

### Post-#075 batch_runner.py structure

`batch_runner.py` is now **1498 LOC** (down from 2198 pre-#075). #075 extracted `execute_feature` + 10 helpers into `feature_executor.py`, `FeatureResult` into `types.py`, and `CIRCUIT_BREAKER_THRESHOLD` into `constants.py`. `batch_runner.py` re-exports all three via imports at lines 88–90.

Key targets for Phase 2 (outcome routing layer):

| Function | Location | LOC | Description |
|----------|----------|-----|-------------|
| `_apply_feature_result` | batch_runner:503–833 | ~330 | Top-level sync function. Handles non-merge status paths + no-commit guard + merge routing + CI deferral + circuit breaker firing. Does NOT perform the async `dispatch_review` call. |
| `_accumulate_result` (closure) | batch_runner:898–1284 | ~386 | Async closure inside `run_batch`. Holds `async with lock:`. Contains the `dispatch_review` async call, review routing, post-merge recovery dispatch, and delegates to `_apply_feature_result`. |
| `_write_back_to_backlog` | batch_runner:452–458 | ~40 | Sync helper. Called from 10+ sites in `_apply_feature_result` and from `_accumulate_result`. |
| `_find_backlog_item_path` | batch_runner:438–451 | ~14 | Sync helper. Used by `_write_back_to_backlog`. |

### _run_one (post-#075)

`_run_one` (lines 1285–1331) is now a thin shell:
1. Pre-dispatch circuit-breaker check under `async with lock:`
2. Acquires concurrency semaphore
3. Calls `await execute_feature(...)` — delegates to `feature_executor`
4. Passes result to `await _accumulate_result(name, result)`

After Phase 2, step 4 becomes `await outcome_router.apply_feature_result(name, result, ctx)`.

### _accumulate_result — closure structure (the primary extraction challenge)

`_accumulate_result` is defined as a **closure** inside `run_batch` (line ~898). It closes over 12+ variables from `run_batch`:

- `batch_result` — mutable BatchResult being built
- `lock` — asyncio.Lock (CRITICAL: used for the lock-release-reacquire pattern)
- `consecutive_pauses_ref` — mutable list[int] for circuit breaker
- `recovery_attempts_map` — mutable dict[str, int] for recovery gate
- `worktree_branches`, `worktree_paths`, `repo_path_map` — per-feature path maps
- `integration_worktrees`, `integration_branches` — multi-repo state
- `session_id`, `backlog_ids`, `feature_names`, `config`

The epic's proposed `apply_feature_result` signature omits `recovery_attempts_map`, `worktree_paths`, `worktree_branches`, `repo_path_map`, `integration_worktrees`, `session_id`, and `feature_names`. All of these are needed.

### The async lock-release-reacquire pattern

The most structurally significant constraint for extraction:

```
_accumulate_result enters:
    async with lock:            # ← line 910: acquired for fast-path routing
        ... call _apply_feature_result for non-completed results
        ... call merge_feature for completed results
        ... call dispatch_review (async) if review required
        ... (lock is released when async with block exits)
    
    if need_recovery:           # ← lock released here, outside async with
        recovery result = await recover_test_failure(...)
        async with lock:        # ← line 1202: re-acquired for routing recovery result
            ... route recovery result
```

`dispatch_review` (and `merge_feature`) are called **inside** the `async with lock:` block. This means the `dispatch_review` call holds the lock while waiting for the review agent (~minutes). This is an existing design choice, not a bug — other features cannot process results while a review is in flight.

**Consequence for extraction**: `outcome_router.apply_feature_result` must be `async def`. The lock must either be passed as a parameter or the outcome router restructured so the caller (`_accumulate_result` remnant or `_run_one`) manages the lock and calls two phases of outcome_router (pre-lock and post-lock).

### dispatch_review call site

Called inside `_accumulate_result` at lines 991–1006, within `async with lock:`, after a successful `merge_feature` call, gated by `requires_review(tier, criticality)`:

```python
rr = await dispatch_review(
    feature=name,
    worktree_path=worktree_paths.get(name, ...),
    branch=actual_branch or f"pipeline/{name}",
    spec_path=Path(f"lifecycle/{name}/spec.md"),
    complexity=tier,
    criticality=criticality,
    base_branch=_effective_base_branch(...),
    repo_path=_effective_merge_repo_path(...),
    log_path=config.pipeline_events_path,
)
```

Lazy import at call site: `from cortex_command.pipeline.review_dispatch import dispatch_review  # noqa: E402`.

### Circuit breaker — mutation sites

`consecutive_pauses_ref` is mutated at:

**In `_apply_feature_result` (sync, will move to outcome_router):**
- Line 547: reset to 0 — repair_completed merge success
- Line 586: increment — repair_completed FF merge failed
- Line 613: increment — completed, no-commit guard
- Line 666: reset to 0 — completed, merge success (approved)
- Line 733: increment — completed, merge failed
- Line 782: increment — failed (non-parse-error)
- Line 801: increment — paused fallthrough
- Line 815: **circuit breaker fire** (threshold check)

**In `_accumulate_result` (async closure, will move to outcome_router):**
- Line 1061: reset to 0 — merge success, no review or review approved
- Lines 1212, 1231: reset to 0 — recovery merged
- Line 1258: increment — recovery failed
- Line 1266: **circuit breaker fire** (second check, covers recovery path)

There are **two** circuit-breaker check sites; both must be preserved in the extraction.

**In `feature_executor.py` (`_handle_failed_task`, line 200):** Read-only soft check only (does not mutate).

### recovery_attempts_map — mutable state

`recovery_attempts_map: dict[str, int]` is a closure variable with its own lifecycle:
- Populated from `overnight_state` at run_batch start (lines 871, 876)
- Mutated in `_accumulate_result`: increment at line 925 (pre-recovery gate) and line 1169
- Read at line 1143 (gate: `recovery_attempts >= 1` blocks second attempt)
- Persisted inside `async with lock:` at lines 1175–1182 (on recovery dispatch)
- Final write-back post-gather at lines 1392–1403

This state is **not** in `FeatureResult` — it lives in the `run_batch` closure. Any extraction must pass it explicitly or bundle it in a context object.

### Shared helpers — import challenge

These helpers are called directly from `_apply_feature_result` and `_accumulate_result` and were designated by the epic to "stay in the orchestrator layer":

| Helper | Current location | Called from |
|--------|-----------------|-------------|
| `_get_changed_files` | batch_runner:323 | `_apply_feature_result` |
| `_classify_no_commit` | batch_runner:344 | `_apply_feature_result` |
| `_effective_base_branch` | batch_runner:157 | `_accumulate_result` (dispatch_review call) |
| `_effective_merge_repo_path` | batch_runner:185 | `_accumulate_result` (dispatch_review, merge_feature calls) |
| `_next_escalation_n` | `deferral.py`:402 | Already imported independently |

If these stay in `batch_runner`/`orchestrator.py` after Phase 2, then `outcome_router` must import from `batch_runner` — creating a back-import (`batch_runner` already imports from `outcome_router`). Either (a) move these helpers to `outcome_router` (they belong to outcome routing), or (b) move them to a third shared location (e.g., `claude/overnight/routing_helpers.py`), or (c) accept that `batch_runner` exports them for `outcome_router` to import.

**Resolution for spec**: Moving them to `outcome_router` is the cleanest option — they operate on the same data (`FeatureResult`, `BatchResult`, path maps) as outcome routing. The epic's "stay in orchestrator" designation was based on them being shared with `feature_executor`, but `feature_executor` does NOT import any of these four (verified post-#075). They are exclusively outcome-routing concerns.

### Test coverage

`claude/overnight/tests/test_lead_unit.py` (1797 lines) was added in #080 as characterization tests. Key test classes:

- `TestApplyFeatureResult` (line 93): 8 tests covering circuit-breaker counter mechanics and status dispatch for `_apply_feature_result`
- `TestApplyFeatureResultVariants` (line 775): 5 tests for merge routing variants
- `TestConsecutivePausesSequence` (line 907): 3 tests for pause/merge sequencing and threshold firing
- `TestRecoveryDispatchPersistence` (line 297): recovery_attempts persisted to disk
- `TestRecoveryGate` (line 410): gate blocks second recovery attempt
- `TestBudgetExhaustionSignal` (line 494): budget exhausted global abort
- `TestAccumulateResultViaBatch` (line 1373): drives `run_batch` end-to-end to exercise `_accumulate_result` paths (CI deferral, budget exhausted, multi-feature recovery, review gating)

**Critical note for Phase 2**: `TestAccumulateResultViaBatch` patches `claude.overnight.batch_runner.*` for all review/merge/state targets (e.g., `claude.overnight.batch_runner.merge_feature`, `claude.overnight.batch_runner.dispatch_review`). After extraction, these patch targets will break — they must be updated to patch `claude.overnight.outcome_router.*`. This is a known migration cost.

### feature_executor.py — import boundary (enforced by test)

`feature_executor.py` has **zero runtime imports** from `batch_runner.py`. Only a `TYPE_CHECKING` guard imports `BatchConfig`. This boundary is enforced by `test_feature_executor_boundary.py`. The same pattern should be adopted for `outcome_router.py` — no runtime back-imports from `batch_runner`.

### FeatureResult contract

```python
@dataclass
class FeatureResult:
    name: str
    status: str  # merged, paused, deferred, failed, repair_completed
    error: Optional[str] = None
    deferred_question_count: int = 0
    files_changed: list[str] = field(default_factory=list)
    repair_branch: Optional[str] = None
    trivial_resolved: bool = False
    repair_agent_used: bool = False
    parse_error: bool = False
    resolved_files: list[str] = field(default_factory=list)
```

Treated as frozen API for Phase 2 (per ticket scope).

## Open Questions

- **Closure context packaging**: `_accumulate_result` closes over 12+ variables. The extraction must either (a) pass all of them as parameters to `apply_feature_result`, (b) create an `OutcomeContext` dataclass bundling them, or (c) keep `_accumulate_result` as a thin dispatcher closure in `batch_runner` that constructs the context and calls `outcome_router.apply_feature_result(ctx, name, result)`. Which approach is preferred? The ticket acceptance criterion says "clean signature" — (b) or (c) are both cleaner than 12+ positional params. Deferred to spec.

- **Async structure**: `dispatch_review` and `merge_feature` are async and called inside `async with lock:`. The sync `_apply_feature_result` helper handles non-async status routing. Does `outcome_router.apply_feature_result` become a single `async def` that takes ownership of the lock (passed as parameter), or does it split into a sync routing layer + separate async entry point for the merge/review path? Deferred to spec.

- **Shared helper ownership**: `_get_changed_files`, `_classify_no_commit`, `_effective_base_branch`, `_effective_merge_repo_path` are called exclusively from outcome routing code (not by `feature_executor`). The cleanest move is to `outcome_router.py` itself, despite the epic's "stay in orchestrator" note. Deferred to spec — user should confirm direction.

- **Test migration**: `TestAccumulateResultViaBatch` patches `claude.overnight.batch_runner.*`. After extraction, patch paths must move to `claude.overnight.outcome_router.*`. This is mechanical but must be accounted for in the plan. Deferred to spec.
