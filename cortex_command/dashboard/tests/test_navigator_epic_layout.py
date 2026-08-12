"""Unit tests for cortex_command/dashboard/backlog/epic_layout.py.

Surface B's geometry is computed entirely on the server, so these tests are
the only place the numbers are checked — a bad coordinate reaches the
operator as a drawn frame, not as an exception. They assert structure and
arithmetic only: nothing here asserts that a sentence appears in the
verdict line, which repo policy forbids and which would make every future
rewording a test failure.

The epic shapes are taken from the real development corpus, because the
distribution is the design premise: 10 of 11 epics there declare **zero**
intra-epic ordering, so the pool-only frame is the path under test, not an
edge case. The three real shapes used are a 9-child epic with 2 intra-epic
edges and 2 external blockers, a 3-child epic whose only edges arrive from
outside it, and a 5-child epic with no edges at all.

Tests cover:
  - the wave/pool split: only an edge-touched node gets a wave
  - the five required shapes — 0 edges, 1 child, 9 children / 2 edges,
    40 children, external-only — with strictly positive dimensions
  - dimensions positive and children fully covered on a degenerate epic
    (no children, unknown id) as well
  - pool placement decided from measured widths: beside when it fits the
    panel, wrapped beneath when it does not, never wrapped without a spine
  - per-epic marker ids, unique across frames and never the shared "ah"
  - discharged edges drawn but never creating a spine
  - every elbow endpoint resolvable in ``pos``
  - byte-stable output: equal inputs produce equal layouts
  - cycles and self-loops terminating instead of hanging
  - non-numeric ids (UUID-shaped blocker refs) not raising
"""

from __future__ import annotations

import unittest

from cortex_command.dashboard.backlog.epic_layout import (
    NH,
    NW,
    PANEL_W,
    POOL_COLS,
    POOL_INSET,
    EpicLayout,
    LayoutContext,
    elbow,
    intra_waves,
    layout_epic,
)

# --- corpus-derived fixtures ------------------------------------------------
#
# Child lists and edges lifted from the development corpus's active slice.
# Ids are kept as the real ones so the shapes stay recognisable against the
# graph they came from; no assertion below depends on a literal id beyond
# membership in these fixtures.

EPIC_LARGE = "344"          # 9 children, 2 intra-epic edges, 2 external blockers
EPIC_EXTERNAL_ONLY = "263"  # 3 children, 0 intra-epic edges, 3 external edges
EPIC_FLAT = "455"           # 5 children, no edges of any kind
EPIC_SOLO = "126"           # 1 child

CORPUS_CHILDREN = {
    EPIC_LARGE: ["364", "388", "395", "417", "242", "381", "419", "430", "478"],
    EPIC_EXTERNAL_ONLY: ["384", "276", "278"],
    EPIC_FLAT: ["483", "484", "486", "487", "485"],
    EPIC_SOLO: ["138"],
    "139": ["147", "148", "439"],
    "236": ["247", "257"],
}

CORPUS_LIVE_EDGES = [
    ("242", "388"),   # intra-epic, EPIC_LARGE
    ("242", "417"),   # intra-epic, EPIC_LARGE
    ("331", "242"),   # external into EPIC_LARGE
    ("424", "430"),   # external into EPIC_LARGE
    ("331", "278"),   # external into EPIC_EXTERNAL_ONLY
    ("432", "439"),   # external into another epic entirely
    ("106", "107"),   # elsewhere in the slice: must not reach any frame
]

# The lapsed holds: #265 closed, so these constrain nothing but are still
# drawn. Both point into EPIC_EXTERNAL_ONLY.
CORPUS_DISCHARGED_EDGES = [
    ("265", "276"),
    ("265", "278"),
]


def corpus_ctx() -> LayoutContext:
    """The development corpus's epic shapes as one layout context."""
    return LayoutContext(
        children=CORPUS_CHILDREN,
        live_edges=CORPUS_LIVE_EDGES,
        discharged_edges=CORPUS_DISCHARGED_EDGES,
    )


def flat_ctx(epic_id: str, count: int) -> LayoutContext:
    """An epic of *count* children and no edges — the corpus's common case."""
    return LayoutContext(children={epic_id: [str(i) for i in range(1, count + 1)]})


