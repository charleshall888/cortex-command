"""Structural regression guard — discovery decompose §7 index-regen gate (#321 R8).

§7's slice has only two callable tokens, so a bare read-before-generate order is
NOT discriminating (a toothless edit that places the read first and still runs
the regen unconditionally satisfies it). The discriminator this test keys on is
the explicit non-cortex-backlog SKIP-ARM advisory — an ungated/unconditional §7
has none. Positive assertion on the real §7 + a NEGATIVE CONTROL over the
verbatim pre-edit §7 (the lone "Run cortex-generate-backlog-index" line).

Mirrors ``tests/test_critical_review_gate_nonlocal_failsafe.py`` /
``tests/test_decompose_rules.py``.
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
DECOMPOSE = REPO_ROOT / "skills" / "discovery" / "references" / "decompose.md"

BACKEND_READER = "cortex-read-backlog-backend"
REGEN_ANCHOR = "cortex-generate-backlog-index"
SKIP_ADVISORY = "no index to regenerate"  # the non-local skip-arm witness
SECTION_HEADING = "### 7. Update Index"

# The verbatim pre-edit §7 — the negative control. Two-token slice, unconditional
# regen, no gate, no skip arm. ``_gate_present`` MUST return False here.
PRE_EDIT_SECTION = (
    "### 7. Update Index\n\n"
    "Run `cortex-generate-backlog-index` to update the backlog index.\n"
)


def _slice_section(text: str, heading: str) -> str:
    start = text.index(heading)
    rest = text.index("\n### ", start + len(heading))
    return text[start:rest]


def _gate_present(section: str) -> bool:
    """True only when §7 resolves the backend AND carries the non-local
    skip-arm advisory, with the gate read before the regen call. The skip-arm
    advisory is the structural witness of conditionality — it is what a
    toothless two-token edit cannot produce."""
    if BACKEND_READER not in section:
        return False
    if SKIP_ADVISORY not in section:  # the non-local stand-down
        return False
    if REGEN_ANCHOR not in section:
        return False
    return section.index(BACKEND_READER) < section.index(REGEN_ANCHOR)


def test_decompose_section7_gates_index_regen() -> None:
    text = DECOMPOSE.read_text(encoding="utf-8")
    section = _slice_section(text, SECTION_HEADING)
    assert _gate_present(section), (
        "decompose.md §7 must resolve `cortex-read-backlog-backend` and carry "
        "a non-local skip-arm advisory; the index regen must no longer be "
        "unconditional."
    )


def test_negative_control_pre_edit_section_is_ungated() -> None:
    # Discriminator: the verbatim pre-edit §7 (unconditional regen) must NOT
    # pass — confirming the positive test fails on a toothless/ungated edit.
    assert not _gate_present(PRE_EDIT_SECTION)


def test_section7_resolves_independently_not_via_section5() -> None:
    # R8: §7 must re-resolve here, not reuse §5's create-scoped value (the
    # zero-piece branch never computes it). Pin the independent-resolution note.
    text = DECOMPOSE.read_text(encoding="utf-8")
    section = _slice_section(text, SECTION_HEADING)
    assert "zero-piece" in section, "§7 must justify independent re-resolution"
    assert "ADR-0016" in section
