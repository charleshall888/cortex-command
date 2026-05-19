"""Structural contract test for the worktree-interactive dispatch surface.

Asserts that `skills/lifecycle/references/implement.md`:
  (a) Contains the menu label "Implement on feature branch with worktree" in §1.
  (b) Invokes `cortex-interactive-lock acquire {slug}` at least once in the
      worktree-interactive dispatch block at §1a.
  (c) Fires BOTH overnight-active rejection guards — pre-creation at §1 Step A
      AND post-creation at §1a.ii — via `_interactive_overnight_check.sh`.

Structural-only — no live SDK dispatch. Reads implement.md text once at
module scope and asserts substring/pattern presence.
"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
IMPLEMENT_MD = REPO_ROOT / "skills" / "lifecycle" / "references" / "implement.md"

# Read once at module scope per the task specification.
_IMPLEMENT_TEXT = IMPLEMENT_MD.read_text()


def test_menu_label_present_in_section_1() -> None:
    """§1 branch-selection menu must include the worktree-interactive option label."""
    # Locate the §1 Pre-Flight Check section (up to §1a).
    match = re.search(
        r"### 1\. Pre-Flight Check.*?(?=### 1a\.)", _IMPLEMENT_TEXT, flags=re.DOTALL
    )
    assert match is not None, (
        "Could not locate '### 1. Pre-Flight Check' section in implement.md"
    )
    section_1 = match.group(0)

    assert "Implement on feature branch with worktree" in section_1, (
        "§1 branch-selection menu must contain the label "
        "'Implement on feature branch with worktree'"
    )


def test_interactive_lock_acquire_in_worktree_dispatch_block() -> None:
    """The worktree-interactive dispatch block (§1 / §1a) must invoke the lock acquire command."""
    assert "cortex-interactive-lock acquire" in _IMPLEMENT_TEXT, (
        "implement.md must invoke 'cortex-interactive-lock acquire {slug}' "
        "in the worktree-interactive dispatch block"
    )


def test_overnight_guard_sidecar_called_at_least_twice() -> None:
    """Both overnight-active rejection guards must invoke _interactive_overnight_check.sh.

    Guard 1 fires pre-creation at §1 Step A (before the worktree is created).
    Guard 2 fires post-selection at §1a.ii (inside the Interactive Worktree
    Creation section, after the user has selected the worktree option).

    The test asserts count >= 2 — location is not pinned (line numbers drift).
    """
    occurrences = re.findall(
        r"_interactive_overnight_check\.sh", _IMPLEMENT_TEXT
    )
    assert len(occurrences) >= 2, (
        f"implement.md must reference '_interactive_overnight_check.sh' at least "
        f"twice (pre-creation §1 Step A + post-creation §1a.ii); "
        f"found {len(occurrences)} occurrence(s)"
    )
