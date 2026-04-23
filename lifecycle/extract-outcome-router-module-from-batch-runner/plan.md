# Plan: extract-outcome-router-module-from-batch-runner

## Overview

Build `outcome_router.py` fully alongside `batch_runner.py` (Tasks 1–4 — no removal yet), then surgically excise the moved code from `batch_runner.py` (Task 8), then migrate all test patches and direct imports to match the new ownership (Task 9 — `just test` gate). New unit tests for `outcome_router` run independently and use targeted pytest. This ordering guarantees that mock patches are never in the wrong state: tests stay at `batch_runner.*` until `batch_runner.py` no longer has the functions, then migrate immediately.

## Tasks

### [x] Task 1: Scaffold `outcome_router.py` with `OutcomeContext` dataclass
- **Files**: `claude/overnight/outcome_router.py`
- **What**: Create the new module with `from __future__ import annotations`, stdlib imports, TYPE_CHECKING guard for `BatchResult`/`BatchConfig`, and the `OutcomeContext` dataclass. No function implementations yet.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Follow `claude/overnight/feature_executor.py` lines 1–25 as the structural pattern for module header and TYPE_CHECKING guard.
  - `from __future__ import annotations` must be the very first line.
  - TYPE_CHECKING guard: `if TYPE_CHECKING: from cortex_command.overnight.batch_runner import BatchResult, BatchConfig` — same pattern as `feature_executor.py` lines 20–21.
  - `OutcomeContext` is a `@dataclass` with these 13 fields: `batch_result: BatchResult`, `lock: asyncio.Lock`, `consecutive_pauses_ref: list[int]`, `recovery_attempts_map: dict[str, int]`, `worktree_paths: dict[str, Path]`, `worktree_branches: dict[str, str]`, `repo_path_map: dict[str, Path | None]`, `integration_worktrees: dict[str, Path]`, `integration_branches: dict[str, str]`, `session_id: str`, `backlog_ids: dict[str, int | None]`, `feature_names: list[str]`, `config: BatchConfig`.
  - `FeatureResult` is imported from `claude.overnight.types` (runtime import — not under TYPE_CHECKING).
  - `CIRCUIT_BREAKER_THRESHOLD` from `claude.overnight.constants`. `asyncio`, `Path`, `dataclasses.dataclass`, `typing.TYPE_CHECKING` are stdlib.
- **Verification**:
  - `python3 -c "from cortex_command.overnight import outcome_router"` — pass if exit 0
  - `grep 'from __future__ import annotations' claude/overnight/outcome_router.py` — pass if exit 0
  - `grep -c 'class OutcomeContext' claude/overnight/outcome_router.py` = 1

---

