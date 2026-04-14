# Specification: add-characterization-tests-for-batch-runner-pre-extraction

## Problem Statement

`batch_runner.py` (2198 LOC) has no dedicated unit tests. The #075 → #076 → #077 extraction chain will refactor ~1500 LOC of this file — moving `execute_feature` to `feature_executor.py`, `_apply_feature_result` to `outcome_router.py`, and the session orchestration layer to `orchestrator.py`. Without characterization tests, the only regression oracle for each extraction PR is a multi-hour overnight run — not a reviewable gate. This ticket pins the current behavior of the five highest-risk behavioral surfaces before any extraction begins, so each PR in the chain can demonstrate "before == after" programmatically.

## Requirements

1. **execute_feature happy-path characterization (Must-have)** — Add tests to `test_lead_unit.py` exercising `execute_feature` on the success path (all tasks complete). Assert: returned `FeatureResult.status == "completed"`, `overnight_log_event` called with `FEATURE_COMPLETE` event (or equivalent), task-completion markers written.
   - Acceptance criteria: `just test` exits 0; `grep -c "class TestExecuteFeature" claude/overnight/tests/test_lead_unit.py` ≥ 1

2. **execute_feature failed-task paths (Must-have)** — Add tests for each brain-triage outcome produced by `execute_feature` when a task fails: SKIP (returns None — task marked done, next task continues), DEFER (returns `FeatureResult(status="deferred")`), PAUSE (returns `FeatureResult(status="paused")`). All agent dispatch calls mocked with `AsyncMock`.
   - Acceptance criteria: `just test` exits 0; `grep -c "def test_.*execute_feature" claude/overnight/tests/test_lead_unit.py` ≥ 3

3. **_handle_failed_task brain-decision characterization (Must-have)** — Add tests to `test_brain.py` for the three BrainAction outcomes not currently covered (only the circuit-breaker check exists today): SKIP → returns `None`, calls `mark_task_done_in_plan`; DEFER → returns `FeatureResult(status="deferred")`, calls `write_deferral`; PAUSE → returns `FeatureResult(status="paused")`, increments `consecutive_pauses_ref[0]`. Each test mocks `request_brain_decision` to return the target `BrainAction`.
   - Acceptance criteria: `just test` exits 0; `grep -cE "def test_.*skip|def test_.*defer|def test_.*pause" claude/overnight/tests/test_brain.py` ≥ 3

4. **_apply_feature_result — all status variants (Must-have)** — Add tests to `test_lead_unit.py` for each of the five `FeatureResult.status` values as consumed by `_apply_feature_result`: `completed`, `failed`, `paused`, `deferred`, `repair_completed`. Each test asserts at least one `BatchResult` field mutation (e.g., `batch_result.features_merged`, `batch_result.features_paused`, etc.) and at least one `overnight_log_event` call with the correct event constant. `review_result` must be `None` in all test invocations — the non-None branch is unreachable in production.
   - Acceptance criteria: `just test` exits 0; `grep -cE "status.*=.*['\"]completed['\"]|status.*=.*['\"]failed['\"]|status.*=.*['\"]paused['\"]|status.*=.*['\"]deferred['\"]|status.*=.*['\"]repair_completed['\"]" claude/overnight/tests/test_lead_unit.py` ≥ 5

5. **consecutive_pauses_ref circuit-breaker mutation sequence (Must-have)** — Add at least one test driving `_apply_feature_result` through a sequence of pause/merge/pause calls and asserting `consecutive_pauses_ref` mutation: each `paused` result increments `consecutive_pauses_ref[0]`; each non-paused result resets it to 0. At `CIRCUIT_BREAKER_THRESHOLD` (3) consecutive pauses, a circuit-breaker event is logged and remaining features are listed.
   - Acceptance criteria: `just test` exits 0; `grep -c "consecutive_pauses" claude/overnight/tests/test_lead_unit.py` ≥ 3

6. **Conflict-recovery branching characterization (Must-have)** — Add tests for the three conflict-recovery paths inside `execute_feature` (lines 679–825):
   - Trivial-eligible conflict (≤3 files, no hot files): `resolve_trivial_conflict` called; returns `FeatureResult(status="repair_completed", trivial_resolved=True)`.
   - Non-trivial conflict, repair succeeds: `dispatch_repair_agent` called; returns `FeatureResult(status="repair_completed", repair_agent_used=True)`.
   - Recovery budget exhausted: returns `FeatureResult(status="deferred")` without calling repair functions.
   - Acceptance criteria: `just test` exits 0; `grep -cE "resolve_trivial_conflict|dispatch_repair_agent|recovery_attempts.*exhaust" claude/overnight/tests/test_lead_unit.py` ≥ 3

