"""View-models for the backlog navigator.

This is the only module in the package that knows what a *section* is. The four
helpers beneath it answer separate questions — what depends on what
(:mod:`.graph`), what is it worth (:mod:`.score`), where does it sit
(:mod:`.bands`), where does it go on a page (:mod:`.epic_layout`) — and none of
them knows that the answers get arranged into "§ 01 READY" and "§ 02 EPICS".
Keeping that knowledge here is what lets a template be a template: every
sentence, count and coordinate a template prints is computed below and handed
over as a plain dict, so the Jinja layer has no arithmetic and no vocabulary
decisions left to make.

**One record, one appearance.** The page is partitioned so that a ticket is
rendered exactly once. A ticket that declares a resolvable ``parent`` belongs
to that epic's map and appears nowhere else; everything else is "loose" and
appears in the ready or blocked list. This is the operator's rule, and
:func:`_partition` is the single place it is applied — a second site would be
how the same ticket comes to read one thing in a list and another in a frame.

**The board does not argue.** It ranks and it shows structure; it does not
nominate a pick, rate alternates, or print the ledger behind a score. The
points column is what makes an ordering falsifiable, and the hover card
carries the working for any single row on demand. Deciding what to work on is
the ``/dev`` skill's job, not this surface's.

Two properties are load-bearing and are the reason several things below look
more careful than they need to:

**Nothing is read from disk.** Every builder takes the 30s poll's snapshot and
nothing else. A route that hit the filesystem would do it once per viewer per
poll for data the poller already holds, and the corpus argument
:func:`~.graph.build_graph` wants is reconstructible from the snapshot: the
slice records *are* the corpus for every id on the board, and the snapshot's
``blocked_why`` already carries the resolved status and title of every ref
pointing off it. ``root`` is therefore accepted (the route resolves it anyway,
and this builder sits beside the ``data.py`` builders that do take it) and
deliberately unread.

**The same snapshot renders byte-identically.** Every collection built here is
either sorted or built in a sorted iteration order, and no value anywhere reads
the wall clock — the ``stale`` term is anchored to ``max(updated)`` inside
:mod:`.score` for exactly this reason. A swap of an unchanged snapshot must
produce the same bytes, or the operator's cursor moves under their hand every
thirty seconds. Nothing here renders per-operator disclosure state: an epic is
always emitted closed and the client re-opens it after the swap.

An absent snapshot (never polled, or a non-``cortex-backlog`` backend, which
clears it to ``None``) returns a schema-complete empty view-model. Templates
render an empty state from a *present* key rather than guarding every access,
which is the difference between a page that says "awaiting first poll" and one
that renders blanks because a dotted lookup found an ``Undefined``.
"""

from __future__ import annotations

from typing import Any

from cortex_command.dashboard.backlog import bands as bands_mod
from cortex_command.dashboard.backlog.bands import OPEN_STATUSES
from cortex_command.dashboard.backlog.epic_layout import (
    PAD,
    POOL_INSET,
    SPINE_HEAD_H,
    LayoutContext,
    layout_epic,
)
from cortex_command.dashboard.backlog.graph import build_graph, normalize_ref
from cortex_command.dashboard.backlog.score import ScoreContext, score_of

# Band letter → the one- or two-word state a node or row carries. A *label*
# rather than a truncated title: a shortened title would be a width guess
# against an unbundled font.
_NODE_STATE = {
    "A": "ready",
    "B": "in flight",
    "C": "ready",
    "D": "ready",
    "E": "ready",
    "E*": "ready",
    "E′": "epic",
    "F": "deferred",
    "G": "held",
    "G′": "lapsed",
    "H": "off board",
}

# Band letter → border style, so a node in a frame carries the same channel the
# same record carries in its list row. Mirrors ``bands._BAND_META`` by key
# rather than importing the tuple, because a node needs a *default* for an id
# the partition never saw (an external blocker off the slice) and a lookup with
# a default is the honest expression of that.
_BORDER_OF_BAND = {
    "A": "solid",
    "B": "solid",
    "C": "solid",
    "D": "solid",
    "E": "solid",
    "E*": "solid",
    "E′": "dotted",
    "F": "dotted",
    "G": "dashed",
    "G′": "ghost",
    "H": "ghost",
}

# The sparse marks a ready row can carry. Three glyphs over the whole board,
# each naming a reason this row is not merely "startable and medium priority".
# Deliberately not a column of words: the dominant scoring term is `priority`
# on 49 of 51 startable rows in the largest real corpus, so a per-row reason
# column would print the same word forty-nine times.
_ROW_MARK = {
    "A": ("⚷", "holds other work"),
    "B": ("▸", "already in flight"),
    "G′": ("✓", "declared blocker has already closed"),
}

# Bands whose rows are startable today. G′ is inside it deliberately: a hold
# whose blocker already completed IS startable, and that is the entire finding
# the band exists to report.
_READY_KEYS = ("A", "B", "C", "D", "E", "E*", "G′")

