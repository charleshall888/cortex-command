"""Tests for the scale-research-fanout-by-complexity feature, Phase 2 (Task 11).

Covers two acceptance gates of the Phase-2 discovery integration:

  A) Brief-generation contract against the Task-10 §6 schema (spec R8).
     A discovery ``research.md`` written to the *current shipped* §6 output
     template must still satisfy the machine parser that the
     Research→Decompose gate and ``score-corpus`` paths depend on. The
     shipped parser is ``_extract_headline_and_architecture`` — it hard-reads
     ``## Architecture`` (and ``## Headline Finding`` when present) and is the
     R4-gate / score-corpus source surface. This test proves the Task-10
     research rewrite did not break that parser: the extractor returns the
     ``## Architecture`` body with both ``### Pieces`` and
     ``### How they connect`` intact, rather than collapsing to the
     whole-file fallback (the "missing-architecture" outcome R8 guards
     against).

     Note on ``generate-brief``: the shipped ``cortex-discovery
     generate-brief`` subcommand dispatches a *live* Claude sub-agent to
     author the prose brief, so an unconditional exit-0 assertion would
     require API auth (the live path is already covered, auth-gated, in
     ``tests/test_discovery_gate_brief.py``). The hermetic, auth-free guard
     that the §6 template satisfies the parser is the extractor contract
     tested here — that is the surface the discovery research rewrite could
     have regressed.

  B) Round-trip persistence (spec R9). ``emit_research_sizing`` then
     ``read_research_sizing`` for the same topic round-trips the
     complexity + criticality pair.

  C) Resume-without-assessment default (spec R9 core acceptance).
     ``read_research_sizing`` for a topic with NO persisted assessment
     returns discovery's floor default — ``complexity=simple,
     criticality=medium`` — and never errors. The criticality floor is
     ``medium`` (discovery's upward bias), NOT ``low``; this test pins that
     distinction explicitly.

Conventions mirror ``tests/test_discovery_module.py``: public functions are
imported directly from ``cortex_command.discovery`` and exercised against a
hermetic ``tmp_path`` repo root with ``LIFECYCLE_SESSION_ID`` cleared so the
events-log resolver routes to ``cortex/research/<topic>/`` rather than an
active lifecycle directory.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cortex_command.discovery import (
    DEFAULT_RESEARCH_SIZING,
    _extract_headline_and_architecture,
    emit_research_sizing,
    read_research_sizing,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    """A bare tmp repo root with empty cortex/research/ and cortex/lifecycle/."""
    (tmp_path / "cortex" / "research").mkdir(parents=True)
    (tmp_path / "cortex" / "lifecycle").mkdir(parents=True)
    return tmp_path


# The current (Task-10) discovery §6 research.md output template. Mirrors the
# machine-parsed shape in skills/discovery/references/research.md §4 — the
# `## Architecture` → `### Pieces` / `### How they connect` headings that
# decompose.md and cortex_command/discovery.py hard-read. Built fresh here
# (rather than reusing the auth-gated fixtures under tests/fixtures/) so this
# test is a deliberate, minimal restatement of the SHIPPED template the
# parser must accept.
_TASK10_RESEARCH_MD = """\
# Research: example-topic

## Research Questions
1. Which approach fits the existing patterns? → **Answered: approach A.**
2. What are the integration points? → **Answered: the events.log resolver.**

## Codebase Analysis
- Existing pattern X used in `[src/foo.py:42]`.
- Integration point: the shared fan-out engine.
- `NOT_FOUND(query="async ContextVar", scope="src/**/*.py")` — no callers.

## Feasibility Assessment
| Approach | Effort | Risks | Prerequisites |
|----------|--------|-------|---------------|
| A | S | low | none |

## Architecture

### Pieces
- Sizing read-back — reads the persisted complexity/criticality assessment.
- Fan-out dispatcher — sizes the parallel research wave from that assessment.

