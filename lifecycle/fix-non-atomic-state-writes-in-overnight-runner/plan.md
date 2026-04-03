# Plan: fix-non-atomic-state-writes-in-overnight-runner

## Overview

Bottom-up implementation: add `durable_fsync()` to `common.py` first (the shared foundation), then update the two existing atomic write helpers to use it, extract `save_batch_result()`, fix the four bug sites in turn, create the `orchestrator_io.py` convention module, update the prompt, and finish with tests. Tasks 2–5 can run in parallel once Task 1 completes; Tasks 6–8 run after their respective dependencies.

## Tasks

### Task 1: Add durable_fsync() and update atomic_write() in common.py
- **Files**: `claude/common.py`
- **What**: Add a `durable_fsync(fd: int) -> None` helper that calls `fcntl.fcntl(fd, fcntl.F_FULLFSYNC)` on macOS and `os.fsync(fd)` elsewhere. Update the existing `atomic_write()` function (lines ~273–312) to call `f.flush()` and `durable_fsync()` on the file descriptor before calling `os.replace()`.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `claude/common.py` lines 273–312 contain `atomic_write()`. It currently uses `tempfile.mkstemp()` + `os.write()` + `os.close()` + `os.replace()` without fsync. Pattern: add `os.write(fd, data)` → `os.flush()`-equivalent → `durable_fsync(fd)` → `os.close(fd)` → `os.replace()`. **Import placement**: `import fcntl` must be inside the `if sys.platform == "darwin":` branch of `durable_fsync` — not at module level. `fcntl` does not exist on non-POSIX platforms (e.g., Windows); a top-level import would break every caller of `common.py` on those platforms.
- **Verification**: `just test` passes. Grep `common.py` for `F_FULLFSYNC` and `durable_fsync` to confirm both are present.
- **Status**: [ ] pending