class IntraWavesTests(unittest.TestCase):
    """The wave/pool distinction, which the whole surface is built on."""

    def test_only_edge_touched_nodes_get_a_wave(self):
        """A child no sibling constrains is ABSENT from the mapping.

        Returning 0 for it would place it in the first column of a declared
        sequence that was never declared, which is the exact claim this
        surface exists to avoid making.
        """
        kids = ["1", "2", "3", "4"]
        wave, sub = intra_waves(kids, [("1", "2")])

        self.assertEqual({"1": 0, "2": 1}, wave)
        self.assertEqual([("1", "2")], sub)
        self.assertNotIn("3", wave)
        self.assertNotIn("4", wave)

    def test_no_edges_yields_no_waves(self):
        wave, sub = intra_waves(["1", "2", "3"], [])
        self.assertEqual({}, wave)
        self.assertEqual([], sub)

    def test_edges_outside_the_epic_are_discarded(self):
        """Both an inbound external edge and an unrelated one are filtered."""
        wave, sub = intra_waves(["1", "2"], [("9", "1"), ("7", "8")])
        self.assertEqual({}, wave)
        self.assertEqual([], sub)

    def test_longest_path_layering(self):
        """A node reachable by two paths takes the LONGEST, not the first."""
        wave, _sub = intra_waves(
            ["1", "2", "3", "4"],
            [("1", "2"), ("2", "3"), ("3", "4"), ("1", "4")],
        )
        self.assertEqual({"1": 0, "2": 1, "3": 2, "4": 3}, wave)

    def test_cycle_terminates(self):
        """A cycle must stop at the iteration bound, not hang.

        The layering is not cycle-*proof* — a cycle inflates its members'
        waves until the bound is hit. It is cycle-*safe*: the bound is one
        relaxation pass per node, so the worst case is that many passes
        times the edge count, and the partial layering left behind is still
        a drawable frame rather than an exception or a spin.
        """
        wave, sub = intra_waves(["1", "2", "3"], [("1", "2"), ("2", "1")])

        self.assertEqual({"1", "2"}, set(wave))
        self.assertEqual(2, len(sub))
        self.assertLessEqual(max(wave.values()), (len(wave) + 1) * len(sub))

        cyclic = layout_epic(
            "1",
            LayoutContext(
                children={"1": ["1", "2", "3"]},
                live_edges=[("1", "2"), ("2", "1")],
            ),
        )
        self.assertGreater(cyclic.width, 0)
        self.assertGreater(cyclic.height, 0)

    def test_self_loop_is_dropped(self):
        """A self-loop would relax forever; it is discarded, not survived."""
        wave, sub = intra_waves(["1", "2"], [("1", "1"), ("1", "2")])
        self.assertEqual([("1", "2")], sub)
        self.assertEqual({"1": 0, "2": 1}, wave)

    def test_duplicate_edges_collapse(self):
        _wave, sub = intra_waves(["1", "2"], [("1", "2"), ("1", "2")])
        self.assertEqual([("1", "2")], sub)

    def test_integer_ids_are_stringified(self):
        """The snapshot's child ids are ints while items is str-keyed."""
        wave, sub = intra_waves([1, 2], [(1, 2)])
        self.assertEqual({"1": 0, "2": 1}, wave)
        self.assertEqual([("1", "2")], sub)


