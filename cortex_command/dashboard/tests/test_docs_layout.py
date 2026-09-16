"""Unit tests for cortex_command/dashboard/docs/layout.py.

The ladder and the strip are computed entirely on the server, so these
tests are where the numbers are checked — a bad coordinate reaches the
operator as a drawn frame, not an exception. They assert structure and
arithmetic: boxes inside the frame, boxes not overlapping, every edge
segment clear of every box it does not start or end at, ints everywhere,
and byte-stable output. Nothing here pins a verdict sentence.

The hand corpus is built from ``model`` dataclasses with no disk: a
constitution, a policy, a root, a config, a readme, three mapped areas plus
a glossary, twelve ADRs (one shelf of exactly seven so the six-cap fires,
one uncited so the pool exists, one superseded, one ghost successor), a
dangling cite and an ADR-to-ADR cite that must never be drawn.
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
    # cites: CLAUDE owns 9; policies owns 8; project owns 1 and 3;
    # lifecycle owns 2,4,5,6,7,12,13 (seven, so the six-cap fires)
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


def crosses_box(seg: tuple[int, int, int, int], bx: int, by: int) -> bool:
    """True when the segment passes through the *interior* of a box."""
    x1, y1, x2, y2 = seg
    lo_x, hi_x = min(x1, x2), max(x1, x2)
    lo_y, hi_y = min(y1, y2), max(y1, y2)
    return lo_x < bx + NW and hi_x > bx and lo_y < by + NH and hi_y > by


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
            self.assertLessEqual(n.x + NW, layout.width, n.path)
            self.assertLessEqual(n.y + NH, layout.height, n.path)
        nodes = layout.nodes
        for i, a in enumerate(nodes):
            for b in nodes[i + 1:]:
                overlap = (
                    a.x < b.x + NW and a.x + NW > b.x
                    and a.y < b.y + NH and a.y + NH > b.y
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
                        crosses_box(seg, n.x, n.y),
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
        self.assertLess(xs[LIFECYCLE], xs[adr_path(1)])
        self.assertEqual(len({n.x for n in self.layout.nodes if n.kind == "adr"}), 1)

    def test_shelf_collapses_at_seven(self):
        drawn = {n.path for n in self.layout.nodes}
        lifecycle_shelf = [2, 4, 5, 6, 7, 12, 13]
        shown = [n for n in lifecycle_shelf if adr_path(n) in drawn]
        self.assertEqual(len(shown), SHELF_MAX)
        self.assertNotIn(adr_path(13), drawn)
        more = [lb for lb in self.layout.labels if lb.role == "more"]
        self.assertEqual(len(more), 1)
        self.assertIn(LIFECYCLE, more[0].href or "")
        self.assertTrue(more[0].href.startswith("?expand="))
        # no edge into the hidden chip
        self.assertFalse(any(e.dst == adr_path(13) for e in self.layout.edges))

    def test_expand_lifts_the_cap(self):
        lay = layout_ladder(self.corpus, expand=frozenset({LIFECYCLE}))
        self.assert_frame_sound(lay)
        drawn = {n.path for n in lay.nodes}
        self.assertIn(adr_path(13), drawn)
        self.assertEqual([lb for lb in lay.labels if lb.role == "more"], [])
        self.assertTrue(any(e.dst == adr_path(13) for e in lay.edges))

    def test_focus_on_hidden_adr_lifts_its_shelf(self):
        lay = layout_ladder(self.corpus, focus=adr_path(13))
        here = [n for n in lay.nodes if n.focus == "here"]
        self.assertEqual([n.path for n in here], [adr_path(13)])

    def test_shelf_ownership_is_first_citer(self):
        ys = {n.path: n.y for n in self.layout.nodes}
        # CLAUDE owns 9; policies (index before project) owns 8; project owns
        # 1 and 3. The owner's box aligns to its shelf's first chip.
        self.assertEqual(ys[CLAUDE], ys[adr_path(9)])
        self.assertEqual(ys[POLICIES], ys[adr_path(8)])
        self.assertLess(ys[adr_path(9)], ys[adr_path(8)])
        self.assertEqual(ys[PROJECT], min(ys[adr_path(1)], ys[adr_path(3)]))
        self.assertLess(ys[adr_path(8)], ys[adr_path(1)])
        self.assertLess(ys[adr_path(3)], ys[adr_path(2)])
        self.assertEqual(ys[LIFECYCLE], ys[adr_path(2)])
        shelf = [lb for lb in self.layout.labels if lb.role == "shelf"]
        self.assertEqual(len(shelf), 4)
        self.assertTrue(shelf[0].text.startswith("CLAUDE.md cites 1"))
        self.assertTrue(shelf[1].text.startswith("policies.md cites 1"))

    def test_pool_holds_the_uncited_and_the_ghost(self):
        pool_boxes = [b for b in self.layout.boxes if b.role == "pool"]
        self.assertEqual(len(pool_boxes), 1)
        box = pool_boxes[0]
        pos = {n.path: n for n in self.layout.nodes}
        for p in (adr_path(10), adr_path(11)):
            n = pos[p]
            self.assertTrue(box.x <= n.x and n.x + NW <= box.x + box.w, p)
            self.assertTrue(box.y <= n.y and n.y + NH <= box.y + box.h, p)
        self.assertFalse(box.y <= pos[adr_path(1)].y <= box.y + box.h)
        pool_labels = [lb for lb in self.layout.labels if lb.role == "pool"]
        self.assertEqual(len(pool_labels), 1)
        self.assertIn("2", pool_labels[0].text)

    def test_pool_caps_at_eight_and_expands(self):
        c = hand_corpus()
        for n in range(20, 31):
            c.nodes[adr_path(n)] = adr(n)
        lay = layout_ladder(c)
        self.assert_frame_sound(lay)
        in_pool = [n for n in lay.nodes if n.kind == "adr" and n.in_count == 0]
        self.assertEqual(len(in_pool), POOL_MAX)
        more = [lb for lb in lay.labels if lb.role == "more" and "pool" in (lb.href or "")]
        self.assertEqual(len(more), 1)
        lifted = layout_ladder(c, expand=frozenset({"pool"}))
        self.assert_frame_sound(lifted)
        self.assertEqual(len([n for n in lifted.nodes if n.in_count == 0 and n.kind == "adr"]), 13)  # 10, ghost 11, 20–30

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
        self.assertEqual(kinds, {"parent", "maps-area", "global", "cites", "supersedes"})
        # adr → adr cites are counts, never lines
        self.assertFalse(any(
            e.kind == "cites" and e.src.startswith("cortex/adr/") for e in self.layout.edges
        ))
        # a pair joined by both parent and maps-area draws one blue line
        blue = [(e.src, e.dst) for e in self.layout.edges if e.kind in ("parent", "maps-area")]
        pairs = {frozenset(p) for p in blue}
        self.assertEqual(len(pairs), len(blue))
        # dangling cite: no node, no edge
        self.assertFalse(any(e.dst == DANGLING for e in self.layout.edges))
        self.assertFalse(any(n.path == DANGLING for n in self.layout.nodes))

    def test_multi_column_edges_use_the_top_channel(self):
        top = min(n.y for n in self.layout.nodes)
        trunks = [e for e in self.layout.edges if e.kind == "cites" and e.src in (PROJECT, POLICIES, CLAUDE)]
        self.assertTrue(trunks)
        for e in trunks:
            segs = segments(e.d)
            self.assertEqual(len(segs), 5, e.d)
            _x1, y1, _x2, y2 = segs[2]
            self.assertEqual(y1, y2)
            self.assertLess(y1, top, e.d)
        # one trunk per source: every project.md trunk shares its channel y
        ys = {segments(e.d)[2][1] for e in trunks if e.src == PROJECT}
        self.assertEqual(len(ys), 1)

    def test_supersedes_routes_right_of_the_adr_column(self):
        right = max(n.x + NW for n in self.layout.nodes)
        sup = [e for e in self.layout.edges if e.kind == "supersedes"]
        self.assertEqual(len(sup), 2)
        for e in sup:
            _x1, _y1, lane_x, _y2 = segments(e.d)[0]
            self.assertGreater(lane_x, right)
        self.assertGreater(self.layout.width, right + PAD)

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
        self.assertEqual(ef[(POLICIES, adr_path(8))], "far")
        self.assertTrue(all(n.focus == "none" for n in self.layout.nodes))
        self.assertTrue(all(e.focus == "none" for e in self.layout.edges))

    def test_unknown_focus_is_no_focus(self):
        lay = layout_ladder(self.corpus, focus="docs/absent.md")
        self.assertTrue(all(n.focus == "none" for n in lay.nodes))

    def test_column_labels(self):
        cols = [lb for lb in self.layout.labels if lb.role == "column"]
        self.assertEqual(len(cols), 4)
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
        self.assertEqual(len([lb for lb in lay.labels if lb.role == "column"]), 3)

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
