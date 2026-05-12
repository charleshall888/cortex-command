# Review: Fix next_question_id() race condition in deferral.py

**Reviewer**: Claude (automated)
**Cycle**: 1
**Date**: 2026-04-03

## Stage 1: Spec Compliance

### R1: Fix four TypeError call sites — PASS

All four `_next_escalation_n()` call sites now pass three required arguments (`feature`, `config.batch_id`, `escalations_path`). The AST acceptance check produces no output (no calls with fewer than 3 args). Each call site also correctly constructs `escalations_path = Path("lifecycle/escalations.jsonl")` in the immediately preceding line, keeping the path consistent with `write_escalation()`'s default.

### R2: Atomic deferral file creation via O_EXCL — PASS

`write_deferral()` now uses `os.open(str(dest), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)` in a retry loop (up to `_max_attempts=100`). On `FileExistsError`, the loop increments the candidate ID and retries. Content is written directly to the O_EXCL file descriptor with no temp-file indirection, matching the spec's resolved decision. The error-handling path correctly closes the fd and unlinks the partial file on write failure. `grep -c 'O_EXCL' deferral.py` returns 5 (>= 1).

### R3: Document escalation race as theoretical — PASS

A thorough TOCTOU comment is added to `_next_escalation_n()` documenting: (1) the theoretical race, (2) why it is safe under the current architecture (single coroutine per feature), (3) why O_EXCL is inapplicable (JSONL append pattern), and (4) what would need to change if the dispatch model changes. `grep -c 'TOCTOU' deferral.py` returns 2 (>= 1).

### R4: Existing tests pass — PASS

`just test` exits 0 with all 3 test suites passing (test-pipeline, test-overnight, tests).

### R5: Correct misleading docstring — PASS

The old `next_question_id()` docstring claiming "Thread-safe via filesystem -- no in-memory counters" has been replaced with an accurate description: the function "Return[s] a hint for the next available question ID" and "actual uniqueness is enforced by `O_CREAT | O_EXCL` in `write_deferral`." `grep -c 'Thread-safe via filesystem' deferral.py` returns 0.

## Stage 2: Code Quality

### Naming conventions

Consistent with project patterns. The `_max_attempts` parameter uses underscore prefix to signal it is a testing/internal knob, not public API. Variable names (`candidate_id`, `qid`, `fd`, `dest`) are clear and conventional.

### Error handling

The O_EXCL write path has correct cleanup: on `BaseException` during `os.write`/`os.close`, the fd is closed (ignoring `OSError`) and the partial file is unlinked (ignoring `OSError`), then the exception re-raises. This prevents leaked file descriptors and orphaned partial files. The `OSError` raise after exhausting `_max_attempts` provides a descriptive message.

### Test coverage

The spec's acceptance criteria are all automated checks (AST parsing, grep counts, `just test`). All pass. No new unit tests were added for the O_EXCL retry loop or the `_max_attempts` exhaustion path, but the spec did not require new tests beyond R4 ("existing tests pass").

### Pattern consistency

The O_EXCL pattern is appropriate for this use case and avoids the `fcntl.flock` / lockfile patterns that the pipeline's architectural constraints prohibit. The `_max_attempts` parameter follows the same underscore-prefix-with-default pattern used elsewhere in the codebase for testing hooks.

### Note on commit scope

Commit `dbca281` ("Fix four TypeError call sites in _next_escalation_n") also includes a refactor of `_read_spec_excerpt` into `_get_spec_path` / `_read_spec_content`, which belongs to a separate feature (replace-spec-dump-with-jit-loading). This does not affect correctness of the deferral fix, but is a commit hygiene observation -- the two changes could have been separate commits.

## Requirements Drift

**State**: none
**Findings**:
- None
**Update needed**: None

The deferral system acceptance criterion ("Deferral files are written atomically") is satisfied by O_EXCL's atomic filename claiming. The non-functional requirement "All session state writes use tempfile + `os.replace()`" applies to session state files (`overnight-state.json`), not deferral files, so the mechanism change does not create drift.

## Verdict

```json
{
  "verdict": "APPROVED",
  "cycle": 1,
  "issues": [],
  "requirements_drift": "none"
}
```
