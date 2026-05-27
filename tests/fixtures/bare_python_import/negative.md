# Bare-Python Import Lint — Negative Fixtures

Each section below contains a case that should produce ZERO L201 violations.

### Stdlib-only-python3-c

This invocation uses only stdlib — no cortex_command import.

python3 -c "import json,sys; print(json.loads(sys.stdin.read()))"

### Narrative-prose-mention

The module cortex_command.pipeline.worktree provides the worktree creation
logic. You can read about it in the docs. No invocation here, just prose.

### Inline-code-span-mention

The following inline-code span is NOT an invocation and must not flag:
`python3 -c "import cortex_command"` — this is a code-span, not live code.

### Sentinel-immediate

<!-- bare-python-lint:ignore-next -->
```python
import cortex_command
```

### Sentinel-with-blank-line

<!-- bare-python-lint:ignore-next -->

```python
import cortex_command
```

### Two-sentinels-before-two-regions

<!-- bare-python-lint:ignore-next -->

```python
import cortex_command
```

<!-- bare-python-lint:ignore-next -->

```python
from cortex_command.pipeline import create_worktree
```
