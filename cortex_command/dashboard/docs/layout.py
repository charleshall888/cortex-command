"""Docs view geometry: the constitution ladder and the neighbourhood strip.

Both functions return a :class:`model.MapLayout` and nothing else — no
markup, no CSS classes beyond the words the model already names, and every
coordinate an ``int`` so an unchanged corpus re-renders byte-identically.
The template draws what it is handed and does no arithmetic. This is the
same contract ``backlog/epic_layout.py`` holds, and the three disciplines it
learned the hard way are kept here: every ``max()`` over a possibly-empty
collection takes ``default=``, arrowhead marker ids are per frame, and an
edge's vertical run always sits in a *lane* the layout knows is clear of
every box.

The ladder
----------

Four fixed columns, assigned by document kind and never by longest path::

    constitution | root + policy + config + readme | areas + glossary | ADRs

An ADR is placed exactly once, on a *shelf* under the first governing
non-ADR doc (index order) that cites it. The shelf owner's own box is
pulled down to the top of its shelf so the row reads "this doc, and the
decisions it leans on". ADRs no doc cites sit in a dashed pool at the foot
of the column — the epic frame's undeclared-pool grammar, reused so absence
reads as a finding. Long shelves collapse to :data:`SHELF_MAX` chips plus a
``more`` label whose href lifts the cap for that shelf; the pool likewise
under the ``expand`` key ``pool``.

Routing: an edge whose endpoints sit in adjacent columns is an ``elbow()``
through the gutter between them. An edge spanning two or more columns
cannot use a gutter midpoint — an intervening column of boxes is in the
way — so it climbs its own gutter into a *top channel* above every box,
crosses, and descends the gutter left of its target. One trunk per source:
project.md citing nine ADRs draws one trunk that forks nine times, not nine
near-parallel trunks. Same-column edges (supersedes, ADR → ADR) route in a
reserved gutter right of the last column so they never cross a citation.

Parent edges are stored child → parent in the corpus but *drawn* parent →
child with the arrowhead toward the child, which is also how ``maps-area``
and ``global`` already point; a pair connected by both a Parent line and a
Conditional Loading row therefore draws one blue arrow, not two opposing
ones. ``MapEdge.src``/``dst`` keep the corpus direction so focus classes
stay truthful.

The strip
---------

Three columns — everything pointing at the focus, the focus, everything it
points at — with a node on both sides sitting left as ``both``. All in-edges
share one lane and all out-edges another, so a doc with seventeen citers
draws one bus, not seventeen verticals.
"""

from __future__ import annotations

from collections.abc import Iterable

from cortex_command.dashboard.backlog.epic_layout import ARROW_INSET, elbow
from cortex_command.dashboard.docs.model import (
    MAP_NH,
    MAP_NW,
    Corpus,
    DocEdge,
    DocNode,
    MapBox,
    MapEdge,
    MapLabel,
    MapLayout,
    MapNode,
)

# --- geometry constants ----------------------------------------------------

NW, NH = MAP_NW, MAP_NH
PAD = 26
COL_GAP = 72           # gutter between columns; every lane lives in one
ROW_GAP = 14           # between stacked doc boxes in columns 0–2
ADR_GAP = 8            # between chips on a shelf or in the pool

HEAD_H = 34            # column-label band above the channel
LABEL_DY = 12          # column-label baseline inside the band
TRUNK_STEP = 10        # vertical pitch between trunks in the top channel
CHANNEL_PAD = 12       # clearance below the last trunk before the first box

SHELF_LABEL_H = 20     # label band above a shelf's first chip
SHELF_GAP = 22         # from the last chip of one shelf to the next label
MORE_H = 22            # the ``+N more`` label's row
POOL_GAP = 26          # from the last shelf to the pool box
POOL_INSET = 10        # pool box overhang either side of the chips
POOL_HEAD_H = 30
POOL_FOOT_H = 8

LANE_MARGIN = 12       # first lane's offset from the gutter's left edge
LANE_STEP_MAX = 12     # lanes never spread wider than this
SUP_MARGIN = 22        # first supersedes lane, clear of the pool overhang
SUP_STEP = 10
SUP_TAIL = 8

SHELF_MAX = 6
POOL_MAX = 8
SIDE_MAX = 12

MIN_FRAME_W = 320
FOOT_H = 30

