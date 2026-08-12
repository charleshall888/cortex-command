"""Surface B geometry: every coordinate in one epic's dependency frame.

This module computes and returns numbers. It emits no markup, and the
template that consumes it does no arithmetic — a rendered frame's height is
already known on the server, so a 30s htmx morph-swap cannot reflow it.
JS never computes a coordinate here; there is no client-side layout engine.

The load-bearing distinction, and the reason this file exists at all:

    **Only a node touched by an intra-epic edge gets a wave.**

Everything else lands in the *undeclared pool*. That is not an error path.
On the development corpus 10 of 11 epics have zero intra-epic edges, so the
pool-only frame is the designed output for the common case: no spine, no
arrows, no implied sequence — the children sit inside one dashed enclosure
and the frame's verdict line says the ordering was never declared. The
largest epic (9 children, 2 intra-epic edges) is the same grammar with a
small spine and the remaining children still pooled. An epic that *does*
declare an order and one that never did differ only in their counts, which
is what makes the absence readable rather than invisible.

Three failure modes from the prototype this replaces are fixed here, and
each is cheap to reintroduce:

* **Marker ids are per-epic** (``arw-e344``). The prototype emitted
  ``id="ah"`` once per frame and every ``url(#ah)`` in the document resolved
  to the first definition, so the moment the top frame left the DOM on a
  morph-swap every remaining frame lost its arrowheads. Arrowheads are the
  only channel that says which way an edge points.
* **Every ``max()`` over a possibly-empty collection takes ``default=``.**
  An epic with no spine and an epic with no children are both real inputs.
* **Externals are placed, not implied.** A blocker living outside the epic
  gets a real position in a left-hand column and a real elbow, rather than
  a text stub whose width would have to be guessed from a font metric this
  project does not bundle.

Coordinates are integers throughout. Floats would render as ``34.0`` on one
platform and ``34`` on another, and byte-identical re-render under an
unchanged poll is a requirement of this surface, not a nicety.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

# --- geometry constants ----------------------------------------------------
#
# The seven names below are fixed by the build contract. NW/NH are the node
# box; COL_GAP is the channel an elbow routes through between spine columns;
# PANEL_W is the widest a frame may get before its pool wraps beneath the
# spine instead of sitting beside it.
NW, NH, COL_GAP, ROW_GAP, PAD, POOL_COLS, PANEL_W = 244, 68, 78, 16, 26, 4, 1120

# Pool rows are taller than spine rows because each pool node carries a label
# above it; the pool's own inset and column gap are narrower than the spine's
# because nothing routes between pool columns — there are no edges in there.
POOL_ROW_GAP = 26
POOL_INSET = 16
POOL_COL_GAP = 20

# Reserved caption bands: the spine's heading sits above the first spine row,
# and the pool enclosure's label sits inside its own box above the first row.
SPINE_HEAD_H = 34
POOL_HEAD_H = 30
POOL_FOOT_H = 8

# Clear space between the spine's right edge and a pool placed beside it.
SPINE_POOL_GAP = 44

# A frame narrower than this reads as a dropped panel rather than a small
# epic, and a frame with no drawable content at all still needs a positive
# viewBox. Both floors are applied unconditionally.
MIN_FRAME_W = 320
FRAME_FOOT_H = 30

# The arrowhead is drawn at the path's end, so the path stops short of the
# target node's left edge by this much or the marker overlaps the box.
ARROW_INSET = 8

# Edge kinds carried on every elbow dict. "live" is a declared constraint
# between two children; "discharged" is one whose blocker is already closed
# (a lapsed hold — it is drawn as a ghost, and deliberately does NOT create a
# spine, because it constrains nothing); "external" points in from outside.
EDGE_LIVE = "live"
EDGE_DISCHARGED = "discharged"
EDGE_EXTERNAL = "external"


@dataclass(frozen=True)
class LayoutContext:
    """The slice of graph truth one frame needs, and nothing else.

    ``view.py`` builds this; ``graph.py``'s ``Graph`` maps onto it directly
    (``Graph.live`` → :attr:`live_edges`, ``Graph.discharged`` →
    :attr:`discharged_edges`). It is deliberately not the ``Graph`` itself:
    an epic's children come from the snapshot's epic map, not the graph, and
    this module should be constructible from a literal in a test.

    Attributes:
        children: Epic id → its child ids. **String-keyed.** The snapshot's
            epic map carries child ids as ints while ``items`` is str-keyed
            — the trap documented in ``ticket_feed``'s module docstring — so
            child ids are stringified on read here, but the *keys* are the
            caller's responsibility to normalise.
        live_edges: ``(blocker, blocked)`` pairs that still constrain.
        discharged_edges: ``(blocker, blocked)`` pairs whose blocker has
            already closed. Rendered, never load-bearing.
    """

    children: Mapping[str, Sequence[str]]
    live_edges: Sequence[tuple[str, str]] = ()
    discharged_edges: Sequence[tuple[str, str]] = ()


@dataclass(frozen=True)
class EpicLayout:
    """Every number one epic frame needs. No markup, no CSS, no classes.

    Attributes:
        pos: Node id → ``(x, y)`` of its box's top-left corner. Covers the
            epic's children **and** its external blockers, because the
            template has no other channel through which to place them.
        spine: Children touched by a live intra-epic edge, ordered by
            ``(wave, id)`` — i.e. reading order down each column.
        pool: Children no sibling constrains, in id order.
        pool_box: ``(x, y, w, h)`` of the dashed enclosure, or ``None`` when
            the pool is empty. ``None`` rather than a zero-size tuple so a
            template that guards on it draws nothing instead of drawing a
            degenerate rectangle at the origin.
        wrapped: True when the pool was placed *beneath* an existing spine
            rather than beside it. Decided here from measured widths.
        ncols: Number of spine columns; 0 when nothing is constrained.
        width: viewBox width. Strictly positive for every input.
        height: viewBox height. Strictly positive for every input.
        externals: Blocker ids referenced by a child but living outside this
            epic, in id order. Every one is in :attr:`pos`.
        elbows: One dict per drawn edge — ``kind``, ``src``, ``dst``,
            ``path`` (an SVG path ``d`` string). Both endpoints of every
            elbow are always in :attr:`pos`.
        marker_id: This frame's arrowhead marker id, unique per epic.
        verdict: The computed one-line ordering claim printed above the
            frame. The explanatory paragraph is printed once in the section
            lede, never per epic.
        constrained: Children touched by a live intra-epic edge.
        total: Children in this epic.
    """

    pos: dict[str, tuple[int, int]]
    spine: list[str]
    pool: list[str]
    pool_box: tuple[int, int, int, int] | None
    wrapped: bool
    ncols: int
    width: int
    height: int
    externals: list[str]
    elbows: list[dict]
    marker_id: str
    verdict: str
    constrained: int
    total: int


def _sort_key(node_id: str) -> tuple[int, int, str]:
    """Order ids numerically when they are numbers, lexically when not.

    Ticket ids are digit strings, but a ``blocked_by`` ref is an open field:
    the feed's own resolver already recognises UUID-shaped and free-text
    refs, either of which reaches an external blocker slot here. A bare
    ``key=int`` would raise on the first one, so numbers sort before
    non-numbers and non-numbers sort among themselves by text.
    """
    text = str(node_id)
    if text.isdigit():
        return (0, int(text), "")
    return (1, 0, text)


def _normalise_edges(edges: Iterable[Sequence[str]]) -> list[tuple[str, str]]:
    """Stringify, drop self-loops, dedupe, and sort an edge list.

    Sorting is not cosmetic: elbow order is emission order, and this surface
    must re-render byte-identically when nothing changed. Self-loops are
    dropped because a node cannot precede itself — kept, one would relax on
    every pass of the wave loop and burn the whole iteration bound.
    """
    seen = {
        (str(a), str(b))
        for a, b in edges
        if str(a) != str(b)
    }
    return sorted(seen, key=lambda e: (_sort_key(e[0]), _sort_key(e[1])))


def intra_waves(
    children: Iterable[str],
    edges: Iterable[Sequence[str]],
) -> tuple[dict[str, int], list[tuple[str, str]]]:
    """Layer the children by longest path over intra-epic edges only.

    Args:
        children: The epic's child ids.
        edges: Candidate ``(blocker, blocked)`` pairs from the whole graph;
            everything with an endpoint outside *children* is discarded here
            rather than by the caller, so the caller cannot forget to.

    Returns:
        ``(wave, sub)`` — the wave index of each **touched** node, and the
        intra-epic edge subset in deterministic order.

    Only nodes that an edge touches appear in ``wave``. A child no sibling
    constrains is absent from the mapping entirely, which is how
    :func:`layout_epic` tells spine from pool; returning ``0`` for it would
    silently claim it belongs in the first column of a declared sequence.

    Layering is iterative relaxation (``wave[b] = max(wave[b], wave[a]+1)``)
    bounded by the node count. The corpus holds no cycles and the deepest
    chain is 2, but a cycle must terminate rather than hang, and the bound —
    not a visited-set — is what guarantees that: one full pass per node is
    the most a longest-path relaxation can need on an acyclic graph, so
    hitting the bound is itself the cycle signal and the partial layering it
    leaves is still drawable.
    """
    kids = {str(child) for child in children}
    sub = [
        (a, b) for a, b in _normalise_edges(edges) if a in kids and b in kids
    ]

    touched: set[str] = set()
    for a, b in sub:
        touched.add(a)
        touched.add(b)

    wave = dict.fromkeys(sorted(touched, key=_sort_key), 0)
    for _ in range(len(touched) + 1):
        changed = False
        for a, b in sub:
            if wave[b] < wave[a] + 1:
                wave[b] = wave[a] + 1
                changed = True
        if not changed:
            break
    return wave, sub


def elbow(x1: int, y1: int, x2: int, y2: int, lane: int) -> str:
    """Return the SVG path ``d`` for one edge: out, across, down, in.

    A right-angled elbow whose vertical run sits in *lane* — an x the caller
    has established is clear of every node box. The caller owns that choice
    because only the caller knows the column grid; this function is the
    stringifier.

    ``lane`` used to be derived here as the midpoint between the endpoints,
    and that is the defect this signature exists to prevent. A midpoint is
    only clear when the target sits in the column immediately right of the
    source: for any longer hop it lands *inside* an intervening node box.
    On the development corpus that drew ten edge segments straight through
    node boxes across two of five frames, including three arrows crossing
    the dashed pool enclosure of an epic whose own label says its children
    are unordered. There is no midpoint that is clear in general, so the
    lane is an input.

    The path stops short of the target by :data:`ARROW_INSET` to leave room
    for the arrowhead marker.

    All arithmetic is integer: the same input must produce the same bytes.
    """
    return f"M {x1} {y1} H {lane} V {y2} H {x2 - ARROW_INSET}"


def _pool_width(cols: int) -> int:
    """Width of a pool enclosure *cols* node-columns wide, including inset."""
    if cols <= 0:
        return 0
    return POOL_INSET * 2 + cols * (NW + POOL_COL_GAP) - POOL_COL_GAP


def _ext_lanes(externals: Sequence[str]) -> dict[str, int]:
    """One reserved vertical channel per external blocker, left of the content.

    Externals occupy ``x`` in ``[PAD, PAD + NW]`` and the epic's own content
    starts at ``PAD + NW + COL_GAP``, so the ``COL_GAP`` between them is
    empty by construction and is the only strip on the frame guaranteed to
    stay that way. Each external gets its own x inside it, evenly spaced and
    ordered by the caller's already-sorted list, so the assignment is stable
    across renders.

    Per *external*, not per *edge*: one blocker holding three children draws
    one trunk that forks, which is the true shape of the relationship. Giving
    each edge its own lane would draw three near-parallel verticals saying
    the same thing.
    """
    if not externals:
        return {}
    step = max(1, COL_GAP // (len(externals) + 1))
    return {
        node: PAD + NW + (i + 1) * step for i, node in enumerate(externals)
    }


def _marker_id(epic_id: str) -> str:
    """Return this epic's arrowhead marker id, namespaced and id-safe.

    The namespacing is the whole point (see the module docstring): a shared
    marker id makes every frame after the first depend on the first frame
    staying in the DOM, which on a morph-swapped page it does not. Characters
    an epic id should never contain are folded to ``-`` so the value is
    always a usable HTML id even if the id vocabulary widens.
    """
    safe = "".join(
        ch if (ch.isalnum() or ch in "-_") else "-" for ch in str(epic_id)
    )
    return f"arw-e{safe}"


def _verdict(constrained: int, total: int) -> str:
    """Return the frame's one-line ordering claim.

    Two phrasings, one grammar: the numbers do the work, so an epic with a
    partial spine and an epic with none read as the same kind of statement
    with different counts. Nothing here names an id or a corpus count — every
    number is computed from the epic in hand.
    """
    noun = "child" if total == 1 else "children"
    if constrained == 0:
        return f"NO ORDERING DECLARED — 0 of {total} {noun} constrained by a sibling"
    return (
        f"PARTIAL ORDERING — {constrained} of {total} {noun} "
        "constrained by a sibling"
    )


def layout_epic(epic_id: str, ctx: LayoutContext) -> EpicLayout:
    """Compute every coordinate for one epic frame.

    Args:
        epic_id: The epic whose frame this is. An id with no children yields
            an empty but dimensionally valid frame rather than an error —
            the caller routes small epics to the tail table, and this
            function is not the place to re-litigate that threshold.
        ctx: See :class:`LayoutContext`.

    Returns:
        An :class:`EpicLayout` whose ``width`` and ``height`` are strictly
        positive for every input, including no children, no edges, one
        child, and forty children.
    """
    kids = sorted(
        {str(child) for child in ctx.children.get(str(epic_id), ())},
        key=_sort_key,
    )
    kid_set = set(kids)

    # Waves come from live edges only. A discharged edge is drawn (a lapsed
    # hold is a finding — two tickets on the dev corpus look blocked and are
    # in fact the easiest picks on the board) but it constrains nothing, so
    # it must not conjure a spine out of an epic that never declared one.
    wave, sub = intra_waves(kids, ctx.live_edges)
    spine = sorted(wave, key=lambda node: (wave[node], _sort_key(node)))
    pool = [k for k in kids if k not in wave]

    # An external blocker is any edge head that points *into* this epic from
    # outside it, live or discharged: a hold that has lapsed is exactly as
    # worth drawing as one that has not. Deduped, because one external
    # ticket commonly blocks several children of the same epic.
    ext_live = [
        (a, b)
        for a, b in _normalise_edges(ctx.live_edges)
        if b in kid_set and a not in kid_set
    ]
    ext_discharged = [
        (a, b)
        for a, b in _normalise_edges(ctx.discharged_edges)
        if b in kid_set and a not in kid_set
    ]
    externals = sorted({a for a, _b in ext_live + ext_discharged}, key=_sort_key)

    # Which *pool* children an external blocker points at. The pool is the one
    # region of a frame with no routing gutters between its columns, so an
    # arrow can only reach a pool node cleanly from the left. Hoisting these
    # into the pool's first column below is what makes that approach true by
    # construction rather than true by luck of the id order.
    ext_targets = [
        node
        for node in pool
        if any(b == node for _a, b in ext_live + ext_discharged)
    ]
    if ext_targets:
        held = set(ext_targets)
        pool = ext_targets + [node for node in pool if node not in held]

    pos: dict[str, tuple[int, int]] = {}

    # Externals occupy their own column hard against the frame's left edge,
    # and the epic's own content starts one column further right. Placing
    # them (rather than labelling them at the frame edge) is what lets the
    # width account for them, so the panel never has to reflow to fit a
    # stub whose rendered width we would otherwise be guessing.
    ext_offset = (NW + COL_GAP) if externals else 0
    origin_x = PAD + ext_offset
    for row, node in enumerate(externals):
        pos[node] = (PAD, PAD + SPINE_HEAD_H + row * (NH + ROW_GAP))

    bycol: dict[int, list[str]] = {}
    for node in spine:
        bycol.setdefault(wave[node], []).append(node)
    ncols = max((w + 1 for w in wave.values()), default=0)
    for col in range(ncols):
        for row, node in enumerate(bycol.get(col, [])):
            pos[node] = (
                origin_x + col * (NW + COL_GAP),
                PAD + SPINE_HEAD_H + row * (NH + ROW_GAP),
            )

    tallest_col = max((len(col) for col in bycol.values()), default=0)
    spine_h = tallest_col * (NH + ROW_GAP)
    spine_w = ncols * (NW + COL_GAP) if ncols else 0

    # Where the pool goes is decided HERE, from measured widths, not by CSS
    # and not by JS. The server therefore knows the frame's exact height
    # before it renders, which is what keeps an htmx morph-swap from
    # reflowing the panel under the operator's cursor. Beside the spine if
    # the whole frame still fits the panel; wrapped beneath it otherwise.
    beside_cols = max(1, min(2, len(pool)))
    fits_beside = (
        PAD * 2 + ext_offset + spine_w + SPINE_POOL_GAP + _pool_width(beside_cols)
        <= PANEL_W
    )
    # A pool an external blocker points into cannot sit beside the spine: the
    # only clear approach to a pool node is from the left, and beside-placement
    # puts the entire spine between the external column and the pool's left
    # edge. Dropping the pool below keeps the routing gutter unobstructed.
    beside = bool(ncols) and fits_beside and not ext_targets

    # The pool is the one part of a frame whose width we get to choose, so it
    # is fitted to the panel budget rather than allowed to overrun it. A frame
    # wider than the panel pans horizontally, which is fine when a long spine
    # earns it — but a pool spilling past the edge only because an external
    # blocker column pushed its origin right would make the operator pan for
    # nothing. Measured on the dev corpus this is 3 frames of 11, including
    # the largest. POOL_COLS stays the ceiling; the budget only lowers it.
    fit_cols = (
        PANEL_W - PAD * 2 - ext_offset - POOL_INSET * 2 + POOL_COL_GAP
    ) // (NW + POOL_COL_GAP)
    max_pool_cols = max(1, min(POOL_COLS, fit_cols))

    # The pool fills column-major, and the column count is capped so that the
    # first column is long enough to hold every externally-held child. Both
    # halves of that are one requirement: an external arrow must reach its
    # target without crossing a sibling, the approach is from the left, so the
    # target has to be in column 0. Column-major makes the first column the
    # first `pool_rows` entries, and the hoist above made those the held ones.
    #
    # Always satisfiable — a single column holds every child — so this narrows
    # a frame rather than ever failing to place one. Reading order is not lost:
    # the enclosure's whole claim is that its children have no declared order,
    # and the roster beneath the frame lists them in this same sequence.
    def _cols_for(cols: int) -> int:
        if not ext_targets:
            return cols
        while cols > 1 and -(-len(pool) // cols) < len(ext_targets):
            cols -= 1
        return cols

    if not pool:
        pool_cols, pool_x0, pool_y0, wrapped = 0, 0, 0, False
    elif beside:
        pool_cols, wrapped = beside_cols, False
        pool_x0 = origin_x + spine_w + SPINE_POOL_GAP
        pool_y0 = PAD + 22
    else:
        # No spine at all is the common case, and it is not "wrapped" — there
        # is nothing above the pool to wrap beneath. The flag means "pushed
        # below a spine that would not fit next to it", and a template that
        # explains the placement must only say so when it happened.
        pool_cols = _cols_for(max(1, min(max_pool_cols, len(pool))))
        wrapped = bool(ncols)
        pool_x0 = origin_x
        pool_y0 = PAD + 22 + (spine_h + 40 if ncols else 0)

    pool_box: tuple[int, int, int, int] | None = None
    if pool:
        pool_rows = (len(pool) + pool_cols - 1) // pool_cols
        for i, node in enumerate(pool):
            col, row = i // pool_rows, i % pool_rows
            pos[node] = (
                pool_x0 + POOL_INSET + col * (NW + POOL_COL_GAP),
                pool_y0 + POOL_HEAD_H + row * (NH + POOL_ROW_GAP),
            )
        # Columns actually occupied, which a short last column makes smaller
        # than `pool_cols`: three children over four permitted columns fill
        # three. Sizing the enclosure to the permitted count would draw a
        # dashed box with an empty column inside it.
        used_cols = (len(pool) + pool_rows - 1) // pool_rows
        pool_box = (
            pool_x0,
            pool_y0,
            _pool_width(used_cols),
            POOL_HEAD_H + pool_rows * (NH + POOL_ROW_GAP) + POOL_FOOT_H,
        )

    # Every edge routes its vertical run through a lane the layout knows is
    # empty. Two kinds of lane, because there are two kinds of clear space:
    #
    # * an **external** edge uses its own blocker's reserved channel in the
    #   gutter between the externals column and the epic's content, so a
    #   blocker holding several children draws one trunk that forks;
    # * an **intra-epic** edge uses the ``COL_GAP`` gutter immediately left of
    #   its target's spine column, which is the strip that gap exists for.
    #
    # Neither is the midpoint between the endpoints. See :func:`elbow`.
    lane_of_ext = _ext_lanes(externals)

    def _lane(src: str, dst: str) -> int:
        if src in lane_of_ext:
            return lane_of_ext[src]
        col = wave.get(dst, 0)
        # Clamped so a target in column 0 — which no intra-epic edge can have,
        # every column-0 node being unconstrained — could not route off-canvas
        # if one ever arrived.
        return max(PAD, origin_x + col * (NW + COL_GAP) - COL_GAP // 2)

    # Elbows are emitted in a fixed order — live, then discharged, then
    # external — and each group is already sorted, so two renders of the
    # same data produce the same path list in the same order.
    elbows: list[dict] = []
    for kind, pairs in (
        (EDGE_LIVE, sub),
        (EDGE_DISCHARGED, [
            (a, b)
            for a, b in _normalise_edges(ctx.discharged_edges)
            if a in kid_set and b in kid_set
        ]),
        (EDGE_EXTERNAL, ext_live),
        (EDGE_DISCHARGED, ext_discharged),
    ):
        for a, b in pairs:
            # Every endpoint is placed by construction: intra edges are
            # filtered to children and externals were just positioned. The
            # guard is here so a caller that hands us an edge we did not
            # filter loses one arrow rather than raising mid-render.
            if a not in pos or b not in pos:
                continue
            ax, ay = pos[a]
            bx, by = pos[b]
            elbows.append({
                "kind": kind,
                "src": a,
                "dst": b,
                "path": elbow(
                    ax + NW, ay + NH // 2, bx, by + NH // 2, _lane(a, b)
                ),
            })

    # Extents. Every max() below takes an explicit default because each of
    # these collections is empty in a shape the corpus actually contains.
    right = max(
        origin_x + spine_w,
        (pool_box[0] + pool_box[2]) if pool_box else 0,
        (PAD + NW) if externals else 0,
        MIN_FRAME_W,
    )
    ext_h = len(externals) * (NH + ROW_GAP)
    bottom = max(
        PAD + SPINE_HEAD_H + spine_h,
        PAD + SPINE_HEAD_H + ext_h,
        (pool_box[1] + pool_box[3]) if pool_box else 0,
    )

    return EpicLayout(
        pos=pos,
        spine=spine,
        pool=pool,
        pool_box=pool_box,
        wrapped=wrapped,
        ncols=ncols,
        width=int(right + PAD),
        height=int(bottom + FRAME_FOOT_H),
        externals=externals,
        elbows=elbows,
        marker_id=_marker_id(epic_id),
        verdict=_verdict(len(spine), len(kids)),
        constrained=len(spine),
        total=len(kids),
    )
