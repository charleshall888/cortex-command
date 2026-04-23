# Research: Add characterization tests for batch_runner pre-extraction

**Backlog**: [080-add-characterization-tests-for-batch-runner-pre-extraction](../../backlog/080-add-characterization-tests-for-batch-runner-pre-extraction.md)
**Date**: 2026-04-13
**Phase**: Research

## Epic Reference

This ticket is scoped from epic [research/implement-in-autonomous-worktree-overnight-component-reuse/research.md](../../research/implement-in-autonomous-worktree-overnight-component-reuse/research.md). That research covers the full 3-way decomposition of `batch_runner.py` into `orchestrator.py`, `feature_executor.py`, and `outcome_router.py`. This ticket's scope is strictly pre-extraction: pin the current behavior of the five highest-risk behavioral surfaces before any extraction begins. The test suite written here is the regression oracle for the #075 → #076 → #077 chain.

## Codebase Analysis

### Files that will change

**New tests added to existing file (preferred):**
- `/Users/charlie.hall/Workspaces/cortex-command/claude/overnight/tests/test_lead_unit.py` — existing unit test file that already covers `_apply_feature_result`, run_batch-level behaviors (recovery dispatch/gate, budget exhausted signal, circuit breaker, no-commit guard). New characterization tests should be added here, not in a new `test_batch_runner.py` file. Rationale: (1) functions move to `feature_executor.py` (#075) and `outcome_router.py` (#076), so import paths will need migration regardless; (2) `test_lead_unit.py` already has the right class structure and conftest stubs; (3) a new parallel file would need migration twice (at #075 and again at #076).

**Fixtures (new directory):**
- `claude/overnight/tests/fixtures/batch_runner/` — as specified in the backlog item

**No production code changes** — this is test-only work.

### Existing test coverage (do not duplicate)

- `claude/overnight/tests/test_brain.py` — already tests `_handle_failed_task` from `batch_runner`. New tests must extend, not duplicate.
- `claude/overnight/tests/test_lead_unit.py` — existing classes:
  - `TestApplyFeatureResult`: covers basic _apply_feature_result outcome routing
  - `TestRecoveryDispatchPersistence`: covers recovery_attempts_map increment, test-failure recovery via run_batch
  - `TestBudgetExhaustionSignal`: covers budget_exhausted → consecutive_pauses_ref path (but only via `_apply_feature_result` directly — see Coverage Gap below)
  - `TestNoCommitHandling`, `TestSuffixedBranchHandling`, `TestCircuitBreakerBehavior`, `TestBranchCleanupOnPause`
- `claude/overnight/tests/test_deferral.py`, `test_state.py`, `test_plan.py`, `test_escalations.py` — adjacent modules, in scope only if integration boundary changes

### Architecture of _accumulate_result — CONFIRMED CLOSURE

`_accumulate_result` is defined at **line 1598** as `async def _accumulate_result(name, result)` inside `run_batch()`. It closes over 12+ `run_batch`-local variables:

```
batch_result, lock, consecutive_pauses_ref, config, backlog_ids, feature_names,
worktree_branches, repo_path_map, integration_branches, integration_worktrees,
session_id, recovery_attempts_map
```

It **cannot be called without first constructing all of `run_batch`'s local state**. The correct test strategy is Alternative A+C (see Tradeoffs section below).

### CRITICAL: review_result parameter in _apply_feature_result is structurally dead

`_apply_feature_result`'s `review_result` parameter is always passed as `None` at all four call sites inside `_accumulate_result` (lines 1622, 1670, 1838, 1854). The actual review gating logic (lines 1688–1757) lives entirely in `_accumulate_result`, not in `_apply_feature_result`. The `review_result is not None and review_result.deferred` branch in `_apply_feature_result` (line 1341) is structurally dead code today. Do not write tests asserting behavior through that branch — it cannot be reached by any production call path.

### FeatureResult status variants

| Status | Return site |
|--------|-------------|
| `completed` | Line 1066 — all tasks finished |
| `failed` | Lines 832–850, 960–964 — parse error, dependency error, unexpected exception |
| `paused` | Lines 819–824, 970–991 — budget exhausted, brain PAUSE, repair failed |
| `deferred` | Lines 568–573, 760–764, 812–817, 1030–1034 — brain DEFER, exit-report question, repair deferral |
| `repair_completed` | Lines 738–744, 793–798 — trivial conflict resolved or repair agent succeeded |

FeatureResult fields: `name`, `status`, `error`, `deferred_question_count`, `files_changed`, `repair_branch`, `trivial_resolved`, `repair_agent_used`, `parse_error`, `resolved_files`

### Coverage gaps (what must be added)

1. **CI deferral paths** (`ci_pending`, `ci_failing`) via `run_batch` with `merge_feature` returning the appropriate error string — not in `test_lead_unit.py` today
2. **Review gating via `dispatch_review`** — 4 cases: no review required (gating matrix skip), APPROVED verdict, deferred verdict, `dispatch_review` raises. These require patching the lazy import (see Integration Points)
3. **`global_abort_signal` via budget_exhausted in `run_batch`** — `TestBudgetExhaustionSignal` only calls `_apply_feature_result` directly, which does NOT set the signal (that is `_accumulate_result`'s job). No end-to-end test confirms the signal fires via the full `run_batch` path
4. **`_handle_failed_task` fixture extension** — `test_brain.py` covers the function but may not exercise all `consecutive_pauses_ref` mutation sequences per the backlog's acceptance criteria; verify before adding redundant tests

### Integration points and mock surfaces

**To test `execute_feature` directly:**
```python
from cortex_command.overnight.batch_runner import execute_feature

# Must mock:
patch("claude.overnight.batch_runner.load_state")          → OvernightState mock
patch("claude.overnight.batch_runner.read_events")         → yields event dicts or nothing
patch("claude.overnight.batch_runner.retry_task")          # AsyncMock → RetryResult
patch("claude.overnight.batch_runner.parse_feature_plan")  → FeaturePlan mock
patch("claude.overnight.batch_runner.mark_task_done_in_plan")
patch("claude.overnight.batch_runner._read_exit_report")   → (action, reason, question)
patch("claude.overnight.batch_runner.pipeline_log_event")
patch("claude.overnight.batch_runner.overnight_log_event")
patch("claude.overnight.batch_runner.subprocess.run")
# Conflict recovery (for surface 5):
patch("claude.overnight.batch_runner.resolve_trivial_conflict")  # AsyncMock
patch("claude.overnight.batch_runner.dispatch_repair_agent")     # AsyncMock
patch("claude.overnight.batch_runner.save_state")
```

**To test `_apply_feature_result` directly:**
```python
from cortex_command.overnight.batch_runner import _apply_feature_result

# Must mock:
patch("claude.overnight.batch_runner.subprocess.run")
patch("claude.overnight.batch_runner.merge_feature")           # AsyncMock → MergeResult
patch("claude.overnight.batch_runner.cleanup_worktree")
patch("claude.overnight.batch_runner.overnight_log_event")
patch("claude.overnight.batch_runner._write_back_to_backlog")
patch("claude.overnight.batch_runner._get_changed_files")
patch("claude.overnight.batch_runner._classify_no_commit")
patch("claude.overnight.batch_runner.write_deferral")
patch("claude.overnight.batch_runner._next_escalation_n")
```

**To test `_accumulate_result` behaviors via `run_batch`:**
```python
# Must mock (in addition to above):
patch("claude.overnight.batch_runner.parse_master_plan")
patch("claude.overnight.batch_runner.create_worktree")
patch("claude.overnight.batch_runner.load_throttle_config")
patch("claude.overnight.batch_runner.ConcurrencyManager")
patch("claude.overnight.batch_runner.execute_feature")         # AsyncMock → inject FeatureResult
patch("claude.overnight.batch_runner.recover_test_failure")   # AsyncMock
patch("claude.overnight.batch_runner.save_batch_result")
patch("claude.overnight.batch_runner.load_state")
patch("claude.overnight.batch_runner.save_state")
# CRITICAL: result_dir must be set to tmp_path in BatchConfig
# Default result_dir = _LIFECYCLE_ROOT writes lifecycle/batch-1-results.json to the REAL repo
```

**CRITICAL: Patching `dispatch_review` lazy import:**

`dispatch_review` is imported lazily inside `_accumulate_result` at line 1691: `from cortex_command.pipeline.review_dispatch import dispatch_review`. This import binds `dispatch_review` to the local scope of the `_accumulate_result` closure call, not to `batch_runner` module namespace. Standard `patch.object(batch_runner, "dispatch_review")` will fail because `dispatch_review` is never a `batch_runner` module-level attribute.

Correct approach: patch at the **source module** before the lazy import executes:
```python
patch("claude.pipeline.review_dispatch.dispatch_review")  # AsyncMock
```
Then also patch `batch_runner_module.requires_review` and `batch_runner_module.read_tier`/`batch_runner_module.read_criticality` (these ARE module-level imports in batch_runner):
```python
patch("claude.overnight.batch_runner.requires_review")       → True or False
patch("claude.overnight.batch_runner.read_tier")             → "complex" or "simple"
patch("claude.overnight.batch_runner.read_criticality")      → "high" etc.
```

### Conventions to follow

- **conftest.py is inherited**: All tests in `claude/overnight/tests/` automatically get SDK stubs and `backlog.update_item` stubs from conftest.py — no per-test setup needed for these
- **Patching style**: `patch(...) as mock_name` context manager in `setUp`, or `self.addCleanup(p.stop)` for multiple patches
- **Async tests**: Use `unittest.IsolatedAsyncioTestCase` for `run_batch`-level tests (existing pattern). Use bare `pytest.mark.asyncio` only if adding new top-level async functions
- **Temp directories**: Always use `tmp_path` (pytest) or `tempfile.TemporaryDirectory()` with tearDown. **Never** rely on real `lifecycle/` path in tests
- **AsyncMock required**: All coroutine functions (execute_feature, merge_feature, retry_task, recover_test_failure) must be mocked with `AsyncMock`, not `Mock`. Using `Mock` for coroutines returns a non-awaitable and silently fails

## Web Research

### Async testing patterns

- **AsyncMock (Python 3.8+)**: Required for any coroutine being mocked. `patch()` on a coroutine in Python 3.8+ auto-substitutes `AsyncMock`. Supports `return_value`, `side_effect` (exception, function, or iterable), and all `assert_called_*` methods.
- **Unawaited `create_task` hazard**: `run_batch` creates background tasks (`_heartbeat_loop`). If tests run with `IsolatedAsyncioTestCase`, these are automatically cleaned up. When using bare pytest-asyncio, must manually collect and await pending tasks after assertion.
- **Mutable `call_args_list`**: Stores references, not copies. If code mutates the argument after the mock call (e.g., mutating a dict passed as an event payload), assertions see post-mutation values. Use `side_effect` with `deepcopy` into a separate list when asserting on event payload content.
- **Concurrent call ordering**: `asyncio.gather`-dispatched agents have non-deterministic ordering. Assert on `set(mock.call_args_list)` or `mock.assert_any_call(...)`, not ordered sequence.

### Snapshot/golden-master libraries (for JSONL event log assertion)

- **syrupy**: External snapshot files in `__snapshots__/`. Recommended for file-based golden masters. `snapshot(name="label")` for multiple assertions; `props("id", "timestamp")` to strip volatile fields.
- **inline-snapshot**: In-source snapshots via `== snapshot()`. Good for keeping expected values near test code.
- **Anti-pattern**: Raw string comparison against hardcoded JSONL — unmaintainable. Prefer asserting on parsed list-of-dicts with volatile fields stripped.

**Recommendation for this codebase**: Avoid external snapshot libraries to start. Use `batch_result` field assertions (existing pattern in test_lead_unit.py) for behavioral coverage; reserve JSONL snapshot assertions for event-type sequences only (strip `ts` fields before comparison).

## Requirements & Constraints

### Test command
`just test` — runs the full test suite. New tests in `test_lead_unit.py` will automatically be included.

### Acceptance criteria (from backlog item #080)
- Tests run in under 60 seconds (all agent calls and subprocess operations mocked)
- Pin all `FeatureResult.status` variants produced by `execute_feature` and consumed by `_apply_feature_result`
- Pin conflict-recovery branching (trivial / repair-agent / budget-exhausted)
- Pin `consecutive_pauses_ref` and `recovery_attempts_map` mutation sequences across a representative multi-feature batch
- Tests pass against current `batch_runner.py` and remain the regression gate across #075, #076, #077

### Scope exclusions
- No extraction or renaming (that is #075/#076/#077)
- No full end-to-end overnight-session tests (mock at agent-dispatch boundary, not CLI boundary)
- No characterization of session-layer concerns (ConcurrencyManager, round loop, heartbeat) — those are #077's integration tests

### Architectural constraints from requirements/pipeline.md
- Repair attempt cap is a **fixed architectural constraint**: max 2 attempts for test failures; single Sonnet→Opus escalation for merge conflicts. Fixtures must not encode more attempts than the cap.
- State writes are atomic (`os.replace()`). Tests using real temp directories will observe this correctly.
- `events.log` is JSONL append-only. Assert on ordered sequences of parsed dicts.

## Tradeoffs & Alternatives

### The _accumulate_result problem

The backlog item lists `_accumulate_result` (inline outcome routing, lines 1598–1984) as a test target. Because it is a closure, it cannot be called directly. Four alternatives considered:

| Approach | Summary | Recommendation |
|----------|---------|----------------|
| **A: via `run_batch`** | Drive outer function with mocked execute_feature; assert on BatchResult fields and event log | Recommended for closure-unique behaviors |
| **B: Extract first** | Move _accumulate_result to module-level before adding tests | Rejected — scope creep, inverts "characterize before extract" |
| **C: Test only _apply_feature_result** | Skip _accumulate_result as SUT | Partial — use for outcome routing, but leaves CI deferral + global_abort_signal gap |
| **D: Reconstruct closure in test** | Manually mirror run_batch's locals in a test fixture | Rejected — drift risk makes tests unreliable as oracle |

### Recommended approach: A+C hybrid

1. **Test `_apply_feature_result` directly (C)** for all outcome-routing branches: each `FeatureResult.status` variant, backlog write-back, event-log entries, `consecutive_pauses_ref` increments. This function is already module-level; maps cleanly to pipeline test patterns.

2. **Test `_accumulate_result` via `run_batch` (A)** for behaviors **unique to the closure** and not delegated to `_apply_feature_result`:
   - `ci_pending` / `ci_failing` deferral path
   - Review gating via `dispatch_review` (4 cases: skip, APPROVED, deferred, raises)
   - `global_abort_signal` assignment when budget_exhausted fires end-to-end
   - `recovery_attempts_map[name]` increment sequence across a multi-feature batch

3. **Test `execute_feature` directly** for: happy path (all tasks completed), failed-task brain triage delegation, conflict-recovery branching (trivial / repair-agent / exhausted-budget).

4. **Test `_handle_failed_task` via extension of `test_brain.py`** for coverage gaps not already present (verify before adding, to avoid duplication).

### Estimated test count: 25–35 new tests

| Surface | New tests |
|---------|-----------|
| `execute_feature` (task dispatch, failure, conflict recovery branches) | ~10 |
| `_handle_failed_task` gaps (if any, beyond test_brain.py) | ~3–5 |
| `_apply_feature_result` (all status variants, dead `review_result` branch excluded) | ~8 |
| `_accumulate_result` via `run_batch` (CI deferral, review gating, abort signal) | ~6–8 |
| Multi-feature `consecutive_pauses_ref` / `recovery_attempts_map` sequence | ~3 |

## Open Questions

- **Test file placement**: Should new tests go into `test_lead_unit.py` or a new `test_batch_runner.py`? **Resolved by research**: Use `test_lead_unit.py`. Functions migrate to `feature_executor.py` (#075) and `outcome_router.py` (#076); a new file would need import-path migration twice. `test_lead_unit.py` already has the right class structure and conftest stubs (adversarial finding).

- **dispatch_review patch strategy**: Lazy import requires patching at `claude.pipeline.review_dispatch.dispatch_review`. Shared fixture vs. per-test context manager? **Resolved by research**: Per-test context manager — only ~6 tests need it; a shared conftest fixture would add overhead without simplifying anything at that volume.
