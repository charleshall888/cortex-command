"""Multi-fixture brief test suite for the discovery-output-density feature.

Tests three acceptance contracts (spec Req 5, 6, 7):

  test_brief_passes_all_fixtures
      Runs ``generate-brief`` against all three fixture research.md files and
      scores each produced brief against the six reader-study patterns.
      Skipped when live API auth is not present (marked with skipif).

  test_brief_failure_falls_back_to_architecture
      Simulates a structural failure in ``generate-brief`` (malformed input that
      triggers ``validation_failed``) and asserts the subcommand exits non-zero
      and emits a ``gate_brief_generated`` event with ``status: validation_failed``.
      Skipped when live API auth is not present.

  test_gate_renders_brief_not_architecture
      Tests the gate render contract directly against the file-reading logic
      described in SKILL.md: brief.md present → display brief content; brief.md
      absent → fall back to ``## Architecture`` body + ``brief_generation_failed``
      warning. Does NOT need live API auth and always runs.

Gate-render helper note
-----------------------
The gate render surface is prose-only in ``skills/discovery/SKILL.md`` (no
Python callable). The test implements the file-reading contract directly,
mirroring exactly what an agent following SKILL.md would do: read brief.md if
present and valid, otherwise extract the ## Architecture section from
research.md and emit a ``brief_generation_failed`` warning. This is the same
contract Task 9's ``score-corpus`` subcommand will exercise over the live
``cortex/research/*/brief.md`` set.

Pattern-scoring helper
----------------------
``_score_brief_patterns`` lives in ``cortex_command/_brief_scoring.py`` and is
imported by this test file.  The ``score-corpus`` subcommand in
``cortex_command/discovery.py`` imports the same helper for corpus-wide
regression scanning (Task 9).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from cortex_command._brief_scoring import _score_brief_patterns  # noqa: F401 (re-exported for tests)

# ---------------------------------------------------------------------------
# Repo paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "discovery-brief"
DISCOVERY_MODULE = [sys.executable, "-m", "cortex_command.discovery"]

# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------


def has_claude_auth() -> bool:
    """Return True when a live Claude API auth credential is present in the env.

    Checks for ``ANTHROPIC_API_KEY`` (direct API key) and
    ``CLAUDE_CODE_OAUTH_TOKEN`` (OAuth token used by Claude Code CLI).
    Does not attempt a live query — purely an environment probe.
    """
    return bool(
        os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
    )


_REQUIRES_AUTH = pytest.mark.skipif(
    not has_claude_auth(),
    reason="requires live Claude API auth (ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN)",
)

# ---------------------------------------------------------------------------
# Pattern-scoring helper
#
# Extracted to cortex_command/_brief_scoring.py (Task 9). Imported above.
# The import line at the top of this file re-exports _score_brief_patterns
# so existing references within the test functions need no changes.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# validate_brief import (used by test 1 and test 3)
# ---------------------------------------------------------------------------

from cortex_command.discovery import (  # noqa: E402
    GATE_BRIEF_WORD_CAP,
    brief_word_overage,
    validate_brief,
)

# Over-cap soft-note marker. Mirrors the literal phrasing the Task 4 prose in
# skills/discovery/SKILL.md emits — "(summary ran N words over the 275-word
# advisory cap)". The render helper below appends this note when a posted brief
# is over-cap; keeping the helper's emitted note and the prose in lockstep is
# the authoring-discipline parity this mirror exists to enforce.
_OVER_CAP_NOTE_CAP_TOKENS = GATE_BRIEF_WORD_CAP + 25  # 275 in the prose


# ---------------------------------------------------------------------------
# Test 1: brief passes all fixtures (requires API auth)
# ---------------------------------------------------------------------------


@_REQUIRES_AUTH
def test_brief_passes_all_fixtures(tmp_path: Path) -> None:
    """For each fixture research.md, generate-brief produces a brief that:

    (a) is <= GATE_BRIEF_WORD_CAP + 25 words
    (b) contains decision-content anchors per validate_brief
    (c) scores 0 of 6 reader-study patterns
    """
    fixture_dirs = sorted(FIXTURES_DIR.iterdir())
    assert len(fixture_dirs) >= 3, (
        f"Expected >= 3 fixture directories in {FIXTURES_DIR}, found {len(fixture_dirs)}"
    )

    for fixture_dir in fixture_dirs:
        research_md = fixture_dir / "research.md"
        assert research_md.is_file(), f"Missing research.md in {fixture_dir}"

        brief_out = tmp_path / fixture_dir.name / "brief.md"
        brief_out.parent.mkdir(parents=True, exist_ok=True)

        proc = subprocess.run(
            DISCOVERY_MODULE + [
                "generate-brief",
                "--research-md", str(research_md),
                "--persist-to", str(brief_out),
            ],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, (
            f"generate-brief failed for fixture '{fixture_dir.name}'.\n"
            f"stderr: {proc.stderr}\nstdout: {proc.stdout}"
        )

        brief = proc.stdout.strip()
        assert brief, (
            f"generate-brief returned empty stdout for fixture '{fixture_dir.name}'"
        )

        # (a) Word-cap tolerance
        word_count = len(brief.split())
        cap = GATE_BRIEF_WORD_CAP + 25
        assert word_count <= cap, (
            f"Fixture '{fixture_dir.name}': brief is {word_count} words, "
            f"exceeds GATE_BRIEF_WORD_CAP+25={cap}"
        )

        # (b) Decision-content anchors
        ok, reason = validate_brief(brief)
        assert ok, (
            f"Fixture '{fixture_dir.name}': brief failed validate_brief: {reason}\n"
            f"Brief text:\n{brief}"
        )

        # (c) Pattern scoring — all six must score 0
        pattern_scores = _score_brief_patterns(brief)
        failing = {k: v for k, v in pattern_scores.items() if v != 0}
        assert not failing, (
            f"Fixture '{fixture_dir.name}': brief triggered {len(failing)} "
            f"reader-study pattern(s): {list(failing.keys())}\n"
            f"Brief text:\n{brief}"
        )


# ---------------------------------------------------------------------------
# Test 2: generate-brief failure exits non-zero and emits validation_failed
# ---------------------------------------------------------------------------


@_REQUIRES_AUTH
def test_brief_failure_falls_back_to_architecture(tmp_path: Path) -> None:
    """Simulate generate-brief receiving a structurally malformed input.

    A research.md that is empty (or contains no decision-content anchors) will
    cause the generated brief to fail ``validate_brief``; the subcommand must:
      - exit non-zero
      - emit a ``gate_brief_generated`` event with ``status: validation_failed``

    We create a minimal malformed research.md that contains no "decided",
    "alternative", "tradeoff", or "cost" vocabulary, so any brief the model
    produces will fail the decision-content anchor check.
    """
    # Malformed input: contains no decision-content vocabulary and is too short
    # to meet the anchor requirements.
    malformed_dir = tmp_path / "malformed-topic"
    malformed_dir.mkdir()
    malformed_research = malformed_dir / "research.md"
    malformed_research.write_text(
        "# Research: empty-stub\n\nXXX STRUCTURALLY INCOMPLETE XXX\n",
        encoding="utf-8",
    )

    events_dir = tmp_path / "cortex" / "research" / "malformed-topic"
    events_dir.mkdir(parents=True)

    proc = subprocess.run(
        DISCOVERY_MODULE + [
            "generate-brief",
            "--research-md", str(malformed_research),
            "--topic", "malformed-topic",
            "--repo-root", str(tmp_path),
        ],
        capture_output=True,
        text=True,
    )

    # Subcommand must exit non-zero.
    assert proc.returncode != 0, (
        "generate-brief was expected to fail on a malformed/stub input that "
        "cannot produce a valid brief, but it exited 0.\n"
        f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
    )

    # The events.log must contain a gate_brief_generated event with status
    # indicating failure (validation_failed, empty, or sdk_unavailable).
    events_log = events_dir / "events.log"
    assert events_log.is_file(), (
        f"Expected events.log at {events_log} after generate-brief failure, "
        f"but file was not created.\nstderr: {proc.stderr}"
    )

    events = [json.loads(line) for line in events_log.read_text().splitlines() if line.strip()]
    assert events, f"events.log is empty after generate-brief failure: {events_log}"

    brief_events = [e for e in events if e.get("event") == "gate_brief_generated"]
    assert brief_events, (
        f"No gate_brief_generated event found in events.log.\nEvents: {events}"
    )

    last_event = brief_events[-1]
    failure_statuses = {"validation_failed", "empty", "sdk_unavailable"}
    assert last_event.get("status") in failure_statuses, (
        f"Expected gate_brief_generated event with a failure status "
        f"({failure_statuses}), got status={last_event.get('status')!r}.\n"
        f"Full event: {last_event}"
    )


# ---------------------------------------------------------------------------
# Test 3: gate renders brief, falls back to Architecture when brief absent
# (does NOT require API auth — tests the file-reading contract directly)
# ---------------------------------------------------------------------------

# Gate-render helper note:
# The gate render surface in this repo is prose-only (SKILL.md instructs the
# agent to read cortex/research/<topic>/brief.md and display it; there is no
# Python gate-render callable). This test implements the same contract as a
# pure file-reading exercise: read brief.md if it passes validate_brief;
# otherwise extract the ## Architecture section from research.md and append a
# brief_generation_failed warning. This mirrors exactly what an agent
# following SKILL.md would produce, and is the correct test surface for a
# prose-only skill instruction.
#
# The GATE_OPTIONS string must match the verbatim text in SKILL.md (Req 7).
# The four gate options that Req 7 requires to be preserved verbatim.
# SKILL.md lists them as separate bolded bullets; we verify each is present
# rather than checking for the pipe-separated shorthand the spec uses in its
# grep acceptance command (which represents the conceptual set, not the literal
# string that must appear in the file).
_GATE_OPTION_ITEMS = ("`approve`", "`revise`", "`drop`", "`promote-sub-topic`")


def _render_gate(topic_dir: Path, research_md: Path) -> str:
    """Render the Research → Decompose gate content for a topic directory.

    Mirrors the SKILL.md gate-render contract:
      1. If ``brief.md`` exists in ``topic_dir`` and passes ``validate_brief``,
         return its content. When the posted brief is over-cap (anchor-valid but
         exceeds the advisory ceiling), the brief text is still returned, with a
         one-line soft note appended — the cap is advisory, not a posting gate.
      2. Otherwise, extract the ``## Architecture`` body from ``research_md``
         and return it with a ``brief_generation_failed`` warning prefixed.

    This is not a published Python API — it is a test-local implementation of
    the file-reading contract described in SKILL.md.  Task 9's ``score-corpus``
    subcommand exercises the same contract over the live corpus.

    The over-cap soft note mirrors the Task 4 prose in
    ``skills/discovery/SKILL.md`` verbatim — "(summary ran N words over the
    275-word advisory cap)". This mirror and that prose must stay in lockstep.
    """
    brief_path = topic_dir / "brief.md"
    if brief_path.is_file():
        brief_text = brief_path.read_text(encoding="utf-8").strip()
        if brief_text:
            ok, _ = validate_brief(brief_text)
            if ok:
                overage = brief_word_overage(brief_text)
                if overage > 0:
                    note = (
                        f"(summary ran {overage} words over the "
                        f"{_OVER_CAP_NOTE_CAP_TOKENS}-word advisory cap)"
                    )
                    return f"{brief_text}\n\n{note}"
                return brief_text

    # Fallback: extract ## Architecture section from research.md.
    research_text = research_md.read_text(encoding="utf-8")
    lines = research_text.splitlines()
    architecture_body_lines: list[str] = []
    in_arch = False
    for line in lines:
        if line.rstrip() == "## Architecture":
            in_arch = True
            continue
        if in_arch and line.startswith("## "):
            break
        if in_arch:
            architecture_body_lines.append(line)

    architecture_body = "\n".join(architecture_body_lines).strip()
    warning = "brief_generation_failed: brief.md missing or failed validation"
    return f"{warning}\n\n{architecture_body}"


def test_gate_renders_brief_not_architecture(tmp_path: Path) -> None:
    """Gate-render contract: brief.md present → brief content; absent → Architecture fallback.

    Uses the ``simple-topic`` fixture as the research.md source and writes a
    pre-generated brief.md into a temp topic dir to simulate a successful
    brief generation without needing a live API call.
    """
    # Use the simple-topic fixture as our research source.
    fixture_research_md = FIXTURES_DIR / "simple-topic" / "research.md"
    assert fixture_research_md.is_file(), (
        f"simple-topic fixture not found at {fixture_research_md}"
    )

    # --- Scenario A: brief.md is present and valid ---

    topic_dir_a = tmp_path / "scenario-a" / "simple-topic"
    topic_dir_a.mkdir(parents=True)

    # Write a minimal valid brief that passes validate_brief.
    # It must contain: 'decide'/'decided', 'alternative'/'options', 'tradeoff'/'cost'.
    valid_brief = (
        "The team decided to use the native GitHub badge over third-party options. "
        "Two alternatives were considered: Shields.io and Codecov. "
        "The tradeoff is that the native badge only shows pass/fail with no coverage metrics, "
        "but this cost is acceptable given the zero-dependency benefit."
    )
    ok, reason = validate_brief(valid_brief)
    assert ok, f"Test setup: pre-written brief is invalid — fix the test: {reason}"

    (topic_dir_a / "brief.md").write_text(valid_brief + "\n", encoding="utf-8")

    rendered_a = _render_gate(topic_dir_a, fixture_research_md)

    # The rendered output must contain the brief content.
    assert "native GitHub badge" in rendered_a, (
        "Rendered gate output does not contain brief content when brief.md is present.\n"
        f"Rendered:\n{rendered_a}"
    )

    # The rendered output must NOT contain the verbatim ## Architecture Pieces text.
    # The simple-topic fixture has "## Architecture" with "### Pieces" sub-section.
    assert "## Architecture" not in rendered_a, (
        "Rendered gate output contains '## Architecture' heading when brief.md is "
        "present — gate should display the brief, not the Architecture section.\n"
        f"Rendered:\n{rendered_a}"
    )
    assert "### Pieces" not in rendered_a, (
        "Rendered gate output contains '### Pieces' (from Architecture section) "
        "when brief.md is present.\n"
        f"Rendered:\n{rendered_a}"
    )

    # --- Scenario B: brief.md is absent — must fall back to Architecture ---

    topic_dir_b = tmp_path / "scenario-b" / "simple-topic"
    topic_dir_b.mkdir(parents=True)
    # No brief.md written.

    rendered_b = _render_gate(topic_dir_b, fixture_research_md)

    # The fallback must include the Architecture body.
    assert "### Pieces" in rendered_b, (
        "Fallback rendered gate output is missing '### Pieces' from the Architecture "
        "section when brief.md is absent.\n"
        f"Rendered:\n{rendered_b}"
    )

    # The fallback must include the brief_generation_failed warning.
    assert "brief_generation_failed" in rendered_b, (
        "Fallback rendered gate output is missing the 'brief_generation_failed' warning "
        "when brief.md is absent.\n"
        f"Rendered:\n{rendered_b}"
    )

    # The fallback must NOT contain the brief text from Scenario A.
    assert "native GitHub badge" not in rendered_b, (
        "Fallback rendered gate output contains brief text from Scenario A — "
        "brief isolation between tmp_path scenarios failed.\n"
        f"Rendered:\n{rendered_b}"
    )

    # --- Scenario C: brief.md is over-cap but anchored — display brief + note ---
    #
    # Mirrors the FULL over-cap render contract that the Task 4 SKILL.md prose
    # encodes: an anchor-valid brief over the advisory ceiling is posted as the
    # gate summary (NOT discarded for the Architecture fallback), followed by a
    # one-line soft note. The cap is advisory, not a posting gate.

    topic_dir_c = tmp_path / "scenario-c" / "simple-topic"
    topic_dir_c.mkdir(parents=True)

    # An anchor-valid brief padded over GATE_BRIEF_WORD_CAP + 25 (275) words.
    over_cap_brief = (
        "The team decided to use the native GitHub badge over third-party options. "
        "Two alternatives were considered: Shields.io and Codecov. "
        "The tradeoff is that the native badge only shows pass/fail with no coverage "
        "metrics, but this cost is acceptable given the zero-dependency benefit. "
    ) + "filler " * 280
    assert len(over_cap_brief.split()) > GATE_BRIEF_WORD_CAP + 25, (
        "Test setup: over-cap brief must exceed GATE_BRIEF_WORD_CAP + 25 to "
        "exercise the over-cap render path."
    )
    ok_c, reason_c = validate_brief(over_cap_brief)
    assert ok_c, (
        "Test setup: over-cap brief must pass validate_brief (cap is advisory) "
        f"so it posts rather than falling back: {reason_c}"
    )
    assert brief_word_overage(over_cap_brief) > 0, (
        "Test setup: over-cap brief must report a positive overage."
    )

    (topic_dir_c / "brief.md").write_text(over_cap_brief + "\n", encoding="utf-8")

    rendered_c = _render_gate(topic_dir_c, fixture_research_md)

    # The rendered output must contain the brief content.
    assert "native GitHub badge" in rendered_c, (
        "Over-cap rendered gate output does not contain brief content — an "
        "anchor-valid over-cap brief must still post.\n"
        f"Rendered:\n{rendered_c}"
    )

    # The rendered output must carry the soft-note marker (mirrors the Task 4
    # prose token "advisory cap" / "over").
    assert "advisory cap" in rendered_c, (
        "Over-cap rendered gate output is missing the 'advisory cap' soft-note "
        "marker that the Task 4 SKILL.md prose mandates.\n"
        f"Rendered:\n{rendered_c}"
    )
    assert "over" in rendered_c, (
        "Over-cap rendered gate output is missing the overage 'over' phrasing.\n"
        f"Rendered:\n{rendered_c}"
    )

    # The rendered output must NOT fall back to the ## Architecture body.
    assert "## Architecture" not in rendered_c, (
        "Over-cap rendered gate output contains '## Architecture' — an over-cap "
        "anchored brief must NOT trigger the Architecture fallback.\n"
        f"Rendered:\n{rendered_c}"
    )
    assert "### Pieces" not in rendered_c, (
        "Over-cap rendered gate output contains '### Pieces' (Architecture "
        "section body) — the over-cap brief must post, not fall back.\n"
        f"Rendered:\n{rendered_c}"
    )

    # --- SKILL.md gate options check ---
    # Verify the canonical SKILL.md source still carries all four gate options (Req 7).
    # The options appear as individual bolded bullets; we check each is present.
    discovery_skill = REPO_ROOT / "skills" / "discovery" / "SKILL.md"
    skill_text = discovery_skill.read_text(encoding="utf-8")
    for option in _GATE_OPTION_ITEMS:
        assert option in skill_text, (
            f"skills/discovery/SKILL.md no longer contains gate option {option!r}. "
            "Req 7 requires all four options (approve, revise, drop, promote-sub-topic) "
            "to be preserved in the Research → Decompose gate prose."
        )


# ---------------------------------------------------------------------------
# Test 4: validation_failed event payload carries brief_excerpt (no auth)
# ---------------------------------------------------------------------------


def test_validation_failed_event_includes_brief_excerpt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The gate_brief_generated event with status=validation_failed must include
    a non-empty ``brief_excerpt`` (first 200 chars) when the rejected brief was
    non-empty.

    Drives the validation_failed branch by stubbing ``_run_brief_query`` to
    return a deterministic non-empty brief that fails ``validate_brief`` (it
    contains no decision/alternatives/tradeoff anchors). Asserts the events.log
    entry written under ``tmp_path`` carries the new ``brief_excerpt`` field.
    """
    import argparse

    from cortex_command import discovery

    # A non-empty brief that fails validate_brief: no decision/alternatives/
    # tradeoff anchors anywhere in the text. The "X" filler keeps the brief
    # under the word cap so the rejection reason is anchor-missing rather than
    # over-cap (either failure mode would still emit validation_failed, but
    # anchor-missing is the more representative case we want to instrument).
    rejected_brief = (
        "This brief discusses several topics in plain prose without any of "
        "the required anchor vocabulary. It enumerates findings, surveys the "
        "landscape, and notes observations. No conclusion is rendered here."
    )
    ok, _ = validate_brief(rejected_brief)
    assert not ok, (
        "Test setup: the rejected_brief is supposed to fail validate_brief "
        "so the validation_failed branch fires — fix the test fixture."
    )

    async def _stub_run_brief_query(
        research_md_content: str,
        retry_feedback: str | None = None,
    ) -> str:
        return rejected_brief

    monkeypatch.setattr(discovery, "_run_brief_query", _stub_run_brief_query)

    # Lay out a research.md under tmp_path so the subcommand can resolve a
    # topic + repo-root and find the events log target.
    topic = "validation-failed-excerpt-test"
    research_dir = tmp_path / "cortex" / "research" / topic
    research_dir.mkdir(parents=True)
    research_md = research_dir / "research.md"
    research_md.write_text(
        "# Research: validation-failed-excerpt-test\n\nstub content.\n",
        encoding="utf-8",
    )

    args = argparse.Namespace(
        research_md=str(research_md),
        topic=topic,
        repo_root=str(tmp_path),
        persist_to=None,
    )

    rc = discovery._cmd_generate_brief(args)
    assert rc != 0, (
        "generate-brief was expected to exit non-zero when the stubbed brief "
        f"fails validate_brief, but exit code was {rc}."
    )

    events_log = research_dir / "events.log"
    assert events_log.is_file(), (
        f"Expected events.log at {events_log} after generate-brief failure, "
        "but file was not created."
    )

    events = [
        json.loads(line)
        for line in events_log.read_text().splitlines()
        if line.strip()
    ]
    brief_events = [e for e in events if e.get("event") == "gate_brief_generated"]
    assert brief_events, (
        f"No gate_brief_generated event found in events.log.\nEvents: {events}"
    )

    failed_events = [e for e in brief_events if e.get("status") == "validation_failed"]
    assert failed_events, (
        "Expected at least one gate_brief_generated event with "
        f"status=validation_failed; got statuses: "
        f"{[e.get('status') for e in brief_events]}"
    )

    last_failed = failed_events[-1]
    assert "brief_excerpt" in last_failed, (
        f"validation_failed event payload is missing brief_excerpt field.\n"
        f"Event: {last_failed}"
    )
    excerpt = last_failed["brief_excerpt"]
    assert isinstance(excerpt, str) and excerpt, (
        f"brief_excerpt must be a non-empty string; got {excerpt!r}"
    )
    # The excerpt is the first 200 chars of the rejected brief (or fewer if
    # the brief is shorter). Verify the prefix matches.
    assert excerpt == rejected_brief[:200], (
        f"brief_excerpt does not match first 200 chars of rejected brief.\n"
        f"Expected: {rejected_brief[:200]!r}\nGot: {excerpt!r}"
    )


