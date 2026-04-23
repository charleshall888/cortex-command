# Plan: rename-batch-runner-to-orchestrator-and-add-integration-tests

## Overview

Move all session-layer logic from `batch_runner.py` into a new `orchestrator.py`, reduce the former to a ≤50 LOC CLI wrapper, convert `consecutive_pauses_ref: list[int]` to a `CircuitBreakerState` dataclass, update every import site and patch target, and add `test_orchestrator.py` integration tests — completing the three-phase batch_runner decomposition.

## Tasks

### Task 1: Add `CircuitBreakerState` to `types.py`
- [x]
- **Files**: `claude/overnight/types.py`
- **What**: Add `@dataclass class CircuitBreakerState` with a single field `consecutive_pauses: int = 0` alongside the existing `FeatureResult` dataclass. This foundational addition unblocks every `consecutive_pauses_ref` replacement task.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `types.py` (31 LOC) currently defines only `FeatureResult`; `dataclasses.dataclass` is already imported. Add `CircuitBreakerState` as a second dataclass in the same file — no new imports needed.
- **Verification**: `grep -c "class CircuitBreakerState" claude/overnight/types.py` = 1

---

### Task 2: Create `orchestrator.py` with session-layer logic and `BatchConfig`/`BatchResult`
- [x]
- **Files**: `claude/overnight/orchestrator.py`
- **What**: Create the new module by moving everything from `batch_runner.py` except the CLI entrypoint: `BatchConfig`, `BatchResult`, `run_batch()`, `_run_one()` (with inline budget exhaustion replacing `_accumulate_result`), `_heartbeat_loop()`, `_derive_session_id()`, and all helper imports. `_run_one` checks budget exhaustion before constructing `OutcomeContext`; if exhausted, writes state, emits `BATCH_BUDGET_EXHAUSTED`, sets `batch_result.global_abort_signal = True`, and returns without calling `outcome_router`. `OutcomeContext` is constructed with `cb_state=CircuitBreakerState()` (not `consecutive_pauses_ref=[0]`). The heartbeat task must use `from asyncio import create_task` at the top of the module (not `asyncio.create_task()`) so the heartbeat test can patch it at the module level as `claude.overnight.orchestrator.create_task`.
- **Depends on**: [1]
- **Complexity**: complex
- **Context**:
  - Source range: `batch_runner.py` lines 1–401 (everything up to `build_parser`), including the module-level imports block (lines 1–70)
  - `BatchConfig` fields: `batch_id, plan_path, test_command, base_branch, overnight_state_path, overnight_events_path, result_dir, pipeline_events_path, throttle_tier`
  - `BatchResult` fields: `batch_id, features_merged, features_paused, features_deferred, features_failed, circuit_breaker_fired, global_abort_signal, abort_reason, key_files_changed`
  - Budget exhaustion block (currently `_accumulate_result` lines 191–241): becomes an inline check inside `_run_one` before `OutcomeContext` construction; no `_accumulate_result` function survives in `orchestrator.py`
  - All symbols that `run_batch` calls must be bound in `orchestrator.py`'s module namespace (not re-imported via a helper) so `patch.object(orchestrator_module, "parse_master_plan", ...)` etc. work in migrated tests: `parse_master_plan`, `create_worktree`, `load_throttle_config`, `ConcurrencyManager`, `overnight_log_event`, `load_state`, `save_state`, `save_batch_result`, `transition`, `execute_feature`, `outcome_router`
  - `OutcomeContext` initialization: `cb_state=CircuitBreakerState()` — import `CircuitBreakerState` from `claude.overnight.types`
  - `_LIFECYCLE_ROOT` constant and `logger` move with the session logic
  - Do NOT import from `batch_runner.py`; `orchestrator.py` must have zero imports of `claude.overnight.batch_runner`
  - The heartbeat uses `from asyncio import create_task` at module level so tests can patch `claude.overnight.orchestrator.create_task` without affecting the global `asyncio` namespace
- **Verification**: `grep -c "async def run_batch" claude/overnight/orchestrator.py` = 1; `grep -c "class BatchConfig" claude/overnight/orchestrator.py` = 1; `grep -c "global_abort_signal = True" claude/overnight/orchestrator.py` ≥ 1; `grep -c "consecutive_pauses_ref" claude/overnight/orchestrator.py` = 0; `python3 -c "import cortex_command.overnight.orchestrator"` exits 0

