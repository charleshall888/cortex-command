"""Wiring + content tests for the post-refine-commit reference.

Verifies two things per R5 acceptance:

1. ``skills/lifecycle/SKILL.md`` references ``post-refine-commit`` within 50
   lines after both the ``phase_transition specify→plan`` block and the
   ``lifecycle_cancelled`` mention in Step 3 §4. The line-distance bound is
   what protects against future edits that move the wiring sentence to an
   unrelated section — a plain ordered-substring DOTALL regex would not.

2. ``skills/lifecycle/references/post-refine-commit.md`` contains the five
   required content tokens that mirror Task 4's verification greps:
   ``cortex-read-commit-artifacts``, ``/cortex-core:commit``, a halt clause,
   a since-last-commit qualifier, and a cancel-path keyword. This converts
   the wiring test from a bare ``.exists()`` check into a durable guard so
   future regressions in ``post-refine-commit.md``'s substantive content
   cause CI failure.

Per R5: full end-to-end refine→commit testing is interactive/session-
dependent (the refine spec-approval surface requires user input), so the
binary-checkable surface for the wiring change is this file plus the
``/cortex-core:commit`` skill's own tests (which exercise the leaf commit
operation only, not the post-refine caller contract).
"""

from __future__ import annotations

import pathlib


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[1]


def _line_indices(lines: list[str], needles: list[str]) -> list[int]:
    """Return indices of lines that contain ALL of ``needles`` (substring match)."""
    return [
        i
        for i, line in enumerate(lines)
        if all(needle in line for needle in needles)
    ]


def test_post_refine_commit_reference_exists() -> None:
    repo_root = _repo_root()
    ref = repo_root / "skills" / "lifecycle" / "references" / "post-refine-commit.md"
    assert ref.exists(), f"post-refine-commit.md missing at {ref}"
    plugin_ref = (
        repo_root
        / "plugins"
        / "cortex-core"
        / "skills"
        / "lifecycle"
        / "references"
        / "post-refine-commit.md"
    )
    assert plugin_ref.exists(), f"plugin-tree mirror missing at {plugin_ref}"


def test_skill_md_wires_post_refine_commit_within_distance() -> None:
    repo_root = _repo_root()
    skill = repo_root / "skills" / "lifecycle" / "SKILL.md"
    lines = skill.read_text(encoding="utf-8").splitlines()

    phase_transition_lines = _line_indices(
        lines, ["phase_transition", "specify", "plan"]
    )
    cancelled_lines = _line_indices(lines, ["lifecycle_cancelled"])
    post_refine_lines = _line_indices(lines, ["post-refine-commit"])

    assert phase_transition_lines, (
        "SKILL.md Step 3 §4 must contain a phase_transition specify→plan line"
    )
    assert cancelled_lines, (
        "SKILL.md Step 3 §4 must reference lifecycle_cancelled "
        "(post-refine-commit handles both approval and cancel paths)"
    )
    assert post_refine_lines, (
        "SKILL.md must reference post-refine-commit (Step 6 of refine delegation)"
    )

    def within_50_lines_after(anchor: int) -> bool:
        return any(p >= anchor and p - anchor <= 50 for p in post_refine_lines)

    assert within_50_lines_after(min(phase_transition_lines)), (
        "post-refine-commit reference must appear within 50 lines after the "
        f"phase_transition specify→plan block (anchor lines {phase_transition_lines}, "
        f"post-refine-commit lines {post_refine_lines})"
    )
    assert within_50_lines_after(min(cancelled_lines)), (
        "post-refine-commit reference must appear within 50 lines after the "
        f"lifecycle_cancelled mention (anchor lines {cancelled_lines}, "
        f"post-refine-commit lines {post_refine_lines})"
    )


def test_post_refine_commit_contains_required_tokens() -> None:
    repo_root = _repo_root()
    ref = repo_root / "skills" / "lifecycle" / "references" / "post-refine-commit.md"
    text = ref.read_text(encoding="utf-8")
    text_lower = text.lower()

    assert "cortex-read-commit-artifacts" in text, (
        "post-refine-commit.md must invoke the cortex-read-commit-artifacts binstub"
    )
    assert "/cortex-core:commit" in text, (
        "post-refine-commit.md must invoke /cortex-core:commit"
    )
    halt_tokens = ("halt", "do not auto-advance", "do not advance")
    assert any(t in text_lower for t in halt_tokens), (
        f"post-refine-commit.md must encode a halt clause (one of {halt_tokens})"
    )
    since_tokens = ("since the last commit", "since last commit", "most recent")
    assert any(t in text_lower for t in since_tokens), (
        f"post-refine-commit.md must encode the since-last-commit qualifier "
        f"(one of {since_tokens})"
    )
    cancel_tokens = ("cancelled", "cancel")
    assert any(t in text_lower for t in cancel_tokens), (
        f"post-refine-commit.md must reference the cancel path "
        f"(one of {cancel_tokens})"
    )
