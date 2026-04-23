# Review: extract-outcome-router-module-from-batch-runner (Cycle 2)

## Stage 1: Spec Compliance

### Requirement 1: New `outcome_router.py` module
- **Expected**: `claude/overnight/outcome_router.py` exists with `apply_feature_result` and `OutcomeContext`.
- **Actual**: File exists. `grep -c 'class OutcomeContext'` = 1. `async def apply_feature_result` at line 760.
- **Verdict**: PASS

### Requirement 2: `OutcomeContext` dataclass
- **Expected**: `@dataclass` with the 13 specified fields; `from __future__ import annotations`; `BatchResult`/`BatchConfig` only under `TYPE_CHECKING`.
- **Actual**: `from __future__ import annotations` at line 8; `TYPE_CHECKING` guard block at lines 19–20 and 57 for type-only imports; dataclass at line 65. Module imports cleanly; `batch_runner` imports cleanly — no circular import.
- **Verdict**: PASS

### Requirement 3: `apply_feature_result` public contract
- **Expected**: `async def apply_feature_result(name, result, ctx)` that owns the lock; all listed helpers moved out of `batch_runner.py`.
- **Actual**: `grep -c` for the seven function defs in `batch_runner.py` = 0. All helpers present in `outcome_router.py`. `async def apply_feature_result` acquires `async with ctx.lock:` on entry; two-phase lock pattern preserved (release for `recover_test_failure`, re-acquire for recovery result routing).
- **Verdict**: PASS

### Requirement 4: `_accumulate_result` becomes a short shim
- **Expected**: Shim performs (1) budget_exhausted early-exit, (2) OutcomeContext construction, (3) delegation without holding the lock. Explicit criterion: `grep -c 'budget_exhausted|global_abort_signal' claude/overnight/outcome_router.py` = 0.
- **Actual**: Cycle 1's duplicated budget_exhausted block has been removed from `outcome_router.apply_feature_result`. `grep -c 'budget_exhausted\|global_abort_signal' claude/overnight/outcome_router.py` = **0** (was 7 in cycle 1). The shim in `batch_runner.py` (lines 191–241) handles budget_exhausted detection + `load_state`/`save_state`/`overnight_log_event(BATCH_BUDGET_EXHAUSTED)` outside the lock, then constructs `OutcomeContext` and delegates. Shim is ~50 lines — marginally above the spec's "~40 lines max" soft limit but the delta comes from the budget_exhausted try/except block that must stay in the shim per the spec's session-layer pin; acceptable. `grep -c 'budget_exhausted\|global_abort_signal' claude/overnight/batch_runner.py` = 9 (≥ 1 required). `grep -c 'await outcome_router.apply_feature_result' claude/overnight/batch_runner.py` = 1.
- **Verdict**: PASS

### Requirement 5: Import boundary enforcement
- **Expected**: Zero runtime imports from `claude.overnight.batch_runner` in `outcome_router.py`; boundary test exists and passes.
- **Actual**: `test_outcome_router_boundary.py` AST-walks the module, excludes `TYPE_CHECKING`-guarded imports, and asserts no runtime `claude.overnight.batch_runner` references. `just test-overnight` → 261 passed, 1 xpassed.
- **Verdict**: PASS

### Requirement 6: Both circuit-breaker sites preserved
- **Expected**: `grep -c 'CIRCUIT_BREAKER_THRESHOLD' claude/overnight/outcome_router.py` ≥ 2.
- **Actual**: 3 occurrences (import + two check sites).
- **Verdict**: PASS

### Requirement 7: `recovery_attempts_map` persistence preserved
- **Expected**: State-write of `recovery_attempts` after increment, inside the lock on recovery dispatch.
- **Actual**: Present inside `apply_feature_result`; `TestRecoveryDispatchPersistence` passes as part of `just test-overnight`.
- **Verdict**: PASS

### Requirement 8: Unit tests for outcome routing
- **Expected**: ≥ 8 tests covering status transitions, circuit breaker, backlog write-back, review gating, post-merge recovery.
- **Actual**: `test_outcome_router.py` contains 9 test functions covering all required scenarios.
- **Verdict**: PASS

### Requirement 9: Existing test suite passes with migrated patch targets
- **Expected**: All existing tests pass; `_apply_feature_result`/`_write_back_to_backlog`/`merge_feature`/`recover_test_failure` patches migrated away from `batch_runner_module` in `test_lead_unit.py`.
- **Actual**: Migration grep returns 0. Full suite passes (`just test-overnight` 261 passed, 1 xpassed).
- **Verdict**: PASS

### Requirement 10: `batch_runner.py` imports `outcome_router`
- **Expected**: Import statement present; CLI entry point still works.
- **Actual**: `from cortex_command.overnight import outcome_router` + `from cortex_command.overnight.outcome_router import OutcomeContext` present. `python3 -m claude.overnight.batch_runner --help` exits 0.
- **Verdict**: PASS

## Stage 2: Code Quality

- **Naming conventions**: Consistent with `feature_executor.py` pattern — module-level `async def` public entry, `OutcomeContext` dataclass, private `_` prefix on helpers, `TYPE_CHECKING` guard matches Phase 1 precedent.
- **Error handling**: budget_exhausted state-write in the shim wraps `load_state`/`save_state` in try/except so a persistence failure cannot abort the batch — matches pre-extraction behavior.
- **Test coverage**: 9 unit tests in `test_outcome_router.py` directly exercise the extracted module with mocked `merge_feature`/`recover_test_failure`/review helpers. Boundary test (`test_outcome_router_boundary.py`) enforces the import rule statically. Regression coverage preserved via migrated `TestApplyFeatureResult`/`TestAccumulateResultViaBatch` patch targets.
- **Pattern consistency**: Extraction follows the Phase 1 `feature_executor.py` template — same `from __future__ import annotations`, same `TYPE_CHECKING` pattern for `BatchResult`/`BatchConfig`, same "shim delegates after minimal session-layer work" contract.
- **Rework quality**: The cycle 1 duplication fix is clean — the duplicated block was removed entirely from `outcome_router.apply_feature_result`, leaving the shim as the single authoritative site for budget_exhausted. No vestigial references (e.g. `ctx.batch_result.global_abort_signal` reads) remain in the router.

## Requirements Drift

**State**: none
**Findings**:
- None
**Update needed**: None

## Verdict

```json
{"verdict": "APPROVED", "cycle": 2, "issues": [], "requirements_drift": "none"}
```