### How they connect
The read-back feeds the dispatcher: the assessment values index the shared
count matrix, and the dispatcher fans out that many angle-specialized agents.

## Decision Records
Chose the shared engine over a discovery-local copy to prevent drift; the
tradeoff is a cross-skill reference dependency, which was accepted.

## Open Questions
- None blocking.
"""


# ---------------------------------------------------------------------------
# A) Brief-generation contract against the Task-10 §6 schema (spec R8)
# ---------------------------------------------------------------------------


def test_architecture_extractor_accepts_task10_template(tmp_path: Path) -> None:
    """A §6-template research.md still parses: the architecture extractor
    returns the `## Architecture` body with `### Pieces` and
    `### How they connect` intact (no missing-architecture collapse).

    This is the hermetic guard for spec R8: the discovery research rewrite
    (Task 10) preserved the machine-parsed schema the R4 gate / score-corpus
    path consume.
    """
    research_md = tmp_path / "example-topic" / "research.md"
    research_md.parent.mkdir(parents=True)
    research_md.write_text(_TASK10_RESEARCH_MD, encoding="utf-8")

    extracted = _extract_headline_and_architecture(research_md)

    # The extractor must surface the Architecture section and both required
    # sub-headings — these are the headings decompose.md calls "the
    # decomposition source of record" and that the R4-gate path hard-reads.
    assert "## Architecture" in extracted, (
        "Architecture extractor dropped the '## Architecture' heading from a "
        "research.md written to the shipped §6 template — the discovery "
        "research rewrite would have broken the R4 gate / score-corpus parser.\n"
        f"Extracted:\n{extracted}"
    )
    assert "### Pieces" in extracted, (
        "Architecture extractor dropped the '### Pieces' sub-section "
        "(decompose.md's 'decomposition source of record').\n"
        f"Extracted:\n{extracted}"
    )
    assert "### How they connect" in extracted, (
        "Architecture extractor dropped the '### How they connect' sub-section "
        "from the §6 template.\n"
        f"Extracted:\n{extracted}"
    )

    # The Pieces bullets must survive (not just the heading).
    assert "Sizing read-back" in extracted and "Fan-out dispatcher" in extracted, (
        "Architecture extractor lost the Pieces bullet content.\n"
        f"Extracted:\n{extracted}"
    )

    # The extractor must STOP at the next non-target section (it is a section
    # slice, not the whole-file fallback). A missing-architecture collapse
    # would return the entire document, including these later headings.
    assert "## Research Questions" not in extracted, (
        "Architecture extractor returned the whole file (Research Questions "
        "leaked in) instead of slicing the Architecture section — this is the "
        "whole-file fallback the parser hits when '## Architecture' is absent. "
        "The §6 template should be parsed as a real section.\n"
        f"Extracted:\n{extracted}"
    )
    assert "## Decision Records" not in extracted, (
        "Architecture extractor over-ran into '## Decision Records' — the "
        "section slice should end at the next top-level heading.\n"
        f"Extracted:\n{extracted}"
    )


# ---------------------------------------------------------------------------
# B) Round-trip persistence (spec R9)
# ---------------------------------------------------------------------------


def test_research_sizing_round_trips_complex_high(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """emit then read round-trips a non-default complexity/criticality pair.

    complex/high in → complex/high out, proving the persisted
    discovery_research_sizing event survives the clarify→research resume
    boundary and is read back verbatim.
    """
    monkeypatch.delenv("LIFECYCLE_SESSION_ID", raising=False)
    topic = "round-trip-topic"

    events_log = emit_research_sizing(
        topic=topic,
        complexity="complex",
        criticality="high",
        repo_root=repo_root,
    )
    # The event landed under cortex/research/<topic>/ (no lifecycle override).
    assert events_log == (
        repo_root / "cortex" / "research" / topic / "events.log"
    )
    assert events_log.is_file()

    sizing = read_research_sizing(topic=topic, repo_root=repo_root)
    assert sizing["complexity"] == "complex", sizing
    assert sizing["criticality"] == "high", sizing


def test_research_sizing_read_returns_most_recent(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When multiple assessments are emitted, the read returns the latest one.

    Guards the "most recent persisted assessment" contract: a re-run of
    Clarify that re-sizes the topic must override the earlier value on the
    next Research read.
    """
    monkeypatch.delenv("LIFECYCLE_SESSION_ID", raising=False)
    topic = "re-sized-topic"

    emit_research_sizing(
        topic=topic, complexity="simple", criticality="low", repo_root=repo_root
    )
    emit_research_sizing(
        topic=topic, complexity="complex", criticality="critical", repo_root=repo_root
    )

    sizing = read_research_sizing(topic=topic, repo_root=repo_root)
    assert sizing == {"complexity": "complex", "criticality": "critical"}, sizing


