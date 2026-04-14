# Review: add-characterization-tests-for-batch-runner-pre-extraction

## Stage 1: Spec Compliance

### R1 — execute_feature happy-path characterization — PASS
- `TestExecuteFeature.test_happy_path_single_task_completes` at test_lead_unit.py:1073.
- Asserts `result.status == "completed"` and `result.name == "test-feat"`.
- Acceptance grep `class TestExecuteFeature` → 1 (≥1).

### R2 — execute_feature failed-task paths — PASS
- Three tests: `test_execute_feature_brain_triage_skip_returns_paused`, `..._defer_returns_deferred`, `..._pause_returns_paused` (test_lead_unit.py:1095, 1122, 1154).
- SKIP and PAUSE both return `status="paused"` because `_handle_failed_task` returning `None` causes execute_feature to fall through — this matches production semantics.
- DEFER propagates `FeatureResult(status="deferred")` unchanged.
- AsyncMock used on `_handle_failed_task` and `retry_task`.
- Acceptance grep `def test_.*execute_feature` → 3 (≥3).

### R3 — _handle_failed_task brain-decision characterization — PASS
- `TestHandleFailedTaskBrainActions` at test_brain.py:308 — three methods.
- SKIP → `assertIsNone(result)`, `mark_task_done.assert_called_once()`, `mock_write_deferral.assert_not_called()`.
- DEFER → `status="deferred"`, `deferred_question_count == 1`, `write_deferral.assert_called_once()`, `mark_task_done.assert_not_called()`. Matches spec verbatim.
- PAUSE → `assertIsNone(result)`, neither `mark_task_done_in_plan` nor `write_deferral` called — exactly as spec instructs. Production confirms PAUSE returns None with no side effects (batch_runner.py:576).
- Existing circuit-breaker test preserved; not duplicated.
- Acceptance grep for skip/defer/pause → 5 (≥3).

### R4 — _apply_feature_result all status variants — PASS
- `TestApplyFeatureResultVariants` at test_lead_unit.py:774 — five methods covering completed/failed/paused/deferred/repair_completed.
- Each asserts a BatchResult field mutation and the matching event constant (FEATURE_COMPLETE / FEATURE_FAILED / FEATURE_PAUSED / FEATURE_DEFERRED / REPAIR_AGENT_RESOLVED).
- `review_result=None` used consistently per the edge-case note.
- Acceptance grep status variants → 28 (≥5).

### R5 — consecutive_pauses_ref circuit-breaker mutation — PASS
- `TestConsecutivePausesSequence` at test_lead_unit.py:906: three methods.
- `test_pause_then_merge_resets_counter` verifies pause → 1, merge → 0.
- `test_pause_merge_pause_sequence` verifies 1 → 0 → 1 with no circuit-breaker.
- `test_threshold_consecutive_pauses_fires_circuit_breaker` uses `CIRCUIT_BREAKER_THRESHOLD` constant (not hardcoded 3) and asserts `batch.circuit_breaker_fired`.
- Acceptance grep `consecutive_pauses` → 5 (≥3).

### R6 — Conflict-recovery branching — PASS
- `TestConflictRecoveryBranching` at test_lead_unit.py:1191: three async tests.
- Trivial: `resolve_trivial_conflict` awaited once; repair NOT awaited; `status="repair_completed"`, `trivial_resolved=True`.
- Non-trivial: `dispatch_repair_agent` awaited once; trivial NOT awaited; `repair_agent_used=True`.
- Budget exhausted: neither awaited; `write_deferral` called; `status="deferred"`.
- Acceptance grep for recovery keywords → 11 (≥3).

### R7 — _accumulate_result CI deferral via run_batch — PASS
- `test_ci_pending_defers_feature` and `test_ci_failing_defers_feature` drive `run_batch` with mocked `merge_feature` returning `error="ci_pending"`/`"ci_failing"`.
- Both assert `features_deferred` contains the feature.
- `BatchConfig(result_dir=tmp_path, overnight_state_path=tmp_path/...)` used — no live repo writes.
- Acceptance grep `ci_pending|ci_failing` → 8 (≥2).

