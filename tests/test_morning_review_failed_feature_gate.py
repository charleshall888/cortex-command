"""Structural regression guard — morning-review §4 failed-feature create gate (#321 R11).

§4's failed-feature handler writes a `cortex/backlog/NNN-*.md` file via
``cortex-create-backlog-item``. On a non-cortex-backlog repo that violates the
``none`` no-writes guarantee. This pins the gate: the create must be preceded by
a ``cortex-read-backlog-backend`` resolution with a non-local skip arm, mirroring
the already-gated §6b auto-close. Discriminating: positive on the real §4 +
NEGATIVE CONTROL over the verbatim pre-edit step 6.

Mirrors ``tests/test_critical_review_gate_nonlocal_failsafe.py``.
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
WALKTHROUGH = (
    REPO_ROOT / "skills" / "morning-review" / "references" / "walkthrough.md"
)

BACKEND_READER = "cortex-read-backlog-backend"
CREATE_ANCHOR = "cortex-create-backlog-item"
SKIP_ADVISORY = "disabled for this repo"  # the non-local skip-arm witness
SECTION_HEADING = "## Section 4 — Failed Features"

# The verbatim pre-edit step 6 — the negative control: the create call with no
# preceding gate or skip arm. ``_gate_present`` MUST return False here.
PRE_EDIT_SECTION = (
    "6. If the user says yes (or any affirmative), invoke `/backlog-author compose` with a\n"
    "   context block derived from the failure summary, capture the returned body, then\n"
    "   call `cortex-create-backlog-item --title \"investigate <feature-slug>\" --status\n"
    "   should-have --type bug --body \"<returned-body>\"` to write the ticket.\n"
)


def _slice_section(text: str, heading: str) -> str:
    start = text.index(heading)
    rest = text.index("\n## ", start + len(heading))
    return text[start:rest]


def _gate_present(section: str) -> bool:
    """True only when §4 resolves the backend AND carries the non-local skip-arm
    advisory before the create call. The skip arm is the structural witness of
    conditionality that a bare create call lacks."""
    if BACKEND_READER not in section:
        return False
    if SKIP_ADVISORY not in section:  # the non-local stand-down
        return False
    if CREATE_ANCHOR not in section:
        return False
    return section.index(BACKEND_READER) < section.index(CREATE_ANCHOR)


def test_section4_gates_create_on_backend() -> None:
    text = WALKTHROUGH.read_text(encoding="utf-8")
    section = _slice_section(text, SECTION_HEADING)
    assert _gate_present(section), (
        "morning-review §4 must resolve `cortex-read-backlog-backend` and carry "
        "a non-local skip-arm advisory before `cortex-create-backlog-item`, "
        "mirroring the §6b auto-close gate."
    )


def test_negative_control_pre_edit_step6_is_ungated() -> None:
    # Discriminator: the verbatim pre-edit step 6 (bare create call) must NOT
    # pass — confirming the positive test fails on an ungated edit.
    assert not _gate_present(PRE_EDIT_SECTION)
