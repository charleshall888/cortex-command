# Parallel Execution

Run several lifecycle features at once with the `Agent` tool, one worktree per feature:

```
Agent(isolation: "worktree", prompt: "/cortex-core:build {feature}")
```

Prefer this over manual `git worktree add`: worktrees land at `<repo>/.claude/worktrees/{feature}/`, inside the project's trusted paths, and are cleaned up for you. If you must create one by hand, get the path from `cortex-worktree-resolve {name}`, and run `git branch -d <name>` before a retry, since a failed checkout can leave the branch behind.

Never `cd <worktree-path> && git <cmd>` — a built-in Claude Code security check blocks it. Inspect from the main repo CWD by branch name: `git log HEAD..worktree/{task-name} --oneline`, where `{task-name}` is the `name` passed to `Agent(isolation: "worktree")` and the branch is always `worktree/{name}`.
