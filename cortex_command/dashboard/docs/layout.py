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

Three indents, assigned by document kind and never by longest path, then
the decisions::

    constitution
      root + policy + config + readme
        areas + glossary                  | ADR shelves

Every non-ADR doc gets a *band* of its own: a horizontal strip of the frame
no other doc box shares. Bands run top to bottom by indent, then index
order. Because no two doc boxes share a band, a horizontal run at a doc's
own height crosses nothing, which is what lets the doc column be one column
wide and leave the width to the shelves. Structural lines run a *rail* left
of every box — one lane per source — leaving the source's left edge and
entering the target's, so a root with nineteen areas draws one bus.

A decision sits exactly once, on a *shelf* in its strongest citer's band: a
grid of :data:`SHELF_COLS` chips framed beside the doc, with one line from
the doc into the frame. The strongest citer is the governing doc that
mentions the ADR most often, ties going to the doc citing the fewest ADRs
(the more specific home), then index order. An *index* doc — the ADR
README, which lists every decision — cites nothing here: a list is not a
dependency, and counting it gave one doc most of the shelves. ADRs no other
doc cites sit in a dashed pool under the last band, so absence reads as a
finding. Long shelves collapse to :data:`SHELF_MAX` chips plus a ``more``
label whose href lifts the cap for that shelf; the pool likewise under the
``expand`` key ``pool``.

A citation from any doc other than the shelf owner is not a line. It is a
hover link: every node carries ``links``, the paths that light up when it is
hovered — a doc's decisions wherever they sit, a decision's citers and its
supersedes neighbours. Lines for those crossed the whole map and merged into
a solid bar on a 112-ADR corpus; the owner line and the light carry the same
facts without it.

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
    MAP_CH,
    MAP_CW,
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
CW, CH = MAP_CW, MAP_CH
PAD = 26
COL_GAP = 72           # strip: gutter between columns; every lane lives in one
ROW_GAP = 14           # between one band and the next
CHIP_GAP = 8           # between chips on a shelf or in the pool, both axes

INDENT = 20            # ladder: a doc box steps right this far per column
RAIL_STEP = 8          # ladder: pitch between structural lanes in the left rail
SHELF_GAP_X = 36       # ladder: from the widest doc box to the shelf chips

HEAD_H = 34            # column-label band above the first doc
LABEL_DY = 12          # column-label baseline inside the band

SHELF_COLS = 4
SHELF_LABEL_H = 22     # label band above a shelf's frame
SHELF_INSET = 8        # shelf frame overhang around its chips
MORE_H = 22            # the ``+N more`` label's row
POOL_GAP = 26          # from the last band to the pool box
POOL_HEAD_H = 30
POOL_FOOT_H = 8

LANE_MARGIN = 12       # first lane's offset from the gutter's left edge
LANE_STEP_MAX = 12     # lanes never spread wider than this

SHELF_MAX = 16
POOL_MAX = 12
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
COLUMN_LABELS = ("DOCS", "DECISIONS")
STRUCTURAL = ("parent", "maps-area", "global")

#: Docs that list decisions rather than lean on them. Their cites are neither
#: shelves nor hover links. Kept in step with ``corpus.ADR_README``.
INDEX_DOCS = frozenset({"cortex/adr/README.md"})


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
    :data:`LANE_STEP_MAX` apart, and never past the right margin: a shelf
    frame or the pool box overhangs the gutter right of the area column, and
    a lane must stay clear of it.
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
    key: str,
) -> str:
    """SVG ``d`` from box A (mid-height *ay*) to box B (mid-height *by*).

    *lane_of* is keyed by ``(gutter, key)`` where gutter ``g`` is the strip
    right of column ``g``. Every case ends with a horizontal into the target
    so the arrowhead marker sits flat. A run that crosses whole columns does
    so at an endpoint's own height, which the caller guarantees is clear:

    * rightward: across at A's height, down gutter ``bcol-1``, into B's left
      (the strip only ever crosses one gutter);
    * same column: out the right side, down the gutter right of the column,
      back in to the target's right edge;
    * leftward: out A's left side, down gutter ``acol-1``, across at B's
      height into B's right edge.
    """
    dc = bcol - acol
    if dc >= 1:
        return elbow(ax + NW, ay, bx, by, lane_of[(bcol - 1, key)])
    if dc == 0:
        return (
            f"M {ax + NW} {ay} H {lane_of[(acol, key)]} V {by} "
            f"H {bx + NW + ARROW_INSET}"
        )
    return (
        f"M {ax} {ay} H {lane_of[(acol - 1, key)]} V {by} "
        f"H {bx + NW + ARROW_INSET}"
    )


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
    chip: bool = False, links: tuple[str, ...] = (),
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
        w=CW if chip else NW,
        h=CH if chip else NH,
        chip=chip,
        links=links,
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


