"""Unit tests for :mod:`cortex_command.backlog.readiness`.

Each test pins one row of the canonical reason-string table from spec R3
of the ``extract-backlog-pick-ready-set-into-bin-backlog-ready`` lifecycle.

The helper is filesystem-pure: tests use lightweight stand-in objects via
``types.SimpleNamespace`` to avoid coupling to the full ``BacklogItem``
dataclass. The :class:`cortex_command.overnight.backlog.BacklogItem`
satisfies the same attribute-access protocol — that path is exercised
indirectly by Tasks 2/3.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from cortex_command.backlog import (
    ReadinessPartition,
    is_item_ready,
    partition_ready,
)


ELIGIBLE = ("backlog", "ready", "in_progress", "implementing", "refined")


def _item(
    *,
    id: int,
    status: str = "backlog",
    blocked_by: list[str] | None = None,
    uuid: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=id,
        status=status,
        blocked_by=blocked_by or [],
        uuid=uuid,
    )


# ---------------------------------------------------------------------------
# Reason-string table coverage (one test per row)
# ---------------------------------------------------------------------------


def test_empty_blocked_by_eligible_status_passes() -> None:
    """Row: empty blocked_by + eligible status → (True, None)."""
    item = _item(id=1, status="refined")
    is_ready, reason = is_item_ready(
        item, [item], eligible_statuses=ELIGIBLE,
        treat_external_blockers_as="blocking",
    )
    assert is_ready is True
    assert reason is None


def test_status_outside_eligible_returns_status_reason() -> None:
    """Row: ``status: <value>`` for status not in eligible_statuses."""
    item = _item(id=2, status="complete")
    is_ready, reason = is_item_ready(
        item, [item], eligible_statuses=ELIGIBLE,
        treat_external_blockers_as="blocking",
    )
    assert is_ready is False
    assert reason == "status: complete"


def test_external_blocker_non_digit_ref() -> None:
    """Row: non-digit, non-UUID ref → ``external blocker: <ref>``."""
    item = _item(
        id=3, status="backlog",
        blocked_by=["anthropics/claude-code#34243"],
    )
    is_ready, reason = is_item_ready(
        item, [item], eligible_statuses=ELIGIBLE,
        treat_external_blockers_as="blocking",
    )
    assert is_ready is False
    assert reason == "external blocker: anthropics/claude-code#34243"


def test_all_terminal_blockers_pass() -> None:
    """Row: blockers resolved (terminal status) → (True, None)."""
    blocker = _item(id=10, status="complete")
    item = _item(id=11, status="refined", blocked_by=["10"])
    is_ready, reason = is_item_ready(
        item, [blocker, item], eligible_statuses=ELIGIBLE,
        treat_external_blockers_as="blocking",
    )
    assert is_ready is True
    assert reason is None


def test_one_non_terminal_internal_blocker_returns_sentinel() -> None:
    """Row: one internal non-terminal blocker → (False, None) sentinel."""
    blocker = _item(id=20, status="in_progress")
    item = _item(id=21, status="refined", blocked_by=["20"])
    is_ready, reason = is_item_ready(
        item, [blocker, item], eligible_statuses=ELIGIBLE,
        treat_external_blockers_as="blocking",
    )
    assert is_ready is False
    assert reason is None


def test_multiple_non_terminal_internal_blockers_sentinel_wins() -> None:
    """Row: multiple non-terminal internal blockers → sentinel."""
    b1 = _item(id=30, status="in_progress")
    b2 = _item(id=31, status="backlog")
    item = _item(id=32, status="refined", blocked_by=["30", "31"])
    is_ready, reason = is_item_ready(
        item, [b1, b2, item], eligible_statuses=ELIGIBLE,
        treat_external_blockers_as="blocking",
    )
    assert is_ready is False
    assert reason is None


def test_zero_padded_blocker_id_resolves_like_unpadded() -> None:
    """Row: ``"036"`` resolves identically to ``"36"``."""
    blocker = _item(id=36, status="complete")
    item = _item(id=37, status="refined", blocked_by=["036"])
    is_ready, reason = is_item_ready(
        item, [blocker, item], eligible_statuses=ELIGIBLE,
        treat_external_blockers_as="blocking",
    )
    assert is_ready is True
    assert reason is None

    # And the inverse: an unpadded ref resolving against an item whose id
    # we look up via the padded key still works.
    blocker2 = _item(id=8, status="complete")
    item2 = _item(id=40, status="refined", blocked_by=["8"])
    is_ready2, reason2 = is_item_ready(
        item2, [blocker2, item2], eligible_statuses=ELIGIBLE,
        treat_external_blockers_as="blocking",
    )
    assert is_ready2 is True
    assert reason2 is None


def test_uuid_blocker_not_in_all_items() -> None:
    """Row: UUID-shaped ref absent from all_items → ``blocker not found: <uuid>``."""
    missing_uuid = "12345678-1234-1234-1234-123456789012"
    item = _item(id=50, status="refined", blocked_by=[missing_uuid])
    is_ready, reason = is_item_ready(
        item, [item], eligible_statuses=ELIGIBLE,
        treat_external_blockers_as="blocking",
    )
    assert is_ready is False
    assert reason == f"blocker not found: {missing_uuid}"


def test_self_referential_blocker() -> None:
    """Row: item references its own id → ``self-referential blocker: <id>``."""
    item = _item(id=60, status="refined", blocked_by=["60"])
    is_ready, reason = is_item_ready(
        item, [item], eligible_statuses=ELIGIBLE,
        treat_external_blockers_as="blocking",
    )
    assert is_ready is False
    assert reason == "self-referential blocker: 60"


def test_treat_external_blockers_as_resolved_legacy_behavior() -> None:
    """``treat_external_blockers_as='resolved'`` silently skips non-digit refs."""
    item = _item(
        id=70, status="refined",
        blocked_by=["anthropics/claude-code#34243"],
    )
    is_ready, reason = is_item_ready(
        item, [item], eligible_statuses=ELIGIBLE,
        treat_external_blockers_as="resolved",
    )
    assert is_ready is True
    assert reason is None


# ---------------------------------------------------------------------------
# partition_ready
# ---------------------------------------------------------------------------


def test_partition_ready_returns_parallel_lists_with_rejection_causes() -> None:
    """``partition_ready`` returns parallel ready/ineligible lists.

    The ``rejection`` field is ``"status"`` for status failures and
    ``"blocker"`` for any blocker-related failure (including the sentinel).
    """
    ready_item = _item(id=80, status="refined")
    status_fail = _item(id=81, status="complete")
    blocker = _item(id=82, status="in_progress")
    blocker_fail = _item(id=83, status="refined", blocked_by=["82"])
    external_fail = _item(
        id=84, status="refined",
        blocked_by=["anthropics/claude-code#34243"],
    )

    items = [ready_item, status_fail, blocker_fail, external_fail]
    all_items = items + [blocker]

    partition = partition_ready(
        items, all_items, eligible_statuses=ELIGIBLE,
        treat_external_blockers_as="blocking",
    )

    assert isinstance(partition, ReadinessPartition)
    assert partition.ready == [ready_item]

    # Ineligible list is parallel — same length as inputs minus ready.
    assert len(partition.ineligible) == 3

    by_id = {entry[0].id: entry for entry in partition.ineligible}

    item, reason, rejection = by_id[81]
    assert reason == "status: complete"
    assert rejection == "status"

    # Sentinel from helper materializes with rejection="blocker".
    item, reason, rejection = by_id[83]
    assert rejection == "blocker"

    item, reason, rejection = by_id[84]
    assert reason == "external blocker: anthropics/claude-code#34243"
    assert rejection == "blocker"