class RequiredShapeTests(unittest.TestCase):
    """The five shapes the build contract names, plus the empty epic."""

    def assert_frame_is_drawable(self, layout: EpicLayout, expected_children: int):
        """Every invariant that must hold for any frame, whatever its shape."""
        self.assertGreater(layout.width, 0)
        self.assertGreater(layout.height, 0)
        self.assertEqual(expected_children, layout.total)
        # Spine and pool partition the children exactly: nothing is drawn
        # twice and nothing falls off the frame.
        self.assertEqual(
            expected_children, len(layout.spine) + len(layout.pool)
        )
        self.assertEqual(set(), set(layout.spine) & set(layout.pool))
        for node in list(layout.spine) + list(layout.pool) + list(layout.externals):
            self.assertIn(node, layout.pos)
            x, y = layout.pos[node]
            self.assertGreaterEqual(x, 0)
            self.assertGreaterEqual(y, 0)
            # A node must fit inside the frame it was measured for.
            self.assertLessEqual(x + NW, layout.width)
            self.assertLessEqual(y + NH, layout.height)

    def test_zero_edges_is_the_designed_path(self):
        """10 of 11 corpus epics land here: no spine, every child pooled."""
        layout = layout_epic(EPIC_FLAT, corpus_ctx())

        self.assert_frame_is_drawable(layout, 5)
        self.assertEqual([], layout.spine)
        self.assertEqual(0, layout.ncols)
        self.assertEqual(0, layout.constrained)
        self.assertEqual(5, len(layout.pool))
        self.assertIsNotNone(layout.pool_box)
        self.assertEqual([], layout.elbows)
        # Not "wrapped": there is no spine for the pool to have wrapped under.
        self.assertFalse(layout.wrapped)

    def test_one_child(self):
        layout = layout_epic(EPIC_SOLO, corpus_ctx())

        self.assert_frame_is_drawable(layout, 1)
        self.assertEqual(1, len(layout.pool))
        self.assertEqual([], layout.spine)
        self.assertIsNotNone(layout.pool_box)

    def test_nine_children_two_edges(self):
        """The corpus's largest epic: a small spine and a large pool."""
        layout = layout_epic(EPIC_LARGE, corpus_ctx())

        self.assert_frame_is_drawable(layout, 9)
        # Two edges from one source touch three nodes; the other six pool.
        self.assertEqual(["242", "388", "417"], layout.spine)
        self.assertEqual(3, layout.constrained)
        self.assertEqual(6, len(layout.pool))
        self.assertEqual(2, layout.ncols)
        # Both intra-epic edges drawn, plus one elbow per external blocker.
        kinds = [e["kind"] for e in layout.elbows]
        self.assertEqual(2, kinds.count("live"))
        self.assertEqual(["331", "424"], layout.externals)
        self.assertEqual(2, kinds.count("external"))

    def test_forty_children(self):
        """A pool far wider than the panel packs into POOL_COLS columns."""
        layout = layout_epic("900", flat_ctx("900", 40))

        self.assert_frame_is_drawable(layout, 40)
        self.assertEqual(40, len(layout.pool))
        # Placement must stay inside the panel budget even at this size.
        self.assertLessEqual(layout.width, PANEL_W)
        # 40 nodes in 4 columns is 10 rows, and every one has its own row.
        rows = {y for _x, y in layout.pos.values()}
        self.assertEqual(10, len(rows))

    def test_external_only_edge(self):
        """Every edge arrives from outside: still no spine, still no order."""
        layout = layout_epic(EPIC_EXTERNAL_ONLY, corpus_ctx())

        self.assert_frame_is_drawable(layout, 3)
        self.assertEqual([], layout.spine)
        self.assertEqual(0, layout.ncols)
        self.assertEqual(3, len(layout.pool))
        # One live external blocker and one already-closed one, deduped: #265
        # blocks two of the three children through a single node.
        self.assertEqual(["265", "331"], layout.externals)
        self.assertEqual(3, len(layout.elbows))
        self.assertEqual(
            {"external": 1, "discharged": 2},
            {
                kind: [e["kind"] for e in layout.elbows].count(kind)
                for kind in {e["kind"] for e in layout.elbows}
            },
        )

    def test_epic_with_no_children_still_has_a_frame(self):
        """A childless or unknown epic must degrade, not raise."""
        for epic_id in ("900", EPIC_LARGE):
            with self.subTest(epic_id=epic_id):
                layout = layout_epic(epic_id, LayoutContext(children={}))
                self.assert_frame_is_drawable(layout, 0)
                self.assertIsNone(layout.pool_box)
                self.assertEqual([], layout.elbows)
                self.assertEqual([], layout.externals)

    def test_every_corpus_epic_is_drawable(self):
        """No shape in the real slice produces a bad frame."""
        ctx = corpus_ctx()
        for epic_id, children in CORPUS_CHILDREN.items():
            with self.subTest(epic=epic_id):
                self.assert_frame_is_drawable(
                    layout_epic(epic_id, ctx), len(children)
                )


