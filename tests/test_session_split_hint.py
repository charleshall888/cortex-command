"""The served envelope carries no session-split hint (#474, removing #394's).

#394 added a `session_split_hint` key at the refine→plan and plan→implement
seams. Served, it read as a request to stop rather than as information: #423
reworded it, #445 added a Stop hook, and the operator still had to spend turns
saying "keep going". Removed on the operator's standing decision that an
unprompted operator splits fine on their own.

This is an absence assertion — it keeps the removal removed. Reintroducing the
key (or any per-state nudge in its place) fails here, which is the point: the
next reader should re-open #474 rather than re-derive the affordance from
project.md's "Phase boundaries are session boundaries" line.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cortex_command.lifecycle import next_verb
from cortex_command.lifecycle import transition_table as tt

# build_served_envelope does no I/O on the log path (stringified only).
_DUMMY_LOG = Path("/nonexistent/cortex/lifecycle/x/events.log")


@pytest.mark.parametrize("state", sorted(tt.STATE_NAMES))
def test_no_session_split_hint_served(state: str) -> None:
    envelope = next_verb.build_served_envelope(state=state, events_log=_DUMMY_LOG)
    assert "session_split_hint" not in envelope, (
        f"{state}: the session-split hint was removed in #474 — reopen that "
        "ticket rather than re-adding the key"
    )
