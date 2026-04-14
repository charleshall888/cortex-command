# Specification: extract-feature-executor-module-from-batch-runner

## Problem Statement

`batch_runner.py` is 2198 LOC and conflates three distinct architectural layers — session orchestration, per-feature execution, and outcome routing — in a single file with no unit tests for the execution layer. Any change to how features are dispatched, retried, or conflict-recovered requires reading and reasoning about the full file. This ticket extracts the per-feature execution layer (`execute_feature()` and ~600 LOC of helpers) into a new module `feature_executor.py`, giving per-feature execution a clear, documented public contract and making its helpers independently testable. This is Phase 1 of the 3-phase batch_runner decomposition (Candidate A from the epic research).

## Requirements

_Classification: Requirements 1–8 are must-have (correctness and regression gates; the extraction is incomplete without them). Requirement 9 is should-have (risk mitigation documentation for Phase 2; failure to include it increases merge-conflict risk with #076 but does not break overnight execution)._

1. **[Must] Create `claude/overnight/feature_executor.py`** containing `execute_feature()` and all its helpers: idempotency management (`_compute_plan_hash`, `_make_idempotency_token`, `_check_task_completed`, `_write_completion_token`), context loading (`_read_spec_content`, `_read_learnings`, `_render_template`, `_get_spec_path`), exit-report validation (`_read_exit_report`), brain-agent triage (`_handle_failed_task`), and conflict recovery policy (trivial fast-path, repair agent dispatch, budget gate). `_run_task` stays as an inner closure inside `execute_feature` — do NOT extract it as a module-level function.

   The public signature of `execute_feature` must be preserved exactly as it exists in the current `batch_runner.py`:

   ```python
   async def execute_feature(
       feature: str,
       worktree_path: Path,
       config: "BatchConfig",
       spec_path: Optional[str] = None,
       manager: Optional["ConcurrencyManager"] = None,
       consecutive_pauses_ref: Optional[list[int]] = None,
       repo_path: Path | None = None,
       integration_branches: dict[str, str] | None = None,
   ) -> FeatureResult:
   ```

   (`BatchConfig` and `ConcurrencyManager` are string-quoted because they are behind a `TYPE_CHECKING` guard — see Technical Constraints.)

   - Acceptance (a): `grep -n "^async def execute_feature" claude/overnight/feature_executor.py` exits 0 with at least one match.
   - Acceptance (b): `python3 -c "from claude.overnight.feature_executor import execute_feature"` exits 0.
   - Acceptance (c): `grep -cn "^def _run_task\|^async def _run_task" claude/overnight/feature_executor.py` prints `0` — `_run_task` is not at module level.

2. **[Must] Create `claude/overnight/types.py`** containing the `FeatureResult` dataclass. The docstring must include the complete status-to-field mapping. The full field inventory and mapping is as follows (reproduce this in the docstring):

   ```
   Fields:
     name: str                           — feature slug (always set)
     status: str                         — one of: merged, paused, deferred, failed, repair_completed
     error: Optional[str]                — set on paused, failed; describes the error
     deferred_question_count: int        — number of deferred questions (deferred path)
     files_changed: list[str]            — populated by _accumulate_result (not set by execute_feature)
     repair_branch: Optional[str]        — set on repair_completed (trivial and repair-agent paths)
     trivial_resolved: bool              — True when trivial fast-path resolved the conflict
     repair_agent_used: bool             — True when Sonnet/Opus repair agent ran
     parse_error: bool                   — True when plan parse failed (affects circuit-breaker logic)
     resolved_files: list[str]           — files resolved by trivial fast-path

   Status-to-field mapping:
     merged:           no optional fields set
     repair_completed: repair_branch, trivial_resolved, resolved_files, repair_agent_used
     paused:           error (required), parse_error (may be True)
     deferred:         deferred_question_count
     failed:           error (required)
   ```

   Both `feature_executor.py` and `batch_runner.py` must import `FeatureResult` from `claude.overnight.types`. The `FeatureResult` class definition must be removed from `batch_runner.py` and replaced with `from claude.overnight.types import FeatureResult`.

   - Acceptance (a): `grep -n "class FeatureResult" claude/overnight/types.py` exits 0 with a match.
   - Acceptance (b): `python3 -c "from claude.overnight.types import FeatureResult"` exits 0.
   - Acceptance (c): `grep -rn "from claude.overnight.batch_runner import FeatureResult" claude/overnight/` exits 1 (no matches).
   - Acceptance (d): `grep -n "from claude.overnight.types import.*FeatureResult" claude/overnight/batch_runner.py` exits 0 with a match.
   - Acceptance (e): `grep -cn "^class FeatureResult" claude/overnight/batch_runner.py` prints `0` — the class is no longer defined there.

3. **[Must] Create `claude/overnight/constants.py`** containing `CIRCUIT_BREAKER_THRESHOLD`. Both `batch_runner.py` and `feature_executor.py` import it from `constants.py`. The constant must not be defined as a standalone value in either file.
   - Acceptance (a): `grep -n "CIRCUIT_BREAKER_THRESHOLD" claude/overnight/constants.py` exits 0 with a match.
   - Acceptance (b): `grep -n "^CIRCUIT_BREAKER_THRESHOLD = " claude/overnight/batch_runner.py` exits 1 (no match).
   - Acceptance (c): `grep -n "^CIRCUIT_BREAKER_THRESHOLD = " claude/overnight/feature_executor.py` exits 1 (no match).

4. **[Must] `feature_executor.py` must not import from `batch_runner` or `orchestrator` at runtime.** A module-level docstring in `feature_executor.py` states: "This module must not import from `claude.overnight.batch_runner` or `claude.overnight.orchestrator`." A new test file `claude/overnight/tests/test_feature_executor_boundary.py` uses `ast.parse` to enforce the boundary:
   - Check all `ImportFrom` nodes: assert no `node.module` starts with `claude.overnight.batch_runner` or `claude.overnight.orchestrator`.
   - Check all `Import` nodes: assert no `alias.name` starts with `claude.overnight.batch_runner` or `claude.overnight.orchestrator`.
   - Acceptance: `pytest claude/overnight/tests/test_feature_executor_boundary.py -v` exits 0.

5. **[Must] `batch_runner.py` re-exports `execute_feature` in its namespace** so that existing call sites (including test `patch.object(batch_runner_module, "execute_feature", ...)` patterns) continue to work without modification.
   - Acceptance (a): `grep -n "from claude.overnight.feature_executor import execute_feature" claude/overnight/batch_runner.py` exits 0 with a match.
   - Acceptance (b): `python3 -c "from claude.overnight.batch_runner import execute_feature"` exits 0.

6. **[Must] Update test import paths and patch targets.** The following symbols move to new locations; update imports and mock/patch targets throughout the test suite:

   **Symbols moving to `claude.overnight.feature_executor`:**
   - `_compute_plan_hash`, `_make_idempotency_token`, `_check_task_completed`, `_write_completion_token` (from `test_idempotency.py`)
   - `_read_exit_report` and related execution-layer functions (from `test_exit_report.py`)
   - `_handle_failed_task` (from `test_brain.py`)
   - `_read_learnings` (from `test_lead_unit.py` line 27, and `test_brain.py`)
   - `_read_exit_report`, `_render_template`, `_handle_failed_task` (patched via `patch.object(batch_runner_module, ...)` in `test_lead_unit.py` — these must become `patch.object(feature_executor_module, ...)`)

   **Symbols moving to `claude.overnight.types`:**
   - `FeatureResult` (from `test_lead_unit.py` and `tests/fixtures/batch_runner/feature_result_variants.py`)

   **Patch path updates required (use `"claude.overnight.feature_executor.<name>"` instead of `"claude.overnight.batch_runner.<name>"` for these symbols):**
   - `request_brain_decision` — in `test_brain.py` (1 site)
   - `_read_learnings` — in `test_brain.py` (3 sites)
   - `_read_exit_report`, `_render_template`, `_handle_failed_task` — in `test_lead_unit.py` (multiple `patch.object` calls targeting `batch_runner_module`)

   - Acceptance: `just test` exits 0 with all existing tests passing.

7. **[Must] Unit tests for extracted pure helpers** must pass after the import-path migration.
   - Acceptance: `pytest claude/overnight/tests/test_idempotency.py claude/overnight/tests/test_exit_report.py claude/overnight/tests/test_brain.py -v` exits 0.

8. **[Must] Full regression gate passes.**
   - Acceptance: `just test` exits 0.

9. **[Should] PR description documents the post-#075 `_run_one` shape** to reduce merge-conflict risk with Phase 2 (#076). The relevant facts (derive from current `batch_runner.py`) are:
   - `_run_one` is an inner async function of `run_batch`, defined approximately at line 1985 in the current file. Signature: `async def _run_one(name: str) -> None`. It stays as an inner function after Phase 1.
   - Post-Phase 1, step 5 of `_run_one` calls `await execute_feature(...)` via the name imported at the top of `batch_runner.py` (the re-export). All 8 parameters are passed by keyword: `feature=name, worktree_path=..., config=..., spec_path=..., manager=..., consecutive_pauses_ref=..., repo_path=..., integration_branches=...`.
   - Phase 2 (#076) will change `_run_one` by collapsing the inline call to `await _accumulate_result(name, result)` into a single outcome-routing call to the extracted `outcome_router.apply_feature_result(...)`. The `_accumulate_result` helper currently spans ~400 LOC in `batch_runner.py` and is the primary target of Phase 2 extraction.
   - Acceptance: Interactive/session-dependent — PR body contains a `### \`_run_one\` shape after Phase 1` section covering the above three facts.

## Non-Requirements

- Daytime pipeline is NOT in scope for this ticket.
- `_get_changed_files` and `_classify_no_commit` do NOT move in Phase 1 — they are called only from `_apply_feature_result` (Phase 2 territory). They will move to `outcome_router.py` in Phase 2.
- `FeatureResult` discriminated-union refactor (splitting into per-status frozen dataclasses) is NOT in scope — deferred as a follow-up.
- `_run_task` inner closure does NOT get extracted as a standalone function.
- `BatchConfig` does NOT move to `types.py` in Phase 1 — it stays in `batch_runner.py`; `feature_executor.py` uses a `TYPE_CHECKING`-guarded import for its type annotation.
- `BatchResult` does NOT move in Phase 1 — it stays in `batch_runner.py` (orchestrator territory).
- Doc updates to `docs/overnight-operations.md` and `docs/pipeline.md` are NOT in scope for Phase 1 — deferred to Phase 3.
- The CLI contract (`python3 -m claude.overnight.batch_runner`) is NOT changed.
- No new public API surfaces beyond `execute_feature()`.

## Edge Cases

- **`asyncio.to_thread(save_state, ...)` concurrency hazard**: The call inside conflict recovery creates a known race if two features hit the repair path concurrently and both try to persist state. Pre-existing — not introduced by this extraction. Preserve the `_save_ok` guard intact and add a code comment documenting the race.
- **`conftest.py` coupling**: `conftest.py` stubs `backlog.update_item` before batch_runner is imported. `feature_executor.py` must not add unconditional module-level imports that fall outside the existing conftest stubs. If new imports are needed, update `conftest.py` accordingly.
- **`from __future__ import annotations`**: Required in `feature_executor.py`. Some carried-over annotations reference lazily-imported types; without this import they would raise `NameError` at module load.
- **`TYPE_CHECKING` guard for `BatchConfig`**: `execute_feature` accesses `config.*` attributes at runtime via duck-typing — no `isinstance` check exists. The guard is sufficient. Pattern: `from __future__ import annotations` at top, then `if TYPE_CHECKING: from claude.overnight.batch_runner import BatchConfig`.
- **`_run_task` inner closure**: Captures ~8 variables from `execute_feature`'s outer scope. Stays as inner function — do not extract it as a standalone function.

## Changes to Existing Behavior

- MODIFIED: `execute_feature()` lives in `batch_runner.py` → lives in `feature_executor.py`; `batch_runner.py` re-exports it so call sites and `patch.object(batch_runner_module, "execute_feature", ...)` patterns are unaffected.
- MODIFIED: `FeatureResult` dataclass lives in `batch_runner.py` → lives in `types.py`; both `feature_executor.py` and `batch_runner.py` import from `claude.overnight.types`.
- MODIFIED: `CIRCUIT_BREAKER_THRESHOLD` constant lives in `batch_runner.py` → lives in `constants.py`; both files import from `claude.overnight.constants`.
- ADDED: `claude/overnight/feature_executor.py` — per-feature execution module.
- ADDED: `claude/overnight/types.py` — shared data types (`FeatureResult` with documented status-to-field mapping).
- ADDED: `claude/overnight/constants.py` — shared constants (`CIRCUIT_BREAKER_THRESHOLD`).
- ADDED: `claude/overnight/tests/test_feature_executor_boundary.py` — AST-based import boundary enforcement test.
- No behavioral changes to overnight session execution.

## Technical Constraints

- **No circular imports**: `feature_executor` → `batch_runner` is forbidden (enforced by the boundary test in Req 4). `batch_runner` → `feature_executor` is the permitted direction.
- **`types.py` imports only from stdlib and third-party** — no imports from `claude.overnight.*`. This prevents it from becoming a node in the internal dependency graph. Note: this constraint applies to the Phase 1 contents (FeatureResult only). Before adding `BatchResult` or other orchestrator-layer types in Phase 2, verify that their field types do not require overnight-package imports.
- **`constants.py` imports only from stdlib** — no project imports.
- **`batch_runner.py` CLI contract is unchanged**: `python3 -m claude.overnight.batch_runner` remains the entry point; `BatchConfig` and `__main__` block remain in `batch_runner.py`.
- **All state writes use `tempfile + os.replace()`** (existing pattern, must be preserved in extracted code).
- **Feature status lifecycle transitions are identical** after extraction: `pending → running → merged/paused/deferred/failed`.
- **Repair attempt cap is a fixed architectural constraint**: Sonnet→Opus single escalation for merge conflicts; max 2 attempts (Sonnet + Opus) for test failures. These values must not change.
- **`from __future__ import annotations` is mandatory** in `feature_executor.py`.
- **`TYPE_CHECKING` guard for `BatchConfig`** — precedent: `claude/pipeline/conflict.py` line 23 already does this.
- **Re-export of `execute_feature` in `batch_runner.py`** must not be removed — `patch.object(batch_runner_module, "execute_feature", ...)` in characterization tests depends on it.
- **Private helpers (`_read_exit_report`, `_render_template`, `_handle_failed_task`, `_read_learnings`) are NOT re-exported from `batch_runner.py`** — their test patch targets must be updated to `"claude.overnight.feature_executor.<name>"` as specified in Req 6.

## Open Decisions

None — all design decisions resolved during the spec interview.