# The collapsed panels under the tail, in reading order: (key, label, gloss).
# Epic containers (E′) are absent because an epic is a section head, not a row
# anywhere.
#
# Band H is not a category. Its label read "untriaged · closed in place ·
# off-board", which is the three unrelated reasons a record can land in the
# band, printed as though they were one — and a reader could not tell which of
# the three applied to any given row without opening the ticket. It is split
# here on the same facts, tested in the same order, that ``bands._RULES`` used
# to assign the band, so the split cannot disagree with the banding: no row
# changes band, and every row still lands in exactly one panel.
#
# "Closed in place" is not among them, and its absence is the measurement
# rather than an oversight. ``collect_items`` drops a terminal-status record
# before it reaches ``active_items`` (``if is_terminal: continue``), so no such
# record is ever in the ordering; the only terminal records that reach the
# board at all are the closed epic heads the feed adds to ``items`` alone, and
# those are off-board by the test below, which runs first. A panel for it would
# be a label no row can carry — the same unreachable-arm defect as the
# "discharged blocker" markup this table's rows used to render.
_TAIL_PANELS: tuple[tuple[str, str, str], ...] = (
    ("deferred", "deferred", ""),
    ("untriaged", "untriaged", "status: new — set a status and they rank"),
    ("offboard", "off the board", "absent from the board's ordering"),
    ("unruled", "unrecognised status", "not a status or priority the bands know"),
)


# ---------------------------------------------------------------------------
# Snapshot → context
# ---------------------------------------------------------------------------


def _snapshot(state: object) -> dict | None:
    """The poll's snapshot, or ``None`` when there has not been one."""
    snap = getattr(state, "backlog_snapshot", None)
    return snap if isinstance(snap, dict) else None


def _backend(state: object) -> str:
    """The resolved backlog backend, for the gate every backlog read sits behind."""
    return str(getattr(state, "backlog_backend", "cortex-backlog") or "")


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _id_key(tid: str) -> tuple[int, int, str]:
    """Numeric ids ascending, non-numeric after them — the package's ordering."""
    return (0, int(tid), "") if tid.isdigit() else (1, 0, tid)


def _items_of(snapshot: dict) -> dict[str, dict]:
    """The active slice, id-keyed with string keys.

    The snapshot already stringifies its keys; re-normalising costs one pass
    and removes the whole class of silent miss where an int key looks up as
    absent and every record scores as unknown.
    """
    raw = snapshot.get("items") or {}
    return {str(key): value for key, value in raw.items() if isinstance(value, dict)}


def _offslice_of(snapshot: dict) -> dict[str, dict]:
    """The snapshot's corpus resolution for ids the board points at but lacks.

    Absent on a snapshot written before the key existed, which is a live case:
    the poller retains the last good snapshot across a failed poll, so a
    process can serve one shape while running the code for another. An empty
    map degrades to the old placeholder rather than raising.
    """
    raw = snapshot.get("offslice") or {}
    return {str(key): value for key, value in raw.items() if isinstance(value, dict)}


def _corpus_of(snapshot: dict, items: dict[str, dict]) -> list[dict]:
    """Reconstruct :func:`~.graph.build_graph`'s corpus argument.

    The graph reads the corpus for exactly two things — a ref's status and its
    title — and the snapshot already carries both for every ref that points off
    the slice, in ``blocked_why``. So the corpus is the slice records plus one
    stub per off-slice ref, and no file is opened.

    The status is what makes this more than a nicety: it is the sole input to
    the discharged/live classification, and therefore the sole reason the HOLD
    LAPSED band can exist. A stub without it would redraw two startable tickets
    as blocked.
    """
    corpus: list[dict] = list(items.values())
    seen = set(items)
    for rows in (snapshot.get("blocked_why") or {}).values():
        for row in rows or []:
            ref = normalize_ref(row.get("ref"))
            if not ref or ref in seen:
                continue
            # A ref the feed could not resolve gets NO stub. Stubbing it made
            # it a known record inside ``build_graph``, which is the sole test
            # separating an ``unresolvable`` edge from an ``external`` one — so
            # a bare uuid left behind by a deleted ticket was classified as a
            # real off-board blocker, printed as "#<uuid>" with a link to a
            # page that 404s, and the ``unresolvable`` arm every downstream
            # reader branches on was unreachable from this path.
            if row.get("kind") == "not_found":
                continue
            seen.add(ref)
            stub: dict[str, Any] = {"id": ref, "status": row.get("status")}
            # Only when the feed actually resolved one. An invented placeholder
            # title would print on a held row as though it were the blocker's
            # real name; absent, the row falls back to naming the status.
            if row.get("title"):
                stub["title"] = row["title"]
            corpus.append(stub)
    return corpus