### [x] Task 2: Add sync helper functions to `outcome_router.py`
- **Files**: `claude/overnight/outcome_router.py`
- **What**: Copy the 6 sync helper functions from `batch_runner.py` into `outcome_router.py`. Do NOT modify `batch_runner.py` in this task — functions must remain in both modules until Task 8.
- **Depends on**: [1]
- **Complexity**: complex
- **Context**:
  - Copy these functions from `batch_runner.py` (verify current location by `def` signature — line numbers below are approximate from post-#075 state):
    - `_effective_base_branch` (~lines 157–183): takes `config`, `integration_branches`
    - `_effective_merge_repo_path` (~lines 185–322): takes `config`, `name`, `result`, `repo_path_map`, `integration_worktrees`, `integration_branches`
    - `_get_changed_files` (~lines 323–342)
    - `_classify_no_commit` (~lines 344–389)
    - `_find_backlog_item_path` (~lines 438–451)
    - `_write_back_to_backlog` (~lines 452–458) — calls `_find_backlog_item_path`
  - All import dependencies for these helpers must be added to `outcome_router.py`'s imports (e.g., `subprocess`, `json`, `Optional`). Do NOT import these functions from `batch_runner` — define them in `outcome_router` itself.
  - **Whole-function copy**: copy each function from the `def` line through the last line of the function body — not just the `def` line.
- **Verification**:
  - `grep -c 'def _effective_base_branch\|def _effective_merge_repo_path\|def _get_changed_files\|def _classify_no_commit\|def _find_backlog_item_path\|def _write_back_to_backlog' claude/overnight/outcome_router.py` = 6
  - `python3 -c "from cortex_command.overnight import outcome_router"` — pass if exit 0

---

### [x] Task 3: Move `_apply_feature_result` to `outcome_router.py`
- **Files**: `claude/overnight/outcome_router.py`
- **What**: Copy the sync `_apply_feature_result` helper from `batch_runner.py` into `outcome_router.py`, adapting every closure-variable reference to use `ctx.{field}` instead. Do NOT remove it from `batch_runner.py` yet.
- **Depends on**: [2]
- **Complexity**: complex
- **Context**:
  - Source: `batch_runner.py` ~lines 503–833 (find by `def _apply_feature_result` signature). Copy the ENTIRE function including body — not just the `def` line.
  - New signature: `def _apply_feature_result(name: str, result: FeatureResult, ctx: OutcomeContext) -> None`.
  - Every closure variable (`consecutive_pauses_ref`, `batch_result`, `worktree_paths`, `worktree_branches`, `repo_path_map`, `integration_worktrees`, `integration_branches`, `session_id`, `backlog_ids`, `feature_names`, `config`) → `ctx.{fieldname}`.
  - The 6 helper functions called from within `_apply_feature_result` are already in `outcome_router.py` (Task 2) — no import needed.
  - `CIRCUIT_BREAKER_THRESHOLD` check at ~line 815: this is site 1 of 2; preserve it unchanged.
  - Other callee imports (`merge_feature`, etc.): find their source in `batch_runner.py`'s module-level import block; replicate in `outcome_router.py`.
- **Verification**:
  - `grep -c 'def _apply_feature_result' claude/overnight/outcome_router.py` = 1
  - `grep -c 'CIRCUIT_BREAKER_THRESHOLD' claude/overnight/outcome_router.py` ≥ 1
  - `python3 -c "from cortex_command.overnight import outcome_router"` — pass if exit 0

---

### [x] Task 4: Implement async `apply_feature_result` in `outcome_router.py`
- **Files**: `claude/overnight/outcome_router.py`
- **What**: Add the async public function `apply_feature_result(name, result, ctx)`. It owns the lock, calls `_apply_feature_result` and `merge_feature` inside the first lock block, handles `dispatch_review` inside that same block, and implements the two-phase lock-release-reacquire for the recovery dispatch path.
- **Depends on**: [3]
- **Complexity**: complex
- **Context**:
  - Signature: `async def apply_feature_result(name: str, result: FeatureResult, ctx: OutcomeContext) -> None`.
  - Callers must NOT hold the lock when calling this function — it acquires `async with ctx.lock:` on entry.
  - Two-phase lock structure (from `_accumulate_result` at batch_runner ~lines 910–1284):
    1. First `async with ctx.lock:` — call `_apply_feature_result`, call `merge_feature`, call `dispatch_review` if `requires_review` returns True. **`dispatch_review` stays INSIDE this lock** (pre-existing behavior — holding the lock during async review dispatch is intentional).
    2. After block exits, check `need_recovery` flag set inside the block.
    3. If `need_recovery`: increment `ctx.recovery_attempts_map[name]` (before dispatch, ~line 1169), then call `await recover_test_failure(...)` outside the lock.
    4. Second `async with ctx.lock:` — route recovery result; second circuit-breaker check site belongs here (~line 1266, site 2 of 2).
  - `dispatch_review` import: top-level `from cortex_command.pipeline.review_dispatch import dispatch_review` (no lazy import needed — no circular dependency).
  - `requires_review`, `read_tier`, `read_criticality`, `write_deferral`: find their import sources in `batch_runner.py`'s module-level imports and replicate.
  - After this task `CIRCUIT_BREAKER_THRESHOLD` must appear ≥ 2 times total in `outcome_router.py`.
- **Verification**:
  - `grep -c 'async def apply_feature_result' claude/overnight/outcome_router.py` = 1
  - `grep -c 'CIRCUIT_BREAKER_THRESHOLD' claude/overnight/outcome_router.py` — pass if result ≥ 2
  - `python3 -c "import cortex_command.overnight.batch_runner"` — pass if exit 0 (no circular import)

---

### [x] Task 5: Add `test_outcome_router_boundary.py`
- **Files**: `claude/overnight/tests/test_outcome_router_boundary.py`
- **What**: Boundary test asserting `outcome_router.py` has no runtime imports from `claude.overnight.batch_runner`. Mirrors `test_feature_executor_boundary.py`.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Copy the structure of `claude/overnight/tests/test_feature_executor_boundary.py` verbatim.
  - Change `_FEATURE_EXECUTOR_PATH` to point at `outcome_router.py` (`parents[1] / "outcome_router.py"`).
  - `_FORBIDDEN_PREFIXES`: `("claude.overnight.batch_runner",)`.
  - Class: `TestOutcomeRouterImportBoundary`, method: `test_no_forbidden_imports`.
- **Verification**:
  - `python3 -m pytest claude/overnight/tests/test_outcome_router_boundary.py -v` — pass if exit 0 and `PASSED` in output

---

### [x] Task 6: Add `test_outcome_router.py` — status transitions and circuit breaker
- **Files**: `claude/overnight/tests/test_outcome_router.py`
- **What**: Create the new test file with 6 tests that exercise `apply_feature_result` directly. Patch targets are all `claude.overnight.outcome_router.*`.
- **Depends on**: [4]
- **Complexity**: complex
- **Context**:
  - Test entry point: `await outcome_router.apply_feature_result(name, result, ctx)`.
  - Use the same async test harness pattern as `test_lead_unit.py` (check its imports and class base).
  - Build a factory helper for `OutcomeContext`: real `asyncio.Lock()`, `MagicMock` for `batch_result` and `config`, empty dicts for path maps, `consecutive_pauses_ref=[0]`.
  - All patches at `claude.overnight.outcome_router.*` — never `batch_runner.*`.
  - `dispatch_review` mock: check `TestAccumulateResultViaBatch` in test_lead_unit.py for the mock return-value structure.
  - Required 6 tests:
    1. `status=merged` — `merge_feature` called once; `_write_back_to_backlog` called; `consecutive_pauses_ref[0]` reset to 0
    2. `status=paused` — `merge_feature` NOT called; `consecutive_pauses_ref[0]` incremented; `_write_back_to_backlog` NOT called
    3. `status=deferred` — `write_deferral` called; `consecutive_pauses_ref[0]` incremented
    4. `status=failed` (parse_error=False) — `consecutive_pauses_ref[0]` incremented; `merge_feature` NOT called
    5. `status=repair_completed` — routes through merge path; `merge_feature` called
    6. Circuit breaker fires — set `consecutive_pauses_ref[0] = CIRCUIT_BREAKER_THRESHOLD - 1`; send `status=paused`; assert circuit-breaker executes (see `TestConsecutivePausesSequence` in test_lead_unit.py for assertion pattern)
- **Verification**:
  - `python3 -m pytest claude/overnight/tests/test_outcome_router.py -v` — pass if exit 0
  - `grep -c 'def test_' claude/overnight/tests/test_outcome_router.py` ≥ 6

---

### [x] Task 7: Add `test_outcome_router.py` — review gating and recovery path
- **Files**: `claude/overnight/tests/test_outcome_router.py`
- **What**: Add 3 more tests to the existing file covering review gating and recovery dispatch. All patches at `claude.overnight.outcome_router.*`.
- **Depends on**: [6]
- **Complexity**: complex
- **Context**:
  - Continue in the same test class(es) from Task 6, or add a new class in the same file.
  - Required 3 tests:
    7. Review gating (gated) — `requires_review` returns True; after `status=merged` + successful `merge_feature`, assert `dispatch_review` called once with correct `feature` and `branch` args.
    8. Review gating (ungated) — `requires_review` returns False; assert `dispatch_review` NOT called.
    9. Recovery path — `merge_feature` returns success + test failure indicator; assert `recover_test_failure` awaited once; assert `ctx.recovery_attempts_map[name]` incremented before dispatch.
- **Verification**:
  - `python3 -m pytest claude/overnight/tests/test_outcome_router.py -v` — pass if exit 0
  - `grep -c 'def test_' claude/overnight/tests/test_outcome_router.py` ≥ 9

---

### [x] Task 8: Remove moved functions + collapse `_accumulate_result` shim in `batch_runner.py`
- **Files**: `claude/overnight/batch_runner.py`
- **What**: Delete the 7 helpers and `_apply_feature_result` from `batch_runner.py` (each function entirely — `def` line + full body); replace the `_accumulate_result` closure body with the ~40-line shim; add `from cortex_command.overnight import outcome_router` and `from cortex_command.overnight.outcome_router import OutcomeContext` to imports; remove now-dead imports.
- **Depends on**: [4]
- **Complexity**: complex
- **Context**:
  - **Delete entirely** (find by `def` signature; approximate line numbers from post-#075 state — verify current locations before editing):
    - `_effective_base_branch` (~157–183)
    - `_effective_merge_repo_path` (~185–322): ~137-line body — delete `def` line AND all 137 lines of body
    - `_get_changed_files` (~323–342)
    - `_classify_no_commit` (~344–389)
    - `_find_backlog_item_path` (~438–451)
    - `_write_back_to_backlog` (~452–458)
    - `_apply_feature_result` (~503–833): ~330-line body — delete `def` line AND full body
  - **"Entirely" means**: from the `def` line through the last line of the function body (the last line that is indented as part of the function). After deletion, run `python3 -m py_compile claude/overnight/batch_runner.py` to confirm no syntax errors from orphaned indented code.
  - **Now-dead imports to remove** (verify each against remaining code — do not remove if still referenced):
    - `import hashlib` (~line 16) — only used by `_get_changed_files`
    - `from cortex_command.pipeline.conflict import ConflictClassification, dispatch_repair_agent, resolve_trivial_conflict` (~line 35) — only used by the deleted helpers
    - The `from backlog.update_item import ...` imports (~lines 392–393) — only used by `_find_backlog_item_path` / `_write_back_to_backlog`
    - The `_OVERNIGHT_TO_BACKLOG` dict (~lines 398–419), `_backlog_dir` global, and `sys.path` mutation block (~lines 376–379) — only used by deleted helpers
    - `set_backlog_dir` function (~line 386) — only writes `_backlog_dir` which is now unused; also delete its call site in `run_batch` (~line 866)
    - Also remove from `batch_runner.py` module-level any symbols that were previously imported for the deleted functions but are no longer needed after extracting to `outcome_router` (e.g., `merge_feature`, `recover_test_failure`, `requires_review`, `read_tier`, `read_criticality`, `write_deferral`, `write_deferral`, `_next_escalation_n` — only keep these if they are still referenced by remaining code outside the deleted functions)
  - **`_accumulate_result` shim**: Replace the entire closure body (~386 lines, ~898–1284) with:
    1. Budget-exhausted early-exit: open the current `_accumulate_result` in `batch_runner.py`, locate the `async with lock:` block's first section (~lines 910–952), identify the budget/abort detection logic (the condition that sets `batch_result.global_abort_signal = True` and calls `load_state`/`save_state`/`overnight_log_event`), and lift that block verbatim into the shim — placed BEFORE the `OutcomeContext` construction, outside any lock. Note: this moves the budget check from inside the lock to before the lock call; this is intentional — `apply_feature_result` owns the lock, so the shim cannot hold it.
    2. Construct `OutcomeContext(batch_result=batch_result, lock=lock, consecutive_pauses_ref=consecutive_pauses_ref, recovery_attempts_map=recovery_attempts_map, worktree_paths=worktree_paths, worktree_branches=worktree_branches, repo_path_map=repo_path_map, integration_worktrees=integration_worktrees, integration_branches=integration_branches, session_id=session_id, backlog_ids=backlog_ids, feature_names=feature_names, config=config)`.
    3. `await outcome_router.apply_feature_result(name, result, ctx)`.
  - Do NOT run `just test` as verification for this task — the test suite is intentionally broken at this point (test patches still reference `batch_runner.*` for moved functions; Task 9 repairs this).
- **Verification**:
  - `grep -c 'def _apply_feature_result\|def _write_back_to_backlog\|def _find_backlog_item_path\|def _get_changed_files\|def _classify_no_commit\|def _effective_base_branch\|def _effective_merge_repo_path' claude/overnight/batch_runner.py` = 0
  - `grep -c 'await outcome_router.apply_feature_result' claude/overnight/batch_runner.py` = 1
  - `grep -c 'budget_exhausted\|global_abort_signal' claude/overnight/batch_runner.py` — pass if result ≥ 1
  - `python3 -m py_compile claude/overnight/batch_runner.py` — pass if exit 0 (no syntax errors from orphaned code)
  - `python3 -m claude.overnight.batch_runner --help` — pass if exit 0

---

### [x] Task 9: Migrate all test patch targets, direct imports, and affected test files
- **Files**: `claude/overnight/tests/test_lead_unit.py`, `claude/overnight/tests/test_no_commit_classification.py`
- **What**: Migrate every reference to moved symbols across both test files: update top-level `from batch_runner import ...` bindings, all direct call sites, all `patch.object` targets, all `@patch` decorators, and `_install_common_patches` entries. After this task `just test` must pass.
- **Depends on**: [8]
- **Complexity**: complex
- **Context**:
  - **`test_no_commit_classification.py`**: This file imports `_classify_no_commit` directly from `batch_runner` (now deleted). Update the import to `from cortex_command.overnight.outcome_router import _classify_no_commit`.
  - **`test_lead_unit.py` — top-level name-bound imports (~lines 21–29)**:
    The file contains `from cortex_command.overnight.batch_runner import _apply_feature_result, _effective_merge_repo_path, ...` (and possibly other moved symbols). These name-bound imports resolve to functions that no longer exist in `batch_runner`. Update them: add `from cortex_command.overnight.outcome_router import _apply_feature_result, _effective_merge_repo_path` (and any other moved symbols imported here). Direct call sites like `_apply_feature_result(...)` at ~lines 112, 205, 229, 514, 749, 811, 829, 848, 867, 892, 928, 947 and `_effective_merge_repo_path(...)` at ~lines 592, 611, 631, 666, 684 will continue to work correctly once the import is updated.
  - **`test_lead_unit.py` — `TestApplyFeatureResult` family (~lines 93, 699, 775, 907)**: Add `import cortex_command.overnight.outcome_router as outcome_router_module` alongside the existing `batch_runner_module` binding. Replace `patch.object(batch_runner_module, '<symbol>', ...)` → `patch.object(outcome_router_module, '<symbol>', ...)` for all moved symbols: `_apply_feature_result`, `_write_back_to_backlog`, `_get_changed_files`, `merge_feature`, `recover_test_failure`, `requires_review`, `read_tier`, `read_criticality`, `write_deferral`, `_effective_base_branch`, `_effective_merge_repo_path`. `dispatch_review` is already patched at `claude.pipeline.review_dispatch.dispatch_review` — do NOT change.
  - **`test_lead_unit.py` — `TestAccumulateResultViaBatch._install_common_patches` (~line 1449)**: Migrate 8 patch strings: `'claude.overnight.batch_runner.merge_feature'` → `'claude.overnight.outcome_router.merge_feature'` (and same for `recover_test_failure`, `_write_back_to_backlog`, `_get_changed_files`, `requires_review`, `read_tier`, `read_criticality`, `write_deferral`). Symbols that stay at `batch_runner.*`: `parse_master_plan`, `create_worktree`, `load_state`, `save_state`, `load_throttle_config`, `ConcurrencyManager`, `execute_feature`, `cleanup_worktree`, `save_batch_result`, `overnight_log_event`, `transition`.
  - Scan the full file for any other `batch_runner` references to moved symbols not covered above.
- **Verification**:
  - `grep 'batch_runner_module\|batch_runner\.' claude/overnight/tests/test_lead_unit.py | grep -c '_apply_feature_result\|_write_back_to_backlog\|merge_feature\|recover_test_failure'` = 0
  - `grep -c 'from cortex_command.overnight.batch_runner import _classify_no_commit' claude/overnight/tests/test_no_commit_classification.py` = 0
  - `just test` — pass if exit 0

---

## Verification Strategy

After all tasks complete, `just test` must exit 0 with no new failures (Task 9's gate). Spot-checks:
1. `python3 -c "import cortex_command.overnight.batch_runner; import cortex_command.overnight.outcome_router"` — no circular import
2. `grep -c 'def _apply_feature_result\|def _write_back_to_backlog' claude/overnight/batch_runner.py` = 0
3. `grep -c 'CIRCUIT_BREAKER_THRESHOLD' claude/overnight/outcome_router.py` ≥ 2
4. `python3 -m claude.overnight.batch_runner --help` exits 0

## Veto Surface

- **No duplication window for tests**: Prior plan versions migrated test patches before removing functions from `batch_runner.py`. That inverted the correct dependency (mock patches must target the module where the function resolves its names — LEGB). This plan keeps all test patches at `batch_runner.*` until Task 8 removes the functions, then migrates everything in Task 9.
- **`OutcomeContext` in `outcome_router.py`**: Could go in `models.py` alongside `FeatureResult`. Defaults to co-location since `FeatureResult` migration is Phase 3 scope.
- **Dead import removal**: Task 8 lists specific imports to remove. If any listed import is still referenced by surviving code, skip removing it and note the miss in the commit message.

## Scope Boundaries

- **No behavioral changes**: This is a move, not a rewrite. One minor intentional behavioral shift: the `budget_exhausted` early-exit check moves from inside `async with lock:` (current) to before the lock call (shim). The worst-case impact is one extra feature result processed before an abort propagates — acceptable.
- **FeatureResult frozen**: No new fields, no typed status variants.
- **CircuitBreakerState dataclass**: `consecutive_pauses_ref` stays `list[int]`. Deferred to #077.
- **`batch_runner.py` → `orchestrator.py` rename**: Phase 3 (#077).
- **Re-export shim**: `batch_runner.py` does NOT re-export moved symbols.
- **`budget_exhausted` semantics stay in `_accumulate_result`**: The abort logic (signal set, state saved) stays in the shim — just moves from inside the lock to before it.
