"""Escalation write + orchestrator read round-trip integration test.

Originally Task 19's R27 E2E test exercised three sub-cases:

(a) Two parallel ``overnight_start_run`` calls via the real stdio MCP
    transport (``cortex mcp-server`` subprocess).
(b) ``overnight_cancel`` reaching a real grandchild via the runner's
    in-handler tree-walker (also via the real stdio MCP transport).
(c) ``write_escalation`` + orchestrator read round-trip.

Sub-cases (a) and (b) were removed when ticket 146 R7 retired the
in-process ``cortex mcp-server`` subcommand (the deprecation stub now
exits non-zero rather than serving MCP). The new MCP runtime lives in
``plugins/cortex-overnight/server.py`` and its E2E coverage
is exercised by the plugin-side test surface.

Sub-case (c) survives because it does not depend on the MCP transport —
it round-trips an escalation record through ``write_escalation`` and
the orchestrator's read path. After ticket 111 the orchestrator-round
prompt no longer parses ``escalations.jsonl`` inline; it calls
``aggregate_round_context`` (the in-process aggregator) which returns
pre-computed ``unresolved`` and ``all_entries`` lists. This test now
exercises that aggregator path directly, preserving the original
through-line concern: an orchestrator reading escalations must surface
the new ``{session_id}-{feature}-{round}-q1`` ID format without crashing.
"""

from __future__ import annotations

import json
from pathlib import Path


def _fixture_session_id() -> str:
    """Return a deterministic session-id that satisfies SESSION_ID_RE."""
    return "overnight-2026-04-24-e2e"


def test_escalation_write_and_orchestrator_prompt_read_roundtrip(
    tmp_path,
) -> None:
    """``write_escalation`` + ``aggregate_round_context`` round-trip.

    Closes the through-line concern that an acceptance criterion
    (escalations migrate to per-session) can pass while the named hazard
    (orchestrator-prompt agent crashing on the new ``escalation_id``
    format under the new path) remains open. The test:

    1. Writes a real ``EscalationEntry`` via the production
       ``write_escalation`` API at ``session_dir/escalations.jsonl``.
    2. Asserts the on-disk record carries the new
       ``{session_id}-{feature}-{round}-q1`` ID format.
    3. Calls ``aggregate_round_context(session_dir, round_num)`` — the
       same call the orchestrator-round prompt now makes — and asserts
       the entry surfaces in both ``ctx["escalations"]["all_entries"]``
       and ``ctx["escalations"]["unresolved"]`` with the new ID format.
    """
    from cortex_command.overnight.deferral import (
        EscalationEntry,
        write_escalation,
    )
    from cortex_command.overnight.orchestrator_io import (
        aggregate_round_context,
    )
    from cortex_command.overnight.state import OvernightState, save_state

    session_id = _fixture_session_id()
    session_dir = tmp_path / "lifecycle" / "sessions" / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    # The aggregator re-raises FileNotFoundError if overnight-state.json
    # is missing (per spec R5), so seed a minimal valid state.
    save_state(
        OvernightState(features={}),
        state_path=session_dir / "overnight-state.json",
    )

    feature = "feat-x"
    round_num = 1
    entry = EscalationEntry.build(
        session_id=session_id,
        feature=feature,
        round=round_num,
        n=1,
        question="Is the spec ambiguous?",
        context="Implementing the foo() helper.",
    )
    write_escalation(entry, session_dir=session_dir)

    # On-disk shape: the escalation_id must be the new
    # {session_id}-{feature}-{round}-q1 format (R18 / Task 6).
    escalations_path = session_dir / "escalations.jsonl"
    raw = escalations_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(raw) == 1, f"expected 1 line, got {len(raw)}: {raw}"
    record = json.loads(raw[0])
    expected_id = f"{session_id}-{feature}-{round_num}-q1"
    assert record["escalation_id"] == expected_id, (
        f"expected escalation_id={expected_id!r}, got "
        f"{record['escalation_id']!r}"
    )
    assert record["session_id"] == session_id
    assert record["type"] == "escalation"

    # The orchestrator-round prompt now calls aggregate_round_context
    # instead of parsing escalations.jsonl inline. Exercise that exact
    # call and verify the entry surfaces with the new ID format.
    ctx = aggregate_round_context(session_dir, round_num)

    all_entries = ctx["escalations"]["all_entries"]
    assert isinstance(all_entries, list)
    assert len(all_entries) == 1, (
        f"expected 1 parsed entry, got {len(all_entries)}: {all_entries}"
    )
    parsed = all_entries[0]
    assert parsed.get("escalation_id") == expected_id, (
        f"parsed entry escalation_id={parsed.get('escalation_id')!r}; "
        f"expected {expected_id!r}"
    )

    unresolved = ctx["escalations"]["unresolved"]
    unresolved_ids = {e.get("escalation_id") for e in unresolved}
    assert expected_id in unresolved_ids, (
        f"new-format escalation_id {expected_id!r} did not surface as "
        f"unresolved: {unresolved_ids}"
    )


if __name__ == "__main__":  # pragma: no cover
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
