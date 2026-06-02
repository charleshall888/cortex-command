---
name: demo
description: Piped true-positive fixture — cortex-worktree-create after a pipe separator without --feature must flag E101
---

Pipe the output of one command into cortex-worktree-create:

```bash
echo "ready" | cortex-worktree-create --base-branch main
```

The token `cortex-worktree-create` appears immediately after the `|` separator,
which is a command-position acceptance point. The invocation is missing the
required `--feature` flag and must be flagged as E101.
