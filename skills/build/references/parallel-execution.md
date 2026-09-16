# Parallel Execution

Run several lifecycle features at once with the `Agent` tool, one worktree per feature:

```
Agent(isolation: "worktree", prompt: "/cortex-core:build {feature}")
```

Prefer this over manual `git worktree add` — worktrees land at `<repo>/.claude/worktrees/{feature}/` under the project trust scope and are auto-cleaned. If manual creation is unavoidable, compute the path with `cortex-worktree-resolve {name}` and `git branch -d <name>` before retrying, since a failed checkout can orphan the branch.

Never `cd <worktree-path> && git <cmd>` — it trips a hardcoded Claude Code security check with no bypass. Inspect from the main repo CWD via remote-ref syntax: `git log HEAD..worktree/{task-name} --oneline`, where `{task-name}` is the `name` passed to `Agent(isolation: "worktree")` and the branch is always `worktree/{name}`.
