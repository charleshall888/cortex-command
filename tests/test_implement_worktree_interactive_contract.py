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


def test_gate_and_gated_path_use_same_binary() -> None:
    """§1 runtime-probe gate and §1a step iii invocation must reference the same binary.

    This is the class-level structural guard against literal-substring drift
    breaking gate↔gated agreement: if the binary named in the §1 `command -v`
    check diverges from the binary invoked in §1a step iii, the gate silently
    lets through a binary it never tested.
    """
    # Extract §1 body (Pre-Flight Check up to §1a).
    section_1_match = re.search(
        r"### 1\. Pre-Flight Check.*?(?=### 1a\.)", _IMPLEMENT_TEXT, flags=re.DOTALL
    )
    assert section_1_match is not None, (
        "Could not locate '### 1. Pre-Flight Check' section in implement.md"
    )
    section_1 = section_1_match.group(0)

    # Extract §1a body (from §1a heading up to §1b or end of string).
    section_1a_match = re.search(
        r"### 1a\..*?(?=### 1b\.|\Z)", _IMPLEMENT_TEXT, flags=re.DOTALL
    )
    assert section_1a_match is not None, (
        "Could not locate '### 1a.' section in implement.md"
    )
    section_1a = section_1a_match.group(0)

    # Narrow §1a to the step iii sub-section (between **iii. and **iv.).
    iii_start = section_1a.find("**iii.")
    assert iii_start != -1, "Could not locate '**iii.' marker in §1a of implement.md"
    iv_start = section_1a.find("**iv.", iii_start)
    section_1a_iii = section_1a[iii_start:iv_start] if iv_start != -1 else section_1a[iii_start:]

    # Extract binary from §1 gate: `command -v <name>`.
    gate_match = re.search(r"command -v (\S+)", section_1)
    assert gate_match is not None, (
        "Could not find 'command -v <binary>' pattern in §1 of implement.md"
    )
    gate_binary = gate_match.group(1)

    # Extract binary from §1a step iii: first token on a line followed by --feature interactive-.
    # The line may be a bare invocation or a shell assignment (var=$(<binary> ...)).
    gated_match = re.search(
        r"^(?:\w+=\$\()?(\S+?)\s+--feature\s+interactive-", section_1a_iii, flags=re.MULTILINE
    )
    assert gated_match is not None, (
        "Could not find '<binary> --feature interactive-' invocation in §1a step iii of implement.md"
    )
    gated_binary = gated_match.group(1)

    assert gate_binary == gated_binary, (
        f"gate uses '{gate_binary}' but §1a step iii invokes '{gated_binary}' "
        "— gate and gated path must call the same binary"
    )
