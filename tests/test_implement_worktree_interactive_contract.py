"""Structural contract test for the worktree-interactive dispatch surface.

The worktree entry machinery (§1 Step A + the §1a interactive-worktree
sequence) moved out of ``implement.md`` into
``skills/lifecycle/references/worktree-entry.md`` in the
lifecycle-corpus-trim-wave-2 route-conditional extraction: trunk-mode runs
no longer load it. ``implement.md`` §1 keeps the picker (its labels are the
``EnterWorktree`` authorization handoff) and hands off the entry-mode marker
with an imperative "read worktree-entry.md and follow it" link at both
routing seams (the ``resolved``:worktree-interactive arm and the picker's
worktree selection). The behavioral pins below are unchanged — only the host
file each one lives in changed.

Asserts that:
  (a) ``implement.md`` §1 contains the menu label "Implement on feature branch
      with worktree" (the picker stays in implement.md).
  (b) ``worktree-entry.md`` invokes the interactive-lock acquire (now composed
      inside `cortex-lifecycle-prepare-worktree`) in the §1a dispatch block.
  (c) BOTH overnight-active rejection guards fire in ``worktree-entry.md`` —
      pre-creation at Step A via `_interactive_overnight_check.sh` directly,
      AND post-selection at §1a.i via `cortex-lifecycle-prepare-worktree`,
      which re-implements the same active-session/runner.pid check in Python
      (see that module's docstring for why it doesn't subprocess into the
      sidecar — the sidecar is a skill-tree asset, the verb ships in the
      separately-installed cortex-command wheel).

Post-consolidation (§1a's guard→lock→create sequence collapsed into one
verb call), several assertions here were updated to match the new shape;
each updated test's docstring explains what changed and why the dropped
half is now covered by `cortex_command/lifecycle/tests/test_prepare_worktree.py`
instead.

Structural-only — no live SDK dispatch. Reads implement.md and worktree-entry.md
text once at module scope and asserts substring/pattern presence.
"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
IMPLEMENT_MD = REPO_ROOT / "skills" / "lifecycle" / "references" / "implement.md"
WORKTREE_ENTRY_MD = (
    REPO_ROOT / "skills" / "lifecycle" / "references" / "worktree-entry.md"
)

# Read once at module scope per the task specification.
_IMPLEMENT_TEXT = IMPLEMENT_MD.read_text()
_WORKTREE_ENTRY_TEXT = WORKTREE_ENTRY_MD.read_text()


def test_menu_label_present_in_section_1() -> None:
    """§1 branch-selection menu must include the worktree-interactive option label."""
    # Locate the §1 Pre-Flight Check section. §1a moved to worktree-entry.md, so
    # §1 is now bounded at the next real heading '### 2. Task Dispatch'.
    match = re.search(
        r"### 1\. Pre-Flight Check.*?(?=### 2\.)", _IMPLEMENT_TEXT, flags=re.DOTALL
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
    it so a reader knows what the composed verb does. §1a now lives in
    worktree-entry.md (route-conditional extraction).
    """
    assert "cortex-interactive-lock acquire" in _WORKTREE_ENTRY_TEXT, (
        "worktree-entry.md must document 'cortex-interactive-lock acquire' as "
        "part of the worktree-interactive dispatch block (now composed inside "
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
    §1a's guard moved out of skill prose into the verb. Both guards now live in
    worktree-entry.md (Step A + §1a moved there in the route-conditional
    extraction).
    """
    assert "_interactive_overnight_check.sh" in _WORKTREE_ENTRY_TEXT, (
        "worktree-entry.md Step A must still invoke the sidecar directly"
    )
    assert "cortex-lifecycle-prepare-worktree" in _WORKTREE_ENTRY_TEXT, (
        "worktree-entry.md §1a must invoke cortex-lifecycle-prepare-worktree, "
        "which composes the second overnight guard internally"
    )


def test_sidecar_invocation_form_bash_s_count() -> None:
    """The one remaining sidecar invocation (Step A) keeps its ``bash -s --`` form.

    §1a's guard moved into cortex-lifecycle-prepare-worktree (a Python
    re-implementation, not a second subprocess into the sidecar), so only
    Step A's direct invocation remains. A dropped ``-s --`` (which would
    swallow the positional message/root args) is otherwise caught by no
    lint, so the count is pinned here at exactly 1 post-consolidation. Step A
    now lives in worktree-entry.md (route-conditional extraction), so the count
    is pinned there — implement.md carries zero after the extraction.
    """
    count = _WORKTREE_ENTRY_TEXT.count("bash -s --")
    assert count == 1, (
        f"worktree-entry.md must contain exactly one 'bash -s --' sidecar "
        f"invocation (Step A only — §1a's guard now lives inside "
        f"cortex-lifecycle-prepare-worktree); found {count}"
    )
    assert "bash -s --" not in _IMPLEMENT_TEXT, (
        "implement.md must carry zero 'bash -s --' invocations after the "
        "worktree-entry.md extraction — Step A moved out of §1"
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
    overnight-guard + lock-acquire + worktree-create sequence. §1a moved to
    worktree-entry.md (route-conditional extraction), so the gated path is
    extracted from that file.
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

    # Gated side: the '**i. Prepare**' block (ends at '**Step v') in
    # worktree-entry.md, where §1a now lives. Narrowing to the Prepare block so
    # a future --feature-bearing command elsewhere in §1a can't become the
    # compared binary and silently repoint the gate↔gated parity check.
    prepare_match = re.search(
        r"\*\*i\..*?(?=\*\*Step v)", _WORKTREE_ENTRY_TEXT, flags=re.DOTALL
    )
    assert prepare_match is not None, (
        "Could not locate the '**i. Prepare**' block (bounded at '**Step v') "
        "in §1a of worktree-entry.md"
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
    # §1 Pre-Flight Check. §1a moved to worktree-entry.md, so §1 is now bounded
    # at the next real heading '### 2. Task Dispatch' (NOT \\Z/EOF — so later
    # sections cannot leak in).
    section_1_match = re.search(
        r"### 1\. Pre-Flight Check.*?(?=### 2\.)", _IMPLEMENT_TEXT, flags=re.DOTALL
    )
    assert section_1_match is not None, (
        "Could not locate '### 1. Pre-Flight Check' section in implement.md"
    )
    section_1 = section_1_match.group(0)

    # §1a Interactive Worktree Creation now lives in worktree-entry.md. The
    # §1a.i step is the block between the '**i.' and '**Step v' markers there.
    i_start = _WORKTREE_ENTRY_TEXT.find("**i.")
    assert i_start != -1, "Could not locate '**i.' marker in §1a of worktree-entry.md"
    step_v_start = _WORKTREE_ENTRY_TEXT.find("**Step v", i_start)
    assert step_v_start != -1, (
        "Could not locate '**Step v' marker in §1a of worktree-entry.md"
    )
    step_i = _WORKTREE_ENTRY_TEXT[i_start:step_v_start]

    # (i) discriminator: the call never appears in §1 of implement.md — it
    # belongs only to §1a.i (now in worktree-entry.md).
    assert "cortex-lifecycle-prepare-worktree" not in section_1, (
        "implement.md §1 must not contain 'cortex-lifecycle-prepare-worktree' "
        "— the call belongs only to §1a.i in worktree-entry.md"
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
