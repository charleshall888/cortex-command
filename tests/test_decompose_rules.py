#!/usr/bin/env python3
"""Section-aware placement tests for the reframe-discovery decompose protocol.

Parses skills/discovery/references/decompose.md into sections by heading
(handling both `##` and `### N.` heading levels), strips HTML-comment
blocks, and asserts each rule's text appears within its expected section.

This file covers the post-reframe decompose protocol per spec
`cortex/lifecycle/reframe-discovery-to-principal-architect-posture/spec.md`:

- §2 Consume the Architecture Section (3 tests)
- §4 Single-piece branch (2 tests)
- §4 Zero-piece branch (2 tests)
- Uniform body template — Role/Integration/Edges/Touch-points (3 tests)
- R15 post-decompose batch-review gate (2 tests)
- Prescriptive-prose-check integration (2 tests)
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


@pytest.fixture(scope="module")
def raw_text() -> str:
    """Raw decompose.md text without HTML-comment stripping or section parsing."""
    return DECOMPOSE_MD.read_text()


def _find_section(sections: dict[str, str], keyword: str) -> str:
    """Return the body of the first section whose heading contains `keyword`.

    Case-insensitive substring match on the heading text.
    """
    keyword_lower = keyword.lower()
    for heading, body in sections.items():
        if keyword_lower in heading.lower():
            return body
    pytest.fail(f"no section heading contains '{keyword}'; headings: {list(sections)}")


# ---- §2: Consume the Architecture Section (3 tests) ----

def test_architecture_consumption_references_pieces_subsection(sections: dict[str, str]) -> None:
    """§2 must direct the agent to consume the approved `### Pieces` sub-section."""
    body = _find_section(sections, "Consume the Architecture Section")
    assert "### Pieces" in body, (
        "§2 must reference the `### Pieces` sub-section as the source-of-truth "
        "input to decompose"
    )


def test_architecture_consumption_one_piece_per_ticket(sections: dict[str, str]) -> None:
    """§2 must specify one ticket candidate per Pieces bullet (no re-derivation)."""
    body = _find_section(sections, "Consume the Architecture Section")
    assert "one ticket candidate" in body or "one ticket" in body, (
        "§2 must establish the one-piece-to-one-ticket-candidate mapping"
    )
    # The reframe explicitly forbids re-deriving pieces from raw findings.
    assert "re-derive" in body or "Do not re-derive" in body, (
        "§2 must forbid re-deriving pieces from raw findings"
    )


def test_architecture_consumption_piece_set_fixed_at_entry(sections: dict[str, str]) -> None:
    """§2 must establish that the piece-set is fixed at decompose entry."""
    body = _find_section(sections, "Consume the Architecture Section")
    assert "fixed at decompose entry" in body or "piece-set is fixed" in body, (
        "§2 must state the piece-set is fixed at decompose entry"
    )
    # And the escape valve is to return to research, not silent mutation.
    assert "return to the research phase" in body or "return to research" in body.lower(), (
        "§2 must direct agents to return to research rather than mutate the set silently"
    )


# ---- §4: Single-piece branch (2 tests) ----

def test_single_piece_branch_no_epic(sections: dict[str, str]) -> None:
    """§4 single-piece branch creates one ticket, no epic."""
    body = _find_section(sections, "Determine Grouping")
    assert "Single-piece branch" in body or "single-piece" in body.lower(), (
        "§4 must document the single-piece branch"
    )
    # No epic for piece_count = 1.
    assert "No epic" in body or "no epic" in body, (
        "single-piece branch must explicitly state no epic is created"
    )


def test_single_piece_branch_piece_count_one(sections: dict[str, str]) -> None:
    """§4 single-piece branch names the piece_count = 1 trigger."""
    body = _find_section(sections, "Determine Grouping")
    assert "piece_count = 1" in body or "piece_count=1" in body, (
        "§4 single-piece branch must name the piece_count = 1 trigger explicitly"
    )


# ---- §4: Zero-piece branch (2 tests) ----

def test_zero_piece_branch_two_subcases(sections: dict[str, str]) -> None:
    """§4 zero-piece branch documents fold-into and no-tickets verdict sub-cases."""
    body = _find_section(sections, "Determine Grouping")
    assert "Zero-piece branch" in body or "zero-piece" in body.lower(), (
        "§4 must document the zero-piece branch"
    )
    assert "Fold-into" in body or "fold-into" in body.lower(), (
        "zero-piece branch must document the fold-into-#N sub-case"
    )
    assert "No-tickets verdict" in body or "no-tickets" in body.lower(), (
        "zero-piece branch must document the no-tickets verdict sub-case"
    )


def test_zero_piece_branch_decomposed_md_still_written(sections: dict[str, str]) -> None:
    """§4 zero-piece branch must specify that decomposed.md is still written as audit trail."""
    body = _find_section(sections, "Determine Grouping")
    assert "still written" in body or "decomposed.md" in body, (
        "zero-piece branch must specify decomposed.md is still written as audit trail"
    )
    # Machine-readable frontmatter marker.
    assert "decomposition_verdict: zero-piece" in body, (
        "zero-piece branch must specify the `decomposition_verdict: zero-piece` "
        "frontmatter marker"
    )


# ---- Uniform body template — Role/Integration/Edges/Touch-points (3 tests) ----

def test_uniform_template_four_section_headers_present(raw_text: str) -> None:
    """The uniform body template names all four section headers at column 0."""
    # The template block in §2 lists these as `^## Role$`, `^## Integration$`, etc.
    assert re.search(r"^## Role$", raw_text, re.MULTILINE), "uniform template missing `## Role`"
    assert re.search(r"^## Integration$", raw_text, re.MULTILINE), (
        "uniform template missing `## Integration`"
    )
    assert re.search(r"^## Edges$", raw_text, re.MULTILINE), "uniform template missing `## Edges`"
    assert re.search(r"^## Touch points", raw_text, re.MULTILINE), (
        "uniform template missing `## Touch points`"
    )


def test_uniform_template_no_defect_novel_binary(sections: dict[str, str]) -> None:
    """The uniform template applies to all pieces — no defect/novel branching."""
    body = _find_section(sections, "Consume the Architecture Section")
    assert "uniform" in body.lower(), (
        "§2 must describe the template as uniform across all pieces"
    )
    # The reframe explicitly removes the defect-vs-novel binary.
    assert (
        "no defect-vs-novel" in body.lower()
        or "no defect/novel" in body.lower()
        or "no per-shape branching" in body.lower()
    ), (
        "§2 must explicitly state no defect-vs-novel or per-shape branching"
    )


def test_uniform_template_edge_vs_touchpoint_distinction(sections: dict[str, str]) -> None:
    """§2 documents the Edge-vs-Touch-point semantic distinction with a worked example."""
    body = _find_section(sections, "Consume the Architecture Section")
    assert "Edge-vs-Touch-point" in body or "Edge-vs-Touch" in body, (
        "§2 must document the Edge-vs-Touch-point semantic distinction"
    )
    # Edges name contracts by name; Touch points cite paths.
    assert "naming each contract surface by name" in body or "contract surface by name" in body, (
        "Edge-vs-Touch-point distinction must specify Edges names contracts by name"
    )
    # Worked example must show the boundary in action.
    assert "Worked example" in body, (
        "§2 must include a worked example illustrating the Edge-vs-Touch-point boundary"
    )
    # The worked example shows path:line in Touch points (not Edges).
    assert "## Touch points" in body and "## Edges" in body, (
        "worked example must show both ## Edges and ## Touch points sections"
    )


# ---- R15 post-decompose batch-review gate (2 tests) ----

def test_r15_batch_review_gate_three_options_documented(sections: dict[str, str]) -> None:
    """§5 documents the R15 gate's three options (approve-all/revise-piece/drop-piece)."""
    body = _find_section(sections, "Create Backlog Tickets")
    # All three options appear by literal name.
    assert "approve-all" in body, "R15 gate must document the approve-all option"
    assert "revise-piece" in body, "R15 gate must document the revise-piece <N> option"
    assert "drop-piece" in body, "R15 gate must document the drop-piece <N> option"
    # The gate is user-blocking before any tickets commit.
    assert "user-blocking" in body.lower(), (
        "R15 gate must be documented as user-blocking"
    )
    # Revise re-presents the FULL batch, not just ticket N.
    assert "full batch" in body.lower() or "FULL batch" in body, (
        "revise-piece must re-present the full batch (not just ticket N)"
    )


