# Research: Fix next_question_id() race condition in deferral.py

## Codebase Analysis

### Target Functions

**`next_question_id()`** (`deferral.py:90–110`): Glob-scans `deferred_dir` for `{feature}-q*.md`, extracts max numeric suffix via regex, returns `max_id + 1`. No synchronization. Docstring claims "Thread-safe via filesystem — no in-memory counters" which is incorrect for async concurrency — the glob→compute→write sequence is a classic TOCTOU race.

**`_next_escalation_n()`** (`deferral.py:389–416`): Reads `escalations.jsonl`, counts entries matching `feature` + `round`, returns `count + 1`. Same TOCTOU pattern — two concurrent readers see the same count and produce the same ID.

### Actual Race Exposure

The race is **theoretical in the current architecture**. Each feature name maps to exactly one `execute_feature()` coroutine in the outer `asyncio.gather` at `batch_runner.py:1914`. Since `next_question_id()` scopes its glob to `{feature}-q*.md`, two different features deferring concurrently produce differently-named files (`feature_a-q001.md` vs `feature_b-q001.md`) — no collision. For a collision to occur, the same feature name would need concurrent `execute_feature()` calls, which the current dispatch model prevents.

Similarly, `_next_escalation_n()` filters by feature+round, so cross-feature concurrency doesn't cause collisions.

The race becomes real if the dispatch model ever allows concurrent execution of the same feature (e.g., retry + new execution overlapping).

### Active Bug: TypeError Call Sites

Four call sites invoke `_next_escalation_n(feature)` with **one argument** instead of the required three `(feature, round, escalations_path)`:

| Line | Location | Status |
|------|----------|--------|
| `batch_runner.py:707` | `execute_feature()` conflict recovery budget-exhausted | **TypeError at runtime** |
| `batch_runner.py:758` | `execute_feature()` repair-agent deferral | **TypeError at runtime** |
| `batch_runner.py:1326` | `_apply_feature_result()` CI-blocking deferral | **TypeError at runtime** |
| `batch_runner.py:1645` | `_accumulate_result()` CI-blocking deferral | **TypeError at runtime** |

Only `batch_runner.py:951–953` calls `_next_escalation_n` correctly with all three arguments. The broken call sites will crash before any race can occur — but they represent four broken deferral paths that silently fail (caught by `asyncio.gather(return_exceptions=True)`).

### Lock-Free Constraint Scope

The lock-free architectural constraint (`requirements/pipeline.md:94,100`) is explicitly about **session state file reads** — justified by "the forward-only phase transition model ensures re-reading a new state is safe." This justification does not apply to ID generation, where stale reads produce duplicates, not safely-forward-compatible results.

The codebase already uses `asyncio.Lock()` in two places:
- `batch_runner.py:1515`: guards `_accumulate_result`
- `throttle.py:119`: `ConcurrencyManager._overflow_lock`

In-process `asyncio.Lock` is consistent with the architectural constraint.

### Existing Concurrency Patterns

- **Atomic writes**: `tempfile + os.replace()` for state files (standard pattern)
- **asyncio.Lock**: Already used for serializing result accumulation
- **Per-feature isolation**: Deferral files are scoped by feature name in the glob pattern
- **Sequential post-gather processing**: Task results within a feature are processed in a sequential `for item in results:` loop after the inner `asyncio.gather` completes — no async yield between `next_question_id()` and `write_deferral()`

### Consumer Requirements

Deferral file consumers (`read_deferrals()`, `report.py:844–855`, `summarize_deferrals()`) parse `question_id` as an integer and format with `:03d`. Consumers tolerate gaps in IDs but require integer values. UUIDs would break `report.py:855`.

### Fix Approaches

**Option A — `O_CREAT | O_EXCL` loop (lock-free)**: Replace the scan→compute→write pattern with an exclusive-create loop in `write_deferral()`. Start from 1 (or the scanned max), attempt `os.open(path, O_CREAT | O_EXCL | O_WRONLY)`, increment on `FileExistsError`. Eliminates the TOCTOU entirely without any lock. Fits the file-based architecture cleanly.

**Option B — `asyncio.Lock` in `write_deferral()`**: Wrap the `next_question_id()` call and subsequent file write in an `asyncio.Lock`. Requires making `write_deferral` async or hoisting the lock to call sites. Consistent with existing patterns (`batch_runner.py:1515`) but adds coupling between scan and write that currently doesn't exist.

**Option C — Monotonic counter file**: Persist a counter in e.g. `deferred/.next_id`. Read, increment, write atomically. Adds state outside the deferral files themselves — more moving parts for questionable benefit over O_EXCL.

## Open Questions

- Should the four broken `_next_escalation_n()` TypeError call sites be fixed as part of this ticket, or tracked separately? They are in the same functions and the same concurrency context, but fixing argument counts is a separate bug from fixing the race pattern.
