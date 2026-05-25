"""Parity test pinning the §1 branch-selection picker's worktree option label.

The implement-phase reference at ``skills/lifecycle/references/implement.md``
contains a §1 branch-selection picker that presents three options to the
user. One of those options — today rendered as
``**Implement on feature branch with worktree**`` — is the authorization
handoff for the auto-enter pathway: when the user selects it, the picker
fires and the §1a path may invoke ``EnterWorktree``. The live ``EnterWorktree``
schema requires a user-direct mention of "worktree" in the authorizing
instruction; the option label IS that instruction.

This test extracts the §1 picker block from implement.md by a stable
anchor (the ``**Branch selection**`` heading to the next ``**`` boundary)
and asserts that at least one option label between those anchors contains
the literal word ``worktree``. It is forward-looking: it passes today, but
catches future label renames that would silently break the picker-fires
path's semantic anchor to the ``EnterWorktree`` authorization story.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
IMPLEMENT_MD = REPO_ROOT / "skills" / "lifecycle" / "references" / "implement.md"

# §1 picker block bounded by the ``**Branch selection**`` heading and the
# next line-start ``**``-prefixed boundary (e.g. ``**Branch-mode dispatch
# preflight**``, ``**Uncommitted-changes guard**``, etc.).
_BLOCK_PATTERN = re.compile(
    r"^\*\*Branch selection\*\*.*?(?=^\*\*)",
    re.MULTILINE | re.DOTALL,
)

# Option label: a list item ``- **<label>**`` (with optional ``(recommended)``
# or trailing text). Captures the bolded label text only.
_OPTION_LABEL = re.compile(r"^-\s+\*\*([^*]+)\*\*", re.MULTILINE)


def _extract_picker_block() -> str:
    """Return the §1 picker block text bounded by the stable anchors."""
    content = IMPLEMENT_MD.read_text(encoding="utf-8")
    match = _BLOCK_PATTERN.search(content)
    if not match:
        pytest.fail(
            "Could not locate the §1 picker block anchored on "
            "'**Branch selection**' in "
            f"{IMPLEMENT_MD.relative_to(REPO_ROOT)}. The anchor heading or "
            "the next '**' boundary is missing — update the anchor or "
            "restore the block."
        )
    return match.group(0)


def _extract_option_labels(block: str) -> list[str]:
    """Return the list of bolded option labels from the picker block."""
    return [m.group(1).strip() for m in _OPTION_LABEL.finditer(block)]


def test_picker_block_extractable() -> None:
    """The §1 picker block must be locatable via the stable anchor."""
    block = _extract_picker_block()
    assert block, "Picker block extracted but was empty."


def test_picker_block_contains_option_labels() -> None:
    """The §1 picker block must contain at least one parseable option label."""
    block = _extract_picker_block()
    labels = _extract_option_labels(block)
    assert labels, (
        "No bolded option labels found inside the §1 picker block. "
        "Expected at least one '- **<label>**' list item between the "
        "'**Branch selection**' anchor and the next '**' boundary."
    )


def test_at_least_one_option_label_mentions_worktree() -> None:
    """Pin the picker's worktree option: at least one label says 'worktree'.

    This is the structural lock on the picker-fires path's authorization
    story. If this assertion fails, a future rename has stripped the
    'worktree' token from every option label, breaking the user-direct
    mention that the ``EnterWorktree`` schema requires.
    """
    block = _extract_picker_block()
    labels = _extract_option_labels(block)
    assert any("worktree" in label.lower() for label in labels), (
        "No §1 picker option label contains the literal word 'worktree'. "
        f"Labels seen: {labels!r}. The auto-enter pathway's authorization "
        "anchor has been lost — restore 'worktree' to the relevant option "
        "label (e.g. 'Implement on feature branch with worktree')."
    )
