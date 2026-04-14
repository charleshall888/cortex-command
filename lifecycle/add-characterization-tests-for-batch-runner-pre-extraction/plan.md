# Plan: add-characterization-tests-for-batch-runner-pre-extraction

## Overview

Append new test classes to `test_lead_unit.py` (for `batch_runner` surfaces) and `test_brain.py` (for `_handle_failed_task` extension), plus a fixture directory. Tasks 1, 2, and 3 are independent and map to distinct files; tasks 4–6 chain sequentially on `test_lead_unit.py` because each appends a new class. Task 7 extends the class created by Task 6 by inserting new test methods into the existing class — it must NOT create a new class with the same name.

## Tasks

### Task 1: Create fixture directory and fixture files
- **Files**:
  - `claude/overnight/tests/fixtures/__init__.py`
  - `claude/overnight/tests/fixtures/batch_runner/__init__.py`
  - `claude/overnight/tests/fixtures/batch_runner/plan_simple.md`
  - `claude/overnight/tests/fixtures/batch_runner/spec_simple.md`
  - `claude/overnight/tests/fixtures/batch_runner/feature_result_variants.py`
  - `claude/overnight/tests/fixtures/batch_runner/events_completed.jsonl`
- **What**: Create the fixture directory hierarchy (with `__init__.py` files to make subdirectories Python packages) and four content files: a one-task plan in plan.md format, a minimal spec, a Python reference module with one `FeatureResult` per status variant, and a JSONL event log listing the expected event sequence (event type + feature only — no `ts` field) for a happy-path `execute_feature` run.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - `FeatureResult` dataclass at `claude/overnight/batch_runner.py:125` — status variants are `"completed"`, `"failed"`, `"paused"`, `"deferred"`, `"repair_completed"`; constructor: `FeatureResult(name=..., status=..., error=None, ...)`
  - `__init__.py` files: both empty. Required so that `claude.overnight.tests.fixtures.batch_runner.feature_result_variants` is importable as a package path.
  - `plan_simple.md` must be in the format `parse_feature_plan` expects: markdown with `### Task 1: description`, followed by `- **Files**: ...`, `- **Depends on**: none`, `- **Complexity**: simple`, `- **Verification**: ...`, `- **Status**: [ ] pending`. One task only.
  - `spec_simple.md`: two-line file — `# Spec` header + one requirement line. Used only as a readable path reference; content not parsed by tests.
  - `feature_result_variants.py`: a plain Python module defining module-level `FeatureResult` instances, one per status. Import: `from claude.overnight.batch_runner import FeatureResult`. Name them `COMPLETED`, `FAILED`, `PAUSED`, `DEFERRED`, `REPAIR_COMPLETED`. Tests in Tasks 3–7 construct `FeatureResult` instances inline; this module serves as a reference and can be imported in future tests that prefer fixture reuse.
  - `events_completed.jsonl`: each line is a JSON dict with `"event"` and `"feature"` keys, NO `"ts"` field. Typical happy-path sequence: `task_output`, `task_git_state` (one per task), then the `FEATURE_COMPLETE` event constant string (see `claude/overnight/events.py`).
- **Verification**: `ls claude/overnight/tests/fixtures/batch_runner/ | wc -l` → pass if count ≥ 4 (the two `__init__.py` files count toward the total)
- **Status**: [x] complete

---

### Task 2: Add TestHandleFailedTaskBrainActions to test_brain.py (R3)
- **Files**:
  - `claude/overnight/tests/test_brain.py`
