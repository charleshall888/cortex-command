"""Backlog ticket-feed snapshot for the dashboard.

Builds the single in-memory picture of backlog truth that command-station
views read, so status-checking happens on a persistent surface instead of
in token-metered sessions. The snapshot is computed here as pure calls and
committed by ``_poll_slow`` in one assignment; this module never writes to
disk and never mutates a snapshot in place.

The schema below is the contract downstream views implement against. It is
pinned rather than discovered: consumers must be buildable from this
docstring without reading the code that fills it.

.. code-block:: text

    {
      "schema_version": "1",
      "polled_ts":   "<ISO8601 UTC>",   # supplied by the caller; only the
                                        # 30s poll writes it, so it stays
                                        # honest when a fault freezes the
                                        # snapshot (see mark_snapshot_stale)
      "stale":       false,             # true once a caught fault retained
                                        # a prior snapshot
      "items":       {"<id>": {<collect_items record>, "deferred_status": bool,
                               "deferred_tag": bool, "phase": "<str>|null"}},
      "item_order":  ["<id>", ...],     # collect_items' priority-then-id order
      "epics":       {<build_epic_map envelope verbatim>},
      "ready":       ["<id>", ...],
      "ineligible":  [{"id": "<id>", "reason": "<str>", "kind": "status"|"blocker"}],
      "blocked_why": {"<id>": [{"ref": "<str>", "kind": "internal"|"external"|"not_found",
                                "status": "<str>|null", "title": "<str>|null"}]},
      "active_ids":  [<int>, ...],
      "archive_ids": [<int>, ...],
      "counts":      {"active": <int>, "archived": <int>}
    }

Shape notes that are load-bearing for consumers:

* ``items`` is id-keyed, not a list, so resolving one ticket is a subscript
  rather than a scan. Ids are stringified everywhere they are used as keys;
  ``active_ids``/``archive_ids`` stay integers because they are identity
  sets, not lookups.
* Status, type, and priority are carried through raw. All three vocabularies
  are documented as closed enums but are open in practice — the item-creation
  verb applies no restriction — so every display switch needs a default branch.
* ``phase`` collapses the several spellings of "no phase" to one null value;
  any other phase passes through verbatim, including values outside the
  documented set. The phase vocabulary is open wherever an item's phase comes
  from raw frontmatter rather than an on-disk lifecycle directory.
* Deferral is two independent flags, never one. The readiness partition does
  not read tags, deliberately, so a tag-deferred item at an eligible status
  legitimately lands in ``ready`` and a view must be able to badge that case
  distinctly from a deferred *status*.
* An absent corpus yields a schema-complete envelope with empty collections,
  which is a different fact from a snapshot of ``None`` (never polled).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from cortex_command.backlog.build_epic_map import build_epic_map
from cortex_command.backlog.generate_index import collect_items
from cortex_command.backlog.readiness import (
    _build_status_lookup,
    _looks_like_uuid,
    partition_ready,
)
from cortex_command.overnight.backlog import ELIGIBLE_STATUSES

SCHEMA_VERSION = "1"

# Every spelling of "this item has no phase" seen across real corpora, plus
# the YAML null tokens that would survive the index writer's own narrower
# check. Compared case-folded; whitespace-only values strip to "".
_NULL_PHASE_TOKENS = frozenset({"", "null", "none", "nil", "~"})

# The tag whose presence marks an item deferred. Reimplemented here rather
# than imported: the index writer's predicate sits behind a private name in
# a module that a shipped spec fenced off, and teaching the readiness helper
# about tags would contradict that same spec.
_DEFERRED_TAG = "deferred"


def _normalize_phase(raw: object) -> str | None:
    """Collapse the null spellings of a lifecycle phase to ``None``.

    Anything else is returned stripped but otherwise verbatim — inventing a
    display mapping here would assume a closed phase vocabulary that the
    raw-frontmatter path does not enforce.
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if text.lower() in _NULL_PHASE_TOKENS:
        return None
    return text


def _has_deferred_tag(record: dict) -> bool:
    """Return True iff *record* carries the deferral tag (whole-element match)."""
    return any(
        str(tag).strip().lower() == _DEFERRED_TAG for tag in record.get("tags", [])
    )


