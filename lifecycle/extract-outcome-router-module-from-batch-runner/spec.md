# Specification: Extract outcome_router module from batch_runner

## Problem Statement

`batch_runner.py` mixes three architectural layers in one 1498-LOC file (after Phase 1). The outcome-routing layer — everything that happens after a feature produces a result: merge, review gating, test-failure recovery, backlog write-back, circuit-breaker firing — is scattered across `_apply_feature_result` (~330 LOC) and `_accumulate_result` (~386 LOC, a closure). Extracting this layer into `claude/overnight/outcome_router.py` is Phase 2 of the 3-phase batch_runner decomposition. The benefit is the same as Phase 1: each remaining module answers one question, policy decisions are centralized, and the outcome-routing code becomes unit-testable with mocked merge/review callouts.

## Requirements

### R1 — New `outcome_router.py` module
Create `claude/overnight/outcome_router.py` containing the full outcome-routing layer.

**Acceptance criteria**:
- `grep -l 'def apply_feature_result' claude/overnight/outcome_router.py` — file exists with the function (exit 0)
- `grep -c 'class OutcomeContext' claude/overnight/outcome_router.py` = 1

### R2 — `OutcomeContext` dataclass
Define an `OutcomeContext` dataclass in `outcome_router.py` bundling all closure variables from `_accumulate_result`. The module uses `from __future__ import annotations` (matching the `feature_executor.py` pattern), so unquoted field type names are valid even when those types are imported only under `TYPE_CHECKING`:

```
batch_result: BatchResult
lock: asyncio.Lock
consecutive_pauses_ref: list[int]
recovery_attempts_map: dict[str, int]
worktree_paths: dict[str, Path]
worktree_branches: dict[str, str]
repo_path_map: dict[str, Path | None]
integration_worktrees: dict[str, Path]
integration_branches: dict[str, str]
session_id: str
backlog_ids: dict[str, int | None]
feature_names: list[str]
config: BatchConfig
```

`BatchResult` and `BatchConfig` are imported under `TYPE_CHECKING` only — no runtime back-import from `batch_runner`.

**Acceptance criteria**:
- `python3 -c "from claude.overnight import outcome_router"` exits 0 (module imports cleanly)
- `grep 'from __future__ import annotations' claude/overnight/outcome_router.py` exits 0
- `grep 'TYPE_CHECKING' claude/overnight/outcome_router.py` exits 0
- `python3 -c "import claude.overnight.batch_runner"` exits 0 (no circular import)

### R3 — `apply_feature_result` public contract
Move outcome routing into `async def apply_feature_result(name: str, result: FeatureResult, ctx: OutcomeContext) -> None`.

`apply_feature_result` **owns the lock**: it acquires `async with ctx.lock:` internally on entry. The caller (`_accumulate_result` shim) must NOT hold the lock when calling `apply_feature_result`.

What moves from `batch_runner.py`:
- `_apply_feature_result` (lines 503–833) — becomes an internal helper in `outcome_router`
- The `dispatch_review` async call and its verdict routing from `_accumulate_result` (lines 991–1064)
- The post-merge recovery dispatch (`need_recovery` flag, `recover_test_failure` call) from `_accumulate_result` (lines 1143–1270)
- `_write_back_to_backlog` (lines 452–458)
- `_find_backlog_item_path` (lines 438–451)
- `_get_changed_files` (lines 323–342)
- `_classify_no_commit` (lines 344–389)
- `_effective_base_branch` (lines 157–183)
- `_effective_merge_repo_path` (lines 185–322)

**Acceptance criteria**:
- `grep -c 'def _apply_feature_result\|def _write_back_to_backlog\|def _find_backlog_item_path\|def _get_changed_files\|def _classify_no_commit\|def _effective_base_branch\|def _effective_merge_repo_path' claude/overnight/batch_runner.py` = 0 (none remain in batch_runner)
- `grep -c 'def _write_back_to_backlog' claude/overnight/outcome_router.py` = 1
- `grep -c 'async def apply_feature_result' claude/overnight/outcome_router.py` = 1

### R4 — `_accumulate_result` becomes a short shim
`_accumulate_result` stays in `batch_runner.py` as a short closure (~40 lines max) that:
1. Checks the `budget_exhausted` global abort signal (lines 928–950: sets `batch_result.global_abort_signal`, calls `load_state`/`save_state`/`overnight_log_event`) — this is session-layer state persistence that stays in `_accumulate_result`, NOT delegated to `outcome_router`
2. Constructs `OutcomeContext`
3. Calls `await outcome_router.apply_feature_result(name, result, ctx)` — the shim must NOT hold the lock before this call