- **What**: Append class `TestHandleFailedTaskBrainActions(unittest.IsolatedAsyncioTestCase)` with three async tests: SKIP action → `_handle_failed_task` returns `None` and `mark_task_done_in_plan` was called; DEFER action → returns `FeatureResult(status="deferred")` and `write_deferral` was called; PAUSE action → returns `None` and neither `mark_task_done_in_plan` nor `write_deferral` was called.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - `_handle_failed_task` signature at `claude/overnight/batch_runner.py:497`: `async def _handle_failed_task(feature, task, all_tasks, spec_excerpt, retry_result, consecutive_pauses_ref, manager=None, round=0, log_path=Path(...))`
  - Circuit-breaker pre-check at line 517 fires when `consecutive_pauses_ref[0] >= CIRCUIT_BREAKER_THRESHOLD - 1` (i.e., `>= 2`). Set `consecutive_pauses_ref=[0]` so it never fires.
  - Required mocks (use `_start_patch` helper from `TestRequestBrainDecision` at lines 157–161):
    - `patch("claude.overnight.batch_runner.request_brain_decision", new_callable=AsyncMock)` → return `BrainDecision(action=BrainAction.SKIP/DEFER/PAUSE, reasoning="r", confidence=0.9)`
    - `patch("claude.overnight.batch_runner.overnight_log_event")`
    - `patch("claude.overnight.batch_runner.mark_task_done_in_plan")`
    - `patch("claude.overnight.batch_runner.write_deferral")`
    - `patch("claude.overnight.batch_runner._read_learnings", return_value="(No prior learnings.)")` — called to build BrainContext
  - Imports already in test_brain.py: `BrainAction`, `BrainDecision` from `claude.overnight.brain`; `_handle_failed_task` from `claude.overnight.batch_runner`; `FeatureTask` from `claude.pipeline.parser`
  - Construct `task = FeatureTask(number=1, description="desc", depends_on=[], files=[], complexity="simple")`. Construct `retry_result = MagicMock(attempts=1, final_output="err")`.
  - Existing class `TestHandleFailedTask` at line 272 has the circuit-breaker test — do NOT add a duplicate of it. New class name must be `TestHandleFailedTaskBrainActions`.
  - For DEFER test: also assert `batch_runner_module._handle_failed_task` result `.status == "deferred"` and `result.deferred_question_count == 1`.
- **Verification**: `grep -cE "def test_.*skip|def test_.*defer|def test_.*pause" claude/overnight/tests/test_brain.py` → pass if count ≥ 3; `just test` → pass if exit 0
- **Status**: [x] complete

---

### Task 3: Add TestApplyFeatureResultVariants and TestConsecutivePausesSequence to test_lead_unit.py (R4, R5)
- **Files**:
  - `claude/overnight/tests/test_lead_unit.py`
- **What**: Append two new test classes to `test_lead_unit.py`. `TestApplyFeatureResultVariants(unittest.TestCase)`: one test per status variant (completed-with-files, failed, paused, deferred, repair_completed), each asserting the correct `BatchResult` field is populated and `overnight_log_event` is called with the matching event constant. `TestConsecutivePausesSequence(unittest.TestCase)`: tests that drive a pause/non-pause/pause sequence through `_apply_feature_result`, asserting `consecutive_pauses_ref` increments on pause and resets to 0 on a successful merge, and fires the circuit breaker at threshold.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - `_apply_feature_result` signature at `claude/overnight/batch_runner.py:1203` — positional: `name, result, batch_result, consecutive_pauses_ref, config, backlog_ids, feature_names`; keyword: `worktree_branches`, `repo_path`, `worktree_path`, `integration_branches`, `integration_worktrees`, `session_id`, `review_result`. Always pass `review_result=None`.
  - Event constants imported from `claude.overnight.events` (see `claude/overnight/batch_runner.py:61–85`): `FEATURE_COMPLETE`, `FEATURE_DEFERRED`, `FEATURE_FAILED`, `FEATURE_PAUSED`, `REPAIR_AGENT_RESOLVED`, `TRIVIAL_CONFLICT_RESOLVED`
  - `_apply_feature_result` is synchronous (not async); use `unittest.TestCase`, not `IsolatedAsyncioTestCase`.
  - Mocks required for each variant:
    - All variants: `patch.object(batch_runner_module, "overnight_log_event")`, `patch.object(batch_runner_module, "_write_back_to_backlog")`
    - `completed` (success path): additionally mock `_get_changed_files` → `["src/foo.py"]`, `merge_feature` → `MergeResult(success=True, feature=name, conflict=False)`, `cleanup_worktree`
    - `completed`: note that `merge_feature` is NOT a coroutine — use `MagicMock`, not `AsyncMock`
    - `failed`: mock `_write_back_to_backlog` only (no other I/O)
    - `paused`: mock `_write_back_to_backlog` only
    - `deferred`: mock `_write_back_to_backlog` only
    - `repair_completed` (ff-merge success path): additionally mock `patch.object(subprocess, "run")` to return `MagicMock(returncode=0, stdout="", stderr="")` for both git calls; mock `cleanup_worktree`; set `result.repair_branch = "repair/feat-a"` and `result.trivial_resolved = False`
  - `BatchConfig` construction: use temp dir, set `overnight_events_path`, `pipeline_events_path`. No need for `result_dir` since we're not calling `run_batch`.
  - Follow the `_call(self, name, status, batch_result, pauses_ref, **result_kwargs)` helper pattern from `TestApplyFeatureResult` at line 97.
  - `CIRCUIT_BREAKER_THRESHOLD` imported from `claude.overnight.batch_runner` — use it in assertions, do not hardcode 3.
  - For `TestConsecutivePausesSequence`: drive `_apply_feature_result` with alternating pause/complete sequences; verify `consecutive_pauses_ref[0]` resets to 0 after a successful merge (completed + merge success → no-pause increment). Three consecutive pauses → `batch_result.circuit_breaker_fired == True` and `consecutive_pauses_ref[0] == CIRCUIT_BREAKER_THRESHOLD`.
