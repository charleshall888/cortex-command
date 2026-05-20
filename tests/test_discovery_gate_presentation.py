"""Structural tests for the discovery gate presentation and brief-generation changes.

Phase 1 of `improve-discovery-gate-presentation` introduced a
Research→Decompose gate with neutral-terminus `drop` semantics (R3).

Phase 2 of `discovery-output-density-investigate-author-centric` removed the
`## Headline Finding` section and DR-N numbering from the research template
and replaced the dense-section gate display with a fresh-context brief
generator (Tasks 11–13). The structural pins updated in lockstep:

- R3: `skills/discovery/SKILL.md` R4 gate enumeration's `drop` description
  contains the stable dual-use marker phrase indicating both legitimate uses
  (close because research is sufficient AND abandon outright).
- BRIEF_INVOCATION: `skills/discovery/SKILL.md` contains the stable substring
  that anchors the brief-generation CLI invocation prose.
- GATE_OPTIONS: `skills/discovery/SKILL.md` contains the stable `--response`
  argument substring that enumerates all four gate options.

These tests intentionally pin verbatim marker phrases. If the canonical text
is reworded, this test fails loudly and points reviewers at the spec
acceptance criteria.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DISCOVERY_SKILL = REPO_ROOT / "skills" / "discovery" / "SKILL.md"

# Marker phrases pinned verbatim. These are part of the canonical contract —
# if they change, downstream consumers (this test, any future tooling that
# keys off the slot) must update in lockstep.

R3_DROP_DUAL_USE_MARKER_PHRASE = (
    "close discovery when research is sufficient and no tickets are warranted,"
    " OR abandon outright"
)

# Stable substring anchoring the brief-generation CLI invocation in SKILL.md.
BRIEF_INVOCATION_MARKER_PHRASE = "cortex-discovery generate-brief"

# Stable substring from the --response argument example enumerating all four
# gate options (unspaced pipe form as it appears on line 94 of SKILL.md).
# Resolution (a) per task authoring note: use the actual form that appears in
# the file rather than the spaced-pipe spec-authoring artifact.
GATE_OPTIONS_MARKER_PHRASE = "<approve|revise|drop|promote-sub-topic>"


def _first_substring_line(text: str, needle: str) -> int:
    """Return the 1-based line number of the first line containing ``needle``.

    Returns -1 when no line contains the substring.
    """
    for idx, line in enumerate(text.splitlines(), start=1):
        if needle in line:
            return idx
    return -1


def test_brief_invocation_marker_present_in_skill() -> None:
    """BRIEF_INVOCATION: SKILL.md contains the brief-generation CLI invocation prose."""
    assert DISCOVERY_SKILL.is_file(), (
        f"Expected discovery skill at {DISCOVERY_SKILL.relative_to(REPO_ROOT)}"
    )
    text = DISCOVERY_SKILL.read_text(encoding="utf-8")

    assert BRIEF_INVOCATION_MARKER_PHRASE in text, (
        f"BRIEF_INVOCATION check: {DISCOVERY_SKILL.relative_to(REPO_ROOT)} must "
        f"contain the stable marker phrase {BRIEF_INVOCATION_MARKER_PHRASE!r}. "
        "This phrase anchors the brief-generation CLI invocation that drives the "
        "Research→Decompose gate's first content section."
    )


def test_gate_options_marker_present_in_skill() -> None:
    """GATE_OPTIONS: SKILL.md contains the four-option --response argument string."""
    assert DISCOVERY_SKILL.is_file(), (
        f"Expected discovery skill at {DISCOVERY_SKILL.relative_to(REPO_ROOT)}"
    )
    text = DISCOVERY_SKILL.read_text(encoding="utf-8")

    assert GATE_OPTIONS_MARKER_PHRASE in text, (
        f"GATE_OPTIONS check: {DISCOVERY_SKILL.relative_to(REPO_ROOT)} must "
        f"contain the stable marker phrase {GATE_OPTIONS_MARKER_PHRASE!r}. "
        "This substring appears in the --response argument example and enumerates "
        "all four gate options (approve, revise, drop, promote-sub-topic)."
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
