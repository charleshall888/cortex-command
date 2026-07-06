"""Structural ordering tests for morning-review walkthrough.md.

Asserts that backlog ticket closure — now the
``cortex-morning-review-close-tickets`` verb call, which owns the
``cortex-update-item``-based close internally — is positioned AFTER the PR
merge step (``gh pr merge``) in walkthrough.md source order, and that the
closure section is conditioned on a successful merge so it is NOT reached on
the unmerged-PR path. The close operation moved FROM a raw per-feature
``cortex-update-item {id} --status complete`` invocation INTO the verb (see
``cortex_command.overnight.close_tickets``); the ordering property being
guarded — ticket closure never precedes a confirmed merge — is unchanged, so
this file was updated to anchor on the verb's invocation literal rather than
the raw close command it now wraps.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
WALKTHROUGH = (
    REPO_ROOT / "skills" / "morning-review" / "references" / "walkthrough.md"
)
SKILL = REPO_ROOT / "skills" / "morning-review" / "SKILL.md"

MERGE_LITERAL = "gh pr merge"
CLOSE_LITERAL = "cortex-morning-review-close-tickets"
CLOSE_ARG = "--backend"

# Spelling-agnostic close pattern. The ticket-close command has TWO live
# spellings of the same operation — the console form
# (cortex-update-item … --status complete) and the module form
# (python3 -m cortex_command.backlog.update_item … --status complete). An
# absence guard that matched only the console literal would let a module-form
# reintroduction slip back into SKILL.md green. `update[-_]item` matches both
# `update-item` and `update_item`; the trailing `--status complete` anchors on
# the terminal-close argument. Matched per-line, case-insensitively, mirroring
# the `grep -crEi "update[-_]item.*--status complete"` acceptance check.
CLOSE_PATTERN = re.compile(r"update[-_]item.*--status complete", re.IGNORECASE)


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
# Ordering test — gh pr merge appears before the
# cortex-morning-review-close-tickets verb call
# ---------------------------------------------------------------------------


def test_status_complete_appears_after_merge_in_source_order() -> None:
    """cortex-morning-review-close-tickets appears strictly after gh pr merge in walkthrough."""
    lines = _load_lines()

    merge_line = _first_occurrence(lines, MERGE_LITERAL)
    close_line = _first_occurrence(lines, CLOSE_LITERAL)

    assert merge_line is not None, (
        f"'{MERGE_LITERAL}' not found in {WALKTHROUGH.relative_to(REPO_ROOT)}"
    )
    assert close_line is not None, (
        f"'{CLOSE_LITERAL}' not found in {WALKTHROUGH.relative_to(REPO_ROOT)}"
    )

    # Confirm the close line is the actual invocation (carries --backend), not
    # just a passing mention of the verb's name in prose.
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
    review walkthrough must NOT invoke
    python3 -m cortex_command.backlog.update_item <id> --status complete.
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


# ---------------------------------------------------------------------------
# SKILL.md single-source guard (Req 5)
#
# These tests protect two structural invariants of skills/morning-review/
# SKILL.md so the pre-merge close (in EITHER the console `update-item` or the
# module `update_item` spelling) and a mis-placed/duplicate §6b reference
# cannot silently return:
#   (a) no close literal in either spelling appears anywhere in SKILL.md; and
#   (b) exactly one `Section 6b` reference appears, after the "PR Merge" step
#       (semantic-heading anchor — SKILL.md carries no `gh pr merge` literal
#       and step numbers are not durable anchors).
# The positive-control tests below prove these guards are DISCRIMINATING every
# CI run, so a mis-written (never-matching) guard fails loud rather than
# passing vacuously green.
# ---------------------------------------------------------------------------


def _close_literal_present(text: str) -> bool:
    """Return True if any line carries a close literal in either spelling."""
    return any(CLOSE_PATTERN.search(line) for line in text.splitlines())


def _section_6b_ordering_violation(text: str) -> str | None:
    """Return a violation message if SKILL.md-shaped `text` breaks the
    single-source / post-merge-ordering invariant for `Section 6b`, else None.

    Invariant: exactly one `Section 6b` reference, appearing after the
    `PR Merge` heading (semantic anchor — never a step number).
    """
    lines = text.splitlines()
    sixb_lines = [
        i for i, line in enumerate(lines, start=1) if "Section 6b" in line
    ]
    if len(sixb_lines) != 1:
        return (
            f"expected exactly one 'Section 6b' reference, found "
            f"{len(sixb_lines)} (lines {sixb_lines})"
        )

    merge_line = None
    for i, line in enumerate(lines, start=1):
        if "PR Merge" in line:
            merge_line = i
            break
    if merge_line is None:
        return "no 'PR Merge' heading found to anchor ordering"

    sixb_line = sixb_lines[0]
    if sixb_line <= merge_line:
        return (
            f"'Section 6b' reference at line {sixb_line} is not after the "
            f"'PR Merge' heading at line {merge_line} (pre-merge closure "
            f"reference must not survive)"
        )
    return None


def test_skill_md_has_no_close_literal_in_either_spelling() -> None:
    """SKILL.md carries no ticket-close literal in console or module spelling."""
    text = SKILL.read_text(encoding="utf-8")
    assert not _close_literal_present(text), (
        f"A close literal ('update[-_]item … --status complete', either "
        f"spelling) appears in {SKILL.relative_to(REPO_ROOT)}. Backlog-ticket "
        f"closure must be single-sourced to walkthrough §6b (post-merge); the "
        f"pre-merge close must not return to SKILL.md."
    )


def test_skill_md_section_6b_single_and_post_merge() -> None:
    """SKILL.md references `Section 6b` exactly once, after the PR Merge step."""
    text = SKILL.read_text(encoding="utf-8")
    violation = _section_6b_ordering_violation(text)
    assert violation is None, (
        f"Section 6b single-source/ordering invariant broken in "
        f"{SKILL.relative_to(REPO_ROOT)}: {violation}"
    )


# ---------------------------------------------------------------------------
# Durable positive controls (Req 5 — hardening from critical-review)
#
# These live permanently in the test file and run in CI every time. They assert
# the detection helpers' behavior against fixed synthetic literals so a
# mis-written guard (e.g. a close pattern that silently never matches, or an
# ordering check that never flags) fails here rather than passing green while
# providing no real protection. They are NOT self-sealing: the synthetic
# samples are fixed inline in the test, not artifacts produced to dodge
# verification.
# ---------------------------------------------------------------------------


def test_positive_control_close_pattern_matches_both_spellings() -> None:
    """The close-detection pattern matches synthetic close samples in BOTH
    the console (`update-item`) and module (`update_item`) spellings."""
    console_sample = "cortex-update-item 078 --status complete"
    module_sample = (
        "python3 -m cortex_command.backlog.update_item 078 --status complete"
    )
    assert _close_literal_present(console_sample), (
        f"Close pattern failed to match the console-spelling sample "
        f"{console_sample!r} — the guard would be blind to a console-form "
        f"reintroduction."
    )
    assert _close_literal_present(module_sample), (
        f"Close pattern failed to match the module-spelling sample "
        f"{module_sample!r} — the guard would be blind to a module-form "
        f"reintroduction."
    )


def test_positive_control_ordering_check_flags_pre_merge_reference() -> None:
    """The single-source/ordering check flags a synthetic SKILL.md-shaped
    string that carries a §6b reference BEFORE the PR Merge step."""
    synthetic_pre_merge = "\n".join(
        [
            "### Step 4: Auto-Close Backlog Tickets",
            "Close each ticket — see Section 6b for the closer.",
            "### Step 6: PR Merge",
            "Locate the PR and offer to merge it.",
        ]
    )
    assert _section_6b_ordering_violation(synthetic_pre_merge) is not None, (
        "Ordering check failed to flag a synthetic pre-merge 'Section 6b' "
        "reference — the guard would not catch an incompletely-relocated "
        "(lingering pre-merge) §6b reference."
    )
