# Specification: Fix next_question_id() race condition in deferral.py

## Problem Statement

`next_question_id()` and `_next_escalation_n()` in `claude/overnight/deferral.py` use a non-atomic scan-and-increment pattern to generate IDs. Under concurrent `asyncio.gather` execution in `batch_runner.py`, two coroutines could read the same max ID and produce duplicate filenames — causing one deferral file to silently overwrite the other via `os.replace`. Additionally, four call sites invoke `_next_escalation_n()` with the wrong argument count, causing TypeError crashes on those code paths. Both issues affect overnight runner reliability — the TypeErrors make four deferral paths completely non-functional, and the race (theoretical in the current single-coroutine-per-feature dispatch model) risks silent data loss if the dispatch model changes.

## Requirements

### Must-have

1. **Fix four TypeError call sites**: The four broken `_next_escalation_n()` calls at `batch_runner.py` lines 707, 758, 1326, and 1645 must pass all three required arguments `(feature, round, escalations_path)`.
   - Acceptance: `python -c "import ast; tree = ast.parse(open('claude/overnight/batch_runner.py').read()); [print(n.lineno) for n in ast.walk(tree) if isinstance(n, ast.Call) and hasattr(n.func, 'id') and n.func.id == '_next_escalation_n' and len(n.args) < 3]"` produces no output

2. **Atomic deferral file creation via O_EXCL**: `write_deferral()` must use `os.open(path, O_CREAT | O_EXCL | O_WRONLY)` with a retry loop to create deferral files, eliminating the TOCTOU race between ID scanning and file creation. Write content directly to the O_EXCL file descriptor — no temp-file indirection needed (see Resolved Decisions).
   - Acceptance: `grep -c 'O_EXCL' claude/overnight/deferral.py` >= 1

3. **Document escalation race as theoretical**: Add a code comment to `_next_escalation_n()` documenting the TOCTOU exposure and why it is safe under the current architecture (single coroutine per feature, ID scoped by feature+round). The escalation write path appends to a shared JSONL file — O_EXCL is inapplicable to JSONL appends.
   - Acceptance: `grep -c 'TOCTOU' claude/overnight/deferral.py` >= 1

4. **Existing tests pass**: All existing deferral tests must continue to pass after changes.
   - Acceptance: `just test` exits 0

### Should-have

5. **Correct misleading docstring**: `next_question_id()` docstring at `deferral.py:97` claims "Thread-safe via filesystem — no in-memory counters." This should be updated to accurately describe the actual safety mechanism.
   - Acceptance: `grep -c 'Thread-safe via filesystem' claude/overnight/deferral.py` = 0

## Non-Requirements

- No changes to the deferral file format (`{feature}-q{NNN}.md` with 3-digit zero-padded integers)
- No changes to the deferral file content/markdown structure
- No restructuring of the deferral system or `write_deferral` API signature
- No conversion of synchronous functions to async
- No filesystem-level locking (fcntl.flock, lockfiles) — consistent with the pipeline's lock-free architectural constraint for state files
- No fix for the escalation ID race itself — the race is theoretical (same feature+round concurrent execution is architecturally prevented) and the JSONL append pattern makes O_EXCL inapplicable. Documented rather than fixed.

## Edge Cases

- **Empty deferred directory**: O_EXCL loop starts from ID 1; first `os.open` with O_EXCL succeeds immediately. No behavioral change from current code.
- **High contention (many concurrent deferrals)**: The O_EXCL loop retries with incremented IDs on `FileExistsError`. With a reasonable retry cap (e.g., 100 attempts), this handles far more concurrency than the overnight runner produces.
- **Race is currently theoretical**: In the current architecture, each feature name maps to exactly one `execute_feature()` coroutine, and the glob is feature-name-scoped. Cross-feature deferrals never collide. The fix is still warranted because (a) the docstring falsely claims safety, (b) the pattern is unsafe if the dispatch model changes, and (c) O_EXCL is simpler than the current scan-then-replace pattern.
- **Partial file on crash with O_EXCL**: If the process crashes after O_EXCL file creation but before content is fully written, a partial `.md` file remains on disk. `read_deferrals()` (`deferral.py:302-309`) handles this gracefully — `_parse_deferral_file` raises `ValueError` on malformed content, caught by the caller with `warnings.warn()` and `continue`. Partial files are safely skipped, not crash-inducing.
- **`_next_escalation_n` TypeError paths**: These four paths currently crash before any race can occur. Fixing the argument count makes them functional. The escalation race is theoretical and documented, not fixed.

## Technical Constraints

- **IDs must remain non-negative integers**: Consumers (`read_deferrals()`, `report.py:855`) parse `question_id` as int and format with `:03d`. UUIDs or string IDs would break consumers.
- **ID gaps are tolerable**: Consumers sort by ID but don't require sequential IDs (tested by research reviewing `read_deferrals` and `summarize_deferrals`).
- **Lock-free architectural constraint**: `requirements/pipeline.md` states "State file reads are not protected by locks by design." This applies to session state files specifically (justified by forward-only phase transitions). The O_EXCL approach avoids needing any lock.
- **Escalation writes are JSONL appends**: `write_escalation()` (`deferral.py:383`) opens `escalations_path` in append mode. O_EXCL cannot be applied to JSONL append patterns — it only works for per-ID file creation. This is why the escalation race is documented rather than fixed.
- **`round` and `escalations_path` availability at call sites**: The four broken call sites need access to the current round number and escalation file path. These values must be threaded through from the calling context — verify they are available in scope at each call site.
- **Implementation order**: Fix TypeErrors (R1) before adding O_EXCL (R2). The TypeError fix is a trivial argument-passing correction; the O_EXCL change restructures the write path. Decoupling ensures the high-confidence fix is not gated on the more complex change.

## Resolved Decisions

- **O_EXCL directly on destination path**: Use `os.open(dest, O_CREAT | O_EXCL | O_WRONLY)` and write content directly — no temp-file indirection. The partial file concern is mitigated by `read_deferrals()`'s error handling, which skips malformed files with `warnings.warn()`. This is simpler than alternatives (temp-file + `os.link`, or O_EXCL "claim" + rename) and the current code already lacks `durable_fsync` on deferrals, so crash-safety is not regressed.
