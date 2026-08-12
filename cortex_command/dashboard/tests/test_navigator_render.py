"""Rendering tests for the backlog navigator's two surfaces.

Every assertion here is about *structure*, never about prose. That is a repo
policy (``docs/policies.md``) and it is also the only kind of assertion worth
making about these templates: the copy is assembled in ``backlog/view.py`` from
live values, so a test pinning a sentence would be pinning a value that is
supposed to move, while the four defects this file guards against are all
structural and all were real in the design bake-off that produced the surfaces.

The four:

* **Duplicate ``id``.** One prototype emitted ``id="ah"`` seven times for its
  arrowhead marker and referenced ``url(#ah)`` nine times; every reference
  resolves document-wide to the first definition, so the moment the top frame
  left the DOM every remaining frame silently lost its arrowheads. On a page
  that morph-swaps its panels every 30s, the top frame *will* leave the DOM.
  Duplicate ids also poison idiomorph's id keying outright.
* **Nested ``<a>``.** Another emitted a link inside a row that was itself a
  link. That is invalid HTML, the parser unnests it, and 41% of that
  prototype's board came apart.
* **Byte instability.** The surfaces poll every 30s with ``hx-swap="morph"``.
  A render that differs from the previous one on unchanged data moves the
  operator's cursor for no reason, which is why the staleness term is anchored
  to the corpus's own latest ``updated`` rather than to the wall clock.
* **The degenerate corpus.** cortex-command's own slice is four items and zero
  epics. A ``max()`` over an empty collection without a ``default=`` is what
  crashed the winning prototype on it, and "renders a correct small page"
  rather than "renders an error" is the requirement.

Inputs are built by ``ticket_feed.build_backlog_snapshot`` over a markdown
corpus on disk, not hand-transcribed, for the reason the retired triage-board
tests gave: these surfaces are joins across snapshot collections, a bad join
renders blank rather than raising, and a hand-written snapshot would assert
only that the transcription matches itself.
"""

from __future__ import annotations

import hashlib
import tempfile
import types
import unittest
from html import escape
from html.parser import HTMLParser
from pathlib import Path

from cortex_command.dashboard.app import templates
from cortex_command.dashboard.backlog import bands as bands_mod
from cortex_command.dashboard.backlog.graph import normalize_ref
from cortex_command.dashboard.backlog.view import build_navigator
from cortex_command.dashboard.data import parse_backlog_titles
from cortex_command.dashboard.poller import DashboardState
from cortex_command.dashboard.ticket_feed import build_backlog_snapshot

# A corpus exercising every band and both epic paths in one slice:
#
#   1  epic container, three children -> a frame
#   2  keystone: blocks 3 and 4, one of which it solely blocks
#   3  blocked by 2 alone            -> band G, and freed by the counterfactual
#   4  blocked by 2 and by 9         -> band G, and NOT freed
#   5  deferred by status            -> band F
#   6  blocked only by a complete    -> band G' (hold lapsed)
#   7  status new                    -> band H
#   8  open vocabulary throughout    -> band E*, and the unknown-priority note
#   9  a second live blocker for 4, itself startable
#  10  epic container, one child     -> the tail
#  11  child of 10
#  12  child of an epic that is not on the board -> the tail, off-board arm
_CORPUS: tuple[tuple[int, str], ...] = (
    (1, """---
id: 1
title: "Epic: the framed group"
type: epic
status: backlog
priority: high
updated: 2026-03-01
---
container.
"""),
    (2, """---
id: 2
title: "Keystone — holds two others"
type: feature
status: backlog
priority: low
parent: 1
blocks: [3, 4]
updated: 2026-02-01
---
body.
"""),
    (3, """---
id: 3
title: "Held by the keystone alone"
type: feature
status: backlog
priority: high
parent: 1
blocked-by: [2]
updated: 2026-03-01
---
body.
"""),
    (4, """---
id: 4
title: "Held by two live blockers"
type: feature
status: backlog
priority: medium
parent: 1
blocked-by: [2, 9]
updated: 2026-03-01
---
body.
"""),
    (5, """---
id: 5
title: "Deferred by decision"
type: chore
status: deferred
priority: medium
updated: 2026-03-01
---
body.
"""),
    (6, """---
id: 6
title: "Hold lapsed — blocker already complete"
type: bug
status: backlog
priority: medium
blocked-by: [90]
updated: 2026-03-01
---
body.
"""),
    (7, """---
id: 7
title: "Untriaged"
type: feature
status: new
priority: low
updated: 2026-03-01
---
body.
"""),
    (8, """---
id: 8
title: "Open vocabulary everywhere"
type: ""
status: icebox
priority: p0
lifecycle_phase: spec
updated: 2026-03-01
---
body.
"""),
    (9, """---
id: 9
title: "The second blocker"
type: feature
status: backlog
priority: medium
blocks: [4]
updated: 2026-03-01
---
body.
"""),
    (10, """---
id: 10
title: "Epic: one child only"
type: epic
status: backlog
priority: low
updated: 2026-03-01
---
container.
"""),
    (11, """---
id: 11
title: "The only child"
type: feature
status: backlog
priority: low
parent: 10
updated: 2026-03-01
---
body.
"""),
    (12, """---
id: 12
title: "Child of an off-board parent"
type: feature
status: backlog
priority: low
parent: 90
updated: 2026-03-01
---
body.
"""),
    (90, """---
id: 90
title: "Already complete"
type: feature
status: complete
priority: medium
updated: 2026-01-01
---
body.
"""),
)

