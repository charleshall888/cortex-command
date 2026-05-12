# Review: morning-report-surface-failure-root-cause-inline

## Stage 1: Spec Compliance

### Requirement 1: No-commit guard classification
**Rating**: PASS

- **Stale feature**: `_classify_no_commit()` uses `git rev-list {branch}..{base_branch} --count` and when count > 0 returns a string containing "already merged". Satisfies the spec's "already implemented" or "already merged" acceptance criterion.
- **No changes produced**: When count = 0, returns a string containing "no changes produced". Satisfies acceptance criterion.
- **Fallback**: On returncode != 0, timeout, OSError, or any other exception, returns `f"completed with no new commits (branch: {branch})"`. Contains "completed with no new commits" with the branch name. Does not mention log files. Satisfies acceptance criterion.

### Requirement 2: Classification helper contract
**Rating**: PASS

- **Inputs**: Function signature is `_classify_no_commit(feature: str, branch: str, base_branch: str) -> str`. Runs its own `git rev-list` subprocess -- does not receive pre-computed `_get_changed_files()` output.
- **Error handling**: Outer `except (subprocess.TimeoutExpired, OSError, Exception)` catches all exceptions and returns the fallback. Additionally, `returncode != 0` returns fallback before parsing stdout, preventing `int()` conversion errors on empty/invalid output. The caller also validates `if not error:` and substitutes a fallback string if the return is somehow falsy. The no-commit guard cannot raise or produce an empty error string from classification logic.
- **Timeout**: Uses `timeout=30`, consistent with `_get_changed_files()` at line 402.
- **Return value**: Every code path returns a non-empty string (fallback string, stale string, or no-changes string).

### Requirement 3: Enhanced `_suggest_next_step()` patterns
**Rating**: PASS

- `"already implemented"` or `"already merged"` triggers: "Verify prior merge on main, close backlog item if complete"
- `"no changes produced"` triggers: "Check agent output -- agent ran but produced no diff"
- Both are distinct from the default suggestion and from existing patterns (merge conflict, test failure, circuit breaker).
- Existing patterns are unchanged -- the new patterns are inserted before the default return, after the circuit breaker check.

### Requirement 4: Coupling test
**Rating**: PASS

- `tests/test_no_commit_classification.py` imports both `_classify_no_commit` and `_suggest_next_step`.
- Tests four scenarios: stale branch (count=5), fresh branch (count=0), invalid ref (returncode=128), and subprocess timeout.
- For stale and fresh branches: asserts the classifier output contains the expected substring AND `_suggest_next_step(result)` returns a non-default suggestion.
- For invalid ref: asserts fallback is non-empty, contains branch name, AND `_suggest_next_step(result)` equals the default suggestion.
- For timeout: asserts fallback is non-empty and contains branch name.
- All 4 tests pass.

### Requirement 5: Preserve existing error strings
**Rating**: PASS

- Only the no-commit guard error string (lines 1279-1281) was replaced. The old string `"completed with no new commits -- check pipeline-events.log task_output and task_git_state events"` no longer appears in the file.
- Error strings for plan parse error, merge failure, task failure, budget exhausted, and circuit breaker are all unchanged (verified by grep).
- `_suggest_next_step()` changes only add new patterns -- the existing merge conflict, test failure, and circuit breaker patterns are untouched.

### Requirement 6: No schema changes
**Rating**: PASS

- `state.py` and `map_results.py` have zero diff in these commits. No new fields added. `OvernightFeatureStatus.error` remains `Optional[str]`.

## Stage 2: Code Quality

### Naming conventions
The function name `_classify_no_commit` follows the existing underscore-prefixed private helper pattern (`_get_changed_files`, `_read_exit_report`, `_suggest_next_step`). Parameters use the same naming as the surrounding code (`feature`, `branch`, `base_branch`). The test file name `test_no_commit_classification.py` follows the `test_*.py` pattern in `tests/`.

### Error handling
Appropriate for the context. The broad `except (subprocess.TimeoutExpired, OSError, Exception)` is intentionally defensive per the spec requirement that classification must never raise. The caller-side `if not error:` guard is a belt-and-suspenders check consistent with the spec's edge case guidance. The `timeout=30` matches the existing `_get_changed_files()` pattern.

### Test coverage
All four plan verification steps are covered:
- Task 1 verification: `_classify_no_commit` exists as a function (confirmed by import and test execution).
- Task 2 verification: `"check pipeline-events.log"` substring is absent from `batch_runner.py` (confirmed by grep returning 0 matches).
- Task 3 verification: `"already merged"`, `"already implemented"`, and `"no changes produced"` all appear in `report.py` (confirmed by reading the function).
- Task 4 verification: All 4 tests pass.

### Pattern consistency
- Subprocess call uses the same `capture_output=True, text=True, timeout=30` pattern as `_get_changed_files()`.
- Function placement (after `_get_changed_files()`, before exit-report utilities) is logical.
- The `_suggest_next_step()` additions follow the existing `if "keyword" in error_lower:` pattern with consistent return style.
- Test uses `unittest.mock.patch` and `MagicMock` consistent with other tests in the repo.

### Minor observations
- The `except` clause lists `(subprocess.TimeoutExpired, OSError, Exception)` -- `Exception` already covers `OSError`, making `OSError` redundant. This is harmless and arguably improves readability by documenting the expected exception types.
- The `feature` parameter is accepted but unused in the function body (only `branch` and `base_branch` are used in the git command and return strings). This is consistent with the spec which requires the parameter for the contract but the current implementation doesn't need it for the rev-list query. Leaving it in the signature is appropriate for future extensibility.

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

The implementation adds a classification helper and enhanced suggestion patterns within the existing `OvernightFeatureStatus.error` field and `_suggest_next_step()` function. This is consistent with the pipeline requirements' feature execution and failure handling section, which specifies that feature statuses include `paused` for recoverable errors and that failures are surfaced in the morning report. The project-level requirement that "morning is strategic review -- not debugging sessions" is better served by this change. No new behavioral contracts are introduced that would require requirements updates.

## Verdict

```json
{
  "verdict": "APPROVED",
  "cycle": 1,
  "issues": [],
  "requirements_drift": "none"
}
```
