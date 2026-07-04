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


def test_sidecar_invocation_form_bash_s_count() -> None:
    """The two sidecar invocations must keep their ``bash -s --`` form.

    The sidecar is sourced and piped into ``bash -s -- "<message>" "<root>"``
    at §1 Step A and §1a.ii. A dropped ``-s --`` (which would swallow the
    positional message/root args) is otherwise caught by no lint, so the count
    is pinned here at exactly 2 to guard the §1/§1a consolidation trim.
    """
    count = _IMPLEMENT_TEXT.count("bash -s --")
    assert count == 2, (
        f"implement.md must contain exactly two 'bash -s --' sidecar "
        f"invocations (§1 Step A + §1a.ii); found {count}"
    )


def test_gate_and_gated_path_use_same_binary() -> None:
    """The worktree-availability gate and §1a step iii invocation must reference
    the same binary.

    Structural guard against gate↔gated drift: if the binary the availability
    gate probes diverges from the binary §1a step iii invokes, the gate silently
    lets through a binary it never tested. The gate moved from a §1 `command -v`
    check into the cortex-lifecycle-branch-decision verb (which sets
    `worktree_option_available` via `shutil.which(...)`); the gated path stays in
    §1a step iii of implement.md.
    """
    # Gate side: the shutil.which(...) probe inside the branch-decision verb.
    verb_src = (
        REPO_ROOT / "cortex_command" / "lifecycle" / "branch_decision.py"
    ).read_text(encoding="utf-8")
    gate_match = re.search(r'shutil\.which\(["\'](\S+?)["\']\)', verb_src)
    assert gate_match is not None, (
        "Could not find 'shutil.which(\"<binary>\")' availability gate in "
        "branch_decision.py"
    )
    gate_binary = gate_match.group(1)

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


def test_selected_path_acquire_unified_at_1a_ii() -> None:
    """The §1a.ii interactive-lock acquire must be unconditional (no per-entry-mode branch).

    Regression guard for #355: on the picker-``selected`` interactive-worktree
    path the lock acquire must occur only at §1a.ii (after the §1a.i overnight
    guard), identically to the ``suppressed`` path — never early at §1 Step B,
    where an overnight-guard rejection would orphan a held lock.

    Three assertions:
      (i)   [discriminator] §1 contains no ``cortex-interactive-lock acquire``
            (the early Step-B acquire is gone).
      (ii)  [forward-guard] within §1a, the earliest acquire index is after the
            last overnight-sidecar index (the acquire stays behind the guard).
      (iii) [unconditionality discriminator] the §1a.ii step invokes the acquire
            AND names neither entry mode — proving one unconditional acquire, not
            a per-mode branch. A dead-arm half-fix must name a mode and is caught.
    """
    # §1 Pre-Flight Check (up to §1a).
    section_1_match = re.search(
        r"### 1\. Pre-Flight Check.*?(?=### 1a\.)", _IMPLEMENT_TEXT, flags=re.DOTALL
    )
    assert section_1_match is not None, (
        "Could not locate '### 1. Pre-Flight Check' section in implement.md"
    )
    section_1 = section_1_match.group(0)

    # §1a Interactive Worktree Creation, bounded at the next real heading
    # '### 2. Task Dispatch' (NOT \\Z/EOF — so later sections cannot leak in).
    section_1a_match = re.search(
        r"### 1a\..*?(?=### 2\.)", _IMPLEMENT_TEXT, flags=re.DOTALL
    )
    assert section_1a_match is not None, (
        "Could not locate '### 1a.' section (bounded at '### 2.') in implement.md"
    )
    section_1a = section_1a_match.group(0)

    # The §1a.ii step: narrow §1a between the '**ii.' and '**iii.' markers.
    ii_start = section_1a.find("**ii.")
    assert ii_start != -1, "Could not locate '**ii.' marker in §1a of implement.md"
    iii_start = section_1a.find("**iii.", ii_start)
    assert iii_start != -1, "Could not locate '**iii.' marker in §1a of implement.md"
    step_ii = section_1a[ii_start:iii_start]

    # (i) discriminator: the early §1 Step-B acquire is gone.
    assert "cortex-interactive-lock acquire" not in section_1, (
        "§1 must not contain 'cortex-interactive-lock acquire' — the selected-path "
        "acquire must move out of §1 Step B into §1a.ii (after the overnight guard)"
    )

    # (ii) forward-guard: the acquire stays behind the overnight guard within §1a.
    earliest_acquire = section_1a.find("cortex-interactive-lock acquire")
    last_sidecar = section_1a.rfind("_interactive_overnight_check.sh")
    assert earliest_acquire != -1, (
        "§1a must invoke 'cortex-interactive-lock acquire' at §1a.ii"
    )
    assert last_sidecar != -1, (
        "§1a must invoke the overnight sidecar '_interactive_overnight_check.sh' at §1a.i"
    )
    assert earliest_acquire > last_sidecar, (
        "the §1a lock acquire must come AFTER the §1a.i overnight guard "
        f"(acquire@{earliest_acquire} must be > sidecar@{last_sidecar})"
    )

    # (iii) unconditionality discriminator: the §1a.ii acquire is unconditional —
    # it names neither entry mode, so no dead per-mode arm can hide.
    assert "cortex-interactive-lock acquire" in step_ii, (
        "the §1a.ii step ('**ii.'→'**iii.') must invoke 'cortex-interactive-lock acquire'"
    )
    step_ii_lower = step_ii.lower()
    assert "selected" not in step_ii_lower and "suppressed" not in step_ii_lower, (
        "the §1a.ii acquire must be UNCONDITIONAL — the step must name neither "
        "'selected' nor 'suppressed'; a per-entry-mode branch (dead-arm half-fix) "
        "would name at least one mode and re-introduce the orphan risk"
    )