---

### Task 3: Reduce `batch_runner.py` to thin CLI wrapper (≤50 LOC)
- [x]
- **Files**: `claude/overnight/batch_runner.py`
- **What**: Replace the body of `batch_runner.py` with a ≤50 LOC CLI wrapper. Keep the module docstring (shortened), import `BatchConfig` and `run_batch` from `claude.overnight.orchestrator`, and preserve `build_parser()` and `_run()` by name for CLI contract compatibility. `_run()` constructs a `BatchConfig` from parsed args and calls `asyncio.run(run_batch(config))`. Do NOT re-export `FeatureResult`, `execute_feature`, or `CIRCUIT_BREAKER_THRESHOLD` — those consumers are updated in Task 7/9.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**:
  - `build_parser()` function: lines 408–434; preserve exact function name
  - `_run()` function: lines 435–453; preserve exact function name; same `BatchConfig` field mapping from argparse namespace
  - `if __name__ == "__main__": _run()` block (line 455): keep as-is
  - Only imports needed: `argparse`, `asyncio`, `from cortex_command.overnight.orchestrator import BatchConfig, run_batch`
- **Verification**: `wc -l < claude/overnight/batch_runner.py` ≤ 50; `grep -c "class BatchConfig" claude/overnight/batch_runner.py` = 0; `python3 -m claude.overnight.batch_runner --help` exits 0

---

### Task 4: Update `outcome_router.py` — replace `consecutive_pauses_ref` with `cb_state`
- [x]
- **Files**: `claude/overnight/outcome_router.py`
- **What**: Replace the `OutcomeContext.consecutive_pauses_ref: list[int]` field with `cb_state: CircuitBreakerState`; update all 14 mutation/read sites in `_apply_feature_result` from `ctx.consecutive_pauses_ref[0]` to `ctx.cb_state.consecutive_pauses`; add `CircuitBreakerState` to the runtime import from `claude.overnight.types`; update the TYPE_CHECKING block to import `BatchConfig`/`BatchResult` from `claude.overnight.orchestrator` instead of `batch_runner`. Verify `global_abort_signal = True` does not appear in this file (defensive reads are permitted).
- **Depends on**: [1, 2]
- **Complexity**: complex
- **Context**:
  - `OutcomeContext` at line 68: field `consecutive_pauses_ref: list[int]` → `cb_state: CircuitBreakerState`
  - 14 mutation/read sites (lines 467, 506, 533, 586, 653, 702, 721, 735, 907, 1044, 1063, 1090, 1098, and the threshold comparison at 1098): `ctx.consecutive_pauses_ref[0] += 1` → `ctx.cb_state.consecutive_pauses += 1`; `ctx.consecutive_pauses_ref[0] = 0` → `ctx.cb_state.consecutive_pauses = 0`; `ctx.consecutive_pauses_ref[0] >= CIRCUIT_BREAKER_THRESHOLD` → `ctx.cb_state.consecutive_pauses >= CIRCUIT_BREAKER_THRESHOLD`
  - TYPE_CHECKING block: `from cortex_command.overnight.batch_runner import BatchResult, BatchConfig` → `from cortex_command.overnight.orchestrator import BatchResult, BatchConfig`
  - Permitted: `if ctx.batch_result.global_abort_signal: return` defensive read guard may be retained or added at entry point
- **Verification**: `grep -c "consecutive_pauses_ref" claude/overnight/outcome_router.py` = 0; `grep -c "global_abort_signal = True" claude/overnight/outcome_router.py` = 0; `grep -c "CircuitBreakerState" claude/overnight/outcome_router.py` ≥ 1

---