### Task 2: Update save_state() in state.py to use durable_fsync()
- **Files**: `claude/overnight/state.py`
- **What**: Update `save_state()` (lines 336–376) to import and call `durable_fsync()` from `claude.common` before `os.replace()`. Add `f.flush()`-equivalent call (since save_state uses raw `os.write(fd, ...)`, the fd doesn't have a Python buffer to flush — just call `durable_fsync(fd)` before `os.close(fd)` and `os.replace()`).
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: `claude/overnight/state.py` lines 336–376: `save_state()` uses `tempfile.mkstemp()` + `os.write(fd, payload.encode("utf-8"))` + `os.close(fd)` + `os.replace()`. Insert `durable_fsync(fd)` after `os.write()` and before `os.close()`. Import `durable_fsync` from `claude.common`.
- **Verification**: `just test` passes. Grep `state.py` for `durable_fsync` to confirm it's present.
- **Status**: [ ] pending

### Task 3: Extract save_batch_result() in state.py
- **Files**: `claude/overnight/state.py`
- **What**: Add `save_batch_result(result: BatchResult, path: Path, extra_fields: Optional[dict] = None) -> None` to `state.py`. It serializes the result via `dataclasses.asdict()`, merges `extra_fields` if provided, then writes atomically using the same tempfile + `durable_fsync` + `os.replace` pattern as `save_state()`. Call `path.parent.mkdir(parents=True, exist_ok=True)` before writing.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**: `BatchResult` is defined in `claude/overnight/batch_runner.py`. The function signature: `save_batch_result(result: BatchResult, path: Path, extra_fields: Optional[dict] = None) -> None`. **Circular import guard**: `batch_runner.py` already imports `save_state` from `state.py`, so importing `BatchResult` from `batch_runner.py` into `state.py` would create a circular dependency. Both files already have `from __future__ import annotations` (deferred annotation evaluation). Use a `TYPE_CHECKING` guard: `from typing import TYPE_CHECKING; if TYPE_CHECKING: from claude.overnight.batch_runner import BatchResult`. At runtime, `dataclasses.asdict()` does not need the `BatchResult` type — it works on any dataclass instance. Serialization: convert the dataclass to a dict via `dataclasses.asdict()`, then merge any `extra_fields` dict into that result before JSON-encoding with a trailing newline. Then apply atomic write pattern with `durable_fsync`. Add to `claude/overnight/state.py` near `save_state()`. Export from module (no `__all__` restriction currently).
- **Verification**: `just test` passes. Grep `state.py` for `save_batch_result` to confirm presence. Manually verify function signature matches spec.
- **Status**: [ ] pending

### Task 4: Replace batch results write in batch_runner.py
- **Files**: `claude/overnight/batch_runner.py`
- **What**: Replace `result_path.write_text(...)` at lines ~1956–1963 with `save_batch_result(batch_result, result_path, extra_fields={"throttle_stats": manager.stats})`. Remove the now-redundant `result_dict` construction and the `write_text` call.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: Lines ~1955–1963 in `batch_runner.py`: `result_dict = asdict(batch_result)` → `result_dict["throttle_stats"] = manager.stats` → `result_path.write_text(json.dumps(result_dict, indent=2) + "\n", encoding="utf-8")`. Replace the entire block with one call to `save_batch_result`. Update the existing `save_state` import in `batch_runner.py` to also include `save_batch_result`.
- **Verification**: `just test` passes. Grep `batch_runner.py` for `write_text` — should find zero matches near the result write site. Confirm `save_batch_result` is called with `extra_fields={"throttle_stats": manager.stats}`.
- **Status**: [ ] pending

### Task 5: Add durable_fsync to write_escalation() in deferral.py
- **Files**: `claude/overnight/deferral.py`
- **What**: In `write_escalation()` (lines 355–382), add `f.flush()` and `durable_fsync(f.fileno())` inside the `with open(..., "a")` block after the `f.write(...)` call.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: `write_escalation()` in `claude/overnight/deferral.py` lines 355–382 currently ends with `f.write(json.dumps(record) + "\n")` inside `with open(escalations_path, "a", encoding="utf-8") as f:`. Add `f.flush()` and `durable_fsync(f.fileno())` after the write, before the `with` block exits. Import `durable_fsync` from `claude.common`.
- **Verification**: `just test` passes (TestWriteEscalation in `claude/overnight/tests/test_deferral.py` passes without changes). Grep `deferral.py` for `durable_fsync` confirms it's present.
- **Status**: [ ] pending

### Task 6: Fix recovery_attempts per-feature save in batch_runner.py
- **Files**: `claude/overnight/batch_runner.py`
- **What**: After the `recovery_attempts_map[name] += 1` increment at the test-failure recovery path (~line 1711, inside the `async with lock:` block), immediately load state, update `recovery_attempts` for the feature, and call `save_state()` — all within the same lock scope. Add a code comment noting that `save_state()` is synchronous I/O inside an async lock; this serializes concurrent feature result accumulation but is an accepted tradeoff for typical batch sizes of ~3 features. Also verify at implementation time whether line ~1544 (`result.status != "completed"` branch) increments `recovery_attempts_map[name]` and, if so, whether that branch dispatches a recovery agent — add the same save there only if it's a recovery dispatch point.
- **Depends on**: [2]
- **Complexity**: complex
- **Context**: `batch_runner.py` structure: `async with lock:` block contains multiple branches. Test-failure recovery path: ~line 1711 increments `recovery_attempts_map[name]`; the lock exits at ~line 1714; `recover_test_failure()` is called outside the lock at ~line 1717. Save must happen at ~line 1712, inside the lock, before it exits. Pattern: `load_state(config.overnight_state_path)` → set `state.features[name].recovery_attempts = recovery_attempts_map[name]` → `save_state(state, config.overnight_state_path)`. The `state` object may already be in scope — inspect what's available at that code location. For line ~1544: inspect the `result.status != "completed"` branch to determine if it ends with a return immediately or dispatches a recovery agent.
- **Verification**: `just test` passes. Manual trace: confirm the save call is inside `async with lock:`. Confirm `recovery_attempts` in the persisted state file reflects per-feature increments after a simulated mid-batch interruption (inspect state file after a test run).
- **Status**: [ ] pending

### Task 7: Create orchestrator_io.py wrapper module
- **Files**: `claude/overnight/orchestrator_io.py` (new)
- **What**: Create a thin re-export module that exposes `save_state`, `load_state`, `update_feature_status`, and `write_escalation` as the sanctioned import surface for agent code in the orchestrator prompt. No new logic — re-exports only.
- **Depends on**: [2, 5]
- **Complexity**: simple
- **Context**: `save_state`, `load_state`, `update_feature_status` are exported from `claude.overnight.state`. `write_escalation` is exported from `claude.overnight.deferral`. The module is a plain Python file: re-export these four names. This is a convention module — its purpose is to provide a single audit-point import, not runtime enforcement. Add a module-level docstring noting this.
- **Verification**: `python -c "from claude.overnight.orchestrator_io import save_state, load_state, update_feature_status, write_escalation; print('ok')"` runs without error. Grep `orchestrator_io.py` for all four function names.
- **Status**: [ ] pending

### Task 8: Update orchestrator-round.md prompt
- **Files**: `claude/overnight/prompts/orchestrator-round.md`
- **What**: Replace all raw `write_text(json.dumps(...)` and `Path(...).write_text(` calls for state files with calls to `save_state()` and `update_feature_status()`. Replace raw `open(..., "a")` escalation appends with `write_escalation()`. All imports in pseudocode should reference `orchestrator_io` (e.g., `from claude.overnight.orchestrator_io import save_state, update_feature_status, write_escalation`).
- **Depends on**: [7]
- **Complexity**: simple
- **Context**: `claude/overnight/prompts/orchestrator-round.md` has write_text calls at Steps 0d, 3c, and 4a for `overnight-state.json`, and escalation appends at lines 101, 128, 144. For state writes: replace pseudocode with `save_state(state, state_path)` calls, using `update_feature_status()` for feature status mutations before saving. For escalation appends: replace `open(...)` blocks with `write_escalation(entry, escalations_path)` calls.
- **Verification**: Grep `orchestrator-round.md` for `write_text` — zero matches. Grep for `orchestrator_io` — at least one import statement present. Grep for `Path(.*).write_text` — zero matches for state file writes.
- **Status**: [ ] pending

### Task 9: Add and update tests
- **Files**: `claude/overnight/tests/test_overnight_state.py`, `claude/overnight/tests/test_deferral.py`, `claude/overnight/tests/test_map_results.py`, `claude/overnight/tests/test_lead_unit.py`
- **What**: (a) Add a test for `save_batch_result()` verifying the written JSON contains all BatchResult fields and `throttle_stats` from `extra_fields`. (b) Add a test in `test_lead_unit.py` that exercises the recovery dispatch path and asserts `recovery_attempts` is incremented and persisted in the state file inside the lock scope — this is the automated acceptance criterion for Task 6. (c) Confirm `TestWriteEscalation` passes without modification. Run `just test` to confirm all existing tests pass.
- **Depends on**: [3, 4, 5, 6]
- **Complexity**: complex
- **Context**: New test for `save_batch_result`: create a `BatchResult` instance, write to a temp path with `extra_fields={"throttle_stats": {"total": 0}}`, read back and assert field presence. For Task 6 acceptance: add a test to `test_lead_unit.py` that triggers the test-failure recovery gate (simulates a feature result with test failure + recovery gate open), then reads the state file and asserts `recovery_attempts` was incremented and saved for that feature. The existing `TestRecoveryGate` mocks `save_state` away — either extend it to verify the real save occurs, or add a new test that does not mock `save_state`. `test_deferral.py` has `TestWriteEscalation` — run as-is; expect pass without changes. Check `test_map_results.py` for tests that mock the batch results file format — update if needed.
- **Verification**: `just test` passes with 0 failures. New `save_batch_result` test is present. New or updated recovery dispatch test in `test_lead_unit.py` asserts `recovery_attempts` is persisted per-feature. No tests were silently removed.
- **Status**: [ ] pending

## Verification Strategy

After all tasks complete: run `just test` — all tests must pass. Then do a final grep audit:
- `grep -r "write_text.*json.dumps" claude/overnight/` — should return 0 matches at write sites for state/batch files
- `grep -r "durable_fsync" claude/` — should show presence in common.py, state.py, deferral.py
- `grep "orchestrator_io" claude/overnight/prompts/orchestrator-round.md` — should show import
- Inspect `lifecycle/overnight-state.json` after a test run to confirm recovery_attempts are persisted per-feature (if a test exercises recovery dispatch)
