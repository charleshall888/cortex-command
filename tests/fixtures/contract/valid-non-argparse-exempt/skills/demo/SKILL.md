---
name: demo
description: Non-argparse-exempt fixture for contract lint
---

The cortex-update-item binary uses key=value positional pairs without argparse.
Any invocation against it would normally trip the lint with "unknown flag" —
but the bin/.contract-lint-exceptions.md ledger entry categorically exempts
the binary via the non-argparse-module category.

```bash
cortex-update-item status=complete type=feature title="My ticket"
```
