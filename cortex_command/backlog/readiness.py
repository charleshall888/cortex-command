"""Pure readiness predicate for backlog items.

This module owns the canonical "is this item ready to work on?" predicate
shared by ``cortex_command.overnight.backlog.filter_ready``,
``backlog/generate_index.py``, and the ``bin/cortex-backlog-ready`` script.

The helper does **no** filesystem I/O: artifact-existence checks
(``research.md`` / ``spec.md`` / pipeline-branch merge) remain in
``filter_ready``. This keeps the helper trivially testable and reusable
in non-overnight contexts (e.g. dashboards, future bin scripts).

Reason-string contract
----------------------

The helper returns ``(is_ready, reason)`` where ``reason`` follows the
canonical wire format consumed by ``overnight/plan.py``,
``overnight/backlog.py``, and ``cortex-backlog-ready``'s
``--include-blocked`` output:

    - ``"status: <value>"``                       — status not in eligible_statuses
    - ``"blocked by <id1>: <status1>, <id2>: <status2>"`` — non-terminal internal blockers (multi-blocker comma-joined)
    - ``"external blocker: <ref>"``               — non-digit, non-UUID reference
    - ``"blocker not found: <uuid>"``             — UUID-shaped string not present in all_items
    - ``"self-referential blocker: <id>"``        — item references its own id

The sentinel ``(False, None)`` is returned when at least one blocker is
internal-non-terminal — the caller (``filter_ready``) supplies the final
reason via Phase-2 BFS.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Literal

from cortex_command.common import TERMINAL_STATUSES


# UUID v4-style pattern (8-4-4-4-12 hex). We accept the canonical 36-char form
# as well as bare 8+ hex strings used as short ids elsewhere; in practice the
# only callers feed us either stringified integers, zero-padded ids, full
# UUIDs, or external references like ``"anthropics/claude-code#34243"``.
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _looks_like_uuid(ref: str) -> bool:
    """Return True if *ref* matches the canonical 36-char UUID format."""
    return bool(_UUID_RE.match(ref))


@dataclass
class ReadinessPartition:
    """Result of :func:`partition_ready`.

    Attributes:
        ready: Items that pass the predicate.
        ineligible: Triples of ``(item, reason, rejection)`` where
            ``rejection`` is either ``"status"`` or ``"blocker"`` and
            ``reason`` is the canonical wire-format string from the
            helper's reason-string table.
    """

    ready: list[Any]
    ineligible: list[tuple[Any, str, Literal["status", "blocker"]]]


def _build_status_lookup(all_items: Iterable[Any]) -> dict[str, str]:
    """Build a dual-key id → status lookup.

    Mirrors ``cortex_command/overnight/backlog.py`` lines 475-490: keys are
    inserted as the unpadded stringified id, the zero-padded (3-digit)
    stringified id, and the UUID if the item carries one.
    """
    status_by_id: dict[str, str] = {}
    for item in all_items:
        item_id = str(item.id)
        status_by_id[item_id] = item.status
        status_by_id[item_id.zfill(3)] = item.status
        uuid = getattr(item, "uuid", None)
        if uuid:
            status_by_id[uuid] = item.status
    return status_by_id


def is_item_ready(
    item: Any,
    all_items: Iterable[Any],
    *,
    eligible_statuses: Iterable[str],
    treat_external_blockers_as: Literal["blocking", "resolved"] = "blocking",
) -> tuple[bool, str | None]:
    """Return ``(is_ready, reason)`` for *item*.

    Args:
        item: BacklogItem-like object exposing ``status``, ``blocked_by``,
            ``id``, and (optionally) ``uuid`` via attribute access.
        all_items: Full backlog set used to resolve ``blocked_by`` references.
        eligible_statuses: Status values that pass gate 1.
        treat_external_blockers_as: ``"blocking"`` (new behavior — a
            non-digit, non-UUID reference produces the
            ``"external blocker: <ref>"`` reason) or ``"resolved"`` (legacy
            ``generate_index.py`` behavior — silently skip non-digit refs).

    Returns:
        Tuple ``(is_ready, reason)``. ``reason`` is ``None`` when the item
        is ready *or* when at least one blocker is internal-non-terminal
        (sentinel — the caller supplies the final reason via Phase-2 BFS).
    """
    eligible_set = frozenset(eligible_statuses)

    # Gate 1: status check.
    if item.status not in eligible_set:
        return False, f"status: {item.status}"

    blocked_by = list(getattr(item, "blocked_by", []) or [])
    if not blocked_by:
        return True, None

    status_by_id = _build_status_lookup(all_items)
    item_id_str = str(item.id)
    item_id_padded = item_id_str.zfill(3)

    non_terminal_internal: list[tuple[str, str]] = []  # (ref, status)
    has_internal_blocker = False

    for ref in blocked_by:
        ref_str = str(ref)

        # Self-referential check (digit ref matching item.id).
        if ref_str.isdigit():
            try:
                if int(ref_str) == int(item.id):
                    return False, f"self-referential blocker: {ref_str}"
            except (TypeError, ValueError):
                pass

        # Internal lookups: try the ref as-is, plus zero-padded form.
        candidates = [ref_str]
        if ref_str.isdigit():
            candidates.append(ref_str.zfill(3))

        resolved_status: str | None = None
        for candidate in candidates:
            if candidate in status_by_id:
                resolved_status = status_by_id[candidate]
                break

        if resolved_status is not None:
            has_internal_blocker = True
            if resolved_status not in TERMINAL_STATUSES:
                non_terminal_internal.append((ref_str, resolved_status))
            # Terminal internal blockers are silently resolved.
            continue

        # Not found in all_items. Disambiguate UUID vs external ref.
        if _looks_like_uuid(ref_str):
            return False, f"blocker not found: {ref_str}"

        # External (non-digit, non-UUID) reference.
        if treat_external_blockers_as == "resolved":
            # Legacy generate_index.py behavior: silently skip.
            continue
        return False, f"external blocker: {ref_str}"

    if non_terminal_internal:
        # Sentinel: caller decides via Phase-2 BFS whether these resolve
        # within the same session.
        return False, None

    # All blockers resolved (terminal, or external-treated-as-resolved).
    return True, None


def partition_ready(
    items: Iterable[Any],
    all_items: Iterable[Any] | None = None,
    *,
    eligible_statuses: Iterable[str],
    treat_external_blockers_as: Literal["blocking", "resolved"] = "blocking",
) -> ReadinessPartition:
    """Partition *items* into ready vs. ineligible per :func:`is_item_ready`.

    The sentinel ``(False, None)`` from :func:`is_item_ready` is materialized
    here as the literal reason string ``"blocked by non-terminal internal blocker"``
    with rejection cause ``"blocker"``. Callers that need the helper-only
    sentinel (e.g. ``filter_ready``'s Phase-2 BFS) should call
    :func:`is_item_ready` directly.
    """
    items_list = list(items)
    full_set = items_list if all_items is None else list(all_items)

    ready: list[Any] = []
    ineligible: list[tuple[Any, str, Literal["status", "blocker"]]] = []

    for item in items_list:
        is_ready, reason = is_item_ready(
            item,
            full_set,
            eligible_statuses=eligible_statuses,
            treat_external_blockers_as=treat_external_blockers_as,
        )
        if is_ready:
            ready.append(item)
            continue

        if reason is None:
            # Sentinel: at least one non-terminal internal blocker.
            ineligible.append((item, "blocked by non-terminal internal blocker", "blocker"))
            continue

        rejection: Literal["status", "blocker"] = (
            "status" if reason.startswith("status: ") else "blocker"
        )
        ineligible.append((item, reason, rejection))

    return ReadinessPartition(ready=ready, ineligible=ineligible)
