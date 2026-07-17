"""Served-envelope session-split hint (#394).

`cortex-lifecycle-next` serves one optional `session_split_hint` key at the
refine→plan and plan→implement boundaries (keyed by their target states) — the
structural nudge behind the "Phase boundaries are session boundaries"
constraint in cortex/requirements/project.md. Every other state serves no such
key: the hint is a suggestion at exactly two seams, not a proliferated field.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cortex_command.lifecycle import next_verb
from cortex_command.lifecycle import transition_table as tt

# build_served_envelope does no I/O on the log path (stringified only).
_DUMMY_LOG = Path("/nonexistent/cortex/lifecycle/x/events.log")

_HINT_STATES = {"plan", "implement"}


@pytest.mark.parametrize("state", sorted(tt.STATE_NAMES))
def test_hint_served_only_at_split_states(state: str) -> None:
    envelope = next_verb.build_served_envelope(state=state, events_log=_DUMMY_LOG)
    if state in _HINT_STATES:
        hint = envelope.get("session_split_hint")
        assert isinstance(hint, str) and hint, f"{state}: expected a non-empty hint"
        assert "\n" not in hint, f"{state}: the hint must stay a single line"
    else:
        assert "session_split_hint" not in envelope, (
            f"{state}: session_split_hint must serve only at {sorted(_HINT_STATES)}"
        )
