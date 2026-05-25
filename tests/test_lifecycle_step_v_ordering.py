"""Parity test pinning the operation order of implement.md §1a step v.

The implement-phase reference at ``skills/lifecycle/references/implement.md``
§1a step v (the "Auto-enter sequence") performs five operations in a
load-bearing order:

  1. capture ``_origin_pwd`` (so we can restore CWD on fallback),
  2. probe authorization via ``cortex init --verify-worktree-auth``
     (cheap fast-fail when the consumer's CLAUDE.md fence is absent or
     stale),
  3. probe already-in-worktree state via ``cortex-worktree-precondition``
     (cheap fast-fail before EnterWorktree's "Must not already be in a
     worktree" rejection race),
  4. call ``EnterWorktree(path=...)`` (the actual auto-enter), and
  5. emit the ``interactive_worktree_entered`` event from inside the
     worktree (so ``_resolve_user_project_root_from_cwd()`` lands the row
     in the worktree's events.log, not the main repo's).

Re-ordering any of these silently breaks observable behavior — e.g.,
emitting the event before EnterWorktree completes would land the row in
the wrong events.log; probing after EnterWorktree would either be
redundant (verify-worktree-auth) or impossible to use as a fast-fail
(cortex-worktree-precondition). This test extracts the step v block from
``implement.md`` between the ``**Step v — Auto-enter sequence**`` anchor
and the next ``**`` line-start boundary, then asserts the five tokens
appear in the expected order.

The test catches operation-sequence regressions that the presence-only
greps in T10's verification cannot catch (R11 of
``cortex/lifecycle/lifecycle-implement-auto-enter-worktree-via/spec.md``).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
IMPLEMENT_MD = REPO_ROOT / "skills" / "lifecycle" / "references" / "implement.md"

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

# The five operation tokens in the order they must appear in the step v
# block. Each token is a literal substring search (case-sensitive) —
# they are anchored to specific shell-callable names, CLI flags, tool
# call syntax, and event names that the implementation depends on.
_REQUIRED_ORDER = (
    "_origin_pwd",
    "verify-worktree-auth",
    "cortex-worktree-precondition",
    "EnterWorktree(",
    "interactive_worktree_entered",
)


def _extract_step_v_block() -> str:
    """Return the §1a step v block text bounded by the stable anchors."""
    content = IMPLEMENT_MD.read_text(encoding="utf-8")
    match = _BLOCK_PATTERN.search(content)
    if not match:
        pytest.fail(
            "Could not locate the §1a step v block anchored on "
            "'**Step v — Auto-enter sequence**' in "
            f"{IMPLEMENT_MD.relative_to(REPO_ROOT)}. The anchor heading "
            "or the next '**' line-start boundary is missing — restore "
            "the anchor heading or the next block-level '**' delimiter."
        )
    return match.group(0)


def test_step_v_block_extractable() -> None:
    """The §1a step v block must be locatable via the stable anchor."""
    block = _extract_step_v_block()
    assert block, "Step v block extracted but was empty."


def test_step_v_block_contains_all_required_tokens() -> None:
    """All five operation tokens must appear in the step v block.

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

    The five tokens must appear in the order specified by R11 of the
    spec. Re-ordering any pair silently changes observable behavior
    (e.g., event emission lands in the wrong events.log if it precedes
    the EnterWorktree call). This test catches such regressions.
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
            "changes observable behavior (e.g., emitting the event "
            "before EnterWorktree completes lands the row in the wrong "
            "events.log). Restore the canonical order."
        )