# ---------------------------------------------------------------------------
# Test 4b: over-cap anchored brief posts with ok_over_cap (no auth) — Reqs 3, 4
# ---------------------------------------------------------------------------


def test_over_cap_brief_persists_and_posts_ok_over_cap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An anchor-valid but over-cap brief posts instead of falling back.

    Stubs ``_run_brief_query`` (ignoring ``retry_feedback`` so the first
    validation deterministically passes and no retry fires) to return an
    over-cap brief containing all three decision-content anchors. Asserts the
    subcommand exits 0, writes ``brief.md`` with the stubbed content, and emits
    a ``gate_brief_generated`` event with ``status == "ok_over_cap"`` and the
    real ``brief_word_count``.
    """
    import argparse

    from cortex_command import discovery

    # Build an over-cap brief that passes validate_brief: it opens with a
    # sentence carrying all three anchors (decided / alternatives / tradeoff),
    # then pads with filler so the word count exceeds GATE_BRIEF_WORD_CAP + 25.
    anchor_sentence = (
        "We decided on the native approach after we weighed the alternatives, "
        "accepting the maintenance cost as a tradeoff."
    )
    filler = (
        "The research surveyed the landscape and enumerated supporting context "
        "in plain prose across many sentences. "
    )
    over_cap_brief = anchor_sentence + " " + (filler * 30).strip()

    expected_word_count = len(over_cap_brief.split())
    assert brief_word_overage(over_cap_brief) > 0, (
        "Test setup: over_cap_brief must exceed GATE_BRIEF_WORD_CAP + 25 so the "
        f"ok_over_cap path fires; word count is {expected_word_count}."
    )
    ok, reason = validate_brief(over_cap_brief)
    assert ok, (
        "Test setup: over_cap_brief must pass validate_brief (cap is advisory) "
        f"so it posts rather than falling back; got reason: {reason!r}"
    )

    async def _stub_run_brief_query(
        research_md_content: str,
        retry_feedback: str | None = None,
    ) -> str:
        # Ignore retry_feedback: the first validation passes, so no retry fires.
        return over_cap_brief

    monkeypatch.setattr(discovery, "_run_brief_query", _stub_run_brief_query)

    topic = "over-cap-ok-test"
    research_dir = tmp_path / "cortex" / "research" / topic
    research_dir.mkdir(parents=True)
    research_md = research_dir / "research.md"
    research_md.write_text(
        "# Research: over-cap-ok-test\n\nstub content.\n",
        encoding="utf-8",
    )
    persist_to = research_dir / "brief.md"

    args = argparse.Namespace(
        research_md=str(research_md),
        topic=topic,
        repo_root=str(tmp_path),
        persist_to=str(persist_to),
    )

    rc = discovery._cmd_generate_brief(args)
    assert rc == 0, (
        "generate-brief was expected to exit 0 for an anchor-valid over-cap "
        f"brief (cap is advisory), but exit code was {rc}."
    )

    assert persist_to.is_file(), (
        f"Expected brief.md persisted at {persist_to} for an over-cap brief, "
        "but file was not written."
    )
    persisted = persist_to.read_text(encoding="utf-8")
    assert persisted.rstrip("\n") == over_cap_brief.rstrip("\n"), (
        "Persisted brief.md content does not match the stubbed over-cap brief.\n"
        f"Expected:\n{over_cap_brief}\nGot:\n{persisted}"
    )

    events_log = research_dir / "events.log"
    assert events_log.is_file(), (
        f"Expected events.log at {events_log} after generate-brief, but file "
        "was not created."
    )
    events = [
        json.loads(line)
        for line in events_log.read_text().splitlines()
        if line.strip()
    ]
    brief_events = [e for e in events if e.get("event") == "gate_brief_generated"]
    assert brief_events, (
        f"No gate_brief_generated event found in events.log.\nEvents: {events}"
    )
    over_cap_events = [e for e in brief_events if e.get("status") == "ok_over_cap"]
    assert over_cap_events, (
        "Expected a gate_brief_generated event with status=ok_over_cap; got "
        f"statuses: {[e.get('status') for e in brief_events]}"
    )
    last = over_cap_events[-1]
    assert last.get("brief_word_count") == expected_word_count, (
        "ok_over_cap event brief_word_count does not match the brief's word "
        f"count.\nExpected: {expected_word_count}\nGot: {last.get('brief_word_count')}"
    )


# ---------------------------------------------------------------------------
# Test 5: anchor paraphrase coverage (no auth) — spec Reqs 3, 4, 5
#
# Each parametrized test constructs a minimal brief containing the
# under-test token in the corresponding anchor's sentence, plus valid
# canonical tokens for the other two anchors. The decision-anchor test
# slots its token into the first sentence; alternatives into the second;
# tradeoff into the third.
# ---------------------------------------------------------------------------


_DECISION_PARAPHRASE_TOKENS = (
    "decide",
    "decided",
    "decision",
    "decisions",
    "chose",
    "chosen",
    "concluded",
    "settled",
    "selected",
    "picked",
    "opted",
    "agreed",
)


@pytest.mark.parametrize("token", _DECISION_PARAPHRASE_TOKENS)
def test_validate_brief_decision_anchor_paraphrases(token: str) -> None:
    """validate_brief() accepts every canonical decision-anchor token."""
    brief = (
        f"We {token} on X. Two options were weighed. The compromise was Y."
    )
    ok, reason = validate_brief(brief)
    assert ok, (
        f"Expected validate_brief to accept decision token {token!r}, "
        f"but got reason: {reason}\nBrief: {brief!r}"
    )


_ALTERNATIVES_PARAPHRASE_TOKENS = (
    "alternative",
    "alternatives",
    "option",
    "options",
    "considered",
    "considerations",
    "weighed",
    "evaluated",
    "rejected",
)


@pytest.mark.parametrize("token", _ALTERNATIVES_PARAPHRASE_TOKENS)
def test_validate_brief_alternatives_anchor_paraphrases(token: str) -> None:
    """validate_brief() accepts every canonical alternatives-anchor token."""
    brief = (
        f"We decided on X. Two {token} shaped the path. The compromise was Y."
    )
    ok, reason = validate_brief(brief)
    assert ok, (
        f"Expected validate_brief to accept alternatives token {token!r}, "
        f"but got reason: {reason}\nBrief: {brief!r}"
    )


_TRADEOFF_PARAPHRASE_TOKENS = (
    "tradeoff",
    "trade-off",
    "cost",
    "drawback",
    "downside",
    "sacrifice",
    "consequence",
    "compromise",
    "risk",
)


@pytest.mark.parametrize("token", _TRADEOFF_PARAPHRASE_TOKENS)
def test_validate_brief_tradeoff_anchor_paraphrases(token: str) -> None:
    """validate_brief() accepts every canonical tradeoff-anchor token."""
    brief = (
        f"We decided on X. Two options were weighed. The {token} was Y."
    )
    ok, reason = validate_brief(brief)
    assert ok, (
        f"Expected validate_brief to accept tradeoff token {token!r}, "
        f"but got reason: {reason}\nBrief: {brief!r}"
    )


# ---------------------------------------------------------------------------
# Test 6: word-boundary false-positive rejection (no auth) — spec Req 6
#
# Each FP token contains a canonical-anchor token as a substring but is
# semantically unrelated. The brief contains valid prose for the OTHER two
# anchors; the failure reason must name the anchor the FP token was
# (intentionally) failing to satisfy.
# ---------------------------------------------------------------------------


# Tuples of (fp_token, target_anchor_keyword_in_reason, brief_template).
# The brief_template uses {fp} for the FP token and supplies natural prose
# for the OTHER two anchors so only the target anchor fails.
_FALSE_POSITIVE_CASES = (
    # optional ⊃ option (alternatives anchor)
    (
        "optional",
        "alternatives",
        "We decided on X. The {fp} flag was set. The compromise was Y.",
    ),
    # optionality ⊃ option (alternatives anchor)
    (
        "optionality",
        "alternatives",
        "We decided on X. The system has {fp} baked in. The compromise was Y.",
    ),
    # committee ⊃ committed (no canonical) but spec lists it as FP
    # for decision anchor — committee contains no decision token but the
    # spec's canonical false-positive set treats it as exercising the
    # decision-anchor boundary.
    (
        "committee",
        "decision",
        "The {fp} reviewed it. Two options were weighed. The compromise was Y.",
    ),
    # unsettled ⊃ settled (decision anchor)
    (
        "unsettled",
        "decision",
        "Things were {fp}. Two options were weighed. The compromise was Y.",
    ),
    # disagreed ⊃ agreed (decision anchor)
    (
        "disagreed",
        "decision",
        "The team {fp}. Two options were weighed. The compromise was Y.",
    ),
    # costume ⊃ cost (tradeoff anchor)
    (
        "costume",
        "tradeoff",
        "We decided on X. Two options were weighed. The {fp} budget was set.",
    ),
    # pickup ⊃ picked (decision anchor)
    (
        "pickup",
        "decision",
        "The {fp} truck broke. Two options were weighed. The compromise was Y.",
    ),
)


@pytest.mark.parametrize("fp_token,target_anchor,template", _FALSE_POSITIVE_CASES)
def test_validate_brief_word_boundary_false_positives(
    fp_token: str, target_anchor: str, template: str
) -> None:
    """validate_brief() rejects briefs whose only candidate for one anchor is a
    substring false-positive of a canonical token (e.g., 'optional' must not
    satisfy the alternatives anchor via substring match on 'option').
    """
    brief = template.format(fp=fp_token)
    ok, reason = validate_brief(brief)
    assert not ok, (
        f"Expected validate_brief to reject brief with FP token {fp_token!r} "
        f"on {target_anchor} anchor, but it passed.\nBrief: {brief!r}"
    )
    assert target_anchor in reason, (
        f"Expected failure reason to name {target_anchor!r} anchor when "
        f"FP token {fp_token!r} fails to satisfy it; got reason: {reason!r}"
    )


# ---------------------------------------------------------------------------
# Test 7: anchor-missing error messages enumerate broadened tokens — Req 10
#
# Pins ALL THREE anchor-missing failure reasons against representative
# broadened-token substrings so silent narrowing of any reason regresses a
# test. Critical-review found the previous draft only pinned decision-anchor
# tokens; this test closes that gap (cross-cutting acceptance gate, Task 8).
# ---------------------------------------------------------------------------


def test_validate_brief_error_messages_name_broadened_anchors() -> None:
    """validate_brief() anchor-missing reasons enumerate broadened canonical
    tokens for all three anchors (decision, alternatives, tradeoff).
    """
    # (a) Decision-anchor failure: brief has valid alternatives + tradeoff
    # anchors but no decision-anchor token. Reason must enumerate 'chose'
    # AND 'settled' (broadened decision tokens beyond 'decided').
    decision_missing_brief = (
        "Two options were weighed. The compromise was Y."
    )
    ok, reason = validate_brief(decision_missing_brief)
    assert not ok, (
        "Expected validate_brief to reject brief missing decision anchor, "
        f"but it passed.\nBrief: {decision_missing_brief!r}"
    )
    assert "decision" in reason, (
        f"Expected decision-anchor failure reason to name 'decision'; "
        f"got: {reason!r}"
    )
    assert "chose" in reason, (
        f"Expected decision-anchor failure reason to enumerate 'chose' "
        f"(broadened token); got: {reason!r}"
    )
    assert "settled" in reason, (
        f"Expected decision-anchor failure reason to enumerate 'settled' "
        f"(broadened token); got: {reason!r}"
    )

    # (b) Alternatives-anchor failure: brief has valid decision + tradeoff
    # anchors but no alternatives-anchor token. Reason must enumerate at
    # least 2 of {considered, weighed, evaluated, rejected} (broadened
    # alternatives tokens beyond 'alternatives'/'options').
    alternatives_missing_brief = (
        "We decided on X. The compromise was Y."
    )
    ok, reason = validate_brief(alternatives_missing_brief)
    assert not ok, (
        "Expected validate_brief to reject brief missing alternatives "
        f"anchor, but it passed.\nBrief: {alternatives_missing_brief!r}"
    )
    assert "alternatives" in reason, (
        f"Expected alternatives-anchor failure reason to name "
        f"'alternatives'; got: {reason!r}"
    )
    broadened_alt_tokens = {"considered", "weighed", "evaluated", "rejected"}
    present_alt = {tok for tok in broadened_alt_tokens if tok in reason}
    assert len(present_alt) >= 2, (
        f"Expected alternatives-anchor failure reason to enumerate at "
        f"least 2 of {sorted(broadened_alt_tokens)}; found {sorted(present_alt)} "
        f"in reason: {reason!r}"
    )

    # (c) Tradeoff-anchor failure: brief has valid decision + alternatives
    # anchors but no tradeoff-anchor token. Reason must enumerate at least
    # 2 of {drawback, downside, compromise, risk} (broadened tradeoff
    # tokens beyond 'tradeoff'/'cost').
    tradeoff_missing_brief = (
        "We decided on X. Two options were weighed."
    )
    ok, reason = validate_brief(tradeoff_missing_brief)
    assert not ok, (
        "Expected validate_brief to reject brief missing tradeoff anchor, "
        f"but it passed.\nBrief: {tradeoff_missing_brief!r}"
    )
    assert "tradeoff" in reason, (
        f"Expected tradeoff-anchor failure reason to name 'tradeoff'; "
        f"got: {reason!r}"
    )
    broadened_tradeoff_tokens = {"drawback", "downside", "compromise", "risk"}
    present_tradeoff = {
        tok for tok in broadened_tradeoff_tokens if tok in reason
    }
    assert len(present_tradeoff) >= 2, (
        f"Expected tradeoff-anchor failure reason to enumerate at least 2 "
        f"of {sorted(broadened_tradeoff_tokens)}; found "
        f"{sorted(present_tradeoff)} in reason: {reason!r}"
    )


# ---------------------------------------------------------------------------
# Test 8: retry-feedback covers every example token — Req 9
#
# Pins the rendered retry-feedback prose against the full agent-facing
# example-token set (``_GATE_BRIEF_EXAMPLE_TOKENS``) so silent narrowing of
# the retry vocabulary regresses a test. Closes the third-vertex drift
# critical-review flagged: rubric → constant binding (Task 3) and validator
# → 30-token floor (Task 4) were complete, but retry feedback still had a
# hardcoded narrow enumeration prior to Task 6.
# ---------------------------------------------------------------------------


def test_retry_feedback_covers_example_tokens() -> None:
    """Rendered retry feedback enumerates every token in ``_GATE_BRIEF_EXAMPLE_TOKENS``.

    Imports the module-level retry template, renders it with a representative
    ``reason`` argument, and asserts every token from each anchor's full
    example set appears in the rendered prose.
    """
    from cortex_command.discovery import (
        _GATE_BRIEF_EXAMPLE_TOKENS,
        _GATE_BRIEF_RETRY_TEMPLATE,
    )

    rendered = _GATE_BRIEF_RETRY_TEMPLATE.format(
        reason="representative validation failure for test"
    )

    # The dynamic reason must be interpolated into the rendered prose.
    assert "representative validation failure for test" in rendered, (
        "Expected the {reason} placeholder to interpolate the supplied "
        f"reason into the rendered retry feedback; got: {rendered!r}"
    )

    # Every token from every anchor's example set must appear verbatim.
    missing: list[tuple[str, str]] = []
    for anchor, tokens in _GATE_BRIEF_EXAMPLE_TOKENS.items():
        for token in tokens:
            if token not in rendered:
                missing.append((anchor, token))

    assert not missing, (
        "Rendered retry feedback is missing tokens from "
        f"_GATE_BRIEF_EXAMPLE_TOKENS: {missing}\n"
        f"Rendered prose:\n{rendered}"
    )


# ---------------------------------------------------------------------------
# Test 9: canonical-floor parity test (validator side) — Req 8
#
# Pins the validator's accepted vocabulary against a FROZEN LITERAL canonical
# token set declared inside this test file (NOT imported from
# cortex_command.discovery). This is the durability guard against the
# regression mode the previous spec draft missed: even if a future commit
# shrinks both ``_GATE_BRIEF_EXAMPLE_TOKENS`` (Task 3) AND the validator's
# anchor sets (Task 4) in lockstep, this test still fails because the floor
# is declared independently in this file.
#
# DO NOT import the canonical floor from cortex_command/discovery — doing so
# would defeat the lockstep regression guard (per spec Req 8).
# ---------------------------------------------------------------------------


# Frozen at this spec's approval (verbatim from spec Reqs 3-5):
# 12 decision tokens + 9 alternatives tokens + 9 tradeoff tokens = 30 tokens.
_CANONICAL_FLOOR_DECISION_TOKENS = (
    "decide",
    "decided",
    "decision",
    "decisions",
    "chose",
    "chosen",
    "concluded",
    "settled",
    "selected",
    "picked",
    "opted",
    "agreed",
)

_CANONICAL_FLOOR_ALTERNATIVES_TOKENS = (
    "alternative",
    "alternatives",
    "option",
    "options",
    "considered",
    "considerations",
    "weighed",
    "evaluated",
    "rejected",
)

_CANONICAL_FLOOR_TRADEOFF_TOKENS = (
    "tradeoff",
    "trade-off",
    "cost",
    "drawback",
    "downside",
    "sacrifice",
    "consequence",
    "compromise",
    "risk",
)


def _minimal_brief_for(anchor: str, token: str) -> str:
    """Build a minimal brief that places ``token`` in ``anchor``'s sentence and
    fills the other two anchors with canonical tokens.

    The decision sentence uses ``chose``; alternatives uses ``options were
    weighed``; tradeoff uses ``compromise``. When ``token`` belongs to one of
    those anchors, that anchor's slot is rewritten to host the token instead.
    """
    if anchor == "decision":
        return f"We {token} on X. Two options were weighed. The compromise was Y."
    if anchor == "alternatives":
        return f"We chose X. Two {token} shaped the path. The compromise was Y."
    if anchor == "tradeoff":
        return f"We chose X. Two options were weighed. The {token} was Y."
    raise ValueError(f"Unknown anchor: {anchor!r}")


_CANONICAL_FLOOR_CASES = (
    [("decision", t) for t in _CANONICAL_FLOOR_DECISION_TOKENS]
    + [("alternatives", t) for t in _CANONICAL_FLOOR_ALTERNATIVES_TOKENS]
    + [("tradeoff", t) for t in _CANONICAL_FLOOR_TRADEOFF_TOKENS]
)


@pytest.mark.parametrize("anchor,token", _CANONICAL_FLOOR_CASES)
def test_validate_brief_canonical_floor(anchor: str, token: str) -> None:
    """validate_brief() accepts every token in the frozen canonical floor.

    The floor (30 tokens) is declared as a frozen literal in this test file,
    independent of ``cortex_command.discovery``. If the validator's anchor
    set shrinks below this floor (alone or in lockstep with
    ``_GATE_BRIEF_EXAMPLE_TOKENS``), this test fails.
    """
    brief = _minimal_brief_for(anchor, token)
    result = validate_brief(brief)
    assert result == (True, ""), (
        f"Expected validate_brief to accept canonical {anchor} token "
        f"{token!r} and return (True, ''), but got {result!r}.\n"
        f"Brief: {brief!r}"
    )


# ---------------------------------------------------------------------------
# Advisory word cap: over-cap anchored briefs pass; overage is a signal
# ---------------------------------------------------------------------------


def test_validate_brief_over_cap_anchored_passes() -> None:
    """An anchor-valid over-cap brief is accepted: the cap is advisory."""
    anchored = "We decided to ship. Alternatives were weighed. The tradeoff is cost. "
    brief = anchored + "filler " * 400
    assert len(brief.split()) > GATE_BRIEF_WORD_CAP + 25, (
        "Test setup: brief must exceed the advisory ceiling to exercise the "
        "over-cap path."
    )
    result = validate_brief(brief)
    assert result == (True, ""), (
        "Expected validate_brief to accept an anchor-valid over-cap brief and "
        f"return (True, '') (cap is advisory), but got {result!r}."
    )


@pytest.mark.parametrize(
    "filler_words,expect_positive",
    [
        (0, False),
        (10, False),
        (400, True),
    ],
)
def test_brief_word_overage(filler_words: int, expect_positive: bool) -> None:
    """brief_word_overage() returns 0 within the ceiling, positive over it."""
    anchored = "We decided to ship. Alternatives were weighed. The tradeoff is cost. "
    brief = anchored + "filler " * filler_words
    overage = brief_word_overage(brief)
    if expect_positive:
        cap = GATE_BRIEF_WORD_CAP + 25
        assert overage == len(brief.split()) - cap, (
            f"Expected overage to equal words-over-{cap}, got {overage}."
        )
        assert overage > 0
    else:
        assert overage == 0, (
            f"Expected 0 overage for a within-ceiling brief, got {overage}."
        )
