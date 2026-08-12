"""Rendering tests for the backlog navigator's four sections.

Every assertion here is about *structure*, never about prose. That is a repo
policy (``docs/policies.md``) and it is also the only kind of assertion worth
making about these templates: the copy is assembled in ``backlog/view.py`` from
live values, so a test pinning a sentence would be pinning a value that is
supposed to move, while the defects this file guards against are all structural
and all were real in the design bake-off that produced the surface.

The page is § 01 EPICS, § 02 READY, § 03 BLOCKED, § 04 NOT COMPETING — epics
first, because the groups say what the board is made of and a reader who
scrolls past thirty loose rows to reach them has already formed the wrong
picture. Three of the four are conditional. The two invariants those sections
rest on are what most of this file tests:

* **One record, one appearance.** A ticket whose ``parent`` resolves to a real
  ticket is drawn inside that epic's map and nowhere else; an epic container is
  a heading and never a row. So ``ready + blocked + tail + epic children +
  epic heads`` covers the slice exactly once, and ``nav.recon`` says so. The
  reconciliation this replaced compared the sum of the band counts against the
  sum of the band counts — an identity that could not fail — so one test here
  breaks the partition on purpose and requires ``recon.ok`` to go False.
* **One hover shape.** ``view._hover`` is merged *flat* into list rows, frame
  nodes and epic child tiles alike, so one template macro paints all three. The
  first cut nested it under a ``preview`` key on nodes only, and the macro then
  rendered four of six ``data-t-*`` attributes as empty strings with no error
  anywhere. That is a defect no exception and no visual diff catches.

The older structural guards, all earned in the bake-off:

* **Duplicate ``id``.** One prototype emitted ``id="ah"`` seven times for its
  arrowhead marker and referenced ``url(#ah)`` nine times; every reference
  resolves document-wide to the first definition, so the moment the top frame
  left the DOM every remaining frame silently lost its arrowheads. On a page
  that morph-swaps its panels every 30s, the top frame *will* leave the DOM.
  Duplicate ids also poison idiomorph's id keying outright.
* **Nested ``<a>``.** Another emitted a link inside a row that was itself a
  link. That is invalid HTML, the parser unnests it, and 41% of that
  prototype's board came apart.
* **Byte instability.** The surface polls every 30s with ``hx-swap="morph"``.
  A render that differs from the previous one on unchanged data moves the
  operator's cursor for no reason — which is why the staleness term is anchored
  to the corpus's own latest ``updated`` rather than to the wall clock, and why
  the server must never render a ``<details open>``: open state is per-operator
  and is replayed by the client after the swap.
* **Text measured in SVG.** A prototype placed rows with ``<text>`` and a
  guessed character advance for a font this project does not bundle. The frames
  draw two captions as SVG text, which is a fixed label in a reserved caption
  band; a ticket title or id drawn that way is the defect, and it is what the
  ``<foreignObject>`` nodes exist to prevent.
* **The degenerate corpus.** cortex-command's own slice is five items and zero
  epics. A ``max()`` over an empty collection without a ``default=`` is what
  crashed the winning prototype on it, and "renders a correct small page"
  rather than "renders an error" is the requirement.

Inputs are built by the shipped feed over a markdown corpus on disk (via
``backlog_fixtures``), not hand-transcribed, for the reason the retired
triage-board tests gave: this surface is a join across snapshot collections, a
bad join renders blank rather than raising, and a hand-written snapshot would
assert only that the transcription matches itself.
"""

from __future__ import annotations

import hashlib
import re
import tempfile
import types
import unittest
from dataclasses import replace
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from unittest import mock

from jinja2 import TemplateNotFound

from cortex_command.dashboard.app import templates
from cortex_command.dashboard.backlog import bands as bands_mod
from cortex_command.dashboard.backlog import view as view_mod
from cortex_command.dashboard.backlog.graph import normalize_ref
from cortex_command.dashboard.backlog.view import build_navigator
from cortex_command.dashboard.poller import DashboardState
from cortex_command.dashboard.tests.backlog_fixtures import build_snapshot, write_corpus

# A corpus exercising every section, both epic renderings and both frame gates
# in one slice:
#
#   1  epic container, three children, one intra-epic edge -> a frame
#   2  keystone: blocks 3 and 4, one of which it solely blocks
#   3  blocked by 2 alone            -> held, and drawn inside epic 1
#   4  blocked by 2 and by 9         -> held by a live blocker outside the epic
#   5  deferred by status            -> § 04
#   6  blocked only by a complete    -> hold lapsed, and startable today
#   7  status new                    -> § 04, off-board arm
#   8  open vocabulary throughout    -> the unrecognised-status note
#   9  a second live blocker for 4, itself loose and startable
#  10  epic container, one child, no edges -> a child grid, no SVG
#  11  child of 10
#  12  child of an epic that is not on the board
#  13  loose, held live, and one of its two declared blockers has closed
#  14  loose, held by two live blockers at once
#  20  a SECOND framed epic, so a shared marker id cannot hide
#  21  first of the second group, blocks 22
#  22  second of the second group, held inside its epic
#  90  complete, off the slice: a discharged blocker AND an off-board parent
_CORPUS: tuple[dict, ...] = (
    {"id": 1, "title": "Epic — the framed group", "type": "epic",
     "status": "backlog", "priority": "high", "updated": "2026-03-01"},
    {"id": 2, "title": "Keystone, holds two others", "type": "feature",
     "status": "backlog", "priority": "low", "parent": "1",
     "blocks": [3, 4], "updated": "2026-02-01"},
    {"id": 3, "title": "Held by the keystone alone", "type": "feature",
     "status": "backlog", "priority": "high", "parent": "1",
     "blocked_by": [2], "updated": "2026-03-01"},
    {"id": 4, "title": "Held by two live blockers", "type": "feature",
     "status": "backlog", "priority": "medium", "parent": "1",
     "blocked_by": [2, 9], "updated": "2026-03-01"},
    {"id": 5, "title": "Deferred by decision", "type": "chore",
     "status": "deferred", "priority": "medium", "updated": "2026-03-01"},
    {"id": 6, "title": "Hold lapsed, blocker already complete", "type": "bug",
     "status": "backlog", "priority": "medium", "blocked_by": [90],
     "updated": "2026-03-01"},
    {"id": 7, "title": "Untriaged", "type": "feature", "status": "new",
     "priority": "low", "updated": "2026-03-01"},
    {"id": 8, "title": "Open vocabulary everywhere", "type": "",
     "status": "icebox", "priority": "p0", "lifecycle_phase": "spec",
     "updated": "2026-03-01"},
    {"id": 9, "title": "The second blocker", "type": "feature",
     "status": "backlog", "priority": "medium", "blocks": [4],
     "updated": "2026-03-01"},
    {"id": 10, "title": "Epic — one child only", "type": "epic",
     "status": "backlog", "priority": "low", "updated": "2026-03-01"},
    {"id": 11, "title": "The only child", "type": "feature",
     "status": "backlog", "priority": "low", "parent": "10",
     "updated": "2026-03-01"},
    {"id": 12, "title": "Child of an off-board parent", "type": "feature",
     "status": "backlog", "priority": "low", "parent": "90",
     "updated": "2026-03-01"},
    {"id": 13, "title": "Loose, and one declared blocker has closed",
     "type": "feature", "status": "backlog", "priority": "high",
     "blocked_by": [9, 90], "updated": "2026-03-01"},
    {"id": 14, "title": "Loose, and held by both of them", "type": "feature",
     "status": "backlog", "priority": "medium", "blocked_by": [2, 9],
     "updated": "2026-03-01"},
    {"id": 20, "title": "Epic — the second framed group", "type": "epic",
     "status": "backlog", "priority": "medium", "updated": "2026-03-01"},
    {"id": 21, "title": "First of the second group", "type": "feature",
     "status": "backlog", "priority": "medium", "parent": "20",
     "blocks": [22], "updated": "2026-03-01"},
    {"id": 22, "title": "Second of the second group", "type": "feature",
     "status": "backlog", "priority": "medium", "parent": "20",
     "blocked_by": [21], "updated": "2026-03-01"},
    {"id": 90, "title": "Already complete", "type": "feature",
     "status": "complete", "priority": "medium", "updated": "2026-01-01"},
)

# The 5-item / 0-epic slice. cortex-command's own shape: no parent anywhere, no
# dependency edge anywhere, one deferred record so at least two bands exist.
_SMALL_CORPUS: tuple[dict, ...] = tuple(
    {
        "id": i,
        "title": "Small %d" % i,
        "type": "feature",
        "status": "deferred" if i == 5 else "backlog",
        "priority": "medium",
        "updated": "2026-04-0%d" % i,
    }
    for i in range(1, 6)
)

# A held record whose declared blocker names nothing the corpus knows — a bare
# uuid of the shape `cortex-create-backlog-item` writes, left behind when the
# ticket it pointed at was never created or was deleted outright.
_DANGLING_BLOCKER: tuple[dict, ...] = (
    {"id": 200, "title": "Held by a ref that resolves to nothing",
     "type": "bug", "status": "backlog", "priority": "medium",
     "blocked_by": ["6ba7b810-9dad-11d1-80b4-00c04fd430c8"],
     "updated": "2026-03-01"},
    {"id": 201, "title": "Loose, so the board is not empty", "type": "feature",
     "status": "backlog", "priority": "medium", "updated": "2026-03-01"},
)

# Every held record has a parent, so the blocked list is empty while the board
# holds something. The page has to say which of those two facts it is looking
# at, and it says it on the epic that draws the record.
_ALL_HELD_INSIDE_EPICS: tuple[dict, ...] = (
    {"id": 100, "title": "Epic — holds the only held work", "type": "epic",
     "status": "backlog", "updated": "2026-03-01"},
    {"id": 101, "title": "Goes first", "type": "feature", "status": "backlog",
     "parent": "100", "blocks": [102], "updated": "2026-03-01"},
    {"id": 102, "title": "Goes second", "type": "feature", "status": "backlog",
     "parent": "100", "blocked_by": [101], "updated": "2026-03-01"},
)

# The keys ``view._hover`` merges flat into every hoverable dict. One shape for
# a row, a frame node and a child tile — see the module docstring.
_HOVER_KEYS = ("status", "priority", "type", "points", "unblocks")

