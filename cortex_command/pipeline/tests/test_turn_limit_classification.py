"""Turn-limit exhaustion must not read as an unknown crash.

Regression for session ``overnight-2026-07-28-1216``. The CLI exits 1 when it
runs out of ``--max-turns`` while the model still wants a tool, and the SDK
surfaces that only as ``Command failed with exit code 1`` with **empty** child
stderr. Classified ``unknown``, the review gate read it as a could-not-run
ERROR and reverted an already-merged feature, deferring it with a blocking
question whose body read "Issues: (no issues listed)".

Observed signatures from that session:
  implement  max_turns=20  num_turns=21  stop_reason=tool_use
  review     max_turns=30  num_turns=31  stop_reason=tool_use
"""

from __future__ import annotations

import pytest

from cortex_command.pipeline.dispatch import ERROR_RECOVERY, _is_turn_limit_stop


@pytest.mark.parametrize(
    "stop_reason, num_turns, max_turns",
    [
        ("tool_use", 31, 30),  # the review dispatch that lost #414's merge
        ("tool_use", 21, 20),  # the implement dispatch, same session
        ("tool_use", 30, 30),  # boundary: reported at the ceiling, not past it
    ],
)
def test_turn_limit_signature_is_detected(stop_reason, num_turns, max_turns):
    assert _is_turn_limit_stop(stop_reason, num_turns, max_turns) is True


@pytest.mark.parametrize(
    "stop_reason, num_turns, max_turns",
    [
        ("end_turn", 12, 30),   # ordinary completion well under the ceiling
        ("end_turn", 31, 30),   # finished cleanly; not a turn-limit kill
        ("max_tokens", 31, 30),  # context truncation is its own failure mode
        ("tool_use", 5, 30),    # stopped mid-tool-use for some other reason
        ("tool_use", None, 30),  # SDK gave no turn count — cannot claim it
        ("tool_use", 31, None),  # no configured ceiling to compare against
        (None, 31, 30),          # no stop_reason at all
    ],
)
def test_other_stops_are_not_turn_limits(stop_reason, num_turns, max_turns):
    assert _is_turn_limit_stop(stop_reason, num_turns, max_turns) is False


def test_turn_limit_recovery_is_retry_not_unknown():
    """The class must exist and retry.

    Retry is the right recovery: the branch work is intact and the same
    session's implement dispatch recovered on a later attempt after its own
    21/20 stop. What must never happen again is this landing in the
    unclassified bucket the review gate treats as could-not-run.
    """
    assert ERROR_RECOVERY["turn_limit_exhausted"] == "retry"