- **Verification**: `grep -cE "status.*=.*['\"]completed['\"]|status.*=.*['\"]failed['\"]|status.*=.*['\"]paused['\"]|status.*=.*['\"]deferred['\"]|status.*=.*['\"]repair_completed['\"]" claude/overnight/tests/test_lead_unit.py` → pass if count ≥ 5; `grep -c "consecutive_pauses" claude/overnight/tests/test_lead_unit.py` → pass if count ≥ 3; `just test` → pass if exit 0
- **Status**: [x] complete

---

### Task 4: Add TestExecuteFeature to test_lead_unit.py (R1, R2)
- **Files**:
  - `claude/overnight/tests/test_lead_unit.py`
- **What**: Append `TestExecuteFeature(unittest.IsolatedAsyncioTestCase)` with tests for: (a) the happy path (single task, all tasks succeed) — assert `FeatureResult.status == "completed"`; (b) the three brain-triage outcomes when `retry_task` returns failure: SKIP → `_handle_failed_task` returns `None` → `execute_feature` returns `FeatureResult(status="paused")`; DEFER → `_handle_failed_task` returns `FeatureResult(status="deferred")` → `execute_feature` returns that; PAUSE → `_handle_failed_task` returns `None` → `execute_feature` returns `FeatureResult(status="paused")`.
- **Depends on**: [3]
- **Complexity**: complex
- **Context**:
  - `execute_feature` signature at `claude/overnight/batch_runner.py:662`: `async def execute_feature(feature, worktree_path, config, spec_path=None, manager=None, consecutive_pauses_ref=None, repo_path=None, integration_branches=None) -> FeatureResult`
  - Conflict-recovery block at top of `execute_feature` (lines 683–825): triggered when `load_state` succeeds and `read_events` yields a `MERGE_CONFLICT_CLASSIFIED` event for the feature. **To skip it**: mock `patch.object(batch_runner_module, "load_state")` with `side_effect=Exception` — this sets `_skip_repair=True` at line 688.
  - Required mocks (all via `patch.object(batch_runner_module, ...)` except subprocess):
    - `load_state` → `side_effect=Exception`
    - `parse_feature_plan` → `return_value=FeaturePlan(feature="test-feat", overview="", tasks=[FeatureTask(number=1, description="do something", depends_on=[], files=["test.py"], complexity="simple")])`
    - `retry_task` (AsyncMock) → `return_value=RetryResult(success=True, attempts=1, final_output="done", paused=False, idempotency_skipped=False)` for happy path
    - `_read_exit_report` → `return_value=("complete", None, None)` for happy path
    - `mark_task_done_in_plan`
    - `pipeline_log_event`
    - `overnight_log_event`
    - `read_criticality` → `return_value="high"`
    - `_render_template` → `return_value="stub system prompt"`
    - `patch.object(subprocess, "run")` → `return_value=MagicMock(returncode=0, stdout="0\n", stderr="")`
  - For brain-triage tests (R2): mock `retry_task` to return `RetryResult(success=False, attempts=2, final_output="task failed", paused=False, idempotency_skipped=False)`. Then mock `_handle_failed_task` (AsyncMock) to return the target value — either `None` (SKIP or PAUSE) or `FeatureResult(name="test-feat", status="deferred", ...)` (DEFER).
  - Imports needed in test file header (already present): `RetryResult` from `claude.pipeline.retry`; `FeaturePlan` from `claude.pipeline.parser`; `compute_dependency_batches` from `claude.common` — not needed since `parse_feature_plan` is mocked and `compute_dependency_batches` handles a real `FeatureTask` list.
  - `BatchConfig` for these tests: `BatchConfig(batch_id=1, plan_path=Path(tmp)/"plan.md", overnight_events_path=Path(tmp)/"overnight.log", pipeline_events_path=Path(tmp)/"pipeline.log", overnight_state_path=Path(tmp)/"state.json")`
  - `worktree_path` arg: `Path(tmp)` — a real temp directory so path operations inside `_run_task` don't fail
  - **SKIP vs PAUSE are structurally identical at the execute_feature return boundary**: both `_handle_failed_task` SKIP and PAUSE return `None`, and `execute_feature` falls through to `return FeatureResult(status="paused")` in both cases (lines 984–991). When `_handle_failed_task` is mocked directly, the two tests are identical — both mock returning `None` and assert `status="paused"`. This is intentional: the mock boundary chosen (mocking `_handle_failed_task`) tests execute_feature's return-value handling, not _handle_failed_task's internals. The SKIP-specific side effect (`mark_task_done_in_plan`) is tested in Task 2 (test_brain.py) where `_handle_failed_task` runs for real with a mocked `request_brain_decision`. Write three tests to satisfy spec R2 — one for SKIP, one for DEFER, one for PAUSE — acknowledging that SKIP and PAUSE exercise the same `execute_feature` code path.
