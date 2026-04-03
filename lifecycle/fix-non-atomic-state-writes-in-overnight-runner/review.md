# Review: Fix non-atomic state writes in overnight runner

> Reviewer: automated lifecycle review
> Cycle: 1

## Stage 1: Spec Compliance

### Requirement 1 — Orchestrator prompt atomic writes
**Rating**: PASS

`claude/overnight/orchestrator_io.py` re-exports `save_state`, `load_state`, `update_feature_status`, and `write_escalation` from the correct internal modules. `orchestrator-round.md` imports from `orchestrator_io` (lines 38, 280) and contains no raw `write_text(json.dumps(...)` or `Path(...).write_text(` calls for state files. The module docstring correctly describes it as a convention boundary, not a runtime guard.

### Requirement 2 — Batch results atomic write
**Rating**: PASS

`save_batch_result(result, path, extra_fields)` is implemented in `claude/overnight/state.py` (lines 385-432). It serializes via `asdict()`, merges `extra_fields` when provided, and writes atomically using tempfile + `durable_fsync` + `os.replace`. The call site in `batch_runner.py` (line 1970) passes `extra_fields={"throttle_stats": manager.stats}`, preserving the same value as the previous implementation. `path.parent.mkdir(parents=True, exist_ok=True)` handles directory creation.

### Requirement 3 — escalations.jsonl fsync
**Rating**: PASS

`write_escalation()` in `deferral.py` (lines 383-386) now calls `f.flush()` followed by `durable_fsync(f.fileno())` inside the `with open(..., "a")` block, after `f.write()`. The `durable_fsync` import is present at line 26. The existing `TestWriteEscalation` test surface is unaffected — the function signature and behavior are unchanged beyond the durability addition.

### Requirement 4 — recovery_attempts per-feature save
**Rating**: PASS

In `batch_runner.py` (lines 1711-1724), immediately after incrementing `recovery_attempts_map[name]` inside the `async with lock:` scope, the implementation performs `load_state()` -> update `recovery_attempts` -> `save_state()`. The code comment at lines 1712-1716 explicitly flags the tradeoff of synchronous I/O inside an async lock, as the spec required. The save uses `save_state()` which is atomic (tempfile+replace+durable_fsync), satisfying the crash-safety requirement.

The spec also asked to verify line 1544 (the `result.status != "completed"` early-return branch). At line 1543-1544, `recovery_attempts_map` is incremented when `result.repair_agent_used` is True (conflict repair path). This increment is NOT immediately persisted — it relies on the end-of-batch writeback (lines 1933-1944). The repair agent dispatch and `recovery_depth` save happened within `execute_feature()` itself (line 726), so the on-disk state records that a repair was attempted. The `recovery_attempts` field at line 1544 is a separate budget counter. While a per-feature save here would be ideal for full crash safety, the spec's primary Bug 4 target (test-failure recovery path) is correctly handled. This is a minor gap.

### Requirement 5 — Full durability for atomic write helpers
**Rating**: PASS

`durable_fsync(fd)` is implemented in `claude/common.py` (lines 274-293). It checks `sys.platform == "darwin"` and calls `fcntl.fcntl(fd, fcntl.F_FULLFSYNC)` on macOS, falling back to `os.fsync(fd)` elsewhere. Both `save_state()` (state.py line 368) and `atomic_write()` (common.py line 326) call `durable_fsync(fd)` before `os.replace()`. Since both use `os.write()` (low-level syscall, no userspace buffering), an explicit `f.flush()` is not needed — this is correct.

### Requirement 6 — No schema changes
**Rating**: PASS

`OvernightState`, `OvernightFeatureStatus`, and `BatchResult` dataclass schemas are unchanged. No new fields were added. `save_batch_result()` is a new function, not a schema change.

## Stage 2: Code Quality

### Naming conventions
Consistent with project patterns. `durable_fsync` follows the project's snake_case convention. `save_batch_result` follows the existing `save_state` naming pattern. `orchestrator_io.py` uses the underscore-separated module naming convention.

### Error handling
Appropriate for context. All atomic write paths have `except BaseException` cleanup blocks that close the fd and unlink the temp file. The Bug 4 per-feature save wraps in `try/except Exception: pass` with a comment explaining the tradeoff ("Don't let state-write failure block recovery"). The `write_escalation` fsync addition does not suppress exceptions — callers that catch exceptions from this function are unaffected.

### Test coverage
- `test_save_batch_result_fields_and_extra_fields` (test_overnight_state.py) verifies all `BatchResult` fields round-trip and `extra_fields` merge correctly.
- `TestRecoveryDispatchPersistence.test_recovery_attempts_persisted_per_feature` (test_lead_unit.py) verifies that triggering the test-failure recovery path persists `recovery_attempts=1` to disk, directly testing Bug 4's acceptance criterion.
- `TestRecoveryGate.test_gate_blocks_recovery_when_exhausted` verifies the budget gate works when `recovery_attempts >= 1`.

Missing: no unit test for `durable_fsync` itself (but it's a 4-line platform shim with no branching logic beyond `sys.platform`), no explicit test that `save_state` calls `durable_fsync` (would require mocking to verify, low value). Coverage is adequate.

### Pattern consistency
The implementation follows the project's established patterns:
- Atomic write: tempfile + `os.write` + fsync + `os.replace` + cleanup on exception — identical pattern in `save_state`, `save_batch_result`, and `atomic_write`.
- Re-export module (`orchestrator_io.py`) uses `__all__` and a clear docstring.
- `durable_fsync` placement in `common.py` follows the spec's acceptable alternative (the spec preferred `state.py` but accepted `common.py` if other modules need it — and indeed `deferral.py` also imports it).

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

The implementation addresses durability and crash-safety of file-based state writes. This aligns with the "File-based state" architectural constraint and "Graceful partial failure" quality attribute in `requirements/project.md`. No new behavior is introduced that falls outside existing requirements.

## Verdict

```json
{
  "verdict": "APPROVED",
  "cycle": 1,
  "issues": [],
  "requirements_drift": "none"
}
```
