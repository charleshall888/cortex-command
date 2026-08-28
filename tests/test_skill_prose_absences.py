"""Absence guards for skill prose — each keeps a completed removal removed.

Per ``docs/policies.md`` § "No tests on skill prose", a test may not assert
that a phrase *appears* in a SKILL.md or ``references/`` body, nor pin prose
layout (proximity, ordering, section placement): such a test passes only by
keeping the words where they are, so trimming becomes a failure and adding
prose becomes the cheapest way to stay green.

An **absence** assertion points the opposite way — it is satisfied by deleting
words — and is explicitly permitted as the enforcement arm of a trim already
made. This file collects the absence guards that survived the 2026-08-28
prose-test cull; the presence, proximity and ordering assertions they used to
ship alongside were deleted with their files.

Each guard names the removal it protects. A guard whose removal is no longer
meaningful should be deleted, not weakened.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent


def _read(rel: str) -> str:
    path = REPO_ROOT / rel
    assert path.is_file(), f"expected skill prose at {rel}; file is missing"
    return path.read_text(encoding="utf-8")


def test_specify_gate_carries_no_must_decide() -> None:
    """``MUST decide`` stays out of the refine complexity/value gate.

    The gate was rewritten to recommend rather than command; a MUST-escalation
    there re-forces the operator's hand (``docs/policies.md``, MUST-escalation
    policy).
    """
    assert "MUST decide" not in _read("skills/refine/references/specify.md")


def test_worktree_entry_omits_the_retired_auth_probe() -> None:
    """``verify-worktree-auth`` was retired from the auto-enter sequence.

    Re-introducing the probe restores a per-entry round-trip the sequence was
    trimmed to drop.
    """
    text = _read("skills/build/references/worktree-entry.md")
    assert "verify-worktree-auth" not in text


def test_implement_md_carries_no_sidecar_invocation() -> None:
    """``bash -s --`` stays out of implement.md.

    The sidecar invocation moved to worktree-entry.md; a second copy in
    implement.md is the duplicate that motivated the move.
    """
    assert "bash -s --" not in _read("skills/build/references/implement.md")


def test_implement_md_carries_no_daytime_pipeline_tokens() -> None:
    """The daytime autonomous pipeline (#246) stays removed.

    Guards against a sibling-branch revert re-introducing the retired
    dispatch path into implement.md.
    """
    text = _read("skills/build/references/implement.md")
    for token in ("cortex-daytime", "Daytime Dispatch"):
        assert token not in text, f"retired daytime token {token!r} is back"


def test_competing_plans_omits_the_retired_artifact_name() -> None:
    """``plan_comparison`` stays out of competing-plans.md.

    The comparison artifact was folded into plan-synthesizer.md; the old name
    naming a file that no longer exists sends the model looking for it.
    """
    assert "plan_comparison" not in _read(
        "skills/build/references/competing-plans.md"
    )


# Spelling-agnostic close pattern. The ticket-close operation has two live
# spellings — the console form (``cortex-update-item … --status complete``) and
# the module form (``python3 -m cortex_command.backlog.update_item …``). A
# guard matching only the console literal would let a module-form
# reintroduction slip back in green.
_CLOSE_PATTERN = re.compile(r"update[-_]item.*--status complete", re.IGNORECASE)


def test_morning_review_skill_md_does_not_close_tickets() -> None:
    """Ticket closure stays out of the morning-review SKILL.md body.

    Closure moved behind ``cortex-morning-review-close-tickets`` and runs only
    after a successful merge. A close call resident in the always-loaded
    SKILL.md body is reachable before the merge gate.
    """
    text = _read("skills/morning-review/SKILL.md")
    offenders = [ln for ln in text.splitlines() if _CLOSE_PATTERN.search(ln)]
    assert not offenders, (
        "morning-review SKILL.md must not carry a ticket-close call; found: "
        f"{offenders}"
    )


_DRIFTED_VOCAB_TOKENS = (
    "Integration shape",
    "Seam-level edges",
    "Why N pieces",
    "spec R4 GATE-2",
)


@pytest.mark.parametrize("token", _DRIFTED_VOCAB_TOKENS)
def test_discovery_skill_omits_drifted_architecture_vocabulary(
    token: str,
) -> None:
    """Headings the research template no longer emits stay out of discovery.

    ``references/research.md`` §6 emits only ``### Pieces`` and ``### How they
    connect``. Each token here names a heading or pointer that template
    dropped; a reference to one sends the model looking for a section that
    will never be written.
    """
    assert token not in _read("skills/discovery/SKILL.md")
