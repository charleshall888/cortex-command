# Review: fix-test-plan-py-failures-from-worktree-bootstrap-changes

## Stage 1: Spec Compliance

### Requirement 1: Update `test_git_worktree_prune_called` assertion
**Rating**: PASS

The assertion was changed from `call(["git", "worktree", "prune"])` to `call(["git", "worktree", "prune", "--expire", "now"], cwd=Path.cwd().resolve())`. This matches the spec exactly. The test exits 0.

### Requirement 2: Update `test_git_worktree_add_called_with_correct_args` assertion
**Rating**: PASS

`cwd=Path.cwd().resolve()` was added to the existing `call(...)` kwargs, alongside the pre-existing `check=True`. The test exits 0.

### Requirement 3: Update `test_cross_repo_prune_called_with_cwd` filter
**Rating**: PASS

The filter changed from `c.args[0] == ["git", "worktree", "prune"]` to `c.args[0] == ["git", "worktree", "prune", "--expire", "now"]`. This matches the spec exactly. The test exits 0.

### Requirement 4: Full test class passes
**Rating**: PASS

`pytest claude/overnight/tests/test_plan.py::TestInitializeOvernightState` exits 0 with all 30 tests passing.

### Non-requirements verified
- No changes to production code (`plan.py`): confirmed via `git diff` -- no diff.
- No changes to `_cross_repo_side_effects` helper: confirmed -- none of the 3 diff hunks touch it.
- No changes to adjacent tests using `cmd[:3]` prefix matching (e.g., `test_prune_called_before_add`): confirmed -- those tests are untouched.

## Stage 2: Code Quality

### Naming conventions
Consistent with project patterns. No new test methods, variables, or helpers introduced -- only assertion values were updated.

### Error handling
Not applicable -- this is a test-only fix updating assertion expectations to match production behavior.

### Test coverage
All three acceptance tests were run individually and pass. The full class (30 tests) passes, confirming no regressions in adjacent tests.

### Pattern consistency
The changes follow the existing pattern in the test file. The `cwd=Path.cwd().resolve()` pattern is already used elsewhere in the class (e.g., `test_integration_branches_populated_for_home_repo`, `test_integration_branches_home_repo_regression`). The `--expire now` args match what production code passes.

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Verdict

```json
{
  "verdict": "APPROVED",
  "cycle": 1,
  "issues": [],
  "requirements_drift": "none"
}
```
