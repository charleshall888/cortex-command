# Research: Rename batch_runner to orchestrator and add integration tests

**Feature**: rename-batch-runner-to-orchestrator-and-add-integration-tests  
**Lifecycle**: #077  
**Date**: 2026-04-14  
**Tier**: complex | **Criticality**: high

## Epic Reference

Background context from the parent epic: `research/implement-in-autonomous-worktree-overnight-component-reuse/research.md`

The epic research (DR-5) established that the 3-phase batch_runner decomposition is the primary value driver. Phases 1 and 2 (feature_executor.py and outcome_router.py extraction) were completed in #076. This ticket covers Phases 3 and 4: creating orchestrator.py as the session layer and adding integration tests for `orchestrator.run_batch`.

## Codebase Analysis

### Current state of batch_runner.py after #076

`claude/overnight/batch_runner.py` is **456 LOC** — not yet a thin CLI wrapper. It still contains:

- **`BatchConfig`** (dataclass, lines 78–100): `batch_id`, `plan_path`, `test_command`, `base_branch`, `overnight_state_path`, `overnight_events_path`, `result_dir`, `pipeline_events_path`, `throttle_tier`
- **`BatchResult`** (dataclass, lines 102–126): `batch_id`, `features_merged`, `features_paused`, `features_deferred`, `features_failed`, `circuit_breaker_fired`, `global_abort_signal`, `abort_reason`, `key_files_changed`
- **`run_batch()`** (lines 128–401): the session-layer orchestration loop — round scheduling, worktree creation, concurrency management, final state write-back, heartbeat task creation
- **`_accumulate_result()`** (inner function, lines 191–241): **not a thin shim** — contains ~50 lines of real logic: `budget_exhausted` detection, `global_abort_signal` set, state write, `BATCH_BUDGET_EXHAUSTED` event emission, then `OutcomeContext` construction and delegation to `outcome_router.apply_feature_result`
- **`_run_one()`** (inner function, lines 243–289): pre/post semaphore circuit breaker checks, `FEATURE_START` event emission, `manager.acquire/release` around `execute_feature`, then calls `_accumulate_result`
- **`_heartbeat_loop()`** + **`_derive_session_id()`** (lines 296–339): heartbeat background task, async
- **`build_parser()`** + **`_run()`** (lines 408–452): CLI entrypoint (argparse, `asyncio.run`)

**`claude/overnight/orchestrator.py` does not exist.** `orchestrator_io.py` is a separate, unrelated 4-function re-export shim for sanctioned orchestrator agent imports — it is not the destination for Phase 3.

### BatchConfig / BatchResult location and import graph

Both are defined in `batch_runner.py`. Current importers:

**Runtime imports (will need updating after rename):**
- `claude/overnight/__init__.py` — re-exports `BatchConfig`, `BatchResult`, `run_batch`
- `claude/overnight/smoke_test.py` — `BatchConfig, run_batch` directly
- `claude/overnight/tests/test_lead_unit.py` — `BatchResult`, `BatchConfig`, `CIRCUIT_BREAKER_THRESHOLD`, `FeatureResult`, `execute_feature` (the last two are not defined in batch_runner; they are imported there from `types.py` and `feature_executor.py` — this re-export chain will break after rename unless explicitly preserved)
- `claude/overnight/tests/test_exit_report.py` — `BatchConfig, execute_feature`
- `claude/pipeline/tests/test_trivial_conflict.py` — `execute_feature`
- `claude/pipeline/tests/test_repair_agent.py` — `execute_feature`
- `claude/overnight/tests/test_overnight_state.py` — `BatchResult`

**TYPE_CHECKING-only imports (no circular risk; still need path updates):**
- `claude/overnight/feature_executor.py` — `BatchConfig`
- `claude/overnight/outcome_router.py` — `BatchResult, BatchConfig`
- `claude/overnight/state.py` — `BatchResult`
- `claude/pipeline/conflict.py` — `BatchConfig`

**Design constraint**: `CIRCUIT_BREAKER_THRESHOLD` is imported by `test_lead_unit.py` from `claude.overnight.batch_runner` but is actually defined in `claude.overnight.constants`. This re-export chain must be preserved or re-routed after the move.

### consecutive_pauses_ref current state

