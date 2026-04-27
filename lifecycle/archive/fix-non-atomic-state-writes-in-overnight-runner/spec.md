# Specification: Fix non-atomic state writes in overnight runner

> Epic reference: `research/harness-design-long-running-apps/research.md` covers the broader overnight harness design; this spec addresses only the four reliability gaps and the underlying durability posture of the atomic write helpers.

## Problem Statement

The overnight runner executes unattended. Four write sites can silently corrupt state on crash: (1) the orchestrator prompt instructs raw `write_text` for `overnight-state.json`, causing `JSONDecodeError` on every subsequent read if the process is killed mid-write; (2) `batch_runner.py` writes `batch-{N}-results.json` non-atomically, causing `map_results.py` to mark every feature as failed including ones that merged successfully; (3) `write_escalation()` appends to `escalations.jsonl` without fsync, silently losing escalations that should appear in the morning report; (4) `recovery_attempts` is saved end-of-batch, so a mid-batch kill causes a repair agent to be re-dispatched for a feature that already consumed its budget. Additionally, the existing `save_state()` and `atomic_write()` helpers are atomic (tempfile + os.replace) but not durable — they omit fsync, so a power-loss crash after `os.replace()` but before the OS write-back cache flushes to disk can still lose data. Since the runner is unattended overnight on a battery-powered macOS machine, this is a real failure scenario.

## Requirements

1. **Bug 1 — Orchestrator prompt atomic writes**: Create `claude/overnight/orchestrator_io.py` that re-exports `save_state()`, `load_state()`, `update_feature_status()`, and `write_escalation()` as the sanctioned API for agent code in the orchestrator. Update `orchestrator-round.md` to import from `orchestrator_io` and replace all pseudocode `write_text` calls with `save_state()` / `update_feature_status()` calls. Note: `orchestrator_io.py` is a convention boundary — it documents the intended import surface but does not prevent the agent from importing `state.py` directly (the agent has full Python import access). Its value is as an audit point and intent signal, not a runtime guard. Acceptance: no raw `write_text(json.dumps(...)` or `Path(...).write_text(` calls remain in `orchestrator-round.md` for state files.

2. **Bug 2 — Batch results atomic write**: Extract `save_batch_result(result: BatchResult, path: Path, extra_fields: Optional[dict] = None) -> None` in `claude/overnight/state.py` that writes using the atomic tempfile + os.replace pattern with `durable_fsync` (see Requirement 5). If `extra_fields` is provided, merge it into the serialized dict before writing. Replace the `result_path.write_text(...)` call in `batch_runner.py` (~lines 1956–1963) with `save_batch_result(result, result_path, extra_fields={"throttle_stats": manager.stats})`. Acceptance: (a) the write at that call site uses tempfile + os.replace + `durable_fsync`; (b) `throttle_stats` is present in the written JSON with the same value as the current implementation.

3. **Bug 3 — escalations.jsonl fsync**: In `write_escalation()` in `deferral.py`, add `f.flush()` followed by `durable_fsync(f.fileno())` (see Requirement 5) inside the `with open(..., "a")` block, after the `f.write()` call. Acceptance: `TestWriteEscalation` still passes; the function now calls flush and fsync before returning.

4. **Bug 4 — recovery_attempts per-feature save**: In `batch_runner.py`, when the test-failure recovery path is taken (currently the `async with lock:` block around line 1711 where `recovery_attempts_map[name]` is incremented before the lock is released and `recover_test_failure()` is dispatched outside the lock), add `load_state()` → update `recovery_attempts` for the feature → `save_state()` immediately after the increment, inside the lock scope. Note: `save_state()` is synchronous I/O; calling it inside an async lock will serialize concurrent feature result accumulation around each disk write. This is an accepted tradeoff for a batch size of ~3 features — flag it in a code comment. Separately, verify at implementation time whether line 1544 (`result.status != "completed"` early-return branch) also increments `recovery_attempts` and whether a save is needed there; if that branch does not dispatch a recovery agent, no save is needed. Acceptance: if the process is killed between two test-failure recovery dispatches in the same batch, the first feature's `recovery_attempts` increment is present in the persisted state when the session is resumed.

