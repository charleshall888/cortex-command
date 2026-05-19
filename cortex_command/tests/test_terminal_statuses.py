"""Tests verifying 'superseded' is recognised as a terminal status."""
import cortex_command.overnight.plan as _plan
from cortex_command.common import TERMINAL_STATUSES


def test_superseded_in_common_terminal_statuses() -> None:
    assert "superseded" in TERMINAL_STATUSES


def test_superseded_in_plan_terminal() -> None:
    assert "superseded" in _plan._TERMINAL
