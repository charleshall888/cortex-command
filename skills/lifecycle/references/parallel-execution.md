# Parallel Execution

When the user requests running multiple lifecycle features in parallel (e.g., "/cortex-core:lifecycle 120 and 121 in parallel"), use the `Agent` tool with `isolation: "worktree"` for each feature:

```
Agent(
  isolation: "worktree",
  prompt: "/cortex-core:lifecycle {feature}"
)
```

**Prefer the `Agent` tool's `isolation: "worktree"` over manual `git worktree add`.** Same-repo worktrees resolve to `<repo>/.claude/worktrees/{feature}/` under the project's trust scope (rationale: `cortex/adr/0005-repo-relative-worktree-placement.md`); the `Agent` tool creates and auto-cleans them. If manual worktree creation is ever needed, compute the target via `cortex-worktree-resolve {name}` rather than hardcoding a path — and note that `git worktree add` creates the branch *before* checking out files, so a failed checkout leaves an orphaned branch (`git branch -d <name>` before retrying).

## Worktree Inspection Invariant

**Prohibited**: `cd <worktree-path> && git <cmd>` — this triggers a hardcoded Claude Code security check ("Compound commands with cd and git require approval to prevent bare repository attacks") that is not bypassable by allow rules or sandbox config. It also fails general compound-command allow-rule matching.

**Correct pattern**: inspect worktree branches from the main repo CWD using remote-ref syntax:

```
git log HEAD..worktree/{task-name} --oneline
```

The task name is the `name` parameter passed to `Agent(isolation: "worktree")`; the branch is always `worktree/{name}` (from `claude/hooks/cortex-worktree-create.sh`).
