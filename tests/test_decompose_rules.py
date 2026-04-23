#!/usr/bin/env python3
"""Section-aware placement tests for R1–R7, R9 rules in decompose.md.

Parses skills/discovery/references/decompose.md into sections by heading
(handling both `##` and `### N.` heading levels), strips HTML-comment
blocks, and asserts each rule's text appears within its expected section.
A grep-only gate passes when rule text is stranded in HTML comments or
the wrong section; this module is the authoritative placement signal.
"""

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).parent.parent
DECOMPOSE_MD = REPO_ROOT / "skills" / "discovery" / "references" / "decompose.md"


def _strip_html_comments(text: str) -> str:
    """Remove all `<!-- ... -->` blocks before section parsing."""
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)


def _parse_sections(text: str) -> dict[str, str]:
    """Parse markdown into a {heading: body} map.

    Handles both `##` and `### N.` heading levels. Each section's body
    is the text from the heading line up to (but excluding) the next
    heading at the same or higher level (i.e., `##` or `###`). Headings
    that appear inside fenced code blocks are ignored so that literal
    `##`/`###` lines in examples do not split sections.
    """
    lines = text.splitlines()
    sections: dict[str, str] = {}
    current_heading: str | None = None
    current_body: list[str] = []
    in_fence = False

    heading_pattern = re.compile(r"^(#{2,3})\s+(.+?)\s*$")
    fence_pattern = re.compile(r"^\s*```")

    for line in lines:
        if fence_pattern.match(line):
            in_fence = not in_fence
            if current_heading is not None:
                current_body.append(line)
            continue

        if not in_fence:
            m = heading_pattern.match(line)
            if m:
                if current_heading is not None:
                    sections[current_heading] = "\n".join(current_body)
                current_heading = m.group(2).strip()
                current_body = []
                continue

        if current_heading is not None:
            current_body.append(line)

    if current_heading is not None:
        sections[current_heading] = "\n".join(current_body)

    return sections


@pytest.fixture(scope="module")
def sections() -> dict[str, str]:
    assert DECOMPOSE_MD.exists(), f"decompose.md not found at {DECOMPOSE_MD}"
    raw = DECOMPOSE_MD.read_text()
    stripped = _strip_html_comments(raw)
    return _parse_sections(stripped)


def _find_section(sections: dict[str, str], keyword: str) -> str:
    """Return the body of the first section whose heading contains `keyword`.

    Case-insensitive substring match on the heading text.
    """
    keyword_lower = keyword.lower()
    for heading, body in sections.items():
        if keyword_lower in heading.lower():
            return body
    pytest.fail(f"no section heading contains '{keyword}'; headings: {list(sections)}")


# ---- R1: Codebase-grounded Value norm in Constraints ----

def test_r1_norm_in_constraints(sections: dict[str, str]) -> None:
    body = _find_section(sections, "Constraints")
    assert "not sufficient Value" in body, (
        "R1: 'not sufficient Value' must appear in §Constraints"
    )


# ---- R2: Flagging rules in §2 Identify Work Items ----

def test_r2_file_line_citation_in_identify_work_items(sections: dict[str, str]) -> None:
    body = _find_section(sections, "Identify Work Items")
    assert "[file:line]" in body, (
        "R2: '[file:line]' citation anchor must appear in §2 Identify Work Items"
    )


def test_r2_premise_unverified_in_identify_work_items(sections: dict[str, str]) -> None:
    body = _find_section(sections, "Identify Work Items")
    assert "premise-unverified" in body, (
        "R2: 'premise-unverified' must appear in §2 Identify Work Items"
    )


def test_r2_canonical_pattern_in_identify_work_items(sections: dict[str, str]) -> None:
    body = _find_section(sections, "Identify Work Items")
    assert "canonical pattern" in body, (
        "R2: 'canonical pattern' surface-pattern helper must appear in §2 Identify Work Items"
    )


def test_r2_absence_of_citation_anchor_in_identify_work_items(sections: dict[str, str]) -> None:
    body = _find_section(sections, "Identify Work Items")
    assert ("absence of" in body) or ("no citation" in body), (
        "R2: absence-of-citation anchor ('absence of' or 'no citation') "
        "must appear in §2 Identify Work Items"
    )


def test_r2_adhoc_fallback_anchor_in_identify_work_items(sections: dict[str, str]) -> None:
    body = _find_section(sections, "Identify Work Items")
    assert ("ad-hoc" in body) or ("no research.md" in body) or ("R2(b)" in body), (
        "R2: ad-hoc fallback anchor ('ad-hoc' or 'no research.md' or 'R2(b)') "
        "must appear in §2 Identify Work Items"
    )


# ---- R3/R4/R6: Routing and cap logic in §2 ----

