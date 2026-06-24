"""Structural regression guard — lifecycle complete.md Step 10 index-sync gate (#321 R12).

Step 9's write-back is already backend-gated, but Step 10's index regen ran
unconditionally "regardless of whether [write-back] succeeded, failed, or was
skipped". This pins the gate: the regen must be preceded by a
``cortex-read-backlog-backend`` resolution with a non-local skip arm.
Discriminating: positive on the real Step 10 + NEGATIVE CONTROL over the
verbatim pre-edit (unconditional) Step 10 intro.

Mirrors ``tests/test_critical_review_gate_nonlocal_failsafe.py``.
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
COMPLETE = REPO_ROOT / "skills" / "lifecycle" / "references" / "complete.md"

BACKEND_READER = "cortex-read-backlog-backend"
REGEN_ANCHOR = "cortex-generate-backlog-index"
SKIP_ADVISORY = "disabled for this repo"  # the non-local skip-arm witness
SECTION_HEADING = "### Step 10 — Backlog Index Sync"

# The verbatim pre-edit Step 10 intro — the negative control: the regen runs
# unconditionally with no gate or skip arm. ``_gate_present`` MUST return False.
PRE_EDIT_SECTION = (
    "### Step 10 — Backlog Index Sync\n\n"
    "After the `cortex-update-item` call (regardless of whether it succeeded, "
    "failed, or was skipped), regenerate the backlog index using this fallback "
    "chain:\n\n"
    "   - Else run `command -v cortex-generate-backlog-index` — if found on "
    "PATH, run `cortex-generate-backlog-index`.\n"
)


def _slice_section(text: str, heading: str) -> str:
    start = text.index(heading)
    rest = text.index("\n### ", start + len(heading))
    return text[start:rest]


def _gate_present(section: str) -> bool:
    """True only when Step 10 resolves the backend AND carries the non-local
    skip-arm advisory before the regen call. The skip arm is the structural
    witness of conditionality an unconditional regen lacks."""
    if BACKEND_READER not in section:
        return False
    if SKIP_ADVISORY not in section:  # the non-local stand-down
        return False
    if REGEN_ANCHOR not in section:
        return False
    return section.index(BACKEND_READER) < section.index(REGEN_ANCHOR)


def test_step10_gates_index_regen_on_backend() -> None:
    text = COMPLETE.read_text(encoding="utf-8")
    section = _slice_section(text, SECTION_HEADING)
    assert _gate_present(section), (
        "complete.md Step 10 must resolve `cortex-read-backlog-backend` and "
        "carry a non-local skip-arm advisory before the index regen; the regen "
        "must no longer run unconditionally."
    )


def test_negative_control_pre_edit_section_is_ungated() -> None:
    # Discriminator: the verbatim pre-edit (unconditional) Step 10 must NOT
    # pass — confirming the positive test fails on an ungated edit.
    assert not _gate_present(PRE_EDIT_SECTION)
