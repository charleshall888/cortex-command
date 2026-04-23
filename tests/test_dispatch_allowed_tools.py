"""Contract test: the documented `_ALLOWED_TOOLS` list in docs/overnight-operations.md
must match `claude.pipeline.dispatch._ALLOWED_TOOLS` exactly (as a set).

Parses the fenced Python list literal from the docs at runtime and asserts
set-equality against the imported constant. Catches both code drift (tool
added/removed in dispatch.py without doc update) and doc drift (tool changed
in doc without code update).

Follows the precedent set by tests/test_events_contract.py.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from cortex_command.pipeline.dispatch import _ALLOWED_TOOLS

REPO_ROOT = Path(__file__).parent.parent
DOC_PATH = REPO_ROOT / "docs" / "overnight-operations.md"

# Matches a fenced Python block containing `_ALLOWED_TOOLS = [ ... ]` and
# captures the list literal body (including the surrounding brackets).
_DOC_LIST_RE = re.compile(
    r"```python\s*\n\s*_ALLOWED_TOOLS\s*=\s*(\[[^\]]*\])\s*\n```",
    re.MULTILINE,
)


def test_documented_allowed_tools_matches_dispatch_module():
    """The Python list literal documented in overnight-operations.md must match
    claude.pipeline.dispatch._ALLOWED_TOOLS as a set."""
    assert DOC_PATH.is_file(), (
        f"Source-of-truth doc missing: {DOC_PATH}. "
        "This test reads the documented _ALLOWED_TOOLS list from that file; "
        "a missing file must fail loudly, not silently pass."
    )

    text = DOC_PATH.read_text(encoding="utf-8")
    match = _DOC_LIST_RE.search(text)
    assert match, (
        f"Could not find a fenced ```python block containing "
        f"`_ALLOWED_TOOLS = [...]` in {DOC_PATH}. "
        "Expected format:\n"
        '    ```python\n'
        '    _ALLOWED_TOOLS = ["Read", "Write", ...]\n'
        '    ```'
    )

    documented = ast.literal_eval(match.group(1))
    assert isinstance(documented, list), (
        f"Parsed _ALLOWED_TOOLS from doc is not a list: {documented!r}"
    )

    doc_set = set(documented)
    code_set = set(_ALLOWED_TOOLS)

    only_in_doc = doc_set - code_set
    only_in_code = code_set - doc_set

    assert doc_set == code_set, (
        "Drift between documented _ALLOWED_TOOLS and "
        "claude.pipeline.dispatch._ALLOWED_TOOLS:\n"
        f"  only in {DOC_PATH.name}: {sorted(only_in_doc)}\n"
        f"  only in dispatch.py:      {sorted(only_in_code)}\n"
        f"  doc list:   {documented}\n"
        f"  code list:  {_ALLOWED_TOOLS}"
    )