7. **_accumulate_result — CI deferral paths via run_batch (Must-have)** — Add tests driving `run_batch` with a single feature and mocked `execute_feature`, `merge_feature` returning `ci_pending` or `ci_failing` error strings. Assert that `batch_result.features_deferred` contains the feature name for both CI error cases. `BatchConfig` must use `result_dir=tmp_path` in all `run_batch` tests (default `result_dir = _LIFECYCLE_ROOT` writes `lifecycle/batch-1-results.json` to the live repo).
   - Acceptance criteria: `just test` exits 0; `grep -cE "ci_pending|ci_failing" claude/overnight/tests/test_lead_unit.py` ≥ 2

8. **_accumulate_result — review gating via run_batch (Must-have)** — Add tests driving `run_batch` with a single feature and mocked `execute_feature` returning `FeatureResult(status="completed")`, `merge_feature` returning `MergeResult(success=True)`, for four review-gating scenarios:
   - (a) Review not required (`requires_review` patched to return `False`): `dispatch_review` never called; `batch_result.features_merged` contains feature.
   - (b) Review approved (`dispatch_review` returns `ReviewResult(deferred=False, verdict="APPROVED")`): `batch_result.features_merged` contains feature.
   - (c) Review deferred (`dispatch_review` returns `ReviewResult(deferred=True)`): `batch_result.features_deferred` contains feature.
   - (d) Review raises exception: `batch_result.features_paused` contains feature.
   - `dispatch_review` must be patched at `claude.pipeline.review_dispatch.dispatch_review` (lazy import at line 1691 — not a `batch_runner` module-level attribute).
   - Acceptance criteria: `just test` exits 0; `grep -c "review_gating\|review_not_required\|review_approved\|review_deferred\|review_raises" claude/overnight/tests/test_lead_unit.py` ≥ 4

9. **_accumulate_result — budget_exhausted global_abort_signal via run_batch (Must-have)** — Add a test driving `run_batch` with a single feature and mocked `merge_feature` returning `error="budget_exhausted"`. Assert `batch_result.global_abort_signal == True` and that `run_batch` returns without processing additional features.
   - Acceptance criteria: `just test` exits 0; `grep -c "global_abort_signal\|budget_exhausted" claude/overnight/tests/test_lead_unit.py` ≥ 1

10. **multi-feature recovery_attempts_map behavior via run_batch (Must-have)** — Add at least one test driving `run_batch` with 2 features in a single call. Feature A has a test-failure that triggers recovery (assert `recover_test_failure` AsyncMock was called for Feature A; assert `merge_feature` was subsequently called for Feature A). Feature B does not have a test-failure (assert `recover_test_failure` was NOT called for Feature B). Because `recovery_attempts_map` is a local variable inside `run_batch`, the test cannot assert on it directly — assert instead on the observable call sequence: `recover_test_failure` called exactly once (for Feature A), and `merge_feature` called for Feature A after the recovery call.
    - Acceptance criteria: `just test` exits 0; `grep -c "recover_test_failure" claude/overnight/tests/test_lead_unit.py` ≥ 1

11. **Fixture files (Should-have)** — Create representative fixture files at `claude/overnight/tests/fixtures/batch_runner/`:
    - `plan_simple.md` — minimal one-task plan.md (for `execute_feature` tests)
    - `spec_simple.md` — minimal spec.md (for `execute_feature` tests)
    - `feature_result_variants.py` — one `FeatureResult` instance per status variant, importable by tests
    - At least one JSONL fixture file (`events_completed.jsonl`) containing the expected event sequence for the happy-path execute_feature run
    - Acceptance criteria: `ls claude/overnight/tests/fixtures/batch_runner/ | wc -l` ≥ 4

12. **Test performance (Must-have)** — All new characterization tests complete in under 60 seconds total when run with `just test`. All agent dispatch calls, subprocess operations, and file I/O are mocked.
    - Acceptance criteria: `time just test` total wall-clock time < 60 seconds

## Non-Requirements

