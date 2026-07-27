# Parallel Execution

To run multiple lifecycle features at once ("lifecycle 120 and 121 in parallel"), use the `Agent` tool with `isolation: "worktree"` per feature:

```
Agent(isolation: "worktree", prompt: "/cortex-core:lifecycle {feature}")
```

**Prefer this over manual `git worktree add`.** Same-repo worktrees resolve to `<repo>/.claude/worktrees/{feature}/` under the project trust scope, and the Agent tool creates and auto-cleans them. If manual creation is unavoidable, compute the target via `cortex-worktree-resolve {name}` — never hardcode it — and `git branch -d <name>` before retrying, since a failed checkout can orphan the branch.

**Never `cd <worktree-path> && git <cmd>`** — it trips a hardcoded Claude Code security check ("Compound commands with cd and git require approval to prevent bare repository attacks") with no bypass. Inspect worktree branches from the main repo CWD via remote-ref syntax instead:

```
git log HEAD..worktree/{task-name} --oneline
```

`{task-name}` is the `name` passed to `Agent(isolation: "worktree")`; the branch is always `worktree/{name}`.
