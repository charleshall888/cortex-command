"""``write_escalation_outcome`` — the orchestrator's writer for escalation outcomes.

``write_escalation`` only writes worker-raised ``type: "escalation"`` rows from
an ``EscalationEntry``; the orchestrator-round prompt used to call it with a
plain dict (``AttributeError``) and a file path (nested ``escalations.jsonl``),
and even a non-raising call could never produce the ``resolution``/``promoted``
rows ``aggregate_round_context`` reads. These tests pin the contract the prompt
now calls: the helper's rows close an escalation in ``unresolved`` and a
resolution lands in ``prior_resolutions_by_feature``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cortex_command.overnight.deferral import (
    EscalationEntry,
    write_escalation,
    write_escalation_outcome,
)
from cortex_command.overnight.orchestrator_context import aggregate_round_context
from cortex_command.overnight.state import OvernightState, save_state


def _session_with_one_escalation(session_dir: Path) -> str:
    save_state(
        OvernightState(session_id="sess-1", plan_ref="cortex/lifecycle/x/plan.md"),
        session_dir / "overnight-state.json",
    )
    entry = EscalationEntry.build(
        session_id="sess-1",
        feature="feat-a",
        round=1,
        n=1,
        question="Which auth provider?",
        context="worker blocked",
    )
    write_escalation(entry, session_dir)
    return entry.escalation_id


def test_resolution_closes_unresolved_and_buckets_prior(tmp_path: Path) -> None:
    esc_id = _session_with_one_escalation(tmp_path)
    assert aggregate_round_context(tmp_path, 1)["escalations"]["unresolved"]

    write_escalation_outcome(
        tmp_path, kind="resolution", escalation_id=esc_id, feature="feat-a",
        answer="Use OAuth2 per spec §auth.",
    )

    ctx = aggregate_round_context(tmp_path, 2)["escalations"]
    assert ctx["unresolved"] == []
    prior = ctx["prior_resolutions_by_feature"]["feat-a"]
    assert len(prior) == 1
    assert prior[0]["type"] == "resolution"
    assert prior[0]["answer"] == "Use OAuth2 per spec §auth."
    assert prior[0]["resolved_by"] == "orchestrator"
    assert prior[0]["escalation_id"] == esc_id


def test_promotion_closes_unresolved_without_becoming_prior(tmp_path: Path) -> None:
    esc_id = _session_with_one_escalation(tmp_path)

    write_escalation_outcome(
        tmp_path, kind="promoted", escalation_id=esc_id, feature="feat-a",
    )

    ctx = aggregate_round_context(tmp_path, 2)["escalations"]
    assert ctx["unresolved"] == []
    assert "feat-a" not in ctx["prior_resolutions_by_feature"]
    rows = [json.loads(l) for l in (tmp_path / "escalations.jsonl").read_text().splitlines()]
    assert rows[-1]["type"] == "promoted"
    assert rows[-1]["promoted_by"] == "orchestrator"
    assert "ts" in rows[-1]


def test_rejects_unknown_kind_and_answerless_resolution(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        write_escalation_outcome(tmp_path, kind="closed", escalation_id="x", feature="f")
    with pytest.raises(ValueError):
        write_escalation_outcome(tmp_path, kind="resolution", escalation_id="x", feature="f")
    assert not (tmp_path / "escalations.jsonl").exists()
