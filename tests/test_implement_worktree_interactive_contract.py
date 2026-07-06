"""Structural contract test for the worktree-interactive dispatch surface.

Asserts that `skills/lifecycle/references/implement.md`:
  (a) Contains the menu label "Implement on feature branch with worktree" in §1.
  (b) Invokes the interactive-lock acquire (now composed inside
      `cortex-lifecycle-prepare-worktree`) in the worktree-interactive
      dispatch block at §1a.
  (c) Fires BOTH overnight-active rejection guards — pre-creation at §1 Step A
      via `_interactive_overnight_check.sh` directly, AND post-selection at
      §1a.i via `cortex-lifecycle-prepare-worktree`, which re-implements the
      same active-session/runner.pid check in Python (see that module's
      docstring for why it doesn't subprocess into the sidecar — the sidecar
      is a skill-tree asset, the verb ships in the separately-installed
      cortex-command wheel).

Post-consolidation (§1a's guard→lock→create sequence collapsed into one
verb call), several assertions here were updated to match the new shape;
each updated test's docstring explains what changed and why the dropped
half is now covered by `cortex_command/lifecycle/tests/test_prepare_worktree.py`
instead.

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
    """The worktree-interactive dispatch block (§1a) must document the lock acquire.

    The literal ``cortex-interactive-lock acquire`` invocation moved out of
    skill prose and into ``cortex-lifecycle-prepare-worktree`` (which calls
    the same ``acquire_lock`` primitive internally); §1a's prose still names
    it so a reader knows what the composed verb does.
    """
    assert "cortex-interactive-lock acquire" in _IMPLEMENT_TEXT, (
        "implement.md must document 'cortex-interactive-lock acquire' as part "
        "of the worktree-interactive dispatch block (now composed inside "
        "cortex-lifecycle-prepare-worktree)"
    )


def test_overnight_guard_fires_at_both_call_sites() -> None:
    """Both overnight-active guards must still fire, in their new shapes.

    Guard 1 fires pre-creation at §1 Step A, invoking the sidecar script
    directly. Guard 2 fires post-selection at §1a, now composed inside the
    cortex-lifecycle-prepare-worktree verb — which re-implements the same
    active-session/runner.pid check in Python rather than subprocessing into
    the sidecar (see that module's docstring: the sidecar is a skill-tree
    asset installed via the plugin channel, while the verb ships in the
    separately-installed cortex-command wheel, so the two are not guaranteed
    co-located on disk at runtime).

    This replaces the prior ``occurrences >= 2`` count on
    ``_interactive_overnight_check.sh`` alone, which no longer holds now that
    §1a's guard moved out of skill prose into the verb.
    """
    assert "_interactive_overnight_check.sh" in _IMPLEMENT_TEXT, (
        "implement.md §1 Step A must still invoke the sidecar directly"
    )
    assert "cortex-lifecycle-prepare-worktree" in _IMPLEMENT_TEXT, (
        "implement.md §1a must invoke cortex-lifecycle-prepare-worktree, "
        "which composes the second overnight guard internally"
    )


def test_sidecar_invocation_form_bash_s_count() -> None:
    """The one remaining sidecar invocation (§1 Step A) keeps its ``bash -s --`` form.

    §1a's guard moved into cortex-lifecycle-prepare-worktree (a Python
    re-implementation, not a second subprocess into the sidecar), so only
    Step A's direct invocation remains. A dropped ``-s --`` (which would
    swallow the positional message/root args) is otherwise caught by no
    lint, so the count is pinned here at exactly 1 post-consolidation.
    """
    count = _IMPLEMENT_TEXT.count("bash -s --")
    assert count == 1, (
        f"implement.md must contain exactly one 'bash -s --' sidecar "
        f"invocation (§1 Step A only — §1a's guard now lives inside "
        f"cortex-lifecycle-prepare-worktree); found {count}"
    )


def test_gate_and_gated_path_use_same_binary() -> None:
    """The worktree-availability gate and §1a's prepare-worktree invocation must
    reference the same binary.

    Structural guard against gate↔gated drift: if the binary the availability
    gate probes diverges from the binary §1a actually invokes, the gate
    silently lets through a binary it never tested. The gate lives in the
    cortex-lifecycle-branch-decision verb (`worktree_option_available` via
    `shutil.which(...)`); the gated path is §1a's single
    `cortex-lifecycle-prepare-worktree` call, which now composes the
    overnight-guard + lock-acquire + worktree-create sequence.
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

    # Extract §1a body, bounded at the next real heading '### 2.' (implement.md
    # has no '### 1b.', so anchoring on '### 2.' avoids a \Z/EOF fallback that
    # could silently absorb unrelated later sections).
    section_1a_match = re.search(
        r"### 1a\..*?(?=### 2\.)", _IMPLEMENT_TEXT, flags=re.DOTALL
    )
    assert section_1a_match is not None, (
        "Could not locate '### 1a.' section (bounded at '### 2.') in implement.md"
    )
    section_1a = section_1a_match.group(0)

    # Narrow to the '**i. Prepare**' block (ends at '**Step v') so a future
    # --feature-bearing command elsewhere in §1a can't become the compared
    # binary and silently repoint the gate↔gated parity check.
    prepare_match = re.search(
        r"\*\*i\..*?(?=\*\*Step v)", section_1a, flags=re.DOTALL
    )
    assert prepare_match is not None, (
        "Could not locate the '**i. Prepare**' block (bounded at '**Step v') "
        "in §1a of implement.md"
    )
    prepare_block = prepare_match.group(0)

    # Extract binary: first token on a line followed by --feature. The line
    # may be a bare invocation or a shell assignment (var=$(<binary> ...)).
    gated_match = re.search(
        r"^(?:\w+=\$\()?(\S+?)\s+--feature\s+", prepare_block, flags=re.MULTILINE
    )
    assert gated_match is not None, (
        "Could not find '<binary> --feature ...' invocation in the §1a Prepare "
        "block of implement.md"
    )
    gated_binary = gated_match.group(1)

    assert gate_binary == gated_binary, (
        f"gate uses '{gate_binary}' but §1a invokes '{gated_binary}' "
        "— gate and gated path must call the same binary"
    )


