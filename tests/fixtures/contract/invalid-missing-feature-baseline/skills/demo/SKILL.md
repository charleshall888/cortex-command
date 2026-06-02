---
name: demo
description: Baseline true-positive fixture — bare invocation of cortex-worktree-create without --feature must flag E101
---

Create a worktree without the required `--feature` flag:

```bash
cortex-worktree-create --base-branch main
```

The invocation above is in command position and omits the required `--feature`
flag. The contract scanner must flag it as E101.