# ---------------------------------------------------------------------------
# C) Resume-without-assessment default (spec R9 core acceptance)
# ---------------------------------------------------------------------------


def test_research_sizing_default_on_resume_without_assessment(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reading sizing for a topic with NO persisted assessment returns the
    floor default (simple/medium) and never errors.

    This is the explicit "safe default on resume" guard the integration
    review required: Research entered before Clarify ran (or a legacy
    discovery dir) must not be an unhandled-missing-input failure.

    The criticality floor is asserted to be MEDIUM, not low — discovery's
    upward bias means a missing assessment defaults to the cautious floor,
    not the absolute minimum. This assertion would fail if the default
    regressed to simple/low.
    """
    monkeypatch.delenv("LIFECYCLE_SESSION_ID", raising=False)

    # No emit for this topic — the events.log does not exist at all.
    sizing = read_research_sizing(
        topic="never-assessed-topic", repo_root=repo_root
    )

    assert sizing["complexity"] == "simple", (
        f"resume-without-assessment must default complexity to 'simple'; "
        f"got {sizing!r}"
    )
    # Explicit floor pin: MEDIUM, not low. Discovery's upward bias.
    assert sizing["criticality"] == "medium", (
        "resume-without-assessment must default criticality to the 'medium' "
        "floor (discovery's upward bias), NOT 'low'. A regression to "
        f"simple/low would fail here. Got {sizing!r}"
    )
    assert sizing["criticality"] != "low", (
        "criticality floor must never be 'low' on the missing-assessment "
        f"default path; got {sizing!r}"
    )

    # The documented module default constant matches the read-back floor.
    assert sizing == {
        "complexity": DEFAULT_RESEARCH_SIZING["complexity"],
        "criticality": DEFAULT_RESEARCH_SIZING["criticality"],
    }, (
        "read_research_sizing default must equal DEFAULT_RESEARCH_SIZING; "
        f"got {sizing!r} vs {DEFAULT_RESEARCH_SIZING!r}"
    )


def test_research_sizing_default_when_log_has_no_sizing_event(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An events.log that exists but contains no discovery_research_sizing row
    still falls back to the floor default (simple/medium) without error.

    Covers the "log present, assessment absent" sub-case distinct from the
    "no log at all" case above — e.g. a topic whose only events are
    checkpoint responses, never a sizing emit.
    """
    monkeypatch.delenv("LIFECYCLE_SESSION_ID", raising=False)
    topic = "log-without-sizing"

    events_log = repo_root / "cortex" / "research" / topic / "events.log"
    events_log.parent.mkdir(parents=True)
    # A non-sizing event line plus a malformed line (Tolerant Reader).
    events_log.write_text(
        '{"event":"approval_checkpoint_responded","response":"approve"}\n'
        "this-is-not-json\n",
        encoding="utf-8",
    )

    sizing = read_research_sizing(topic=topic, repo_root=repo_root)
    assert sizing == {"complexity": "simple", "criticality": "medium"}, sizing
