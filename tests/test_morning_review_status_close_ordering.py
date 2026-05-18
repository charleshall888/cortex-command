"""Structural ordering tests for morning-review walkthrough.md.

Asserts that backlog ticket closure (cortex-update-item status=complete) is
positioned AFTER the PR merge step (gh pr merge) in walkthrough.md source
order, and that the closure section is conditioned on a successful merge so
it is NOT reached on the unmerged-PR path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
WALKTHROUGH = (
    REPO_ROOT / "skills" / "morning-review" / "references" / "walkthrough.md"
)

MERGE_LITERAL = "gh pr merge"
CLOSE_LITERAL = "cortex-update-item"
CLOSE_ARG = "status=complete"


def _load_lines() -> list[str]:
    return WALKTHROUGH.read_text(encoding="utf-8").splitlines()


def _first_occurrence(lines: list[str], needle: str) -> int | None:
    """Return 1-based line number of first line containing needle, or None."""
    for i, line in enumerate(lines, start=1):
        if needle in line:
            return i
    return None


def _section_6b_start(lines: list[str]) -> int | None:
    """Return 1-based line number of the Section 6b heading, or None."""
    for i, line in enumerate(lines, start=1):
        if "## Section 6b" in line:
            return i
    return None


def _section_6_pr_review_start(lines: list[str]) -> int | None:
    """Return 1-based line number of the Section 6 PR Review heading, or None."""
    for i, line in enumerate(lines, start=1):
        if "## Section 6" in line and "PR Review" in line:
            return i
    return None


# ---------------------------------------------------------------------------
# Ordering test — gh pr merge appears before cortex-update-item status=complete
# ---------------------------------------------------------------------------


def test_status_complete_appears_after_merge_in_source_order() -> None:
    """cortex-update-item status=complete appears strictly after gh pr merge in walkthrough."""
    lines = _load_lines()

    merge_line = _first_occurrence(lines, MERGE_LITERAL)
    close_line = _first_occurrence(lines, CLOSE_LITERAL)

    assert merge_line is not None, (
        f"'{MERGE_LITERAL}' not found in {WALKTHROUGH.relative_to(REPO_ROOT)}"
    )
    assert close_line is not None, (
        f"'{CLOSE_LITERAL}' not found in {WALKTHROUGH.relative_to(REPO_ROOT)}"
    )

    # Confirm the close line also carries status=complete (not just cortex-update-item)
    close_line_text = lines[close_line - 1]
    assert CLOSE_ARG in close_line_text, (
        f"Line {close_line} contains '{CLOSE_LITERAL}' but not '{CLOSE_ARG}': "
        f"{close_line_text!r}"
    )

    assert close_line > merge_line, (
        f"Ordering violation: '{CLOSE_LITERAL} {CLOSE_ARG}' appears at line "
        f"{close_line} but '{MERGE_LITERAL}' first appears at line {merge_line}. "
        f"Ticket closure must come AFTER the merge step."
    )


# ---------------------------------------------------------------------------
# Section placement test — Section 6b is after Section 6 (PR Review)
# ---------------------------------------------------------------------------


def test_section_6b_appears_after_section_6_pr_review() -> None:
    """Section 6b heading appears after Section 6 PR Review heading in walkthrough."""
    lines = _load_lines()

    section_6_line = _section_6_pr_review_start(lines)
    section_6b_line = _section_6b_start(lines)

    assert section_6_line is not None, (
        "Could not find '## Section 6' PR Review heading in "
        f"{WALKTHROUGH.relative_to(REPO_ROOT)}"
    )
    assert section_6b_line is not None, (
        "Could not find '## Section 6b' heading in "
        f"{WALKTHROUGH.relative_to(REPO_ROOT)}"
    )

    assert section_6b_line > section_6_line, (
        f"Section 6b heading (line {section_6b_line}) must appear after "
        f"Section 6 PR Review heading (line {section_6_line})"
    )


# ---------------------------------------------------------------------------
# Unmerged-PR path test — Section 6b is gated on a successful merge
#
# The morning-review skill is a Claude Code skill (not runnable Python code),
# so there is no runtime path to execute. Instead we assert the structural
# gate: Section 6b's prose must contain explicit language that skips the
# section when no merge was performed. This is the walkthrough's enforcement
# mechanism for the "unmerged PR → no ticket closure" invariant.
# ---------------------------------------------------------------------------


def test_section_6b_is_gated_on_successful_merge() -> None:
    """Section 6b prose must include a skip condition for the unmerged-PR path.

    When the PR has not yet been merged (i.e., the user declined, skipped, or
    the PR was already closed/merged before this review session), the morning-
    review walkthrough must NOT invoke cortex-update-item status=complete.
    This test verifies that Section 6b contains explicit prose conditioning
    its execution on a successful merge, so the unmerged-PR path cannot reach
    the closure step.
    """
    lines = _load_lines()

    section_6b_start = _section_6b_start(lines)
    assert section_6b_start is not None, (
        "Could not find '## Section 6b' heading — cannot verify merge gate"
    )

    # Extract Section 6b content: from its heading to the next ## heading or EOF.
    section_6b_lines: list[str] = []
    for line in lines[section_6b_start:]:  # section_6b_start is 1-based; slice is 0-based
        if line.startswith("## ") and "Section 6b" not in line:
            break
        section_6b_lines.append(line)

    section_6b_text = "\n".join(section_6b_lines)

    # The section must reference skipping when merge was not performed.
    # Accept any of these canonical skip-gate phrases.
    skip_gate_phrases = [
        "Skip this section",
        "skip this section",
        "merge was declined",
        "merge was skipped",
        "no merge",
    ]
    found_gate = any(phrase in section_6b_text for phrase in skip_gate_phrases)
    assert found_gate, (
        "Section 6b does not contain a merge-gate skip condition. "
        "The section must explicitly state when it is skipped (e.g., when the "
        "merge was declined or skipped) to prevent ticket closure on the "
        "unmerged-PR path. Expected one of: "
        + ", ".join(repr(p) for p in skip_gate_phrases)
    )

    # Additionally, the close literal must NOT appear before Section 6b in
    # any unconditional context (i.e., not in Section 5's stub).
    section_5_content: list[str] = []
    in_section_5 = False
    for line in lines:
        if "## Section 5" in line:
            in_section_5 = True
        elif line.startswith("## ") and in_section_5:
            break
        if in_section_5:
            section_5_content.append(line)

    section_5_text = "\n".join(section_5_content)
    assert CLOSE_LITERAL not in section_5_text, (
        f"'{CLOSE_LITERAL}' found in Section 5 content — ticket closure "
        f"must only appear in Section 6b, not in Section 5's stub."
    )