class PoolPlacementTests(unittest.TestCase):
    """Beside or beneath is decided in Python, from measured widths."""

    def test_pool_sits_beside_a_spine_when_it_fits(self):
        ctx = LayoutContext(
            children={"1": ["10", "11", "12"]}, live_edges=[("10", "11")]
        )
        layout = layout_epic("1", ctx)

        self.assertEqual(["12"], layout.pool)
        self.assertFalse(layout.wrapped)
        self.assertIsNotNone(layout.pool_box)
        pool_x, pool_y, _w, _h = layout.pool_box
        spine_right = max(x for x, _y in (layout.pos[n] for n in layout.spine)) + NW
        # Beside means: starts right of the spine, and level with its top.
        self.assertGreater(pool_x, spine_right)
        self.assertLess(pool_y, min(y for _x, y in layout.pos.values()) + NH)
        self.assertLessEqual(layout.width, PANEL_W)

    def test_pool_wraps_beneath_when_it_does_not_fit(self):
        layout = layout_epic(EPIC_LARGE, corpus_ctx())

        self.assertTrue(layout.wrapped)
        pool_x, pool_y, _w, _h = layout.pool_box
        spine_bottom = max(y for _x, y in (layout.pos[n] for n in layout.spine)) + NH
        self.assertGreater(pool_y, spine_bottom)
        # Wrapped means flush with the spine's own left edge — which is not
        # the frame's left edge when an external-blocker column precedes it.
        spine_left = min(x for x, _y in (layout.pos[n] for n in layout.spine))
        self.assertEqual(pool_x, spine_left)

    def test_wrapped_is_false_whenever_there_is_no_spine(self):
        """"Wrapped" is a claim about a spine; without one it cannot be true."""
        for count in (1, 2, 9, 40):
            with self.subTest(children=count):
                layout = layout_epic("1", flat_ctx("1", count))
                self.assertFalse(layout.wrapped)

    def test_pool_never_overflows_the_panel_on_its_own(self):
        """Only a spine may push a frame past the panel; a pool may not.

        A frame wider than the panel pans horizontally, which a long
        declared spine earns. A pool spilling over — because its column
        count ignored the external-blocker column that shifted its origin —
        would make the operator pan to read nodes that had no order to show
        in the first place.
        """
        ctx = corpus_ctx()
        for epic_id in CORPUS_CHILDREN:
            with self.subTest(epic=epic_id):
                layout = layout_epic(epic_id, ctx)
                if layout.pool_box is not None:
                    pool_x, _y, pool_w, _h = layout.pool_box
                    self.assertLessEqual(pool_x + pool_w + 26, PANEL_W)

    def test_pool_keeps_its_full_column_count_when_it_fits(self):
        """The panel budget lowers the column ceiling; it does not replace it."""
        layout = layout_epic("900", flat_ctx("900", 40))
        xs = sorted({x for x, _y in layout.pos.values()})
        self.assertEqual(POOL_COLS, len(xs))

    def test_pool_box_encloses_every_pool_node(self):
        for epic_id in (EPIC_FLAT, EPIC_LARGE, EPIC_EXTERNAL_ONLY):
            with self.subTest(epic=epic_id):
                layout = layout_epic(epic_id, corpus_ctx())
                bx, by, bw, bh = layout.pool_box
                for node in layout.pool:
                    x, y = layout.pos[node]
                    self.assertGreaterEqual(x, bx)
                    self.assertGreaterEqual(y, by)
                    self.assertLessEqual(x + NW, bx + bw)
                    self.assertLessEqual(y + NH, by + bh)

    def test_pool_box_is_none_when_every_child_is_on_the_spine(self):
        ctx = LayoutContext(children={"1": ["10", "11"]}, live_edges=[("10", "11")])
        layout = layout_epic("1", ctx)

        self.assertEqual([], layout.pool)
        self.assertIsNone(layout.pool_box)


class MarkerIdTests(unittest.TestCase):
    """G4: a shared marker id costs every frame but the first its arrowheads."""

    def test_marker_id_is_namespaced_per_epic(self):
        ctx = corpus_ctx()
        ids = [layout_epic(e, ctx).marker_id for e in CORPUS_CHILDREN]

        self.assertEqual(len(ids), len(set(ids)))
        self.assertNotIn("ah", ids)
        for marker_id, epic_id in zip(ids, CORPUS_CHILDREN, strict=True):
            self.assertEqual(f"arw-e{epic_id}", marker_id)

    def test_marker_id_is_id_safe_for_an_odd_epic_id(self):
        layout = layout_epic("a b/c", LayoutContext(children={}))
        self.assertEqual("arw-ea-b-c", layout.marker_id)