# The subset that must reach the markup as a NON-EMPTY attribute. ``points`` is
# legitimately absent for an off-slice node (there is no score for a record the
# board does not hold), and the macro omits the attribute rather than printing
# an empty one, so it is asserted at the model level instead.
_HOVER_ATTRS = ("status", "priority", "type", "unblocks")


def _fake_request(path: str = "/backlog") -> types.SimpleNamespace:
    """Minimal stand-in for the Starlette Request; base.html reads only the path."""
    return types.SimpleNamespace(url=types.SimpleNamespace(path=path))


def _state_for(corpus, tmp: Path) -> DashboardState:
    """Write *corpus* to disk and poll it into a DashboardState.

    The corpus goes through ``backlog_fixtures``, so what is rendered here is
    what the poller commits — including the frontmatter facts that yield an
    empty snapshot rather than an error when a fixture gets them wrong (the id
    comes from the filename; ``blocked_by`` is written as ``blocked-by``).
    """
    write_corpus(tmp, corpus)
    state = DashboardState()
    state.backlog_backend = "cortex-backlog"
    state.backlog_snapshot = build_snapshot(tmp)
    return state


def _render(name: str, **context) -> str:
    """Render one fragment exactly as its route handler does."""
    return templates.env.get_template(name).render(request=_fake_request(), **context)


def _render_nav(state: DashboardState) -> str:
    """The whole polled fragment — all four sections, as one document.

    The epic map used to be a peer page and the two fragments were concatenated
    here so an id collision between them could not hide. They are one document
    now, which is exactly the "somebody later puts both panels on one page"
    case the concatenation guarded against, so the id and anchor assertions run
    over the real page rather than a simulated one.
    """
    return _render("navigator.html", nav=build_navigator(state, None))


def _epic_html(epic: dict) -> str:
    """One epic's disclosure, through the same macro the page calls.

    Rendering the macro directly is what lets the frame-gate assertions be
    about *one* group. Splitting the whole page on a string would tie them to
    the order the sections happen to render in.
    """
    return str(templates.env.get_template("_nav_epics.html").module.epic_block(epic))


