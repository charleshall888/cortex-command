"""Conftest for cortex_command/overnight/tests.

Stubs out backlog.update_item and the claude_agent_sdk before any test in
this package imports from cortex_command.overnight.batch_runner.  The stubs must be in
sys.modules before batch_runner.py is first imported because batch_runner.py executes two
unconditional module-level imports:

    from backlog.update_item import update_item, _find_item   (line ~550)

and the SDK import chain is triggered transitively through
cortex_command.pipeline.dispatch.
"""

import sys
import types as _types

# ---------------------------------------------------------------------------
# Stub backlog.update_item BEFORE installing the SDK stub.
# batch_runner.py imports from backlog.update_item unconditionally at module level;
# without this the import fires (and fails) as soon as any test imports from
# cortex_command.overnight.batch_runner.
# ---------------------------------------------------------------------------
_backlog_mod = _types.ModuleType("backlog")
_backlog_update_mod = _types.ModuleType("backlog.update_item")
_backlog_update_mod.update_item = lambda *a, **kw: None
_backlog_update_mod._find_item = lambda *a, **kw: None
sys.modules.setdefault("backlog", _backlog_mod)
sys.modules.setdefault("backlog.update_item", _backlog_update_mod)

# ---------------------------------------------------------------------------
# Install the claude_agent_sdk stub (reuses the pipeline test helper).
# ---------------------------------------------------------------------------
from cortex_command.tests._stubs import _install_sdk_stub  # noqa: E402

_install_sdk_stub()


# ---------------------------------------------------------------------------
# Shared JSONL parsing helper for overnight test files.
# Preserves 'ts' fields — required for cap/sort ordering tests.
# ---------------------------------------------------------------------------

import json as _json  # noqa: E402 (local import to avoid polluting test namespace)
from pathlib import Path  # noqa: E402


def _parse_jsonl(path: Path) -> list[dict]:
    """Read a JSONL file and return a list of parsed dicts (ts fields preserved)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return [_json.loads(line) for line in lines if line.strip()]