`_run_one` is unchanged.

```python
async def _accumulate_result(name: str, result: FeatureResult) -> None:
    # budget_exhausted early-exit (session-layer, stays here)
    if batch_result.budget_exhausted:
        batch_result.global_abort_signal = True
        batch_result.abort_reason = "budget_exhausted"
        # ... load_state / save_state / overnight_log_event ...
        return
    # context construction + delegation (no lock held here)
    ctx = OutcomeContext(
        batch_result=batch_result,
        lock=lock,
        consecutive_pauses_ref=consecutive_pauses_ref,
        recovery_attempts_map=recovery_attempts_map,
        worktree_paths=worktree_paths,
        worktree_branches=worktree_branches,
        repo_path_map=repo_path_map,
        integration_worktrees=integration_worktrees,
        integration_branches=integration_branches,
        session_id=session_id,
        backlog_ids=backlog_ids,
        feature_names=feature_names,
        config=config,
    )
    await outcome_router.apply_feature_result(name, result, ctx)
```

**Acceptance criteria**:
- `grep -c 'await outcome_router.apply_feature_result' claude/overnight/batch_runner.py` = 1
- `grep -c 'budget_exhausted\|global_abort_signal' claude/overnight/batch_runner.py` ≥ 1 (budget_exhausted check remains in batch_runner)
- `grep -c 'budget_exhausted\|global_abort_signal' claude/overnight/outcome_router.py` = 0 (budget_exhausted logic does NOT move to outcome_router)

### R5 — Import boundary enforcement
`outcome_router.py` must have zero runtime imports from `claude.overnight.batch_runner`. `BatchResult` and `BatchConfig` are allowed only under `TYPE_CHECKING`.

**Acceptance criteria**:
- A new test `claude/overnight/tests/test_outcome_router_boundary.py` passes: `just test` exits 0 and the test asserts that `claude.overnight.outcome_router` has no runtime dependency on `claude.overnight.batch_runner`
- `python3 -c "from claude.overnight import outcome_router"` exits 0

### R6 — Both circuit-breaker sites preserved
The circuit-breaker check (`consecutive_pauses_ref[0] >= CIRCUIT_BREAKER_THRESHOLD`) fires at two places:
1. Inside the sync routing logic (fires on pause/fail/no-commit paths)
2. After the recovery path (fires when recovery fails)

Both sites must exist in `outcome_router.py` after extraction.

**Acceptance criteria**:
- `grep -c 'CIRCUIT_BREAKER_THRESHOLD' claude/overnight/outcome_router.py` ≥ 2

### R7 — `recovery_attempts_map` persistence preserved
`recovery_attempts_map` persistence (write to state inside `async with ctx.lock:` on recovery dispatch; this write lives inside `apply_feature_result`) must still occur after extraction.

**Acceptance criteria**:
- `just test` exits 0 with `TestRecoveryDispatchPersistence` passing

### R8 — Unit tests for outcome routing
Add unit tests for `outcome_router.apply_feature_result` that exercise the extracted module directly (without running `run_batch`). Tests import from `claude.overnight.outcome_router` and patch at `claude.overnight.outcome_router.*`.

Minimum coverage:
- Status transitions: merged, paused, deferred, failed, repair_completed
- Circuit breaker fires after `CIRCUIT_BREAKER_THRESHOLD` consecutive pauses
- Backlog write-back called on the correct status transitions
- Review gating: gated feature dispatches review; ungated skips
- Post-merge recovery path triggered when merge succeeds but tests fail

**Acceptance criteria**:
- `just test` exits 0
- `grep -l 'apply_feature_result' claude/overnight/tests/test_outcome_router.py` — file exists (exit 0)
- `grep -c 'def test_' claude/overnight/tests/test_outcome_router.py` ≥ 8

### R9 — Existing test suite passes with migrated patch targets (regression gate)
All existing tests in `claude/overnight/tests/` pass after extraction.

**Patch target migration — re-export strategy**: `batch_runner.py` does NOT re-export moved symbols from `outcome_router`. The moved symbols live exclusively in `outcome_router`'s namespace. All tests that patched `claude.overnight.batch_runner.{symbol}` for a moved symbol must be updated to patch `claude.overnight.outcome_router.{symbol}`.

