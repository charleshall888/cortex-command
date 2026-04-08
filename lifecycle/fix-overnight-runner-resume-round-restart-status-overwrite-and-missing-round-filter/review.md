# Review: fix-overnight-runner-resume-round-restart-status-overwrite-and-missing-round-filter

## Stage 1: Spec Compliance

### Requirement 1: ROUND initialized from state on resume
**Rating: PASS**

Line 519 of `runner.sh`:
```bash
ROUND=$(STATE_PATH="$STATE_PATH" python3 -c "import json, os; print(json.load(open(os.environ['STATE_PATH']))['current_round'])")
```
ROUND is read from `state['current_round']`, not hardcoded. `grep -c '^ROUND=1$'` returns 0 as required.

### Requirement 2: Skip already-mapped rounds on resume
**Rating: PASS**

Lines 593-604 of `runner.sh` check for `${SESSION_DIR}/batch-${ROUND}-results.json` before each round. If the file exists, the round is skipped and ROUND is incremented. `grep -c 'batch-.*results.json'` returns 4 (>= 1), with the primary check at line 593.

### Requirement 3: Round filter in orchestrator-round.md
**Rating: PASS**

Section 1 of `orchestrator-round.md` (lines 162-175) contains a Python code block that filters features by `round_assigned <= current_round`, with paused features always included. Uses `{round_number}` template variable for substitution. `grep -c 'round_assigned'` returns 2 (one in the code block at line 169, one in the explanation at line 173).

### Requirement 4: Terminal-status guard in _map_results_to_state()
**Rating: PASS**

`map_results.py` has `_TERMINAL_STATUSES` guards at:
- Line 32: constant definition
- Line 103: `features_paused` loop guard
- Line 114: `features_deferred` loop guard
- Line 125: `features_failed` loop guard
- Line 169: `_handle_missing_results` guard (pre-existing)

Total count: 5 (>= 4). `features_merged` (line 90-95) is correctly unguarded per the non-requirements.

### Requirement 5: Unit tests for terminal-status guard
**Rating: PASS**

`tests/test_map_results.py` contains all four required test functions:
- `test_paused_result_does_not_overwrite_merged`
- `test_failed_result_does_not_overwrite_merged`
- `test_deferred_result_does_not_overwrite_merged`
- `test_merged_result_overwrites_failed`

Each test writes a state file with the initial status, calls `_map_results_to_state`, and asserts the expected final status.

### Requirement 6: MERGED_BEFORE per-round capture
**Rating: PASS**

No `MERGED_BEFORE=0` pre-loop initialization exists (`grep -c 'MERGED_BEFORE=0'` returns 0). Instead, `MERGED_BEFORE` is captured inside the loop at lines 607-613, after the batch-results skip check and before the orchestrator spawn. Line 794 provides the round-to-round continuity via `MERGED_BEFORE=$MERGED_AFTER`.

### Requirement 7: Stall check uses -le 0
**Rating: PASS**

Line 777: `if [[ $MERGED_THIS_ROUND -le 0 ]]; then`. `grep -c 'MERGED_THIS_ROUND -le 0'` returns 1.

### Requirement 8: count_pending() includes paused
**Rating: PASS**

Line 360 of `runner.sh`:
```python
count = sum(1 for f in features.values() if f.get('status') in ('pending', 'running', 'paused'))
```
The `REMAINING_PENDING` check at line 783 also includes `'paused'`:
```python
print(sum(1 for f in features.values() if f.get('status') in ('pending', 'paused')))
```
`grep -c 'pending.*running.*paused|paused.*pending.*running'` returns 1 (the count_pending function at line 360).

### Requirement 9 (Should-Have): Runner resume tests
**Rating: PASS**

`tests/test_runner_resume.py` exists with three tests:
- `test_count_pending_includes_paused`: verifies count_pending returns >= 1 for a paused-only state
- `test_count_pending_zero_for_merged`: verifies count_pending returns 0 for merged-only state
- `test_runner_sh_count_pending_contains_paused`: structural assertion that runner.sh's count_pending function body contains 'paused'

The structural assertion at test line 74-91 is a good guard against test/production divergence.

## Stage 2: Code Quality

### Naming conventions
Consistent with existing project patterns. `_TERMINAL_STATUSES` follows the existing constant naming convention (private, uppercase). Test names follow the `test_<behavior>` convention used elsewhere. `count_pending()` follows the existing helper naming convention in runner.sh.

### Error handling
Appropriate for context. The terminal-status guards use `continue` to skip, which is the simplest correct approach. The batch-results skip path (line 593-604) updates `state.current_round` before advancing, maintaining state consistency. The `mktemp -p "${TMPDIR:-/tmp}"` fix at line 521 ensures sandbox compatibility.

### Test coverage
All four required test scenarios are covered in `test_map_results.py`. The `test_runner_resume.py` adds coverage for the count_pending behavior change and includes the structural assertion that verifies the production code matches the test's assumptions. One minor note: the tests do not cover the edge case where a feature appears in both `features_merged` and `features_paused` in the same results dict (spec edge case), but this is an implicit consequence of processing order and the guard, not a separate code path requiring its own test.

### Pattern consistency
- Guards in `_map_results_to_state()` follow the same pattern as the pre-existing guard in `_handle_missing_results()`: check `fs.status in _TERMINAL_STATUSES`, then `continue`.
- The round filter in `orchestrator-round.md` uses Python code-block style matching the existing section 2a dependency gate pattern.
- Test files use `pytest` with `tmp_path` fixture, consistent with other tests in the project.
- The batch-results skip check writes state via `load_state`/`save_state` (atomic), consistent with all other state writes in runner.sh.

## Requirements Drift

**State: none**

The implementation matches all stated requirements:

- **pipeline.md "Paused sessions resume to the phase they paused from"**: The ROUND-from-state and batch-results-skip fixes restore correct resume behavior, aligning with this requirement.
- **pipeline.md "paused means recoverable error -- paused features auto-retry when session resumes"**: The `count_pending()` paused inclusion ensures paused features are not prematurely dropped from the dispatch loop.
- **pipeline.md "Features already at merged are skipped via idempotency tokens on resume"**: The terminal-status guard in `_map_results_to_state()` provides this guarantee for the status overwrite path.
- **pipeline.md "All state writes are atomic"**: The implementation uses `save_state()` with atomic `os.replace()` for all new state writes; the prompt-only round filter introduces no new state writes.

No new behavior is introduced that is not already reflected in the requirements documents.

## Verdict

```json
{
  "verdict": "APPROVED",
  "cycle": 1,
  "issues": [],
  "requirements_drift": "none"
}
```