### Task 5: Update `feature_executor.py` — replace `consecutive_pauses_ref` parameter and TYPE_CHECKING import
- [x]
- **Files**: `claude/overnight/feature_executor.py`
- **What**: Update `execute_feature` signature: replace `consecutive_pauses_ref: Optional[list[int]] = None` with `cb_state: Optional[CircuitBreakerState] = None`; update internal initialization from `pauses_ref = consecutive_pauses_ref if consecutive_pauses_ref is not None else [0]` to `cb_state_eff = cb_state if cb_state is not None else CircuitBreakerState()`; update `_handle_failed_task` parameter from `consecutive_pauses_ref: list[int]` to `cb_state: CircuitBreakerState` and threshold comparison from `consecutive_pauses_ref[0] >= ...` to `cb_state.consecutive_pauses >= ...`; add `CircuitBreakerState` import from `claude.overnight.types`; update TYPE_CHECKING import of `BatchConfig` from `batch_runner` → `orchestrator`.
- **Depends on**: [1, 2]
- **Complexity**: simple
- **Context**:
  - `execute_feature` at line 351: parameter `consecutive_pauses_ref: Optional[list[int]] = None`
  - Line 663: `pauses_ref = consecutive_pauses_ref if consecutive_pauses_ref is not None else [0]` — replace with `CircuitBreakerState()` default
  - `_handle_failed_task` at line 186: `consecutive_pauses_ref: list[int]` → `cb_state: CircuitBreakerState`
  - Line 200: `consecutive_pauses_ref[0] >= CIRCUIT_BREAKER_THRESHOLD - 1` → `cb_state.consecutive_pauses >= CIRCUIT_BREAKER_THRESHOLD - 1`
  - TYPE_CHECKING block: `from cortex_command.overnight.batch_runner import BatchConfig` → `from cortex_command.overnight.orchestrator import BatchConfig`
- **Verification**: `grep -c "consecutive_pauses_ref" claude/overnight/feature_executor.py` = 0

---

### Task 6: Update non-test import sites (`__init__.py`, `smoke_test.py`, `state.py`, `conflict.py`)
- [x]
- **Files**: `claude/overnight/__init__.py`, `claude/overnight/smoke_test.py`, `claude/overnight/state.py`, `claude/pipeline/conflict.py`
- **What**: Re-point all four files from `batch_runner` to `orchestrator`. In `__init__.py`: change `BatchConfig`, `BatchResult`, `run_batch` re-export source. In `smoke_test.py`: update top-level import. In `state.py`: update TYPE_CHECKING import of `BatchResult`. In `conflict.py`: update TYPE_CHECKING import of `BatchConfig`.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**:
  - `__init__.py`: `from cortex_command.overnight.batch_runner import BatchConfig, BatchResult, run_batch` → `from cortex_command.overnight.orchestrator import BatchConfig, BatchResult, run_batch`
  - `smoke_test.py`: similar top-level import update (line numbers may vary; scan for `batch_runner`)
  - `state.py` TYPE_CHECKING block (line ~12): `from cortex_command.overnight.batch_runner import BatchResult` → `from cortex_command.overnight.orchestrator import BatchResult`
  - `conflict.py` TYPE_CHECKING block: `from cortex_command.overnight.batch_runner import BatchConfig` → `from cortex_command.overnight.orchestrator import BatchConfig`
- **Verification**: `grep -rn "from cortex_command.overnight.batch_runner import" claude/overnight/__init__.py claude/overnight/smoke_test.py claude/overnight/state.py claude/pipeline/conflict.py` returns 0 matches

---

### Task 7: Update test import paths (`test_exit_report.py`, `test_trivial_conflict.py`, `test_repair_agent.py`, `test_overnight_state.py`)
- [x]
- **Files**: `claude/overnight/tests/test_exit_report.py`, `claude/pipeline/tests/test_trivial_conflict.py`, `claude/pipeline/tests/test_repair_agent.py`, `claude/overnight/tests/test_overnight_state.py`
- **What**: Update `from cortex_command.overnight.batch_runner import ...` in each test file to use canonical module locations. Do not change test logic — only import lines.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**:
  - `test_exit_report.py` line 18: `from cortex_command.overnight.batch_runner import BatchConfig, execute_feature` → split: `BatchConfig` from `claude.overnight.orchestrator`; `execute_feature` from `claude.overnight.feature_executor`
  - `test_trivial_conflict.py` line 32: `from cortex_command.overnight.batch_runner import execute_feature` → `from cortex_command.overnight.feature_executor import execute_feature`
  - `test_repair_agent.py` line 23: `from cortex_command.overnight.batch_runner import execute_feature` → `from cortex_command.overnight.feature_executor import execute_feature`
  - `test_overnight_state.py` line 16: `from cortex_command.overnight.batch_runner import BatchResult` → `from cortex_command.overnight.orchestrator import BatchResult`