- **Verification**: `grep -c "class TestExecuteFeature" claude/overnight/tests/test_lead_unit.py` → pass if count ≥ 1; `grep -c "def test_.*execute_feature" claude/overnight/tests/test_lead_unit.py` → pass if count ≥ 3; `just test` → pass if exit 0
- **Status**: [x] complete

---

### Task 5: Add TestConflictRecoveryBranching to test_lead_unit.py (R6)
- **Files**:
  - `claude/overnight/tests/test_lead_unit.py`
- **What**: Append `TestConflictRecoveryBranching(unittest.IsolatedAsyncioTestCase)` with three tests for the conflict-recovery paths in `execute_feature` (lines 679–825): (a) trivial-eligible conflict (≤3 files, no hot files) → `resolve_trivial_conflict` called, returns `FeatureResult(status="repair_completed", trivial_resolved=True)`; (b) non-trivial / trivial-failed, recovery_depth=0 → `dispatch_repair_agent` called, returns `FeatureResult(status="repair_completed", repair_agent_used=True)`; (c) recovery budget exhausted (recovery_depth ≥ 1) → neither repair function called, returns `FeatureResult(status="deferred")`.
- **Depends on**: [4]
- **Complexity**: complex
- **Context**:
  - Conflict-recovery block entry condition: `load_state` succeeds AND `read_events` yields at least one event where `event == MERGE_CONFLICT_CLASSIFIED` and `feature == <name>`. The last matching event is used.
  - `MERGE_CONFLICT_CLASSIFIED` constant: `"merge_conflict_classified"` (string literal used at line 700 and 1436). Import from `claude.overnight.events` or patch `read_events` to yield a dict directly.
  - `OvernightState` / `OvernightFeatureStatus` from `claude.overnight.state`: `OvernightState(session_id="s1", plan_ref="plan.md", features={"feat-a": OvernightFeatureStatus(recovery_depth=0, recovery_attempts=0)})`.
  - Trivial path: conflict event `details.conflicted_files` ≤ 3 entries, no entries in hot-files list. `resolve_trivial_conflict` (AsyncMock) → `MagicMock(success=True, repair_branch="repair/feat-a", resolved_files=["f.py"])`.
  - Non-trivial / dispatch-repair path: either set `conflicted_files` to 4+ entries (non-trivial) OR mock `resolve_trivial_conflict` to return `MagicMock(success=False)` (trivial attempted but failed). Then `dispatch_repair_agent` (AsyncMock) → `MagicMock(success=True, repair_branch="repair/feat-a", error=None)`. Also mock `save_state` (asyncio.to_thread wraps it — mock `patch.object(batch_runner_module, "save_state")`). See note below on asyncio.to_thread.
  - Budget-exhausted path: `OvernightFeatureStatus(recovery_depth=0, recovery_attempts=1)` (recovery_attempts ≥ 1 at line 748). Neither repair function called. Mock `write_deferral`.
  - Required mocks for all three tests:
    - `load_state` → `return_value=<OvernightState with features[name]>`
    - `read_events` → iterable yielding `{"event": "merge_conflict_classified", "feature": "feat-a", "details": {"conflicted_files": [...], "conflict_summary": "conflict"}}` — patch as `MagicMock(return_value=iter([event_dict]))`
    - `resolve_trivial_conflict` (AsyncMock)
    - `dispatch_repair_agent` (AsyncMock)
    - `save_state`
    - `write_deferral`
    - `overnight_log_event`
    - `pipeline_log_event`
    - `_render_template` → `return_value="stub"`
    - `read_criticality` → `return_value="high"`
    - `parse_feature_plan` — still mocked to prevent plan-file reads after the recovery block. Set to return a FeaturePlan that triggers `return FeatureResult(status="deferred")` via the budget-exhausted path... Actually for (a) and (b), conflict recovery returns early BEFORE reaching `parse_feature_plan`. For (c), it also returns early. So `parse_feature_plan` is never called in these three tests — mock it defensively but don't assert on it.
  - `asyncio.to_thread` wraps `save_state` at line 770. Since `save_state` is mocked at the module level, `asyncio.to_thread(save_state, ...)` will call the mock. No special handling needed.
  - Hot-files guard at line 720: `_hot_files` is loaded from `overnight-strategy.json` via `Path(config.overnight_state_path).parent / "overnight-strategy.json"`. Since that file won't exist in the temp dir, `_hot_files = []` (OSError except at line 722). No mock needed for this.
