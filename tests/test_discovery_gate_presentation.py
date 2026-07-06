"""Structural tests for the discovery gate presentation and brief-generation changes.

Phase 1 of `improve-discovery-gate-presentation` introduced a
Research→Decompose gate with neutral-terminus `drop` semantics (R3).

Phase 2 of `discovery-output-density-investigate-author-centric` removed the
`## Headline Finding` section and DR-N numbering from the research template
and replaced the dense-section gate display with a fresh-context brief
generator (Tasks 11–13). The structural pins updated in lockstep:

- R3: the R4 gate enumeration's `drop` description contains the stable
  dual-use marker phrase indicating both legitimate uses (close because
  research is sufficient AND abandon outright).
- BRIEF_INVOCATION: contains the stable substring that anchors the
  brief-generation CLI invocation prose.
- GATE_OPTIONS: contains the stable `--response` argument substring that
  enumerates all four gate options.

The `progressive-disclosure-discovery-overnight` restructuring extracted the
full R4 gate (previously inline in `skills/discovery/SKILL.md`) to
`skills/discovery/references/decompose-gate.md`, read lazily at the
Research/Decompose phase boundary instead of loaded on every invocation.
These pins retarget to that file — the assertions are unchanged.

These tests intentionally pin verbatim marker phrases. If the canonical text
is reworded, this test fails loudly and points reviewers at the spec
acceptance criteria.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DECOMPOSE_GATE = REPO_ROOT / "skills" / "discovery" / "references" / "decompose-gate.md"

# Marker phrases pinned verbatim. These are part of the canonical contract —
# if they change, downstream consumers (this test, any future tooling that
# keys off the slot) must update in lockstep.

R3_DROP_DUAL_USE_MARKER_PHRASE = (
    "close discovery when research is sufficient and no tickets are warranted,"
    " OR abandon outright"
)

# Stable substring anchoring the brief-generation CLI invocation prose.
BRIEF_INVOCATION_MARKER_PHRASE = "cortex-discovery generate-brief"

# Stable substring from the --response argument example enumerating all four
# gate options (unspaced pipe form, as it appears in the emit-checkpoint-response
# invocation block). Resolution (a) per task authoring note: use the actual form
# that appears in the file rather than the spaced-pipe spec-authoring artifact.
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
    """BRIEF_INVOCATION: decompose-gate.md contains the brief-generation CLI invocation prose."""
    assert DECOMPOSE_GATE.is_file(), (
        f"Expected discovery skill at {DECOMPOSE_GATE.relative_to(REPO_ROOT)}"
    )
    text = DECOMPOSE_GATE.read_text(encoding="utf-8")

    assert BRIEF_INVOCATION_MARKER_PHRASE in text, (
        f"BRIEF_INVOCATION check: {DECOMPOSE_GATE.relative_to(REPO_ROOT)} must "
        f"contain the stable marker phrase {BRIEF_INVOCATION_MARKER_PHRASE!r}. "
        "This phrase anchors the brief-generation CLI invocation that drives the "
        "Research→Decompose gate's first content section."
    )


def test_gate_options_marker_present_in_skill() -> None:
    """GATE_OPTIONS: decompose-gate.md contains the four-option --response argument string."""
    assert DECOMPOSE_GATE.is_file(), (
        f"Expected discovery skill at {DECOMPOSE_GATE.relative_to(REPO_ROOT)}"
    )
    text = DECOMPOSE_GATE.read_text(encoding="utf-8")

    assert GATE_OPTIONS_MARKER_PHRASE in text, (
        f"GATE_OPTIONS check: {DECOMPOSE_GATE.relative_to(REPO_ROOT)} must "
        f"contain the stable marker phrase {GATE_OPTIONS_MARKER_PHRASE!r}. "
        "This substring appears in the --response argument example and enumerates "
        "all four gate options (approve, revise, drop, promote-sub-topic)."
    )


def test_r3_drop_description_has_dual_use_marker() -> None:
    """R3: decompose-gate.md's `drop` description carries the dual-use marker phrase."""
    assert DECOMPOSE_GATE.is_file(), (
        f"Expected discovery skill at {DECOMPOSE_GATE.relative_to(REPO_ROOT)}"
    )
    text = DECOMPOSE_GATE.read_text(encoding="utf-8")

    assert R3_DROP_DUAL_USE_MARKER_PHRASE in text, (
        f"R3 check: {DECOMPOSE_GATE.relative_to(REPO_ROOT)} must contain the "
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
                f"{DECOMPOSE_GATE.relative_to(REPO_ROOT)} but not on a line "
                "that also references `drop`. The phrase must describe the "
                f"`drop` option specifically. Offending line: {line!r}"
            )
            break


