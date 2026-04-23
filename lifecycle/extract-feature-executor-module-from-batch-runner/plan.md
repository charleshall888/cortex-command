# Plan: extract-feature-executor-module-from-batch-runner

## Overview

Extract `execute_feature()` and ~600 LOC of helpers from `batch_runner.py` into a new `feature_executor.py` module, with `FeatureResult` going into `types.py` and `CIRCUIT_BREAKER_THRESHOLD` into `constants.py`. The migration is done in dependency order (constants → types → feature_executor → batch_runner update → tests), with `batch_runner.py` re-exporting `execute_feature` so run-batch call sites and `patch.object(batch_runner_module, "execute_feature", ...)` patterns remain unmodified.

## Tasks

### Task 1: Create `claude/overnight/constants.py`
- **Files**: `claude/overnight/constants.py`
- **What**: Create a new module holding `CIRCUIT_BREAKER_THRESHOLD = 3`. Module-level docstring states it imports only from stdlib and no other overnight package imports should be added without checking the Phase 2 import graph.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Current definition is at `batch_runner.py` line 1200. Value is `3`. The constant appears at three sites in batch_runner (lines 517, 1515, 1966) — Task 4 removes the definition and adds the import. Task 3 imports from constants.py instead of batch_runner.
- **Verification**: `grep -n "CIRCUIT_BREAKER_THRESHOLD" claude/overnight/constants.py` — pass if exits 0 with one match. `python3 -c "from cortex_command.overnight.constants import CIRCUIT_BREAKER_THRESHOLD"` — pass if exits 0.
- **Status**: [ ] pending

### Task 2: Create `claude/overnight/types.py`
- **Files**: `claude/overnight/types.py`
- **What**: Create a new module with the `FeatureResult` dataclass. The module docstring must state that types.py imports only from stdlib and third-party — no `claude.overnight.*` imports allowed. The `FeatureResult` docstring must include the complete status-to-field mapping table from Req 2 of the spec.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Current `FeatureResult` is defined at `batch_runner.py` lines 125–138. Fields: `name: str`, `status: str`, `error: Optional[str] = None`, `deferred_question_count: int = 0`, `files_changed: list[str] = field(default_factory=list)`, `repair_branch: Optional[str] = None`, `trivial_resolved: bool = False`, `repair_agent_used: bool = False`, `parse_error: bool = False`, `resolved_files: list[str] = field(default_factory=list)`. Use `@dataclass` decorator. Import `Optional` from `typing`, `dataclass` and `field` from `dataclasses`. Status-to-field mapping from the spec: merged (no optional fields), repair_completed (repair_branch, trivial_resolved, resolved_files, repair_agent_used), paused (error required, parse_error may be True), deferred (deferred_question_count), failed (error required).
- **Verification**: `grep -n "class FeatureResult" claude/overnight/types.py` — pass if exits 0 with one match. `python3 -c "from cortex_command.overnight.types import FeatureResult"` — pass if exits 0.
- **Status**: [ ] pending

