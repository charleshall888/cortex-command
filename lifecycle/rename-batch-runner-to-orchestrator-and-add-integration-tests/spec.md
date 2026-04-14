# Specification: Rename batch_runner to orchestrator and add integration tests

**Feature**: rename-batch-runner-to-orchestrator-and-add-integration-tests  
**Lifecycle**: #077  
**Date**: 2026-04-14  
**Tier**: complex | **Criticality**: high

## Problem Statement

`claude/overnight/batch_runner.py` (456 LOC after #076) still contains all session-layer logic — `run_batch()`, `_run_one()`, `_accumulate_result()`, heartbeat, session state initialization, worktree creation, and final persistence — alongside `BatchConfig`, `BatchResult`, and the CLI entry point. This mixes session orchestration with CLI plumbing in one file and leaves the core overnight orchestration path with no dedicated integration tests. Phase 3 of the batch_runner decomposition creates `orchestrator.py` as the session layer, makes `batch_runner.py` a thin ~30 LOC CLI wrapper, and adds integration tests for `orchestrator.run_batch`. This is the final regression gate for the three-phase refactor and closes the `python3 -m claude.overnight.batch_runner` invocation contract.

## Requirements

1. **[must-have]** **Create `claude/overnight/orchestrator.py`** containing all session-layer logic: `run_batch()`, `_run_one()`, budget exhaustion detection, `_heartbeat_loop()`, `_derive_session_id()`, session state initialization (spec_paths, backlog_ids, recovery_attempts, repo_paths, integration branches/worktrees), worktree creation for all features, final persistence (recovery_attempts write-back, budget-exhausted pause, session phase transitions), and global constraints (circuit breaker check gate, abort signal propagation).  
   Acceptance: `grep -c "async def run_batch" claude/overnight/orchestrator.py` = 1

2. **[must-have]** **Move `BatchConfig` and `BatchResult` to `orchestrator.py`** so the CLI wrapper imports from the session layer, not the reverse.  
   Acceptance: `grep -c "class BatchConfig" claude/overnight/orchestrator.py` = 1; `grep -c "class BatchConfig" claude/overnight/batch_runner.py` = 0

3. **[must-have]** **Reduce `batch_runner.py` to a thin CLI wrapper** (~30–40 LOC): argparse parser via `build_parser()`, `BatchConfig` construction, and `asyncio.run(run_batch(config))` via `_run()`. `build_parser()` and `_run()` are preserved by name for CLI contract compatibility.  
   Acceptance: `wc -l < claude/overnight/batch_runner.py` ≤ 50

4. **[must-have]** **Add `CircuitBreakerState` dataclass to `claude/overnight/types.py`** (alongside `FeatureResult`) with field `consecutive_pauses: int = 0`. Replace all `consecutive_pauses_ref: list[int]` usage throughout the codebase — including in `outcome_router.py` (all ~12 mutation/read sites in `_apply_feature_result`), `feature_executor.py` (`_handle_failed_task` signature at line 186 and threshold comparison at line 200), `OutcomeContext` field declaration, and `test_outcome_router.py` (8+ direct assertions on `ctx.consecutive_pauses_ref[0]`) — using `cb_state: CircuitBreakerState` as the field/parameter name and `.consecutive_pauses` as the accessor.  
   Acceptance: `grep -c "class CircuitBreakerState" claude/overnight/types.py` = 1; `grep -rn "consecutive_pauses_ref" claude/overnight/` returns 0 matches

5. **[must-have]** **Budget exhaustion detection lives in orchestrator.py** (`_run_one` or a named helper). Before constructing `OutcomeContext` and delegating to `outcome_router.apply_feature_result`, `_run_one` checks whether the budget is exhausted; if so, it writes state, emits the `BATCH_BUDGET_EXHAUSTED` event, sets `batch_result.global_abort_signal = True`, and returns without calling `outcome_router`. `outcome_router.py` may defensively read `batch_result.global_abort_signal` as a guard, but must not be the site that assigns it to `True`.  
   Acceptance: `grep -c "global_abort_signal" claude/overnight/orchestrator.py` ≥ 1; `grep -c "global_abort_signal = True" claude/overnight/outcome_router.py` = 0 (the assignment to True — budget detection — does not appear in outcome_router)

6. **[must-have]** **Update all import sites** to reference symbols from their canonical locations after the move:
   - `feature_executor.py`, `outcome_router.py`, `state.py`, `claude/pipeline/conflict.py` TYPE_CHECKING imports: `claude.overnight.batch_runner` → `claude.overnight.orchestrator`  
   - `smoke_test.py`, `claude/overnight/__init__.py`: import `BatchConfig`, `BatchResult`, `run_batch` from `orchestrator`  
   - `test_lead_unit.py`, `test_exit_report.py`, `test_trivial_conflict.py`, `test_repair_agent.py`, `test_overnight_state.py`: update imports to canonical locations (`FeatureResult` → `claude.overnight.types`, `execute_feature` → `claude.overnight.feature_executor`, `CIRCUIT_BREAKER_THRESHOLD` → `claude.overnight.constants`)  
   Acceptance: `grep -rn "from claude.overnight.batch_runner import" claude/` returns 0 matches (no remaining direct imports from batch_runner except the `if __name__ == "__main__"` block inside batch_runner itself, if any)

7. **[must-have]** **CLI invocation contract preserved**: `python3 -m claude.overnight.batch_runner --plan <path> --batch-id <id>` works unchanged.  
   Acceptance: `python3 -m claude.overnight.batch_runner --help` exits 0 (verifies argparse is wired in thin wrapper); `python3 -c "from claude.overnight import BatchConfig, run_batch"` exits 0 (verifies package import chain is clean); `just test` exits 0

8. **[must-have]** **Add `claude/overnight/tests/test_orchestrator.py`** with `unittest.IsolatedAsyncioTestCase` integration tests for `orchestrator.run_batch`. Required scenarios:
   - Multi-feature batch: 2+ features with mocked `execute_feature` (use `autospec=True`) + `outcome_router.apply_feature_result` (use `autospec=True`); assert all features are dispatched and results accumulated
   - Concurrency semaphore: mock `ConcurrencyManager`; assert `acquire`/`release` is called per feature
   - Circuit breaker firing: mock consecutive pauses at threshold; assert `circuit_breaker_fired=True` in `BatchResult` and no further features are dispatched
   - Budget exhaustion: mock `_budget_exhausted` returning `True` mid-batch; assert `global_abort_signal=True` and batch exits without calling `outcome_router.apply_feature_result`
   - Heartbeat task lifecycle: assert `_heartbeat_loop` is created as an `asyncio.Task`, and after `run_batch` completes the task is both cancelled and awaited (no "task was destroyed but it is pending" warnings)  
   Acceptance: `just test` exits 0; `grep -c "class.*IsolatedAsyncioTestCase" claude/overnight/tests/test_orchestrator.py` ≥ 1; `grep -c "def test_" claude/overnight/tests/test_orchestrator.py` ≥ 5

9. **[must-have]** **Migrate `TestAccumulateResultViaBatch` in `test_lead_unit.py`**: update patch targets from `claude.overnight.batch_runner.*` to their canonical module. Patch at the module where the symbol is defined or bound at call time — not at a re-export site. Key mappings: `execute_feature` → `claude.overnight.orchestrator`; `parse_master_plan`, `create_worktree`, `load_state`, `save_state`, `save_batch_result` → `claude.overnight.orchestrator` (where they are imported and used); `ConcurrencyManager` → `claude.overnight.orchestrator`; `overnight_log_event` → `claude.overnight.orchestrator`; `transition` (for session-phase writes) → `claude.overnight.state` (the canonical definition site — patch here, not `orchestrator.transition`). Do not delete existing tests — migrate them.  
   Acceptance: `just test` exits 0; `grep "claude.overnight.batch_runner" claude/overnight/tests/test_lead_unit.py` returns 0 matches

10. **[should-have]** **Update `requirements/pipeline.md`** to reference `orchestrator.py` (not `batch_runner.py`) as the session management module. The Session Orchestration section's description currently names `batch_runner.py`.  
    Acceptance: `grep "orchestrator.py" requirements/pipeline.md` matches ≥ 1 line; `grep "batch_runner.py" requirements/pipeline.md` returns 0 matches in session-management descriptions (the file may still reference `batch_runner.py` in the CLI invocation context)

## Non-Requirements

- This ticket does not build the daytime pipeline driver (Phase 5) — that remains a follow-on if TC4 evidence materializes
- No behavioral changes to overnight session execution — this is a pure structural refactor preserving all runtime behavior
- No changes to `feature_executor.py` or `outcome_router.py` logic (beyond import path updates and the `CircuitBreakerState` field rename in `OutcomeContext`)
- `orchestrator_io.py` is a separate, unrelated module — do not confuse it with the new `orchestrator.py`
- No logic changes to `state.py`, `throttle.py`, `deferral.py`, `brain.py`, `strategy.py` (import path update in `state.py` is in scope per R6; no other changes)

## Edge Cases

- **`__init__.py` re-export surface**: `claude/overnight/__init__.py` currently re-exports `BatchConfig`, `BatchResult`, `run_batch` from `batch_runner`. After the move, re-exports must be updated to import from `orchestrator`. Downstream code that imports via `claude.overnight` (not `claude.overnight.batch_runner` directly) will continue to work transparently.
- **Test conftest stubs**: `claude/overnight/tests/conftest.py` installs stubs before any import of batch_runner. Verify the stub still runs correctly after the import chain changes (stubs reference `backlog.update_item` and `claude_agent_sdk` — these should be unaffected by the batch_runner rename).
- **CIRCUIT_BREAKER_THRESHOLD re-export chain**: `test_lead_unit.py` imports this from `claude.overnight.batch_runner` but the canonical home is `claude.overnight.constants`. After the rename, this import must be updated to `claude.overnight.constants`.
- **Circular import safety**: After R6 updates TYPE_CHECKING imports in `feature_executor.py`, `outcome_router.py`, and `state.py` from `claude.overnight.batch_runner` to `claude.overnight.orchestrator`, all three files are safe from circular imports at runtime because all three have `from __future__ import annotations` (PEP 563), ensuring annotation-only references to `BatchConfig`/`BatchResult` are lazily evaluated as strings rather than triggering eager imports. Confirmed: `feature_executor.py:8`, `outcome_router.py:8`, `state.py:12`.
- **Heartbeat task leak in tests**: The heartbeat `asyncio.Task` must be properly cancelled and awaited in `test_orchestrator.py` to avoid "task was destroyed but it is pending" warnings. `asyncio.Task.cancel()` alone is not sufficient — the test must also `await` the task (expecting `CancelledError`).
- **`outcome_router` defensive guard**: After R5, `outcome_router.apply_feature_result` may retain a read-guard `if ctx.batch_result.global_abort_signal: return` at its entry point as a defensive check. This is permitted — only the assignment `global_abort_signal = True` (budget detection) must not appear in `outcome_router.py`.

## Changes to Existing Behavior

- ADDED: `claude/overnight/orchestrator.py` — new module containing session orchestration logic
- MODIFIED: `claude/overnight/batch_runner.py` — from 456 LOC session orchestrator to ≤50 LOC CLI wrapper
- MODIFIED: `claude/overnight/types.py` — `CircuitBreakerState` dataclass added; `FeatureResult` unchanged
- MODIFIED: `claude/overnight/outcome_router.py` — `OutcomeContext.consecutive_pauses_ref: list[int]` → `cb_state: CircuitBreakerState`; all ~12 mutation/read sites updated to `.consecutive_pauses`
- MODIFIED: `claude/overnight/feature_executor.py` — `_handle_failed_task` signature and threshold comparison updated; TYPE_CHECKING import path updated
- MODIFIED: `claude/overnight/__init__.py` — re-exports updated to point to `orchestrator`
- MODIFIED: `claude/overnight/tests/test_lead_unit.py` — patch targets and import paths updated; `TestAccumulateResultViaBatch` targets migrated
- MODIFIED: `claude/overnight/tests/test_outcome_router.py` — 8+ direct assertions on `ctx.consecutive_pauses_ref[0]` updated to `ctx.cb_state.consecutive_pauses`
- ADDED: `claude/overnight/tests/test_orchestrator.py` — new integration test file
- MODIFIED: `requirements/pipeline.md` — Session Orchestration section updated to reference `orchestrator.py`

## Technical Constraints

- **stdlib unittest only**: No `pytest-asyncio`. Async tests use `unittest.IsolatedAsyncioTestCase` — established in #076 and all prior overnight test files.
- **Mocking pattern**: String-form `unittest.mock.patch` targets, `MagicMock`, `AsyncMock`, `addCleanup(p.stop)` — consistent with existing test patterns. For the new `test_orchestrator.py` integration tests, use `autospec=True` on `execute_feature` and `apply_feature_result` mocks to prevent silent no-op patching if function signatures drift during the refactor.
- **`orchestrator_io.py` is unrelated**: The existing `claude/overnight/orchestrator_io.py` is a 4-function state-management re-export shim for sanctioned orchestrator agents. The new `orchestrator.py` is a different module — do not rename or modify `orchestrator_io.py`.
- **No inverted dependency**: After the move, `batch_runner.py` imports from `orchestrator.py` (CLI wrapper depends on session layer). `orchestrator.py` must not import from `batch_runner.py`.
- **Atomic state writes**: The `os.replace()` atomic write pattern for `overnight-state.json` is already implemented in `state.py` and called from within `run_batch`'s final persistence logic. This constraint is preserved as-is when the logic moves to `orchestrator.py`.
- **Patch target placement**: When migrating test patches, use the module where the symbol is defined or bound at call time — not the import chain. `from claude.overnight.state import transition` in orchestrator means the correct patch target for `transition` is `claude.overnight.state.transition`, not `claude.overnight.orchestrator.transition`.

## Open Decisions

- None. All design decisions resolved during the spec interview.