def _parents_of(
    items: dict[str, dict], offslice: dict[str, dict] | None = None
) -> dict[str, list[str]]:
    """Epic id → its active children, from each record's own ``parent`` field.

    Derived from ``parent`` rather than from the snapshot's ``epics`` envelope
    because the envelope is pruned for an older board's grouping rules (a closed
    epic is kept only while it still has children) while this map has to answer
    a different question: which container does the ``epic`` score term credit,
    and whose children does a map draw.

    **The parent must resolve to a real ticket.** A group is where a child goes
    *instead of* the ready list, so a typo in a ``parent`` field would otherwise
    move a startable ticket into a phantom epic named after the typo and take
    it off the board entirely. An unresolvable parent is treated as no parent:
    the ticket stays loose and stays visible, which is the failure this rule is
    chosen to produce.
    """
    known = set(items) | set(offslice or {})
    parents: dict[str, list[str]] = {}
    for tid in sorted(items, key=_id_key):
        parent = normalize_ref(items[tid].get("parent"))
        if parent and parent != tid and parent in known:
            parents.setdefault(parent, []).append(tid)
    return parents


def _context(
    snapshot: dict,
) -> tuple[dict[str, dict], Any, ScoreContext, dict[str, list[str]]]:
    """Assemble the slice, its graph, its score context and its parent map."""
    items = _items_of(snapshot)
    graph = build_graph(items, _corpus_of(snapshot, items))
    parents = _parents_of(items, _offslice_of(snapshot))
    ctx = ScoreContext(items=items, graph=graph, parents=parents)
    return items, graph, ctx, parents


# ---------------------------------------------------------------------------
# Shared reference helpers
# ---------------------------------------------------------------------------


def _title_of(tid: str, items: dict[str, dict], offslice: dict | None = None) -> str:
    """A ticket's title, from the board or from the corpus behind it.

    ``offslice`` carries the snapshot's corpus resolution for ids the board
    points at but does not hold. When it names one, the real title is used and
    the caller states the disposition separately (see :func:`_offslice_state`);
    the placeholder survives only for a reference the corpus cannot name at
    all, where it is true.

    Never the empty string: every place this feeds is a link's accessible name
    or a sentence, and a blank there reads as a rendering failure rather than
    as missing data.
    """
    record = items.get(tid)
    if record is not None:
        return _text(record.get("title")) or "untitled"
    known = (offslice or {}).get(tid)
    if known:
        return _text(known.get("title")) or "untitled"
    return "names no known ticket"


def _offslice_state(tid: str, offslice: dict | None) -> str:
    """The one- or two-word disposition of an id that is not on the board.

    Fits the SVG-text rule's label budget, so a node box can carry it, and it
    is the ticket's own status rather than a statement about the board. A
    corpus status is a single word for every spelling cortex writes; an
    unrecognised one is passed through rather than bucketed, because consumer
    repos run their own vocabularies.
    """
    known = (offslice or {}).get(tid) or {}
    return _text(known.get("status")) or "off board"


def _unrecognised_status_note(record: dict) -> str:
    """Name a status cortex does not know, or return the empty string.

    Unrecognised statuses are deliberately still ranked — cortex installs into
    repos that run their own vocabularies, and a board that swept ``must-have``
    into "untriaged" would be empty in such a repo. The obligation that comes
    with ranking them is to say so.
    """
    status = _text(record.get("status"))
    if not status or status.lower() in OPEN_STATUSES:
        return ""
    return "status · %s" % status


# ---------------------------------------------------------------------------
# Rows
# ---------------------------------------------------------------------------


def _row(
    row: bands_mod.Row,
    band_key: str,
    items: dict[str, dict],
    ctx: ScoreContext,
) -> dict:
    """One list row: four printed cells, plus a sparse mark and its blockers.

    The ``why it sits here`` column is gone. It was blank on 54 of 78 rows on
    the largest real corpus — including 46 of the 51 startable ones — because
    the band label already *was* the reason for most of them, and the width it
    claimed came off the title and wrapped half the table onto two lines. What
    it uniquely carried (which blockers hold this row) survives as
    ``blockers``, rendered only in § 03 where every row has some.

    The rank column is gone for the same reason: it was empty on 46 of 51
    startable rows, because bands D and E refuse to rank. ``points`` is the
    ordering claim and it is present on every row.
    """
    mark, mark_title = _ROW_MARK.get(band_key, ("", ""))
    record = items.get(row.id) or {}
    direct = ctx.direct_of(row.id)
    onward = ctx.downstream_of(row.id)
    return {
        # The one hover field a Row does not already carry. status/priority/
        # type come straight off the record and are deliberately verbatim, so
        # they are not re-derived here — but the key set a row exposes has to
        # match a node's exactly, or the shared macro reads Undefined.
        "unblocks": "%d direct / %d downstream" % (len(direct), len(onward)),
        "id": row.id,
        "title": row.title,
        "href": "/tickets/%s" % row.id,
        "points": row.points,
        "type": row.type or "unset",
        "status": row.status or "unset",
        "priority": row.priority or "unset",
        "band": band_key,
        "border_style": _BORDER_OF_BAND.get(band_key, "solid"),
        "state": _NODE_STATE.get(band_key, "on board"),
        "mark": mark,
        "mark_title": mark_title,
        # Present only when the status is outside cortex's own vocabulary. The
        # board still ranks such a record — consumer repos run their own
        # statuses — but it says so on the row that makes the claim.
        "status_note": _unrecognised_status_note(record),
        # ``href`` is None for a ref the corpus cannot name — an id or a bare
        # uuid left behind by a deleted or never-created ticket. Such a ref
        # linked to ``/tickets/<ref>`` is a link to a 404, and § 03's own lede
        # promises each row "names the live blocker holding it", which a dead
        # link does not. The epic map already draws the same dangling reference
        # as an unlinked "names no known ticket" node; this is that treatment,
        # in the one other place a ref reaches the page.
        "blockers": [
            {
                "id": blocker.ref,
                "title": blocker.title or "",
                "status": blocker.status or "",
                "discharged": blocker.discharged,
                "unresolvable": blocker.kind == "unresolvable",
                "href": (
                    None if blocker.kind == "unresolvable"
                    else "/tickets/%s" % blocker.ref
                ),
            }
            for blocker in row.blockers
        ],
    }


