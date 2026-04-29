"""Round-startup state aggregator for the overnight orchestrator.

Consolidates the four scattered file reads that the orchestrator-round prompt
performs at round startup (overnight-state.json, overnight-strategy.json,
escalations.jsonl, session-plan.md) into a single in-process function call.

This module is read-only with respect to all state files, lock-free per
requirements/pipeline.md:127,134, and performs no in-process caching (each
round-spawn gets a fresh read).
"""

import json
import sys
from dataclasses import asdict
from pathlib import Path

from cortex_command.overnight.state import load_state
from cortex_command.overnight.strategy import load_strategy

_EXPECTED_SCHEMA_VERSION = 1


def aggregate_round_context(session_dir: Path, round_number: int) -> dict:
    """Aggregate round-startup state from session-dir files into a single dict.

    Reads overnight-state.json, overnight-strategy.json, escalations.jsonl,
    and session-plan.md from ``session_dir`` and returns a nested dict keyed
    by source with a top-level ``schema_version`` field.

    Args:
        session_dir: Path to the session directory containing the round-startup
            state files (e.g. ``lifecycle/sessions/<session_id>/``).
        round_number: Current round number. Included for schema-version
            tracing; not used for filtering — callers retain round-filter
            logic.

    Returns:
        dict with keys ``schema_version`` (int), ``state`` (dict from
        asdict(OvernightState)), ``strategy`` (dict from
        asdict(OvernightStrategy)), ``escalations`` (dict with
        ``unresolved`` and ``all_entries`` lists), and
        ``session_plan_text`` (str).

    Raises:
        FileNotFoundError: If ``overnight-state.json`` is absent.
        RuntimeError: If the assembled dict's ``schema_version`` does not
            match ``_EXPECTED_SCHEMA_VERSION`` (schema-drift guard).
    """
    # --- state ---------------------------------------------------------------
    state_path = session_dir / "overnight-state.json"
    # load_state raises FileNotFoundError if missing; propagate per spec R5.
    state_obj = load_state(state_path)

    # --- strategy ------------------------------------------------------------
    strategy_path = session_dir / "overnight-strategy.json"
    # load_strategy returns OvernightStrategy() defaults on missing/invalid.
    strategy_obj = load_strategy(strategy_path)

    # --- escalations ---------------------------------------------------------
    escalations_path = session_dir / "escalations.jsonl"
    all_entries: list[dict] = []
    if escalations_path.exists():
        with escalations_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    all_entries.append(json.loads(line))
                except json.JSONDecodeError:
                    print(
                        f"WARNING: Skipping malformed {escalations_path} line: {line[:80]}",
                        file=sys.stderr,
                    )
                    continue

    # Compute unresolved: escalation entries whose escalation_id has no
    # matching resolution or promoted entry — mirrors orchestrator-round.md:52-61.
    escalation_ids = {
        e["escalation_id"]
        for e in all_entries
        if e.get("type") == "escalation" and "escalation_id" in e
    }
    resolved_ids = {
        e["escalation_id"]
        for e in all_entries
        if e.get("type") in ("resolution", "promoted") and "escalation_id" in e
    }
    unresolved_ids = escalation_ids - resolved_ids
    unresolved = [
        e
        for e in all_entries
        if e.get("type") == "escalation" and e.get("escalation_id") in unresolved_ids
    ]

    # --- session plan --------------------------------------------------------
    session_plan_path = session_dir / "session-plan.md"
    if session_plan_path.exists():
        session_plan_text = session_plan_path.read_text(encoding="utf-8")
    else:
        session_plan_text = ""

    # --- assemble ------------------------------------------------------------
    payload = {
        "schema_version": 1,
        "state": asdict(state_obj),
        "strategy": asdict(strategy_obj),
        "escalations": {
            "unresolved": unresolved,
            "all_entries": all_entries,
        },
        "session_plan_text": session_plan_text,
    }

    if payload["schema_version"] != _EXPECTED_SCHEMA_VERSION:
        raise RuntimeError(f"orchestrator_context schema_version drift: returned {payload['schema_version']}, expected {_EXPECTED_SCHEMA_VERSION}")

    return payload
