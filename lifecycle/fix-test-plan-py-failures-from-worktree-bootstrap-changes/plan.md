# Plan: fix-test-plan-py-failures-from-worktree-bootstrap-changes

## Overview

Update 3 test assertions in `TestInitializeOvernightState` to match the post-`1bd7bde` subprocess call signatures. Single file, mechanical changes: add `"--expire", "now"` to prune command lists and `cwd=Path.cwd().resolve()` kwargs where production now passes them.

## Tasks

### Task 1: Update prune call assertion in test_git_worktree_prune_called
- **Files**: `claude/overnight/tests/test_plan.py`
- **What**: Change the `call()` matcher at line 95 from the 3-element prune command to the 5-element command with `--expire now`, and add the `cwd` kwarg.
- **Depends on**: none
- **Complexity**: trivial
- **Context**: `test_git_worktree_prune_called` (lines 90-96). Current assertion: `call(["git", "worktree", "prune"])`. Production signature: `subprocess.run(["git", "worktree", "prune", "--expire", "now"], cwd=repo_root)`. The `_run` helper does not pass `project_root`, so `repo_root` defaults to `Path.cwd().resolve()`.
- **Verification**: `pytest claude/overnight/tests/test_plan.py::TestInitializeOvernightState::test_git_worktree_prune_called` — pass if exit 0
- **Status**: [x] done

### Task 2: Add cwd kwarg to worktree add assertion in test_git_worktree_add_called_with_correct_args
- **Files**: `claude/overnight/tests/test_plan.py`
- **What**: Add `cwd=Path.cwd().resolve()` to the `call(...)` matcher at lines 104-114 alongside the existing `check=True`.
- **Depends on**: none
- **Complexity**: trivial
- **Context**: `test_git_worktree_add_called_with_correct_args` (lines 98-115). Current assertion includes `check=True` but no `cwd`. Production signature: `subprocess.run([...], cwd=repo_root, check=True)`.
- **Verification**: `pytest claude/overnight/tests/test_plan.py::TestInitializeOvernightState::test_git_worktree_add_called_with_correct_args` — pass if exit 0
- **Status**: [x] done

### Task 3: Update prune command filter in test_cross_repo_prune_called_with_cwd
- **Files**: `claude/overnight/tests/test_plan.py`
- **What**: Change the list comprehension filter at line 551 from `["git", "worktree", "prune"]` to `["git", "worktree", "prune", "--expire", "now"]` so it matches the post-`1bd7bde` cross-repo prune call.
- **Depends on**: none
- **Complexity**: trivial
- **Context**: `test_cross_repo_prune_called_with_cwd` (lines 532-558). Filter: `c.args[0] == ["git", "worktree", "prune"]`. The `cwd == cross_repo_path` check is already correct — only the command list needs updating.
- **Verification**: `pytest claude/overnight/tests/test_plan.py::TestInitializeOvernightState::test_cross_repo_prune_called_with_cwd` — pass if exit 0
- **Status**: [x] done

## Verification Strategy

Run the full test class after all 3 tasks: `pytest claude/overnight/tests/test_plan.py::TestInitializeOvernightState` — pass if exit 0 with all tests passing. This confirms both the 3 fixed tests and all adjacent tests remain green.
