---
name: demo
description: Env-prefix true-positive fixture — cortex-worktree-create preceded by an env assignment without --feature must flag E101
---

Create a worktree with an environment variable prefix:

```bash
FOO=1 cortex-worktree-create --base-branch main
```

The token `cortex-worktree-create` follows the space after the env assignment
`FOO=1` and is in command position — the `=` belongs to the env assignment,
not the token. The invocation is missing the required `--feature` flag and
must be flagged as E101.
