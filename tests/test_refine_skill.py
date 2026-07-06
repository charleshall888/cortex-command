"""Prose-shape assertions for the refine §4 complexity-value gate.

The gate lives in skills/refine/references/specify.md §4 (inlined there from
the refine SKILL.md adaptation list — specify.md's sole consumer is refine).
The gate block must (a) place the `(Recommended)` suffix instruction within
proximity of the anchor, (b) contain a "recommend" trigger inside the block,
(c) place a rationale clue ("rationale" or "because") before the first
`(Recommended)` occurrence (rationale-first ordering), and (d) not contain
`MUST decide` (negative regression guard against MUST-escalation drift, per
docs/policies.md's MUST-escalation policy).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SKILL_MD = REPO_ROOT / "skills" / "refine" / "references" / "specify.md"

ANCHOR = "Complexity/value gate"


def _slice_section_4(text: str) -> str:
    """Return the gate block — from the anchor paragraph to the next blank line.

    The gate is the paragraph beginning `**Complexity/value gate**` inside
    specify.md §4 (User Approval), ending at the paragraph boundary.
    """
    start_match = re.search(rf"^\*\*{re.escape(ANCHOR)}\*\*", text, re.MULTILINE)
    if not start_match:
        pytest.fail(f"Could not locate gate anchor '{ANCHOR}' paragraph in {SKILL_MD}")
    start = start_match.start()
    after = text[start_match.end():]
    end_match = re.search(r"\n\s*\n", after)
    end = start_match.end() + (end_match.start() if end_match else len(after))
    return text[start:end]


def _line_of(text: str, needle: str) -> int:
    """Return the 1-indexed line number of the first occurrence of needle."""
    idx = text.find(needle)
    if idx == -1:
        return -1
    return text.count("\n", 0, idx) + 1


def test_recommended_suffix_within_35_lines_of_anchor() -> None:
    """The `(Recommended)` literal appears within 35 lines after the anchor."""
    text = SKILL_MD.read_text(encoding="utf-8")
    anchor_line = _line_of(text, ANCHOR)
    assert anchor_line > 0, f"anchor '{ANCHOR}' not found"
    rec_line = _line_of(text, "(Recommended)")
    assert rec_line > 0, "'(Recommended)' literal not found"
    assert rec_line >= anchor_line, (
        f"'(Recommended)' at line {rec_line} appears before anchor at line {anchor_line}"
    )
    assert (rec_line - anchor_line) <= 35, (
        f"'(Recommended)' at line {rec_line} is more than 35 lines after "
        f"the '{ANCHOR}' anchor at line {anchor_line}"
    )


def test_recommend_trigger_inside_section_4_bullet() -> None:
    """The §4 bullet block contains a 'recommend' trigger phrase."""
    text = SKILL_MD.read_text(encoding="utf-8")
    block = _slice_section_4(text)
    assert re.search(r"\b[Ii] recommend\b|\brecommend ", block), (
        "§4 bullet block does not contain 'I recommend' or 'recommend ' "
        "trigger — recommendation-first phrasing is missing"
    )


def test_rationale_or_because_precedes_recommended() -> None:
    """A rationale clue ('rationale' or 'because') appears between the anchor
    and the first `(Recommended)` literal, proving rationale-first ordering.
    """
    text = SKILL_MD.read_text(encoding="utf-8")
    anchor_idx = text.find(ANCHOR)
    assert anchor_idx >= 0, f"anchor '{ANCHOR}' not found"
    rec_idx = text.find("(Recommended)", anchor_idx)
    assert rec_idx > anchor_idx, "'(Recommended)' literal not found after anchor"
    between = text[anchor_idx:rec_idx]
    assert re.search(r"\brationale\b|\bbecause\b", between), (
        "Neither 'rationale' nor 'because' appears between the "
        f"'{ANCHOR}' anchor and the first '(Recommended)' literal — "
        "rationale-first ordering not enforced"
    )


def test_no_must_decide_regression() -> None:
    """The §4 bullet does not contain 'MUST decide' — guards against
    MUST-escalation regression per docs/policies.md's MUST-escalation policy.
    """
    text = SKILL_MD.read_text(encoding="utf-8")
    block = _slice_section_4(text)
    assert "MUST decide" not in block, (
        "§4 bullet contains 'MUST decide' — MUST-escalation requires an "
        "evidence artifact per docs/policies.md's MUST-escalation policy; "
        "use the soft-form 'Decide' instead"
    )