### Task 3: Create `claude/overnight/feature_executor.py`
- **Files**: `claude/overnight/feature_executor.py`
- **What**: Create the new per-feature execution module containing `execute_feature()` and all its helpers, moved verbatim from `batch_runner.py`. Add the import boundary docstring, `from __future__ import annotations`, TYPE_CHECKING guard for `BatchConfig`, and import `FeatureResult` from types.py and `CIRCUIT_BREAKER_THRESHOLD` from constants.py. Add a code comment on the `asyncio.to_thread(save_state, ...)` concurrency race.
- **Depends on**: [1, 2]
- **Complexity**: complex
- **Context**:
  Functions to move from batch_runner.py (preserve definitions verbatim, update imports):
  - `_render_template` (line 338) — pure helper
  - `_get_spec_path` (line 346) — pure helper
  - `_read_spec_content` (line 361) — pure helper
  - `_read_learnings` (line 374) — pure helper
  - `_read_exit_report` (line 448) — pure helper
  - `async def _handle_failed_task` (line 497) — async helper calling brain.py + deferral
  - `_compute_plan_hash` (line 584) — pure helper
  - `_make_idempotency_token` (line 596) — pure helper
  - `_check_task_completed` (line 607) — pure helper
  - `_write_completion_token` (line 634) — pure helper
  - `async def execute_feature` (line 662) — public entry point; keeps `_run_task` as inner closure

  Module-level docstring: "This module contains the per-feature execution layer extracted from batch_runner.py. This module must not import from `claude.overnight.batch_runner` or `claude.overnight.orchestrator`."

  Module dependencies (derive exact import lines from the corresponding block in `batch_runner.py`, following the same aliases — do not invent new ones):
  - stdlib: `asyncio`, `hashlib`, `json`, `logging`, `os`, `subprocess`, `dataclasses` (dataclass + field), `datetime` (datetime + timezone), `pathlib` (Path), `typing` (TYPE_CHECKING, Optional)
  - TYPE_CHECKING guard: import `BatchConfig` from `claude.overnight.batch_runner` — guarded so it resolves only at type-check time, not at runtime
  - `claude.common`: `compute_dependency_batches`, `mark_task_done_in_plan`, `read_criticality`
  - `claude.pipeline.conflict`: `ConflictClassification`, `dispatch_repair_agent`, `resolve_trivial_conflict`
  - `claude.pipeline.parser`: `FeatureTask`, `parse_feature_plan`
  - `claude.pipeline.retry`: `RetryResult`, `retry_task`
  - `claude.pipeline.events`: the `log_event` function aliased as `pipeline_log_event` — look up the exact alias used in `batch_runner.py`
  - `claude.overnight.brain`: `BrainAction`, `BrainContext`, `request_brain_decision`
  - `claude.overnight.deferral`: `SEVERITY_BLOCKING`, `DeferralQuestion`, `EscalationEntry`, `write_deferral`, `write_escalation`, `_next_escalation_n`
  - `claude.overnight.events`: `FEATURE_DEFERRED`, `MERGE_CONFLICT_CLASSIFIED`, `WORKER_MALFORMED_EXIT_REPORT`, `WORKER_NO_EXIT_REPORT`, `log_event` aliased as `overnight_log_event`, `read_events`
  - `claude.overnight.state`: `load_state`, `save_state`
  - `claude.overnight.types`: `FeatureResult`
  - `claude.overnight.constants`: `CIRCUIT_BREAKER_THRESHOLD`

  The `asyncio.to_thread(save_state, ...)` call in conflict recovery (around the `_save_ok` guard): add a comment `# Concurrency hazard (pre-existing): two concurrent features on the repair path may race on overnight-state.json. The _save_ok guard is the existing mitigation — do not remove it.`

  Precedent: `claude/pipeline/conflict.py` line 23 for the TYPE_CHECKING pattern.
- **Verification**: (a) `grep -n "^async def execute_feature" claude/overnight/feature_executor.py` — pass if exits 0 with one match. (b) `python3 -c "from cortex_command.overnight.feature_executor import execute_feature"` — pass if exits 0. (c) `grep -cn "^def _run_task\|^async def _run_task" claude/overnight/feature_executor.py` — pass if prints `0`.
- **Status**: [ ] pending

