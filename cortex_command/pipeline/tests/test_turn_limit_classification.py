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


# ---------------------------------------------------------------------------
# Turn ceilings are a backstop, not a working constraint
# ---------------------------------------------------------------------------
#
# Measured across every session on disk when these numbers were set: 32
# dispatches with a recorded turn count, successful runs spanning 7-30 turns
# (median 14). The old ceilings were 15/20/30 — the busiest healthy dispatch
# landed exactly on the `complex` cap, and two dispatches were killed at 21/20
# and 31/30, the latter reverting an already-merged feature.

_OBSERVED_MAX_HEALTHY_TURNS = 30


def test_every_tier_ceiling_clears_observed_work_by_a_wide_margin():
    """A ceiling reachable by ordinary work is not a backstop."""
    from cortex_command.pipeline.dispatch import TIER_CONFIG

    for tier, cfg in TIER_CONFIG.items():
        assert cfg["max_turns"] >= _OBSERVED_MAX_HEALTHY_TURNS * 4, (
            f"tier {tier!r} caps at {cfg['max_turns']} turns, too close to the "
            f"{_OBSERVED_MAX_HEALTHY_TURNS} a healthy dispatch has already used"
        )


def test_every_tier_keeps_a_budget_cap():
    """Cost control lives in the budget, which is why turns can be generous.

    Raising the turn ceilings is only safe because ``max_budget_usd`` is
    enforced independently and pauses the session when tripped. Dropping a
    budget cap would silently convert the raised turn ceiling into the sole —
    and now very loose — spend guard.
    """
    from cortex_command.pipeline.dispatch import TIER_CONFIG

    for tier, cfg in TIER_CONFIG.items():
        assert cfg.get("max_budget_usd", 0) > 0, (
            f"tier {tier!r} has no budget cap; turns must not be the only guard"
        )


def test_orchestrator_ceiling_stays_bounded_while_it_has_no_budget_cap():
    """The orchestrator is spawned without a budget flag.

    ``claude -p`` gets ``--max-turns`` and nothing else, so this constant is the
    only thing bounding a runaway round. It may rise when the orchestrator gains
    a cost cap; until then it must stay small enough that a runaway is
    affordable — observed rounds cost ~$0.58/turn.
    """
    from cortex_command.overnight.runner import ORCHESTRATOR_MAX_TURNS

    assert ORCHESTRATOR_MAX_TURNS >= 100, "must clear observed rounds comfortably"
    assert ORCHESTRATOR_MAX_TURNS <= 150, (
        "without a budget cap this is the only spend ceiling on an orchestrator "
        "round; at ~$0.58/turn a larger value permits a runaway costing >$85"
    )