def _rank_key(entry: dict) -> tuple:
    """Points descending, then id — the one ordering every list here uses.

    Applied *across* bands rather than within them. The bands still decide
    which list a record lands in; they no longer decide the order inside it,
    because a band boundary in the middle of a points-sorted run is an
    inversion the reader can see (band E's top row outscored eight band-D rows
    on the largest real corpus) and cannot explain.
    """
    return (-entry["points"], _id_key(entry["id"]))


# ---------------------------------------------------------------------------
# § 02 — epic maps
# ---------------------------------------------------------------------------


def _hover(
    tid: str,
    ctx: ScoreContext,
    items: dict[str, dict],
    offslice: dict | None = None,
) -> dict:
    """The facts a hover card shows, resolved from data already computed.

    Returned FLAT, and merged into every hoverable thing at the top level —
    list rows, frame nodes and child tiles alike. Nesting it under a
    ``preview`` key is what made the first cut of this ship blank chips on
    every node in a frame: the row dicts carried ``status`` at the top level
    and the node dicts carried it one level down, so a single template macro
    read one of them correctly and the other as ``Undefined``, which renders as
    the empty string with no error anywhere. One shape, one macro, no branch.

    Deliberately carries no ticket *body*. The body is a per-request read
    (``load_ticket_body``'s docstring gives the size argument — folding bodies
    into a polled fragment would morph hundreds of KB into the DOM twice a
    minute), so hover shows the classification, which is free, and the modal
    fetches the prose, which is not. Hover therefore costs no request and
    cannot lag behind the pointer.

    ``points`` is the *computed* score from :func:`~.score.score_of`, not a
    frontmatter field — there is no ``points`` key in any corpus. It is the
    same number the ready list prints, which is what lets the card defend a
    row's position without the board having to print a ledger.
    """
    record = items.get(tid) or {}
    on_slice = tid in items
    direct = ctx.direct_of(tid) if on_slice else ()
    onward = ctx.downstream_of(tid) if on_slice else ()
    # An off-board blocker has a status the corpus knows, and it is the single
    # most useful thing the card can say about it: "complete" means the arrow
    # you just hovered is a hold that has already lapsed.
    known = (offslice or {}).get(tid) or {}
    return {
        "status": _text(record.get("status")) or _text(known.get("status")) or "unset",
        "priority": _text(record.get("priority")) or "unset",
        "type": _text(record.get("type")) or "unset",
        "points": score_of(tid, ctx).total if on_slice else None,
        "unblocks": "%d direct / %d downstream" % (len(direct), len(onward)),
    }


def _node(
    tid: str,
    xy: tuple[int, int],
    items: dict[str, dict],
    band_of: dict[str, str],
    offslice: dict,
    *,
    external: bool = False,
    hover: dict | None = None,
) -> dict:
    """One node box: a coordinate, a link, and a label of at most two words.

    The full title travels as ``title`` and is drawn by CSS inside a
    ``<foreignObject>`` the server already sized. It is never measured here —
    the fonts are not bundled, Georgia is what renders, and a box sized to a
    guessed advance is the defect that rule exists to prevent.

    ``state`` and ``border_style`` say what the ticket IS, never where it sits.
    Being external to this epic is already carried by the left-hand column and
    its caption. Most external blockers are on the board, and half of the rest
    are complete — which is the useful word, because it says this arrow's hold
    has already lapsed.
    """
    key = band_of.get(tid, "")
    return {
        # Merged flat, not nested: see :func:`_hover`. Every hoverable dict on
        # this surface answers to the same keys, so one template macro serves
        # a row, a node and a tile without knowing which it has.
        **(hover or {}),
        "id": tid,
        "x": xy[0],
        "y": xy[1],
        "title": _title_of(tid, items, offslice),
        "state": (
            _NODE_STATE.get(key, "on board")
            if tid in items
            else _offslice_state(tid, offslice)
        ),
        "border_style": (
            _BORDER_OF_BAND.get(key, "solid") if tid in items else "ghost"
        ),
        "href": "/tickets/%s" % tid,
        "external": external,
    }


