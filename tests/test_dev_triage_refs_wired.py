"""Wiring + content guard for the dev-router lazy-reference extraction (#343).

Pins the *static* wiring of the two consumer-keyed references extracted from
``skills/dev/SKILL.md`` — ``references/triage-rendering.md`` (Step 3c, Branch 1)
and ``references/criticality-heuristics.md`` (Step 2, Branch 5 + Step-4 decline)
— so they cannot silently regress after the one-shot grep acceptances vanish.
Follows the ``tests/test_competing_plans_wired.py`` precedent (file+mirror
existence, single-occurrence ${CLAUDE_SKILL_DIR} pointer, directive distinct
from the stub heading).

The load-bearing assertion is the body-absence *negative control*: a FULL-SPAN
token set (both block sub-headings plus distinctive body lines, not just the
one-shot sentinels) must be absent from the body. A partial re-inline that kept
the pointers — or a copy-not-move that left content resident — fails here even
though the stub pointers still name their targets.

Deliberately OUT OF SCOPE (so this gate is honest rather than self-sealing): the
*runtime* missed-read / read-but-not-applied failure — whether the model
actually follows the imperative pointer and applies the relocated logic at run
time — is untestable in a static check and is not asserted.
"""

from __future__ import annotations

import pathlib

_REFS = ("triage-rendering.md", "criticality-heuristics.md")

# Full-span negative-control tokens: block sub-headings + distinctive body
# lines spanning each moved block, not just the one-shot acceptance sentinels.
_MOVED_TOKENS = (
    # criticality-heuristics block
    "Payments, billing, financial data",
    "### Heuristic Signals",
    "### Forming the Suggestion",
    "No elevated signals",
    # triage-rendering block
    "Flat Ready List",
    "Per-epic workflow recommendation",
    "Suppress children",
    "Suppress epics",
    "No active child tickets found",
)

# The stub headings that must survive as anchors (content moved, headings kept).
_STUB_HEADINGS = (
    "## Step 2: Criticality Pre-Assessment",
    "### 3c. Present Ready Items with Workflow Recommendations",
)


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[1]


def _skill_path() -> pathlib.Path:
    return _repo_root() / "skills" / "dev" / "SKILL.md"


def _skill_lines() -> list[str]:
    return _skill_path().read_text(encoding="utf-8").splitlines()


def test_both_references_and_mirrors_exist() -> None:
    root = _repo_root()
    for ref in _REFS:
        canonical = root / "skills" / "dev" / "references" / ref
        assert canonical.exists(), f"canonical reference missing at {canonical}"
        mirror = (
            root / "plugins" / "cortex-core" / "skills" / "dev" / "references" / ref
        )
        assert mirror.exists(), f"plugin-tree mirror missing at {mirror}"


def test_body_pointers_use_skill_dir_form_and_occur_once() -> None:
    """Each body Read pointer resolves via ${CLAUDE_SKILL_DIR} and occurs once."""
    text = _skill_path().read_text(encoding="utf-8")
    for ref in _REFS:
        token = "${CLAUDE_SKILL_DIR}/references/" + ref
        count = text.count(token)
        assert count == 1, (
            f"body must contain exactly one own-dir ${{CLAUDE_SKILL_DIR}} pointer to "
            f"{ref} (found {count}); a bare-relative path or a second occurrence "
            "(e.g. a propagation manifest) breaks SP002 / single-occurrence wiring"
        )


def test_read_directives_are_distinct_imperative_lines() -> None:
    """The pointer line is a distinct imperative Read line, not the stub heading."""
    lines = _skill_lines()
    for ref in _REFS:
        token = "${CLAUDE_SKILL_DIR}/references/" + ref
        directive = [ln for ln in lines if token in ln]
        assert len(directive) == 1, f"expected one pointer line for {ref}"
        line = directive[0]
        assert "Read" in line, (
            f"the {ref} pointer must be an imperative Read directive, not a bare link"
        )
        assert line.strip() not in _STUB_HEADINGS, (
            f"the {ref} pointer line must be distinct from a stub heading — an alias "
            "would let a revert drop the routing wire while the heading survives"
        )


def test_stub_headings_survive() -> None:
    lines = {ln.strip() for ln in _skill_lines()}
    for heading in _STUB_HEADINGS:
        assert heading in lines, f"stub heading must be kept as an anchor: {heading}"


def test_moved_content_absent_from_body_negative_control() -> None:
    """Full-span negative control: no moved token remains resident in the body.

    This is the assertion that actually catches a re-inline, a partial move, or a
    copy-not-move. Keying on the full-span token set (sub-headings + distinctive
    body lines) rather than the one-shot sentinels means leaving, e.g.,
    ``### Forming the Suggestion`` or Block-2's body resident fails here.
    """
    text = _skill_path().read_text(encoding="utf-8")
    resident = [tok for tok in _MOVED_TOKENS if tok in text]
    assert not resident, (
        "moved content must be ABSENT from skills/dev/SKILL.md (move, not copy); "
        f"these tokens are still resident: {resident}"
    )