Initialized in `run_batch()` as `consecutive_pauses_ref = [0]` (a mutable `list[int]` used as a pass-by-reference counter).

Flow:
- Passed into `OutcomeContext.consecutive_pauses_ref: list[int]` (outcome_router.py line 68)
- Mutated extensively inside `outcome_router._apply_feature_result` (read/write at ~12 sites, lines 467, 506, 533, 586, 653, 702, 721, 735, 907, 1044, 1063, 1090, 1098)
- Passed separately into `feature_executor.execute_feature` → `_handle_failed_task` (read-only, line 200 — only checks the circuit-breaker soft threshold, does not mutate)

A `CircuitBreakerState` dataclass conversion would touch:
1. `batch_runner.py` (initialization)
2. `outcome_router.py` (OutcomeContext field declaration + all ~12 mutation/read sites in `_apply_feature_result`)
3. `feature_executor.py` (read in `_handle_failed_task`)
4. All test files that construct `consecutive_pauses_ref=[0]` literals

### Integration test infrastructure

- **Test runner**: `just test` (stdlib `unittest`, not pytest)
- **Async tests**: `unittest.IsolatedAsyncioTestCase` — pytest-asyncio is explicitly not a project dependency
- **Mocking pattern**: `unittest.mock.patch` with string targets, `MagicMock`, `AsyncMock`; `addCleanup(p.stop)` pattern
- **Conftest** (`claude/overnight/tests/conftest.py`): stubs `backlog.update_item` and `claude_agent_sdk` before any test imports
- **Existing run_batch tests**: in `test_lead_unit.py` `TestAccumulateResultViaBatch` (lines 1395–1775+) — drives `run_batch()` with heavy mocking of `parse_master_plan`, `create_worktree`, `load_state`, `execute_feature`, `merge_feature`, `recover_test_failure`
- **No `test_orchestrator.py` exists** — integration tests for orchestrator.run_batch are a new file

The `TestAccumulateResultViaBatch` class in `test_lead_unit.py` is the baseline to migrate/replace. It currently patches `claude.overnight.batch_runner.*` — after rename the patch targets become `claude.overnight.orchestrator.*`.

### Prior precedent for this rename pattern

- `claude/pipeline/review_dispatch.py` was extracted from batch_runner in an earlier phase and the boundary survived. Same extraction pattern applies.
- `feature_executor.py` and `outcome_router.py` were extracted in #076; import structure is already stable.
- `__init__.py` re-exports are the canonical way consumers access batch_runner symbols — keeping this file updated avoids needing to hunt down all importers.

## Open Questions

- **BatchConfig/BatchResult home after Phase 3**: Three options — (a) stay in batch_runner.py (inverted dependency: CLI wrapper exports types used by orchestrator), (b) move to orchestrator.py (natural home, ~7 import sites need updating), (c) promote to `claude/overnight/types.py` or a new `claude/overnight/config.py` (cleanest but extra file). Decision gates the import restructuring scope.

- **`_accumulate_result` budget_exhausted logic disposition**: The ticket describes `_accumulate_result()` as "(collapsed to single call into outcome_router)" — but the function contains real logic (budget_exhausted detection, global_abort_signal, state write, event emission) that is **not** currently in outcome_router. This logic must either (a) move into `outcome_router.apply_feature_result` as a new pre-routing step, or (b) become a named function in `orchestrator.py` called before delegating to outcome_router. Option (a) cleanly centralizes budget logic in outcome_router; option (b) keeps the orchestrator layer aware of budget state. Design decision needed in spec.

- **`consecutive_pauses_ref` cleanup decision**: The ticket defers this to spec. The dataclass conversion path is non-trivial (~3 files + test updates); leaving it as `list[int]` avoids churn but leaves a sharp edge in the API. Spec should pick one approach and specify the OutcomeContext field type accordingly — since integration test mocking of the circuit-breaker boundary depends on this choice.

- **`test_lead_unit.py` import re-routing**: `test_lead_unit.py` imports `FeatureResult` and `execute_feature` from `claude.overnight.batch_runner` (not their canonical locations). After rename, these break unless the new `batch_runner.py` thin wrapper re-exports them (adding import indirection) or tests are updated to import from canonical locations. The cleaner path is to update tests.