**`TestApplyFeatureResult` family** (test_lead_unit.py line 93, `TestApplyFeatureResultVariants` line 775, `TestApplyFeatureResultWorktreePaths` line 699, `TestConsecutivePausesSequence` line 907): These classes use `patch.object(batch_runner_module, ...)` where `batch_runner_module = import claude.overnight.batch_runner`. After `_apply_feature_result` and its internal callees move to `outcome_router`, these classes must import `outcome_router_module = claude.overnight.outcome_router` and patch against that module instead.

**`TestAccumulateResultViaBatch` (line 1373)**: `_install_common_patches` (line ~1449) currently patches 14 symbols at `claude.overnight.batch_runner.*`. After extraction, the patch target for each symbol changes based on where the name is USED (not where it's defined):
- Patch at `claude.overnight.outcome_router.*`: `merge_feature`, `recover_test_failure`, `_write_back_to_backlog`, `_get_changed_files`, `requires_review`, `read_tier`, `read_criticality`, `write_deferral`
- Patch remains at `claude.overnight.batch_runner.*`: `parse_master_plan`, `create_worktree`, `load_state`, `save_state`, `load_throttle_config`, `ConcurrencyManager`, `execute_feature`, `cleanup_worktree`, `save_batch_result`, `overnight_log_event`, `transition`
- `dispatch_review` is already correctly patched at `claude.pipeline.review_dispatch.dispatch_review` — do NOT change this patch target

**`TestBudgetExhaustionSignal` (line 494)**: `load_state`, `save_state`, `overnight_log_event` remain in `_accumulate_result` (session-layer, per R4). Their patch targets stay at `claude.overnight.batch_runner.*` — no migration needed.

**Acceptance criteria**:
- `just test` exits 0
- `grep 'batch_runner_module\|batch_runner\.' claude/overnight/tests/test_lead_unit.py | grep -c '_apply_feature_result\|_write_back_to_backlog\|merge_feature\|recover_test_failure'` = 0 (patched symbols have migrated to outcome_router)

### R10 — `batch_runner.py` imports `outcome_router`
`batch_runner.py` imports `outcome_router` and uses it in `_accumulate_result`.

**Acceptance criteria**:
- `grep -c 'from claude.overnight import outcome_router\|import outcome_router' claude/overnight/batch_runner.py` ≥ 1
- `python3 -m claude.overnight.batch_runner --help` exits 0 (CLI entry point still works)

## Non-Requirements

- **FeatureResult restructuring**: The `FeatureResult` dataclass fields are frozen for this ticket. No typed status variants, validation, or field-owner documentation.
- **CircuitBreakerState dataclass**: `consecutive_pauses_ref` continues as a mutable `list[int]`. Clean-up deferred to #077 or follow-up.
- **`recovery_attempts_map` cleanup**: Mutable dict stays as-is via `OutcomeContext`. Same deferred scope.
- **Daytime pipeline**: This ticket extracts the module; the daytime driver (Phase 5) is a separate optional decision.
- **`batch_runner.py` → `orchestrator.py` rename**: Phase 3 (#077). Out of scope here.
- **New outcome routing logic**: This is a move, not a rewrite. No behavioral changes to routing decisions.
- **Re-export shim in `batch_runner`**: `batch_runner` does NOT re-export moved symbols from `outcome_router`. Tests must be updated to patch the correct module.

## Edge Cases

- **Lock ownership contract**: `apply_feature_result` acquires `async with ctx.lock:` on entry. The `_accumulate_result` shim calls `apply_feature_result` WITHOUT holding the lock. Violating this contract — e.g., shim acquires the lock then calls `apply_feature_result`, which also tries to acquire it — would deadlock immediately (asyncio.Lock is not reentrant).
- **Lock-release-reacquire (recovery path)**: `apply_feature_result` must release the lock during the recovery dispatch (`need_recovery` path: exits the first `async with ctx.lock:` block) and re-acquire (`async with ctx.lock:`) for recovery result routing. Flattening this into a single lock acquisition would deadlock if the recovery agent itself needs to acquire the lock.
- **`dispatch_review` inside the lock**: `dispatch_review` is called while holding the lock (pre-existing behavior). This holds the lock for the duration of the review agent (~minutes). Do not move `dispatch_review` outside the lock — this would change the concurrency behavior and potentially allow other features to process results concurrently with an in-flight review.
- **Recovery attempt gating**: `recovery_attempts_map[name]` must be incremented before the recovery dispatch to prevent double-recovery. Gate check `recovery_attempts >= 1` must read the post-increment value.
- **`feature_names` list dependency**: Logic in `apply_feature_result` uses `ctx.feature_names` for round-completion detection (checking if all features have resolved).
- **Multi-repo path resolution**: `_effective_base_branch` and `_effective_merge_repo_path` use `ctx.integration_worktrees` and `ctx.integration_branches`.
- **Lazy `dispatch_review` import**: Currently a local lazy import inside `_accumulate_result` to avoid circular import. In `outcome_router.py`, this import becomes top-level — `from claude.pipeline.review_dispatch import dispatch_review` — no circular dependency exists with `review_dispatch.py`.
- **budget_exhausted stays in `_accumulate_result`**: Lines 928–950 are session-layer state (sets global abort signal, persists state). They stay in the shim and do NOT move to `outcome_router`. `TestBudgetExhaustionSignal` patch targets remain at `claude.overnight.batch_runner.*`.

## Changes to Existing Behavior

- MODIFIED: `_accumulate_result` in `batch_runner.py` — collapsed from ~386 lines to ~40 lines; retains `budget_exhausted` early-exit; delegates outcome routing to `outcome_router.apply_feature_result`
- MODIFIED: `_apply_feature_result`, `_write_back_to_backlog`, `_find_backlog_item_path`, `_get_changed_files`, `_classify_no_commit`, `_effective_base_branch`, `_effective_merge_repo_path` — moved from `batch_runner.py` to `outcome_router.py`; no behavioral changes
- ADDED: `OutcomeContext` dataclass in `outcome_router.py`
- ADDED: `claude/overnight/outcome_router.py` module
- ADDED: `claude/overnight/tests/test_outcome_router.py` unit tests
- ADDED: `claude/overnight/tests/test_outcome_router_boundary.py` import boundary test
- MODIFIED: `TestApplyFeatureResult`-family patch targets — migrated from `batch_runner_module` to `outcome_router_module`
- MODIFIED: `TestAccumulateResultViaBatch._install_common_patches` patch targets — partial migration per R9 table
- REMOVED: Lazy `from claude.pipeline.review_dispatch import dispatch_review` local import in `_accumulate_result` — replaced with top-level import in `outcome_router.py`

## Technical Constraints

- **`apply_feature_result` must be `async def`**: It awaits `dispatch_review` (async, ~minutes per call) and `recover_test_failure` (async). The existing sync `_apply_feature_result` helper handles non-async routing paths and becomes an internal sync helper called from the async outer function.
- **`from __future__ import annotations` required**: `outcome_router.py` must start with `from __future__ import annotations` (matching `feature_executor.py` line 8). This defers all annotation evaluation to strings, making unquoted `BatchResult` and `BatchConfig` field type annotations safe even when those types are imported only under `TYPE_CHECKING`.
- **`BatchResult`/`BatchConfig` imports under `TYPE_CHECKING`**: No runtime import from `batch_runner.py`. Pattern: `if TYPE_CHECKING: from claude.overnight.batch_runner import BatchResult, BatchConfig` (same as `feature_executor.py` lines 20–21).
- **`asyncio.Lock` owned by `run_batch`**: Created at line 895; shared with the heartbeat loop. Must be passed into `OutcomeContext`, not created inside `apply_feature_result`. `apply_feature_result` acquires it on entry via `async with ctx.lock:`.
- **Two-phase lock pattern must be preserved**: `apply_feature_result` acquires the lock, releases it for recovery dispatch, re-acquires for recovery result routing. Same structure as current `_accumulate_result` lines 910, 1186–1202. Do NOT flatten to a single acquisition.
- **`CIRCUIT_BREAKER_THRESHOLD` from `constants.py`**: Import from `claude.overnight.constants`. No `claude.overnight.*` circular dependency.
- **`_next_escalation_n` from `deferral.py`**: Import from `claude.overnight.deferral` (same as `feature_executor.py`).
- **No `batch_runner` runtime imports in `outcome_router`**: The boundary test enforces this. If `outcome_router` needs a type at runtime, it belongs in `types.py` or `constants.py`.
- **`budget_exhausted` stays in `_accumulate_result`**: Not part of `apply_feature_result`'s contract. `OutcomeContext` does not carry the budget_exhausted signal.

## Open Decisions

- **`OutcomeContext` placement — `outcome_router.py` vs. a new `models.py`**: Defining it in `outcome_router.py` is the default. A separate `models.py` could house both `FeatureResult` and `OutcomeContext` for discoverability — but requires migrating existing `FeatureResult` imports, which is Phase 3's renaming scope. Deferred: requires implementation-level judgment on whether the import chain is simpler with `OutcomeContext` co-located with `apply_feature_result` or in a separate models module.