class EdgeGeometryTests(unittest.TestCase):
    """Elbows, and the guarantee that both ends of one are placed."""

    def test_every_elbow_endpoint_is_positioned(self):
        ctx = corpus_ctx()
        for epic_id in CORPUS_CHILDREN:
            layout = layout_epic(epic_id, ctx)
            for edge in layout.elbows:
                with self.subTest(epic=epic_id, edge=edge["path"]):
                    self.assertIn(edge["src"], layout.pos)
                    self.assertIn(edge["dst"], layout.pos)
                    self.assertTrue(edge["path"].startswith("M "))

    def test_discharged_intra_edge_does_not_create_a_spine(self):
        """A lapsed hold is drawn, but it constrains nothing.

        This is the one place the two edge classes must behave differently:
        a discharged blocker means the child is startable today, so treating
        it as ordering would re-assert exactly the false constraint the
        board exists to retract.
        """
        ctx = LayoutContext(
            children={"1": ["10", "11"]}, discharged_edges=[("10", "11")]
        )
        layout = layout_epic("1", ctx)

        self.assertEqual([], layout.spine)
        self.assertEqual(0, layout.ncols)
        self.assertEqual(["10", "11"], layout.pool)
        self.assertEqual(["discharged"], [e["kind"] for e in layout.elbows])

    def test_elbow_path_is_integral(self):
        """Float coordinates would break byte-identical re-render."""
        self.assertEqual("M 0 0 H 50 V 20 H 92", elbow(0, 0, 100, 20, 50))

    def test_elbow_routes_through_the_given_lane_not_the_midpoint(self):
        """The lane is an input, and nothing recomputes it from the endpoints.

        A midpoint is clear only for a hop into the very next column; for any
        longer hop it lands inside an intervening node box. Passing a lane
        that is deliberately not the midpoint pins that the caller's channel
        is the one used.
        """
        self.assertEqual("M 0 0 H 12 V 20 H 92", elbow(0, 0, 100, 20, 12))

    def _segments(self, path: str) -> list[tuple[str, int, int, int]]:
        """Decompose an ``M/H/V`` path into axis-aligned segments.

        ``("H", lo, hi, y)`` for a horizontal run and ``("V", lo, hi, x)`` for
        a vertical one, endpoints normalised low-to-high so a run drawn
        right-to-left compares the same as one drawn left-to-right.
        """
        tokens = path.split()
        out: list[tuple[str, int, int, int]] = []
        x, y = int(tokens[1]), int(tokens[2])
        i = 3
        while i < len(tokens):
            if tokens[i] == "H":
                nxt = int(tokens[i + 1])
                out.append(("H", min(x, nxt), max(x, nxt), y))
                x = nxt
            else:
                nxt = int(tokens[i + 1])
                out.append(("V", min(y, nxt), max(y, nxt), x))
                y = nxt
            i += 2
        return out

    def test_no_edge_passes_through_a_node_box(self):
        """The invariant the whole lane mechanism exists to hold.

        An arrow that runs through an unrelated node box asserts a
        relationship between two tickets that have none, and it does it in
        the one channel this surface has for saying what holds what. Before
        the routing lanes this failed on two of the corpus's five framed
        epics — ten segments in all, three of them arrows crossing the dashed
        enclosure of an epic whose own label says its children are unordered.

        Endpoints are excluded: an edge is *supposed* to touch the boxes it
        joins.
        """
        ctx = corpus_ctx()
        for epic_id in CORPUS_CHILDREN:
            layout = layout_epic(epic_id, ctx)
            for edge in layout.elbows:
                for kind, lo, hi, fixed in self._segments(edge["path"]):
                    for node, (nx, ny) in layout.pos.items():
                        if node in (edge["src"], edge["dst"]):
                            continue
                        if kind == "H":
                            hit = ny <= fixed <= ny + NH and lo < nx + NW and hi > nx
                        else:
                            hit = nx <= fixed <= nx + NW and lo < ny + NH and hi > ny
                        with self.subTest(epic=epic_id, edge=edge["path"], node=node):
                            self.assertFalse(hit)

    def test_two_blockers_never_share_a_vertical_lane(self):
        """Distinct sources get distinct channels, so a fork stays legible.

        Two trunks on one x would merge into a single drawn line carrying two
        unrelated claims. Edges from the *same* blocker do share a lane, and
        should: that is one trunk forking, which is the true shape.
        """
        layout = layout_epic(EPIC_EXTERNAL_ONLY, corpus_ctx())
        runs: list[tuple[int, int, int, str]] = []
        for edge in layout.elbows:
            for kind, lo, hi, fixed in self._segments(edge["path"]):
                if kind == "V" and hi > lo:
                    runs.append((fixed, lo, hi, edge["src"]))

        self.assertTrue(runs, "the fixture must actually draw vertical runs")
        for i, (x1, lo1, hi1, src1) in enumerate(runs):
            for x2, lo2, hi2, src2 in runs[i + 1 :]:
                if src1 == src2:
                    continue
                with self.subTest(a=src1, b=src2):
                    self.assertFalse(x1 == x2 and min(hi1, hi2) > max(lo1, lo2))

    def test_externally_held_children_sit_in_the_pools_first_column(self):
        """The property that makes a clean left approach possible at all.

        An external arrow reaches a pool node from the left; the pool has no
        routing gutters between its columns, so a target outside column 0 can
        only be reached by crossing a sibling.
        """
        ctx = corpus_ctx()
        for epic_id in CORPUS_CHILDREN:
            layout = layout_epic(epic_id, ctx)
            if not layout.pool_box:
                continue
            held = {
                edge["dst"]
                for edge in layout.elbows
                if edge["src"] in layout.externals and edge["dst"] in layout.pool
            }
            first_col_x = layout.pool_box[0] + POOL_INSET
            for node in held:
                with self.subTest(epic=epic_id, node=node):
                    self.assertEqual(first_col_x, layout.pos[node][0])

    def test_externals_do_not_overlap_the_spine(self):
        layout = layout_epic(EPIC_LARGE, corpus_ctx())
        ext_right = max(x for x, _y in (layout.pos[n] for n in layout.externals)) + NW
        own_left = min(
            x for x, _y in (layout.pos[n] for n in layout.spine + layout.pool)
        )
        self.assertLessEqual(ext_right, own_left)