def _frame(
    epic_id: str,
    ctx: ScoreContext,
    items: dict[str, dict],
    band_of: dict[str, str],
    layout_ctx: LayoutContext,
    offslice: dict,
) -> dict:
    """One epic's dependency geometry, or ``None`` when it declares none.

    The frame is drawn only for a group the layout found at least one edge in.
    That gate is the whole answer to the measurement that retired this
    renderer: it drew a dashed box around an unordered list for every group
    with nothing to say, once per group, and those boxes were most of its
    output. Ten of eleven groups now render as a plain child grid instead, and
    the geometry appears exactly where it is not decoration.

    Every coordinate below was computed in :mod:`.epic_layout` and is passed
    through verbatim. Nothing here measures text.
    """
    layout = layout_epic(epic_id, layout_ctx)
    if not layout.elbows:
        return {}

    external_set = set(layout.externals)
    nodes = [
        _node(
            tid,
            layout.pos[tid],
            items,
            band_of,
            offslice,
            external=tid in external_set,
            hover=_hover(tid, ctx, items, offslice),
        )
        for tid in sorted(layout.pos, key=_id_key)
    ]
    return {
        "verdict": layout.verdict,
        "constrained": layout.constrained,
        "total": layout.total,
        "width": layout.width,
        "height": layout.height,
        "marker_id": layout.marker_id,
        # Per-epic, so two frames on one page cannot collide, and stable, so
        # the pan container's scrollLeft survives a swap.
        "pan_id": "epic-pan-%s" % epic_id,
        "pool_box": layout.pool_box,
        # Where the enclosure's own two-word label sits. Computed here because
        # it is geometry, and because the inset it depends on is a layout
        # constant the template has no business knowing.
        "pool_label": (
            {"x": layout.pool_box[0] + POOL_INSET, "y": layout.pool_box[1] + 20}
            if layout.pool_box
            else None
        ),
        # The externals column's own heading, in the caption band the layout
        # already reserves above the first node row.
        "ext_label": (
            {"x": PAD, "y": PAD + SPINE_HEAD_H - 12} if layout.externals else None
        ),
        "externals": layout.externals,
        "elbows": layout.elbows,
        "nodes": nodes,
    }


def _epic(
    epic_id: str,
    children: list[str],
    ctx: ScoreContext,
    items: dict[str, dict],
    band_of: dict[str, str],
    layout_ctx: LayoutContext,
    active: frozenset[str],
    offslice: dict,
) -> dict:
    """One epic: its head line, its counts, and the map behind its disclosure.

    Renders whether or not the container is on the board. A group whose parent
    sits off the slice used to be routed to a separate tail table with a
    different state vocabulary, which is how the same off-slice ticket came to
    read ``complete`` in a frame and ``off board`` in the tail. One builder,
    one vocabulary, no drift — and the same rule now covers the frame and the
    grid, which are two renderings of one child list rather than two lists.

    A completed head with live children is not an error to hide. It is a
    grooming finding, and the head line says so rather than burying it.
    """
    # "On the board" means the head is in the board's ACTIVE set, which is
    # ``item_order`` and neither of the two nearby sets that look like it.
    # ``items`` is wider: the snapshot backfills a closed head into it so a
    # heading has a record to render with. The band partition is wider still,
    # because it runs over ``items`` and routes those backfilled heads into
    # band H. Testing either one called a completed parent on-board.
    on_board = epic_id in active
    record = items.get(epic_id)
    kids = sorted(children, key=_id_key)

    grid = [
        {
            # Same flat merge the nodes get, for the same reason.
            **_hover(tid, ctx, items, offslice),
            "id": tid,
            "title": _title_of(tid, items, offslice),
            "href": "/tickets/%s" % tid,
            "state": (
                _NODE_STATE.get(band_of[tid], "ready")
                if tid in band_of
                else _offslice_state(tid, offslice)
            ),
            "border_style": _BORDER_OF_BAND.get(band_of.get(tid, ""), "ghost"),
        }
        for tid in kids
    ]

    ready = sum(1 for tid in kids if band_of.get(tid) in _READY_KEYS)
    held = sum(1 for tid in kids if band_of.get(tid) == "G")
    deferred = sum(1 for tid in kids if band_of.get(tid) == "F")

    # The summary an operator reads while the epic is closed, and therefore the
    # only thing that can make them open it. Zero-valued clauses are dropped
    # rather than printed: "0 held" on nine of eleven groups is noise that
    # makes the two groups which DO hold something harder to spot.
    parts = []
    if ready:
        parts.append("%d ready" % ready)
    if held:
        parts.append("%d held" % held)
    if deferred:
        parts.append("%d deferred" % deferred)
    if not parts:
        parts.append("nothing startable")

    return {
        # The epic head is hoverable and clickable like any other ticket, so it
        # gets the same flat payload every row, node and tile gets. Merged
        # first, so the explicit keys below win where they overlap: ``status``
        # here resolves a backfilled head's own word, which is finer than the
        # generic lookup.
        **_hover(epic_id, ctx, items, offslice),
        "id": epic_id,
        "title": _title_of(epic_id, items, offslice),
        "href": "/tickets/%s" % epic_id,
        # Id-stable and position-independent, so the client's open-state store
        # reattaches to the same epic after the list reorders.
        "details_id": "nav-epic-%s" % epic_id,
        "on_board": on_board,
        # The one- or two-word disposition, matching the vocabulary a node box
        # and a child tile use.
        "state": "epic",
        # The backfilled record's own status when there is one, because it is
        # the ticket's real status; the corpus resolution only when there is
        # not. Keyed on the record rather than on ``on_board`` so an off-board
        # head still reports "complete" rather than a coarser fallback.
        "status": (
            (_text(record.get("status")) or "unset")
            if record is not None
            else _offslice_state(epic_id, offslice)
        ),
        "count": len(kids),
        "ready": ready,
        "held": held,
        "deferred": deferred,
        "summary": " · ".join(parts),
        "children": grid,
        "frame": _frame(epic_id, ctx, items, band_of, layout_ctx, offslice),
    }


