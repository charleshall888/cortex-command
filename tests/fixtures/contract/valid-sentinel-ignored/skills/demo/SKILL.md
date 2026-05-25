---
name: demo
description: Sentinel-ignored fixture for contract lint
---

This invocation is deliberately invalid (missing required flags) but is
suppressed by the sentinel marker placed immediately above the code fence.

<!-- contract-lint:ignore-next -->
```bash
cortex-create-backlog-item --title "My feature"
```