class RobustnessTests(unittest.TestCase):
    """Open vocabularies and repeat renders."""

    def test_repeat_layout_is_identical(self):
        """An unchanged 30s poll must re-render byte-for-byte."""
        ctx = corpus_ctx()
        for epic_id in CORPUS_CHILDREN:
            with self.subTest(epic=epic_id):
                self.assertEqual(
                    layout_epic(epic_id, ctx), layout_epic(epic_id, ctx)
                )

    def test_child_id_order_does_not_change_the_layout(self):
        """Placement is derived from the ids, not from the input's order."""
        forward = layout_epic("1", LayoutContext(children={"1": ["10", "9", "11"]}))
        reverse = layout_epic("1", LayoutContext(children={"1": ["11", "10", "9"]}))
        self.assertEqual(forward, reverse)

    def test_non_numeric_ids_do_not_raise(self):
        """Blocker refs are an open field: UUIDs and free text both reach here."""
        ctx = LayoutContext(
            children={"1": ["10", "abc"]},
            live_edges=[("3f2a-not-a-number", "10"), ("10", "abc")],
        )
        layout = layout_epic("1", ctx)

        self.assertEqual(["3f2a-not-a-number"], layout.externals)
        self.assertEqual(["10", "abc"], layout.spine)
        self.assertGreater(layout.width, 0)
        self.assertGreater(layout.height, 0)

    def test_duplicate_children_are_placed_once(self):
        layout = layout_epic("1", LayoutContext(children={"1": ["10", "10", "11"]}))
        self.assertEqual(2, layout.total)
        self.assertEqual(["10", "11"], layout.pool)

    def test_verdict_counts_match_the_partition(self):
        """The verdict's numbers are the frame's numbers, not a recount."""
        ctx = corpus_ctx()
        for epic_id, children in CORPUS_CHILDREN.items():
            with self.subTest(epic=epic_id):
                layout = layout_epic(epic_id, ctx)
                self.assertEqual(len(layout.spine), layout.constrained)
                self.assertEqual(len(children), layout.total)
                self.assertIn(str(layout.constrained), layout.verdict)
                self.assertIn(str(layout.total), layout.verdict)


if __name__ == "__main__":
    unittest.main()
