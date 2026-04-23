# Review: rename-batch-runner-to-orchestrator-and-add-integration-tests

## Stage 1: Spec Compliance

### R1: Create `claude/overnight/orchestrator.py` with all session-layer logic
- **Expected**: New module with `run_batch`, `_run_one`, heartbeat, session init, worktree creation, final persistence, circuit-breaker gate, abort propagation.
- **Actual**: `claude/overnight/orchestrator.py` exists (412 LOC) with `run_batch` (line 112), `_run_one` (line 175), `_heartbeat_loop` (line 281), `_derive_session_id` (line 273), session state init (lines 129–156), worktree creation (lines 159–164), and final persistence (lines 360–392). `grep -c "async def run_batch"` = 1.
- **Verdict**: PASS
- **Notes**: Module docstring explicitly notes no reverse dependency on `batch_runner`; matches constraint.

### R2: Move `BatchConfig` and `BatchResult` to `orchestrator.py`
- **Expected**: Dataclasses live in orchestrator; batch_runner imports them.
- **Actual**: `class BatchConfig` on orchestrator.py line 62, `class BatchResult` on line 88. `batch_runner.py` imports them via `from cortex_command.overnight.orchestrator import BatchConfig, BatchResult, run_batch` (line 12). `grep -c "class BatchConfig"` orchestrator = 1, batch_runner = 0.
- **Verdict**: PASS

### R3: Reduce `batch_runner.py` to thin CLI wrapper (≤50 LOC)
- **Expected**: ~30–40 LOC, `build_parser()` + `_run()` preserved.
- **Actual**: `wc -l batch_runner.py` = 48. Retains `build_parser()` (line 15) and `_run()` (line 27). Only logic is argparse + BatchConfig construction + `asyncio.run(run_batch(config))`.
- **Verdict**: PASS

### R4: Add `CircuitBreakerState` to `types.py`; eliminate `consecutive_pauses_ref`
- **Expected**: `CircuitBreakerState` dataclass in types.py; `grep -rn "consecutive_pauses_ref" claude/overnight/` = 0.
- **Actual**: `class CircuitBreakerState` at `types.py:35` with `consecutive_pauses: int = 0`. Grep returns 2 docstring-only references (test_lead_unit.py:945 in a class docstring, test_brain.py:277 in a test method docstring). All runtime usages eliminated — parameters, fields, and assertions are migrated to `cb_state.consecutive_pauses` throughout.
- **Verdict**: PARTIAL
- **Notes**: Strict `grep` acceptance fails with 2 matches; both are historical references in docstrings that describe test intent. The architectural intent (no code-level usage of the old name) is fully satisfied. Minor cleanup opportunity — not a functional defect.

### R5: Budget exhaustion detection lives in `orchestrator.py`; not in `outcome_router.py`
- **Expected**: `_run_one` in orchestrator detects budget exhaustion and sets `global_abort_signal = True`; outcome_router does not assign it.
- **Actual**: orchestrator.py lines 226–249 contain the inline budget-exhaustion check that sets `batch_result.global_abort_signal = True`, writes state, emits `BATCH_BUDGET_EXHAUSTED`, and returns without calling outcome_router. `grep global_abort_signal claude/overnight/outcome_router.py` = 0 matches (no read-guard or assignment). `grep global_abort_signal orchestrator.py` = 8 matches.
- **Verdict**: PASS