def test_r3_ask_user_question_in_identify_work_items(sections: dict[str, str]) -> None:
    body = _find_section(sections, "Identify Work Items")
    assert "AskUserQuestion" in body, (
        "R3: 'AskUserQuestion' must appear in §2 Identify Work Items"
    )


def test_r4_pre_consolidation_in_identify_work_items(sections: dict[str, str]) -> None:
    body = _find_section(sections, "Identify Work Items")
    assert ("pre-consolidation" in body) or ("before Consolidation" in body), (
        "R4: 'pre-consolidation' or 'before Consolidation' anchor "
        "must appear in §2 Identify Work Items"
    )


def test_r4_more_than_3_in_identify_work_items(sections: dict[str, str]) -> None:
    body = _find_section(sections, "Identify Work Items")
    assert "more than 3" in body, (
        "R4: 'more than 3' cap threshold must appear in §2 Identify Work Items"
    )


def test_r4_all_items_flagged_in_identify_work_items(sections: dict[str, str]) -> None:
    body = _find_section(sections, "Identify Work Items")
    assert ("all items flagged" in body) or ("all items are flagged" in body), (
        "R4: 'all items flagged' or 'all items are flagged' "
        "must appear in §2 Identify Work Items"
    )


def test_r4_return_to_research_in_identify_work_items(sections: dict[str, str]) -> None:
    body = _find_section(sections, "Identify Work Items")
    assert "Return to research" in body, (
        "R4: 'Return to research' offer must appear in §2 Identify Work Items"
    )


def test_r6_batch_review_in_identify_work_items(sections: dict[str, str]) -> None:
    body = _find_section(sections, "Identify Work Items")
    assert "Present the proposed work items" in body, (
        "R6: 'Present the proposed work items' batch-review anchor "
        "must appear in §2 Identify Work Items"
    )


def test_r3_flagged_item_in_identify_work_items(sections: dict[str, str]) -> None:
    body = _find_section(sections, "Identify Work Items")
    assert "flagged item" in body, (
        "R3: 'flagged item' must appear in §2 Identify Work Items"
    )


# ---- R7: Event names co-located with fire site in §2 ----

def test_r7_decompose_flag_in_identify_work_items(sections: dict[str, str]) -> None:
    body = _find_section(sections, "Identify Work Items")
    assert "decompose_flag" in body, (
        "R7: 'decompose_flag' event must appear in §2 Identify Work Items"
    )


def test_r7_decompose_ack_in_identify_work_items(sections: dict[str, str]) -> None:
    body = _find_section(sections, "Identify Work Items")
    assert "decompose_ack" in body, (
        "R7: 'decompose_ack' event must appear in §2 Identify Work Items"
    )


def test_r7_decompose_drop_in_identify_work_items(sections: dict[str, str]) -> None:
    body = _find_section(sections, "Identify Work Items")
    assert "decompose_drop" in body, (
        "R7: 'decompose_drop' event must appear in §2 Identify Work Items"
    )


# ---- R5: Flag propagation through consolidation in §3 ----

def test_r5_propagation_anchor_in_consolidation_review(sections: dict[str, str]) -> None:
    body = _find_section(sections, "Consolidation Review")
    assert (
        ("merged item carries the flag" in body)
        or ("flag propagat" in body)
        or ("consolidated item inherits" in body)
        or ("merged items retain" in body)
    ), (
        "R5: propagation anchor ('merged item carries the flag' or 'flag propagat' "
        "or 'consolidated item inherits' or 'merged items retain') "
        "must appear in §3 Consolidation Review"
    )


def test_r5_originating_anchor_in_consolidation_review(sections: dict[str, str]) -> None:
    body = _find_section(sections, "Consolidation Review")
    assert ("originating" in body) or ("originally flagged" in body), (
        "R5: 'originating' or 'originally flagged' anchor "
        "must appear in §3 Consolidation Review"
    )


def test_r5_invariant_anchor_in_consolidation_review(sections: dict[str, str]) -> None:
    body = _find_section(sections, "Consolidation Review")
    assert (
        ("cannot reduce" in body)
        or ("invariant" in body)
        or ("any input flag survives" in body)
    ), (
        "R5: invariant anchor ('cannot reduce' or 'invariant' or "
        "'any input flag survives') must appear in §3 Consolidation Review"
    )


# ---- R9: Dropped Items subsection within §6 Write Decomposition Record ----

def test_r9_dropped_items_subsection_in_write_decomposition_record(sections: dict[str, str]) -> None:
    body = _find_section(sections, "Write Decomposition Record")
    assert "## Dropped Items" in body, (
        "R9: '## Dropped Items' subsection heading must appear "
        "within §6 Write Decomposition Record"
    )
