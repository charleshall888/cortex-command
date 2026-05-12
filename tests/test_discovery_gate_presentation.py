"""Structural tests for the improve-discovery-gate-presentation Phase 1 changes.

Phase 1 of `improve-discovery-gate-presentation` reorders the discovery
Research→Decompose gate so the user-visible payload leads with a
`## Headline Finding` section above `## Architecture`, and rewords `drop`'s
gate-option description to neutral-terminus dual-use semantics. The Phase 1
acceptance criteria (R1, R2, R3) are structural-prose checks against the
canonical source files:

- R1: `skills/discovery/references/research.md` contains `## Headline Finding`
  above `## Architecture` and carries a stable marker phrase under the slot
  that anchors the content-population directive.
- R2: `skills/discovery/SKILL.md` R4 gate-prose section names
  `## Headline Finding` before `## Architecture`.
- R3: `skills/discovery/SKILL.md` R4 gate enumeration's `drop` description
  contains the stable dual-use marker phrase indicating both legitimate uses
  (close because research is sufficient AND abandon outright).

These tests intentionally pin verbatim marker phrases finalized in Tasks 1
and 2 of the lifecycle (commits 2d79b91e and e84a2484). If the canonical
text is reworded, this test fails loudly and points reviewers at the spec
acceptance criteria.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RESEARCH_TEMPLATE = REPO_ROOT / "skills" / "discovery" / "references" / "research.md"
DISCOVERY_SKILL = REPO_ROOT / "skills" / "discovery" / "SKILL.md"

# Marker phrases pinned verbatim from Task 1 and Task 2 commits. These are
# part of the canonical contract — if they change, downstream consumers
# (this test, the spec acceptance grep, any future tooling that keys off
# the slot) must update in lockstep.
R1_HEADLINE_MARKER_PHRASE = (
    "State the verdict and the one or two key findings supporting it"
)
R3_DROP_DUAL_USE_MARKER_PHRASE = (
    "close discovery when research is sufficient and no tickets are warranted,"
    " OR abandon outright"
)

HEADLINE_HEADING = "## Headline Finding"
ARCHITECTURE_HEADING = "## Architecture"


def _line_index(text: str, needle: str) -> int:
    """Return the 1-based line number of the first line equal to ``needle``.

    Returns -1 when no line matches. Uses exact-line equality (stripped of
    trailing whitespace) so partial-match collisions in narrative prose do
    not pass.
    """
    for idx, line in enumerate(text.splitlines(), start=1):
        if line.rstrip() == needle:
            return idx
    return -1


def _first_substring_line(text: str, needle: str) -> int:
    """Return the 1-based line number of the first line containing ``needle``.

    Returns -1 when no line contains the substring. Used for the R2 prose
    check where the heading is mentioned inside backticks within a sentence.
    """
    for idx, line in enumerate(text.splitlines(), start=1):
        if needle in line:
            return idx
    return -1


def test_r1_headline_finding_template_slot() -> None:
    """R1: template has `## Headline Finding` above `## Architecture` with marker phrase."""
    assert RESEARCH_TEMPLATE.is_file(), (
        f"Expected research template at {RESEARCH_TEMPLATE.relative_to(REPO_ROOT)}"
    )
    text = RESEARCH_TEMPLATE.read_text(encoding="utf-8")

    headline_line = _line_index(text, HEADLINE_HEADING)
    architecture_line = _line_index(text, ARCHITECTURE_HEADING)

    assert headline_line > 0, (
        f"R1 check: {RESEARCH_TEMPLATE.relative_to(REPO_ROOT)} is missing the "
        f"`{HEADLINE_HEADING}` heading (exact-line match). The Phase 1 "
        "acceptance criterion requires this slot to exist in the template."
    )
    assert architecture_line > 0, (
        f"R1 check: {RESEARCH_TEMPLATE.relative_to(REPO_ROOT)} is missing the "
        f"`{ARCHITECTURE_HEADING}` heading (exact-line match)."
    )
    assert headline_line < architecture_line, (
        f"R1 check: `{HEADLINE_HEADING}` (line {headline_line}) must appear "
        f"ABOVE `{ARCHITECTURE_HEADING}` (line {architecture_line}) in "
        f"{RESEARCH_TEMPLATE.relative_to(REPO_ROOT)}. The gate reads the "
        "headline first."
    )
    assert R1_HEADLINE_MARKER_PHRASE in text, (
        f"R1 check: {RESEARCH_TEMPLATE.relative_to(REPO_ROOT)} must carry the "
        f"stable marker phrase {R1_HEADLINE_MARKER_PHRASE!r} under the "
        f"`{HEADLINE_HEADING}` slot. This phrase anchors the "
        "content-population directive the spec requires."
    )

    # The marker phrase must actually live under the Headline Finding slot,
    # not somewhere else in the file. Slice from the slot heading to the
    # next H2 and require the phrase appears in that window.
    lines = text.splitlines()
    slot_body_lines: list[str] = []
    in_slot = False
    for line in lines:
        if line.rstrip() == HEADLINE_HEADING:
            in_slot = True
            continue
        if in_slot and line.startswith("## "):
            break
        if in_slot:
            slot_body_lines.append(line)
    slot_body = "\n".join(slot_body_lines)
    assert R1_HEADLINE_MARKER_PHRASE in slot_body, (
        f"R1 check: the marker phrase {R1_HEADLINE_MARKER_PHRASE!r} must "
        f"appear in the body UNDER `{HEADLINE_HEADING}`, not elsewhere in "
        f"{RESEARCH_TEMPLATE.relative_to(REPO_ROOT)}."
    )


def test_r2_gate_prose_orders_headline_finding_before_architecture() -> None:
    """R2: SKILL.md R4 gate prose names Headline Finding before Architecture."""
    assert DISCOVERY_SKILL.is_file(), (
        f"Expected discovery skill at {DISCOVERY_SKILL.relative_to(REPO_ROOT)}"
    )
    text = DISCOVERY_SKILL.read_text(encoding="utf-8")

    headline_mention_line = _first_substring_line(text, "## Headline Finding")
    architecture_mention_line = _first_substring_line(text, "## Architecture")

    assert headline_mention_line > 0, (
        f"R2 check: {DISCOVERY_SKILL.relative_to(REPO_ROOT)} must mention "
        f"`## Headline Finding` in the R4 gate-prose section."
    )
    assert architecture_mention_line > 0, (
        f"R2 check: {DISCOVERY_SKILL.relative_to(REPO_ROOT)} must mention "
        f"`## Architecture` in the R4 gate-prose section."
    )
    assert headline_mention_line <= architecture_mention_line, (
        f"R2 check: first mention of `## Headline Finding` "
        f"(line {headline_mention_line}) must appear at or before the first "
        f"mention of `## Architecture` (line {architecture_mention_line}) in "
        f"{DISCOVERY_SKILL.relative_to(REPO_ROOT)}. The gate's first content "
        "section is Headline Finding."
    )


def test_r3_drop_description_has_dual_use_marker() -> None:
    """R3: SKILL.md R4 gate's `drop` description carries the dual-use marker phrase."""
    assert DISCOVERY_SKILL.is_file(), (
        f"Expected discovery skill at {DISCOVERY_SKILL.relative_to(REPO_ROOT)}"
    )
    text = DISCOVERY_SKILL.read_text(encoding="utf-8")

    assert R3_DROP_DUAL_USE_MARKER_PHRASE in text, (
        f"R3 check: {DISCOVERY_SKILL.relative_to(REPO_ROOT)} must contain the "
        f"stable dual-use marker phrase "
        f"{R3_DROP_DUAL_USE_MARKER_PHRASE!r} in `drop`'s gate-option "
        "description. The phrase encodes that `drop` is a neutral terminus, "
        "not a failure-only exit."
    )

    # The marker phrase must live on the `drop` bullet — guard against a
    # rewording that moves the phrase to a different gate option's bullet.
    for line in text.splitlines():
        if R3_DROP_DUAL_USE_MARKER_PHRASE in line:
            assert "`drop`" in line, (
                "R3 check: the dual-use marker phrase appears in "
                f"{DISCOVERY_SKILL.relative_to(REPO_ROOT)} but not on a line "
                "that also references `drop`. The phrase must describe the "
                f"`drop` option specifically. Offending line: {line!r}"
            )
            break