- **Verification**: `grep -rn "from cortex_command.overnight.batch_runner import" claude/overnight/tests/test_exit_report.py claude/overnight/tests/test_overnight_state.py claude/pipeline/tests/test_trivial_conflict.py claude/pipeline/tests/test_repair_agent.py` returns 0 matches

---

### Task 8: Update `test_outcome_router.py` — `consecutive_pauses_ref` → `cb_state.consecutive_pauses`
- [x]
- **Files**: `claude/overnight/tests/test_outcome_router.py`
- **What**: Update all `OutcomeContext` construction calls and assertions. In the `_make_ctx` helper: replace `consecutive_pauses_ref` parameter with `cb_state: Optional[CircuitBreakerState] = None` and initialize as `CircuitBreakerState(consecutive_pauses=pauses)`. Update all 8+ `ctx.consecutive_pauses_ref[0]` assertions to `ctx.cb_state.consecutive_pauses`. Add `CircuitBreakerState` import.
- **Depends on**: [1, 4]
- **Complexity**: simple
- **Context**:
  - `_make_ctx` helper (line ~351): `consecutive_pauses_ref: Optional[list[int]] = None` parameter; line 47 construction: `consecutive_pauses_ref=pauses if pauses is not None else [0]` → `cb_state=CircuitBreakerState(consecutive_pauses=pauses if pauses is not None else 0)`
  - Assertion sites (lines 104, 141, 177, 202, 241, 271 and additional occurrences): `ctx.consecutive_pauses_ref[0]` → `ctx.cb_state.consecutive_pauses`
  - Add: `from cortex_command.overnight.types import CircuitBreakerState`
- **Verification**: `grep -c "consecutive_pauses_ref" claude/overnight/tests/test_outcome_router.py` = 0

---

### Task 9: Migrate `TestAccumulateResultViaBatch` patch targets in `test_lead_unit.py`
- [x]
- **Files**: `claude/overnight/tests/test_lead_unit.py`
- **What**: Replace all `batch_runner` module references with canonical targets. Update the module alias, top-level imports, and every `patch.object` / string patch call. Do not delete any tests — only update targets and import paths.
- **Depends on**: [2, 3, 5, 6, 7, 8]
- **Complexity**: complex
- **Context**:
  - Line 21: `import cortex_command.overnight.batch_runner as batch_runner_module` → `import cortex_command.overnight.orchestrator as orchestrator_module`
  - Line 24: `from cortex_command.overnight.batch_runner import (BatchConfig, BatchResult, CIRCUIT_BREAKER_THRESHOLD, ...)` → split imports: `BatchConfig, BatchResult` from `claude.overnight.orchestrator`; `CIRCUIT_BREAKER_THRESHOLD` from `claude.overnight.constants`; `FeatureResult` from `claude.overnight.types`; `execute_feature` from `claude.overnight.feature_executor`
  - `patch.object(batch_runner_module, "parse_master_plan", ...)` → `patch.object(orchestrator_module, "parse_master_plan", ...)` — the enumerated lines (168, 184, 199, 214, 228, 245, 269, 293, 309, 327, 419, 503) are examples only; do a **full-file pass** to catch all occurrences, including those at lines 579, 786, 983, 1000, 1010, 1022 and any others in test classes beyond `TestAccumulateResultViaBatch`
  - `patch.object(batch_runner_module, "create_worktree", ...)` → `patch.object(orchestrator_module, "create_worktree", ...)`
  - `patch.object(batch_runner_module, "ConcurrencyManager", ...)` → `patch.object(orchestrator_module, "ConcurrencyManager", ...)`
  - `patch.object(batch_runner_module, "overnight_log_event", ...)` → `patch.object(orchestrator_module, "overnight_log_event", ...)`
  - `transition` patch target: **`claude.overnight.orchestrator.transition`** (string form: `"claude.overnight.orchestrator.transition"`) — NOT `claude.overnight.state.transition`. When `orchestrator.py` does `from cortex_command.overnight.state import transition`, the name `transition` is bound in `orchestrator.__dict__`. Calls inside `orchestrator.py` look up `transition` in `orchestrator.__dict__`, so patching `claude.overnight.state.transition` is invisible to those calls; the correct target is `claude.overnight.orchestrator.transition`.
  - `_install_common_patches` helper in `TestAccumulateResultViaBatch` (lines ~1472–1530): contains ~10 string-form patches such as `self._start_patch("claude.overnight.batch_runner.parse_master_plan", ...)` and `self._start_patch("claude.overnight.batch_runner.save_batch_result", ...)` — migrate all to `claude.overnight.orchestrator.*` targets. `save_batch_result` appears only here and must not be omitted.
  - Inline local imports at lines 355, 460, 1560, 1587, 1611, 1664, 1700, 1736, 1775, 1811: `from cortex_command.overnight.batch_runner import run_batch` → `from cortex_command.overnight.orchestrator import run_batch`
  - Line 1467: `from cortex_command.overnight.batch_runner import FeatureResult as _FR` → `from cortex_command.overnight.types import FeatureResult as _FR` (destination is `claude.overnight.types`, not `orchestrator`)
