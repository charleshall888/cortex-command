"""Escalation write + orchestrator-prompt read round-trip integration test.

Originally Task 19's R27 E2E test exercised three sub-cases:

(a) Two parallel ``overnight_start_run`` calls via the real stdio MCP
    transport (``cortex mcp-server`` subprocess).
(b) ``overnight_cancel`` reaching a real grandchild via the runner's
    in-handler tree-walker (also via the real stdio MCP transport).
(c) ``write_escalation`` + orchestrator-prompt render round-trip.

Sub-cases (a) and (b) were removed when ticket 146 R7 retired the
in-process ``cortex mcp-server`` subcommand (the deprecation stub now
exits non-zero rather than serving MCP). The new MCP runtime lives in
``plugins/cortex-overnight-integration/server.py`` and its E2E coverage
is exercised by the plugin-side test surface.

Sub-case (c) survives because it does not depend on the MCP transport —
it round-trips an escalation record through ``write_escalation`` and the
orchestrator-prompt's Step 0b read path. It closes the through-line
concern from Task 19 critical review: that an acceptance criterion
(escalations migrate to per-session) can pass while the named hazard
(orchestrator-prompt agent crashing on the new ``escalation_id`` format)
remains open.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional


def _fixture_session_id() -> str:
    """Return a deterministic session-id that satisfies SESSION_ID_RE."""
    return "overnight-2026-04-24-e2e"


def test_escalation_write_and_orchestrator_prompt_read_roundtrip(
    tmp_path,
) -> None:
    """``write_escalation`` + orchestrator-prompt render round-trip.

    Closes the through-line concern that an acceptance criterion
    (escalations migrate to per-session) can pass while the named hazard
    (orchestrator-prompt agent crashing on the new ``escalation_id``
    format under the new path) remains open. The test:

    1. Writes a real ``EscalationEntry`` via the production
       ``write_escalation`` API at ``session_dir/escalations.jsonl``.
    2. Asserts the on-disk record carries the new
       ``{session_id}-{feature}-{round}-q1`` ID format.
    3. Renders the orchestrator-round prompt via ``fill_prompt()`` with
       the fixture ``session_dir`` so ``{session_dir}`` is substituted.
    4. Extracts the Step 0b Python block (the one that actually reads
       ``escalations.jsonl`` into ``entries``) and exec's it against a
       fresh globals dict with synthetic stand-ins for the
       ``orchestrator_io`` symbols imported at the top of the block.
    5. Asserts the parsed entry's ``escalation_id`` matches the new
       format and that the unresolved-set computation surfaces it as
       unresolved.
    """
    from cortex_command.overnight.deferral import (
        EscalationEntry,
        write_escalation,
    )
    from cortex_command.overnight.fill_prompt import fill_prompt

    session_id = _fixture_session_id()
    session_dir = tmp_path / "lifecycle" / "sessions" / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

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

    # Render the orchestrator-round prompt with the fixture session_dir.
    plan_path = session_dir / "overnight-plan.md"
    state_path = session_dir / "overnight-state.json"
    events_path = session_dir / "overnight-events.log"
    rendered = fill_prompt(
        round_number=round_num,
        state_path=state_path,
        plan_path=plan_path,
        events_path=events_path,
        session_dir=session_dir,
        tier="simple",
    )

    # Belt-and-suspenders: substitution actually happened.
    assert "{session_dir}" not in rendered, (
        "{session_dir} token survived fill_prompt — substitution incomplete"
    )
    assert str(escalations_path) in rendered, (
        f"rendered prompt does not contain expected substituted "
        f"escalations path {escalations_path!s}"
    )

    # Extract the Step 0b Python block — the one that reads
    # ``escalations.jsonl`` and computes ``entries`` / ``unresolved_ids``.
    blocks = re.findall(
        r"^```python\n(.*?)\n^```",
        rendered,
        flags=re.DOTALL | re.MULTILINE,
    )
    assert blocks, "no python code blocks in rendered prompt"

    # The first block is the unresolved-set computation (per the prompt
    # template); locate it explicitly via its escalations_path assignment.
    target_block: Optional[str] = None
    for block in blocks:
        if "escalations_path" in block and "unresolved_ids" in block:
            target_block = block
            break
    assert target_block is not None, (
        "could not locate the Step 0b unresolved-set computation block "
        "in the rendered prompt"
    )

    # Build a fresh globals dict with synthetic stand-ins for the
    # orchestrator_io functions imported at the top of the block. They
    # are not invoked by Step 0b (only by Step 0d's resolution path), so
    # the stand-ins are plain identity-style placeholders that satisfy
    # the import.
    def _save_state(*args, **kwargs):  # pragma: no cover — unused at exec
        return None

    def _update_feature_status(*args, **kwargs):  # pragma: no cover
        return None

    def _write_escalation(*args, **kwargs):  # pragma: no cover
        return None

    # The block's ``from cortex_command.overnight.orchestrator_io import ...``
    # statement will run at exec time and pull the real symbols. That is
    # acceptable for the read-path test — the block does not invoke them.
    # We exec against a fresh globals dict so any leak from this test
    # process's imports is irrelevant to the contract check.
    fresh_globals: dict = {"__builtins__": __builtins__}

    exec(  # noqa: S102 — controlled-input exec of templated prompt block
        target_block, fresh_globals
    )

    # The block populates ``entries`` (parsed JSON dicts) and
    # ``unresolved_ids`` (set of escalation_ids without a
    # resolution/promoted entry). Verify both observable side effects
    # carry the new {session_id}-{feature}-{round}-q1 format.
    entries = fresh_globals.get("entries")
    assert isinstance(entries, list), (
        f"block did not populate `entries` as a list: "
        f"{type(entries).__name__}"
    )
    assert len(entries) == 1, (
        f"expected 1 parsed entry, got {len(entries)}: {entries}"
    )
    parsed = entries[0]
    assert isinstance(parsed, dict)
    assert parsed.get("escalation_id") == expected_id, (
        f"parsed entry escalation_id={parsed.get('escalation_id')!r}; "
        f"expected {expected_id!r}"
    )

    unresolved_ids = fresh_globals.get("unresolved_ids")
    assert isinstance(unresolved_ids, set), (
        f"block did not populate `unresolved_ids` as a set: "
        f"{type(unresolved_ids).__name__}"
    )
    assert expected_id in unresolved_ids, (
        f"new-format escalation_id {expected_id!r} did not surface as "
        f"unresolved: {unresolved_ids}"
    )


if __name__ == "__main__":  # pragma: no cover
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