### Task 4: Update `claude/overnight/batch_runner.py` — remove moved symbols, add imports and re-export
- **Files**: `claude/overnight/batch_runner.py`
- **What**: Remove `FeatureResult` class definition, `CIRCUIT_BREAKER_THRESHOLD` constant definition, and the definitions of all functions moved to feature_executor.py. Add `from cortex_command.overnight.types import FeatureResult`, `from cortex_command.overnight.constants import CIRCUIT_BREAKER_THRESHOLD`, and `from cortex_command.overnight.feature_executor import execute_feature`. Do NOT remove or re-export `_read_learnings`, `_read_exit_report`, `_render_template`, `_handle_failed_task`, or any other private helpers.
- **Depends on**: [3]
- **Complexity**: complex
- **Context**:
  Definitions to remove (line references are current; reconfirm when editing):
  - `class FeatureResult` (lines 125–138)
  - Functions: `_render_template` (338), `_get_spec_path` (346), `_read_spec_content` (361), `_read_learnings` (374), `_read_exit_report` (448), `async def _handle_failed_task` (497), `_compute_plan_hash` (584), `_make_idempotency_token` (596), `_check_task_completed` (607), `_write_completion_token` (634), `async def execute_feature` (662, including the inner `_run_task` closure)
  - `CIRCUIT_BREAKER_THRESHOLD = 3` (line 1200)

  After removal, add near the top of the imports section:
  ```
  from cortex_command.overnight.types import FeatureResult
  from cortex_command.overnight.constants import CIRCUIT_BREAKER_THRESHOLD
  from cortex_command.overnight.feature_executor import execute_feature
  ```

  Placement: the three new imports should be grouped after existing `claude.overnight.*` imports and before `claude.pipeline.*` imports (or wherever the existing overnight imports are grouped). The re-export of `execute_feature` makes it available as `batch_runner.execute_feature` so `patch.object(batch_runner_module, "execute_feature", ...)` in test_lead_unit.py continues to work.

  `CIRCUIT_BREAKER_THRESHOLD` and `FeatureResult` remain available as attributes of the batch_runner module via Python's import semantics (no explicit re-export declaration needed).

  Note: `_apply_feature_result` (line ~1200), `_accumulate_result` (line ~1535), `run_batch`, `BatchConfig`, `BatchResult`, `__main__` block — all stay in batch_runner unchanged.
- **Verification**: (a) `grep -n "from cortex_command.overnight.feature_executor import execute_feature" claude/overnight/batch_runner.py` — pass if exits 0 with one match. (b) `python3 -c "from cortex_command.overnight.batch_runner import execute_feature"` — pass if exits 0. (c) `grep -cn "^class FeatureResult" claude/overnight/batch_runner.py` — pass if prints `0`. (d) `grep -n "^CIRCUIT_BREAKER_THRESHOLD = " claude/overnight/batch_runner.py` — pass if exits 1 (no match). (e) `grep -n "^async def execute_feature" claude/overnight/batch_runner.py` — pass if exits 1 (no match).
- **Status**: [ ] pending

### Task 5: Create `claude/overnight/tests/test_feature_executor_boundary.py`
- **Files**: `claude/overnight/tests/test_feature_executor_boundary.py`
- **What**: Create the AST-based import boundary test that asserts `feature_executor.py` contains no imports from `claude.overnight.batch_runner` or `claude.overnight.orchestrator`.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**:
  Test uses `ast.parse(Path("claude/overnight/feature_executor.py").read_text())`. Walk all nodes — for `ast.ImportFrom` nodes check `node.module` does not start with `"claude.overnight.batch_runner"` or `"claude.overnight.orchestrator"`. For `ast.Import` nodes check no `alias.name` starts with those prefixes. Use `unittest.TestCase`. Module docstring: "Enforces that feature_executor.py does not import from batch_runner or orchestrator — prevents circular imports."
  Pattern: existing boundary tests in the codebase for reference (check `tests/` for ast-based test patterns if any exist).
- **Verification**: `pytest claude/overnight/tests/test_feature_executor_boundary.py -v` — pass if exits 0.
- **Status**: [ ] pending

### Task 6: Update test imports and patch paths — `test_idempotency.py`, `test_exit_report.py`, `test_brain.py`, `feature_result_variants.py`
- **Files**:
  - `claude/overnight/tests/test_idempotency.py`
  - `claude/overnight/tests/test_exit_report.py`
  - `claude/overnight/tests/test_brain.py`
  - `claude/overnight/tests/fixtures/batch_runner/feature_result_variants.py`
