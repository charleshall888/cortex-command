---
schema_version: "1"
uuid: f5b6f15c-0942-43c1-b523-e97df19ffeeb
title: "Fix test_plan.py failures from worktree bootstrap changes"
status: complete
priority: medium
type: bug
tags: [overnight-runner, tests]
areas: [tests]
created: 2026-04-03
updated: 2026-04-03
parent: "018"
session_id: null
lifecycle_phase: complete
lifecycle_slug: fix-test-plan-py-failures-from-worktree-bootstrap-changes
complexity: simple
criticality: high
spec: cortex/lifecycle/archive/fix-test-plan-py-failures-from-worktree-bootstrap-changes/spec.md
---

## Context

Commit `1bd7bde` ("Fix worktree bootstrap to use correct repo and prune grace period") changed `cortex_command/overnight/plan.py` to add `cwd=project_root` to `subprocess.run` calls and `--expire now` to `git worktree prune` calls. The three tests in `TestInitializeOvernightState` were not updated to match the new call signatures, leaving the test suite failing.

## Failing tests

```
cortex_command/overnight/tests/test_plan.py::TestInitializeOvernightState::test_git_worktree_prune_called
cortex_command/overnight/tests/test_plan.py::TestInitializeOvernightState::test_git_worktree_add_called_with_correct_args
cortex_command/overnight/tests/test_plan.py::TestInitializeOvernightState::test_cross_repo_prune_called_with_cwd
```

## What broke

- `test_git_worktree_prune_called` expects `call(["git", "worktree", "prune"])` — actual is `call(["git", "worktree", "prune", "--expire", "now"], cwd=...)`
- `test_git_worktree_add_called_with_correct_args` expects `git worktree add` without `cwd` kwarg — actual includes `cwd=project_root`
- `test_cross_repo_prune_called_with_cwd` expects `cwd=cross_repo_path` on the prune call but the actual call structure changed after `1bd7bde`

Fix is to update the three test assertions to match the new call signatures introduced in `1bd7bde`.
