---
name: demo
description: Invalid unknown-subcommand-flag fixture — bogus flag on a known subcommand must produce E102
---

Emit a research sizing event with an unknown flag:

```bash
cortex-discovery emit-research-sizing --topic my-feature --complexity simple --criticality medium --nope
```