- No extraction or renaming of any functions (that is #075/#076/#077 scope)
- No full end-to-end overnight-session tests; fixtures mock at the agent-dispatch boundary, not the CLI boundary
- No characterization of session-layer concerns: `ConcurrencyManager`, `run_batch` round-scheduling, heartbeat, budget allocation — those are #077's integration tests. This means no assertions on those behaviors; mocking them as scaffolding to isolate the surfaces under test is required and permitted.
- No modification of `batch_runner.py`, `brain.py`, or any pipeline module production code
- No snapshot libraries (syrupy, inline-snapshot, ApprovalTests) — use direct assertions on `BatchResult` fields and `mock.call_args_list`

## Edge Cases

- **`review_result=None` dead code**: `_apply_feature_result`'s `review_result` parameter is always `None` at all four call sites in `_accumulate_result` (lines 1622, 1670, 1838, 1854). Do not write tests asserting behavior of the `review_result is not None` branch — it is unreachable in production and testing it would misrepresent the regression gate.

- **`result_dir` default writes to live repo**: `BatchConfig.result_dir` defaults to `_LIFECYCLE_ROOT` (the actual `lifecycle/` directory). Every `run_batch` test must pass `result_dir=tmp_path` explicitly; failure to do so silently writes `lifecycle/batch-N-results.json` to the working tree.

- **`dispatch_review` lazy import trap**: `dispatch_review` is imported at line 1691 inside the `_accumulate_result` closure — `batch_runner` never holds it as a module-level attribute. `patch("claude.overnight.batch_runner.dispatch_review")` will fail. Correct patch target: `patch("claude.pipeline.review_dispatch.dispatch_review")`. The patch context manager must wrap the entire `await run_batch(...)` call — not just the post-call assertion; `self.addCleanup(p.stop)` in `setUp` is the safest pattern, as it guarantees the patch is active throughout the test body. `requires_review`, `read_tier`, and `read_criticality` ARE module-level imports in `batch_runner` and can be patched at `claude.overnight.batch_runner.{name}`.

- **`test_brain.py` duplication guard**: `test_brain.py` already has one `_handle_failed_task` test (circuit-breaker fires when `consecutive_pauses_ref=[2]`). New tests add SKIP, DEFER, and PAUSE variants — do not re-add the circuit-breaker test.

- **AsyncMock required**: All coroutine functions (`execute_feature`, `merge_feature`, `retry_task`, `recover_test_failure`, `dispatch_review`, `request_brain_decision`) must use `AsyncMock`. Using `MagicMock` for a coroutine returns a non-awaitable and causes the test to silently pass incorrect state.

- **Mutable `call_args_list` references**: When asserting on event payload content from `overnight_log_event` call args, use `deepcopy` in `side_effect` if the payload dict is mutated after the mock call. Otherwise `call_args_list` stores the post-mutation value.

- **Concurrent call ordering**: For `run_batch` tests that dispatch multiple features, `asyncio.gather` ordering is non-deterministic. Assert on set membership (`set(batch_result.features_merged)`) rather than list order.

## Changes to Existing Behavior

- ADDED: `TestExecuteFeature` class in `claude/overnight/tests/test_lead_unit.py` (new test class)
- ADDED: `TestHandleFailedTaskBrainActions` class or equivalent in `claude/overnight/tests/test_brain.py` (SKIP, DEFER, PAUSE variants)
- ADDED: `TestApplyFeatureResultVariants` class or equivalent in `claude/overnight/tests/test_lead_unit.py` (all FeatureResult.status variants)
- ADDED: `TestAccumulateResultViaBatch` class or equivalent in `claude/overnight/tests/test_lead_unit.py` (CI deferral, review gating, abort signal, recovery_attempts_map)
- ADDED: `TestConflictRecoveryBranching` class or equivalent in `claude/overnight/tests/test_lead_unit.py`
- ADDED: `claude/overnight/tests/fixtures/batch_runner/` directory with fixture files

## Technical Constraints

- **Test placement**: `test_lead_unit.py` (for batch_runner surfaces) and `test_brain.py` (for `_handle_failed_task` extension). Do NOT create `test_batch_runner.py` — functions move to `feature_executor.py` (#075) and `outcome_router.py` (#076); a new file would need import-path migration twice.
- **conftest.py inheritance**: All tests in `claude/overnight/tests/` automatically receive SDK stubs and `backlog.update_item` stubs from `conftest.py`. No per-test setup needed for these imports.
- **`_FakeBatchConfig` pattern**: An existing minimal-config stub is used in `test_lead_unit.py`. New tests extend this pattern; do not construct a full `BatchConfig` with real filesystem paths for anything except `result_dir` (which must be `tmp_path`).
- **`overnight_state_path` must be a temp path**: For `run_batch`-level tests, `BatchConfig.overnight_state_path` must be set to a temp path (same class of hazard as `result_dir` — defaults to a live repo path that will be written during test execution).
- **Required mock targets for run_batch-level tests**: R7–R10 call `run_batch`, which unconditionally invokes the following infrastructure on every call. These must be mocked to isolate the surfaces under test and prevent subprocess/filesystem side-effects:
  - `parse_master_plan` — reads plan.md from disk
  - `create_worktree` — runs real git subprocess
  - `load_state` — reads overnight state file
  - `load_throttle_config` — reads config file
  - `ConcurrencyManager` — manages concurrency slots
  - `asyncio.create_task` (or the `_heartbeat_loop` coroutine directly) — spawns background heartbeat
- **Patching style**: `patch(...)` as context manager or `self.addCleanup(p.stop)` in `setUp`. Consistent with `test_brain.py` lines 157–162.
- **`unittest.IsolatedAsyncioTestCase`**: Required for async test methods. Do not use bare `pytest.mark.asyncio` for `run_batch`-level tests — the existing test classes use `IsolatedAsyncioTestCase`.
- **`CIRCUIT_BREAKER_THRESHOLD`**: Imported from `claude.overnight.batch_runner` as the authoritative threshold value (currently 3). Do not hardcode 3 in test assertions.
- **Recovery attempts cap**: Max 2 attempts for test failures; single Sonnet→Opus escalation for merge conflicts. Test fixtures must not encode more attempts than the cap.

## Open Decisions

None.
