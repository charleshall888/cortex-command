# Worktree Merge-Back (Implement §2e)

Consumed by Implement §2e only on the worktree-dispatch arm; the sequential path never reads it (mode is fixed in §1 before any batch runs).

After checkpoint, merge each completed task's worktree branch back into the feature branch and clean up, so later batches' worktrees (created via `claude/hooks/cortex-worktree-create.sh`) branch from the updated HEAD and see prior batches' changes.

For each task in the batch, in task order:

1. **No changes**: the Agent result shows no changes → the worktree was already auto-cleaned by the Agent tool. Skip merge and cleanup.
2. **Failed commit**: `git log HEAD..worktree/{task-name} --oneline` showed zero lines (no commit produced) → skip the merge but still clean up: `git worktree remove "$(cortex-worktree-resolve {task-name})"` then `git branch -d worktree/{task-name}`.
3. **Merge** (task passed the checkpoint): `git merge worktree/{task-name}` from the feature branch.
4. **Cleanup** (after a successful merge): `git worktree remove "$(cortex-worktree-resolve {task-name})"` then `git branch -d worktree/{task-name}`.
5. **Merge conflict**: surface it as an integration error naming `worktree/{task-name}`. Continue the remaining batch tasks — do not roll back already-merged branches.