MARKER_LADDER = "arw-docs-ladder"
MARKER_STRIP = "arw-docs-strip"

COLUMN_OF = {
    "constitution": 0,
    "policy": 1, "root": 1, "config": 1, "readme": 1,
    "area": 2, "glossary": 2, "doc": 2,
    "adr": 3,
}
COLUMN_LABELS = ("CONSTITUTION", "ROOT + POLICY", "AREA DOCS", "DECISIONS")
STRUCTURAL = ("parent", "maps-area", "global")


# --- shared helpers ----------------------------------------------------------

def _col_x(col: int) -> int:
    return PAD + col * (NW + COL_GAP)


def _column(node: DocNode) -> int:
    return COLUMN_OF.get(node.kind, 2)


def _live_edges(corpus: Corpus) -> list[DocEdge]:
    """Corpus edges with two placed endpoints: no dangling, no self-cites."""
    nodes = corpus.nodes
    return [
        e for e in corpus.edges
        if not e.dangling and e.src in nodes and e.dst in nodes and e.src != e.dst
    ]


def _lanes(x0: int, keys: Iterable[str]) -> dict[str, int]:
    """One x per key inside a COL_GAP-wide gutter starting at *x0*.

    Evenly spaced from the gutter's left margin, never wider than
    :data:`LANE_STEP_MAX` apart, and never past the right margin: the
    right-hand column's pool box overhangs the gutter by
    :data:`POOL_INSET`, and a lane must stay clear of it.
    """
    keys = list(keys)
    if not keys:
        return {}
    usable = COL_GAP - 2 * LANE_MARGIN
    step = max(1, min(LANE_STEP_MAX, usable // len(keys)))
    return {k: x0 + LANE_MARGIN + i * step for i, k in enumerate(keys)}


def _route(
    ax: int, ay: int, acol: int,
    bx: int, by: int, bcol: int,
    lane_of: dict[tuple[int, str], int],
    trunk_y: dict[str, int],
    key: str,
) -> str:
    """SVG ``d`` from box A to box B whose vertical runs sit in known lanes.

    *lane_of* is keyed by ``(gutter, key)`` where gutter ``g`` is the strip
    right of column ``g``; *trunk_y* by *key*. Every case ends with a
    horizontal into the target so the arrowhead marker sits flat:

    * adjacent, rightward: ``elbow()`` through gutter ``acol``;
    * two or more columns rightward: up gutter ``acol`` to the trunk,
      across the channel, down gutter ``bcol-1``;
    * same column: out the right side, down the gutter right of the
      column, back in to the target's right edge;
    * leftward: the mirror images, entering the target's right edge.
    """
    amid, bmid = ay + NH // 2, by + NH // 2
    dc = bcol - acol
    if dc == 1:
        return elbow(ax + NW, amid, bx, bmid, lane_of[(acol, key)])
    if dc >= 2:
        return (
            f"M {ax + NW} {amid} H {lane_of[(acol, key)]} V {trunk_y[key]} "
            f"H {lane_of[(bcol - 1, key)]} V {bmid} H {bx - ARROW_INSET}"
        )
    if dc == 0:
        return (
            f"M {ax + NW} {amid} H {lane_of[(acol, key)]} V {bmid} "
            f"H {bx + NW + ARROW_INSET}"
        )
    if dc == -1:
        return (
            f"M {ax} {amid} H {lane_of[(bcol, key)]} V {bmid} "
            f"H {bx + NW + ARROW_INSET}"
        )
    return (
        f"M {ax} {amid} H {lane_of[(acol - 1, key)]} V {trunk_y[key]} "
        f"H {lane_of[(bcol, key)]} V {bmid} H {bx + NW + ARROW_INSET}"
    )


def _gutters_used(acol: int, bcol: int) -> tuple[int, ...]:
    """Which gutters a route from column *acol* to *bcol* runs a vertical in."""
    dc = bcol - acol
    if dc == 1 or dc == 0:
        return (acol,)
    if dc >= 2:
        return (acol, bcol - 1)
    if dc == -1:
        return (bcol,)
    return (acol - 1, bcol)


def _node_focus(path: str, focus: str | None, ins: set[str], outs: set[str]) -> str:
    if focus is None:
        return "none"
    if path == focus:
        return "here"
    if path in ins and path in outs:
        return "both"
    if path in ins:
        return "in"
    if path in outs:
        return "out"
    return "far"


def _edge_focus(e: DocEdge, focus: str | None) -> str:
    if focus is None:
        return "none"
    if e.dst == focus:
        return "in"
    if e.src == focus:
        return "out"
    return "far"


def _state(node: DocNode) -> str:
    if not node.exists:
        return "missing"
    if node.kind == "adr":
        return node.status or "adr"
    return node.kind


def _map_node(
    corpus: Corpus, node: DocNode, x: int, y: int, focus: str,
) -> MapNode:
    """Build the drawn node; ``←n →n`` counts are *cites* edges only, which
    is the same number the index page prints as ``cited by N``."""
    return MapNode(
        path=node.path,
        x=x,
        y=y,
        short=node.short,
        title=node.title,
        kind=node.kind,
        status=node.status,
        state=_state(node),
        href=node.href,
        focus=focus,
        in_count=len(corpus.in_edges(node.path, ("cites",))),
        out_count=len([
            e for e in corpus.out_edges(node.path, ("cites",)) if not e.dangling
        ]),
        ghost=not node.exists,
    )


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _empty(marker: str, verdict: str, total: int) -> MapLayout:
    return MapLayout(
        width=MIN_FRAME_W,
        height=PAD + HEAD_H + NH + FOOT_H,
        marker_id=marker,
        verdict=verdict,
        drawn=0,
        total=total,
        empty=True,
    )


# --- the ladder --------------------------------------------------------------

def layout_ladder(
    corpus: Corpus,
    focus: str | None = None,
    expand: frozenset[str] = frozenset(),
) -> MapLayout:
    """Compute the constitution ladder for a whole corpus.

    Args:
        corpus: The governing set and its edges.
        focus: A node path to mark ``here``; one-hop neighbours (any edge
            kind in the corpus, drawn or not) get ``in``/``out``/``both``,
            the rest ``far``. A path not in the corpus is treated as no
            focus. A focused ADR hiding under a collapsed shelf lifts that
            shelf's cap, so the ``here`` node is always drawn.
        expand: Shelf-owner paths (and/or ``"pool"``) whose collapse cap is
            lifted.

    Returns:
        A :class:`MapLayout` with strictly positive dimensions for every
        input. ``empty`` is True — with a verdict saying why — when fewer
        than two governing docs exist or no edge joins any two nodes; the
        nodes are still placed so a template may draw them if it likes.
    """
    nodes = corpus.nodes
    order = [n.path for n in corpus.ordered()]
    rank = {p: i for i, p in enumerate(order)}
    gov = corpus.governing()
    gov_set = {n.path for n in gov}
    edges = _live_edges(corpus)
    if focus is not None and focus not in nodes:
        focus = None

    # What gets a box: every governing doc, plus any ghost or grey neighbour
    # a structural or supersedes edge ties to one. Cited-only neighbours are
    # not drawn — cites are drawn only into the ADR column.
    drawn: set[str] = set(gov_set)
    for e in edges:
        structural = e.kind in STRUCTURAL or e.kind == "supersedes"
        if structural and (e.src in gov_set or e.dst in gov_set):
            drawn.add(e.src)
            drawn.add(e.dst)

    def is_citer(n: DocNode) -> bool:
        return n.governing and n.exists and n.kind != "adr"

    # Shelf ownership: the first governing non-ADR citer in index order.
    owner: dict[str, str] = {}
    for e in edges:
        if e.kind != "cites" or e.dst not in drawn:
            continue
        if nodes[e.dst].kind != "adr" or not is_citer(nodes[e.src]):
            continue
        cur = owner.get(e.dst)
        if cur is None or rank[e.src] < rank[cur]:
            owner[e.dst] = e.src
    shelves: dict[str, list[str]] = {}
    pool: list[str] = []
    for p in order:
        if p not in drawn or nodes[p].kind != "adr":
            continue
        if p in owner:
            shelves.setdefault(owner[p], []).append(p)
        else:
            pool.append(p)
    shelf_owners = sorted(shelves, key=lambda p: rank[p])

    lifted = set(expand)
    if focus is not None:
        if focus in owner:
            lifted.add(owner[focus])
        elif focus in pool:
            lifted.add("pool")

    def expand_href(key: str) -> str:
        return "?expand=" + ",".join(sorted(lifted | {key}))

    shelf_vis: dict[str, list[str]] = {}
    for o in shelf_owners:
        members = shelves[o]
        capped = len(members) > SHELF_MAX and o not in lifted
        shelf_vis[o] = members[:SHELF_MAX] if capped else members
    pool_capped = len(pool) > POOL_MAX and "pool" not in lifted
    pool_vis = pool[:POOL_MAX] if pool_capped else pool

    hidden = {p for o in shelf_owners for p in shelves[o] if p not in shelf_vis[o]}
    hidden |= {p for p in pool if p not in pool_vis}
    visible = drawn - hidden
    col_of = {p: _column(nodes[p]) for p in visible}

    # Which edges are drawn, and in which direction the line runs. Structural
    # kinds dedupe on the drawn (parent, child) pair; cites only from a
    # non-ADR citer into the ADR column; supersedes as stored.
    drawn_edges: list[tuple[str, str, DocEdge]] = []
    seen_pairs: set[tuple[str, str]] = set()
    for e in edges:
        if e.src not in visible or e.dst not in visible:
            continue
        if e.kind in STRUCTURAL:
            frm, to = (e.dst, e.src) if e.kind == "parent" else (e.src, e.dst)
            if (frm, to) in seen_pairs:
                continue
            seen_pairs.add((frm, to))
        elif e.kind == "cites":
            if nodes[e.dst].kind != "adr" or not is_citer(nodes[e.src]):
                continue
            frm, to = e.src, e.dst
        elif e.kind == "supersedes":
            frm, to = e.src, e.dst
        else:
            continue
        drawn_edges.append((frm, to, e))

    # Lanes: per gutter, one x per source, in index order. Trunks: one y per
    # source whose edges span two or more columns, in index order.
    gutter_keys: dict[int, list[str]] = {}
    trunk_keys: list[str] = []
    for frm, to, _e in drawn_edges:
        for g in _gutters_used(col_of[frm], col_of[to]):
            keys = gutter_keys.setdefault(g, [])
            if frm not in keys:
                keys.append(frm)
        if abs(col_of[to] - col_of[frm]) >= 2 and frm not in trunk_keys:
            trunk_keys.append(frm)
    trunk_keys.sort(key=lambda p: rank[p])
    lane_of: dict[tuple[int, str], int] = {}
    for g, keys in gutter_keys.items():
        keys.sort(key=lambda p: rank[p])
        if g >= 3:
            for i, k in enumerate(keys):
                lane_of[(g, k)] = _col_x(3) + NW + SUP_MARGIN + i * SUP_STEP
        else:
            for k, x in _lanes(_col_x(g) + NW, keys).items():
                lane_of[(g, k)] = x
    channel_h = (len(trunk_keys) * TRUNK_STEP + CHANNEL_PAD) if trunk_keys else 0
    trunk_y = {k: PAD + HEAD_H + i * TRUNK_STEP for i, k in enumerate(trunk_keys)}
    y_top = PAD + HEAD_H + channel_h

    # Column 3 first: shelves in owner order, then the pool. Shelf tops are
    # what the other columns align to.
    pos: dict[str, tuple[int, int]] = {}
    labels: list[MapLabel] = []
    boxes: list[MapBox] = []
    shelf_top: dict[str, int] = {}
    x3 = _col_x(3)
    y = y_top
    for o in shelf_owners:
        vis = shelf_vis[o]
        members = shelves[o]
        cited = len([
            e for e in corpus.out_edges(o, ("cites",))
            if not e.dangling and e.dst in nodes and nodes[e.dst].kind == "adr"
        ])
        text = f"{nodes[o].short} cites {cited}"
        if cited != len(members):
            text += f" · {len(members)} here"
        labels.append(MapLabel(x=x3, y=y + SHELF_LABEL_H - 6, text=text, role="shelf"))
        y += SHELF_LABEL_H
        shelf_top[o] = y
        for p in vis:
            pos[p] = (x3, y)
            y += NH + ADR_GAP
        if len(vis) < len(members):
            labels.append(MapLabel(
                x=x3, y=y + MORE_H - 8,
                text=f"+{len(members) - len(vis)} more",
                role="more", href=expand_href(o),
            ))
            y += MORE_H + ADR_GAP
        y += SHELF_GAP - ADR_GAP
    pool_bottom = 0
    if pool:
        py = y + (POOL_GAP if shelf_owners else 0)
        labels.append(MapLabel(
            x=x3, y=py + 18, text=f"cited by no doc · {len(pool)}", role="pool",
        ))
        cy = py + POOL_HEAD_H
        for p in pool_vis:
            pos[p] = (x3, cy)
            cy += NH + ADR_GAP
        if pool_capped:
            labels.append(MapLabel(
                x=x3, y=cy + MORE_H - 8,
                text=f"+{len(pool) - len(pool_vis)} more",
                role="more", href=expand_href("pool"),
            ))
            cy += MORE_H + ADR_GAP
        ph = (cy - ADR_GAP - py) + POOL_FOOT_H
        boxes.append(MapBox(x=x3 - POOL_INSET, y=py, w=NW + 2 * POOL_INSET, h=ph, role="pool"))
        pool_bottom = py + ph

    # Columns 0–2 stack in index order; a shelf owner drops to its shelf.
    for col in range(3):
        cursor = y_top
        for p in order:
            if p not in visible or col_of[p] != col:
                continue
            ny = max(cursor, shelf_top.get(p, 0))
            pos[p] = (_col_x(col), ny)
            cursor = ny + NH + ROW_GAP

    used_cols = {col_of[p] for p in pos}
    for col in sorted(used_cols):
        labels.append(MapLabel(
            x=_col_x(col), y=PAD + LABEL_DY, text=COLUMN_LABELS[col], role="column",
        ))

    # Focus is one-hop adjacency over the whole corpus, drawn or not.
    ins = {e.src for e in corpus.in_edges(focus)} if focus else set()
    outs = {e.dst for e in corpus.out_edges(focus)} if focus else set()

    map_nodes = [
        _map_node(corpus, nodes[p], pos[p][0], pos[p][1], _node_focus(p, focus, ins, outs))
        for p in order if p in pos
    ]
    map_edges = [
        MapEdge(
            src=e.src, dst=e.dst, kind=e.kind,
            d=_route(
                pos[frm][0], pos[frm][1], col_of[frm],
                pos[to][0], pos[to][1], col_of[to],
                lane_of, trunk_y, frm,
            ),
            focus=_edge_focus(e, focus),
        )
        for frm, to, e in drawn_edges
    ]

    right = max((x + NW for x, _y in pos.values()), default=PAD)
    right = max(
        right,
        max((x + SUP_TAIL for (g, _k), x in lane_of.items() if g >= 3), default=0),
        (x3 + NW + POOL_INSET) if pool else 0,
        MIN_FRAME_W - PAD,
    )
    bottom = max(
        max((y + NH for _x, y in pos.values()), default=y_top),
        pool_bottom,
        max((lb.y for lb in labels), default=0),
    )

    n_adr = len([n for n in gov if n.kind == "adr"])
    n_area = len([n for n in gov if n.kind == "area"])
    total = len(gov)
    empty = total < 2 or not edges
    if total < 2:
        verdict = f"{_plural(total, 'doc')} · nothing to map"
    elif not edges:
        verdict = f"{_plural(total, 'doc')} · no links between them"
    else:
        verdict = (
            f"{_plural(total, 'doc')} · {_plural(n_area, 'area')} · "
            f"{_plural(n_adr, 'decision')} · {len(pool)} cited by no doc"
        )

    return MapLayout(
        width=int(right + PAD),
        height=int(bottom + FOOT_H),
        nodes=map_nodes,
        edges=map_edges,
        labels=labels,
        boxes=boxes,
        marker_id=MARKER_LADDER,
        verdict=verdict,
        drawn=len(map_nodes),
        total=total,
        empty=empty,
    )


# --- the neighbourhood strip -------------------------------------------------

def layout_neighbourhood(corpus: Corpus, focus: str) -> MapLayout:
    """Compute the one-hop strip around *focus*: in | here | out.

    A node both pointing at the focus and pointed at by it sits on the left
    with ``focus="both"`` and draws two edges. Each side is capped at
    :data:`SIDE_MAX` with a ``more`` label (no href — the cited-by panel
    lists the rest). ``empty`` is True when nothing touches the focus, or
    when *focus* is not a corpus node.
    """
    nodes = corpus.nodes
    here = nodes.get(focus)
    total = len(corpus.governing())
    if here is None:
        return _empty(MARKER_STRIP, "not in the corpus", total)

    order = [n.path for n in corpus.ordered()]
    edges = _live_edges(corpus)
    ins = {e.src for e in edges if e.dst == focus}
    outs = {e.dst for e in edges if e.src == focus}
    left = [p for p in order if p in ins]
    right = [p for p in order if p in outs and p not in ins]
    left_vis = left[:SIDE_MAX] if len(left) > SIDE_MAX else left
    right_vis = right[:SIDE_MAX] if len(right) > SIDE_MAX else right
    visible = set(left_vis) | set(right_vis) | {focus}

    pitch = NH + ROW_GAP
    y_top = PAD + HEAD_H

    def col_h(vis: list[str], all_: list[str]) -> int:
        if not vis:
            return 0
        return len(vis) * pitch - ROW_GAP + (MORE_H if len(vis) < len(all_) else 0)

    tallest = max(col_h(left_vis, left), col_h(right_vis, right), NH)
    pos: dict[str, tuple[int, int]] = {focus: (_col_x(1), y_top + (tallest - NH) // 2)}
    col_of: dict[str, int] = {focus: 1}
    labels: list[MapLabel] = []
    for col, vis, all_ in ((0, left_vis, left), (2, right_vis, right)):
        yy = y_top
        for p in vis:
            pos[p] = (_col_x(col), yy)
            col_of[p] = col
            yy += pitch
        if len(vis) < len(all_):
            labels.append(MapLabel(
                x=_col_x(col), y=yy - ROW_GAP + MORE_H - 8,
                text=f"+{len(all_) - len(vis)} more", role="more",
            ))

    # One shared lane per direction: in-edges converge on the focus's left
    # edge and read as a bus; out-edges fork from its right edge. Out-edges
    # to a ``both`` node run back leftward in gutter 0 on the ``out`` lane.
    lane_of: dict[tuple[int, str], int] = {}
    for (g, k), x in (
        ((0, "in"), _lanes(_col_x(0) + NW, ["in", "out"])["in"]),
        ((0, "out"), _lanes(_col_x(0) + NW, ["in", "out"])["out"]),
        ((1, "out"), _lanes(_col_x(1) + NW, ["out"])["out"]),
    ):
        lane_of[(g, k)] = x

    map_edges: list[MapEdge] = []
    for e in edges:
        if e.dst == focus and e.src in visible:
            frm, to, key = e.src, focus, "in"
        elif e.src == focus and e.dst in visible:
            frm, to, key = focus, e.dst, "out"
        else:
            continue
        map_edges.append(MapEdge(
            src=e.src, dst=e.dst, kind=e.kind,
            d=_route(
                pos[frm][0], pos[frm][1], col_of[frm],
                pos[to][0], pos[to][1], col_of[to],
                lane_of, {}, key,
            ),
            focus=_edge_focus(e, focus),
        ))

    labels.append(MapLabel(x=_col_x(0), y=PAD + LABEL_DY, text=f"{len(ins)} IN", role="column"))
    labels.append(MapLabel(x=_col_x(1), y=PAD + LABEL_DY, text="THIS DOC", role="column"))
    labels.append(MapLabel(x=_col_x(2), y=PAD + LABEL_DY, text=f"{len(outs)} OUT", role="column"))

    map_nodes = [
        _map_node(corpus, nodes[p], pos[p][0], pos[p][1], _node_focus(p, focus, ins, outs))
        for p in order if p in pos
    ]
    right_x = max((x + NW for x, _y in pos.values()), default=PAD)
    right_x = max(right_x, _col_x(1) + NW, MIN_FRAME_W - PAD)
    bottom = max(
        max((y + NH for _x, y in pos.values()), default=y_top),
        max((lb.y for lb in labels), default=0),
    )
    return MapLayout(
        width=int(right_x + PAD),
        height=int(bottom + FOOT_H),
        nodes=map_nodes,
        edges=map_edges,
        labels=labels,
        marker_id=MARKER_STRIP,
        verdict=f"{len(ins)} in · {len(outs)} out",
        drawn=len(map_nodes),
        total=total,
        empty=not (ins or outs),
    )
