"""Prose-contract tests for the refine producer side of the #337
refine->research considerations file channel.

Guards the migration of the alignment-considerations hand-off from a
model-parsed ``research-considerations="<bullets>"`` value-arg to a file
channel: refine writes ``research-considerations.md`` (overwriting, coupled
to the arg, sequenced before the dispatch) and emits only the benign
``research-considerations-file=<path>``.

Classification (per spec R11):
  - Red-before-green (strings change with the migration): R1 (write +
    coupled-arg present; old value-arg absent), R2 (escaping caveat removed),
    R3 (write instruction precedes the dispatch fence), no-stale-bare-key.
  - Preservation / negative-control (green today and after): R7 (conditional
    fire retained; no clear/truncate-each-run discipline).

Modeled on tests/test_refine_skill.py's anchored-slice + negative-regression
pattern.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SKILL_MD = REPO_ROOT / "skills" / "refine" / "SKILL.md"

PROP_HEADING = "### Alignment-Considerations Propagation"
DISPATCH_ANCHOR = "/cortex-core:research topic="
# A line that both names the considerations file and carries a write verb.
WRITE_LINE_RE = re.compile(
    r"^.*\b(?:write|writes|writing|overwrite|overwriting|overwrites)\b"
    r".*research-considerations\.md.*$",
    re.IGNORECASE | re.MULTILINE,
)


def _read() -> str:
    return SKILL_MD.read_text(encoding="utf-8")


def _propagation_block(text: str) -> str:
    """Slice from the propagation heading to the next ``### `` / ``## `` heading."""
    start = text.find(PROP_HEADING)
    if start == -1:
        pytest.fail(f"propagation heading {PROP_HEADING!r} not found in {SKILL_MD}")
    after = text[start + len(PROP_HEADING):]
    end_match = re.search(r"\n#{2,3} ", after)
    end = start + len(PROP_HEADING) + (end_match.start() if end_match else len(after))
    return text[start:end]


def _line_of(text: str, needle: str) -> int:
    """1-indexed line of the first occurrence of needle, or -1."""
    idx = text.find(needle)
    return text.count("\n", 0, idx) + 1 if idx != -1 else -1


# --- R2 anchor (non-vacuity; green before and after) ----------------------


def test_propagation_heading_present() -> None:
    """The ``### Alignment-Considerations Propagation`` h3 heading exists once."""
    text = _read()
    headings = re.findall(rf"^{re.escape(PROP_HEADING)}\s*$", text, re.MULTILINE)
    assert len(headings) == 1, (
        f"expected exactly one {PROP_HEADING!r} h3 heading, found {len(headings)}"
    )


# --- R2 caveat removed (red-before-green) ---------------------------------


def test_refine_escaping_caveat_removed() -> None:
    """The 'Strip or paraphrase away ... = or \"' caveat is gone."""
    assert "Strip or paraphrase away" not in _read(), (
        "refine still carries the escaping caveat — the file channel removes it"
    )


# --- R1 write + coupled arg present; old value-arg absent (red-before-green)


def test_old_value_arg_absent() -> None:
    """The old ``research-considerations="`` value-arg form is gone."""
    assert 'research-considerations="' not in _read(), (
        "refine still emits the value-arg research-considerations=\"...\""
    )


def test_file_write_and_coupling_present() -> None:
    """The propagation block writes the file (overwriting) and carries the
    coupled ``research-considerations-file`` path arg."""
    block = _propagation_block(_read())
    assert WRITE_LINE_RE.search(block), (
        "propagation block has no write instruction targeting "
        "research-considerations.md"
    )
    assert re.search(r"overwrit", block, re.IGNORECASE), (
        "propagation block does not specify overwrite (vs append) semantics"
    )
    assert "research-considerations-file" in block, (
        "propagation block does not carry the coupled research-considerations-file arg"
    )


# --- R3 write precedes dispatch (red-before-green) -------------------------


def test_write_precedes_dispatch() -> None:
    """The first write-instruction line naming research-considerations.md
    appears before the ``/cortex-core:research topic=`` dispatch fence."""
    text = _read()
    write_match = WRITE_LINE_RE.search(text)
    assert write_match, (
        "no write-instruction line naming research-considerations.md found"
    )
    write_line = text.count("\n", 0, write_match.start()) + 1
    dispatch_line = _line_of(text, DISPATCH_ANCHOR)
    assert dispatch_line > 0, f"dispatch anchor {DISPATCH_ANCHOR!r} not found"
    assert write_line < dispatch_line, (
        f"write instruction at line {write_line} does not precede the dispatch "
        f"fence at line {dispatch_line} (read-before-write hazard)"
    )


# --- no stale bare value-key survives (red-before-green) -------------------


def test_no_stale_bare_value_key() -> None:
    """No bare ``research-considerations`` value-key reference survives — every
    occurrence is either ``research-considerations-file`` or the path
    ``research-considerations.md``."""
    text = _read()
    stale = re.findall(r"research-considerations(?!-file)(?!\.md)", text)
    assert not stale, (
        f"{len(stale)} stale bare research-considerations value-key reference(s) "
        f"survive after migration"
    )


# --- R7 conditional-fire + coupling retained; no clear-each-run (preservation)


def test_conditional_fire_retained() -> None:
    """The block fires only when an Apply'd alignment finding exists."""
    block = _propagation_block(_read())
    assert "Apply'd" in block, "propagation block lost the Apply'd-finding condition"
    assert "only when" in block, (
        "propagation block lost its 'only when' conditional-fire language"
    )


def test_no_clear_each_run_discipline() -> None:
    """No clear/truncate-each-run discipline is introduced (coupling, not
    clearing, keeps absence structural)."""
    block = _propagation_block(_read())
    assert not re.search(r"(clear|truncate)[^\n]*each run", block, re.IGNORECASE), (
        "propagation block introduces a clear/truncate-each-run discipline"
    )
    assert not re.search(r"each run[^\n]*(clear|truncate)", block, re.IGNORECASE), (
        "propagation block introduces a clear/truncate-each-run discipline"
    )
