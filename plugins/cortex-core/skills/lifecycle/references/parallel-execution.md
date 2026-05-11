# Parallel Execution

When the user requests running multiple lifecycle features in parallel (e.g., "/cortex-core:lifecycle 120 and 121 in parallel"), use the `Agent` tool with `isolation: "worktree"` for each feature:

```
Agent(
  isolation: "worktree",
  prompt: "/cortex-core:lifecycle {feature}"
)
```

**Do not use `git worktree add` manually in sandboxed sessions.** This fails for two reasons:

1. **`.claude/` is sandbox-restricted at the Seatbelt OS level**: Any worktree target inside `.claude/` (e.g., `.claude/worktrees/{feature}`) will fail because git tries to write tracked `.claude/**` files into the new worktree. The restriction is broader than what `denyWithinAllow` explicitly shows.
2. **Orphaned branches**: `git worktree add` creates the branch *before* checking out files. A failed checkout leaves an orphaned branch that blocks the next attempt with "branch already exists". Clean up with `git branch -d <name>` before retrying.

The `Agent` tool's `isolation: "worktree"` handles all of this correctly — it creates the worktree outside the sandbox write path and auto-cleans if no changes are made. If manual worktree creation is ever needed, use `$TMPDIR` (not `.claude/`) as the target.

## Worktree Inspection Invariant

**Prohibited**: `cd <worktree-path> && git <cmd>` — this triggers a hardcoded Claude Code security check ("Compound commands with cd and git require approval to prevent bare repository attacks") that is not bypassable by allow rules or sandbox config. It also fails general compound-command allow-rule matching.

**Correct pattern**: inspect worktree branches from the main repo CWD using remote-ref syntax:

```
git log HEAD..worktree/{task-name} --oneline
```

The task name is the `name` parameter passed to `Agent(isolation: "worktree")`; the branch is always `worktree/{name}` (from `claude/hooks/cortex-worktree-create.sh` line 30).

Hook `updatedPermissions` session injection: ruled out — `updatedPermissions` is exclusive to `PermissionRequest` hooks; `WorktreeCreate` command hooks use plain-text stdout only and cannot inject session allow rules. Fix is behavioral only: use `git log HEAD..worktree/{name}` from main CWD (never `cd <path> && git`).