# The 5-item / 0-epic slice. cortex-command's own shape: no parent anywhere, no
# dependency edge anywhere, one deferred record so at least two bands exist.
_SMALL_CORPUS: tuple[tuple[int, str], ...] = tuple(
    (
        i,
        "---\nid: %d\ntitle: \"Small %d\"\ntype: feature\nstatus: %s\n"
        "priority: medium\nupdated: 2026-04-0%d\n---\nbody.\n"
        % (i, i, "deferred" if i == 5 else "backlog", i),
    )
    for i in range(1, 6)
)


def _fake_request(path: str = "/backlog") -> types.SimpleNamespace:
    """Minimal stand-in for the Starlette Request; base.html reads only the path."""
    return types.SimpleNamespace(url=types.SimpleNamespace(path=path))


def _state_for(corpus, tmp: Path) -> DashboardState:
    """Write *corpus* to disk and poll it into a DashboardState."""
    backlog = tmp / "cortex" / "backlog"
    lifecycle = tmp / "cortex" / "lifecycle"
    backlog.mkdir(parents=True, exist_ok=True)
    lifecycle.mkdir(parents=True, exist_ok=True)
    for item_id, text in corpus:
        (backlog / ("%d-item.md" % item_id)).write_text(text, encoding="utf-8")

    state = DashboardState()
    state.backlog_backend = "cortex-backlog"
    state.backlog_snapshot = build_backlog_snapshot(
        backlog,
        lifecycle,
        parse_backlog_titles(backlog).by_id,
        "2026-04-09T00:00:00+00:00",
    )
    return state


def _render(name: str, **context) -> str:
    """Render one fragment exactly as its route handler does."""
    return templates.env.get_template(name).render(
        request=_fake_request(), **context
    )


def _render_both(state: DashboardState) -> str:
    """The whole polled fragment.

    Named "both" from when the epic map was a peer page and the two fragments
    were concatenated so an id collision between them could not hide. They are
    one document now — that is exactly the "somebody later puts both panels on
    one page" case the concatenation was guarding against — so the id and
    anchor assertions run over the real page rather than a simulated one.
    """
    return _render("navigator.html", nav=build_navigator(state, None))


