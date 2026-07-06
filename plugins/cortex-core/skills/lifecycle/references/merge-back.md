# Worktree Merge-Back (Implement §2e)

Consumed by Implement §2e only on the worktree-dispatch arm; the sequential path never reads it (mode is fixed in §1).

After checkpoint, merge each completed task's worktree branch into the feature branch and clean up, so later batches' worktrees branch from the updated HEAD and see prior batches' changes.

For each task in the batch, in order:

1. **No changes**: Agent result shows no changes → already auto-cleaned. Skip merge and cleanup.
2. **Failed commit**: `git log HEAD..worktree/{task-name} --oneline` shows zero lines → skip the merge, clean up: `git worktree remove "$(cortex-worktree-resolve {task-name})"` then `git branch -d worktree/{task-name}`.
3. **Merge** (passed checkpoint): `git merge worktree/{task-name}` from the feature branch.
4. **Cleanup** (after successful merge): same two commands as step 2.
5. **Merge conflict**: surface as an integration error naming `worktree/{task-name}`; continue remaining tasks, do not roll back merged branches.