### R6: Update all import sites to canonical locations
- **Expected**: `grep -rn "from cortex_command.overnight.batch_runner import" claude/` = 0.
- **Actual**: One match remains: `claude/overnight/daytime_pipeline.py:25: from cortex_command.overnight.batch_runner import BatchConfig`. `daytime_pipeline.py` is owned by a separate parallel lifecycle (#078) whose commits interleave with #077; it was added before orchestrator.py existed. All files listed in R6 and in the plan's Changed Files list are correctly migrated. The import still resolves because batch_runner re-exports via `from cortex_command.overnight.orchestrator import BatchConfig, BatchResult, run_batch` (with `noqa: F401`).
- **Verdict**: PARTIAL
- **Notes**: Strict acceptance fails by 1 match in a cross-lifecycle file not in #077's scope. Non-blocking: the re-export means imports still work. Worth updating daytime_pipeline.py's import in a follow-up touch (it's a one-line change to use `claude.overnight.orchestrator`).

### R7: CLI invocation contract preserved
- **Expected**: `python3 -m cortex_command.overnight.batch_runner --help` exits 0; `from cortex_command.overnight import BatchConfig, run_batch` works; `just test` passes.
- **Actual**: `--help` prints usage correctly. `from cortex_command.overnight import BatchConfig, run_batch` exits 0. `just test` reports `Test suite: 3/3 passed`.
- **Verdict**: PASS

### R8: Add `test_orchestrator.py` with ≥5 IsolatedAsyncioTestCase integration tests
- **Expected**: ≥5 `def test_`, ≥1 IsolatedAsyncioTestCase, required scenarios covered, autospec on execute_feature + apply_feature_result.
- **Actual**: File exists with `TestOrchestratorRunBatch(unittest.IsolatedAsyncioTestCase)` and 5 test methods: multi-feature dispatch, concurrency semaphore, circuit breaker short-circuit, budget exhaustion, heartbeat task lifecycle. `autospec=True` used on `execute_feature` (line 144, 152) and `apply_feature_result` (line 161). All 5 pass.
- **Verdict**: PASS
- **Notes**: Circuit-breaker test (Scenario 3) correctly observes that pre-seeding `CircuitBreakerState` is not itself what short-circuits `_run_one` — the gate is `batch_result.circuit_breaker_fired`. Test engineers the outcome through an apply callback plus semaphore serialization; still meets the spec intent (assert breaker fires, no further features dispatched).

### R9: Migrate `TestAccumulateResultViaBatch` patch targets
- **Expected**: `grep "claude.overnight.batch_runner" test_lead_unit.py` = 0.
- **Actual**: Grep returns 0 matches. All patch targets migrated to `claude.overnight.orchestrator.*` (including `transition` — see spec-vs-plan note below). 48 tests in test_lead_unit pass.
- **Verdict**: PASS
- **Notes**: Per the review brief, the plan's correction to patch `transition` at `claude.overnight.orchestrator.transition` (not `claude.overnight.state.transition`) is the correct Python semantics — the symbol is bound in orchestrator's module dict by `from … import transition`. Implementation follows the plan.

### R10: Update `requirements/pipeline.md` to reference `orchestrator.py`
- **Expected**: `orchestrator.py` appears in Session Orchestration description; `batch_runner.py` does not in session-management descriptions.
- **Actual**: `requirements/pipeline.md:15` now reads `The overnight runner (orchestrator.py) manages session-level state…`. Line 62 still mentions `batch_runner owns all events.log writes` in a feature-execution bullet; this is an architectural claim (not pure CLI-invocation context) but the spec acceptance allows CLI-context references and this one is borderline. The Session Orchestration section itself is correctly updated.
- **Verdict**: PASS
- **Notes**: Consider updating line 62 to `orchestrator owns all events.log writes` in a follow-up for full consistency.

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: Consistent. `CircuitBreakerState` follows the `FeatureResult` dataclass pattern in `types.py`. `cb_state` parameter name is used uniformly across orchestrator, feature_executor, and outcome_router. Module docstrings follow existing conventions.
- **Error handling**: Matches the project pattern of `try/except Exception: pass` guards around state I/O inside `run_batch` (lines 150, 240, 371, 391) — consistent with pre-refactor behavior. The `# Don't let state-write failure abort the batch` comments document intent. Preserves graceful-partial-failure from project.md. The late-exception `gather` handler (lines 317–357) correctly re-invokes outcome_router for failures raised out of `_run_one`, including a guarded budget-exhaustion check.
- **Test coverage**: All 5 R8 scenarios exercised; `autospec=True` used on both mandated mocks. Heartbeat test captures the task object via a spy on `create_task` and asserts `done()` and `cancelled()` post-return. Full test suite green (`just test` = 3/3 passed; `test_orchestrator` = 5/5; `test_lead_unit` = 48/48).
- **Pattern consistency**: Uses `asyncio.Lock` + `asyncio.gather(return_exceptions=True)` + `create_task` for heartbeat — mirrors the pre-refactor control flow in batch_runner. TYPE_CHECKING import migration in `state.py`, `feature_executor.py`, `outcome_router.py`, and `conflict.py` uses the PEP 563 `from __future__ import annotations` pattern per spec Edge Cases. No circular imports introduced (verified by successful `from cortex_command.overnight import BatchConfig, run_batch`).

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": ["daytime_pipeline.py:25 still imports BatchConfig from batch_runner — cross-lifecycle (#078) cleanup, non-blocking", "Two docstring-only references to consecutive_pauses_ref remain in test_lead_unit.py:945 and test_brain.py:277"], "requirements_drift": "none"}
```