class _Structure(HTMLParser):
    """Collects the structural facts the invariants are stated in terms of.

    Written against ``html.parser`` rather than a DOM library because the
    dashboard ships no parser dependency and these are counting problems: ids
    seen, anchor nesting depth reached, the tag shape of the tables, and the
    attribute payload on every hoverable element. ``convert_charrefs`` stays
    on; entities are not what is under test.
    """

    #: Void elements never open a scope, so they must not push onto the stack.
    VOID = frozenset(
        {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
         "meta", "param", "source", "track", "wbr"}
    )

    #: The elements whose text content a join is asserted against — the three
    #: places a ticket's own title is meant to be visible to a reader.
    TEXT_CLASSES = frozenset({"node-title", "ekid__title", "nav-table__title"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: list[str] = []
        self.nested_anchors: list[str] = []
        self.tags: dict[str, int] = {}
        self.classes: dict[str, int] = {}
        self.th_scopes: list[str] = []
        self.svg_texts: list[str] = []
        # Every native tooltip source. `title="…"` on any element and a
        # `<title>` child inside an <svg> render the same grey OS tooltip,
        # which is what competed with the hover card.
        self.title_attrs: list[str] = []
        #: Attributes of every ``<details>``, so "carries an id" and "is not
        #: server-opened" are askable without a prefix convention.
        self.details: list[dict] = []
        #: Attributes of every ``.js-ticket`` — the elements the hover card and
        #: the modal are delegated onto, and the ones whose payload must match.
        self.js_tickets: list[dict] = []
        #: One record per ``<table>``: its enclosing section id and its cell
        #: counts, so a header/body mismatch is visible.
        self.tables: list[dict] = []
        #: The attributes of every ``<tr>``. The row is the hoverable and the
        #: click target now, so "the payload is on the row" is a fact about an
        #: element type rather than about a class the row happens to carry.
        self.rows: list[dict] = []
        #: The id of every ``<section>``, in document order. Distinct from
        #: :attr:`ids`, which is every id on the page — a disclosure, a filter
        #: control and a section are all "an id" to that list, and only one of
        #: them is a section of the page.
        self.section_ids: list[str] = []
        #: Text content collected per :attr:`TEXT_CLASSES` member. A title that
        #: reaches only an ``aria-label`` is still in the document, so "the
        #: title rendered" has to be asked of the element that shows it.
        self.text_by_class: dict[str, list[str]] = {}
        self._stack: list[str] = []
        self._sections: list[str] = []
        self._tables: list[dict] = []
        self._captures: list[tuple[int, str, int]] = []
        self._in_svg_text = False

    def _record_attrs(self, tag: str, attributes: dict) -> None:
        if "id" in attributes:
            self.ids.append(attributes["id"])
        if "title" in attributes:
            self.title_attrs.append(attributes["title"])
        for token in (attributes.get("class") or "").split():
            self.classes[token] = self.classes.get(token, 0) + 1
        if "js-ticket" in (attributes.get("class") or "").split():
            self.js_tickets.append(attributes)
        self.tags[tag] = self.tags.get(tag, 0) + 1

    def handle_starttag(self, tag, attrs) -> None:
        attributes = dict(attrs)
        self._record_attrs(tag, attributes)
        if tag == "a" and "a" in self._stack:
            self.nested_anchors.append(attributes.get("href", ""))
        if tag == "th":
            self.th_scopes.append(attributes.get("scope", ""))
        if tag == "details":
            self.details.append(attributes)
        if tag == "tr":
            self.rows.append(attributes)
        if tag == "section":
            self._sections.append(attributes.get("id", ""))
            if attributes.get("id"):
                self.section_ids.append(attributes["id"])
        if tag == "table":
            self._tables.append(
                {"section": self._sections[-1] if self._sections else "",
                 "th": 0, "td": 0, "tr": 0}
            )
        if self._tables and tag in ("th", "td", "tr"):
            self._tables[-1][tag] += 1
        if tag == "text":
            self._in_svg_text = True
            self.svg_texts.append("")
        if tag not in self.VOID:
            self._stack.append(tag)
        # Registered at the depth reached *after* the push, so the matching
        # end tag drops it without needing to be recognised by name.
        for token in (attributes.get("class") or "").split():
            if token in self.TEXT_CLASSES:
                bucket = self.text_by_class.setdefault(token, [])
                bucket.append("")
                self._captures.append((len(self._stack), token, len(bucket) - 1))

    def handle_startendtag(self, tag, attrs) -> None:
        self._record_attrs(tag, dict(attrs))

    def handle_endtag(self, tag) -> None:
        if tag == "text":
            self._in_svg_text = False
        if tag == "section" and self._sections:
            self._sections.pop()
        if tag == "table" and self._tables:
            self.tables.append(self._tables.pop())
        if tag in self._stack:
            while self._stack:
                if self._stack.pop() == tag:
                    break
        while self._captures and self._captures[-1][0] > len(self._stack):
            self._captures.pop()

    def handle_data(self, data) -> None:
        if self._in_svg_text and self.svg_texts:
            self.svg_texts[-1] += data
        for _depth, token, index in self._captures:
            self.text_by_class[token][index] += data


def _parse(html: str) -> _Structure:
    parser = _Structure()
    parser.feed(html)
    return parser


def _section_ordinals(html: str) -> list[int]:
    """The § numbers the register actually printed, in document order."""
    return [int(n) for n in re.findall(r"§\s*0*(\d+)</strong>", html)]


def _appearance_buckets(nav: dict, slice_ids: set[str]) -> dict[str, list[str]]:
    """Where every record on the board is drawn, one bucket per place.

    The five buckets are the page's own decomposition — the reconciliation line
    prints exactly these — so a record in two of them is a record an operator
    reads twice, and a record in none is a record that vanished from a
    read-only board without raising anything.

    Epic heads are filtered to the slice: an epic whose container sits off the
    board renders as a heading over its live children, and it is not one of the
    slice's own records.
    """
    return {
        "ready": [row["id"] for row in nav["ready"]],
        "blocked": [row["id"] for row in nav["blocked"]],
        "tail": [row["id"] for panel in nav["tail"] for row in panel["rows"]],
        "children": [kid["id"] for epic in nav["epics"] for kid in epic["children"]],
        "heads": [epic["id"] for epic in nav["epics"] if epic["id"] in slice_ids],
    }


class _Fixture(unittest.TestCase):
    """Base class owning the tmp corpus, so each subclass polls once."""

    CORPUS = _CORPUS

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.state = _state_for(cls.CORPUS, Path(cls._tmp.name))
        cls.html = _render_nav(cls.state)
        cls.parsed = _parse(cls.html)
        # The model behind the markup, for the assertions that are joins
        # against it rather than counts over the tags.
        cls.nav = build_navigator(cls.state, None)
        cls.items = cls.state.backlog_snapshot["items"]

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def epic(self, epic_id: str) -> dict:
        return next(e for e in self.nav["epics"] if e["id"] == epic_id)


class TestNoDuplicateIds(_Fixture):
    """Every ``id`` in the rendered output is unique.

    The page renders arrowhead markers, disclosures and pan containers with
    server-assigned ids, and all three break in a different way when an id
    repeats: ``url(#marker)`` resolves to the wrong definition, the open-details
    restore reattaches to the wrong epic, and idiomorph keys two nodes as one.
    """

    def test_ids_are_unique_across_the_page(self):
        seen: dict[str, int] = {}
        for value in self.parsed.ids:
            seen[value] = seen.get(value, 0) + 1
        duplicates = sorted(k for k, n in seen.items() if n > 1)
        self.assertEqual([], duplicates, "duplicate id= values: %s" % duplicates)

    def test_something_actually_carried_an_id(self):
        # Guards the assertion above against passing vacuously if the surface
        # ever stops emitting ids at all — at which point the disclosure restore
        # and the scroll preservation are silently dead.
        self.assertGreater(len(self.parsed.ids), 0)

    def test_two_frames_rendered_so_a_shared_marker_id_cannot_hide(self):
        # The non-vacuity guard for the assertion above, and the reason the
        # corpus carries a second framed epic at all: with one frame on the
        # page, a marker id shared by every frame is indistinguishable from a
        # per-epic one, and that defect cost a prototype its arrowheads.
        framed = [epic for epic in self.nav["epics"] if epic["frame"]]
        self.assertGreater(len(framed), 1)
        self.assertEqual(
            len(framed), len({epic["frame"]["marker_id"] for epic in framed})
        )

    def test_every_details_carries_an_id(self):
        # A disclosure without a server-rendered id snaps shut on every 30s
        # morph, because the client's open-state store has nothing to key on.
        # Stated over every <details> rather than over one id prefix, so a new
        # kind of disclosure is covered without anyone remembering to add it.
        self.assertGreater(len(self.parsed.details), 0, "no <details> rendered")
        without = [d for d in self.parsed.details if not d.get("id")]
        self.assertEqual([], without, "a <details> rendered without an id")


class TestSectionRegister(_Fixture):
    """The § register counts up by one across every section that drew.

    The pair matters: ``TestDegenerateCorpus`` pins that a suppressed section
    leaves no hole, and this pins that a counter cannot satisfy that by
    printing § 01 four times over.
    """

    def test_all_four_sections_number_contiguously(self):
        self.assertEqual([1, 2, 3, 4], _section_ordinals(self.html))


class TestNoNestedAnchors(_Fixture):
    """No ``<a>`` is a descendant of another ``<a>``, anywhere on the page."""

    def test_zero_nested_anchors(self):
        self.assertEqual([], self.parsed.nested_anchors)

    def test_anchors_were_actually_rendered(self):
        # Every list row, tail row, tile and node links out to /tickets/{id};
        # zero anchors would mean the page rendered without its click-through.
        self.assertGreater(self.parsed.tags.get("a", 0), 0)


class TestListsAreTables(_Fixture):
    """The list sections are real tables with column headers.

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

    def test_every_table_body_matches_its_own_header(self):
        # A column added to the header and not to the body (or the reverse)
        # renders a table that is skewed rather than broken, which no exception
        # and no smoke test sees.
        self.assertTrue(self.parsed.tables)
        for table in self.parsed.tables:
            with self.subTest(section=table["section"]):
                self.assertGreater(table["th"], 0)
                self.assertEqual(table["td"], table["th"] * (table["tr"] - 1))

    def test_only_the_blocked_table_carries_the_extra_column(self):
        # ``show_blockers`` is the single way the three callers of one row macro
        # differ. Asserted as a shape over the sections rather than as a column
        # count, so trimming or adding a shared column stays a one-line change.
        widths = {table["section"]: table["th"] for table in self.parsed.tables}
        self.assertIn("nav-blocked", widths)
        self.assertIn("nav-ready", widths)
        self.assertEqual(widths["nav-ready"] + 1, widths["nav-blocked"])
        for section, width in widths.items():
            if section != "nav-blocked":
                self.assertEqual(widths["nav-ready"], width)

    def test_no_svg_title_element_anywhere(self):
        """An absence assertion, and the point of the change that made it true.

        A ``<title>`` child is a legitimate accessible name and that is why one
        was there — but browsers also paint it as an OS tooltip, so hovering a
        node produced the styled hover card and a grey system tooltip at once.
        The accessible name now comes from the anchor's own text and its
        ``aria-label``, neither of which any browser renders twice.
        """
        self.assertEqual(0, self.parsed.tags.get("title", 0))

    def test_no_hoverable_element_carries_a_native_title(self):
        """The other spelling of the same defect, narrowed to where it bites.

        ``title="…"`` renders the OS tooltip, and the double-tooltip only
        happens where the styled card also fires — which is exactly the
        ``.js-ticket`` elements the delegated handlers key on. Elsewhere (a row
        mark, a blocker link) the native tooltip is the only tooltip there is,
        so the rule is stated over the hoverable set rather than the document.
        """
        self.assertGreater(len(self.parsed.js_tickets), 0)
        offenders = [el.get("data-ticket") for el in self.parsed.js_tickets if "title" in el]
        self.assertEqual([], offenders)

    def test_no_ticket_title_or_id_is_drawn_as_svg_text(self):
        """SVG ``<text>`` is for fixed captions only, never for a record.

        The frames legitimately draw two captions that way, inside a caption
        band the layout reserves. What may never be an SVG ``<text>`` is a
        ticket's title or its id: the fonts are not bundled, Georgia is what
        renders, and a box sized to a guessed advance is the defect three of
        five prototypes shipped. Those travel through ``<foreignObject>``,
        where CSS wraps them inside a box the server already sized.
        """
        drawn = [
            (node["id"], node["title"])
            for epic in self.nav["epics"] if epic["frame"]
            for node in epic["frame"]["nodes"]
        ]
        self.assertTrue(drawn, "the fixture must render at least one frame node")
        for text in self.parsed.svg_texts:
            for tid, title in drawn:
                with self.subTest(text=text, ticket=tid):
                    self.assertNotIn(title, text)
                    self.assertNotIn("#%s" % tid, text)

    def test_every_frame_node_is_a_foreign_object(self):
        # The positive half of the rule above: the count is the join, so a node
        # that regressed to SVG text would leave one behind.
        nodes = sum(
            len(epic["frame"]["nodes"])
            for epic in self.nav["epics"] if epic["frame"]
        )
        self.assertGreater(nodes, 0)
        self.assertEqual(nodes, self.parsed.tags.get("foreignobject", 0))

    def test_every_rendered_child_carries_its_ticket_title(self):
        """Every child the model names reaches the element that shows it.

        Asserted as a join, not as prose: the words are the corpus's, and what
        is under test is that the data got there. A group that rendered its ids
        but dropped its titles would still look plausible on the page.

        Read off the title element rather than off the whole document, because
        a node also carries its title inside ``aria-label``: a substring search
        over the page passes on a frame whose visible titles are all blank.
        """
        expected: list[tuple[str, str]] = []
        for epic in self.nav["epics"]:
            if epic["frame"]:
                expected += [(n["title"], "node-title") for n in epic["frame"]["nodes"]]
            else:
                expected += [(k["title"], "ekid__title") for k in epic["children"]]
        self.assertTrue(expected, "the fixture must render at least one child")
        for title, token in expected:
            with self.subTest(title=title):
                shown = [t.strip() for t in self.parsed.text_by_class.get(token, [])]
                self.assertIn(title, shown)

    def test_every_listed_row_carries_its_ticket_title(self):
        # The same join for the three lists. Substring rather than equality:
        # the title cell also holds the unrecognised-status chip.
        rows = (
            list(self.nav["ready"]) + list(self.nav["blocked"])
            + [row for panel in self.nav["tail"] for row in panel["rows"]]
        )
        self.assertTrue(rows)
        shown = self.parsed.text_by_class.get("nav-table__title", [])
        self.assertTrue(shown)
        for row in rows:
            with self.subTest(row=row["id"]):
                self.assertTrue(any(row["title"] in cell for cell in shown))


class TestOneHoverShape(_Fixture):
    """A row, a frame node and a child tile answer to the same keys.

    ``view._hover`` is merged FLAT into all three, so a single template macro
    paints them without a branch. The first cut nested the payload under a
    ``preview`` key on nodes and tiles but not on rows, and the macro then read
    four of six attributes as ``Undefined`` — which Jinja renders as the empty
    string, with no error anywhere. The page looked right and every card in
    every frame was blank.
    """

    def _hoverables(self) -> dict[str, list[dict]]:
        return {
            "row": list(self.nav["ready"]) + list(self.nav["blocked"])
            + [row for panel in self.nav["tail"] for row in panel["rows"]],
            "node": [
                node
                for epic in self.nav["epics"] if epic["frame"]
                for node in epic["frame"]["nodes"]
            ],
            "tile": [
                kid
                for epic in self.nav["epics"] if not epic["frame"]
                for kid in epic["children"]
            ],
        }

    def test_all_three_hoverable_shapes_are_present(self):
        # The guard. Every assertion below is satisfied trivially by a corpus
        # that renders only one of the three.
        for kind, dicts in self._hoverables().items():
            with self.subTest(kind=kind):
                self.assertTrue(dicts)

    def test_the_view_model_merges_one_shape_into_all_three(self):
        for kind, dicts in self._hoverables().items():
            for entry in dicts:
                with self.subTest(kind=kind, id=entry["id"]):
                    self.assertLessEqual(set(_HOVER_KEYS), set(entry))

    def test_every_js_ticket_in_the_markup_carries_the_whole_payload(self):
        """The assertion that would have caught the nested-``preview`` bug.

        Stated over the rendered attributes rather than over the model, because
        the model was never wrong: the macro was reading a key that was one
        level down, and an empty string is what that renders as.
        """
        self.assertGreater(len(self.parsed.js_tickets), 0)
        for element in self.parsed.js_tickets:
            ticket = element.get("data-ticket")
            for name in _HOVER_ATTRS:
                with self.subTest(ticket=ticket, attr=name):
                    self.assertTrue(
                        element.get("data-t-%s" % name),
                        "#%s rendered data-t-%s as %r"
                        % (ticket, name, element.get("data-t-%s" % name)),
                    )

    def test_the_three_shapes_all_reach_the_markup_as_js_tickets(self):
        # The markup-side guard, by the class each shape carries. Without it
        # the assertion above passes on a page whose frames rendered no nodes.
        kinds = {"row": 0, "node": 0, "tile": 0}
        for element in self.parsed.js_tickets:
            tokens = set((element.get("class") or "").split())
            if "node-link" in tokens:
                kinds["node"] += 1
            elif "ekid__link" in tokens:
                kinds["tile"] += 1
            else:
                kinds["row"] += 1
        for kind, count in kinds.items():
            with self.subTest(kind=kind):
                self.assertGreater(count, 0)


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
            hashlib.sha256(_render_nav(again).encode()).hexdigest(),
        )

    def test_no_disclosure_is_rendered_open(self):
        """Open state is per-operator, so the server may never render it.

        An absence assertion, and the one this page newly needs: it emits six
        ``<details>`` where the surface it replaced emitted none. A server that
        rendered ``open`` would make the fragment differ per viewer, which is
        the byte-identical-poll property gone — and the client replays the
        operator's own open set after the swap anyway.
        """
        self.assertGreater(len(self.parsed.details), 0)
        opened = [d.get("id") for d in self.parsed.details if "open" in d]
        self.assertEqual([], opened)


class TestOneRecordOneAppearance(_Fixture):
    """The page's central invariant: a record is drawn in exactly one place.

    A ticket whose ``parent`` resolves is drawn inside that epic's map and
    nowhere else, and an epic container is a heading rather than a row. Both
    halves are applied in ``view._partition`` and in no second site, because a
    second site is how the same ticket comes to read one thing in a list and
    another in a frame.
    """

    def buckets(self) -> dict[str, list[str]]:
        return _appearance_buckets(self.nav, set(self.items))

    def test_every_bucket_is_populated(self):
        # The guard: the coverage and disjointness assertions below are both
        # satisfied trivially by a corpus that exercises one bucket.
        for name, ids in self.buckets().items():
            with self.subTest(bucket=name):
                self.assertTrue(ids)

    def test_the_buckets_cover_the_slice_exactly_once(self):
        buckets = self.buckets()
        placed = [tid for ids in buckets.values() for tid in ids]
        self.assertEqual(sorted(set(self.items)), sorted(set(placed)))
        self.assertEqual(len(placed), len(set(placed)), "a record is drawn twice")

    def test_no_id_appears_in_two_buckets(self):
        # Stated pairwise as well, because the count above says only that some
        # record is duplicated and this says which two places disagree.
        buckets = self.buckets()
        for left in buckets:
            for right in buckets:
                if left < right:
                    with self.subTest(left=left, right=right):
                        self.assertEqual(
                            set(), set(buckets[left]) & set(buckets[right])
                        )

    def listed_ids(self) -> set[str]:
        """Every id drawn as a row, in any of the three lists."""
        buckets = self.buckets()
        return set(buckets["ready"]) | set(buckets["blocked"]) | set(buckets["tail"])

    def test_a_child_never_appears_in_a_list(self):
        children = set(self.buckets()["children"])
        self.assertTrue(children)
        self.assertEqual(set(), children & self.listed_ids())

    def test_an_epic_container_is_never_a_row(self):
        heads = {epic["id"] for epic in self.nav["epics"]}
        self.assertTrue(heads)
        self.assertEqual(set(), heads & self.listed_ids())

    def test_recon_reports_the_buckets_it_claims_to(self):
        # The reconciliation is the page's own statement of this invariant, so
        # it has to be the same arithmetic and not a parallel count.
        buckets = self.buckets()
        recon = self.nav["recon"]
        self.assertTrue(recon["ok"])
        self.assertEqual(len(self.items), recon["total"])
        self.assertEqual(len(buckets["ready"]), recon["ready"])
        self.assertEqual(len(buckets["blocked"]), recon["blocked"])
        self.assertEqual(len(buckets["children"]), recon["children"])
        self.assertEqual(len(buckets["tail"]), recon["tail"])
        self.assertEqual(len(buckets["heads"]), recon["heads"])

    def test_every_slice_record_reaches_the_markup(self):
        # The rendering half. A record can satisfy every model assertion above
        # and still be dropped by a template branch, and a read-only board that
        # silently omits a ticket is the worst failure available to it.
        for tid in sorted(self.items):
            with self.subTest(ticket=tid):
                self.assertTrue(
                    'data-ticket="%s"' % tid in self.html
                    or 'id="nav-epic-%s"' % tid in self.html,
                    "#%s reached no row, tile, node or epic heading" % tid,
                )

    def test_an_external_blocker_may_be_drawn_twice_and_still_be_loose(self):
        """The one duplication the invariant permits, pinned so it stays known.

        #9 blocks a child of epic 1 without being one, so it is drawn as an
        external node in that frame *and* listed as the loose startable record
        it is. That is not the invariant breaking: an external node is not one
        of the five buckets, and the alternative — dropping the arrow's tail —
        is a frame that says a child is held by nothing.
        """
        frame = self.epic("1")["frame"]
        self.assertIn("9", frame["externals"])
        self.assertIn("9", [row["id"] for row in self.nav["ready"]])
        self.assertNotIn("9", self.buckets()["children"])


class TestReconciliationCanFail(unittest.TestCase):
    """A record dropped from the partition makes ``recon.ok`` say so.

    The line this replaced compared ``sum(band.count)`` against
    ``sum(band.count)``. That is an arithmetic identity: it printed "every
    record on this board is in exactly one band" unconditionally, including on
    a board that had lost one, and it did that for as long as the page had a
    guarantee. The comparand now is the set of ids the partition actually
    routed, so this test breaks the routing while leaving every count intact —
    the exact input the old form could not distinguish from a healthy board.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.state = _state_for(_CORPUS, Path(cls._tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_a_healthy_board_reconciles(self):
        self.assertTrue(build_navigator(self.state, None)["recon"]["ok"])

    def test_a_dropped_row_breaks_the_reconciliation(self):
        captured: list[bands_mod.Bands] = []
        real = bands_mod.partition

        def lossy(*args, **kwargs):
            banded = real(*args, **kwargs)
            out, dropped = [], False
            for band in banded:
                if not dropped and band.rows:
                    # ``count`` is deliberately left alone: the band still
                    # CLAIMS the record, it just no longer routes it. That is
                    # the shape the sum-vs-sum comparison called healthy.
                    out.append(replace(band, rows=list(band.rows[1:])))
                    dropped = True
                else:
                    out.append(band)
            faulty = replace(banded, bands=tuple(out))
            captured.append(faulty)
            return faulty

        with mock.patch.object(bands_mod, "partition", lossy):
            nav = build_navigator(self.state, None)
        self.assertTrue(captured, "the partition was never called")
        faulty = captured[0]

        # The discriminator: the retired comparison still agrees on this input.
        self.assertEqual(faulty.total, sum(band.count for band in faulty))
        # The live one does not.
        self.assertFalse(nav["recon"]["ok"])
        html = _render("navigator.html", nav=nav)
        self.assertIn("recon--broken", html)

    def test_the_partition_only_reports_ids_it_routed(self):
        # The same claim one level down, against ``_partition`` itself: ``seen``
        # is built from the rows it walked, so it cannot be inflated by a count.
        snapshot = self.state.backlog_snapshot
        items, _graph, ctx, parents = view_mod._context(snapshot)
        banded = bands_mod.partition(items, ctx, item_order=snapshot.get("item_order"))
        child_ids = frozenset(tid for kids in parents.values() for tid in kids)
        # ``head_ids`` is the parent map, not band E′ — the two differ in both
        # directions and keying on the band dropped a childless epic off the
        # page while double-rendering a non-epic parent.
        head_ids = frozenset(parents)
        order = snapshot.get("item_order")
        page = view_mod._partition(
            banded,
            items,
            child_ids,
            head_ids,
            ctx,
            frozenset(str(tid) for tid in order) if order else None,
        )
        self.assertEqual(banded.total, len(page["seen"]))

        short = replace(
            banded,
            bands=tuple(
                replace(band, rows=list(band.rows[1:])) if band.rows else band
                for band in banded[:1]
            )
            + tuple(banded[1:]),
        )
        self.assertEqual(banded.total - 1, len(
            view_mod._partition(
                short,
                items,
                child_ids,
                head_ids,
                ctx,
                frozenset(str(tid) for tid in order) if order else None,
            )["seen"]
        ))


class TestEveryEpicReachesTheSection(_Fixture):
    """Every parent group renders exactly once, whatever its size or status.

    The frame/tail split this replaced routed small and off-board groups to a
    second table with its own state vocabulary, which is how one off-slice
    ticket came to read ``complete`` in a frame and ``off board`` in the tail.
    One list, one vocabulary.
    """

    def test_epics_are_rendered_once_each(self):
        placed = [epic["id"] for epic in self.nav["epics"]]
        self.assertEqual(len(placed), len(set(placed)), "an epic rendered twice")
        for epic_id in placed:
            with self.subTest(epic=epic_id):
                self.assertEqual(1, self.html.count('id="nav-epic-%s"' % epic_id))

    def test_every_epic_has_a_disclosure_in_the_markup(self):
        rendered = [i for i in self.parsed.ids if i.startswith("nav-epic-")]
        self.assertEqual(
            sorted(rendered),
            sorted("nav-epic-%s" % epic["id"] for epic in self.nav["epics"]),
        )

    def test_the_disclosure_id_is_keyed_on_the_epic_not_its_position(self):
        # Position-keyed ids are how an open-state store reattaches to the wrong
        # group after the largest-first ordering moves one.
        for epic in self.nav["epics"]:
            with self.subTest(epic=epic["id"]):
                self.assertEqual("nav-epic-%s" % epic["id"], epic["details_id"])

    def test_the_one_child_group_is_kept_not_dropped(self):
        # It used to be relegated to a tail table for having too few children to
        # frame. There is no threshold now — a group of one is a fact about the
        # board and costs one disclosure.
        self.assertEqual(1, self.epic("10")["count"])

    def test_the_off_board_parent_is_kept_not_dropped(self):
        off = self.epic("90")
        self.assertFalse(off["on_board"])
        self.assertEqual(["12"], [kid["id"] for kid in off["children"]])

    def test_children_match_the_parent_field(self):
        # The join the whole section is: a child appears under the group its
        # own `parent` names, and under no other.
        for epic in self.nav["epics"]:
            for kid in epic["children"]:
                with self.subTest(kid=kid["id"]):
                    self.assertEqual(
                        epic["id"],
                        normalize_ref((self.items.get(kid["id"]) or {}).get("parent")),
                    )

    def test_the_child_count_is_the_children_it_carries(self):
        for epic in self.nav["epics"]:
            with self.subTest(epic=epic["id"]):
                self.assertEqual(epic["count"], len(epic["children"]))

    def test_epic_children_totals_the_groups(self):
        self.assertEqual(
            sum(epic["count"] for epic in self.nav["epics"]),
            self.nav["epic_children"],
        )


class TestFrameGate(_Fixture):
    """Geometry is drawn only where a group declares a dependency order.

    ``view._frame`` returns ``{}`` when the layout finds no elbows, and that
    gate is the whole answer to the measurement that retired this renderer: it
    drew a dashed box around an unordered list for every group with nothing to
    say, once per group, and those boxes were most of its output.
    """

    def test_a_group_with_a_declared_dependency_renders_a_frame(self):
        epic = self.epic("1")
        self.assertTrue(epic["frame"])
        parsed = _parse(_epic_html(epic))
        self.assertEqual(1, parsed.classes.get("epic-svg", 0))
        self.assertGreaterEqual(parsed.classes.get("edge", 0), 1)
        self.assertEqual(len(epic["frame"]["elbows"]), parsed.classes.get("edge", 0))

    def test_a_group_with_none_renders_tiles_and_no_svg(self):
        for epic_id in ("10", "90"):
            with self.subTest(epic=epic_id):
                epic = self.epic(epic_id)
                self.assertEqual({}, epic["frame"])
                parsed = _parse(_epic_html(epic))
                self.assertEqual(0, parsed.tags.get("svg", 0))
                self.assertEqual(1, parsed.classes.get("ekids", 0))
                self.assertEqual(epic["count"], parsed.classes.get("ekid", 0))

    def test_a_framed_group_renders_no_tile_grid(self):
        # The other half of the either/or: the model builds ``children`` for
        # every group, and a template that rendered both would draw each child
        # twice inside one disclosure.
        parsed = _parse(_epic_html(self.epic("1")))
        self.assertEqual(0, parsed.classes.get("ekids", 0))

    def test_an_external_blocker_reaches_the_frame(self):
        """An edge pointing INTO the epic from a non-child is drawn.

        This is the case a per-epic frame was claimed unable to draw, and it is
        the majority of the live edges on the real corpus. #9 blocks #4 without
        being a child of epic 1, so it gets a real position in the left-hand
        lane and a real elbow rather than a text stub whose width would have to
        be guessed from a font this project does not bundle.
        """
        frame = self.epic("1")["frame"]
        self.assertEqual(["9"], list(frame["externals"]))
        self.assertIn("external", [elbow["kind"] for elbow in frame["elbows"]])
        external = [node for node in frame["nodes"] if node["external"]]
        self.assertEqual(["9"], [node["id"] for node in external])
        self.assertIsNotNone(frame["ext_label"])
        # And it survives into the markup as a node like any other.
        self.assertIn('data-ticket="9"', _epic_html(self.epic("1")))

    def test_a_frame_with_no_externals_reserves_no_lane(self):
        # The absence half, and the guard on the assertion above: with the lane
        # unconditional, "the externals reached the frame" would pass on a
        # group that has none.
        frame = self.epic("20")["frame"]
        self.assertEqual([], list(frame["externals"]))
        self.assertIsNone(frame["ext_label"])

    def test_mapped_epics_counts_the_framed_groups(self):
        self.assertEqual(
            sum(1 for epic in self.nav["epics"] if epic["frame"]),
            self.nav["mapped_epics"],
        )
        self.assertGreater(self.nav["mapped_epics"], 0)
        self.assertLess(self.nav["mapped_epics"], len(self.nav["epics"]))

    def test_every_frame_node_is_positioned_by_the_layout(self):
        # Nothing in the template computes a coordinate, so every node must
        # arrive with one. A missing key renders as the empty string in an
        # `x=""` attribute, which browsers treat as 0 and stack every node at
        # the origin.
        for epic in self.nav["epics"]:
            if not epic["frame"]:
                continue
            for node in epic["frame"]["nodes"]:
                with self.subTest(epic=epic["id"], node=node["id"]):
                    self.assertIsInstance(node["x"], int)
                    self.assertIsInstance(node["y"], int)


class TestCyclesAreDisclosed(unittest.TestCase):
    """A dependency cycle reaches the page instead of being detected and dropped.

    The graph has always run Tarjan's SCC on every poll; nothing rendered the
    result. That is worse than not looking: two tickets blocking each other
    both land held, each explained as "waiting on a live blocker", which is
    true of both and actionable for neither.
    """

    CYCLE_CORPUS: tuple[dict, ...] = (
        {"id": 1, "title": "First half of the ring", "type": "feature",
         "status": "backlog", "priority": "medium", "blocked_by": [2],
         "updated": "2026-03-01"},
        {"id": 2, "title": "Second half of the ring", "type": "feature",
         "status": "backlog", "priority": "medium", "blocked_by": [1],
         "updated": "2026-03-01"},
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
        self.assertEqual(1, len(nav["cycles"]))
        self.assertEqual(["1", "2"], [r["id"] for r in nav["cycles"][0]["refs"]])

    def test_the_cycle_reaches_the_markup(self):
        # Structural, not prose: one `census__ring` per cycle, and both members
        # linked inside it. Asserting the sentence would pin wording that is
        # free to change; the ring is the machine token whose absence means the
        # disclosure silently stopped rendering.
        nav = build_navigator(self.state, None)
        html = _render("navigator.html", nav=nav)
        self.assertEqual(len(nav["cycles"]), html.count('class="census__ring"'))
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
            self.assertEqual([], nav["cycles"])
            self.assertNotIn("census__ring", _render("navigator.html", nav=nav))


class TestBlockerPathIsRendered(_Fixture):
    """The blocker semantics survive the join into § 03, blocker named.

    Two distinct things are under test and both were unasserted here until a
    mutation check exposed it: rewriting a single fixture key from the
    hyphenated ``blocked-by:`` the loader reads to the underscored
    ``blocked_by:`` it ignores left every one of this file's tests green. The
    declarations were inert, so nothing downstream of them was being exercised.

    First: a hold lapses only when *every* declared blocker is discharged. Item
    6 names one completed blocker and is startable today; item 13 names one
    completed and one live and is not. Getting this backwards puts a genuinely
    blocked ticket in the list that says "pick this up".

    Second: the blocker is named. The board this replaced said "blocked by
    non-terminal internal blocker" and named nothing, which is the complaint
    the redesign was commissioned against, so the id *and* the title have to
    reach the row.
    """

    def test_the_fixture_declared_blockers_at_all(self):
        # The guard the mutation check earned. Every other assertion in this
        # class passes vacuously on a corpus whose blocker keys the loader
        # never read, so this one fails first and says why.
        declared = [row for row in self.nav["blocked"] if row["blockers"]]
        self.assertTrue(
            declared,
            "no rendered row carries a blocker: check the fixture writes "
            "'blocked_by', which backlog_fixtures renames to the 'blocked-by' "
            "frontmatter key collect_items reads — 'blocked_by:' in the file "
            "parses to [] in silence",
        )

    def test_a_partly_discharged_hold_is_still_held(self):
        # Item 13 declares one completed blocker and one live one. A renderer
        # that lapses a hold as soon as ANY blocker closes puts it in § 01.
        declared = sorted(str(ref) for ref in self.items["13"]["blocked_by"])
        self.assertEqual(["9", "90"], declared)
        self.assertIn("13", [row["id"] for row in self.nav["blocked"]])
        self.assertNotIn("13", [row["id"] for row in self.nav["ready"]])

    def test_a_fully_discharged_hold_is_startable(self):
        lapsed = [row for row in self.nav["ready"] if row["band"] == "G′"]
        self.assertEqual(["6"], [row["id"] for row in lapsed])
        for row in lapsed:
            self.assertTrue(row["blockers"])
            self.assertTrue(all(b["discharged"] for b in row["blockers"]))

    def test_every_blocked_row_keeps_a_live_blocker(self):
        self.assertTrue(self.nav["blocked"])
        for row in self.nav["blocked"]:
            with self.subTest(row=row["id"]):
                self.assertTrue(row["blockers"])
                self.assertTrue(any(not b["discharged"] for b in row["blockers"]))

    def test_every_blocker_reference_carries_id_and_title(self):
        for row in self.nav["blocked"]:
            for blocker in row["blockers"]:
                with self.subTest(row=row["id"], blocker=blocker["id"]):
                    self.assertTrue(blocker["id"])
                    self.assertTrue(
                        blocker["title"],
                        "blocker %s on row %s rendered without a title"
                        % (blocker["id"], row["id"]),
                    )

    def test_the_multi_blocker_row_names_both_of_them(self):
        # Item 14 is held by two live blockers, so a renderer that stops at the
        # first still looks right on every other row on the board.
        row = next(r for r in self.nav["blocked"] if r["id"] == "14")
        self.assertEqual(["2", "9"], sorted(b["id"] for b in row["blockers"]))

    def test_blockers_render_only_in_the_blocked_section(self):
        """``show_blockers`` is the gate, and § 01 carries rows that would fill it.

        The lapsed row (#6) has a blocker and sits in § 01, so a macro that
        ignored the flag would render one there — which is a "waiting on"
        column whose whole content is a hold that has already ended.
        """
        listed = sum(len(row["blockers"]) for row in self.nav["blocked"])
        self.assertGreater(listed, 0)
        self.assertGreater(
            sum(len(row["blockers"]) for row in self.nav["ready"]), 0,
            "the guard: § 01 must carry a row with a blocker on it",
        )
        self.assertEqual(listed, self.parsed.classes.get("band__blocker", 0))

    def test_blocker_ids_and_titles_reach_the_rendered_html(self):
        # The view-model assertions above prove the join; this proves it
        # survives the template, which is where a mis-spelled key silently
        # renders a blank instead of raising.
        for row in self.nav["blocked"]:
            for blocker in row["blockers"]:
                with self.subTest(row=row["id"], blocker=blocker["id"]):
                    self.assertIn("#%s" % blocker["id"], self.html)
                    self.assertIn(escape(blocker["title"]), self.html)

    def test_held_records_inside_an_epic_are_counted_not_listed(self):
        # ``held_total`` counts every held record on the board; the blocked
        # section lists only the loose ones. Without the wider number the page
        # cannot tell an unblocked board from one whose blocked work all sits
        # inside epics.
        listed = {row["id"] for row in self.nav["blocked"]}
        self.assertGreater(self.nav["held_total"], len(listed))
        self.assertEqual(
            self.nav["held_total"] - len(listed), self.nav["held_inside_epics"]
        )

    def test_a_board_whose_held_work_is_all_inside_epics_says_so_on_the_epics(self):
        """The empty-but-not-unblocked case, stated where the records are.

        This corpus holds something and has no loose blocked row to list. The
        page used to answer that with a whole section — a heading, a "1 held"
        count, and a body whose only sentence was that the record was
        somewhere else. The fact survives; the empty section does not. It is a
        clause on the epic lede now, beside the map that draws the record.
        """
        with tempfile.TemporaryDirectory() as tmp:
            state = _state_for(_ALL_HELD_INSIDE_EPICS, Path(tmp))
            nav = build_navigator(state, None)
            self.assertEqual([], nav["blocked"])
            self.assertEqual(1, nav["held_total"])
            self.assertEqual(1, nav["held_inside_epics"])
            html = _render("navigator.html", nav=nav)
            parsed = _parse(html)
            self.assertNotIn("nav-blocked", parsed.ids)
            self.assertIn("nav-epics", parsed.ids)
            # The claim itself, not its wording: the count reaches the page and
            # it reaches the section that draws the record.
            epics = html[html.index('id="nav-epics"'):]
            self.assertIn("held by a live blocker", epics[: epics.index("</section>")])
            self.assertEqual([], parsed.nested_anchors)

    def test_an_unblocked_board_keeps_its_blocked_section(self):
        """The other arm, and the reason the gate is not "hide when empty".

        "Nothing on this board waits on a live blocker" is a finding about the
        board and the section is where it is stated. Only the case where the
        held records exist and are drawn elsewhere loses its section.
        """
        with tempfile.TemporaryDirectory() as tmp:
            state = _state_for(_SMALL_CORPUS, Path(tmp))
            nav = build_navigator(state, None)
            self.assertEqual([], nav["blocked"])
            self.assertEqual(0, nav["held_total"])
            self.assertIn("nav-blocked", _parse(_render("navigator.html", nav=nav)).ids)


class TestUnrecognisedStatusIsDisclosed(_Fixture):
    """A rank made on a status cortex does not know says so, at the claim.

    Cortex installs into repos that run their own status vocabularies, so an
    unrecognised value is deliberately still ranked — banding ``must-have`` as
    untriaged would empty that repo's board. The obligation that comes with
    ranking it is disclosure, on the row that makes the claim.

    The cost on an ordinary board is asserted too, because a disclosure that
    fires on every row is decoration rather than a signal.
    """

    ICEBOX: tuple[dict, ...] = (
        {"id": 10, "title": "Plain low ticket", "type": "chore",
         "status": "backlog", "priority": "low", "updated": "2026-04-01"},
        {"id": 98, "title": "Unknown status, top priority", "type": "feature",
         "status": "icebox", "priority": "critical", "updated": "2026-04-03"},
    )

    def _rows(self, nav: dict) -> list[dict]:
        return (
            list(nav["ready"])
            + list(nav["blocked"])
            + [row for panel in nav["tail"] for row in panel["rows"]]
        )

    def test_the_unknown_status_record_still_reaches_the_ranking(self):
        # The half of the behaviour that must NOT change: it is ranked, not
        # swept off the board for using a word cortex has not seen.
        with tempfile.TemporaryDirectory() as tmp:
            nav = build_navigator(_state_for(self.ICEBOX, Path(tmp)), None)
            self.assertIn("98", [row["id"] for row in nav["ready"]])

    def test_the_row_carries_a_status_note_naming_the_raw_value(self):
        row = next(r for r in self._rows(self.nav) if r["id"] == "8")
        self.assertIn(self.items["8"]["status"], row["status_note"])

    def test_the_note_reaches_the_rendered_row(self):
        # The chip is the machine token: without it the note is computed and
        # dropped, and the ranking makes its claim with nothing next to it.
        noted = [r for r in self._rows(self.nav) if r["status_note"]]
        self.assertTrue(noted)
        self.assertEqual(len(noted), self.parsed.classes.get("nav-chip--warn", 0))

    def test_the_disclosure_is_selective_not_universal(self):
        # The main corpus carries one deliberately hostile record (item 8,
        # ``status: icebox``) alongside ordinary ``backlog`` ones, so it tests
        # both arms at once: a note on every row would mean the predicate had
        # inverted, and a note on none would mean it never fires.
        rows = self._rows(self.nav)
        self.assertTrue([r for r in rows if r["status_note"]], "it never fired")
        self.assertTrue([r for r in rows if not r["status_note"]], "it fired on all")
        for row in rows:
            with self.subTest(row=row["id"]):
                recognised = (row["status"] or "").lower() in bands_mod.OPEN_STATUSES
                self.assertEqual(recognised, not row["status_note"])


class TestHeadDetectionMatchesWhatIsDrawn(unittest.TestCase):
    """Band E′ and "heads a group" are different sets, and the gap ran both ways.

    ``_partition`` used to skip band-E′ rows from every list, on the assumption
    that band E′ is what § 02 draws a heading for. It is not. § 02 is built from
    the parent map, and the two disagree in both directions:

    * An epic whose children have **all completed** is in band E′ but heads no
      group. Keying on the band skipped it from every list while § 02 had
      nothing to render, so it left the page — and the reconciliation, which
      counted band-E′ rows as "heads", still said ``ok``. That is precisely the
      silent drop off a read-only board the footer exists to catch.
    * A ticket typed ``feature`` or ``chore`` that another ticket names as its
      ``parent`` heads a group but is **not** in band E′, so it rendered as a
      § 02 heading *and* as a § 01 row — a direct violation of one record, one
      appearance.

    Widening group detection past ``type: epic`` was deliberate (a de-facto epic
    typed ``chore`` has children and must group them), so both are fixed by
    asking the rendered set rather than by narrowing detection back.

    Each case is its own two-record corpus because the shared fixture cannot
    hold them: one needs an epic with no live children, the other needs a
    non-epic parent, and both would perturb every count the other classes pin.
    """

    def _nav(self, items):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return build_navigator(_state_for(items, Path(tmp.name)), None)

    def test_an_epic_with_no_live_children_still_reaches_the_page(self):
        nav = self._nav(
            [
                {"id": "1", "title": "Childless epic", "type": "epic",
                 "status": "backlog", "priority": "medium"},
                {"id": "2", "title": "A loose ticket", "type": "chore",
                 "status": "backlog", "priority": "medium"},
            ]
        )
        drawn = {
            tid
            for bucket in _appearance_buckets(nav, {"1", "2"}).values()
            for tid in bucket
        }
        self.assertIn("1", drawn)

    def test_a_childless_epic_is_not_counted_as_a_head_it_never_drew(self):
        nav = self._nav(
            [
                {"id": "1", "title": "Childless epic", "type": "epic",
                 "status": "backlog", "priority": "medium"},
                {"id": "2", "title": "A loose ticket", "type": "chore",
                 "status": "backlog", "priority": "medium"},
            ]
        )
        self.assertEqual([], nav["epics"])
        self.assertEqual(0, nav["recon"]["heads"])
        self.assertTrue(nav["recon"]["ok"])

    def test_a_non_epic_parent_is_a_heading_and_not_also_a_row(self):
        nav = self._nav(
            [
                {"id": "1", "title": "Feature that is a parent", "type": "feature",
                 "status": "backlog", "priority": "high"},
                {"id": "2", "title": "Its child", "type": "chore",
                 "status": "backlog", "priority": "medium", "parent": "1"},
            ]
        )
        buckets = _appearance_buckets(nav, {"1", "2"})
        appearances = [tid for bucket in buckets.values() for tid in bucket]
        self.assertEqual(sorted(set(appearances)), sorted(appearances))
        self.assertEqual(["1"], [epic["id"] for epic in nav["epics"]])
        self.assertNotIn("1", buckets["ready"])

    def test_the_non_epic_parent_still_groups_its_child(self):
        """Non-vacuity guard: detection must stay wide, not narrow to type."""
        nav = self._nav(
            [
                {"id": "1", "title": "Feature that is a parent", "type": "feature",
                 "status": "backlog", "priority": "high"},
                {"id": "2", "title": "Its child", "type": "chore",
                 "status": "backlog", "priority": "medium", "parent": "1"},
            ]
        )
        self.assertEqual(
            ["2"], [kid["id"] for epic in nav["epics"] for kid in epic["children"]]
        )


class TestDanglingBlockerRef(unittest.TestCase):
    """A blocker naming no known ticket is not offered as a link.

    The § 03 lede promises that each row "names the live blocker holding it".
    A ref the corpus cannot resolve was printed there as a linked ``#<uuid>``
    pointing at ``/tickets/<uuid>``, which returns 404 — the row named
    something that does not exist and invited a click that dead-ends.

    The cause was upstream of the markup and is what these assertions pin:
    ``view._corpus_of`` stubbed a record for *every* off-slice ref, including
    the ones the feed had already reported as ``not_found``. That stub made the
    ref a known record inside ``build_graph``, whose sole test for
    ``unresolvable`` is membership in exactly that set — so the edge came back
    ``external``, indistinguishable from a real ticket sitting off the board,
    and the ``unresolvable`` arm the row, the "why" sentence and the epic map's
    external lane all branch on could never be reached from a snapshot.
    """

    REF = "6ba7b810-9dad-11d1-80b4-00c04fd430c8"

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.state = _state_for(_DANGLING_BLOCKER, Path(cls._tmp.name))
        cls.nav = build_navigator(cls.state, None)
        cls.html = _render("navigator.html", nav=cls.nav)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_the_fixture_actually_held_the_row(self):
        # The guard the mutation rule earns: every assertion below passes
        # vacuously on a corpus whose blocker declaration the loader ignored.
        self.assertEqual(["200"], [row["id"] for row in self.nav["blocked"]])
        self.assertEqual(
            [self.REF],
            [b["id"] for row in self.nav["blocked"] for b in row["blockers"]],
        )

    def test_the_unresolvable_ref_carries_no_href(self):
        blocker = self.nav["blocked"][0]["blockers"][0]
        self.assertTrue(blocker["unresolvable"])
        self.assertIsNone(blocker["href"])

    def test_no_anchor_in_the_markup_points_at_the_dangling_ref(self):
        self.assertNotIn('href="/tickets/%s"' % self.REF, self.html)

    def test_the_ref_still_reaches_the_reader(self):
        # Unlinking it must not silently drop it: the ref is the only handle
        # the operator has for finding what the declaration meant.
        self.assertIn(self.REF, self.html)
        self.assertIn("names no known ticket", self.html)

    def test_a_resolvable_off_board_blocker_keeps_its_link(self):
        # The complement, so the fix cannot be "unlink every blocker". An
        # archived-but-real blocker is a page that exists and must stay
        # clickable.
        with tempfile.TemporaryDirectory() as tmp:
            corpus = _DANGLING_BLOCKER[1:] + (
                {"id": 202, "title": "Held by a real off-board ticket",
                 "type": "bug", "status": "backlog", "priority": "medium",
                 "blocked_by": [203], "updated": "2026-03-01"},
                {"id": 203, "title": "Real, and in progress", "type": "feature",
                 "status": "in-progress", "priority": "high",
                 "updated": "2026-03-01"},
            )
            nav = build_navigator(_state_for(corpus, Path(tmp)), None)
            blockers = [b for row in nav["blocked"] for b in row["blockers"]]
            self.assertEqual(["203"], [b["id"] for b in blockers])
            self.assertFalse(blockers[0]["unresolvable"])
            self.assertEqual("/tickets/203", blockers[0]["href"])


class TestDegenerateCorpus(unittest.TestCase):
    """Five items, zero epics, zero edges — cortex-command's own shape.

    The page must render, and it must not render *empty*: a correct small board
    is a ready list and a tail, and the sections that have nothing to show must
    be absent rather than present and blank, which reads as a fault.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.state = _state_for(_SMALL_CORPUS, Path(cls._tmp.name))
        cls.nav = build_navigator(cls.state, None)
        cls.html = _render("navigator.html", nav=cls.nav)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_navigator_renders_without_raising(self):
        self.assertGreater(len(self.html.strip()), 0)
        self.assertEqual([], _parse(self.html).nested_anchors)

    def test_the_small_slice_still_ranks_and_reconciles(self):
        self.assertGreater(len(self.nav["ready"]), 0)
        self.assertTrue(self.nav["recon"]["ok"])
        self.assertEqual(
            len(self.state.backlog_snapshot["items"]), self.nav["recon"]["total"]
        )

    def test_a_corpus_with_no_parents_renders_no_epic_section(self):
        # This is the case that made the epic map an empty nav tab on the repo
        # it ships from. Folded in, the section simply does not exist and the
        # page is whole without it.
        self.assertEqual([], self.nav["epics"])
        self.assertEqual(0, self.nav["epic_children"])
        self.assertNotIn("nav-epics", _parse(self.html).ids)

    def test_a_corpus_with_no_edges_draws_no_geometry(self):
        self.assertEqual(0, self.nav["mapped_epics"])
        self.assertEqual(0, _parse(self.html).tags.get("svg", 0))

    def test_the_register_has_no_gap_where_the_epic_section_stood(self):
        """Ordinals count the sections that rendered, not a fixed set of four.

        Two of the four sections are conditional. Against hardcoded ordinals
        this corpus — the shape of the repo the dashboard ships from — printed
        § 01 · § 03 · § 04, and a hole in a numbered register reads as a
        section that failed to draw, which is precisely what the reconciliation
        line at the foot of the page exists to rule out.
        """
        marks = _section_ordinals(self.html)
        self.assertEqual([1, 2, 3], marks)

    def test_ids_stay_unique_on_the_small_slice(self):
        parsed = _parse(_render_nav(self.state))
        seen: dict[str, int] = {}
        for value in parsed.ids:
            seen[value] = seen.get(value, 0) + 1
        self.assertEqual([], sorted(k for k, n in seen.items() if n > 1))


class TestAbsentSnapshot(unittest.TestCase):
    """A ``None`` snapshot renders an empty state, never a traceback.

    ``None`` is two different facts — never polled, and a non-``cortex-backlog``
    backend, which clears the snapshot — and the surface must distinguish them
    rather than raising on either.
    """

    def test_view_models_are_schema_complete_when_unpolled(self):
        state = DashboardState()
        nav = build_navigator(state, None)
        self.assertFalse(nav["available"])
        # Schema-complete: the keys the template touches all exist and are
        # falsy, so it branches on `available` instead of guarding each access.
        # A dotted lookup that found an Undefined would render the empty string
        # and report a blank board rather than an unpolled one.
        self.assertIn("backend", nav)
        for key in (
            "ready", "blocked", "held_total", "epics", "epic_children",
            "mapped_epics", "tail", "cycles", "corpus", "recon", "slice_total",
            "stale", "polled_ts", "as_of",
        ):
            with self.subTest(key=key):
                self.assertIn(key, nav)
                self.assertFalse(nav[key])

    def test_unpolled_fragments_render(self):
        state = DashboardState()
        self.assertGreater(len(_render_nav(state).strip()), 0)

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
    """The page shell extends base.html and carries the poll target.

    It also owns the hover card and the ticket modal, which is the placement
    that keeps them alive: an element inside the poll target is destroyed every
    30 seconds, so a dialog there would be torn out from under an operator
    mid-read and a card would be left describing a row that no longer exists.
    """

    def _shell(self) -> str:
        return templates.env.get_template("backlog.html").render(
            request=_fake_request("/backlog"), state=self.state
        )

    def test_backlog_shell_renders(self):
        parsed = _parse(self._shell())
        self.assertIn("navigator-panel", parsed.ids)
        self.assertEqual([], parsed.nested_anchors)

    def test_the_hover_card_and_modal_live_outside_the_poll_target(self):
        # Machine tokens: the delegated handlers in base.html look them up by
        # id, and an id that moved into the fragment would still render — the
        # card would simply stop surviving a swap, silently.
        shell = _parse(self._shell())
        self.assertIn("epic-hover", shell.ids)
        self.assertIn("ticket-modal", shell.ids)
        self.assertNotIn("epic-hover", self.parsed.ids)
        self.assertNotIn("ticket-modal", self.parsed.ids)

    def test_shell_ids_do_not_collide_with_the_fragment_they_load(self):
        # The fragment is morphed *into* the shell, so an id used by both would
        # be a duplicate on the live page and never on either render alone.
        self.assertEqual(set(), set(_parse(self._shell()).ids) & set(self.parsed.ids))


class TestRetiredSurfacesStayRetired(_Fixture):
    """The board does not argue, and these absences are how that stays true.

    The pick, its alternates, the swap conditions, the counterfactual, the
    six-term ledger and the three census tables are gone, along with the band
    letter, "why it sits here" and rank columns. Ranking by points and drawing
    the dependency structure is the whole job; what to work on is the ``/dev``
    skill's question. Absence assertions are what keep a removal removed — the
    cheapest way for any of this to return is one template include.
    """

    RETIRED_TEMPLATES = (
        "_nav_pick.html", "_nav_ledger.html", "_nav_census.html",
        "_nav_field.html", "_nav_groups.html",
    )
    RETIRED_KEYS = (
        "pick", "alternates", "field", "groups", "group_children",
        "ordered_groups", "census", "contender_count",
    )

    def test_the_retired_templates_are_gone_from_the_loader(self):
        for name in self.RETIRED_TEMPLATES:
            with self.subTest(template=name):
                with self.assertRaises(TemplateNotFound):
                    templates.env.get_template(name)

    def test_the_view_model_carries_no_retired_key(self):
        for key in self.RETIRED_KEYS:
            with self.subTest(key=key):
                self.assertNotIn(key, self.nav)
                self.assertNotIn(key, build_navigator(DashboardState(), None))

    def test_the_page_renders_only_the_four_sections(self):
        # ``<section>`` ids only: the per-epic and per-panel disclosures carry
        # their own, and so does the filter strip and its two controls, none of
        # which are sections. Matched on the element rather than on the id
        # prefix, so a fifth section cannot slip in under a name this list
        # happens not to exclude.
        sections = [
            i for i in self.parsed.section_ids if i.startswith("nav-")
        ]
        self.assertEqual(
            ["nav-blocked", "nav-epics", "nav-ready", "nav-tail"], sorted(sections)
        )

    def test_no_alternate_disclosure_survives(self):
        self.assertEqual([], [i for i in self.parsed.ids if i.startswith("nav-alt")])


class TestEpicsLeadThePage(_Fixture):
    """Structure before list, and the same rule when there is no structure.

    A board's groups say what it is made of. Thirty loose rows above them means
    a reader forms a picture of the board and then meets the thing that
    organises it, which is the wrong way round on every corpus that has one.
    """

    def test_epics_is_the_first_section(self):
        self.assertEqual("nav-epics", self.parsed.section_ids[0])

    def test_ready_leads_when_there_is_no_epic(self):
        # Not a special case: the section simply is not there, and the register
        # renumbers from what rendered.
        with tempfile.TemporaryDirectory() as tmp:
            parsed = _parse(_render_nav(_state_for(_SMALL_CORPUS, Path(tmp))))
            self.assertEqual("nav-ready", parsed.section_ids[0])
            self.assertNotIn("nav-epics", parsed.section_ids)

    def test_the_register_is_contiguous_from_one(self):
        marks = _section_ordinals(self.html)
        self.assertEqual(list(range(1, len(marks) + 1)), marks)


class TestStartableGroupsSortAboveParkedOnes(unittest.TestCase):
    """A group nobody can start never outranks one somebody can.

    The key was ``(-count, -ready, id)``, so size decided first and a group of
    five deferred children sat above four groups that had ready work — measured
    on the wild-light board, where a parked five-child epic ranked fourth of
    thirteen while three epics with ready children ranked below it.

    Both halves matter and the second is the one a naive fix drops: inside the
    startable half the order is still largest-first, because "offers something
    today" is a tiebreaker's worth of information once every group has it.
    """

    def _epics(self, items):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        nav = build_navigator(_state_for(items, Path(tmp.name)), None)
        return [epic["id"] for epic in nav["epics"]]

    @staticmethod
    def _group(head, kids, status):
        """One epic head plus *kids* children, all carrying *status*."""
        out = [{"id": head, "title": "Epic %s" % head, "type": "epic",
                "status": "backlog", "priority": "medium"}]
        out += [
            {"id": "%s%02d" % (head, n), "title": "Child %d" % n, "type": "chore",
             "status": status, "priority": "medium", "parent": head}
            for n in range(1, kids + 1)
        ]
        return out

    def test_a_big_deferred_group_sorts_below_a_small_startable_one(self):
        items = self._group("1", 5, "deferred") + self._group("2", 2, "backlog")
        self.assertEqual(["2", "1"], self._epics(items))

    def test_a_held_only_group_demotes_by_the_same_term(self):
        # Blocked-only groups are not a special case: nothing in them is
        # startable, which is the one thing the leading term asks.
        items = self._group("1", 4, "backlog") + self._group("2", 2, "backlog")
        items[1]["blocked_by"] = ["201"]
        items[2]["blocked_by"] = ["201"]
        items[3]["blocked_by"] = ["201"]
        items[4]["blocked_by"] = ["201"]
        self.assertEqual(["2", "1"], self._epics(items))

    def test_largest_first_still_decides_among_startable_groups(self):
        items = self._group("1", 2, "backlog") + self._group("2", 5, "backlog")
        self.assertEqual(["2", "1"], self._epics(items))


class TestHeadStateComesFromTheHead(unittest.TestCase):
    """The word on the shut line is the head's own status, never the children's.

    The arm tested ``on_board``, and a deferred record is on the board — so a
    head carrying ``status: deferred`` rendered indistinguishably from a live
    one while its children were reported as deferred beneath it.

    The tempting generalisation is to call a group deferred when every child
    is. It states something the corpus does not: the case that prompted this
    was a head at ``backlog`` over five deferred children, where deriving would
    have printed a status the ticket does not carry and hidden the grooming
    defect — the head is the thing that is wrong, and the board's job is to
    show it, not to launder it into a consistent-looking group.
    """

    def _epics(self, items):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        nav = build_navigator(_state_for(items, Path(tmp.name)), None)
        return {epic["id"]: epic for epic in nav["epics"]}

    _CHILD = {"id": "2", "title": "A child", "type": "chore", "priority": "medium",
              "parent": "1"}

    def test_a_deferred_head_says_so(self):
        epics = self._epics(
            [
                {"id": "1", "title": "Parked epic", "type": "epic",
                 "status": "deferred", "priority": "medium"},
                {**self._CHILD, "status": "deferred"},
            ]
        )
        self.assertEqual("deferred", epics["1"]["head_state"])

    def test_a_live_head_over_deferred_children_claims_nothing(self):
        epics = self._epics(
            [
                {"id": "1", "title": "Live epic", "type": "epic",
                 "status": "backlog", "priority": "medium"},
                {**self._CHILD, "status": "deferred"},
                {"id": "3", "title": "Another child", "type": "chore",
                 "status": "deferred", "priority": "medium", "parent": "1"},
            ]
        )
        epic = epics["1"]
        self.assertEqual("", epic["head_state"])
        # The children's disposition is still reported, as a count.
        self.assertEqual(2, epic["deferred"])
        self.assertEqual("2 deferred", epic["summary"])

    def test_a_live_head_over_live_children_says_nothing(self):
        epics = self._epics(
            [
                {"id": "1", "title": "Live epic", "type": "epic",
                 "status": "backlog", "priority": "medium"},
                {**self._CHILD, "status": "backlog"},
            ]
        )
        self.assertEqual("", epics["1"]["head_state"])


class TestTailPanelsNameOneReasonEach(_Fixture):
    """Every tail panel is one reason, and the reason is its label.

    The single panel this replaced was labelled "untriaged · closed in place ·
    off-board" — three unrelated findings under one heading, so no row in it
    could be read without opening the ticket. The split is asserted at the
    classifier, because the corpus a test can write does not reach every arm
    and an arm that cannot be reached from a fixture is exactly the one that
    rots.
    """

    #: Every panel key the view may emit. A panel outside this set is one the
    #: template has no gloss for.
    DECLARED = {"deferred", "untriaged", "offboard", "unruled"}

    @staticmethod
    def _row(tid: str, status: str) -> bands_mod.Row:
        return bands_mod.Row(
            id=tid, title="t", points=0, rank=None, why="", status=status,
            priority=None, type=None, blockers=[],
        )

    def test_each_arm_of_the_classifier(self):
        cases = (
            ("5", "deferred", frozenset({"5"}), "deferred"),
            ("7", "new", frozenset({"7"}), "untriaged"),
            ("8", "icebox", frozenset({"8"}), "unruled"),
            ("9", "backlog", frozenset({"1"}), "offboard"),
        )
        for tid, status, order, expected in cases:
            with self.subTest(status=status, expected=expected):
                self.assertEqual(
                    expected, view_mod._tail_panel_of(self._row(tid, status), order)
                )

    def test_off_board_is_tested_before_untriaged(self):
        """The precedence is ``bands._RULES``', and it has to be.

        ``bands`` assigns band H off-board-first, so a record that is both
        absent from the ordering and ``status: new`` is banded for the former.
        A split that tested ``new`` first would file it under a reason the
        banding did not use, and the panel's label would be a claim no other
        part of the page makes.
        """
        self.assertEqual(
            "offboard",
            view_mod._tail_panel_of(self._row("9", "new"), frozenset({"1"})),
        )

    def test_an_absent_ordering_puts_nothing_off_board(self):
        # ``bands.partition`` reads a falsy ``item_order`` as "no ordering
        # known" and marks every record on-board. Passing a bare empty set
        # instead would file an orderless snapshot's entire tail as off-board.
        self.assertEqual(
            "unruled", view_mod._tail_panel_of(self._row("9", "backlog"), None)
        )

    def test_every_rendered_panel_is_declared_and_non_empty(self):
        self.assertTrue(self.nav["tail"])
        for panel in self.nav["tail"]:
            with self.subTest(panel=panel["key"]):
                self.assertIn(panel["key"], self.DECLARED)
                self.assertGreater(panel["count"], 0)
                self.assertEqual(panel["count"], len(panel["rows"]))

    def test_no_record_is_in_two_panels(self):
        seen = [row["id"] for panel in self.nav["tail"] for row in panel["rows"]]
        self.assertEqual(sorted(set(seen)), sorted(seen))

    def test_the_composite_label_is_gone(self):
        # An absence assertion, which is what keeps a removal removed.
        self.assertNotIn("closed in place", self.html)


class TestWholeRowIsTheTarget(_Fixture):
    """The row is the ticket, not the id cell.

    A title column holding 70% of the table's width and doing nothing when
    clicked is a target the eye reads as live and the pointer does not. The
    payload moves to the ``<tr>`` so the delegated handlers reach it from
    anywhere in the row — and the anchor stays exactly where it was, because it
    is what still works with JS off.
    """

    def _list_rows(self) -> list[dict]:
        return [
            row for row in self.parsed.rows
            if "nav-list__row" in (row.get("class") or "").split()
        ]

    def test_every_list_row_is_the_hoverable(self):
        rows = self._list_rows()
        self.assertGreater(len(rows), 0)
        for row in rows:
            with self.subTest(row=row.get("data-ticket")):
                self.assertIn("js-ticket", (row.get("class") or "").split())

    def test_every_list_row_carries_the_whole_payload(self):
        for row in self._list_rows():
            with self.subTest(row=row.get("data-ticket")):
                self.assertTrue(row.get("data-ticket"))
                for key in _HOVER_ATTRS:
                    self.assertTrue(row.get("data-t-%s" % key), key)

    def test_one_real_anchor_per_row_and_no_more(self):
        """The href stays real and stays the only one the click handler owns.

        cmd-click, middle-click, "open in new tab" and a browser with no JS all
        still reach the ticket page through it. It is marked so the handler can
        tell it from the blocker links in the same row, which point at OTHER
        tickets and must navigate rather than open this one.
        """
        self.assertEqual(
            len(self._list_rows()), self.parsed.classes.get("js-ticket-self", 0)
        )

    def test_the_id_cell_no_longer_carries_the_payload(self):
        # Two elements carrying one ticket's payload is how a hover card comes
        # to paint from the stale half of a row.
        for element in self.parsed.js_tickets:
            with self.subTest(ticket=element.get("data-ticket")):
                self.assertNotIn(
                    "nav-table__id", (element.get("class") or "").split()
                )


class TestFilterStrip(_Fixture):
    """The control over the loose lists, and the two things it must not do.

    It must not reach the epic maps — a frame's geometry is computed
    server-side and hiding one node would leave its arrows pointing at nothing
    — and it must not render in a state, because a fragment that differs per
    operator ends the byte-identical poll the whole surface rests on.
    """

    def test_the_strip_ships_hidden(self):
        # JS unhides it. A reader without JS is never shown a filter that
        # cannot filter.
        self.assertIn('id="nav-filter"', self.html)
        opening = self.html[self.html.index('id="nav-filter"'):]
        self.assertIn("hidden", opening[: opening.index(">")])

    def test_no_chip_is_rendered_pressed(self):
        # The server has no filter state to render. Every chip is off, every
        # row is visible, and the client applies whatever the operator left.
        self.assertNotIn('aria-pressed="true"', self.html)
        self.assertEqual(0, self.parsed.classes.get("nav-list__row--hidden", 0))

    def test_the_facets_are_the_loose_rows_own_types(self):
        loose = [
            *self.nav["ready"], *self.nav["blocked"],
            *(row for panel in self.nav["tail"] for row in panel["rows"]),
        ]
        counted: dict[str, int] = {}
        for row in loose:
            counted[row["type"]] = counted.get(row["type"], 0) + 1
        self.assertEqual(
            counted, {facet["value"]: facet["count"] for facet in self.nav["facets"]}
        )
        self.assertEqual(len(loose), self.nav["loose_total"])

    def test_an_epic_child_does_not_reach_the_facets(self):
        """The population is the rows the filter can actually hide.

        Every child in this corpus is typed ``feature``; a facet count built
        from the slice rather than from the loose rows would say so, and the
        chip would then promise to filter records it cannot touch.
        """
        self.assertGreater(self.nav["epic_children"], 0)
        self.assertEqual(
            self.nav["loose_total"],
            sum(facet["count"] for facet in self.nav["facets"]),
        )
        # The gap IS the epic children plus the heads, which is the whole
        # claim: the facets count the loose half of the board and no more.
        self.assertEqual(
            self.nav["recon"]["total"] - self.nav["loose_total"],
            self.nav["epic_children"] + self.nav["recon"]["heads"],
        )

    def test_every_list_is_filterable_and_reports_its_own_count(self):
        # One wrapper per table, each with the readout the client fills. A
        # table outside a wrapper is a list the filter silently does not reach.
        self.assertEqual(
            len(self.parsed.tables), self.parsed.classes.get("nav-list-wrap", 0)
        )
        self.assertEqual(
            len(self.parsed.tables), self.parsed.classes.get("nav-list__shown", 0)
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