# ---------------------------------------------------------------------------
# Page partition
# ---------------------------------------------------------------------------


def _tail_panel_of(row: bands_mod.Row, order_ids: frozenset[str] | None) -> str:
    """Which tail panel a non-ready, non-blocked record belongs in.

    The order of the tests is the order ``bands._RULES`` applies, and that is
    the whole correctness argument: band H is assigned off-board-first, so a
    record that is both absent from the ordering and ``status: new`` is banded
    for the former. A panel split that tested ``new`` first would file it under
    the reason the band did not use, and the label on the panel would be a
    claim the banding does not make.

    The final arm is a real destination rather than a fallthrough. A record
    whose status or priority is outside cortex's vocabulary reaches it —
    consumer repos run their own — and saying so is better than sweeping it
    into "off the board", which would be false about where it sits.
    """
    status = _text(row.status).lower()
    if status == "deferred":
        return "deferred"
    if order_ids is not None and row.id not in order_ids:
        return "offboard"
    if status == "new":
        return "untriaged"
    return "unruled"


def _partition(
    banded: bands_mod.Bands,
    items: dict[str, dict],
    child_ids: frozenset[str],
    head_ids: frozenset[str],
    ctx: ScoreContext,
    order_ids: frozenset[str] | None,
) -> dict:
    """Route every banded record to the one place on the page it appears.

    The rule the operator set: a ticket that belongs to an epic is seen inside
    that epic's map and nowhere else. So the ready and blocked lists are
    *loose* records only, and the epic section is where their children live.

    Two things decide "appears elsewhere", and both are the *rendered* sets
    rather than a proxy for them:

    ``head_ids`` is what § 02 actually draws a heading for, which is the parent
    map — **not** band E′. Those two differ in both directions and each
    difference was a live bug. A ticket typed ``feature`` that another ticket
    names as its parent heads a group but is not in band E′, so keying on the
    band rendered it as a § 02 heading *and* as a § 01 row. An epic whose
    children have all completed is in band E′ but heads no group, so keying on
    the band skipped it from every list while § 02 had nothing to show — it
    left the page entirely, and the reconciliation still said ``ok``.

    Widening detection past ``type: epic`` was deliberate (a de-facto epic
    typed ``chore`` has children and must group them), so the fix is to ask the
    rendered set rather than to narrow detection back.

    The final ``else`` is a catch-all, mirroring the ``_always`` rule that makes
    :mod:`.bands` total. Without it a band key belonging to none of the three
    destinations silently vanishes, which is the exact failure the footer
    exists to make visible — and a footer that cannot see it is decoration.

    Returns the lists plus the ids consumed and the heads counted, so the caller
    can prove the partition covered the slice without recounting it from a
    different source.
    """
    ready: list[dict] = []
    blocked: list[dict] = []
    tail_rows: dict[str, list[dict]] = {key: [] for key, _l, _g in _TAIL_PANELS}
    seen: set[str] = set()
    heads = 0

    for band in banded:
        for row in band.rows:
            seen.add(row.id)
            # Drawn as a § 02 heading, so never also a row.
            if row.id in head_ids:
                heads += 1
                continue
            # A child is drawn in its epic's map, never in a flat list.
            if row.id in child_ids:
                continue
            entry = _row(row, band.key, items, ctx)
            if band.key in _READY_KEYS:
                ready.append(entry)
            elif band.key == "G":
                blocked.append(entry)
            else:
                # Everything else is tail, and the panel is chosen from the
                # record rather than from its band letter. A container with no
                # live children lands here too, which is where it belongs: it
                # is not startable, not held, and not a group anyone can open.
                # Visible beats silently absent.
                tail_rows[_tail_panel_of(row, order_ids)].append(entry)

    ready.sort(key=_rank_key)
    blocked.sort(key=_rank_key)
    for rows in tail_rows.values():
        rows.sort(key=_rank_key)

    tail = [
        {
            "key": key,
            "label": label,
            "gloss": gloss,
            "slug": "nav-tail-%s" % key,
            "count": len(tail_rows[key]),
            "rows": tail_rows[key],
        }
        for key, label, gloss in _TAIL_PANELS
        if tail_rows[key]
    ]
    return {
        "ready": ready,
        "blocked": blocked,
        "tail": tail,
        "seen": frozenset(seen),
        "heads": heads,
    }