- **Verification**: `grep -cE "resolve_trivial_conflict|dispatch_repair_agent|recovery_attempts.*exhaust" claude/overnight/tests/test_lead_unit.py` → pass if count ≥ 3; `just test` → pass if exit 0
- **Status**: [x] complete

---

### Task 6: Add TestAccumulateResultViaBatch — CI deferral, budget abort, multi-feature recovery (R7, R9, R10)
- **Files**:
  - `claude/overnight/tests/test_lead_unit.py`
- **What**: Append `TestAccumulateResultViaBatch(unittest.IsolatedAsyncioTestCase)` with tests that drive `run_batch` end-to-end: (R7) CI deferral for `ci_pending` and `ci_failing` error strings → `batch_result.features_deferred` contains the feature; (R9) `budget_exhausted` global abort signal → `batch_result.global_abort_signal == True`; (R10) two-feature batch with Feature A triggering test-failure recovery and Feature B not — assert `recover_test_failure` called exactly once.
- **Depends on**: [5]
- **Complexity**: complex
- **Context**:
  - `run_batch` signature at `claude/overnight/batch_runner.py:1535`: `async def run_batch(config: BatchConfig) -> BatchResult`
  - Required mocks for all `run_batch`-level tests — use a `_start_patch` helper following the `addCleanup(p.stop)` pattern in `test_brain.py:157–161`:
    - `batch_runner_module.parse_master_plan` → `return_value=<MasterPlan mock with .features=[mock_feature]>`; `mock_feature.name = "feat-a"`
    - `batch_runner_module.create_worktree` → `return_value=<WorktreeInfo mock with .path=Path(tmp)/"wt", .branch="pipeline/feat-a">`
    - `batch_runner_module.load_state` → `return_value=OvernightState(session_id="s1", plan_ref="plan.md", features={"feat-a": OvernightFeatureStatus(recovery_attempts=0)})`
    - `batch_runner_module.save_state`
    - `batch_runner_module.load_throttle_config` → `return_value=MagicMock()`
    - `batch_runner_module.ConcurrencyManager` → `return_value=<mock_manager>` where `mock_manager.acquire = AsyncMock()`, `mock_manager.release = MagicMock()`, `mock_manager.stats = {}`
    - `batch_runner_module.execute_feature` (AsyncMock) → inject `FeatureResult(name=..., status="completed")`
    - `batch_runner_module._get_changed_files` → `return_value=["src/foo.py"]`
    - `batch_runner_module.merge_feature` → inject target `MergeResult`
    - `batch_runner_module.overnight_log_event`
    - `batch_runner_module._write_back_to_backlog`
    - `batch_runner_module.cleanup_worktree`
    - `batch_runner_module.recover_test_failure` (AsyncMock)
    - `batch_runner_module.save_batch_result`
  - `BatchConfig` for all run_batch-level tests: **must set** `result_dir=Path(tmp)` (default `_LIFECYCLE_ROOT` writes `lifecycle/batch-N-results.json` to live repo) AND `overnight_state_path=Path(tmp)/"state.json"`. Also set `overnight_events_path=Path(tmp)/"overnight.log"`, `pipeline_events_path=Path(tmp)/"pipeline.log"`.
  - **R7 (CI deferral)**: mock `merge_feature` to return `MergeResult(success=False, feature="feat-a", conflict=False, error="ci_pending")` for one test and `"ci_failing"` for another. Assert `len(batch_result.features_deferred) == 1` and `batch_result.features_deferred[0]["name"] == "feat-a"`.
  - **R9 (budget abort)**: mock `execute_feature` to return `FeatureResult(name="feat-a", status="paused", error="budget_exhausted")`. Non-completed features do not reach `merge_feature`; omit that mock. Assert `batch_result.global_abort_signal == True`.
  - **R10 (multi-feature)**: `parse_master_plan` returns plan with 2 features `[feat-a, feat-b]`. `execute_feature` returns `FeatureResult(status="completed")` for both. Mock `merge_feature` via a **feature-name-keyed callable `side_effect`** (not a positional list — list order is non-deterministic under `asyncio.gather`): `def merge_side_effect(**kwargs): return feat_a_fail if kwargs.get("feature") == "feat-a" else feat_b_ok`. Where `feat_a_fail = MergeResult(success=False, conflict=False, test_result=TestResult(passed=False, output="FAILED", return_code=1), error="Tests failed (exit code 1)")` and `feat_b_ok = MergeResult(success=True, conflict=False)`. `recover_test_failure` (AsyncMock) returns `MergeRecoveryResult(success=True, attempts=1, paused=False, flaky=False, error=None)`. Assert: `recover_test_failure` called exactly once; `"feat-b" in set(batch_result.features_merged)`. Assert on set membership and call counts, not list order.
  - `MergeResult`, `TestResult` from `claude.pipeline.merge`; `MergeRecoveryResult` from `claude.pipeline.merge_recovery`; `OvernightState`, `OvernightFeatureStatus` from `claude.overnight.state`
