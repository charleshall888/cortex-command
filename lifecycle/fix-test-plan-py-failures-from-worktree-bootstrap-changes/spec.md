# Specification: fix-test-plan-py-failures-from-worktree-bootstrap-changes

## Problem Statement

Commit `1bd7bde` added `cwd=project_root` and `--expire now` to `subprocess.run` calls in `claude/overnight/plan.py`, but the three tests in `TestInitializeOvernightState` that assert on those call signatures were not updated. The test suite is currently failing, blocking overnight runner validation.

## Requirements

1. **Update `test_git_worktree_prune_called` assertion**: Change `call(["git", "worktree", "prune"])` to `call(["git", "worktree", "prune", "--expire", "now"], cwd=Path.cwd().resolve())`.
   - *Acceptance*: `pytest claude/overnight/tests/test_plan.py::TestInitializeOvernightState::test_git_worktree_prune_called` exits 0.

2. **Update `test_git_worktree_add_called_with_correct_args` assertion**: Add `cwd=Path.cwd().resolve()` kwarg to the existing `call(...)`.
   - *Acceptance*: `pytest claude/overnight/tests/test_plan.py::TestInitializeOvernightState::test_git_worktree_add_called_with_correct_args` exits 0.

3. **Update `test_cross_repo_prune_called_with_cwd` filter**: Change `c.args[0] == ["git", "worktree", "prune"]` to `c.args[0] == ["git", "worktree", "prune", "--expire", "now"]`.
   - *Acceptance*: `pytest claude/overnight/tests/test_plan.py::TestInitializeOvernightState::test_cross_repo_prune_called_with_cwd` exits 0.

4. **Full test class passes**: All tests in `TestInitializeOvernightState` continue to pass after the assertion updates.
   - *Acceptance*: `pytest claude/overnight/tests/test_plan.py::TestInitializeOvernightState` exits 0.

## Non-Requirements

- No changes to production code (`plan.py`) — the production behavior from `1bd7bde` is correct
- No changes to the `_cross_repo_side_effects` helper — it returns positional mocks that are not affected by the signature change
- No changes to adjacent tests using `cmd[:3]` prefix matching — those are deliberately flexible and unaffected
- No updating of stale comments in the helper (cosmetic, separate concern)

## Edge Cases

- **`cwd` value when `project_root` is None**: The `_run` helper does not pass `project_root`, so production defaults to `Path.cwd().resolve()`. Test assertions must use `Path.cwd().resolve()`, not a hardcoded path.

## Technical Constraints

- All changes are in a single file: `claude/overnight/tests/test_plan.py`
- The `call()` matcher from `unittest.mock` requires exact match on both positional args and keyword args — partial matches fail silently
