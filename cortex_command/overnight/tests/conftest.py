"""Conftest for cortex_command/overnight/tests.

Stubs out cortex_command.backlog.update_item and the claude_agent_sdk
before any test in this package imports from
cortex_command.overnight.batch_runner.  The stubs must be in
sys.modules before batch_runner.py is first imported because
outcome_router.py executes module-level imports:

    from cortex_command.backlog.update_item import update_item, _find_item

and the SDK import chain is triggered transitively through
cortex_command.pipeline.dispatch.
"""

import sys
import types as _types

# ---------------------------------------------------------------------------
# Stub cortex_command.backlog.update_item BEFORE installing the SDK stub.
# outcome_router.py imports from cortex_command.backlog.update_item
# unconditionally at module level; without this the import fires (and may
# fail under fixtures that rely on the stub semantics) as soon as any test
# imports from cortex_command.overnight.batch_runner.
# ---------------------------------------------------------------------------
_backlog_update_mod = _types.ModuleType("cortex_command.backlog.update_item")
_backlog_update_mod.update_item = lambda *a, **kw: None
_backlog_update_mod._find_item = lambda *a, **kw: None
sys.modules.setdefault("cortex_command.backlog.update_item", _backlog_update_mod)

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
import os as _os  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest as _pytest  # noqa: E402


@_pytest.fixture(autouse=True)
def _contain_runner_env_exports():
    """Undo any ``os.environ`` mutation a test's runner call leaves behind.

    ``runner.py`` exports ``LIFECYCLE_SESSION_ID`` and ``CORTEX_REPO_ROOT``
    into its **own** process environment on purpose — children need them, and a
    runner process exits when the session does. Under pytest that process is the
    whole suite, so the export outlives the test and every later test inherits a
    ``CORTEX_REPO_ROOT`` pointing at a deleted ``tmp_path``.

    That went unnoticed because the resolvers reached from these tests either
    ignore the variable (``_resolve_user_project_root_from_cwd``) or pin it
    themselves via ``monkeypatch``. It surfaced when #484 moved the lifecycle
    verbs onto the env-honouring main-root resolver: 14 later tests in another
    package started deriving their events.log from the leaked path. Snapshot and
    restore rather than deleting named keys, so the next export added to the
    runner is contained without anyone having to remember this.
    """
    before = dict(_os.environ)
    try:
        yield
    finally:
        _os.environ.clear()
        _os.environ.update(before)


def _parse_jsonl(path: Path) -> list[dict]:
    """Read a JSONL file and return a list of parsed dicts (ts fields preserved)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return [_json.loads(line) for line in lines if line.strip()]
