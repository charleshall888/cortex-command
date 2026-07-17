"""Parity test pinning the operation order of worktree-entry.md §1a step v.

The interactive-worktree-entry reference at
``skills/lifecycle/references/worktree-entry.md`` §1a step v (the
"Auto-enter sequence") performs three operations on the
``selected`` (picker-fired) entry-mode path in a load-bearing order:

  1. capture ``_origin_pwd`` (so we can restore CWD on fallback),
  2. probe already-in-worktree state via ``cortex-worktree-precondition``
     (cheap fast-fail before EnterWorktree's "Must not already be in a
     worktree" rejection race), and
  3. call ``EnterWorktree(path=...)`` (the actual auto-enter).

(A fourth operation — emitting an ``interactive_worktree_entered`` event
from inside the worktree — was deleted with the event itself in #391: it
had no reader.)

Under ADR-0008 the consumer-CLAUDE.md authorization fence was removed, so
the former ``cortex init --verify-worktree-auth`` probe is gone — this
module asserts the token is ABSENT. (§1a step v moved out of implement.md
into worktree-entry.md in the lifecycle-corpus-trim-wave-2 route-conditional
extraction; the behavioral pins are unchanged — only the host file did.) The
``suppressed`` (picker-suppressed,
branch-mode: worktree-interactive) entry mode skips the precondition probe
AND the EnterWorktree call entirely and routes structurally to the
cd-shim; ``test_step_v_pins_suppressed_picker_skip`` pins that structural
skip so a soft-gate implementation (one that keeps the EnterWorktree call
and declines only at runtime) fails the suite.

Re-ordering any of the three operations silently breaks observable
behavior — e.g., probing after EnterWorktree would be impossible to use as
a fast-fail (cortex-worktree-precondition). This test extracts the step v
block from ``worktree-entry.md`` between the ``**Step v — Auto-enter
sequence**`` anchor and the next ``**`` line-start boundary, then asserts
the three tokens appear in the expected order.

The test catches operation-sequence regressions that the presence-only
greps in T10's verification cannot catch (R11 of
``cortex/lifecycle/lifecycle-implement-auto-enter-worktree-via/spec.md``).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
WORKTREE_ENTRY_MD = (
    REPO_ROOT / "skills" / "lifecycle" / "references" / "worktree-entry.md"
)

# §1a step v block bounded by the ``**Step v — Auto-enter sequence**``
# heading and the next line-start ``**``-prefixed boundary (e.g. the
# step vi heading, or any other ``**``-anchored block heading). The
# spec's R11 language describes "the next ``**Step`` heading" — in
# practice §1a's downstream headings are ``**vi.``, ``**vii.``, etc.,
# all of which begin with ``**`` at line start, so this anchor is
# stable and forward-compatible if a future refactor adds explicit
# ``**Step vi —`` headings.
_BLOCK_PATTERN = re.compile(
    r"^\*\*Step v — Auto-enter sequence\*\*.*?(?=^\*\*)",
    re.MULTILINE | re.DOTALL,
)

# The three operation tokens in the order they must appear in the step v
# block. Each token is a literal substring search (case-sensitive) —
# they are anchored to specific shell-callable names, CLI flags, and tool
# call syntax that the implementation depends on.
_REQUIRED_ORDER = (
    "_origin_pwd",
    "cortex-worktree-precondition",
    "EnterWorktree(",
)

# The suppressed-picker structural-skip marker. Per ADR-0008, when §1's
# branch-mode preflight suppresses the picker (branch-mode:
# worktree-interactive), §1a step v must skip the EnterWorktree call
# STRUCTURALLY and route to the cd-shim — not keep the call and decline it
# at runtime. This literal anchors that structural skip; a soft-gate-only
# implementation omits it and fails test_step_v_pins_suppressed_picker_skip.
_SUPPRESSED_SKIP_MARKER = "EnterWorktree skipped: suppressed-picker"

# The removed fence-probe token. ADR-0008 deleted the consumer-CLAUDE.md
# fence, so ``cortex init --verify-worktree-auth`` no longer exists; the
# step v block must not reference it.
_REMOVED_VERIFY_TOKEN = "verify-worktree-auth"


def _extract_step_v_block() -> str:
    """Return the §1a step v block text bounded by the stable anchors."""
    content = WORKTREE_ENTRY_MD.read_text(encoding="utf-8")
    match = _BLOCK_PATTERN.search(content)
    if not match:
        pytest.fail(
            "Could not locate the §1a step v block anchored on "
            "'**Step v — Auto-enter sequence**' in "
            f"{WORKTREE_ENTRY_MD.relative_to(REPO_ROOT)}. The anchor heading "
            "or the next '**' line-start boundary is missing — restore "
            "the anchor heading or the next block-level '**' delimiter."
        )
    return match.group(0)


def test_step_v_block_extractable() -> None:
    """The §1a step v block must be locatable via the stable anchor."""
    block = _extract_step_v_block()
    assert block, "Step v block extracted but was empty."


def test_step_v_block_contains_all_required_tokens() -> None:
    """All three operation tokens must appear in the step v block.

    This is the presence half of the contract; ordering is tested
    separately. Splitting the assertions surfaces a clearer failure
    message when a token is removed entirely vs. when it is merely
    re-ordered.
    """
    block = _extract_step_v_block()
    missing = [token for token in _REQUIRED_ORDER if token not in block]
    assert not missing, (
        "Required operation tokens missing from §1a step v block: "
        f"{missing!r}. Expected all of {list(_REQUIRED_ORDER)!r}."
    )


def test_step_v_operations_appear_in_required_order() -> None:
    """Pin the load-bearing order of the auto-enter sequence operations.

    The three tokens must appear in the order specified by R11 of the
    spec. Re-ordering any pair silently changes observable behavior
    (e.g., probing after the EnterWorktree call is useless as a
    fast-fail). This test catches such regressions.
    """
    block = _extract_step_v_block()
    positions: list[tuple[str, int]] = []
    for token in _REQUIRED_ORDER:
        idx = block.find(token)
        assert idx >= 0, (
            f"Token {token!r} missing from §1a step v block. The "
            "presence test should have caught this first — investigate "
            "test ordering or token rename."
        )
        positions.append((token, idx))

    # Walk pairwise and assert each token's position is strictly
    # greater than the previous one's first occurrence.
    for (prev_token, prev_idx), (curr_token, curr_idx) in zip(
        positions, positions[1:]
    ):
        assert prev_idx < curr_idx, (
            f"§1a step v operation order regression: {curr_token!r} "
            f"appears at index {curr_idx} but {prev_token!r} appears "
            f"at index {prev_idx} — required order is "
            f"{list(_REQUIRED_ORDER)!r}. Re-ordering this sequence "
            "changes observable behavior (e.g., probing after the "
            "EnterWorktree call is useless as a fast-fail). Restore the "
            "canonical order."
        )


def test_step_v_omits_removed_verify_probe() -> None:
    """The deleted ``--verify-worktree-auth`` probe must not reappear.

    ADR-0008 removed the consumer-CLAUDE.md authorization fence and the
    ``cortex init --verify-worktree-auth`` probe that read it. A regression
    re-adding the probe to the auto-enter sequence would reintroduce the
    fence dependency this lifecycle removed.
    """
    block = _extract_step_v_block()
    assert _REMOVED_VERIFY_TOKEN not in block, (
        f"§1a step v references the removed token {_REMOVED_VERIFY_TOKEN!r}. "
        "ADR-0008 deleted the consumer-CLAUDE.md fence and its "
        "verify-worktree-auth probe — the auto-enter sequence must not "
        "depend on it. Remove the reference from implement.md §1a step v."
    )


def test_step_v_pins_suppressed_picker_skip() -> None:
    """Pin the suppressed-picker entry mode's STRUCTURAL EnterWorktree skip.

    Per ADR-0008, when §1's branch-mode preflight suppresses the picker
    (branch-mode: worktree-interactive), §1a step v must skip the
    EnterWorktree call structurally and route to the cd-shim. The marker
    ``EnterWorktree skipped: suppressed-picker`` is the anchor: a soft-gate
    implementation that keeps the EnterWorktree call and relies only on the
    runtime fallback would omit it. This test fails such an implementation.
    """
    block = _extract_step_v_block()
    assert _SUPPRESSED_SKIP_MARKER in block, (
        "§1a step v is missing the suppressed-picker structural-skip marker "
        f"{_SUPPRESSED_SKIP_MARKER!r}. The suppressed entry mode "
        "(branch-mode: worktree-interactive) must skip the EnterWorktree "
        "call structurally and route to the cd-shim (ADR-0008) — not keep "
        "the call and decline it at runtime. Restore the structural branch "
        "in implement.md §1a step v operation 2."
    )