# Drifted Architecture-vocabulary tokens that the
# reconcile-discovery-skillmd-architecture-vocabulary-with ticket removed from
# the GATE-2 fallback and `revise` re-walk (originally in SKILL.md; relocated
# to references/decompose-gate.md by the progressive-disclosure restructuring).
# The template (`references/research.md` §6) emits only `### Pieces` +
# `### How they connect`; these four tokens named headings/pointers it no
# longer produces, so their reappearance signals silent re-drift.
DRIFTED_VOCAB_TOKENS = (
    "Integration shape",
    "Seam-level edges",
    "Why N pieces",
    "spec R4 GATE-2",
)


def test_revise_bullet_vocabulary_conformed_to_emitted_template() -> None:
    """Pin decompose-gate.md to the emitted Architecture vocabulary.

    File-wide: the four drifted tokens must be absent. Scoped to the `revise`
    bullet line specifically: it must carry the live-template pointer
    (`references/research.md`) and the emitted headings (`### Pieces`,
    `### How they connect`). The scoped check closes the spec's Edge Case 2 —
    a degenerate edit that fixes the GATE-2 fallback but stubs/deletes the
    `revise` bullet would leave a bare file-wide `references/research.md`
    check green (the token alone doesn't prove it sits on the interface-
    defining bullet) yet break the `revise` interface contract; the scoped
    check on the `revise` line specifically catches that case.
    """
    assert DECOMPOSE_GATE.is_file(), (
        f"Expected discovery skill at {DECOMPOSE_GATE.relative_to(REPO_ROOT)}"
    )
    text = DECOMPOSE_GATE.read_text(encoding="utf-8")

    # File-wide negative assertions: none of the drifted tokens may return.
    for token in DRIFTED_VOCAB_TOKENS:
        assert token not in text, (
            f"Drift check: {DECOMPOSE_GATE.relative_to(REPO_ROOT)} must NOT "
            f"contain the drifted Architecture-vocabulary token {token!r}. The "
            "emitted template (references/research.md §6) produces only "
            "`### Pieces` + `### How they connect`; this token names a heading "
            "or pointer the template no longer emits."
        )

    # `revise`-bullet-SCOPED positive assertion. A bare file-wide
    # `references/research.md` check wouldn't confirm the token sits on the
    # interface-defining bullet rather than unrelated prose. Locate the
    # `revise` bullet line and assert the live-template pointer and both
    # emitted headings live on it.
    revise_line = next(
        (line for line in text.splitlines() if "`revise`" in line),
        None,
    )
    assert revise_line is not None, (
        f"revise-bullet check: {DECOMPOSE_GATE.relative_to(REPO_ROOT)} must "
        "contain a `revise` gate-option bullet. The bullet was stubbed or "
        "deleted — the GATE-2 fallback may have been conformed in isolation."
    )

    for required in ("references/research.md", "### Pieces", "### How they connect"):
        assert required in revise_line, (
            f"revise-bullet check: the `revise` bullet in "
            f"{DECOMPOSE_GATE.relative_to(REPO_ROOT)} must name {required!r} so "
            "the re-walk points at the live template and re-emits the emitted "
            f"headings. Offending line: {revise_line!r}"
        )