- **What**: Update import statements and mock/patch paths in these four files so they target symbols at their new locations in `feature_executor` and `types`.
- **Depends on**: [3, 4]
- **Complexity**: complex
- **Context**:
  **test_idempotency.py** (lines 20–25): Change `from cortex_command.overnight.batch_runner import (_check_task_completed, _compute_plan_hash, _make_idempotency_token, _write_completion_token)` → `from cortex_command.overnight.feature_executor import (...)`.

  **test_exit_report.py** (lines 18–22 + `_apply_common_mocks` at lines 163–191 + per-test `_read_exit_report` patches at lines 211–212, 232–234, and similar in remaining test methods):
  - Import: `_read_exit_report` moves to feature_executor; `execute_feature` and `BatchConfig` stay importable from batch_runner.
  - All string patch targets in `_apply_common_mocks` change `"claude.overnight.batch_runner.*"` → `"claude.overnight.feature_executor.*"` for: `parse_feature_plan`, `retry_task`, `pipeline_log_event`, `subprocess.run`, `_render_template`, `read_criticality`, `overnight_log_event`, `mark_task_done_in_plan`, `write_escalation`, `_next_escalation_n`.
  - Per-test patches for `_read_exit_report`: change from `"claude.overnight.batch_runner._read_exit_report"` → `"claude.overnight.feature_executor._read_exit_report"`.

  **test_brain.py** (lines 26 + 286–287 + 331–348 + 369–386 + 409–426):
  - Line 26: `from cortex_command.overnight.batch_runner import _handle_failed_task` → `from cortex_command.overnight.feature_executor import _handle_failed_task`.
  - All `"claude.overnight.batch_runner.*"` string patch targets in `TestCircuitBreakerPreDispatch` and `TestHandleFailedTaskBrainActions` → `"claude.overnight.feature_executor.*"`: covers `request_brain_decision`, `overnight_log_event`, `mark_task_done_in_plan`, `write_deferral`, `_read_learnings`.

  **feature_result_variants.py** (line 6): `from cortex_command.overnight.batch_runner import FeatureResult` → `from cortex_command.overnight.types import FeatureResult`.
- **Verification**: `pytest claude/overnight/tests/test_idempotency.py claude/overnight/tests/test_exit_report.py claude/overnight/tests/test_brain.py -v` — pass if exits 0 with all tests passing.
- **Status**: [ ] pending