- **Verification**: `grep -cE "ci_pending|ci_failing" claude/overnight/tests/test_lead_unit.py` → pass if count ≥ 2; `grep -c "global_abort_signal\|budget_exhausted" claude/overnight/tests/test_lead_unit.py` → pass if count ≥ 1; `grep -c "recover_test_failure" claude/overnight/tests/test_lead_unit.py` → pass if count ≥ 1; `just test` → pass if exit 0
- **Status**: [x] complete

---

### Task 7: Add review-gating tests to TestAccumulateResultViaBatch (R8)
- **Files**:
  - `claude/overnight/tests/test_lead_unit.py`
- **What**: Add four test methods to the **existing** `TestAccumulateResultViaBatch` class (created by Task 6) covering the review-gating paths: (a) review not required → feature merged without calling `dispatch_review`; (b) review approved → feature merged; (c) review deferred → feature in `features_deferred`; (d) `dispatch_review` raises exception → feature in `features_deferred`. Each test drives `run_batch` with mocked `execute_feature` returning `FeatureResult(status="completed")` and `merge_feature` returning `MergeResult(success=True)`.
- **Depends on**: [6]
- **Complexity**: complex
- **Context**:
  - **CLASS EXTENSION — NOT APPEND**: Open `claude/overnight/tests/test_lead_unit.py`, locate the existing class `TestAccumulateResultViaBatch` created by Task 6, and add the four new test methods inside that class. Do NOT write a new `class TestAccumulateResultViaBatch:` block — Python allows duplicate class names and the second definition silently shadows the first, dropping all Task 6 tests from pytest discovery. Use the Edit tool to insert the four methods before the closing of the existing class (before `if __name__ == "__main__":` or before the next class definition at the same indentation level).
  - **Lazy-import trap**: `dispatch_review` is imported at `batch_runner.py:1691` inside `_accumulate_result` — `from claude.pipeline.review_dispatch import dispatch_review`. It is never a `batch_runner` module-level attribute. `patch.object(batch_runner_module, "dispatch_review")` will fail silently or raise. Correct patch target: `patch("claude.pipeline.review_dispatch.dispatch_review", new_callable=AsyncMock)`. Use `self.addCleanup(p.stop)` to guarantee the patch is active for the entire `await run_batch(...)` call.
  - `requires_review`, `read_tier`, `read_criticality` ARE module-level imports in `batch_runner` (line 30–32). Patch them at `batch_runner_module.requires_review`, `batch_runner_module.read_tier`, `batch_runner_module.read_criticality`.
  - Same run_batch scaffolding as Task 6: `parse_master_plan`, `create_worktree`, `load_state`, `save_state`, `load_throttle_config`, `ConcurrencyManager`, `execute_feature`, `_get_changed_files`, `overnight_log_event`, `_write_back_to_backlog`, `cleanup_worktree`, `save_batch_result` — all mocked (reuse the `_start_patch` helper and setUp from Task 6's class).
  - Sub-case details:
    - (a) `requires_review` → `return_value=False`: `dispatch_review` must NOT be called; assert `"feat-a" in set(batch_result.features_merged)`.
    - (b) `requires_review=True`, `dispatch_review` → `return_value=MagicMock(deferred=False, verdict="APPROVED", cycle=1)`: assert `"feat-a" in set(batch_result.features_merged)`.
    - (c) `requires_review=True`, `dispatch_review` → `return_value=MagicMock(deferred=True, verdict="DEFERRED_FOR_REVIEW", cycle=1)`: assert `len(batch_result.features_deferred) == 1`.
    - (d) `requires_review=True`, `dispatch_review` → `side_effect=RuntimeError("crash")`: assert `len(batch_result.features_deferred) == 1`. The crash path writes a deferral question (line 1748) — also mock `batch_runner_module.write_deferral`.
  - Method names must match the grep pattern for verification: use `test_review_not_required`, `test_review_approved`, `test_review_deferred`, `test_review_raises`.
  - `BatchConfig`: same constraints as Task 6 — `result_dir=Path(tmp)`, `overnight_state_path=Path(tmp)/"state.json"`.
- **Verification**: `grep -c "review_not_required\|review_approved\|review_deferred\|review_raises" claude/overnight/tests/test_lead_unit.py` → pass if count ≥ 4; `just test` → pass if exit 0
- **Status**: [x] complete

---

## Verification Strategy

After all tasks complete: run `just test` — pass if exit 0 and total wall-clock time ≤ 60 seconds. Run the grep commands from each task's Verification field sequentially to confirm all acceptance criteria are met.

## Veto Surface

- **Task sequencing on test_lead_unit.py**: Tasks 3–6 are chained to prevent file-write conflicts when appending. Tasks 1 and 2 are independent. This is conservative — if the overnight runner dispatches tasks from the same file in parallel, only independent tasks (1, 2, 3) are safe.
- **R2 test design choice**: execute_feature's brain-triage tests mock `_handle_failed_task` directly to isolate execute_feature's return-value handling from brain-decision logic. The complementary test in Task 2 covers `_handle_failed_task` internals. An alternative is to mock `request_brain_decision` instead and let `_handle_failed_task` run — this catches integration errors between execute_feature and _handle_failed_task but requires more mock setup.

## Scope Boundaries

- No changes to `batch_runner.py`, `brain.py`, or any production file.
- No new top-level test files — all additions go into `test_lead_unit.py` or `test_brain.py`.
- No snapshot libraries (syrupy, inline-snapshot) — direct assertions only.
- No characterization of session-layer concerns (`ConcurrencyManager` behavior, heartbeat timing, round scheduling).
- No testing of the `review_result is not None` branch in `_apply_feature_result` (dead code — unreachable in production).
