"""Unit tests for cortex_command/dashboard/docs/layout.py.

The ladder and the strip are computed entirely on the server, so these
tests are where the numbers are checked — a bad coordinate reaches the
operator as a drawn frame, not an exception. They assert structure and
arithmetic: boxes inside the frame, boxes not overlapping, every edge
segment clear of every box it does not start or end at, ints everywhere,
and byte-stable output. Nothing here pins a verdict sentence.

The hand corpus is built from ``model`` dataclasses with no disk: a
constitution, a policy, a root, a config, a readme, three mapped areas plus
a glossary, twelve ADRs (one uncited so the pool exists, one superseded,
one ghost successor, ties that exercise shelf ownership), a dangling cite
and an ADR-to-ADR cite that must never be drawn.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from cortex_command.dashboard.docs.layout import (
    NH,
    NW,
    PAD,
    POOL_MAX,
    SHELF_MAX,
    SIDE_MAX,
    layout_ladder,
    layout_neighbourhood,
)
from cortex_command.dashboard.docs.model import (
    Corpus,
    DocEdge,
    DocNode,
    MapLayout,
)

CLAUDE = "CLAUDE.md"
POLICIES = "docs/policies.md"
PROJECT = "cortex/requirements/project.md"
CONFIG = "cortex/lifecycle.config.md"
README = "cortex/README.md"
LIFECYCLE = "cortex/requirements/lifecycle.md"
BACKLOG = "cortex/requirements/backlog.md"
OBS = "cortex/requirements/observability.md"
GLOSSARY = "cortex/requirements/glossary.md"
GHOST_AREA = "cortex/requirements/nope.md"
DANGLING = "cortex/adr/0099-nope.md"


def adr_path(n: int) -> str:
    return f"cortex/adr/{n:04d}-decision-{n}.md"


def adr(n: int, status: str = "accepted", exists: bool = True, superseded_by: str | None = None) -> DocNode:
    return DocNode(
        path=adr_path(n), kind="adr", title=f"Decision {n}", governing=exists,
        exists=exists, adr_number=n, status=status if exists else None,
        superseded_by=superseded_by,
    )


def doc(path: str, kind: str, title: str | None = None, **kw) -> DocNode:
    return DocNode(path=path, kind=kind, title=title or path, governing=True, **kw)


def hand_corpus() -> Corpus:
    c = Corpus(root=Path("/nonexistent"))
    for n in (
        doc(CLAUDE, "constitution", "Project instructions"),
        doc(POLICIES, "policy", "Policies", parent=CLAUDE),
        doc(PROJECT, "root", "Project", parent=CLAUDE),
        doc(CONFIG, "config", "Lifecycle config"),
        doc(README, "readme", "Cortex readme"),
        doc(LIFECYCLE, "area", "Lifecycle", parent=PROJECT, map_keys=("lifecycle",)),
        doc(BACKLOG, "area", "Backlog", parent=PROJECT, map_keys=("backlog",)),
        doc(OBS, "area", "Observability", parent=PROJECT, map_keys=("observability",)),
        doc(GLOSSARY, "glossary", "Glossary", parent=PROJECT),
        DocNode(path=GHOST_AREA, kind="area", title="nope", governing=False, exists=False),
    ):
        c.nodes[n.path] = n
    for n in range(1, 11):
        c.nodes[adr_path(n)] = adr(n, superseded_by=adr_path(3) if n == 2 else None,
                                   status="superseded" if n == 2 else ("proposed" if n == 5 else "accepted"))
    c.nodes[adr_path(12)] = adr(12)
    c.nodes[adr_path(13)] = adr(13)
    c.nodes[adr_path(11)] = adr(11, exists=False)   # ghost successor of 10
    c.nodes[adr_path(10)] = adr(10, status="superseded", superseded_by=adr_path(11))

    e = c.edges
    # structural
    e.append(DocEdge(src=POLICIES, dst=CLAUDE, kind="parent"))
    e.append(DocEdge(src=PROJECT, dst=CLAUDE, kind="parent"))
    e.append(DocEdge(src=PROJECT, dst=LIFECYCLE, kind="maps-area", keys=("lifecycle",)))
    e.append(DocEdge(src=PROJECT, dst=BACKLOG, kind="maps-area", keys=("backlog",)))
    e.append(DocEdge(src=PROJECT, dst=OBS, kind="maps-area", keys=("observability",)))
    e.append(DocEdge(src=PROJECT, dst=GHOST_AREA, kind="maps-area", keys=("nope",)))
    e.append(DocEdge(src=PROJECT, dst=POLICIES, kind="global"))
    e.append(DocEdge(src=PROJECT, dst=GLOSSARY, kind="global"))
    for area in (LIFECYCLE, BACKLOG, OBS, GLOSSARY):
        e.append(DocEdge(src=area, dst=PROJECT, kind="parent"))
    # cites: project owns 1, 3, 8 (most mentions); CLAUDE owns 9 and backlog
    # owns 4 (narrowest citer); lifecycle owns 2, 5, 6, 7, 12, 13
    e.append(DocEdge(src=POLICIES, dst=adr_path(8), kind="cites", section="Tone"))
    for n in (1, 3, 8):
        e.append(DocEdge(src=PROJECT, dst=adr_path(n), kind="cites", count=2))
    for n in (1, 2, 3, 4, 5, 6, 7, 9, 12, 13):
        e.append(DocEdge(src=LIFECYCLE, dst=adr_path(n), kind="cites"))
    e.append(DocEdge(src=LIFECYCLE, dst=DANGLING, kind="cites", dangling=True))
    e.append(DocEdge(src=BACKLOG, dst=LIFECYCLE, kind="cites"))
    e.append(DocEdge(src=BACKLOG, dst=adr_path(4), kind="cites"))
    e.append(DocEdge(src=CLAUDE, dst=adr_path(9), kind="cites"))
    e.append(DocEdge(src=adr_path(3), dst=adr_path(4), kind="cites"))   # adr→adr: never drawn
    # supersedes
    e.append(DocEdge(src=adr_path(3), dst=adr_path(2), kind="supersedes"))
    e.append(DocEdge(src=adr_path(11), dst=adr_path(10), kind="supersedes"))
    return c


# --- geometry helpers ----------------------------------------------------------

_TOKEN = re.compile(r"^-?\d+$")


def segments(d: str) -> list[tuple[int, int, int, int]]:
    """Walk an ``M/H/V`` path into ``(x1, y1, x2, y2)`` segments."""
    toks = d.split()
    assert toks[0] == "M", d
    x, y = int(toks[1]), int(toks[2])
    out = []
    i = 3
    while i < len(toks):
        op, val = toks[i], int(toks[i + 1])
        nx, ny = (val, y) if op == "H" else (x, val)
        out.append((x, y, nx, ny))
        x, y = nx, ny
        i += 2
    return out


def crosses_box(
    seg: tuple[int, int, int, int], bx: int, by: int, bw: int = NW, bh: int = NH,
) -> bool:
    """True when the segment passes through the *interior* of a box."""
    x1, y1, x2, y2 = seg
    lo_x, hi_x = min(x1, x2), max(x1, x2)
    lo_y, hi_y = min(y1, y2), max(y1, y2)
    return lo_x < bx + bw and hi_x > bx and lo_y < by + bh and hi_y > by


class GeometryMixin:
    def assert_frame_sound(self, layout: MapLayout) -> None:
        assert isinstance(self, unittest.TestCase)
        self.assertGreater(layout.width, 0)
        self.assertGreater(layout.height, 0)
        self.assertIsInstance(layout.width, int)
        self.assertIsInstance(layout.height, int)
        boxes = {n.path: (n.x, n.y) for n in layout.nodes}
        for n in layout.nodes:
            self.assertIsInstance(n.x, int)
            self.assertIsInstance(n.y, int)
            self.assertGreaterEqual(n.x, 0)
            self.assertGreaterEqual(n.y, 0)
            self.assertLessEqual(n.x + n.w, layout.width, n.path)
            self.assertLessEqual(n.y + n.h, layout.height, n.path)
        nodes = layout.nodes
        for i, a in enumerate(nodes):
            for b in nodes[i + 1:]:
                overlap = (
                    a.x < b.x + b.w and a.x + a.w > b.x
                    and a.y < b.y + b.h and a.y + a.h > b.y
                )
                self.assertFalse(overlap, f"{a.path} overlaps {b.path}")
        for e in layout.edges:
            self.assertTrue(e.d.startswith("M "), e.d)
            for tok in e.d.split():
                self.assertTrue(tok in ("M", "H", "V") or _TOKEN.match(tok), e.d)
            self.assertIn(e.src, boxes, e.src)
            self.assertIn(e.dst, boxes, e.dst)
            for seg in segments(e.d):
                for x1, y1, x2, y2 in [seg]:
                    self.assertTrue(0 <= x1 <= layout.width and 0 <= x2 <= layout.width, e.d)
                    self.assertTrue(0 <= y1 <= layout.height and 0 <= y2 <= layout.height, e.d)
                for n in nodes:
                    if n.path in (e.src, e.dst):
                        continue
                    self.assertFalse(
                        crosses_box(seg, n.x, n.y, n.w, n.h),
                        f"{e.kind} {e.src}->{e.dst} runs through {n.path}: {e.d}",
                    )
        for lb in layout.labels:
            self.assertIsInstance(lb.x, int)
            self.assertIsInstance(lb.y, int)
            self.assertLessEqual(lb.y, layout.height)
        for b in layout.boxes:
            self.assertLessEqual(b.x + b.w, layout.width)
            self.assertLessEqual(b.y + b.h, layout.height)


# --- the ladder ------------------------------------------------------------------

class LadderTests(GeometryMixin, unittest.TestCase):
    def setUp(self):
        self.corpus = hand_corpus()
        self.layout = layout_ladder(self.corpus)

    def test_frame_sound(self):
        self.assert_frame_sound(self.layout)
        self.assertFalse(self.layout.empty)
        self.assertTrue(self.layout.verdict)
        self.assertEqual(self.layout.total, len(self.corpus.governing()))
        self.assertEqual(self.layout.drawn, len(self.layout.nodes))

    def test_columns_by_kind(self):
        xs = {n.path: n.x for n in self.layout.nodes}
        self.assertLess(xs[CLAUDE], xs[POLICIES])
        self.assertEqual(xs[POLICIES], xs[PROJECT])
        self.assertEqual(xs[PROJECT], xs[CONFIG])
        self.assertLess(xs[PROJECT], xs[LIFECYCLE])
        self.assertEqual(xs[LIFECYCLE], xs[GLOSSARY])
        # every structural line runs the rail left of every box
        left = min(n.x for n in self.layout.nodes)
        for e in self.layout.edges:
            if e.kind != "cites":
                self.assertLess(segments(e.d)[1][0], left, e.d)
        adr_xs = [n.x for n in self.layout.nodes if n.kind == "adr"]
        self.assertGreater(min(adr_xs), xs[LIFECYCLE] + NW)
        self.assertTrue(all(n.chip for n in self.layout.nodes if n.kind == "adr"))
        self.assertFalse(any(n.chip for n in self.layout.nodes if n.kind != "adr"))

    def test_doc_bands_are_exclusive(self):
        # no two doc boxes share any height: that is what keeps every
        # horizontal run at a doc's own height clear of other boxes
        docs = sorted((n for n in self.layout.nodes if not n.chip), key=lambda n: n.y)
        for a, b in zip(docs, docs[1:]):
            self.assertLessEqual(a.y + a.h, b.y, f"{a.path} shares a band with {b.path}")

    def _long_shelf(self) -> Corpus:
        c = hand_corpus()
        for n in range(20, 21 + SHELF_MAX):
            c.nodes[adr_path(n)] = adr(n)
            c.edges.append(DocEdge(src=LIFECYCLE, dst=adr_path(n), kind="cites"))
        return c

    def test_shelf_collapses_past_the_cap(self):
        lay = layout_ladder(self._long_shelf())
        self.assert_frame_sound(lay)
        drawn = {n.path for n in lay.nodes}
        self.assertNotIn(adr_path(20 + SHELF_MAX), drawn)
        more = [lb for lb in lay.labels if lb.role == "more"]
        self.assertEqual(len(more), 1)
        self.assertIn(LIFECYCLE, more[0].href or "")
        self.assertTrue(more[0].href.startswith("?expand="))

    def test_expand_lifts_the_cap(self):
        lay = layout_ladder(self._long_shelf(), expand=frozenset({LIFECYCLE}))
        self.assert_frame_sound(lay)
        drawn = {n.path for n in lay.nodes}
        self.assertIn(adr_path(20 + SHELF_MAX), drawn)
        self.assertEqual([lb for lb in lay.labels if lb.role == "more"], [])

    def test_focus_on_hidden_adr_lifts_its_shelf(self):
        target = adr_path(20 + SHELF_MAX)
        lay = layout_ladder(self._long_shelf(), focus=target)
        here = [n for n in lay.nodes if n.focus == "here"]
        self.assertEqual([n.path for n in here], [target])

    def test_shelf_ownership_is_strongest_citer(self):
        pos = {n.path: n for n in self.layout.nodes}

        def shelf_of(p: str) -> str:
            owners = [e.src for e in self.layout.edges if e.kind == "cites"]
            frame = [b for b in self.layout.boxes if b.role == "shelf"
                     and b.y <= pos[p].y < b.y + b.h]
            self.assertEqual(len(frame), 1, p)
            mids = {o: pos[o].y + pos[o].h // 2 for o in owners}
            return next(o for o, m in mids.items() if frame[0].y <= m < frame[0].y + frame[0].h)

        # project mentions 1, 3 and 8 twice: most mentions wins over policies
        # and lifecycle; CLAUDE and backlog cite one ADR each, so the narrow
        # citer wins the tie with lifecycle's ten.
        for n in (1, 3, 8):
            self.assertEqual(shelf_of(adr_path(n)), PROJECT, n)
        self.assertEqual(shelf_of(adr_path(9)), CLAUDE)
        self.assertEqual(shelf_of(adr_path(4)), BACKLOG)
        for n in (2, 5, 6, 7, 12, 13):
            self.assertEqual(shelf_of(adr_path(n)), LIFECYCLE, n)
        # the owner's middle is level with its first chip row's middle
        for e in self.layout.edges:
            if e.kind == "cites":
                o, first = pos[e.src], pos[e.dst]
                self.assertEqual(o.y + o.h // 2, first.y + first.h // 2, e.src)

    def test_index_doc_owns_no_shelf(self):
        c = hand_corpus()
        index = "cortex/adr/README.md"
        c.nodes[index] = doc(index, "policy", "ADR index")
        for n in list(range(1, 11)) + [12, 13]:
            c.edges.append(DocEdge(src=index, dst=adr_path(n), kind="cites", count=3))
        lay = layout_ladder(c)
        self.assert_frame_sound(lay)
        self.assertFalse(any(e.src == index for e in lay.edges))
        pos = {n.path: n for n in lay.nodes}
        self.assertEqual(pos[index].links, ())
        self.assertNotIn(index, pos[adr_path(1)].links)
        # ADR-0010 is cited by nothing but the index: still the pool
        pool = [b for b in lay.boxes if b.role == "pool"][0]
        self.assertTrue(pool.y <= pos[adr_path(10)].y < pool.y + pool.h)

    def test_pool_holds_the_uncited_and_the_ghost(self):
        pool_boxes = [b for b in self.layout.boxes if b.role == "pool"]
        self.assertEqual(len(pool_boxes), 1)
        box = pool_boxes[0]
        pos = {n.path: n for n in self.layout.nodes}
        for p in (adr_path(10), adr_path(11)):
            n = pos[p]
            self.assertTrue(box.x <= n.x and n.x + n.w <= box.x + box.w, p)
            self.assertTrue(box.y <= n.y and n.y + n.h <= box.y + box.h, p)
        self.assertFalse(box.y <= pos[adr_path(1)].y <= box.y + box.h)
        pool_labels = [lb for lb in self.layout.labels if lb.role == "pool"]
        self.assertEqual(len(pool_labels), 1)
        self.assertIn("2", pool_labels[0].text)

    def test_pool_caps_and_expands(self):
        c = hand_corpus()
        for n in range(20, 20 + POOL_MAX + 3):
            c.nodes[adr_path(n)] = adr(n)
        lay = layout_ladder(c)
        self.assert_frame_sound(lay)
        in_pool = [n for n in lay.nodes if n.kind == "adr" and n.in_count == 0]
        self.assertEqual(len(in_pool), POOL_MAX)
        more = [lb for lb in lay.labels if lb.role == "more" and "pool" in (lb.href or "")]
        self.assertEqual(len(more), 1)
        lifted = layout_ladder(c, expand=frozenset({"pool"}))
        self.assert_frame_sound(lifted)
        self.assertEqual(
            len([n for n in lifted.nodes if n.in_count == 0 and n.kind == "adr"]),
            POOL_MAX + 3 + 2,   # 10, ghost 11, and the added ones
        )

    def test_ghosts_draw_as_missing(self):
        pos = {n.path: n for n in self.layout.nodes}
        self.assertIn(GHOST_AREA, pos)
        self.assertTrue(pos[GHOST_AREA].ghost)
        self.assertEqual(pos[GHOST_AREA].state, "missing")
        self.assertTrue(pos[adr_path(11)].ghost)
        self.assertEqual(pos[adr_path(11)].state, "missing")
        self.assertEqual(pos[adr_path(2)].state, "superseded")
        self.assertEqual(pos[LIFECYCLE].state, "area")

    def test_edge_kinds_drawn(self):
        kinds = {e.kind for e in self.layout.edges}
        self.assertEqual(kinds, {"parent", "maps-area", "global", "cites"})
        # one cites line per shelf, from its owner, never from an ADR
        cites = [e for e in self.layout.edges if e.kind == "cites"]
        shelves = [b for b in self.layout.boxes if b.role == "shelf"]
        self.assertEqual(len(cites), len(shelves))
        self.assertEqual(len({e.src for e in cites}), len(cites))
        self.assertFalse(any(e.src.startswith("cortex/adr/") for e in cites))
        # a pair joined by both parent and maps-area draws one blue line
        blue = [(e.src, e.dst) for e in self.layout.edges if e.kind in ("parent", "maps-area")]
        pairs = {frozenset(p) for p in blue}
        self.assertEqual(len(pairs), len(blue))
        # dangling cite: no node, no edge
        self.assertFalse(any(e.dst == DANGLING for e in self.layout.edges))
        self.assertFalse(any(n.path == DANGLING for n in self.layout.nodes))

    def test_owner_lines_are_straight_into_their_frame(self):
        shelves = [b for b in self.layout.boxes if b.role == "shelf"]
        for e in self.layout.edges:
            if e.kind != "cites":
                continue
            segs = segments(e.d)
            self.assertEqual(len(segs), 1, e.d)
            x1, y1, x2, y2 = segs[0]
            self.assertEqual(y1, y2)
            self.assertTrue(any(b.y < y1 < b.y + b.h and x2 < b.x for b in shelves), e.d)

    def test_hover_links(self):
        pos = {n.path: n for n in self.layout.nodes}
        # lifecycle lights ADR-0001 although project.md owns it
        self.assertIn(adr_path(1), pos[LIFECYCLE].links)
        self.assertEqual(set(pos[adr_path(4)].links), {LIFECYCLE, BACKLOG})
        # supersedes neighbours light each other; adr → adr cites do not
        self.assertIn(adr_path(3), pos[adr_path(2)].links)
        self.assertNotIn(adr_path(4), pos[adr_path(3)].links)
        self.assertIn(adr_path(11), pos[adr_path(10)].links)
        self.assertEqual(pos[OBS].links, ())

    def test_focus_classes(self):
        lay = layout_ladder(self.corpus, focus=LIFECYCLE)
        f = {n.path: n.focus for n in lay.nodes}
        self.assertEqual(f[LIFECYCLE], "here")
        self.assertEqual(f[PROJECT], "both")       # maps-area in, parent out
        self.assertEqual(f[BACKLOG], "in")         # backlog cites lifecycle
        self.assertEqual(f[adr_path(2)], "out")
        self.assertEqual(f[CLAUDE], "far")
        self.assertEqual(f[OBS], "far")
        ef = {(e.src, e.dst): e.focus for e in lay.edges}
        # the parent line lifecycle→project is folded into the maps-area
        # line project→lifecycle (one blue arrow per pair), which is "in"
        self.assertNotIn((LIFECYCLE, PROJECT), ef)
        self.assertEqual(ef[(PROJECT, LIFECYCLE)], "in")
        self.assertEqual(ef[(LIFECYCLE, adr_path(2))], "out")
        self.assertEqual(ef[(PROJECT, adr_path(1))], "far")
        self.assertTrue(all(n.focus == "none" for n in self.layout.nodes))
        self.assertTrue(all(e.focus == "none" for e in self.layout.edges))

    def test_unknown_focus_is_no_focus(self):
        lay = layout_ladder(self.corpus, focus="docs/absent.md")
        self.assertTrue(all(n.focus == "none" for n in lay.nodes))

    def test_column_labels(self):
        cols = [lb for lb in self.layout.labels if lb.role == "column"]
        self.assertEqual(len(cols), 2)
        self.assertEqual([lb.x for lb in cols], sorted(lb.x for lb in cols))

    def test_empty_for_one_node(self):
        c = Corpus(root=Path("/nonexistent"))
        c.nodes[CLAUDE] = doc(CLAUDE, "constitution")
        lay = layout_ladder(c)
        self.assertTrue(lay.empty)
        self.assertTrue(lay.verdict)
        self.assert_frame_sound(lay)
        self.assertEqual(lay.total, 1)

    def test_empty_for_no_edges(self):
        c = Corpus(root=Path("/nonexistent"))
        c.nodes[CLAUDE] = doc(CLAUDE, "constitution")
        c.nodes[PROJECT] = doc(PROJECT, "root")
        c.nodes[adr_path(1)] = adr(1)
        lay = layout_ladder(c)
        self.assertTrue(lay.empty)
        self.assert_frame_sound(lay)
        self.assertEqual(len(lay.nodes), 3)
        self.assertEqual(lay.edges, [])

    def test_only_dangling_edges_is_empty(self):
        c = Corpus(root=Path("/nonexistent"))
        c.nodes[CLAUDE] = doc(CLAUDE, "constitution")
        c.nodes[PROJECT] = doc(PROJECT, "root")
        c.edges.append(DocEdge(src=PROJECT, dst=DANGLING, kind="cites", dangling=True))
        lay = layout_ladder(c)
        self.assertTrue(lay.empty)
        self.assert_frame_sound(lay)

    def test_no_edges_no_adrs_small_consumer(self):
        c = Corpus(root=Path("/nonexistent"))
        c.nodes[CLAUDE] = doc(CLAUDE, "constitution")
        c.nodes[PROJECT] = doc(PROJECT, "root", parent=CLAUDE)
        c.nodes[LIFECYCLE] = doc(LIFECYCLE, "area", parent=PROJECT)
        c.edges.append(DocEdge(src=PROJECT, dst=CLAUDE, kind="parent"))
        c.edges.append(DocEdge(src=LIFECYCLE, dst=PROJECT, kind="parent"))
        lay = layout_ladder(c)
        self.assertFalse(lay.empty)
        self.assert_frame_sound(lay)
        self.assertEqual(lay.boxes, [])
        self.assertEqual(len([lb for lb in lay.labels if lb.role == "column"]), 1)

    def test_deterministic(self):
        a = layout_ladder(hand_corpus(), focus=LIFECYCLE, expand=frozenset({"pool"}))
        b = layout_ladder(hand_corpus(), focus=LIFECYCLE, expand=frozenset({"pool"}))
        self.assertEqual(a, b)

    def test_counts_are_cites_only(self):
        pos = {n.path: n for n in self.layout.nodes}
        self.assertEqual(pos[adr_path(4)].in_count, 3)   # lifecycle, backlog, ADR-0003
        self.assertEqual(pos[adr_path(3)].out_count, 1)
        self.assertEqual(pos[LIFECYCLE].in_count, 1)      # backlog cites it; parent not counted
        self.assertEqual(pos[LIFECYCLE].out_count, 10)    # dangling excluded

    def test_marker_ids_differ_between_maps(self):
        strip = layout_neighbourhood(self.corpus, PROJECT)
        self.assertNotEqual(self.layout.marker_id, strip.marker_id)
        self.assertNotEqual(self.layout.marker_id, "ah")


# --- the neighbourhood strip -------------------------------------------------------

class StripTests(GeometryMixin, unittest.TestCase):
    def setUp(self):
        self.corpus = hand_corpus()

    def test_project_strip(self):
        lay = layout_neighbourhood(self.corpus, PROJECT)
        self.assert_frame_sound(lay)
        self.assertFalse(lay.empty)
        f = {n.path: n for n in lay.nodes}
        self.assertEqual(f[PROJECT].focus, "here")
        self.assertEqual(f[LIFECYCLE].focus, "both")
        self.assertEqual(f[GLOSSARY].focus, "both")
        self.assertEqual(f[CLAUDE].focus, "out")
        self.assertEqual(f[adr_path(1)].focus, "out")
        self.assertEqual(f[GHOST_AREA].focus, "out")
        self.assertTrue(f[GHOST_AREA].ghost)
        self.assertLess(f[LIFECYCLE].x, f[PROJECT].x)
        self.assertLess(f[PROJECT].x, f[CLAUDE].x)
        # a both node draws an in and an out edge
        kinds = {(e.src, e.dst, e.focus) for e in lay.edges}
        self.assertIn((LIFECYCLE, PROJECT, "in"), kinds)
        self.assertIn((PROJECT, LIFECYCLE, "out"), kinds)
        self.assertEqual(lay.verdict.split(" · ")[0].split()[0], "4")

    def test_left_side_sorted_in_index_order(self):
        lay = layout_neighbourhood(self.corpus, PROJECT)
        left = sorted((n for n in lay.nodes if n.focus in ("in", "both")), key=lambda n: n.y)
        self.assertEqual([n.path for n in left], [LIFECYCLE, BACKLOG, OBS, GLOSSARY])

    def test_side_caps_at_twelve(self):
        c = hand_corpus()
        for n in range(20, 36):
            c.nodes[adr_path(n)] = adr(n)
            c.edges.append(DocEdge(src=LIFECYCLE, dst=adr_path(n), kind="cites"))
        lay = layout_neighbourhood(c, LIFECYCLE)
        self.assert_frame_sound(lay)
        outs = [n for n in lay.nodes if n.focus == "out"]
        self.assertEqual(len(outs), SIDE_MAX)
        more = [lb for lb in lay.labels if lb.role == "more"]
        self.assertEqual(len(more), 1)
        self.assertIsNone(more[0].href)
        self.assertTrue(all(e.dst in {n.path for n in lay.nodes} for e in lay.edges))

    def test_island_is_empty(self):
        lay = layout_neighbourhood(self.corpus, CONFIG)
        self.assertTrue(lay.empty)
        self.assert_frame_sound(lay)
        self.assertEqual([n.path for n in lay.nodes], [CONFIG])

    def test_unknown_focus_is_empty(self):
        lay = layout_neighbourhood(self.corpus, "docs/absent.md")
        self.assertTrue(lay.empty)
        self.assertEqual(lay.nodes, [])
        self.assertGreater(lay.width, 0)

    def test_deterministic(self):
        a = layout_neighbourhood(hand_corpus(), LIFECYCLE)
        b = layout_neighbourhood(hand_corpus(), LIFECYCLE)
        self.assertEqual(a, b)


# --- the real repo -------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[3]


class RealRepoTests(GeometryMixin, unittest.TestCase):
    def setUp(self):
        if not (REPO_ROOT / "cortex" / "adr").is_dir():
            self.skipTest("no cortex/adr in this checkout")
        try:
            from cortex_command.dashboard.docs.corpus import build_corpus
        except ImportError:
            self.skipTest("docs.corpus (Module A1) has not landed")
        self.corpus = build_corpus(REPO_ROOT)

    def test_ladder_no_overlaps(self):
        lay = layout_ladder(self.corpus)
        self.assert_frame_sound(lay)
        self.assertFalse(lay.empty)
        self.assertGreaterEqual(lay.total, 40)

    def test_ladder_expanded_no_overlaps(self):
        every = frozenset({n.path for n in self.corpus.governing()} | {"pool"})
        lay = layout_ladder(self.corpus, expand=every)
        self.assert_frame_sound(lay)
        self.assertEqual(lay.drawn, len(lay.nodes))
        self.assertGreaterEqual(lay.drawn, len(self.corpus.governing()))

    def test_every_governing_doc_has_a_strip(self):
        for n in self.corpus.governing():
            self.assert_frame_sound(layout_neighbourhood(self.corpus, n.path))


if __name__ == "__main__":
    unittest.main()
