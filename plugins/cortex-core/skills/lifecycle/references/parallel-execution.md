# Parallel Execution

When the user requests running multiple lifecycle features in parallel (e.g., "/cortex-core:lifecycle 120 and 121 in parallel"), use the `Agent` tool with `isolation: "worktree"` for each feature:

```
Agent(
  isolation: "worktree",
  prompt: "/cortex-core:lifecycle {feature}"
)
```

**Do not use `git worktree add` manually in sandboxed sessions.** This fails for two reasons:

1. **Seatbelt mandatory deny on `.mcp.json` blocks worktrees under the repo `.claude/` scope**: any worktree target inside the repo's `.claude/` directory fails because `git worktree add` checks out the tracked `.mcp.json` file into the new worktree, and Anthropic's `sandbox-runtime` enforces a mandatory deny on filename `.mcp.json` that operates below user-level `sandbox.filesystem.allowWrite`. Same-repo worktrees now resolve to `$TMPDIR/cortex-worktrees/{feature}/` via `cortex_command/pipeline/worktree.py::resolve_worktree_root()` so they live in the per-user `$TMPDIR` carve-out, outside the deny scope.
2. **Orphaned branches**: `git worktree add` creates the branch *before* checking out files. A failed checkout leaves an orphaned branch that blocks the next attempt with "branch already exists". Clean up with `git branch -d <name>` before retrying.

The `Agent` tool's `isolation: "worktree"` handles all of this correctly — it shells out via `claude/hooks/cortex-worktree-create.sh` (which invokes the single-chokepoint `cortex-worktree-resolve` console script), creating the worktree at `$TMPDIR/cortex-worktrees/{feature}/` and auto-cleaning if no changes are made. If manual worktree creation is ever needed, compute the target via `cortex-worktree-resolve {name}` rather than hardcoding a path.

## Worktree Inspection Invariant

**Prohibited**: `cd <worktree-path> && git <cmd>` — this triggers a hardcoded Claude Code security check ("Compound commands with cd and git require approval to prevent bare repository attacks") that is not bypassable by allow rules or sandbox config. It also fails general compound-command allow-rule matching.

**Correct pattern**: inspect worktree branches from the main repo CWD using remote-ref syntax:

```
git log HEAD..worktree/{task-name} --oneline
```

The task name is the `name` parameter passed to `Agent(isolation: "worktree")`; the branch is always `worktree/{name}` (from `claude/hooks/cortex-worktree-create.sh` line 30).

Hook `updatedPermissions` session injection: ruled out — `updatedPermissions` is exclusive to `PermissionRequest` hooks; `WorktreeCreate` command hooks use plain-text stdout only and cannot inject session allow rules. Fix is behavioral only: use `git log HEAD..worktree/{name}` from main CWD (never `cd <path> && git`).