5. **Full durability for atomic write helpers**: Add a `durable_fsync(fd: int) -> None` helper in `claude/overnight/state.py` (or `claude/common.py`) that calls `fcntl.fcntl(fd, fcntl.F_FULLFSYNC)` on macOS and `os.fsync(fd)` elsewhere. Update `save_state()` and `atomic_write()` to call `f.flush()` and `durable_fsync()` before `os.replace()`. Acceptance: both functions call `durable_fsync` before the rename on all platforms.

6. **No schema changes**: The `OvernightState`, `OvernightFeatureStatus`, and `BatchResult` dataclass schemas are unchanged. No new fields are added to dataclasses.

## Non-Requirements

- Do not fix the `next_question_id()` race in `deferral.py` — this is a pre-existing concurrency bug unrelated to the atomic write patterns; create a separate backlog item.
- Do not add tests that verify the orchestrator agent follows prompt instructions — this is non-deterministic and untestable.
- Do not change `map_results.py`'s `_handle_missing_results()` fallback behavior — it already handles missing/corrupt batch results gracefully.
- Do not change any state schema or serialization format.
- Do not add directory fsync after `os.replace()` — the file itself is safe; directory metadata durability is an accepted tradeoff at this complexity level.

## Edge Cases

- **throttle_stats is caller-provided**: `save_batch_result()` receives `extra_fields` from the call site. If the call site passes `None`, no extra fields are written. The function must not assume any specific fields in `extra_fields` — it merges whatever is given into the serialized dict.
- **First-time file creation**: When `batch-{N}-results.json` doesn't yet exist (first write), `save_batch_result()` should handle `FileNotFoundError` from `os.stat()` gracefully if permission-transfer is implemented — the permission transfer step should skip if the target doesn't exist yet.
- **Directory doesn't exist**: Both `save_batch_result()` and the updated escalation path must call `path.parent.mkdir(parents=True, exist_ok=True)` before writing, consistent with `save_state()`.
- **F_FULLFSYNC not available on non-macOS**: `durable_fsync` must check `sys.platform == "darwin"` and fall back to `os.fsync()` elsewhere. On Linux (if the runner ever runs there), `os.fsync()` is sufficient.
- **Crash between recovery dispatch and recovery_attempts save (Bug 4)**: The load→increment→save for Bug 4 must be structured so that a crash anywhere in the sequence leaves the on-disk state either with the old value or the new value — never corrupted. Using `save_state()` (atomic tempfile+replace with durable_fsync) satisfies this.
- **Orchestrator prompt runs in an AI agent context**: The `orchestrator_io.py` module must be importable from the Python environment that the agent uses. It must not import anything that isn't already available in that environment.

## Technical Constraints

- `durable_fsync` placement: can live in `claude/overnight/state.py` (alongside `save_state`) or `claude/common.py`. Prefer `state.py` to keep the atomic write pattern fully self-contained in one module. `common.py` is acceptable if other modules need it.
- `orchestrator_io.py` is a thin re-export module — no new logic. It imports and re-exports functions from `state.py` and `deferral.py`. It does not duplicate implementations.
- `save_batch_result()` lives in `state.py` alongside `save_state()`. It takes a `BatchResult`, a `Path`, and an optional `extra_fields: Optional[dict] = None`. It serializes the result via `asdict()`, merges `extra_fields` if present, then writes atomically with `durable_fsync`.
- All existing tests must pass after these changes (`just test`).
- The atomic write helpers must maintain the same exception propagation behavior — callers that catch exceptions from `save_state()` or `write_escalation()` must not be silently affected by the fsync additions.

## Open Decisions

- Whether `durable_fsync` should also be applied to `write_deferral()` in `deferral.py` (which already uses tempfile+replace but also omits fsync). The scope as stated covers `save_state()`, `atomic_write()`, `save_batch_result()`, and `write_escalation()`. Deferral writes are lower-stakes than escalation writes (they're human-reviewed at morning, not relied on for session continuity), but consistency argues for applying the same posture. Resolve at implementation time: if the pattern is the same function call, add it; if it requires separate judgment, leave for a follow-up.