def test_r15_batch_review_gate_emits_checkpoint_event(sections: dict[str, str]) -> None:
    """§5 names the `approval_checkpoint_responded` event with `decompose-commit` checkpoint."""
    body = _find_section(sections, "Create Backlog Tickets")
    assert "approval_checkpoint_responded" in body, (
        "R15 gate must emit the approval_checkpoint_responded event by name"
    )
    assert "decompose-commit" in body, (
        "R15 gate must specify the `checkpoint: decompose-commit` field"
    )


# ---- Prescriptive-prose-check integration (2 tests) ----

def test_prescriptive_prose_check_named_in_section_5(sections: dict[str, str]) -> None:
    """§5 names the `bin/cortex-check-prescriptive-prose` scanner and its pre-commit role."""
    body = _find_section(sections, "Create Backlog Tickets")
    assert "cortex-check-prescriptive-prose" in body, (
        "§5 must reference the cortex-check-prescriptive-prose scanner by name"
    )
    # Pre-commit hook is the second-actor surface.
    assert "pre-commit" in body.lower(), (
        "§5 must establish the pre-commit hook as the second-actor surface"
    )


def test_prescriptive_prose_check_section_partitioning(sections: dict[str, str]) -> None:
    """§5 documents the forbidden/permitted sections governing the LEX-1 scanner."""
    body = _find_section(sections, "Create Backlog Tickets")
    # Forbidden sections per ticket body.
    assert "Forbidden sections" in body, (
        "§5 must name the Forbidden sections (Role, Integration, Edges)"
    )
    assert "## Role" in body and "## Integration" in body and "## Edges" in body, (
        "§5 must enumerate the forbidden sections by their header literals"
    )
    # Permitted section is Touch points.
    assert "Permitted section" in body, (
        "§5 must name the Permitted section (Touch points)"
    )
    assert "## Touch points" in body, (
        "§5 must name `## Touch points` as the permitted section literal"
    )
