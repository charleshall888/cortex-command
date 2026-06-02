---
name: demo
description: command -v probe fixture for contract lint — fenced probe with redirection tail
---

Before materializing the worktree, probe whether the console-script is reachable:

```bash
command -v cortex-worktree-create >/dev/null 2>&1
```

Route by exit code: exit 0 means the binary is on PATH; exit 1 means it is not installed.