def _loose_rows(page: dict) -> list[dict]:
    """Every row drawn in a flat list — ready, blocked, and every tail panel.

    The population the filter acts on, and the reason it is a list rather than
    a count: the filter's chips are built from the values these rows carry.
    Epic children are deliberately absent. They are drawn inside a map whose
    geometry is computed server-side, and hiding a node from a frame would
    leave its arrows pointing at nothing.
    """
    return [
        *page["ready"],
        *page["blocked"],
        *(row for panel in page["tail"] for row in panel["rows"]),
    ]


def _facets(rows: list[dict]) -> list[dict]:
    """The ``type`` values the loose lists actually contain, with their counts.

    Derived from the rows on this page rather than from a fixed vocabulary,
    because ``type`` is an open field: a hardcoded feature/bug/chore strip
    offers a consumer repo three filters that match nothing while hiding the
    two values it does use. Commonest first, so the chip that shortens the
    longest list is the leftmost one.
    """
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["type"]] = counts.get(row["type"], 0) + 1
    return [
        {"value": value, "count": counts[value]}
        for value in sorted(counts, key=lambda value: (-counts[value], value))
    ]


def _cycles(graph: Any, items: dict[str, dict]) -> list[dict]:
    """Dependency cycles, as printable rings.

    The graph has always detected these — Tarjan's SCC, on every poll. That is
    the one outcome worse than not looking: a corpus where #a blocks #b blocks
    #a is a defect no ranking can resolve, both tickets sit held forever, and
    the board's own explanation for each ("waiting on a live blocker") is true
    and useless.

    Empty on a healthy corpus, and the page prints nothing at all then.
    """
    return [
        {
            "refs": [
                {"id": tid, "title": _title_of(tid, items), "href": "/tickets/%s" % tid}
                for tid in ring
            ]
        }
        for ring in getattr(graph, "cycles", []) or []
    ]


# ---------------------------------------------------------------------------
# Surface A
# ---------------------------------------------------------------------------


def _empty_navigator(state: object) -> dict:
    """A schema-complete view-model with nothing in it.

    Every key the template touches is present and falsy. The alternative —
    letting the template guard each access — is how a surface ends up rendering
    a blank page instead of saying which of "never polled" and "empty corpus"
    it is looking at.
    """
    return {
        "available": False,
        "backend": _backend(state),
        "stale": False,
        "polled_ts": "",
        "as_of": "",
        "slice_total": 0,
        "ready": [],
        "blocked": [],
        "held_total": 0,
        "held_inside_epics": 0,
        "epics": [],
        "epic_children": 0,
        "mapped_epics": 0,
        "tail": [],
        "facets": [],
        "loose_total": 0,
        "cycles": [],
        "corpus": None,
        "recon": None,
    }


