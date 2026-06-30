"""Prose-contract tests for the research consumer side of the #337
refine->research considerations file channel.

Guards the migration of research's Step 1 from the model-parsed
``research-considerations`` value-key to a ``research-considerations-file``
path key whose file the orchestrator body reads and injects by content.

Classification (per spec R11):
  - Red-before-green (strings change with the migration): R4 (read-and-
    substitute-content instruction present), R5 (escaping caveat removed),
    R6 (positive: read-and-substitute names literal content), no-stale-key.
  - Preservation / negative-control (green today and after): R6 (negative:
    agent-prompt fences carry only the placeholder, never the path), R8
    (standalone reads nothing), reader-contract anchor.

Modeled on tests/test_refine_skill.py's anchored-slice pattern.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SKILL_MD = REPO_ROOT / "skills" / "research" / "SKILL.md"

STEP1_HEADING = "## Step 1: Parse Arguments"
PLACEHOLDER = "{research_considerations_bullets}"


def _read() -> str:
    return SKILL_MD.read_text(encoding="utf-8")


def _slice(text: str, start_anchor: str, stop_re: str) -> str:
    start = text.find(start_anchor)
    if start == -1:
        pytest.fail(f"anchor {start_anchor!r} not found in {SKILL_MD}")
    after = text[start + len(start_anchor):]
    m = re.search(stop_re, after)
    end = start + len(start_anchor) + (m.start() if m else len(after))
    return text[start:end]


def _fenced_blocks(text: str) -> list[str]:
    """All triple-backtick fenced blocks."""
    return re.findall(r"```.*?```", text, re.DOTALL)


# --- anchors (non-vacuity; green before and after) ------------------------


def test_step1_heading_present() -> None:
    assert STEP1_HEADING in _read(), f"{STEP1_HEADING!r} heading missing"


def test_three_placeholders_retained() -> None:
    """The three core-angle injection placeholders are unchanged (anchor)."""
    assert _read().count(PLACEHOLDER) == 3, (
        f"expected exactly 3 {PLACEHOLDER} placeholders"
    )


# --- R5 caveat removed (red-before-green) ---------------------------------


def test_research_escaping_caveat_removed() -> None:
    assert "are not supported in the value" not in _read(), (
        "research still carries the 'not supported in the value' escaping caveat"
    )


# --- R4 key rename + read-and-substitute instruction (red-before-green) ----


def test_research_considerations_file_key_present() -> None:
    assert "research-considerations-file" in _read(), (
        "research Step 1 does not define the research-considerations-file key"
    )


def test_research_reads_and_substitutes_content() -> None:
    """An explicit instruction that research's body reads the file and
    substitutes its literal content (not merely a key rename)."""
    assert re.search(
        r"read\w*\s+(?:that|the)\s+file\s+and\s+substitut\w+\s+its\s+literal\s+content",
        _read(),
        re.IGNORECASE,
    ), "no read-the-file-and-substitute-its-literal-content instruction found"


# --- R6 inject content, not the path (positive red-before-green; negative
#     control structural) ---------------------------------------------------


def test_inject_content_not_path() -> None:
    text = _read()
    # Positive: the read-and-substitute instruction names literal content.
    assert re.search(r"literal\s+content", text, re.IGNORECASE), (
        "injection prose does not name literal content as what is injected"
    )
    # Negative control: every agent-prompt fence that carries the placeholder
    # carries ONLY the placeholder — never the path arg, the .md filename, or a
    # read-the-file directive forwarded into the subagent prompt.
    for fence in _fenced_blocks(text):
        if PLACEHOLDER not in fence:
            continue
        assert "research-considerations-file" not in fence, (
            "agent-prompt fence forwards the research-considerations-file path "
            "arg into the subagent prompt — inject content, not the path"
        )
        assert "research-considerations.md" not in fence, (
            "agent-prompt fence names the research-considerations.md path"
        )
        assert not re.search(r"read\s+(?:that|the)\s+file", fence, re.IGNORECASE), (
            "agent-prompt fence instructs the subagent to read the file itself"
        )


# --- reader contract: absent/empty/whitespace => no injection (red-before-green)


def test_reader_contract_empty_no_injection() -> None:
    """Research conditions injection on the file being non-empty; absent,
    empty, or whitespace-only yields no injection (and no halt)."""
    text = _read()
    assert re.search(
        r"(absent|missing|empty|whitespace)[^.\n]*no\s+(?:considerations\s+)?injection|"
        r"no\s+(?:considerations\s+)?inject[^.\n]*(absent|missing|empty|whitespace)",
        text,
        re.IGNORECASE,
    ), "reader contract (empty/absent/whitespace => no injection) not stated"
    assert re.search(r"do\s+not\s+halt|not\s+halt", text, re.IGNORECASE), (
        "reader contract does not state that a missing file must not halt"
    )


# --- R8 standalone reads nothing (negative control; green before and after) -


def test_standalone_reads_nothing() -> None:
    """The standalone-mode path reads no considerations file (vacuously green
    today; guards a future unconditional read)."""
    standalone = _slice(_read(), "**Standalone mode**", r"\n## ")
    assert "research-considerations-file" not in standalone, (
        "standalone-mode path references the considerations file arg"
    )
    assert not re.search(r"read\s+(?:that|the)\s+(?:considerations\s+)?file", standalone, re.IGNORECASE), (
        "standalone-mode path instructs reading a considerations file"
    )


# --- no stale bare value-key survives (red-before-green) -------------------


def test_no_stale_bare_value_key() -> None:
    """Every research-considerations occurrence is the new -file key; no bare
    value-key reference dangles in Step 1, the injection section, or the
    output trigger."""
    stale = re.findall(r"research-considerations(?!-file)(?!\.md)", _read())
    assert not stale, (
        f"{len(stale)} stale bare research-considerations value-key reference(s) survive"
    )