### Task 7: Update `claude/overnight/tests/test_lead_unit.py`
- **Files**: `claude/overnight/tests/test_lead_unit.py`
- **What**: Update the `_read_learnings` import to come from `feature_executor`, and update all `patch.object(batch_runner_module, ...)` calls in `TestExecuteFeature` and `TestConflictRecoveryBranching` to target a `feature_executor_module` reference for symbols that now live in feature_executor. Leave `TestApplyFeatureResult`, `TestEffectiveMergeRepoPath`, and `TestAccumulateResultViaBatch` patch targets unchanged.
- **Depends on**: [3, 4]
- **Complexity**: complex
- **Context**:
  **Import changes** (lines 19–29):
  - `_read_learnings` (line 27): change import source from `batch_runner` → `feature_executor`. All other imports in the block (`BatchResult`, `BatchConfig`, `CIRCUIT_BREAKER_THRESHOLD`, `FeatureResult`, `_apply_feature_result`, `_effective_merge_repo_path`, `execute_feature`) remain importable from `batch_runner` (either they stayed there or are re-exported from there).
  - Add `import cortex_command.overnight.feature_executor as feature_executor_module` after the existing `import cortex_command.overnight.batch_runner as batch_runner_module` at line 19.

  **TestExecuteFeature** (class starting at line 1013 — all `patch.object(batch_runner_module, ...)` calls in this class that target execution-layer symbols):
  Symbols to redirect to `feature_executor_module`: `load_state`, `parse_feature_plan`, `retry_task`, `_read_exit_report`, `mark_task_done_in_plan`, `pipeline_log_event`, `overnight_log_event`, `read_criticality`, `_render_template`, `_handle_failed_task`.
  Note: TestExecuteFeature contains no `patch.object(batch_runner_module, "execute_feature", ...)` — that pattern lives only in TestAccumulateResultViaBatch (see below).

  **TestConflictRecoveryBranching** (class around line 1193 — all `patch.object(batch_runner_module, ...)` calls in this class that target execution-layer symbols):
  Symbols to redirect to `feature_executor_module`: `load_state`, `resolve_trivial_conflict`, `dispatch_repair_agent`, `save_state`, `write_deferral`, `overnight_log_event`, `pipeline_log_event`, `_render_template`, `read_criticality`, `parse_feature_plan`, `read_events`.
  Note: `read_events` is patched independently in each of the three test methods (not via `_base_patches`), returning a mock iterator of conflict events. After extraction it resolves in `feature_executor.__dict__`, so the patch target must move to `feature_executor_module`.
  Symbol to keep on `batch_runner_module`: `execute_feature`.

  **TestApplyFeatureResult** (class around line 92): leave all `patch.object(batch_runner_module, ...)` unchanged — `_apply_feature_result` and its collaborators (`_write_back_to_backlog`, `overnight_log_event`, `_get_changed_files`, `merge_feature`) stay in batch_runner.

  **TestAccumulateResultViaBatch** (class around line 370): leave `patch.object(batch_runner_module, "execute_feature", ...)` unchanged (lines 378, 464). The re-export works because `_run_one` calls `execute_feature` as a bare name resolved via `batch_runner.__dict__` at call time — patching `batch_runner_module.execute_feature` replaces that entry, so the lookup inside `_run_one` finds the mock. Do not rewrite `_run_one` to call `feature_executor.execute_feature(...)` directly, as that would bypass this patch mechanism.
- **Verification**: `just test` — pass if exits 0 with all tests passing.
- **Status**: [ ] pending

## Verification Strategy

After all tasks complete: `just test` must exit 0 with all existing tests passing. Additionally verify the three acceptance checks from the spec's Req 4 (boundary test) and Req 5 (re-export): `python3 -c "from cortex_command.overnight.batch_runner import execute_feature; from cortex_command.overnight.feature_executor import execute_feature"` and `pytest claude/overnight/tests/test_feature_executor_boundary.py -v` both exit 0. Confirm that `python3 -m claude.overnight.batch_runner --help` (or any entry-point invocation) still works, verifying the CLI contract is unchanged.

## Veto Surface

- **Task order 6 before 7 vs. both together**: Tasks 6 and 7 can run concurrently since they modify separate files. If overnight dispatch parallelizes them, the boundary is clean — neither file is in both tasks' Files list.
- **FeatureResult remaining importable from batch_runner**: batch_runner will have `from cortex_command.overnight.types import FeatureResult`, which makes `FeatureResult` an attribute of the batch_runner module. `test_lead_unit.py` imports it from batch_runner and that import continues to work. If this is undesirable (wanting strict "import from types only"), test_lead_unit.py's import line 24 would need to change — but that's outside the spec's stated requirements.

## Scope Boundaries

- `_get_changed_files` and `_classify_no_commit` stay in `batch_runner.py` — called only from Phase 2 territory (`_accumulate_result`, `_apply_feature_result`).
- `BatchConfig`, `BatchResult`, and the `__main__` block stay in `batch_runner.py`.
- `_run_task` stays as an inner closure inside `execute_feature` — not extracted as a standalone function.
- `FeatureResult` discriminated-union refactor deferred.
- Doc updates to `docs/overnight-operations.md` and `docs/pipeline.md` deferred to Phase 3 (#077).
- No new public API surfaces beyond `execute_feature()`.
