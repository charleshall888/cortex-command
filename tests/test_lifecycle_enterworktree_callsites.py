"""Parity test pinning EnterWorktree call-site co-location with its preconditions.

Every literal ``EnterWorktree(...)`` call site under ``skills/lifecycle/``
must be co-located with the worktree-creation and precondition-probe
surface that the auto-enter sequence depends on. Concretely, within
±60 lines of each call site we require:

  (a) the ``create_worktree`` token — proving the worktree the call
      enters is materialized by the same skill prose, not by an
      out-of-band path, and
  (b) at least one of the structural precondition tokens
      (``show-toplevel``, ``git-common-dir``, ``verify-worktree-auth``,
      ``EnterWorktree skipped``) — proving the precondition probes
      and fallback diagnostic are co-located with the call rather
      than separated into a remote section that could be removed
      without the call site noticing.

This catches wholesale removals or splits of the auto-enter sequence
that the step-v ordering parity test (``test_lifecycle_step_v_ordering.py``)
cannot — that test pins ordering inside a single anchored block, while
this test pins the existence of the surrounding scaffolding regardless
of how the block is named or anchored. The ±60 line proximity allows
local edits inside the auto-enter section but catches scenarios where
EnterWorktree is moved into a remote section away from its supporting
context (per R14 of
``cortex/lifecycle/lifecycle-implement-auto-enter-worktree-via/spec.md``).

Pattern: regex ``EnterWorktree\\s*\\(`` (open-paren required to
distinguish call sites from descriptive prose mentions like
``"EnterWorktree call"`` or ``"EnterWorktree skipped"``).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SKILLS_LIFECYCLE_DIR = REPO_ROOT / "skills" / "lifecycle"

# Regex matches a literal ``EnterWorktree(`` token, optionally with
# whitespace between the identifier and the open-paren. The open-paren
# is load-bearing — it distinguishes the call site from descriptive
# prose like "EnterWorktree skipped" or "EnterWorktree's schema".
_CALL_SITE_PATTERN = re.compile(r"EnterWorktree\s*\(")

# Proximity radius in lines. The call site must have these tokens
# within ±_PROXIMITY_LINES lines.
_PROXIMITY_LINES = 60

# Required co-located tokens (a): the worktree-creation token. The
# call site must enter a worktree that was materialized by the same
# skill prose's create_worktree() invocation.
_CREATE_WORKTREE_TOKEN = "create_worktree"

# Required co-located tokens (b): at least one of the precondition
# probe / fallback tokens must appear in the proximity window. These
# anchor the auto-enter sequence's preconditions and fallback path —
# their absence indicates the EnterWorktree call has been split from
# its supporting context.
_PRECONDITION_TOKENS = (
    "show-toplevel",
    "git-common-dir",
    "verify-worktree-auth",
    "EnterWorktree skipped",
)


def _iter_lifecycle_markdown_files() -> list[Path]:
    """Return all markdown files under ``skills/lifecycle/`` for scanning."""
    return sorted(SKILLS_LIFECYCLE_DIR.rglob("*.md"))


def _find_call_sites() -> list[tuple[Path, int, list[str]]]:
    """Return ``(path, match_line_number, file_lines)`` for every call site.

    ``match_line_number`` is 1-indexed (matches ``cat -n`` / editor
    conventions). ``file_lines`` is the full file's line list, included
    so the caller can slice the proximity window without re-reading.
    """
    call_sites: list[tuple[Path, int, list[str]]] = []
    for md_path in _iter_lifecycle_markdown_files():
        content = md_path.read_text(encoding="utf-8")
        lines = content.splitlines()
        # Build a list of (1-indexed) line numbers where each match
        # falls. We iterate over the regex matches on the full content
        # and convert each match's char-offset to a line number by
        # counting newlines up to that offset.
        for match in _CALL_SITE_PATTERN.finditer(content):
            line_number = content.count("\n", 0, match.start()) + 1
            call_sites.append((md_path, line_number, lines))
    return call_sites


def _proximity_window(lines: list[str], line_number: int) -> str:
    """Return the joined ±_PROXIMITY_LINES window around ``line_number``.

    ``line_number`` is 1-indexed. The window includes the line itself
    plus _PROXIMITY_LINES lines before and after, clipped to file bounds.
    """
    # Convert to 0-indexed for slicing.
    center = line_number - 1
    start = max(0, center - _PROXIMITY_LINES)
    end = min(len(lines), center + _PROXIMITY_LINES + 1)
    return "\n".join(lines[start:end])


def test_at_least_one_enterworktree_callsite_exists() -> None:
    """At least one literal ``EnterWorktree(`` call site must exist.

    The auto-enter sequence is the central deliverable of the
    auto-enter lifecycle. Zero call sites under ``skills/lifecycle/``
    means the wiring has been removed — surface that loud and clear
    rather than letting the per-call-site loop silently pass on an
    empty iteration.
    """
    call_sites = _find_call_sites()
    assert call_sites, (
        "No ``EnterWorktree(`` call sites found anywhere under "
        f"{SKILLS_LIFECYCLE_DIR.relative_to(REPO_ROOT)}. The auto-enter "
        "wiring landed by T10 of the lifecycle-implement-auto-enter-"
        "worktree-via feature has been removed. Restore the call site "
        "in ``skills/lifecycle/references/implement.md`` §1a step v."
    )


@pytest.mark.parametrize(
    "call_site",
    _find_call_sites(),
    ids=lambda cs: f"{cs[0].relative_to(REPO_ROOT)}:{cs[1]}",
)
def test_callsite_has_create_worktree_within_proximity(
    call_site: tuple[Path, int, list[str]],
) -> None:
    """Each call site must have ``create_worktree`` within ±60 lines.

    The token's presence proves the worktree the EnterWorktree call
    targets is materialized by the same skill-prose surface. If
    ``create_worktree`` is moved to a remote section (or removed
    entirely), the call site loses its connection to the worktree-
    creation step and the auto-enter sequence becomes structurally
    incoherent.
    """
    md_path, line_number, lines = call_site
    window = _proximity_window(lines, line_number)
    assert _CREATE_WORKTREE_TOKEN in window, (
        f"EnterWorktree call site at "
        f"{md_path.relative_to(REPO_ROOT)}:{line_number} has no "
        f"``{_CREATE_WORKTREE_TOKEN}`` token within ±{_PROXIMITY_LINES} "
        "lines. The auto-enter sequence requires the worktree-creation "
        "surface to be co-located with the call site — either restore "
        "the ``create_worktree`` reference into the proximity window "
        "or move the EnterWorktree call back near the creation step. "
        "See R14 of "
        "``cortex/lifecycle/lifecycle-implement-auto-enter-worktree-via"
        "/spec.md`` for the structural contract this test enforces."
    )


@pytest.mark.parametrize(
    "call_site",
    _find_call_sites(),
    ids=lambda cs: f"{cs[0].relative_to(REPO_ROOT)}:{cs[1]}",
)
def test_callsite_has_precondition_token_within_proximity(
    call_site: tuple[Path, int, list[str]],
) -> None:
    """Each call site must have ≥1 precondition token within ±60 lines.

    At least one of ``show-toplevel``, ``git-common-dir``,
    ``verify-worktree-auth``, or ``EnterWorktree skipped`` must appear
    in the proximity window. Their absence indicates the precondition
    probes and fallback diagnostic have been split from the call site —
    a structural regression that would let the EnterWorktree call fire
    without its supporting authorization and already-in-worktree probes
    (or without a documented fallback when they fail).
    """
    md_path, line_number, lines = call_site
    window = _proximity_window(lines, line_number)
    found_tokens = [tok for tok in _PRECONDITION_TOKENS if tok in window]
    assert found_tokens, (
        f"EnterWorktree call site at "
        f"{md_path.relative_to(REPO_ROOT)}:{line_number} has none of "
        f"the precondition tokens {list(_PRECONDITION_TOKENS)!r} "
        f"within ±{_PROXIMITY_LINES} lines. The auto-enter sequence "
        "requires at least one precondition-probe or fallback marker "
        "to be co-located with the call site, proving the probes + "
        "fallback diagnostic have not been split into a remote section. "
        "Restore at least one of the listed tokens into the proximity "
        "window, or move the EnterWorktree call back near its "
        "supporting context. See R14 of "
        "``cortex/lifecycle/lifecycle-implement-auto-enter-worktree-via"
        "/spec.md`` for the structural contract this test enforces."
    )
