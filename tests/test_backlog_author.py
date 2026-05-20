"""Behavioral tests for the backlog-author sub-skill and its integration points.

Covers the gameable behaviors specified in Requirement 12 of the
``add-backlog-create-skill`` lifecycle spec:

- ``test_compose_mode_emits_five_section_body``: the compose path produces a
  body that contains all five expected section headings with non-empty content.
- ``test_compose_mode_does_not_call_askuserquestion``: the compose section of
  SKILL.md contains zero ``AskUserQuestion`` references (R6 regression guard).
- ``test_interview_mode_routes_through_askuserquestion``: the interview section
  of SKILL.md references ``AskUserQuestion`` at least once.
- ``test_lex1_rejects_code_block_in_why_section``: LEX-1 scanner exits non-zero
  when given a fixture whose ``## Why`` section contains a fenced code block.
- ``test_create_item_accepts_body_flag``: ``cortex-create-backlog-item --body``
  appends the body verbatim after the frontmatter closing delimiter.

Test functions are added in Task 9. This module provides the skeleton
(imports, fixtures, helpers) that Task 9 will populate.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Repo-level constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "backlog_author"
SKILL_MD = REPO_ROOT / "skills" / "backlog-author" / "SKILL.md"
LEX1_SCRIPT = REPO_ROOT / "bin" / "cortex-check-prescriptive-prose"
CREATE_ITEM_BIN = REPO_ROOT / "bin" / "cortex-create-backlog-item"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_fixture(name: str) -> str:
    """Return the text content of a fixture file by basename."""
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def _run_lex1(file_path: Path) -> subprocess.CompletedProcess[bytes]:
    """Invoke the LEX-1 scanner in positional file-arg mode on *file_path*."""
    return subprocess.run(
        [sys.executable, str(LEX1_SCRIPT), str(file_path)],
        capture_output=True,
        check=False,
    )


def _extract_skill_section(text: str, section_heading: str) -> str:
    """Extract lines belonging to the named ``### <section>`` block in *text*.

    Returns all lines from the heading line up to (but not including) the next
    ``### `` or ``## `` heading, joined as a single string.
    """
    lines = text.splitlines(keepends=True)
    inside = False
    collected: list[str] = []
    for line in lines:
        if line.startswith(f"### {section_heading}"):
            inside = True
            collected.append(line)
            continue
        if inside:
            if line.startswith("### ") or line.startswith("## "):
                break
            collected.append(line)
    return "".join(collected)


# ---------------------------------------------------------------------------
# Test functions (bodies added in Task 9)
# ---------------------------------------------------------------------------


def test_compose_mode_emits_five_section_body() -> None:
    """Compose path produces a body with all five section headings and content.

    Since the compose subcommand is model-invoked at runtime, this test asserts
    the SKILL.md compose section's structural protocol: it references all five
    section headings (Why, Role, Integration, Edges, Touch points) and includes
    the body-template reference and output contract directive.
    """
    skill_text = SKILL_MD.read_text(encoding="utf-8")
    compose_section = _extract_skill_section(skill_text, "compose")

    expected_headings = ["## Why", "## Role", "## Integration", "## Edges", "## Touch points"]
    for heading in expected_headings:
        assert heading in compose_section, (
            f"compose section of SKILL.md does not reference heading {heading!r}"
        )

    # Output contract must be present — the section documents what is emitted.
    assert "body" in compose_section.lower(), (
        "compose section does not document the output body contract"
    )

    # Body-template reference must be present — compose reads the template.
    assert "body-template.md" in compose_section, (
        "compose section does not reference skills/backlog-author/references/body-template.md"
    )


def test_compose_mode_does_not_call_askuserquestion() -> None:
    """Compose section of SKILL.md contains zero AskUserQuestion references."""
    skill_text = SKILL_MD.read_text(encoding="utf-8")
    compose_section = _extract_skill_section(skill_text, "compose")

    assert "AskUserQuestion" not in compose_section, (
        "compose section of SKILL.md references AskUserQuestion — "
        "the compose path must not prompt the user (R6 regression)"
    )


def test_interview_mode_routes_through_askuserquestion() -> None:
    """Interview section of SKILL.md references AskUserQuestion at least once."""
    skill_text = SKILL_MD.read_text(encoding="utf-8")
    interview_section = _extract_skill_section(skill_text, "interview")

    count = interview_section.count("AskUserQuestion")
    assert count >= 1, (
        f"interview section of SKILL.md contains {count} AskUserQuestion reference(s); "
        "expected ≥1 (interview mode must use AskUserQuestion per R6)"
    )


def test_lex1_rejects_code_block_in_why_section() -> None:
    """LEX-1 exits non-zero when Why section contains a fenced code block."""
    fixture_path = FIXTURES_DIR / "why_with_code_block.md"
    result = _run_lex1(fixture_path)

    assert result.returncode != 0, (
        "LEX-1 scanner returned exit 0 for a fixture whose ## Why section "
        "contains a fenced code block — expected non-zero exit (LEX-1 violation)"
    )


def test_create_item_accepts_body_flag(tmp_path: Path) -> None:
    """cortex-create-backlog-item --body appends the body verbatim."""
    fixture_body = _read_fixture("valid_five_section.md")

    # Set up a minimal cortex project layout under tmp_path so the CLI can
    # resolve its backlog directory via CORTEX_REPO_ROOT.
    backlog_dir = tmp_path / "cortex" / "backlog"
    backlog_dir.mkdir(parents=True)

    env = {**__import__("os").environ, "CORTEX_REPO_ROOT": str(tmp_path)}

    result = subprocess.run(
        [
            sys.executable, "-m", "cortex_command.backlog.create_item",
            "--title", "body-flag-test",
            "--status", "backlog",
            "--type", "feature",
            "--body", fixture_body,
        ],
        capture_output=True,
        check=False,
        env=env,
    )

    assert result.returncode == 0, (
        f"cortex-create-backlog-item exited {result.returncode}: "
        f"{result.stderr.decode(errors='replace')}"
    )

    created_files = [p for p in backlog_dir.glob("*.md") if p.name != "index.md"]
    assert len(created_files) == 1, (
        f"expected 1 created backlog item file (excluding index.md), "
        f"found {len(created_files)}: {created_files}"
    )

    created_text = created_files[0].read_text(encoding="utf-8")

    # The body must appear verbatim after the frontmatter closing ---.
    assert fixture_body in created_text, (
        "body fixture was not found verbatim in the created backlog item file"
    )