- **Verification**: `grep -c "claude.overnight.batch_runner" claude/overnight/tests/test_lead_unit.py` = 0; `just test` exits 0

---

### Task 10: Add `test_orchestrator.py` integration tests for `orchestrator.run_batch`
- [x]
- **Files**: `claude/overnight/tests/test_orchestrator.py`
- **What**: Create a new `unittest.IsolatedAsyncioTestCase` test class with ≥5 async test methods covering all required scenarios from spec R8: multi-feature batch dispatch; concurrency semaphore acquire/release per feature; circuit breaker firing halts further dispatch; budget exhaustion prevents `apply_feature_result` call; heartbeat task is cancelled and awaited after `run_batch` completes. Use `autospec=True` on `execute_feature` and `apply_feature_result` mocks.
- **Depends on**: [1, 2, 4, 5, 6, 7, 8, 9]
- **Complexity**: complex
- **Context**:
  - Class: `class TestOrchestratorRunBatch(unittest.IsolatedAsyncioTestCase)`
  - Follow conftest stub pattern: conftest installs stubs before any imports; test file must not import `claude_agent_sdk` or `backlog.update_item` directly
  - Patch string targets use `claude.overnight.orchestrator.*` namespace: `claude.overnight.orchestrator.parse_master_plan`, `claude.overnight.orchestrator.create_worktree`, `claude.overnight.orchestrator.execute_feature`, `claude.overnight.orchestrator.ConcurrencyManager`, `claude.overnight.orchestrator.overnight_log_event`, `claude.overnight.orchestrator.load_state`, `claude.overnight.orchestrator.save_state`, `claude.overnight.orchestrator.save_batch_result`; `transition` → `claude.overnight.orchestrator.transition`
  - `apply_feature_result` patch target: `claude.overnight.outcome_router.apply_feature_result` (imported as `outcome_router.apply_feature_result` inside orchestrator)
  - Scenario — multi-feature: mock `parse_master_plan` returning 2 `FeaturePlan` stubs; mock `execute_feature` with `autospec=True`; assert called for both features; assert `BatchResult` accumulates results
  - Scenario — semaphore: mock `ConcurrencyManager` with `AsyncMock` for `acquire`/`release`; assert each called once per feature
  - Scenario — circuit breaker: patch `claude.overnight.orchestrator.CircuitBreakerState` to return `CircuitBreakerState(consecutive_pauses=CIRCUIT_BREAKER_THRESHOLD)` so that when `_run_one` constructs `CircuitBreakerState()`, it gets the pre-seeded instance; `CIRCUIT_BREAKER_THRESHOLD` must be imported from `claude.overnight.constants` in the test file; assert `result.circuit_breaker_fired = True` and `execute_feature` not called after threshold is reached
  - Scenario — budget exhaustion: patch the internal budget check (whatever callable `_run_one` uses, e.g., a helper function bound in the orchestrator module) to return `True`; assert `result.global_abort_signal = True`; assert `apply_feature_result` mock with `autospec=True` was never called
  - Scenario — heartbeat lifecycle: because `orchestrator.py` uses `from asyncio import create_task` at module level (Task 2), patch `claude.overnight.orchestrator.create_task` to capture the task object returned; after `run_batch` returns, assert `task.cancel()` was called AND `task.cancelled()` is True (requires awaiting the task post-cancel in `addCleanup`); use `addCleanup` to await the task (catching `CancelledError`) so no "task destroyed but pending" warnings appear
  - Use `addCleanup(p.stop)` pattern for all `patch.start()` calls — consistent with existing tests
