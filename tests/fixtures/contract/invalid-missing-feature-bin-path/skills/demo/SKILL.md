---
name: demo
description: Path-prefixed true-positive fixture — cortex-worktree-create with a bin/ prefix followed by flags without --feature must flag E101
---

Create a worktree using an explicit path prefix:

```bash
bin/cortex-worktree-create --base-branch main
```

The token `cortex-worktree-create` has a `bin/` path prefix but is followed
by flags — this is a real run, not a path mention. The token itself has no
extension suffix (unlike `bin/cortex-worktree-create.sh`). The invocation is
missing the required `--feature` flag and must be flagged as E101.