class _Structure(HTMLParser):
    """Collects the three structural facts the acceptance criteria name.

    Written against ``html.parser`` rather than a DOM library because the
    dashboard ships no parser dependency and these are counting problems: ids
    seen, anchor nesting depth reached, and the tag shape of the list
    surfaces. ``convert_charrefs`` stays on; entities are not what is under
    test.
    """

    #: Void elements never open a scope, so they must not push onto the stack.
    VOID = frozenset(
        {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
         "meta", "param", "source", "track", "wbr"}
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: list[str] = []
        self.nested_anchors: list[str] = []
        self.tags: dict[str, int] = {}
        self.th_scopes: list[str] = []
        self.svg_texts: list[str] = []
        # Every native tooltip source. `title="…"` on any element and a
        # `<title>` child inside an <svg> render the same grey OS tooltip,
        # which is what competed with the hover card.
        self.title_attrs: list[str] = []
        self._stack: list[str] = []
        self._in_svg_text = False

    def handle_starttag(self, tag, attrs) -> None:
        attributes = dict(attrs)
        if "id" in attributes:
            self.ids.append(attributes["id"])
        self.tags[tag] = self.tags.get(tag, 0) + 1
        if tag == "a" and "a" in self._stack:
            self.nested_anchors.append(attributes.get("href", ""))
        if tag == "th":
            self.th_scopes.append(attributes.get("scope", ""))
        if "title" in attributes:
            self.title_attrs.append(attributes["title"])
        if tag == "text":
            self._in_svg_text = True
            self.svg_texts.append("")
        if tag not in self.VOID:
            self._stack.append(tag)

    def handle_startendtag(self, tag, attrs) -> None:
        attributes = dict(attrs)
        if "id" in attributes:
            self.ids.append(attributes["id"])
        if "title" in attributes:
            self.title_attrs.append(attributes["title"])
        self.tags[tag] = self.tags.get(tag, 0) + 1

    def handle_endtag(self, tag) -> None:
        if tag == "text":
            self._in_svg_text = False
        if tag in self._stack:
            while self._stack:
                if self._stack.pop() == tag:
                    break

    def handle_data(self, data) -> None:
        if self._in_svg_text and self.svg_texts:
            self.svg_texts[-1] += data


def _parse(html: str) -> _Structure:
    parser = _Structure()
    parser.feed(html)
    return parser


class _Fixture(unittest.TestCase):
    """Base class owning the tmp corpus, so each subclass polls once."""

    CORPUS = _CORPUS

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.state = _state_for(cls.CORPUS, Path(cls._tmp.name))
        cls.html = _render_both(cls.state)
        cls.parsed = _parse(cls.html)
        # The model behind the markup, for the assertions that are joins
        # against it rather than counts over the tags.
        cls.nav = build_navigator(cls.state, None)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()


class TestNoDuplicateIds(_Fixture):
    """Every ``id`` in the rendered output is unique.

    Both surfaces render arrowhead markers, disclosures and pan containers with
    server-assigned ids, and all three break in a different way when an id
    repeats: ``url(#marker)`` resolves to the wrong definition, the
    open-details restore reattaches to the wrong ticket, and idiomorph keys two
    nodes as one.
    """

    def test_ids_are_unique_across_both_surfaces(self):
        seen: dict[str, int] = {}
        for value in self.parsed.ids:
            seen[value] = seen.get(value, 0) + 1
        duplicates = sorted(k for k, n in seen.items() if n > 1)
        self.assertEqual([], duplicates, "duplicate id= values: %s" % duplicates)

    def test_something_actually_carried_an_id(self):
        # Guards the assertion above against passing vacuously if the surfaces
        # ever stop emitting ids at all — at which point the disclosure restore
        # and the scroll preservation are silently dead.
        self.assertGreater(len(self.parsed.ids), 0)

    def test_every_details_carries_an_id(self):
        # A disclosure without a server-rendered id snaps shut on every 30s
        # morph, which is exactly the state default the band grammar replaced.
        details_with_id = [i for i in self.parsed.ids if i.startswith("nav-alt-")]
        self.assertEqual(self.parsed.tags.get("details", 0), len(details_with_id))


class TestNoNestedAnchors(_Fixture):
    """No ``<a>`` is a descendant of another ``<a>``, on either surface."""

    def test_zero_nested_anchors(self):
        self.assertEqual([], self.parsed.nested_anchors)

    def test_anchors_were_actually_rendered(self):
        # Every band row, tail row and node links out to /tickets/{id}; zero
        # anchors would mean the surfaces rendered without their click-through.
        self.assertGreater(self.parsed.tags.get("a", 0), 0)


class TestListsAreTables(_Fixture):
    """The list surfaces are real tables with column headers.

    A ranked list rendered as SVG text (one prototype emitted 0 ``<tr>`` and
    871 ``<text>``) puts every row's position at the mercy of a character
    advance for a font that is not bundled. Tables are the structural
    commitment that no row is placed by a measurement.
    """

    def test_rows_are_table_rows(self):
        self.assertGreater(self.parsed.tags.get("tr", 0), 0)
        self.assertGreater(self.parsed.tags.get("table", 0), 0)

    def test_column_headers_declare_scope(self):
        self.assertGreater(self.parsed.th_scopes.count("col"), 0)
        self.assertNotIn("", self.parsed.th_scopes, "a <th> carries no scope")

    def test_no_svg_text_anywhere(self):
        """An absence assertion, and it keeps a removal removed.

        The rule used to be "SVG text only for labels of at most three words",
        because the epic frames drew their enclosure and externals headings
        that way. There is no SVG on this surface any more: the frames drew two
        arrows across eleven groups and were replaced by a list and a line of
        text. Any ``<text>`` reappearing here is a diagram growing back, and
        with it row positions computed from a character advance for a font that
        is not bundled.
        """
        self.assertEqual([], self.parsed.svg_texts)

    def test_no_svg_title_element_anywhere(self):
        """An absence assertion, and the point of the change that made it true.

        A ``<title>`` child is a legitimate accessible name and that is why one
        was there — but browsers also paint it as an OS tooltip, so hovering a
        node produced the styled hover card and a grey system tooltip at once.
        The accessible name now comes from the anchor's own text, which no
        browser renders twice.
        """
        self.assertEqual(0, self.parsed.tags.get("title", 0))

    def test_no_native_title_attribute_anywhere(self):
        """The other spelling of the same defect.

        ``title="…"`` on any element renders the identical OS tooltip. Nothing
        on either surface may carry one, or the double-tooltip returns through
        a different door.
        """
        self.assertEqual([], self.parsed.title_attrs)

    def test_group_children_carry_their_ticket_title(self):
        """Every child the model names reaches the markup.

        Asserted as a join, not as prose: the words are the corpus's, and what
        is under test is that the data got there. A group that rendered its ids
        but dropped its titles would still look plausible on the page.
        """
        titles = [
            kid["title"]
            for group in self.nav["groups"]
            for kid in group["children"]
        ]
        self.assertTrue(titles, "the fixture must render at least one child")
        for title in titles:
            with self.subTest(title=title):
                self.assertIn(escape(title), self.html)


class TestByteStability(_Fixture):
    """The same snapshot rendered twice is byte-identical.

    This is a property of the *data*, not of the templates: the staleness term
    is measured against the corpus's own latest ``updated`` rather than against
    ``date.today()``, and every collection the view-model builds is ordered.
    Without both, an unchanged 30s poll would morph-swap a different document
    into the page every time.
    """

    def test_navigator_renders_identically(self):
        first = _render("navigator.html", nav=build_navigator(self.state, None))
        second = _render("navigator.html", nav=build_navigator(self.state, None))
        self.assertEqual(
            hashlib.sha256(first.encode()).hexdigest(),
            hashlib.sha256(second.encode()).hexdigest(),
        )

    def test_a_fresh_poll_of_unchanged_files_renders_identically(self):
        # The stronger form: not just the same view-model rendered twice, but
        # the whole path re-run from disk. A wall-clock read anywhere between
        # the files and the HTML fails here and passes above.
        again = _state_for(self.CORPUS, Path(self._tmp.name))
        self.assertEqual(
            hashlib.sha256(self.html.encode()).hexdigest(),
            hashlib.sha256(_render_both(again).encode()).hexdigest(),
        )


class TestBandCoverageIsRendered(_Fixture):
    """The board renders every record, and says so.

    G6 as a rendering assertion rather than only a partition one: a record that
    reaches no band vanishes from a read-only board silently, which is the
    worst failure available to a surface whose whole job is "what is on this".
    """

    def test_every_slice_id_reaches_a_field_row(self):
        nav = build_navigator(self.state, None)
        rendered = {row["id"] for seg in nav["field"] for row in seg["rows"]}
        self.assertEqual(set(self.state.backlog_snapshot["items"]), rendered)

    def test_every_record_lands_in_exactly_one_run(self):
        # The field is one table now, so a record appearing under two
        # disposition runs would read as two different tickets rather than as
        # the duplicate it is.
        ids = [row["id"] for seg in build_navigator(self.state, None)["field"]
               for row in seg["rows"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_reconciliation_totals_agree(self):
        recon = build_navigator(self.state, None)["census"]["reconciliation"]
        self.assertTrue(recon["ok"])
        self.assertEqual(recon["total"], recon["slice_total"])

    def test_no_run_renders_empty(self):
        # Zero-count bands are dropped by the view-model, never emitted as an
        # empty header. A "0 items" row is noise on a page whose whole claim is
        # that what you see is what is there.
        for seg in build_navigator(self.state, None)["field"]:
            self.assertGreater(seg["count"], 0)
            self.assertEqual(seg["count"], len(seg["rows"]))


class TestEveryGroupReachesTheSection(_Fixture):
    """Every parent group renders exactly once, whatever its size or status.

    The frame/tail split this replaced routed small and off-board groups to a
    second table with its own state vocabulary, which is how one off-slice
    ticket came to read ``complete`` in a frame and ``off board`` in the tail.
    One list, one vocabulary.
    """

    def test_groups_are_rendered_once_each(self):
        groups = build_navigator(self.state, None)["groups"]
        placed = [g["id"] for g in groups]
        self.assertEqual(len(placed), len(set(placed)), "a group rendered twice")

    def test_the_one_child_group_is_kept_not_dropped(self):
        # It used to be relegated to the tail for having too few children to
        # frame. There is no threshold now — a group of one is a fact about the
        # board and costs one row.
        groups = {g["id"]: g for g in build_navigator(self.state, None)["groups"]}
        self.assertIn("10", groups)
        self.assertEqual(1, groups["10"]["count"])

    def test_the_off_board_parent_is_kept_not_dropped(self):
        groups = {g["id"]: g for g in build_navigator(self.state, None)["groups"]}
        self.assertIn("90", groups)
        self.assertFalse(groups["90"]["on_board"])

    def test_children_match_the_parent_field(self):
        # The join the whole section is: a child appears under the group its
        # own `parent` names, and under no other.
        items = self.state.backlog_snapshot["items"]
        for group in build_navigator(self.state, None)["groups"]:
            for kid in group["children"]:
                with self.subTest(kid=kid["id"]):
                    self.assertEqual(
                        group["id"],
                        normalize_ref((items.get(kid["id"]) or {}).get("parent")),
                    )

    def test_declared_order_only_names_siblings(self):
        # Ordering is read from blocked_by BETWEEN SIBLINGS and nothing else.
        # An edge reaching outside the group would be an external blocker
        # wearing an ordering statement's clothes.
        for group in build_navigator(self.state, None)["groups"]:
            member = {kid["id"] for kid in group["children"]}
            for hold in group["order"]:
                with self.subTest(group=group["id"], blocker=hold["blocker"]):
                    self.assertIn(hold["blocker"], member)
                    for tid in hold["blocked"]:
                        self.assertIn(tid, member)


class TestCyclesAreDisclosed(unittest.TestCase):
    """A dependency cycle reaches the page instead of being detected and dropped.

    The graph has always run Tarjan's SCC on every poll; nothing rendered the
    result. That is worse than not looking: two tickets blocking each other
    both land in band G, each explained as "waiting on a live blocker", which
    is true of both and actionable for neither.
    """

    CYCLE_CORPUS: tuple[tuple[int, str], ...] = (
        (1, "---\nid: 1\ntitle: \"First half of the ring\"\ntype: feature\n"
            "status: backlog\npriority: medium\nblocked-by: [2]\n"
            "updated: 2026-03-01\n---\nbody.\n"),
        (2, "---\nid: 2\ntitle: \"Second half of the ring\"\ntype: feature\n"
            "status: backlog\npriority: medium\nblocked-by: [1]\n"
            "updated: 2026-03-01\n---\nbody.\n"),
    )

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.state = _state_for(cls.CYCLE_CORPUS, Path(cls._tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_the_fixture_actually_contains_a_cycle(self):
        # The guard: every assertion below passes vacuously on a corpus whose
        # blocker keys the loader never read.
        nav = build_navigator(self.state, None)
        self.assertEqual(1, len(nav["census"]["cycles"]))
        self.assertEqual(
            ["1", "2"], [r["id"] for r in nav["census"]["cycles"][0]["refs"]]
        )

    def test_the_cycle_reaches_the_markup(self):
        # Structural, not prose: one `census__ring` per cycle, and both members
        # linked inside it. Asserting the sentence would pin wording that is
        # free to change; the ring is the machine token whose absence means
        # the disclosure silently stopped rendering.
        nav = build_navigator(self.state, None)
        html = _render("navigator.html", nav=nav)
        self.assertEqual(len(nav["census"]["cycles"]), html.count('class="census__ring"'))
        ring = html.split('class="census__ring"')[1]
        for tid in ("1", "2"):
            self.assertIn('href="/tickets/%s"' % tid, ring)
        self.assertEqual([], _parse(html).nested_anchors)

    def test_a_healthy_corpus_prints_nothing(self):
        # An absence assertion, and the reason the disclosure is affordable:
        # it costs zero pixels on every corpus that has no cycle.
        with tempfile.TemporaryDirectory() as tmp:
            clean = _state_for(_SMALL_CORPUS, Path(tmp))
            nav = build_navigator(clean, None)
            self.assertEqual([], nav["census"]["cycles"])
            self.assertNotIn("census__ring", _render("navigator.html", nav=nav))


class TestOneDefinitionOfStartable(_Fixture):
    """Every "startable" number on the page counts the same records.

    This was wrong twice, in two different places, for one reason: band G′ is
    startable — a hold whose blocker already completed — and it kept being
    counted into some totals and out of others. § 01's header read "51
    startable" over a census group reading 49, and band A's own rationale read
    "2 of 49 startable" under a run heading announcing 51. Three renderings of
    one set, and nothing on the page reconciling them.
    """

    def test_header_field_run_and_census_agree(self):
        nav = build_navigator(self.state, None)
        run = [seg for seg in nav["field"] if seg["key"] == "startable"]
        group = [g for g in nav["census"]["groups"] if g["key"] == "startable"]
        self.assertEqual(1, len(run), "the startable run must exist")
        self.assertEqual(1, len(group), "the startable census group must exist")
        self.assertEqual(nav["contender_count"], run[0]["count"])
        self.assertEqual(nav["contender_count"], group[0]["count"])

    def test_the_lapsed_band_is_inside_that_count(self):
        # The guard that keeps the assertion above from passing vacuously: on a
        # corpus with no G′ rows every definition agrees trivially.
        nav = build_navigator(self.state, None)
        run = [seg for seg in nav["field"] if seg["key"] == "startable"][0]
        self.assertIn("G′", {row["band"] for row in run["rows"]})

    def test_band_a_rationale_counts_the_same_denominator(self):
        # Band A's gloss is the one rationale filled from live counts, so it is
        # the one that can disagree with the run it sits under.
        nav = build_navigator(self.state, None)
        band_a = [b for b in nav["census"]["legend"] if b["key"] == "A"]
        self.assertEqual(1, len(band_a))
        self.assertIn("of %d startable" % nav["contender_count"],
                      band_a[0]["rationale"])


class TestCounterfactualIsTwoWay(_Fixture):
    """``freed`` holds only the ids whose sole live blocker was the pick."""

    def test_sole_blocker_frees_and_double_blocker_does_not(self):
        nav = build_navigator(self.state, None)
        # #2 is the keystone by construction: it holds #3 alone and #4 jointly.
        self.assertEqual("2", nav["pick"]["id"])
        cf = nav["pick"]["counterfactual"]
        self.assertEqual(["3"], [ref["id"] for ref in cf["freed"]])
        self.assertEqual(["4"], [ref["id"] for ref in cf["still_held"]])

    def test_the_pick_is_absent_from_its_own_resulting_board(self):
        nav = build_navigator(self.state, None)
        cf = nav["pick"]["counterfactual"]
        self.assertNotIn(nav["pick"]["id"], [ref["id"] for ref in cf["new_top3"]])


class TestDegenerateCorpus(unittest.TestCase):
    """Five items, zero epics, zero edges — cortex-command's own shape.

    Both pages must render, and neither may render *empty*: a correct small
    page has a pick, an alternate, one or two bands and a census, and the epic
    map has to state that nothing declares a parent rather than showing a blank
    panel that reads as a fault.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.state = _state_for(_SMALL_CORPUS, Path(cls._tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_navigator_renders_without_raising(self):
        html = _render("navigator.html", nav=build_navigator(self.state, None))
        self.assertGreater(len(html.strip()), 0)
        self.assertEqual([], _parse(html).nested_anchors)

    def test_the_small_slice_still_produces_a_pick_and_an_alternate(self):
        nav = build_navigator(self.state, None)
        self.assertIsNotNone(nav["pick"])
        self.assertGreaterEqual(len(nav["alternates"]), 1)
        self.assertGreater(len(nav["field"]), 0)

    def test_a_corpus_with_no_parents_renders_no_group_section(self):
        # This is the case that made the epic map an empty nav tab on the repo
        # it ships from. Folded in, the section simply does not exist and the
        # page is whole without it.
        nav = build_navigator(self.state, None)
        self.assertEqual([], nav["groups"])
        self.assertEqual(0, nav["group_children"])
        self.assertNotIn(
            "nav-groups", _parse(_render("navigator.html", nav=nav)).ids
        )

    def test_ids_stay_unique_on_the_small_slice(self):
        parsed = _parse(_render_both(self.state))
        seen: dict[str, int] = {}
        for value in parsed.ids:
            seen[value] = seen.get(value, 0) + 1
        self.assertEqual([], sorted(k for k, n in seen.items() if n > 1))


class TestAbsentSnapshot(unittest.TestCase):
    """A ``None`` snapshot renders an empty state, never a traceback.

    ``None`` is two different facts — never polled, and a non-``cortex-backlog``
    backend, which clears the snapshot — and the surfaces must distinguish them
    rather than raising on either.
    """

    def test_view_models_are_schema_complete_when_unpolled(self):
        state = DashboardState()
        nav = build_navigator(state, None)
        self.assertFalse(nav["available"])
        # Schema-complete: the keys the templates read all exist and are falsy,
        # so a template branches on `available` instead of guarding each access.
        for key in (
            "pick", "alternates", "field", "groups", "group_children",
            "ordered_groups", "census", "slice_total",
        ):
            self.assertIn(key, nav)

    def test_unpolled_fragments_render(self):
        state = DashboardState()
        self.assertGreater(len(_render_both(state).strip()), 0)

    def test_non_local_backend_renders_the_gate(self):
        state = DashboardState()
        state.backlog_backend = "github-issues"
        nav = build_navigator(state, None)
        self.assertEqual("github-issues", nav["backend"])
        html = _render("navigator.html", nav=nav)
        self.assertGreater(len(html.strip()), 0)
        # The gated arm renders no board at all — reporting an empty corpus it
        # never read would be a false statement about the user's backlog.
        self.assertEqual(0, _parse(html).tags.get("table", 0))


class TestPageShellsRender(_Fixture):
    """The two page shells extend base.html and carry their poll targets."""

    def test_backlog_shell_renders(self):
        html = templates.env.get_template("backlog.html").render(
            request=_fake_request("/backlog"), state=self.state
        )
        parsed = _parse(html)
        self.assertIn("navigator-panel", parsed.ids)
        self.assertEqual([], parsed.nested_anchors)

    def test_shell_ids_do_not_collide_with_the_fragment_they_load(self):
        # The fragment is morphed *into* the shell, so an id used by both would
        # be a duplicate on the live page and never on either render alone.
        shell = _parse(
            templates.env.get_template("backlog.html").render(
                request=_fake_request("/backlog"), state=self.state
            )
        )
        fragment = _parse(
            _render("navigator.html", nav=build_navigator(self.state, None))
        )
        self.assertEqual(set(), set(shell.ids) & set(fragment.ids))


class TestBlockerPathIsRendered(_Fixture):
    """The blocker semantics survive the join into the page, blocker named.

    Two distinct things are under test and both were unasserted here until a
    mutation check exposed it: rewriting a single fixture key from the
    hyphenated ``blocked-by:`` the loader reads to the underscored
    ``blocked_by:`` it ignores left every one of this file's tests green. The
    declarations were inert, so nothing downstream of them was actually being
    exercised.

    First: a hold lapses only when *every* declared blocker is discharged. Item
    6 names one completed blocker and is startable today; items 3 and 4 each
    keep a live one. Getting this backwards puts a genuinely blocked ticket in
    the band that says "pick this up" — the precise error the surface exists to
    prevent, inverted.

    Second: the blocker is named. Today's board says "blocked by non-terminal
    internal blocker" and names nothing, which is the complaint the redesign
    was commissioned against, so the id *and* the title have to reach the row.
    """

    def _bands(self) -> dict[str, list[str]]:
        # The band is a column on the row now rather than a section around it,
        # so the grouping these assertions want is a fold over the field.
        out: dict[str, list[str]] = {}
        for row in self._rows():
            out.setdefault(row["band"], []).append(row["id"])
        return out

    def _rows(self) -> list[dict]:
        nav = build_navigator(self.state, None)
        return [row for seg in nav["field"] for row in seg["rows"]]

    def _rows_of(self, key: str) -> list[dict]:
        return [row for row in self._rows() if row["band"] == key]

    def test_the_fixture_declared_blockers_at_all(self):
        # The guard the mutation check earned. Every other assertion in this
        # class passes vacuously on a corpus whose blocker keys the loader
        # never read, so this one fails first and says why.
        declared = [
            row
            for key in ("G", "G′")
            for row in self._rows_of(key)
            if row["blockers"]
        ]
        self.assertTrue(
            declared,
            "no rendered row carries a blocker: check the fixture spells the "
            "frontmatter key 'blocked-by:' (hyphen), which is what "
            "collect_items reads — 'blocked_by:' parses to [] in silence",
        )

    def test_lapsed_hold_needs_every_blocker_discharged(self):
        bands = self._bands()
        self.assertEqual(["6"], bands.get("G′", []))
        self.assertEqual(["3", "4"], bands.get("G", []))

    def test_lapsed_row_carries_only_discharged_blockers(self):
        for row in self._rows_of("G′"):
            self.assertTrue(row["blockers"])
            self.assertTrue(all(b["discharged"] for b in row["blockers"]))

    def test_held_row_keeps_at_least_one_live_blocker(self):
        for row in self._rows_of("G"):
            self.assertTrue(row["blockers"])
            self.assertTrue(any(not b["discharged"] for b in row["blockers"]))

    def test_every_blocker_reference_carries_id_and_title(self):
        for key in ("G", "G′"):
            for row in self._rows_of(key):
                for blocker in row["blockers"]:
                    self.assertTrue(blocker["id"])
                    self.assertTrue(
                        blocker["title"],
                        "blocker %s on row %s rendered without a title"
                        % (blocker["id"], row["id"]),
                    )

    def test_the_multi_blocker_row_names_both_of_them(self):
        # Item 4 is the one row whose hold survives a partial discharge, so a
        # renderer that stops at the first blocker still looks right on every
        # other row on the board.
        row = next(r for r in self._rows_of("G") if r["id"] == "4")
        self.assertEqual(["2", "9"], sorted(b["id"] for b in row["blockers"]))

    def test_blocker_ids_and_titles_reach_the_rendered_html(self):
        # The view-model assertions above prove the join; this proves it
        # survives the template, which is where a mis-spelled key silently
        # renders a blank instead of raising.
        html = _render("navigator.html", nav=build_navigator(self.state, None))
        for key in ("G", "G′"):
            for row in self._rows_of(key):
                for blocker in row["blockers"]:
                    self.assertIn("#%s" % blocker["id"], html)
                    self.assertIn(blocker["title"], html)


class TestUnrecognisedStatusIsDisclosed(_Fixture):
    """A rank made on a status cortex does not know says so, at the claim.

    Cortex installs into repos that run their own status vocabularies, so an
    unrecognised value is deliberately still ranked — banding ``must-have``
    as untriaged would empty that repo's board. The obligation that comes with
    ranking it is disclosure, and review found the row disclosing while the
    hero did not: a record with ``status: icebox`` was presented as rank 1 of
    the startable field with nothing at the point of the claim saying the
    ranking rested on a word the board cannot interpret.

    The cost on an ordinary board is asserted too, because a disclosure that
    fires on every row is decoration rather than a signal.
    """

    ICEBOX = [
        (10, '---\nid: 10\ntitle: "Plain low ticket"\ntype: chore\n'
             'status: backlog\npriority: low\nupdated: 2026-04-01\n---\nbody.\n'),
        (98, '---\nid: 98\ntitle: "Unknown status, top priority"\ntype: feature\n'
             'status: icebox\npriority: critical\nupdated: 2026-04-03\n---\nbody.\n'),
    ]

    def _icebox_nav(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return build_navigator(_state_for(self.ICEBOX, Path(tmp.name)), None)

    def test_the_unknown_status_record_still_reaches_the_ranking(self):
        # The half of the behaviour that must NOT change: it is ranked, not
        # swept off the board for using a word cortex has not seen.
        nav = self._icebox_nav()
        self.assertEqual("98", nav["pick"]["id"])

    def test_the_pick_carries_a_status_note_naming_the_raw_value(self):
        nav = self._icebox_nav()
        self.assertIn("icebox", nav["pick"]["status_note"])

    def test_the_note_reaches_the_rendered_hero(self):
        nav = self._icebox_nav()
        html = _render("navigator.html", nav=nav)
        hero = html.split("nav-alt")[0]
        self.assertIn("icebox", hero)

    def test_a_recognised_status_carries_no_note(self):
        nav = self._icebox_nav()
        plain = next(e for e in nav["alternates"] if e["id"] == "10")
        self.assertEqual("", plain["status_note"])

    def test_the_disclosure_is_selective_not_universal(self):
        # The main corpus carries one deliberately hostile record (item 8,
        # ``status: icebox``) alongside ordinary ``backlog`` ones, so it tests
        # both arms at once: a chip on every entry would mean the predicate had
        # inverted, and a chip on none would mean it never fires.
        nav = build_navigator(self.state, None)
        entries = [e for e in [nav["pick"]] + list(nav["alternates"]) if e]
        noted = {e["id"] for e in entries if e["status_note"]}
        silent = {e["id"] for e in entries if not e["status_note"]}
        self.assertTrue(noted, "the disclosure never fired")
        self.assertTrue(silent, "the disclosure fired on every entry")
        for entry in entries:
            recognised = entry["status"] in bands_mod.OPEN_STATUSES
            self.assertEqual(recognised, not entry["status_note"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
