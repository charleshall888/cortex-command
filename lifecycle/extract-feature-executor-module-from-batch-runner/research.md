# Research: Extract feature_executor module from batch_runner

## Epic Reference

Epic research: [`research/implement-in-autonomous-worktree-overnight-component-reuse/research.md`](../../research/implement-in-autonomous-worktree-overnight-component-reuse/research.md)

This ticket is Phase 1 of the 3-phase `batch_runner.py` decomposition (Candidate A from the epic). The epic established the architectural seams and justified the split on maintainability grounds. This ticket extracts the per-feature execution layer into `feature_executor.py`; Phase 2 (#076) extracts outcome routing into `outcome_router.py`; Phase 3 (#077) renames batch_runner → orchestrator.py.

---

## Codebase Analysis

### Files That Will Change

| File | Change |
|------|--------|
| `claude/overnight/batch_runner.py` | Remove execute_feature + helpers; add `from cortex_command.overnight.feature_executor import execute_feature`; batch_runner re-exports execute_feature in its namespace so patch targets in test_lead_unit.py continue to work |
| `claude/overnight/feature_executor.py` | New module — ~600–700 LOC |
| `claude/overnight/tests/test_idempotency.py` | Update imports from `batch_runner` → `feature_executor` (lines 20–25) |
| `claude/overnight/tests/test_exit_report.py` | Update imports from `batch_runner` → `feature_executor` (lines 18–22) |
| `claude/overnight/tests/test_brain.py` | Update import for `_handle_failed_task` (line 26) AND update patch path: `"claude.overnight.batch_runner.request_brain_decision"` → `"claude.overnight.feature_executor.request_brain_decision"` (line 287) |
| `claude/overnight/tests/test_lead_unit.py` | Patch targets survive if batch_runner re-exports execute_feature; review all patch paths |
| `claude/overnight/tests/fixtures/batch_runner/feature_result_variants.py` | Update FeatureResult import to feature_executor |
| `docs/overnight-operations.md` | Update strategy file consumers table: `execute_feature` consumer changes from batch_runner → feature_executor |
| `docs/pipeline.md` | Correct stale path: `claude/pipeline/batch_runner.py` → `claude/overnight/batch_runner.py` |

Optionally (if CIRCUIT_BREAKER_THRESHOLD placement decision goes to constants.py):

| File | Change |
|------|--------|
| `claude/overnight/constants.py` | New module — CIRCUIT_BREAKER_THRESHOLD (and potentially other shared constants) |

### `_get_changed_files` and `_classify_no_commit` — Stay in batch_runner

Call site analysis confirmed: both functions are called only from `_apply_feature_result` (lines 1303, 1309) and `_accumulate_result` (line 1656) — exclusively Phase 2/Phase 3 territory. Neither is called from within `execute_feature` or its helpers. They do NOT move in Phase 1. They will move to `outcome_router.py` in Phase 2.

The "What moves" section in the backlog item listing these functions is an error. The "What stays" section's explanation ("Shared helpers ... used by both #075 and #076; both import from orchestrator layer") is authoritative.

### FeatureResult Field Inventory (Complete)

Defined at `batch_runner.py` lines 124–138. All 10 fields are formally declared:

| Field | Type | Default | Populated by |
|-------|------|---------|--------------|
| `name` | `str` | required | all paths |
| `status` | `str` | required | `merged`, `paused`, `deferred`, `failed`, `repair_completed` |
| `error` | `Optional[str]` | `None` | conflict recovery, brain triage, plan parse errors, task failures |
| `deferred_question_count` | `int` | `0` | exit-report deferral, conflict recovery deferral, brain DEFER |
| `files_changed` | `list[str]` | `[]` | populated by `_accumulate_result` (Phase 2), not execute_feature |
| `repair_branch` | `Optional[str]` | `None` | trivial conflict, repair agent dispatch |
| `trivial_resolved` | `bool` | `False` | trivial fast-path |
| `repair_agent_used` | `bool` | `False` | repair agent dispatch |
| `parse_error` | `bool` | `False` | plan parse error path |
| `resolved_files` | `list[str]` | `[]` | trivial conflict path |

No undocumented `getattr` fields on `FeatureResult`. The `getattr(result, "error_type", None)` at line 969 accesses a `RetryResult` object (return from `retry_task`), not a `FeatureResult`.

### Current `_run_one` Shape and Post-#075 Changes

`_run_one` is an inner async function defined inside `run_batch` (lines 1985–2031). It stays in batch_runner as an inner function. The only Phase 1 change: the `await execute_feature(...)` call at step 5 switches from calling the local function to calling the imported one. Signature and callers are unchanged.

### CIRCUIT_BREAKER_THRESHOLD — Cross-Module Usage

The constant appears at three sites:
- Line 517: inside `_handle_failed_task` — moves to feature_executor in Phase 1
- Line 1515: inside `_apply_feature_result` — stays in batch_runner (Phase 2)
- Line 1966: inside `_accumulate_result` — stays in batch_runner (Phase 3)

This is the critical import boundary issue: the constant must be visible in both the new module and the original. Options:
1. **constants.py** (cleanest): new `claude/overnight/constants.py` holds `CIRCUIT_BREAKER_THRESHOLD`; both batch_runner and feature_executor import from there. No circular imports.
2. **Keep in batch_runner**: feature_executor imports it from batch_runner — but this creates a circular import (`batch_runner` imports `feature_executor`; `feature_executor` imports `batch_runner`). Not viable without TYPE_CHECKING tricks, and TYPE_CHECKING does not work for runtime values.
3. **Define in feature_executor**: batch_runner imports from feature_executor — but batch_runner is the orchestration layer importing from an execution module, and a constant used in outcome routing shouldn't live in the execution module.
4. **Duplicate**: define in both. Fragile if the value ever changes.

**Recommended**: Option 1 — create `constants.py`. Worth creating even for one constant since this pattern recurs across all three extraction phases.

### `_run_task` Inner Closure

`_run_task` is a closure defined inside `execute_feature` that captures `consecutive_pauses_ref`, `worktree_path`, `feature`, `config`, `plan_hash`, `spec_path_resolved`, `learnings_dir`, `manager` from the outer function scope. It moves to feature_executor as-is, still as an inner function of `execute_feature`. Do not attempt to extract it as a standalone function — passing all 8+ captured variables as explicit arguments is not worth the cleanup for Phase 1.

### BatchConfig and Circular Import

`execute_feature` uses `BatchConfig` attributes at runtime (e.g., `config.batch_id`, `config.base_branch`, `config.test_command`). `TYPE_CHECKING`-guarded imports work for the type annotation on `execute_feature`'s signature since Python duck-typing means no runtime `isinstance` check exists. The import in feature_executor looks like:

```python
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from cortex_command.overnight.batch_runner import BatchConfig
```

**If** a `constants.py` is created, `BatchConfig` should eventually migrate there too (or to a `types.py`). For Phase 1, TYPE_CHECKING is sufficient.

Note: `conflict.py` already uses this same TYPE_CHECKING pattern for `BatchConfig` at line 23 — precedent exists in the codebase.

### Imports feature_executor Will Need

From the existing batch_runner import chain:

```python
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from cortex_command.overnight.batch_runner import BatchConfig

from cortex_command.common import (
    compute_dependency_batches,
    mark_task_done_in_plan,
    read_criticality,
)
from cortex_command.pipeline.conflict import (
    ConflictClassification,
    dispatch_repair_agent,
    resolve_trivial_conflict,
)
from cortex_command.pipeline.parser import FeatureTask, parse_feature_plan
from cortex_command.pipeline.retry import RetryResult, retry_task
from cortex_command.overnight.brain import BrainAction, BrainContext, request_brain_decision
from cortex_command.overnight.deferral import (
    SEVERITY_BLOCKING,
    DeferralQuestion,
    EscalationEntry,
    write_deferral,
    write_escalation,
)
from cortex_command.overnight.events import (
    FEATURE_DEFERRED,
    MERGE_CONFLICT_CLASSIFIED,
    WORKER_MALFORMED_EXIT_REPORT,
    WORKER_NO_EXIT_REPORT,
    log_event as overnight_log_event,
    read_events,
)
from cortex_command.overnight.state import load_state, save_state
```

Plus `_next_escalation_n` from `claude.overnight.deferral` and `CIRCUIT_BREAKER_THRESHOLD` from `claude.overnight.constants` (if created) or batch_runner (see above).

Note: `from __future__ import annotations` is critical. `_apply_feature_result` uses `ReviewResult | None` as a parameter annotation but the `review_dispatch` import is lazy (inside `_accumulate_result`). Feature_executor must have `from __future__ import annotations` to prevent NameError if any carried-over annotation references a lazily-imported type.

### Existing Test Patterns

From `claude/overnight/tests/`:
- `test_idempotency.py`: `unittest.TestCase`, `tempfile.TemporaryDirectory`, `os.chdir`, direct function import. Direct model for pure helper tests.
- `test_exit_report.py`: `unittest.IsolatedAsyncioTestCase`, `patch`, `AsyncMock`. `_apply_common_mocks()` helper pattern for reusable mock setup.
- `test_brain.py`: Tests `_handle_failed_task`. **Critical**: patch at line 287 targets `"claude.overnight.batch_runner.request_brain_decision"` — must update to `"claude.overnight.feature_executor.request_brain_decision"` after extraction.
- `test_lead_unit.py`: Characterization tests from #080 for `execute_feature` and `_apply_feature_result`. Uses `patch.object(batch_runner_module, ...)` for execute_feature patches — these survive because batch_runner re-exports execute_feature.

`conftest.py` stubs `backlog.update_item` before batch_runner import. feature_executor must not add new unconditional module-level imports outside the stub coverage or test-time imports will fail.

### Prior Art: `review_dispatch.py` Extraction

The prior-art extraction from batch_runner. Key conventions to follow:
1. Module docstring stating what the module provides and explicitly what it does NOT do
2. `from __future__ import annotations` at top
3. `TYPE_CHECKING` guard for circular imports
4. Pure helpers defined before async entry point
5. `FeatureResult` defined in feature_executor (mirrors `ReviewResult` in review_dispatch)

---

## Web Research

### Import Boundary Enforcement

`import-linter` (PyPI) or `tach` enforce directional dependency rules:

```ini
# .importlinter
[importlinter:contract:no-reverse-import]
name=feature_executor cannot import batch_runner
type=forbidden
source_modules=claude.overnight.feature_executor
forbidden_modules=claude.overnight.batch_runner
```

Lighter alternative: ~10-LOC AST-based test that parses `feature_executor.py` and asserts no `ImportFrom` node references `claude.overnight.batch_runner`. Recommended over convention-only enforcement, since boundary enforcement is the primary goal of this refactor.

Anti-pattern: a `utils.py` that grows unbounded. A `constants.py` that imports only from stdlib is safe to import from any module without cycles.

### FeatureResult Contract Documentation

Options:
1. **Docstring table** within feature_executor (chosen for Phase 1) — mirrors ReviewResult in review_dispatch; status-to-field mapping documented inline.
2. **Per-status frozen dataclasses** (discriminated union, `Union[FeatureResultMerged, FeatureResultPaused, ...]`) — eliminates optional fields, enables mypy exhaustiveness via `assert_never`. Best long-term design but too disruptive for Phase 1.
3. **`__post_init__` validation** — intermediate option if future reviewers want runtime contract enforcement without a full redesign.

Phase 1 recommendation: docstring table. Phase 4/5 potential: discriminated union with mypy exhaustiveness checking.

### Characterization Test Pattern

Before extraction: tests exist against `batch_runner.execute_feature`. After extraction: same tests, updated import paths, must pass identically. The #080 characterization test pre-work makes Phase 1 test migration straightforward — it is primarily an import-path update, not new test writing.

For new pure helpers (any added during extraction): parametrized `pytest` with injectable non-deterministic inputs (clock, uuid via default-argument callables).

### "Move then Re-export" Migration Sequence

1. Create feature_executor.py, move functions there
2. In batch_runner.py: `from cortex_command.overnight.feature_executor import execute_feature` (re-export — callers continue to work)
3. Confirm all tests pass
4. Remove any unnecessary re-exports after Phase 2/3 migrations complete

---

## Requirements & Constraints

### From `requirements/project.md`

- **Graceful partial failure**: `execute_feature()` is the unit of failure isolation. Its error-handling contract (returns FeatureResult, never raises) must be fully preserved after extraction.
- **Maintainability through simplicity**: decomposition is the mechanism; the extracted module must be genuinely simpler, not a pass-through wrapper.
- **File-based state**: all state writes use tempfile + `os.replace()`. Any `asyncio.to_thread(save_state, ...)` calls inside execute_feature must be preserved intact.
- **Quality bar**: existing characterization tests (from #080) and integration tests must pass.

### From `requirements/pipeline.md`

- **Feature status lifecycle** (must-have): `pending→running→merged/paused/deferred/failed`. All transitions must be preserved exactly.
- **Fail-forward model** (must-have): one feature's failure cannot block others in the same round.
- **Repair attempt cap** (fixed architectural constraint): Sonnet→Opus single escalation for merge conflicts; max 2 attempts (Sonnet + Opus) for test failures. These are different caps; do not unify.
- **events.log ownership**: batch_runner (and by extension feature_executor, during execution) owns all events.log writes. Review agent writes only review.md.
- **Atomicity**: `tempfile + os.replace()` for all state writes.

### From docs

- **CLI contract**: `python3 -m cortex_command.overnight.batch_runner` must remain the entry point. `BatchConfig` and `__main__` block stay in batch_runner.
- **Doc updates needed**: `docs/overnight-operations.md` strategy file consumers table references execute_feature by module name — must update from batch_runner to feature_executor after extraction. `docs/pipeline.md` has stale path `claude/pipeline/batch_runner.py` — should be `claude/overnight/batch_runner.py`.
- **Scope**: feature_executor.py is an internal overnight library module, not a standalone CLI and not a published package.

---

## Tradeoffs & Alternatives

### FeatureResult Location

**Option A — Move to feature_executor.py** (recommended for Phase 1): natural home as return type of execute_feature; matches ReviewResult pattern in review_dispatch.py. Phase 2 outcome_router imports it from feature_executor. Clean one-directional dependency.

**Option B — Create types.py** (better long-term): clean for both feature_executor and outcome_router to import; avoids inter-module dependencies. Premature in Phase 1 with only one consumer — Phase 2 is when the full picture is clearer. Evaluate at Phase 2 extraction.

**Option C — Keep in batch_runner**: creates `feature_executor → batch_runner` import — the exact circular dependency this extraction aims to eliminate. Not viable.

**Decision**: Option A for Phase 1.

### CIRCUIT_BREAKER_THRESHOLD

As analyzed above: `constants.py` is the clean solution. Duplication and circular imports are both worse. Worth creating now since the same problem recurs in Phase 2 (outcome_router will also need shared constants).

### Test Scope

Primary scope for Phase 1: migrate import paths in existing tests (test_idempotency.py, test_exit_report.py, test_brain.py, test_lead_unit.py). Fix test_brain.py patch path. Verify characterization tests from #080 pass against the extracted module.

Additionally: add an AST-based import boundary test (~10 LOC) that asserts no import from `claude.overnight.batch_runner` in `feature_executor.py`.

### Import Boundary Enforcement

**Docstring** (Option B in agent 4): module-level note "This module must not import from batch_runner or orchestrator." Zero cost, always visible.

**AST test** (Option C in agent 4): ~10 LOC `ast.parse` test, deterministic, catches violations in CI before code review. Strongly recommended.

Convention-only (Option A): insufficient given this is the architectural goal.

---

## Adversarial Review

### `test_brain.py` Patch Path Will Break

`test_brain.py` line 287 patches `"claude.overnight.batch_runner.request_brain_decision"`. After `_handle_failed_task` moves to feature_executor, `request_brain_decision` is resolved in feature_executor's namespace, not batch_runner's. The patch will silently fail to intercept the call — the test may pass with incorrect behavior or fail with SDK errors. **Must update** to `"claude.overnight.feature_executor.request_brain_decision"`.

### `CIRCUIT_BREAKER_THRESHOLD` Circular Import Risk

Cannot keep the constant in batch_runner and import it into feature_executor — that creates the circular import the extraction aims to eliminate (`batch_runner` → `feature_executor` → `batch_runner`). Constants.py is the only clean resolution (not convention-only or duplication).

### `asyncio.to_thread` Concurrency Hazard (Pre-existing)

`execute_feature` calls `asyncio.to_thread(save_state, ...)` at line 770. Two concurrent features hitting the conflict recovery path could race on `overnight-state.json`. This is a pre-existing hazard, not introduced by extraction. The `_save_ok` guard after `asyncio.to_thread` must be preserved in feature_executor. Document the concurrency hazard in a comment.

### conftest.py Coupling

The test `conftest.py` stubs `backlog.update_item` before batch_runner is imported (because batch_runner imports it unconditionally). `feature_executor.py` must not add new unconditional module-level imports beyond what the conftest stubs — or standalone feature_executor tests will fail on import.

### `ReviewResult` Annotation Without Import

`_apply_feature_result` uses `ReviewResult | None` as a parameter annotation (lazy import pattern). This works because `from __future__ import annotations` is present. `feature_executor.py` must also carry `from __future__ import annotations` — and any function signature referencing a lazily-imported type must use string annotations or `__future__` to avoid NameError.

### `_run_task` Not Separately Extractable

`_run_task` is a closure inside `execute_feature` capturing ~8 variables from the outer scope. Extracting it as a standalone function requires threading all of them as explicit arguments. Out of scope for Phase 1 — leave as inner function.

### BatchConfig Runtime Attribute Access

`execute_feature` accesses `config.batch_id`, `config.base_branch`, etc. at runtime. TYPE_CHECKING guard is safe since Python duck-typing doesn't require `isinstance` checks. However, if test fixtures construct `BatchConfig` objects, they must import it from batch_runner — document this dependency so test authors know where BatchConfig lives.

---

## Open Questions

- **CIRCUIT_BREAKER_THRESHOLD placement**: create `claude/overnight/constants.py` for this constant? Adds one new file but avoids circular import and duplication. The epic research's target layout (`batch_runner.py`, `orchestrator.py`, `feature_executor.py`, `outcome_router.py`, `state.py`, `throttle.py`, `deferral.py`, `brain.py`, `strategy.py`) did not include a constants.py — is this deviation acceptable? (Recommended: yes, for this one case.)

- **FeatureResult in feature_executor vs. types.py**: move now (Option A) or wait for Phase 2 to create a shared types.py (Option B)? Decision affects Phase 2 import graph. Deferred: will be resolved in Spec by asking the user.