def _grid_h(n: int) -> int:
    """Height of *n* chips laid :data:`SHELF_COLS` wide, no outer gap."""
    rows = -(-n // SHELF_COLS)
    return rows * (CH + CHIP_GAP) - CHIP_GAP if rows else 0


def _grid_w(n: int) -> int:
    cols = min(n, SHELF_COLS)
    return cols * (CW + CHIP_GAP) - CHIP_GAP if cols else 0


def _grid_pos(x0: int, y0: int, i: int) -> tuple[int, int]:
    r, c = divmod(i, SHELF_COLS)
    return x0 + c * (CW + CHIP_GAP), y0 + r * (CH + CHIP_GAP)


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

    def is_citer(p: str) -> bool:
        n = nodes[p]
        return n.governing and n.exists and n.kind != "adr" and p not in INDEX_DOCS

    doc_cites = [
        e for e in edges
        if e.kind == "cites" and nodes[e.dst].kind == "adr" and is_citer(e.src)
    ]
    breadth: dict[str, int] = {}
    for e in doc_cites:
        breadth[e.src] = breadth.get(e.src, 0) + 1

    # Shelf ownership: most mentions, then the narrowest citer, then index order.
    owner: dict[str, str] = {}
    for e in doc_cites:
        if e.dst not in drawn:
            continue
        cur = owner.get(e.dst)
        cand = (-e.count, breadth[e.src], rank[e.src])
        if cur is None:
            owner[e.dst] = e.src
            continue
        best = max(
            (x.count for x in doc_cites if x.src == cur and x.dst == e.dst), default=0,
        )
        if cand < (-best, breadth[cur], rank[cur]):
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

    lifted = set(expand)
    if focus is not None:
        if focus in owner:
            lifted.add(owner[focus])
        elif focus in pool:
            lifted.add("pool")

    def expand_href(key: str) -> str:
        return "?expand=" + ",".join(sorted(lifted | {key}))

    shelf_vis: dict[str, list[str]] = {}
    for o, members in shelves.items():
        capped = len(members) > SHELF_MAX and o not in lifted
        shelf_vis[o] = members[:SHELF_MAX] if capped else members
    pool_capped = len(pool) > POOL_MAX and "pool" not in lifted
    pool_vis = pool[:POOL_MAX] if pool_capped else pool

    hidden = {p for o in shelves for p in shelves[o] if p not in shelf_vis[o]}
    hidden |= {p for p in pool if p not in pool_vis}
    visible = drawn - hidden
    col_of = {p: _column(nodes[p]) for p in visible}

    # Which edges are lines. Structural kinds between doc boxes, deduped on the
    # drawn (parent, child) pair; one cites line per shelf, owner → first chip.
    lines: list[tuple[str, str, str, str, str]] = []   # frm, to, kind, src, dst
    seen_pairs: set[tuple[str, str]] = set()
    for e in edges:
        if e.kind not in STRUCTURAL:
            continue
        if e.src not in visible or e.dst not in visible:
            continue
        if col_of[e.src] > 2 or col_of[e.dst] > 2:
            continue
        frm, to = (e.dst, e.src) if e.kind == "parent" else (e.src, e.dst)
        if (frm, to) in seen_pairs:
            continue
        seen_pairs.add((frm, to))
        lines.append((frm, to, e.kind, e.src, e.dst))

    # Bands: every doc box in column order, then index order. A doc's column
    # is an indent, not a grid column: bands never share a height, so the doc
    # boxes can sit one under another and leave the width to the shelves.
    band_docs = sorted(
        (p for p in visible if col_of[p] <= 2), key=lambda p: (col_of[p], rank[p]),
    )
    for o in band_docs:
        if o in shelf_vis:
            lines.append((o, shelf_vis[o][0], "cites", o, shelf_vis[o][0]))

    # The rail: one lane per structural source, left of every box. A line
    # leaves its source's left edge, runs the rail, and enters its target's
    # left edge — both horizontals at an endpoint's own band.
    band_rank = {p: i for i, p in enumerate(band_docs)}
    rail_keys = sorted(
        {frm for frm, _to, kind, _s, _d in lines if kind != "cites"},
        key=lambda p: band_rank[p],
    )
    rail_x = {k: PAD + i * RAIL_STEP for i, k in enumerate(rail_keys)}
    doc_x0 = PAD + (len(rail_keys) * RAIL_STEP + LANE_MARGIN if rail_keys else 0)

    def doc_x(p: str) -> int:
        return doc_x0 + col_of[p] * INDENT

    x3 = doc_x0 + 2 * INDENT + NW + SHELF_GAP_X

    pos: dict[str, tuple[int, int]] = {}
    chip: set[str] = set()
    labels: list[MapLabel] = []
    boxes: list[MapBox] = []
    y = PAD + HEAD_H
    for p in band_docs:
        vis = shelf_vis.get(p)
        if not vis:
            pos[p] = (doc_x(p), y)
            y += NH + ROW_GAP
            continue
        members = shelves[p]
        cited = breadth.get(p, 0)
        text = f"{nodes[p].short} · {len(members)} here"
        if cited != len(members):
            text += f" · cites {cited}"
        labels.append(MapLabel(x=x3, y=y + SHELF_LABEL_H - 8, text=text, role="shelf"))
        top = y + SHELF_LABEL_H
        grid_top = top + SHELF_INSET
        for i, a in enumerate(vis):
            pos[a] = _grid_pos(x3, grid_top, i)
            chip.add(a)
        frame_h = _grid_h(len(vis)) + 2 * SHELF_INSET
        boxes.append(MapBox(
            x=x3 - SHELF_INSET, y=top, w=_grid_w(len(vis)) + 2 * SHELF_INSET,
            h=frame_h, role="shelf",
        ))
        # the owner's middle sits level with the first chip row's middle
        pos[p] = (doc_x(p), grid_top + CH // 2 - NH // 2)
        bottom = max(top + frame_h, pos[p][1] + NH)
        if len(vis) < len(members):
            labels.append(MapLabel(
                x=x3, y=bottom + MORE_H - 6,
                text=f"+{len(members) - len(vis)} more",
                role="more", href=expand_href(p),
            ))
            bottom += MORE_H
        y = bottom + ROW_GAP + 6

    pool_bottom = 0
    if pool:
        py = y + (POOL_GAP if band_docs else 0)
        labels.append(MapLabel(
            x=x3, y=py + 18, text=f"cited by no doc · {len(pool)}", role="pool",
        ))
        cy = py + POOL_HEAD_H
        for i, p in enumerate(pool_vis):
            pos[p] = _grid_pos(x3, cy, i)
            chip.add(p)
        cy += _grid_h(len(pool_vis))
        if pool_capped:
            labels.append(MapLabel(
                x=x3, y=cy + MORE_H - 4,
                text=f"+{len(pool) - len(pool_vis)} more",
                role="more", href=expand_href("pool"),
            ))
            cy += MORE_H
        ph = (cy - py) + POOL_FOOT_H
        boxes.append(MapBox(
            x=x3 - SHELF_INSET, y=py, w=max(_grid_w(len(pool_vis)), CW) + 2 * SHELF_INSET,
            h=ph, role="pool",
        ))
        pool_bottom = py + ph

    if band_docs:
        labels.append(MapLabel(x=doc_x0, y=PAD + LABEL_DY, text=COLUMN_LABELS[0], role="column"))
    if chip:
        labels.append(MapLabel(x=x3, y=PAD + LABEL_DY, text=COLUMN_LABELS[1], role="column"))

    # Hover links: a doc lights its decisions, a decision its citers and its
    # supersedes neighbours. Index docs neither light nor are lit by cites.
    link_sets: dict[str, set[str]] = {p: set() for p in pos}
    for e in doc_cites:
        if e.src in pos and e.dst in pos:
            link_sets[e.src].add(e.dst)
            link_sets[e.dst].add(e.src)
    for e in edges:
        if e.kind == "supersedes" and e.src in pos and e.dst in pos:
            link_sets[e.src].add(e.dst)
            link_sets[e.dst].add(e.src)

    # Focus is one-hop adjacency over the whole corpus, drawn or not.
    ins = {e.src for e in corpus.in_edges(focus)} if focus else set()
    outs = {e.dst for e in corpus.out_edges(focus)} if focus else set()

    map_nodes = [
        _map_node(
            corpus, nodes[p], pos[p][0], pos[p][1], _node_focus(p, focus, ins, outs),
            chip=p in chip, links=tuple(sorted(link_sets[p], key=lambda q: rank[q])),
        )
        for p in order if p in pos
    ]

    def mid(p: str) -> int:
        return pos[p][1] + (CH if p in chip else NH) // 2

    def line_focus(kind: str, src: str, dst: str) -> str:
        if focus is None:
            return "none"
        if kind == "cites":
            if focus == src:
                return "out"
            return "in" if focus in shelves.get(src, ()) else "far"
        return _edge_focus(DocEdge(src=src, dst=dst, kind=kind), focus)

    map_edges: list[MapEdge] = []
    for frm, to, kind, src, dst in lines:
        if kind == "cites":
            d = f"M {pos[frm][0] + NW} {mid(frm)} H {x3 - SHELF_INSET - ARROW_INSET}"
        else:
            d = (
                f"M {pos[frm][0]} {mid(frm)} H {rail_x[frm]} V {mid(to)} "
                f"H {pos[to][0] - ARROW_INSET}"
            )
        map_edges.append(MapEdge(
            src=src, dst=dst, kind=kind, d=d, focus=line_focus(kind, src, dst),
        ))

    right = max(
        max((x + (CW if p in chip else NW) for p, (x, _y) in pos.items()), default=PAD),
        max((b.x + b.w for b in boxes), default=0),
        MIN_FRAME_W - PAD,
    )
    bottom = max(
        max((yy + (CH if p in chip else NH) for p, (_x, yy) in pos.items()),
            default=PAD + HEAD_H),
        pool_bottom,
        max((b.y + b.h for b in boxes), default=0),
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
                pos[frm][0], pos[frm][1] + NH // 2, col_of[frm],
                pos[to][0], pos[to][1] + NH // 2, col_of[to],
                lane_of, key,
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