def _navigator_model(state: object) -> dict:
    """Build the navigator — "what is on this board, and how is it structured".

    Args:
        state: The dashboard state. Only ``backlog_snapshot`` and
            ``backlog_backend`` are read.

    Returns:
        A view-model whose every key is present whether or not there is a
        snapshot. ``available`` is the single flag a template branches on.
    """
    snapshot = _snapshot(state)
    if snapshot is None:
        return _empty_navigator(state)

    items, graph, ctx, parents = _context(snapshot)
    offslice = _offslice_of(snapshot)
    banded = bands_mod.partition(items, ctx, item_order=snapshot.get("item_order"))
    band_of = {row.id: band.key for band in banded for row in band.rows}
    active = frozenset(str(tid) for tid in (snapshot.get("item_order") or []))

    child_ids = frozenset(tid for kids in parents.values() for tid in kids)
    # What the epic section actually draws a heading for. Not band E′ — see
    # _partition.
    head_ids = frozenset(parents)
    # Mirrors ``bands.partition``'s own reading of the field to the letter: an
    # absent or empty ``item_order`` is "this snapshot has no ordering", under
    # which every record is on-board. Passing the bare frozenset instead would
    # make an orderless snapshot file its entire tail under "off-board".
    order_ids = active if snapshot.get("item_order") else None
    page = _partition(banded, items, child_ids, head_ids, ctx, order_ids)

    layout_ctx = LayoutContext(
        children=parents,
        live_edges=graph.live,
        discharged_edges=graph.discharged,
    )
    # Startable groups first, then largest first.
    #
    # Size alone put a group with five deferred children above four groups that
    # had ready work, because ``count`` dominated the key — a group nobody can
    # start outranking every group somebody can, on the strength of being big.
    # ``ready`` is the count of children in a startable band, so the leading
    # term is "does this group offer anything today", which is the question the
    # section is read to answer. Held-only groups demote by the same term and
    # for the same reason: their summary already says "2 held".
    #
    # Within each half, largest first — the epic holding nine children is the
    # one a reader came for, and burying it under a two-child group because its
    # id sorts earlier is an ordering with no claim behind it. Ties break on
    # how much of the group is startable, then on id, so the order is total and
    # stable.
    epics = [
        _epic(epic_id, parents[epic_id], ctx, items, band_of, layout_ctx, active, offslice)
        for epic_id in sorted(parents, key=_id_key)
    ]
    epics.sort(key=lambda e: (0 if e["ready"] else 1, -e["count"], -e["ready"], _id_key(e["id"])))

    # The half of the board the eleven bands cannot see. Deliberately NOT
    # summed into a repo total: the snapshot counts active files and archived
    # files and nothing else — a ticket closed in place is in neither, and on
    # a real corpus that is several hundred of them.
    counts = snapshot.get("counts") or {}

    return {
        "available": True,
        "backend": _backend(state),
        "stale": bool(snapshot.get("stale")),
        "polled_ts": _text(snapshot.get("polled_ts")),
        # The corpus's own "today". Printed because the staleness term is
        # measured against it rather than against the wall clock, and a reader
        # comparing a "3 weeks untouched" row to the actual date would
        # otherwise conclude the board was wrong.
        "as_of": ctx.as_of,
        "slice_total": banded.total,
        "ready": page["ready"],
        "blocked": page["blocked"],
        # Every held record on the board, including the ones drawn inside an
        # epic map rather than listed in the blocked section.
        "held_total": sum(1 for key in band_of.values() if key == "G"),
        # The difference between the two, which is the fact the blocked section
        # used to render an entire empty section to state. A board whose held
        # work all sits inside epics has nothing to list and is not unblocked;
        # that sentence belongs on the epic section, where the records are, and
        # a heading over an empty body is not how to say it.
        "held_inside_epics": sum(1 for key in band_of.values() if key == "G")
        - len(page["blocked"]),
        "epics": epics,
        "epic_children": len(child_ids),
        # How many groups have a dependency map to draw at all. Printed once in
        # the section lede so no group has to carry the explanation itself.
        "mapped_epics": sum(1 for epic in epics if epic["frame"]),
        "tail": page["tail"],
        # The filter's vocabulary and its denominator, both measured off the
        # rows this render produced so the control can never offer a value the
        # page does not contain.
        "facets": _facets(_loose_rows(page)),
        "loose_total": len(_loose_rows(page)),
        "cycles": _cycles(graph, items),
        "corpus": {"archived": int(counts.get("archived") or 0)},
        # The completeness claim, and a real one. The comparand is the set of
        # ids the partition actually covered against the slice it was handed —
        # not the sum of the band counts against the sum of the band counts,
        # which is an arithmetic identity that cannot fail and which this page
        # printed as a guarantee for as long as it had one.
        "recon": {
            "ready": len(page["ready"]),
            "blocked": len(page["blocked"]),
            "children": len(child_ids),
            "heads": page["heads"],
            "tail": sum(panel["count"] for panel in page["tail"]),
            "total": banded.total,
            "ok": len(page["seen"]) == banded.total
            and len(banded.covered_ids) == len(items),
        },
    }


def scope_links(model: object, suffix: str) -> object:
    """Append *suffix* to every ``href`` in a view-model, recursively.

    Applied as a final pass over the assembled model rather than threaded
    through the many places that build a ticket URL, because the failure mode
    of threading is silent: a missed site still renders a working-looking link,
    it just points at the wrong repository's ticket. One walk cannot miss a
    site, and a new href added later is covered without anyone remembering to.

    Templates cannot do this job at all. The row, epic and frame templates are
    macro libraries imported without ``with context``, so a page-level
    ``repo_query`` is Undefined inside them and renders as the empty string —
    the same wrong link, with no error anywhere.

    Every href in these models is an internal ticket route, so there is nothing
    here that a repo scope would be wrong for. A no-op for the empty suffix,
    which is the single-repo case.
    """
    if not suffix:
        return model
    if isinstance(model, dict):
        return {
            key: (
                value + suffix
                if key == "href" and isinstance(value, str) and value
                else scope_links(value, suffix)
            )
            for key, value in model.items()
        }
    if isinstance(model, list):
        return [scope_links(item, suffix) for item in model]
    return model


def build_navigator(
    state: object, root: object = None, *, link_suffix: str = ""
) -> dict:
    """The navigator's view-model, with every href scoped to the caller's repo.

    ``link_suffix`` is the query string identifying which tracked repository
    this render belongs to (empty when the process serves one, which is the
    common case and leaves every URL byte-identical). Applied by
    :func:`scope_links` as a single pass over the finished model — see there
    for why this is not threaded through the builders.
    """
    return scope_links(_navigator_model(state), link_suffix)
