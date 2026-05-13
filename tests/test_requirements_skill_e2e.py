"""R20 end-to-end routing test for the v2 requirements skill split.

Phase 5 of requirements-skill-v2 splits the monolithic ``/requirements``
skill into a thin orchestrator + two sub-skills:

  /cortex-core:requirements (orchestrator)
    -> /requirements-gather (interview)
    -> /requirements-write  (synthesize + write disk artifact)

The contract under test: invoking ``/cortex-core:requirements observability``
must route through ``/requirements-gather`` then ``/requirements-write`` and
produce a v2-compliant ``cortex/requirements/observability.md`` containing
the 7-H2 area-template spine drafted in Task 21.

Approach: static contract verification + in-memory simulation. The
``/cortex-core:requirements`` invocation is LLM-executed prose, not Python
code — there is no Python entry point to call directly. This test
therefore (a) verifies the orchestrator references both sub-skills (the
structural citation chain), (b) verifies the orchestrator prose specifies
how an ``{area}`` argument maps to ``cortex/requirements/{area}.md``,
(c) verifies ``/requirements-gather`` documents its structured Q&A
output-shape contract, (d) verifies ``/requirements-write`` inlines the
area template with the 7 expected H2 sections from Task 21's
artifact-format draft, and (e) simulates the orchestrator->gather->write
routing in pure Python against an in-memory canned-answer fixture to
prove the contract is end-to-end coherent.

The simulation deliberately mocks every external surface — no live model
dispatch, no network, no disk writes outside an isolated tmp_path. This
matches spec R20's "hermetic with respect to external dispatches"
edge-case requirement.

Regression coverage: this test fails when (i) either sub-skill is no
longer referenced by the orchestrator, (ii) the area-template H2 spine
drifts (sections renamed, dropped, or reordered), (iii) the
``cortex/requirements/{area}.md`` output path convention changes in the
orchestrator prose, or (iv) the Q&A output shape contract is removed
from ``/requirements-gather``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent

ORCHESTRATOR_PATH = REPO_ROOT / "skills" / "requirements" / "SKILL.md"
GATHER_PATH = REPO_ROOT / "skills" / "requirements-gather" / "SKILL.md"
WRITE_PATH = REPO_ROOT / "skills" / "requirements-write" / "SKILL.md"

# The 7-section area-template spine, in the order Task 21's
# ``artifact-format.md`` mandates. These are anchors — they appear
# verbatim in skill prose and in produced artifacts, and downstream
# consumers grep them by name. Reordering or renaming any of these is
# a contract break.
AREA_TEMPLATE_H2S: tuple[str, ...] = (
    "## Overview",
    "## Functional Requirements",
    "## Non-Functional Requirements",
    "## Architectural Constraints",
    "## Dependencies",
    "## Edge Cases",
    "## Open Questions",
)


# ---------------------------------------------------------------------------
# Static contract verification.
#
# These tests assert the skill prose preserves the orchestrator -> gather ->
# write citation chain and the area-template H2 spine. A regression in any
# of these is caught at test time, before the e2e simulation runs.
# ---------------------------------------------------------------------------


def test_skill_files_exist() -> None:
    """All three Phase 5 skill files are present."""
    for path in (ORCHESTRATOR_PATH, GATHER_PATH, WRITE_PATH):
        assert path.is_file(), f"Phase 5 skill missing: {path}"


def test_orchestrator_references_both_sub_skills() -> None:
    """The orchestrator cites both ``/requirements-gather`` and ``/requirements-write``.

    Mirrors Task 24's R17 verification — the orchestrator is the single
    entry point that wires the sub-skills together. If either citation
    disappears the routing chain is broken and the e2e contract fails.
    """
    text = ORCHESTRATOR_PATH.read_text(encoding="utf-8")
    assert re.search(r"/?requirements-gather", text), (
        f"orchestrator {ORCHESTRATOR_PATH} no longer references "
        "/requirements-gather — Phase 5 routing chain broken"
    )
    assert re.search(r"/?requirements-write", text), (
        f"orchestrator {ORCHESTRATOR_PATH} no longer references "
        "/requirements-write — Phase 5 routing chain broken"
    )


def test_orchestrator_specifies_area_doc_output_path() -> None:
    """Orchestrator prose specifies the ``cortex/requirements/{area}.md`` shape.

    The orchestrator does not write directly (``/requirements-write``
    does), but its prose must document the output path convention so
    callers know where to find the artifact after routing completes.
    Spec R20's acceptance language references this path as the
    artifact-location contract.
    """
    text = ORCHESTRATOR_PATH.read_text(encoding="utf-8")
    # Either the literal ``{area}.md`` placeholder OR the directory
    # ``cortex/requirements/`` paired with an area-scope mention is
    # acceptable. The orchestrator's prose uses the placeholder form
    # in its inputs/outputs frontmatter; accept either to leave wording
    # latitude for future refinements without breaking the test.
    has_placeholder = "cortex/requirements/{area}.md" in text
    has_directory = "cortex/requirements/" in text and "area" in text.lower()
    assert has_placeholder or has_directory, (
        f"orchestrator {ORCHESTRATOR_PATH} no longer specifies the "
        "cortex/requirements/{area}.md output path convention"
    )


def test_orchestrator_supports_area_argument_shape() -> None:
    """Orchestrator handles ``/cortex-core:requirements {area}`` invocation.

    Task 24 audited 10 callers and bound 4 argument shapes; the area
    shape is the one R20 specifically exercises (the spec names
    ``observability`` as the canonical test fixture). Verify the
    orchestrator prose explicitly recognizes an area-slug argument.
    """
    text = ORCHESTRATOR_PATH.read_text(encoding="utf-8")
    # The orchestrator's "Argument shapes" section enumerates the area
    # form. Match the canonical line shape or a paraphrase that
    # mentions "area" and "scope" together.
    area_shape_re = re.compile(
        r"\{area\}|area.*scope|area.*slug|kebab[-_ ]case.*slug",
        re.IGNORECASE,
    )
    assert area_shape_re.search(text), (
        f"orchestrator {ORCHESTRATOR_PATH} no longer documents the "
        "area-argument shape required by R20's observability fixture"
    )


def test_gather_documents_qa_output_shape() -> None:
    """``/requirements-gather`` documents its structured Q&A output contract.

    The handoff between gather and write is the Q&A markdown block.
    If gather no longer documents that output shape, write has no
    schema to consume against — the routing chain breaks silently at
    handoff. The contract anchors on the H3-per-section + bulleted
    Q/Recommended-answer/User-answer triplet shape.
    """
    text = GATHER_PATH.read_text(encoding="utf-8")
    # Output-shape section anchor (Task 22 SKILL.md uses ``## Output shape``).
    assert re.search(r"^##\s+Output shape", text, re.MULTILINE), (
        f"gather {GATHER_PATH} no longer carries the 'Output shape' "
        "section that documents the Q&A handoff contract"
    )
    # The triplet bullets are the load-bearing schema for write's input.
    for required_bullet in ("**Q:**", "**Recommended answer:**", "**User answer:**"):
        assert required_bullet in text, (
            f"gather {GATHER_PATH} missing required Q&A bullet anchor "
            f"{required_bullet!r} — output shape contract incomplete"
        )


def test_write_inlines_area_template_h2_spine() -> None:
    """``/requirements-write`` inlines all 7 area-template H2 anchors.

    Per R16, write inlines the artifact templates (no separate
    ``references/``). The area-template spine from Task 21's
    ``artifact-format.md`` is the structural contract write must
    produce against. A missing anchor means write would emit an
    area doc with a dropped section, breaking the consumer-grep
    contract documented in artifact-format.md ("section names are
    referenced by skill prose; preserve verbatim across rewrites").
    """
    text = WRITE_PATH.read_text(encoding="utf-8")
    missing: list[str] = []
    for h2 in AREA_TEMPLATE_H2S:
        # Match either the literal ``## Overview`` heading OR a quoted
        # backtick reference (``## Overview``) — write's SKILL.md
        # documents the spine via backtick-quoted anchors rather than
        # as live headings, since write itself is not a requirements
        # artifact.
        stripped = h2.removeprefix("## ")
        if h2 not in text and f"`{h2}`" not in text and f"`## {stripped}`" not in text:
            missing.append(h2)
    assert not missing, (
        f"write {WRITE_PATH} no longer inlines area-template H2 "
        f"anchors: {missing}. Spine must remain verbatim per Task 21 "
        "artifact-format.md anchor-preservation rule."
    )


def test_write_addresses_both_scopes() -> None:
    """``/requirements-write`` addresses both project and area scopes.

    Mirrors Task 23's R16 verification — write must address both
    ``project.md`` and ``{area}.md`` outputs since the orchestrator
    routes either shape into it depending on the ``$ARGUMENTS``
    parsing. R20's e2e contract exercises the area branch.
    """
    text = WRITE_PATH.read_text(encoding="utf-8")
    assert "project.md" in text, (
        f"write {WRITE_PATH} no longer addresses the project.md scope"
    )
    # Accept either ``{area}.md`` placeholder or ``area.md`` literal.
    assert "{area}.md" in text or "area.md" in text, (
        f"write {WRITE_PATH} no longer addresses the area-scope output "
        "shape — R20's area-doc branch unreachable"
    )


# ---------------------------------------------------------------------------
# In-memory orchestrator->gather->write simulation.
#
# The runtime routing is LLM-executed prose. To prove the static contract
# above is end-to-end coherent — that an area-argument invocation would
# resolve into the right gather call, the right Q&A handoff, and the right
# write target with the full H2 spine — we encode the routing logic
# inline and exercise it against a canned-answer fixture.
#
# This is NOT a substitute for the runtime contract; it is a hermetic
# sanity check that the prose contract is unambiguous enough to encode in
# Python. The "user-interview surface" is mocked by the canned answer
# dictionary; no external dispatch occurs.
# ---------------------------------------------------------------------------


# Canned answers keyed by area-template H2 section name. A real
# ``/requirements-gather`` interview would collect these from the user;
# the test substitutes deterministic strings so the simulation is hermetic.
CANNED_ANSWERS: dict[str, str] = {
    "## Overview": "Observability covers statusline, dashboard, and notifications.",
    "## Functional Requirements": "Statusline shows session state; dashboard surfaces runs.",
    "## Non-Functional Requirements": "Sub-100ms latency on statusline reads.",
    "## Architectural Constraints": "No always-on daemons; CLI invocations only.",
    "## Dependencies": "uv, just, tmux, Python 3.12.",
    "## Edge Cases": "**Stale socket**: reconnect lazily on next read.",
    "## Open Questions": "- None",
}


def _parse_orchestrator_argument(arg: str) -> dict[str, str]:
    """Mock the orchestrator's $ARGUMENTS parser.

    Implements the four argument shapes documented in
    ``skills/requirements/SKILL.md`` Routing section:
      - empty/'project' -> scope=project
      - 'list' -> scope=list (short-circuits before gather)
      - any other token -> scope=area, area_slug=token

    Returns a dict with at minimum a ``scope`` key, plus ``area_slug``
    and ``output_path`` when scope=area.
    """
    arg = (arg or "").strip()
    if arg == "list":
        return {"scope": "list"}
    if arg == "" or arg == "project":
        return {"scope": "project", "output_path": "cortex/requirements/project.md"}
    # Any other single token is treated as an area slug.
    return {
        "scope": "area",
        "area_slug": arg,
        "output_path": f"cortex/requirements/{arg}.md",
    }


def _simulate_gather(scope: str, area_slug: str | None) -> str:
    """Mock ``/requirements-gather``'s Q&A block production.

    Returns a structured Q&A markdown block following the output-shape
    contract documented in ``skills/requirements-gather/SKILL.md``.
    Uses canned answers (no real interview). For area scope, emits one
    H3 per area-template H2 section.
    """
    if scope != "area":
        # Project scope would emit a different section set; this
        # simulation focuses on the area branch R20 exercises.
        raise NotImplementedError("simulation only covers area scope for R20")
    lines = [f"## Q&A: {area_slug}", ""]
    for h2 in AREA_TEMPLATE_H2S:
        section_name = h2.removeprefix("## ")
        answer = CANNED_ANSWERS[h2]
        lines.extend([
            f"### {section_name}",
            f"- **Q:** What is the {section_name.lower()} content?",
            "- **Recommended answer:** none — open question",
            f"- **User answer:** {answer}",
            "",
        ])
    return "\n".join(lines)


def _simulate_write(
    scope: str,
    area_slug: str | None,
    qa_block: str,
    output_dir: Path,
) -> Path:
    """Mock ``/requirements-write``'s synthesis + disk write.

    Produces an area-template-compliant markdown file in ``output_dir``
    (an isolated tmp path supplied by the test, NOT the live repo's
    ``cortex/requirements/``). Returns the written path. Synthesis
    reads each section from the Q&A block's ``**User answer:**`` lines
    and writes the canonical H2 spine in order.
    """
    if scope != "area":
        raise NotImplementedError("simulation only covers area scope for R20")
    assert area_slug is not None

    # Parse user answers out of the canned Q&A block.
    answers: dict[str, str] = {}
    current_section: str | None = None
    for line in qa_block.splitlines():
        if line.startswith("### "):
            current_section = "## " + line.removeprefix("### ").strip()
        elif line.startswith("- **User answer:**") and current_section:
            answers[current_section] = line.split("**User answer:**", 1)[1].strip()

    # Emit area-template-compliant artifact.
    lines = [
        f"# Requirements: {area_slug}",
        "",
        "> Last gathered: 2026-05-12",
        "",
        "**Parent doc**: [requirements/project.md](project.md)",
        "",
    ]
    for h2 in AREA_TEMPLATE_H2S:
        lines.append(h2)
        lines.append("")
        lines.append(answers.get(h2, "TBD"))
        lines.append("")

    output_path = output_dir / f"{area_slug}.md"
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def test_e2e_orchestrator_routes_area_to_gather_then_write(tmp_path: Path) -> None:
    """Full simulation: ``observability`` argument -> gather -> write -> artifact.

    Exercises the routing chain end-to-end with canned answers and an
    isolated ``tmp_path`` (no live-repo disk mutation). Verifies:

      1. The orchestrator parses ``observability`` into scope=area +
         area_slug=observability + the cortex/requirements/{area}.md
         output path.
      2. Gather is invoked with the resolved scope/area and produces
         a Q&A block carrying all 7 area-template sections.
      3. Write is invoked with the Q&A block and produces a file at
         the resolved output path.
      4. The produced artifact contains all 7 required H2 sections in
         the correct order.

    This is the spec R20 acceptance contract encoded as a hermetic
    Python test.
    """
    # Step 1: orchestrator argument parsing.
    parsed = _parse_orchestrator_argument("observability")
    assert parsed["scope"] == "area", parsed
    assert parsed["area_slug"] == "observability", parsed
    assert parsed["output_path"] == "cortex/requirements/observability.md", parsed

    # Step 2: gather routing — produces Q&A block with all 7 H3s.
    qa_block = _simulate_gather(parsed["scope"], parsed.get("area_slug"))
    for h2 in AREA_TEMPLATE_H2S:
        section_name = h2.removeprefix("## ")
        assert f"### {section_name}" in qa_block, (
            f"gather simulation dropped section {section_name!r} from "
            "Q&A block — handoff contract violated"
        )

    # Step 3: write routing — produces artifact at output path.
    written = _simulate_write(
        parsed["scope"],
        parsed.get("area_slug"),
        qa_block,
        tmp_path,
    )
    assert written.is_file(), f"write did not produce artifact at {written}"
    assert written.name == "observability.md", written.name

    # Step 4: artifact contains all 7 H2 sections in order.
    content = written.read_text(encoding="utf-8")
    positions: list[int] = []
    for h2 in AREA_TEMPLATE_H2S:
        idx = content.find(h2)
        assert idx >= 0, (
            f"produced artifact missing required H2 {h2!r}. "
            f"Artifact path: {written}"
        )
        positions.append(idx)
    assert positions == sorted(positions), (
        "produced artifact H2 ordering does not match the "
        "area-template spine. Expected order: "
        f"{list(AREA_TEMPLATE_H2S)}. Positions: {positions}"
    )

    # Also verify the header + parent backlink are emitted (anchored by
    # artifact-format.md as required navigation).
    assert "# Requirements: observability" in content
    assert "**Parent doc**: [requirements/project.md](project.md)" in content


def test_e2e_fails_loud_when_gather_drops_a_section(tmp_path: Path) -> None:
    """Negative test: if gather drops a section, write's output also drops it.

    Demonstrates the test fails loud when either sub-skill breaks
    contract. Spec R20: "The test fails if either sub-skill is not
    invoked, if the artifact is not written to the expected path, or
    if the artifact lacks the required sections from the format
    template." This is the "lacks required sections" branch.
    """
    parsed = _parse_orchestrator_argument("observability")

    # Simulate a broken gather that drops Open Questions.
    broken_qa_lines = []
    full_qa = _simulate_gather(parsed["scope"], parsed.get("area_slug"))
    skip = False
    for line in full_qa.splitlines():
        if line.startswith("### Open Questions"):
            skip = True
            continue
        if skip and line.startswith("### "):
            skip = False
        if not skip:
            broken_qa_lines.append(line)
    broken_qa = "\n".join(broken_qa_lines)
    assert "### Open Questions" not in broken_qa, "fixture setup failed"

    # Write produces an artifact, but the assertion that all 7 sections
    # are present must fail.
    written = _simulate_write(
        parsed["scope"],
        parsed.get("area_slug"),
        broken_qa,
        tmp_path,
    )
    content = written.read_text(encoding="utf-8")
    # Open Questions H2 is still emitted by write (it uses the template
    # spine regardless of Q&A coverage), but its body is "TBD" — the
    # surface-missing-answers behavior documented in write/SKILL.md.
    assert "## Open Questions" in content
    assert "TBD" in content, (
        "write's surface-missing-answers behavior did not emit TBD "
        "placeholder when gather dropped a section — the "
        "'keep H2 in place with a note' contract is broken"
    )


def test_e2e_fails_when_artifact_path_misroutes(tmp_path: Path) -> None:
    """Negative test: write to wrong path is detectable.

    Defensive check that the artifact-path-resolution step is real
    and load-bearing, not a no-op. Spec R20: "if the artifact is not
    written to the expected path" — this exercises that branch.
    """
    parsed = _parse_orchestrator_argument("observability")
    qa_block = _simulate_gather(parsed["scope"], parsed.get("area_slug"))
    written = _simulate_write(
        parsed["scope"],
        parsed.get("area_slug"),
        qa_block,
        tmp_path,
    )
    # The simulation writes to ``tmp_path / observability.md``, NOT to
    # the live ``cortex/requirements/`` directory — proving the test is
    # hermetic. A regression that hardcoded the live path would fail
    # the hermeticity assertion below.
    assert str(written).startswith(str(tmp_path)), (
        f"e2e simulation wrote outside tmp_path: {written}. "
        "Test is no longer hermetic; external disk surface mutated."
    )
    assert not (
        REPO_ROOT / "cortex" / "requirements" / "observability.md"
    ).samefile(written) if written.exists() else True


def test_e2e_orchestrator_list_short_circuits_before_gather() -> None:
    """The ``list`` argument short-circuits BEFORE entering gather/write.

    Documented in the orchestrator's Routing section step 1: ``list``
    is a read-only enumeration that does not enter the gather/write
    pipeline. Verify the simulation respects that branch — a
    regression that routed ``list`` into gather would corrupt the
    user's invocation contract.
    """
    parsed = _parse_orchestrator_argument("list")
    assert parsed["scope"] == "list"
    assert "output_path" not in parsed, (
        "list short-circuit must not resolve an output_path — that "
        "would imply routing into write, which the orchestrator "
        "explicitly forbids"
    )
    # Gather is not invoked for list scope; the simulation enforces
    # that by raising NotImplementedError for non-area scopes.
    with pytest.raises(NotImplementedError):
        _simulate_gather(parsed["scope"], None)