- **Verification**: `grep -c "class.*IsolatedAsyncioTestCase" claude/overnight/tests/test_orchestrator.py` ≥ 1; `grep -c "def test_" claude/overnight/tests/test_orchestrator.py` ≥ 5; `just test` exits 0

---

### Task 11: Update `requirements/pipeline.md` — Session Orchestration section
- [x]
- **Files**: `requirements/pipeline.md`
- **What**: In the Session Orchestration section, replace references to `batch_runner.py` as the session management module with `orchestrator.py`. The file may retain `batch_runner.py` in CLI invocation examples (e.g., `python3 -m claude.overnight.batch_runner`).
- **Depends on**: none
- **Complexity**: simple
- **Context**: Scan `requirements/pipeline.md` for "batch_runner.py" in prose descriptions; update session-management description text to name `orchestrator.py`; do not change CLI invocation examples
- **Verification**: `grep "orchestrator.py" requirements/pipeline.md` ≥ 1 match; `grep -c "batch_runner.py" requirements/pipeline.md` ≤ 1

---

## Verification Strategy

After all 11 tasks complete, run the full acceptance suite:

```
just test                                                   # exit 0 — all tests pass
grep -c "async def run_batch" claude/overnight/orchestrator.py          # = 1
grep -c "class BatchConfig" claude/overnight/orchestrator.py            # = 1
grep -c "class BatchConfig" claude/overnight/batch_runner.py            # = 0
wc -l < claude/overnight/batch_runner.py                                # ≤ 50
grep -c "class CircuitBreakerState" claude/overnight/types.py           # = 1
grep -rn "consecutive_pauses_ref" claude/overnight/                     # 0 matches
grep -c "global_abort_signal = True" claude/overnight/outcome_router.py # = 0
grep -rn "from cortex_command.overnight.batch_runner import" claude/            # 0 matches
python3 -m claude.overnight.batch_runner --help                         # exit 0
python3 -c "from cortex_command.overnight import BatchConfig, run_batch"        # exit 0
grep -c "class.*IsolatedAsyncioTestCase" claude/overnight/tests/test_orchestrator.py # ≥ 1
grep -c "def test_" claude/overnight/tests/test_orchestrator.py         # ≥ 5
grep -c "claude.overnight.batch_runner" claude/overnight/tests/test_lead_unit.py # = 0
```

## Veto Surface

- **`CircuitBreakerState` in `types.py`**: If placed in `orchestrator.py` instead, `outcome_router.py` would need to import from `orchestrator.py` at runtime — creating a circular import (`orchestrator` → `outcome_router` → `orchestrator`). Keeping it in `types.py` (alongside `FeatureResult`) avoids this entirely.
- **No `_accumulate_result` revival**: The budget exhaustion logic becomes an inline check inside `_run_one` rather than a revived named inner function. This is intentionally simpler; if the implementer prefers a named helper for readability, that's acceptable as long as it lives within `orchestrator.py` and is not a method of a class.
- **`transition` patch target**: `claude.overnight.orchestrator.transition`, not `claude.overnight.state.transition`. When `orchestrator.py` does `from cortex_command.overnight.state import transition`, the name `transition` is bound in `orchestrator.__dict__`. Calls inside `orchestrator.py` look up `transition` in `orchestrator.__dict__`, so patching `claude.overnight.state.transition` is invisible to those calls. The correct patch target is `claude.overnight.orchestrator.transition`.
- **Task ordering**: Tasks 4 and 5 both depend on [1, 2] and can run in parallel; Tasks 6 and 7 can run in parallel; Task 10 can begin as soon as Tasks 1, 2, 4, 5 complete. Task 11 is fully independent.

## Scope Boundaries

- No behavioral changes to overnight session execution — pure structural refactor
- `orchestrator_io.py` is untouched (separate, unrelated module)
- No logic changes to `feature_executor.py` or `outcome_router.py` beyond the `consecutive_pauses_ref` field rename, TYPE_CHECKING import path updates, and adding `CircuitBreakerState` import
- No changes to `state.py`, `throttle.py`, `deferral.py`, `brain.py`, `strategy.py` beyond the TYPE_CHECKING import path update in `state.py`
- Daytime pipeline driver (Phase 5 / #078) is out of scope
