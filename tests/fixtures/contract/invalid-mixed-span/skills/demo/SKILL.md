---
name: demo
description: Mixed-span fixture — path-mention dropped, real invocation missing --feature kept
---

The hook script at `claude/hooks/cortex-worktree-create.sh` registers the handler.

```bash
cortex-worktree-create --base-branch main
```

The path-mention above is a filename reference and should not be flagged.
The fenced invocation is missing the required --feature flag and should produce E101.
