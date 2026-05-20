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
    validate_brief,
)


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
         return its content.
      2. Otherwise, extract the ``## Architecture`` body from ``research_md``
         and return it with a ``brief_generation_failed`` warning prefixed.

    This is not a published Python API — it is a test-local implementation of
    the file-reading contract described in SKILL.md.  Task 9's ``score-corpus``
    subcommand exercises the same contract over the live corpus.
    """
    brief_path = topic_dir / "brief.md"
    if brief_path.is_file():
        brief_text = brief_path.read_text(encoding="utf-8").strip()
        if brief_text:
            ok, _ = validate_brief(brief_text)
            if ok:
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