### R8 — _accumulate_result review gating via run_batch — PASS
- Four async tests at test_lead_unit.py:1650, 1684, 1719, 1758 covering all scenarios.
- `dispatch_review` patched at `claude.pipeline.review_dispatch.dispatch_review` (correct — avoids the lazy-import trap per the spec edge-case note).
- `requires_review`, `read_tier`, `read_criticality` patched at `batch_runner` namespace.
- Scenario (d) review-raises: test asserts `features_deferred` contains the feature. Note: spec R8(d) text says "features_paused", but (i) the spec's accompanying plan says features_deferred, (ii) the production code at batch_runner.py:1747–1751 explicitly appends to `features_deferred` on dispatch_review exception, (iii) characterization tests must mirror current behavior. Test is correct; spec bullet is a text typo.
- Acceptance grep for review scenario tokens → 4 (≥4).

### R9 — budget_exhausted global_abort_signal via run_batch — PASS
- `test_budget_exhausted_sets_global_abort_signal` at test_lead_unit.py:1574.
- Asserts both `batch_result.global_abort_signal == True` and `abort_reason == "budget_exhausted"`.
- Acceptance grep → 31 (≥1).

### R10 — multi-feature recovery_attempts_map via run_batch — PASS
- `test_multi_feature_only_failing_feature_triggers_recovery` at test_lead_unit.py:1597.
- Two features: feat-a fails tests (TestResult passed=False), feat-b merges cleanly.
- Asserts `recover_test_failure.await_count == 1` and `"feat-b" in set(batch_result.features_merged)`.
- Uses `set(...)` for non-deterministic gather ordering per edge-case note.
- Acceptance grep `recover_test_failure` → 12 (≥1).

### R11 — Fixture files — PASS
- `claude/overnight/tests/fixtures/batch_runner/` contains: `__init__.py`, `plan_simple.md`, `spec_simple.md`, `feature_result_variants.py`, `events_completed.jsonl` (6 entries counting __pycache__, 5 files intended, ≥4).
- `feature_result_variants.py` provides one FeatureResult per status variant (completed/failed/paused/deferred/repair_completed).

### R12 — Test performance — PASS
- Full `just test` suite (pipeline + overnight + tests) completes in ~5.7s wall-clock.
- `just test-overnight` alone: 250 tests, 1 xpassed, 0.64s.
- `test_lead_unit.py + test_brain.py`: 70 tests in 0.21s.
- Well under the 60-second budget.

## Stage 2: Code Quality

- **Naming**: Test classes and methods follow the existing pattern (`TestXyz`, `test_<scenario>`) consistent with neighboring code. `_install_common_patches`, `_make_plan`, `_make_state` helpers cleanly factor the repeated run_batch scaffolding.
- **AsyncMock discipline**: All coroutine functions (`execute_feature`, `merge_feature`, `dispatch_review`, `recover_test_failure`, `retry_task`, `request_brain_decision`, `_handle_failed_task`) use `AsyncMock`. `MagicMock` is correctly reserved for non-async callables (e.g., `mark_task_done_in_plan`, `write_deferral`, manager stats).
- **Patch discipline**: `self.addCleanup(p.stop)` via `_start_patch` helper ensures patches survive the entire test body — matches the pattern from test_brain.py:157–162 required by the spec.
- **`result_dir` safety**: Every `run_batch` test constructs `BatchConfig(result_dir=self._tmp, overnight_state_path=self._tmp/"state.json")`, preventing writes to the live `lifecycle/` directory (spec edge-case hazard).
- **Constants**: `CIRCUIT_BREAKER_THRESHOLD` imported from production code, not hardcoded — future-proof against the threshold changing.
- **Minor polish**: R12 `patches[0], patches[1], ...` context-manager expansion in `TestExecuteFeature` is verbose. `contextlib.ExitStack` or composing with `contextlib.contextmanager` would be cleaner. Non-blocking.

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Verdict

```json
{
  "verdict": "APPROVED",
  "cycle": 1,
  "issues": [],
  "requirements_drift": "none"
}
```