def _resolve_blockers(
    record: dict,
    status_by_id: dict[str, str],
    titles_by_id: dict[str, str],
) -> list[dict]:
    """Resolve one item's blocker refs to status and title.

    Preserves the readiness helper's three-way split rather than collapsing
    to found/not-found: an unresolvable reference that looks like a UUID is a
    dangling internal pointer, while a non-digit, non-UUID reference names
    work outside this backlog entirely. A view renders those differently.
    """
    resolved: list[dict] = []
    for ref in record.get("blocked_by", []) or []:
        ref_str = str(ref)

        # Mirror the helper's lookup: bare id first, then zero-padded.
        candidates = [ref_str]
        if ref_str.isdigit():
            candidates.append(ref_str.zfill(3))

        status: str | None = None
        for candidate in candidates:
            if candidate in status_by_id:
                status = status_by_id[candidate]
                break

        if status is not None:
            title_key = str(int(ref_str)) if ref_str.isdigit() else ref_str
            resolved.append({
                "ref": ref_str,
                "kind": "internal",
                "status": status,
                # None for an archived blocker: the title scan is
                # non-recursive, so a view falls back to "#<id> (<status>)".
                "title": titles_by_id.get(title_key),
            })
        elif _looks_like_uuid(ref_str):
            resolved.append({
                "ref": ref_str, "kind": "not_found", "status": None, "title": None,
            })
        else:
            resolved.append({
                "ref": ref_str, "kind": "external", "status": None, "title": None,
            })

    return resolved


def build_backlog_snapshot(
    backlog_dir: Path,
    lifecycle_dir: Path,
    titles_by_id: dict[str, str],
    polled_ts: str,
) -> dict:
    """Return the ticket-feed snapshot documented in this module's docstring.

    Pure with respect to the caller's state: nothing here reads or writes
    ``DashboardState``, and the timestamp is supplied rather than stamped so
    the value can only originate from the loop that actually polled.

    Args:
        backlog_dir: Path to ``cortex/backlog/``.
        lifecycle_dir: Path to ``cortex/lifecycle/``. Resolved against the
            *local* project root; when the dashboard monitors a remote
            project the fleet panel resolves phases against a different tree,
            so per-ticket phases are local-only and may disagree.
        titles_by_id: Stringified item id → title, spanning terminal items.
            Sourced from the title scan the slow poll already runs.
        polled_ts: ISO 8601 UTC timestamp of this successful poll.

    Returns:
        A schema-complete dict. Degenerate corpora yield empty collections,
        never ``None`` and never a partial structure.
    """
    active_items, active_ids, archive_ids, all_items = collect_items(
        backlog_dir, lifecycle_dir
    )

    # The readiness helpers read attribute-style; collect_items returns plain
    # dicts. This is the established bridge, and skipping it raises.
    all_items_ns = [SimpleNamespace(**rec) for rec in all_items]
    active_items_ns = [SimpleNamespace(**rec) for rec in active_items]

    partition = partition_ready(
        active_items_ns,
        all_items_ns,
        eligible_statuses=ELIGIBLE_STATUSES,
        treat_external_blockers_as="blocking",
    )

    # strict_schema=False is not a preference: the default raises on any
    # schema version this code did not write, which in a repo whose corpus
    # this process does not control means one future bump kills the poll
    # permanently.
    epics = build_epic_map(active_items, strict_schema=False)

    status_by_id = _build_status_lookup(all_items_ns)

    items: dict[str, dict] = {}
    item_order: list[str] = []
    blocked_why: dict[str, list[dict]] = {}

    for record in active_items:
        item_id = str(record["id"])
        item_order.append(item_id)
        items[item_id] = {
            **record,
            "deferred_status": record.get("status") == "deferred",
            "deferred_tag": _has_deferred_tag(record),
            "phase": _normalize_phase(record.get("lifecycle_phase")),
        }

        blockers = _resolve_blockers(record, status_by_id, titles_by_id)
        if blockers:
            blocked_why[item_id] = blockers

    return {
        "schema_version": SCHEMA_VERSION,
        "polled_ts": polled_ts,
        "stale": False,
        "items": items,
        "item_order": item_order,
        "epics": epics,
        "ready": [str(item.id) for item in partition.ready],
        "ineligible": [
            {"id": str(item.id), "reason": reason, "kind": rejection}
            for item, reason, rejection in partition.ineligible
        ],
        "blocked_why": blocked_why,
        "active_ids": sorted(active_ids),
        "archive_ids": sorted(archive_ids),
        "counts": {"active": len(active_ids), "archived": len(archive_ids)},
    }


def mark_snapshot_stale(prior: dict | None) -> dict | None:
    """Return *prior* flagged stale, or ``None`` when there is nothing to keep.

    Returns a new dict rather than mutating: the caller commits snapshots in
    a single assignment, and an in-place edit would make a partially-updated
    snapshot observable to a concurrent reader.

    ``polled_ts`` is deliberately left at its last successful value. The only
    other timestamp on the dashboard state is rewritten every two seconds by
    a different loop, so it reads fresh while this data may have been frozen
    for days; ``stale`` is what tells them apart.
    """
    if prior is None:
        return None
    return {**prior, "stale": True}
