# Parallel Execution

To run multiple lifecycle features in parallel (e.g. "/cortex-core:lifecycle 120 and 121 in parallel"), use the `Agent` tool with `isolation: "worktree"` per feature:

```
Agent(isolation: "worktree", prompt: "/cortex-core:lifecycle {feature}")
```

**Prefer `Agent`'s `isolation: "worktree"` over manual `git worktree add`.** Same-repo worktrees resolve to `<repo>/.claude/worktrees/{feature}/` under the project trust scope (rationale: `cortex/adr/0005-repo-relative-worktree-placement.md`); the Agent tool creates and auto-cleans them. If manual creation is unavoidable, compute the target via `cortex-worktree-resolve {name}` (never hardcode); a failed checkout can orphan the branch, so `git branch -d <name>` it before retrying.

## Worktree Inspection Invariant

**Prohibited**: `cd <worktree-path> && git <cmd>` — it trips a hardcoded Claude Code security check ("Compound commands with cd and git require approval to prevent bare repository attacks") that no allow rule or sandbox config bypasses.

**Correct pattern**: inspect worktree branches from the main repo CWD using remote-ref syntax:

```
git log HEAD..worktree/{task-name} --oneline
```

The task name is the `name` parameter passed to `Agent(isolation: "worktree")`; the branch is always `worktree/{name}` (from `claude/hooks/cortex-worktree-create.sh`).
