"""Sanctioned import surface for orchestrator agent code.

This is a convention module — it re-exports the four I/O primitives that
orchestrator-prompt pseudocode is allowed to call, so there is a single
audit-point import rather than scattered imports from multiple internal
modules.  It contains no new logic.
"""

from cortex_command.overnight.deferral import write_escalation
from cortex_command.overnight.orchestrator_context import aggregate_round_context
from cortex_command.overnight.state import load_state, save_state, update_feature_status

__all__ = [
    "aggregate_round_context",
    "load_state",
    "save_state",
    "update_feature_status",
    "write_escalation",
]