def test_prepare_worktree_call_is_unconditional_and_not_in_section_1() -> None:
    """The §1a.i prepare-worktree call must be unconditional and never run in §1.

    Regression guard for #355, updated for the cortex-lifecycle-prepare-worktree
    consolidation (guard→lock→create collapsed into one verb call): on the
    picker-``selected`` interactive-worktree path the call must occur only at
    §1a.i (after §1's branch decision has already routed there) — never early
    in §1 Step B.

    Two assertions:
      (i)  [discriminator] §1 contains no ``cortex-lifecycle-prepare-worktree``
           invocation — the call lives only in §1a.
      (ii) [unconditionality discriminator] the §1a.i block invokes the verb
           AND names neither entry mode — proving one unconditional call, not
           a per-mode branch. A dead-arm half-fix would name a mode and is
           caught.

    The guard-before-lock-before-create ORDERING inside the composed verb
    (previously asserted here via sidecar-vs-acquire line position within
    skill prose) is no longer a skill-prose-level property — it moved into
    the verb's own control flow and is covered instead by
    ``cortex_command/lifecycle/tests/test_prepare_worktree.py``.
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

    # The §1a.i step: narrow §1a between the '**i.' and '**Step v' markers.
    i_start = section_1a.find("**i.")
    assert i_start != -1, "Could not locate '**i.' marker in §1a of implement.md"
    step_v_start = section_1a.find("**Step v", i_start)
    assert step_v_start != -1, "Could not locate '**Step v' marker in §1a of implement.md"
    step_i = section_1a[i_start:step_v_start]

    # (i) discriminator: the call never appears in §1.
    assert "cortex-lifecycle-prepare-worktree" not in section_1, (
        "§1 must not contain 'cortex-lifecycle-prepare-worktree' — the call "
        "belongs only to §1a.i"
    )

    # (ii) unconditionality discriminator: the §1a.i call is unconditional —
    # it names neither entry mode, so no dead per-mode arm can hide.
    assert "cortex-lifecycle-prepare-worktree" in step_i, (
        "the §1a.i step ('**i.'→'**Step v') must invoke "
        "'cortex-lifecycle-prepare-worktree'"
    )
    step_i_lower = step_i.lower()
    assert "selected" not in step_i_lower and "suppressed" not in step_i_lower, (
        "the §1a.i prepare-worktree call must be UNCONDITIONAL — the step must "
        "name neither 'selected' nor 'suppressed'; a per-entry-mode branch "
        "(dead-arm half-fix) would name at least one mode and re-introduce "
        "the orphan risk"
    )
