---
name: demo
description: Demonstrates E104 — not_argparse binary without ledger entry
---

The `cortex-update-item` binary uses `sys.argv` directly and the fixture has no
local ledger entry to document the exemption. The lint must emit E104 to force
the operator to either document the exemption or add a proper argparse parser.

```bash
cortex-update-item status=complete type=feature
```
