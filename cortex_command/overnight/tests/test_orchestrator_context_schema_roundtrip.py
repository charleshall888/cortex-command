"""Round-trip schema-lockstep test for ``aggregate_round_context`` (Task 8 / R4).

Guards the lockstep between the inline literal ``schema_version`` set at
the dict-construction site in
``cortex_command.overnight.orchestrator_context.aggregate_round_context``
and the module-level ``_EXPECTED_SCHEMA_VERSION`` constant. Any future
drift between the two — e.g., bumping the literal without updating the
constant (or vice versa) — must surface in CI as a ``RuntimeError``
before it can land on main.

Also pins the post-Task-6 escalations sub-dict key set to exactly
``{"unresolved", "prior_resolutions_by_feature"}`` and asserts the
pre-Task-6 ``all_entries`` key has been removed.
"""

from __future__ import annotations

import json
from pathlib import Path

from cortex_command.overnight.orchestrator_context import aggregate_round_context
from cortex_command.overnight.state import OvernightState, save_state


def _seed_session(session_dir: Path) -> None:
    """Seed a minimal session dir: state file + one resolution + one promotion."""
    session_dir.mkdir(parents=True, exist_ok=True)

    save_state(
        OvernightState(session_id="overnight-2026-05-11-roundtrip", plan_ref="lifecycle/x/plan.md"),
        state_path=session_dir / "overnight-state.json",
    )

    resolution_entry = {
        "type": "resolution",
        "escalation_id": "overnight-2026-05-11-roundtrip-feat-a-1-q1",
        "feature": "feat-a",
        "answer": "resolved",
    }
    promotion_entry = {
        "type": "promotion",
        "escalation_id": "overnight-2026-05-11-roundtrip-feat-a-1-q2",
        "feature": "feat-a",
        "reason": "promoted to user",
    }

    escalations_path = session_dir / "escalations.jsonl"
    escalations_path.write_text(
        "\n".join([json.dumps(resolution_entry), json.dumps(promotion_entry)]) + "\n",
        encoding="utf-8",
    )


def test_aggregate_round_context_schema_lockstep_roundtrip(tmp_path: Path) -> None:
    """Call aggregate_round_context against a seeded session and assert:

    (a) the call does not raise ``RuntimeError("schema_version drift")``;
    (b) ``escalations`` contains exactly the keys
        ``{"unresolved", "prior_resolutions_by_feature"}``;
    (c) ``all_entries`` is absent from the escalations sub-dict.
    """
    session_dir = tmp_path / "lifecycle" / "sessions" / "overnight-2026-05-11-roundtrip"
    _seed_session(session_dir)

    # (a) Call must not raise — schema_version literal and
    # _EXPECTED_SCHEMA_VERSION must agree.
    result = aggregate_round_context(session_dir, round_number=1)

    # (b) Exact key-set on the escalations sub-dict.
    assert set(result["escalations"].keys()) == {
        "unresolved",
        "prior_resolutions_by_feature",
    }, (
        "escalations sub-dict key set drift detected — Task 6 / R4 pinned "
        f"the shape to {{'unresolved', 'prior_resolutions_by_feature'}}. "
        f"Got: {sorted(result['escalations'].keys())}"
    )

    # (c) Pre-Task-6 'all_entries' key must be absent.
    assert "all_entries" not in result["escalations"], (
        "Pre-Task-6 'all_entries' key resurfaced in the escalations sub-dict — "
        "Task 6 / R4 removed this key and replaced it with "
        "'prior_resolutions_by_feature'. Bump _EXPECTED_SCHEMA_VERSION and "
        "update this assertion if the shape is intentionally changing."
    )
