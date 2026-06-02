---
name: demo
description: Positional-tail true-positive fixture — cortex-worktree-create with a path-like positional arg but no --feature must flag E101
---

Create a worktree by passing a branch name as a positional argument:

```bash
cortex-worktree-create feature/foo
```

The token `cortex-worktree-create` is in command position and is not itself a
path component — the path-component rejection must key on the token, not on
the path-like tail. The invocation is missing the required `--feature` flag
and must be flagged as E101.
