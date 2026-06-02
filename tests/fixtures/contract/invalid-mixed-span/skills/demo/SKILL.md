---
name: demo
description: Mixed-span fixture — one fenced span holds both a path-mention (dropped) and a real invocation missing --feature (kept)
---

A single fenced block below contains BOTH a `.sh` path-mention and a separate
real invocation. The per-match command-position predicate must drop the
path-mention and keep the real run, producing exactly one E101.

```bash
cat claude/hooks/cortex-worktree-create.sh
cortex-worktree-create --base-branch main
```

The first line references the hook filename (path-prefixed, `.sh` suffix) and
must not be flagged. The second line is a genuine invocation missing the
required `--feature` flag and must produce E101.
