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
                                        # active items, PLUS any closed epic
                                        # that still heads a group in "epics"
      "item_order":  ["<id>", ...],     # collect_items' priority-then-id order
      "epics":       {<build_epic_map envelope, epics pruned and children
                       filtered — see _epic_map_for_board>},
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
* ``items`` is not the active set — ``item_order`` is. It carries one extra
  class of record: a closed epic that still has active children, because the
  group heading is that epic's own ticket row and it needs something to render.
  Anything deriving "what is active" must read ``item_order`` (or
  ``active_ids``), never ``items``' keys or length; the flat Standalone list is
  ``item_order``'s complement and the active count is its length.
* ``epics`` is no longer ``build_epic_map``'s output verbatim. Epics are
  *detected* over the whole non-archived corpus so a closed epic still heads
  its group, then children are filtered to active ids and childless closed
  epics are dropped. Every id in a ``children`` list is therefore resolvable
  in ``items``; an epic key is too.
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

Two lookup traps govern every template that reads this snapshot, and both fail
*silently* — they render a blank rather than raising, so a broken join looks
like missing data:

* Jinja tries ``getattr`` before ``__getitem__``, so dotted access to a key
  named ``items`` resolves to the bound ``dict.items`` METHOD and never to the
  snapshot's data. Every snapshot key must be read with a subscript. The same
  trap applies to any per-item key named keys / values / get / update / copy /
  pop.
* ``epics`` is ``build_epic_map``'s two-key envelope, so the epic id map lives
  one level in at ``snap['epics']['epics']``; iterating the outer dict yields
  the literal keys ``schema_version`` and ``epics`` and zero epic ids. Child
  ids inside it are **ints** while ``items`` is str-keyed, so a child id must
  be stringified before the join.

(Recorded here rather than in a template because the template that documented
them — the retired ``triage_board.html`` — was not the only consumer, and a
trap description that lives in one consumer dies with it. Templates that
consume the *view-models* in ``backlog/view.py`` are exempt: no template
touches a snapshot on those surfaces.)
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from cortex_command.backlog.build_epic_map import build_epic_map
from cortex_command.backlog.generate_index import collect_items, full_corpus
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


def _display_record(record: dict) -> dict:
    """Enrich one ``collect_items`` record with the three board-only fields."""
    return {
        **record,
        "deferred_status": record.get("status") == "deferred",
        "deferred_tag": _has_deferred_tag(record),
        "phase": _normalize_phase(record.get("lifecycle_phase")),
    }


def _epic_map_for_board(corpus: list[dict], active_ids: set[int]) -> dict:
    """Build the board's epic map: full-corpus detection, active-only children.

    Two rules that pull in opposite directions, both necessary.

    *Detection* spans the whole non-archived corpus. ``build_epic_map``
    identifies an epic by scanning the list it is handed for ``type: epic``, so
    passing the active slice meant a **closed** epic was not recognized as an
    epic at all — and its still-active children, the late-arriving children
    #438 exists because of, fell through the template's child-id exclusion into
    the Standalone list, asserting they had no parent.

    *Children* are then filtered back to active ids, because every per-row field
    on the board resolves through ``items``, which stays active-only. A closed
    child would subscript to a Jinja ``Undefined`` and render as a blank row
    rather than raise — the silent-failure mode this module's own docstring
    warns consumers about.

    A closed epic is kept only when it still has an active child. Without that
    gate, full-corpus detection would seed a "no active children" group for
    every epic ever finished — 34 of them on this repo, 19 on wild-light. An
    *active* epic is kept regardless, zero children included: that empty group
    is how the board says a live epic has nothing left in flight.

    ``strict_schema=False`` is not a preference: the default raises on any
    schema version this code did not write, which in a repo whose corpus this
    process does not control means one future bump kills the poll permanently.
    """
    envelope = build_epic_map(corpus, strict_schema=False)
    kept: dict[str, dict] = {}
    for epic_id, epic in envelope.get("epics", {}).items():
        children = [
            child for child in epic.get("children", [])
            if child.get("id") in active_ids
        ]
        try:
            epic_is_active = int(epic_id) in active_ids
        except (TypeError, ValueError):
            # A non-numeric epic key cannot be matched against the active set;
            # keep it if it has active children, exactly as the numeric path
            # would, rather than dropping the group on an id-shape surprise.
            epic_is_active = False
        if children or epic_is_active:
            kept[epic_id] = {**epic, "children": children}
    return {**envelope, "epics": kept}


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

    corpus = full_corpus(all_items)
    epics = _epic_map_for_board(corpus, active_ids)

    status_by_id = _build_status_lookup(all_items_ns)

    items: dict[str, dict] = {}
    item_order: list[str] = []
    blocked_why: dict[str, list[dict]] = {}

    for record in active_items:
        item_id = str(record["id"])
        item_order.append(item_id)
        items[item_id] = _display_record(record)

        blockers = _resolve_blockers(record, status_by_id, titles_by_id)
        if blockers:
            blocked_why[item_id] = blockers

    # A closed epic that still heads a group needs a record to render with: the
    # board's group heading IS the epic's own ticket row. These are added to
    # `items` but deliberately NOT to `item_order` — that list is the board's
    # active set, the navigator partitions exactly that set and reconciles its
    # band counts against the size of it, and the flat Standalone list is its
    # complement, so an entry here would both inflate the count and reappear as
    # a standalone row.
    by_id = {str(record["id"]): record for record in corpus}
    for epic_id in epics["epics"]:
        if epic_id in items or epic_id not in by_id:
            continue
        items[epic_id] = _display_record(by_id[epic_id])

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
