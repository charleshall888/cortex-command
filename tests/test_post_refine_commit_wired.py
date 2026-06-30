"""Wiring + content tests for the post-refine-commit reference.

Verifies two things per R5 acceptance:

1. ``skills/lifecycle/references/refine-delegation.md`` references
   ``post-refine-commit`` within 50 lines after both the
   ``phase_transition specify→plan`` block and the ``lifecycle_cancelled``
   mention. The refine-delegation.md file is the extracted home of the
   delegation steps (Task 1 progressive-disclosure move); the line-distance
   bound protects against future edits that move the wiring sentence to an
   unrelated section.  A plain ordered-substring DOTALL regex would not.

   Additionally, ``skills/lifecycle/SKILL.md`` must reference
   ``post-refine-commit`` (at minimum via the Reference-path propagation
   manifest entry and the Reference Files section) to ensure the
   extract-and-manifest pattern is wired end-to-end.

2. ``skills/lifecycle/references/post-refine-commit.md`` contains the required
   content tokens after the #331 Phase 2 collapse: the
   ``cortex-lifecycle-stage-artifacts`` staging-verb invocation (the Staging +
   No-Op Short-Circuit sections collapsed into it, Req 14),
   ``cortex-read-commit-artifacts``, ``/cortex-core:commit``, a halt clause,
   and a cancel-path keyword (the kept Commit-Subject prose). The
   since-last-commit qualifier was dropped — the bottom-up scan / no-op
   narration moved into the verb, which exposes no equivalent prose token. This
   keeps the wiring test a durable guard so future regressions in
   ``post-refine-commit.md``'s substantive content cause CI failure.

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


def test_refine_delegation_wires_post_refine_commit_within_distance() -> None:
    """refine-delegation.md references post-refine-commit near phase_transition/cancelled.

    After the Task 1 progressive-disclosure extraction, the delegation steps
    (including the post-refine-commit trigger) live in refine-delegation.md,
    not in SKILL.md directly. The distance check moves to that file.
    """
    repo_root = _repo_root()
    delegation = (
        repo_root / "skills" / "lifecycle" / "references" / "refine-delegation.md"
    )
    assert delegation.exists(), (
        f"refine-delegation.md missing at {delegation} — "
        "Task 1 progressive-disclosure extraction may not have run"
    )
    lines = delegation.read_text(encoding="utf-8").splitlines()

    phase_transition_lines = _line_indices(
        lines, ["phase_transition", "specify", "plan"]
    )
    cancelled_lines = _line_indices(lines, ["lifecycle_cancelled"])
    post_refine_lines = _line_indices(lines, ["post-refine-commit"])

    assert phase_transition_lines, (
        "refine-delegation.md must contain a phase_transition specify→plan line"
    )
    assert cancelled_lines, (
        "refine-delegation.md must reference lifecycle_cancelled "
        "(post-refine-commit handles both approval and cancel paths)"
    )
    assert post_refine_lines, (
        "refine-delegation.md must reference post-refine-commit (Step 6 of refine delegation)"
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


def test_skill_md_references_post_refine_commit() -> None:
    """SKILL.md must reference post-refine-commit (manifest entry + Reference Files).

    After the Task 1 extraction, SKILL.md references post-refine-commit via:
    - The Reference-path propagation manifest (body-resolved path for
      refine-delegation.md consumers).
    - The Reference Files section (load-on-demand index).
    The test requires at least 2 occurrences to ensure both sites survive.
    """
    repo_root = _repo_root()
    skill = repo_root / "skills" / "lifecycle" / "SKILL.md"
    text = skill.read_text(encoding="utf-8")
    count = text.count("post-refine-commit")
    assert count >= 2, (
        f"SKILL.md must reference post-refine-commit at least twice (manifest + "
        f"Reference Files), found {count}"
    )


def test_post_refine_commit_contains_required_tokens() -> None:
    repo_root = _repo_root()
    ref = repo_root / "skills" / "lifecycle" / "references" / "post-refine-commit.md"
    text = ref.read_text(encoding="utf-8")
    text_lower = text.lower()

    # Req 14: the Staging + No-Op Short-Circuit sections collapsed into the verb.
    assert "cortex-lifecycle-stage-artifacts" in text, (
        "post-refine-commit.md must invoke the 'cortex-lifecycle-stage-artifacts' "
        "staging verb (Req 14) — the Staging + No-Op Short-Circuit sections "
        "collapsed into it"
    )
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
    # NOTE: the since-last-commit qualifier was dropped (#331 Phase 2) — the
    # bottom-up scan / no-op narration moved into the verb, which exposes no
    # equivalent prose token.
    cancel_tokens = ("cancelled", "cancel")
    assert any(t in text_lower for t in cancel_tokens), (
        f"post-refine-commit.md must reference the cancel path "
        f"(one of {cancel_tokens})"
    )
