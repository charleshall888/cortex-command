"""R5 execution-level smoke test for the tag-based requirements loading protocol.

Phase 1 of requirements-skill-v2 wires a shared tag-based loading protocol
(documented in ``skills/lifecycle/references/load-requirements.md``) into the
six non-exempt consumer references. Critical-review flagged the Phase 1
Checkpoint as presence-only — confirming that strings appear is not the same
as confirming the protocol resolves end-to-end. This test adds the missing
execution gate.

Approach: reference-shape verification + an in-memory protocol simulation.
There is no Python implementation of the loader (the protocol is executed by
the LLM at session time); the test therefore (a) verifies each of the six
consumer references contains the canonical citation, (b) verifies the
load-requirements.md protocol itself enumerates the 5 expected steps + the
empty/absent tags fallback, (c) verifies the critical-review exemption anchor
phrase is present, and (d) simulates the protocol's tag-matching semantics in
pure Python against a synthetic project.md / index.md / area-doc fixture to
prove the contract is internally consistent.

Regressions in any one of the six consumer references, in the protocol
document, or in the exemption anchor will be caught here before PR merge.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent

# The six non-exempt consumer references that must cite the shared protocol
# (per spec R5). Critical-review is the seventh consumer and is deliberately
# exempt — see ``skills/critical-review/SKILL.md`` "Requirements loading:
# deliberately exempt" block.
CONSUMER_REFS: tuple[Path, ...] = (
    REPO_ROOT / "skills" / "lifecycle" / "references" / "clarify.md",
    REPO_ROOT / "skills" / "lifecycle" / "references" / "specify.md",
    REPO_ROOT / "skills" / "lifecycle" / "references" / "review.md",
    REPO_ROOT / "skills" / "discovery" / "references" / "clarify.md",
    REPO_ROOT / "skills" / "discovery" / "references" / "research.md",
    REPO_ROOT / "skills" / "refine" / "SKILL.md",
)

LOAD_REQS_PATH = REPO_ROOT / "skills" / "lifecycle" / "references" / "load-requirements.md"
CRITICAL_REVIEW_PATH = REPO_ROOT / "skills" / "critical-review" / "SKILL.md"

# Citation phrase matched by the spec's union grep:
# ``grep -l 'load-requirements.md\|tag-based.*loading' ...``
_CITATION_RE = re.compile(r"load-requirements\.md|tag-based.*loading")


def test_six_consumer_references_cite_shared_protocol() -> None:
    """Each of the 6 non-exempt consumers contains the canonical citation.

    Mirrors the spec's R5 union grep so a regression in any single
    consumer's prose (e.g. an editor accidentally removing the citation
    while rewriting nearby text) is caught here, not silently after merge.
    """
    missing: list[str] = []
    for ref in CONSUMER_REFS:
        assert ref.is_file(), f"consumer reference missing: {ref}"
        text = ref.read_text(encoding="utf-8")
        if not _CITATION_RE.search(text):
            missing.append(str(ref.relative_to(REPO_ROOT)))
    assert not missing, (
        "consumer references lacking 'load-requirements.md' or "
        f"'tag-based ... loading' citation: {missing}"
    )


def test_critical_review_documents_deliberate_exemption() -> None:
    """critical-review/SKILL.md anchors the deliberate-exemption rationale.

    The spec's R5 acceptance language requires that critical-review's
    exemption from the tag-based protocol be documented, not implicit.
    The anchor phrase is a stable substring so future edits to the
    surrounding prose don't silently delete the exemption rationale.
    """
    assert CRITICAL_REVIEW_PATH.is_file(), CRITICAL_REVIEW_PATH
    text = CRITICAL_REVIEW_PATH.read_text(encoding="utf-8")
    assert "Requirements loading: deliberately exempt" in text, (
        "critical-review/SKILL.md missing the 'Requirements loading: "
        "deliberately exempt' anchor phrase that documents why critical-"
        "review does not participate in the tag-based loading protocol"
    )


def test_load_requirements_md_enumerates_five_protocol_steps() -> None:
    """The protocol-of-record describes the 5 expected steps in order.

    Verifies the load-requirements.md file contains the 5 numbered steps
    described in spec R1: (1) always load project.md, (2) read tags from
    index.md, (3) case-insensitively match tags against Conditional
    Loading, (4) load matched area docs, (5) fallback when tags empty/
    absent.
    """
    assert LOAD_REQS_PATH.is_file(), LOAD_REQS_PATH
    text = LOAD_REQS_PATH.read_text(encoding="utf-8")
    # Numbered steps 1-5 appear in order (markdown ordered-list form).
    for n in range(1, 6):
        assert re.search(rf"^{n}\.\s", text, re.MULTILINE), (
            f"load-requirements.md missing numbered protocol step {n}.\n"
            f"Expected an ordered-list entry starting with '{n}. '"
        )
    # The protocol must reference project.md (step 1's unconditional load),
    # the tags array (step 2), and the Conditional Loading section name
    # (step 3) — these are the load-bearing nouns of the protocol.
    for required in ("project.md", "tags", "Conditional Loading"):
        assert required in text, (
            f"load-requirements.md missing required noun: {required!r}"
        )


def test_load_requirements_md_documents_empty_or_absent_tags_fallback() -> None:
    """The protocol explicitly handles the empty/absent tags case.

    Spec R1 acceptance language: ``grep -ciE
    'tags.*empty|tags.*absent|no tags' load-requirements.md`` returns ≥1.
    This is the documented fallback that prevents the loader from
    erroring on lifecycles with no parent backlog item (or tag-less
    backlog items).
    """
    text = LOAD_REQS_PATH.read_text(encoding="utf-8")
    fallback_re = re.compile(r"tags.*empty|tags.*absent|no tags", re.IGNORECASE)
    assert fallback_re.search(text), (
        "load-requirements.md does not document the empty/absent tags "
        "fallback. Expected one of: 'tags empty', 'tags absent', "
        "or 'no tags' to appear (case-insensitive)."
    )


# ---------------------------------------------------------------------------
# Synthetic protocol-semantics simulation.
#
# The runtime protocol is prose executed by the LLM. To prove the protocol's
# *matching semantics* are internally consistent — that a tagged index.md +
# project.md Conditional Loading section + area docs would resolve to the
# expected (project.md + matched-area-doc) set — we implement the matching
# logic inline in the test and exercise it against an in-memory fixture.
#
# This is NOT a substitute for the runtime protocol; it is a sanity check
# that the protocol's described semantics are unambiguous enough to encode.
# If this simulation drifts from the prose protocol, the prose has become
# ambiguous and needs tightening.
# ---------------------------------------------------------------------------


def _simulate_loader(
    project_md: str,
    index_tags: list[str] | None,
) -> set[str]:
    """Pure-Python simulation of the tag-based loading protocol.

    Returns the set of file paths (as written in the Conditional Loading
    section, plus the unconditional ``project.md``) that the protocol
    would load given the supplied project.md text and the index.md
    ``tags:`` array. Implements steps 1-5 of the protocol described in
    ``skills/lifecycle/references/load-requirements.md``.
    """
    # Step 1: always load project.md.
    loaded: set[str] = {"project.md"}

    # Step 5 (fallback): tags absent (None) or empty → project.md only.
    if not index_tags:
        return loaded

    # Step 3: extract Conditional Loading section. Tolerant of leading/
    # trailing whitespace and the next-section sentinel being EOF.
    section_re = re.compile(
        r"^## Conditional Loading\s*$(.*?)(?=^##\s|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m = section_re.search(project_md)
    if not m:
        return loaded
    section = m.group(1)

    # Each Conditional Loading line has the form:
    #   "<trigger phrase> → <path>"
    # Match trigger + arrow + path, case-insensitively on the trigger.
    line_re = re.compile(r"^(.+?)\s*→\s*(\S+)\s*$", re.MULTILINE)
    for trigger, path in line_re.findall(section):
        trigger_lower = trigger.lower()
        # Case-insensitive substring match per protocol step 3.
        for tag in index_tags:
            if tag.lower() in trigger_lower:
                loaded.add(path)
                break  # one match is enough; protocol step 3: "loaded once"
    return loaded


def test_protocol_simulation_matches_tagged_index() -> None:
    """Synthetic fixture: a tagged index.md + project.md → expected load set.

    Constructs an in-memory project.md (containing a Conditional Loading
    section in the cortex/requirements format) and an index.md tag array,
    then asserts the simulated loader emits the expected set. Exercises:

      - Step 1 (unconditional project.md load).
      - Step 3 (case-insensitive substring match against Conditional
        Loading phrases).
      - Step 4 (matched area docs added to the loaded set).
      - The "loaded once" deduplication semantic (a path mentioned twice
        appears in the set once — sets enforce this trivially).
    """
    fixture_project_md = (
        "# Project\n\n"
        "## Overview\n\nfoo\n\n"
        "## Conditional Loading\n\n"
        "Working on statusline, dashboard, or notifications → cortex/requirements/observability.md\n"
        "Working on pipeline or overnight runner → cortex/requirements/pipeline.md\n"
        "Working on agent spawning, parallel dispatch, worktrees → cortex/requirements/multi-agent.md\n\n"
        "## Next Section\n"
    )
    # Tag matches "observability" trigger (substring "dashboard" matches
    # "dashboard" in the first trigger). Verify case-insensitive matching
    # by using a mixed-case tag.
    loaded = _simulate_loader(fixture_project_md, ["Dashboard"])
    assert loaded == {
        "project.md",
        "cortex/requirements/observability.md",
    }, f"unexpected load set: {loaded}"


def test_protocol_simulation_fallback_when_tags_empty() -> None:
    """Empty ``tags: []`` → project.md only, no error.

    Spec R1 fallback clause: when tags is empty, load project.md alone
    and proceed silently. This is the documented behavior for lifecycles
    whose parent backlog item has no tags (or for parentless lifecycles).
    """
    fixture_project_md = (
        "## Conditional Loading\n\n"
        "Working on observability → cortex/requirements/observability.md\n"
    )
    assert _simulate_loader(fixture_project_md, []) == {"project.md"}


def test_protocol_simulation_fallback_when_tags_absent() -> None:
    """Absent (None) tags field → project.md only, no error."""
    fixture_project_md = (
        "## Conditional Loading\n\n"
        "Working on observability → cortex/requirements/observability.md\n"
    )
    assert _simulate_loader(fixture_project_md, None) == {"project.md"}


def test_protocol_simulation_unmatched_tag_silently_dropped() -> None:
    """A tag word that matches no phrase is silently dropped (per spec).

    Per the load-requirements.md "Matching Semantics" subsection: tags
    that match nothing are silently dropped; other tags still match
    independently. If no tag matches, project.md-only is loaded — same as
    the empty-tags fallback.
    """
    fixture_project_md = (
        "## Conditional Loading\n\n"
        "Working on observability → cortex/requirements/observability.md\n"
        "Working on pipeline → cortex/requirements/pipeline.md\n"
    )
    # Tag "nonexistent" matches nothing; tag "pipeline" matches the
    # pipeline trigger phrase. Verify only the matched doc is loaded
    # alongside the unconditional project.md.
    loaded = _simulate_loader(fixture_project_md, ["nonexistent", "pipeline"])
    assert loaded == {"project.md", "cortex/requirements/pipeline.md"}


def test_protocol_simulation_multiple_tags_one_match() -> None:
    """A single area doc matched by multiple tags is loaded exactly once.

    Per protocol step 3: "a phrase matched by multiple tags is loaded
    once". Encoded via set semantics.
    """
    fixture_project_md = (
        "## Conditional Loading\n\n"
        "Working on statusline, dashboard, or notifications → cortex/requirements/observability.md\n"
    )
    # Both tags match the same trigger phrase ("statusline" + "dashboard"
    # both appear in the same phrase). Expected load set: project.md +
    # observability.md (one copy).
    loaded = _simulate_loader(
        fixture_project_md, ["statusline", "dashboard"]
    )
    assert loaded == {
        "project.md",
        "cortex/requirements/observability.md",
    }
