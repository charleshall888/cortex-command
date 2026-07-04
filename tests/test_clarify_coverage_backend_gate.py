"""Structural regression guard — discovery clarify §3 backend gate (#321 R7).

Pins the DOCUMENTED two-arm gate, not runtime behavior: §3 must resolve the
backend via ``cortex-read-backlog-backend`` and stand down on a non-cortex-backlog
backend BEFORE the local ``cortex/backlog`` coverage scan. Discriminating by
construction — a positive assertion on the real §3 plus a NEGATIVE CONTROL over
the verbatim pre-edit §3, so a toothless/ungated edit fails the test rather than
passing green-by-construction.

Mirrors the structural-over-markdown idiom in
``tests/test_critical_review_gate_nonlocal_failsafe.py``.
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
CLARIFY = REPO_ROOT / "skills" / "discovery" / "references" / "clarify.md"

BACKEND_READER = "cortex-read-backlog-backend"
SCAN_ANCHOR = "cortex/backlog/[0-9]*-*.md"
SECTION_HEADING = "### 3. Check Existing Backlog Coverage"

# The verbatim pre-edit §3 — the negative control. ``_gate_present`` MUST return
# False here; that is what proves the positive assertion would fail on an
# ungated/toothless §3 (the gate token and skip arm are simply absent).
PRE_EDIT_SECTION = (
    "### 3. Check Existing Backlog Coverage\n\n"
    "Scan `cortex/backlog/[0-9]*-*.md` titles, tags, and descriptions for "
    "overlap with the topic. If a backlog item already covers this topic "
    "substantially, surface it to the user and ask whether to proceed with "
    "discovery or work from the existing ticket.\n"
)


def _slice_section(text: str, heading: str) -> str:
    start = text.index(heading)
    rest = text.index("\n### ", start + len(heading))
    return text[start:rest]


def _gate_present(section: str) -> bool:
    """True only for a real §3 gate: the backend reader AND a non-local
    skip-arm advisory, positioned before the backlog-scan glob. The skip-arm
    advisory is the structural witness of conditionality — an ungated scan
    has none, so token co-occurrence alone cannot pass this."""
    if BACKEND_READER not in section:
        return False
    if "disabled for this repo" not in section:  # the non-local skip arm
        return False
    if SCAN_ANCHOR not in section:
        return False
    return section.index(BACKEND_READER) < section.index(SCAN_ANCHOR)


def test_clarify_section3_gates_scan_on_backend() -> None:
    text = CLARIFY.read_text(encoding="utf-8")
    section = _slice_section(text, SECTION_HEADING)
    assert _gate_present(section), (
        "clarify.md §3 must resolve `cortex-read-backlog-backend` and carry a "
        "non-local skip-arm advisory positioned before the `cortex/backlog` "
        "scan glob. Restore the two-arm gate ahead of the scan instruction."
    )


def test_negative_control_pre_edit_section_is_ungated() -> None:
    # Discriminator: the verbatim pre-edit §3 must NOT pass — confirming the
    # positive test above would fail on an ungated/toothless edit.
    assert not _gate_present(PRE_EDIT_SECTION)


def test_divergence_note_present() -> None:
    text = CLARIFY.read_text(encoding="utf-8")
    section = _slice_section(text, SECTION_HEADING)
    assert "two arms" in section.lower(), "missing the two-arm divergence note"
