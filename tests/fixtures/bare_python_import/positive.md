# Bare-Python Import Lint — Positive Fixtures

Each section below contains a case that SHOULD produce at least one L201 violation.

### Rule1-labeled-fence-python

```python
import cortex_command
```

### Rule1-labeled-fence-py

```py
from cortex_command.pipeline import create_worktree
```

### Rule2-python3-c-single-line

Run with:

python3 -c "import cortex_command"

### Rule2-python3-c-multiline

Run with:

python3 -c "
import cortex_command
print('hello')
"

### Rule3-heredoc

python3 - <<EOF
import cortex_command
print('done')
EOF

### Rule4-unlabeled-fence-with-invocation

```
python3 -c "import cortex_command"
```

### DynamicImport-find-spec

```bash
python3 -c "import importlib.util; importlib.util.find_spec('cortex_command')"
```

### DynamicImport-import-module

```bash
python3 -c "import importlib; importlib.import_module('cortex_command')"
```
