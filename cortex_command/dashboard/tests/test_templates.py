"""Integration tests for Jinja2 template rendering.

Tests construct DashboardState with synthetic data and render templates directly
via the Jinja2 environment (bypassing HTTP), then assert expected strings appear
in the rendered HTML.

Since the 2026-05-18 htmx redesign, base.html ships only empty section shells and
loads each panel's real content at runtime via ``hx-get="/partials/..."``. Panel
content tests therefore render the matching partial directly (mirroring the
``/partials/*`` route handler's template + context), while structural tests still
render base.html to assert the section shells exist.

Covers:
  - session panel with overnight data shows session_id and "round · N"
  - pipeline panel shows feature name and status badge
  - feature cards show task ratio "N / M tasks" and feature slugs
  - round history table shows the round id span and merged count
  - absent overnight renders "no active session"
  - absent pipeline renders "no pipeline · refinement queue empty"
  - round_history empty list renders "no rounds cleared yet"
  - triage board rows, groups, badges, and states, rendered against the feed
  - ticket_page.html badge strip, epic children, and per-artifact panels
  - ticket_page.html / ticket_artifact.html non-local-backend gate

The triage-board tests below differ from every other test in this file in one
way that is load-bearing: their input is not a hand-written dict. Each builds a
markdown corpus on disk and reads it back through the shipped
``ticket_feed.build_backlog_snapshot``, so a change to the feed's shape fails
these tests instead of silently rendering blanks. The board's whole risk
surface is joins between snapshot collections — an unconverted child id or a
misread envelope renders empty rather than raising — so a snapshot transcribed
by hand would assert only that the transcription matches itself.
"""

from __future__ import annotations

import re
import tempfile
import types
import unittest
from html.parser import HTMLParser
from pathlib import Path

from cortex_command.dashboard.app import templates
from cortex_command.dashboard.data import parse_backlog_titles
from cortex_command.dashboard.poller import DashboardState
from cortex_command.dashboard.tests import backlog_fixtures
from cortex_command.dashboard.ticket_feed import build_backlog_snapshot


def _fake_request(path: str = "/") -> types.SimpleNamespace:
    """Minimal stand-in for the Starlette Request the app injects via request-first
    TemplateResponse. base.html reads only ``request.url.path`` (for nav highlighting),
    so a namespace exposing ``.url.path`` is sufficient for direct-render tests."""
    return types.SimpleNamespace(url=types.SimpleNamespace(path=path))


def _make_overnight_fixture() -> dict:
    """Return a minimal overnight-state dict for rendering tests."""
    return {
        "session_id": "test-session-001",
        "current_round": 2,
        "phase": "running",
        "started_at": "2026-02-26T10:00:00+00:00",
        "features": {
            "feat-alpha": {
                "status": "merged",
                "started_at": "2026-02-26T10:00:00+00:00",
            },
            "feat-beta": {
                "status": "pending",
                "started_at": "2026-02-26T10:00:00+00:00",
            },
        },
        "round_history": [],
    }


def _make_feature_states_fixture() -> dict:
    """Return a minimal feature_states dict for rendering tests."""
    return {
        "feat-alpha": {
            "current_phase": "complete",
            "phase_transitions": [{"from": "research", "to": "complete", "ts": "2026-02-26T11:00:00+00:00"}],
            "rework_cycles": 0,
            "plan_progress": (3, 5),
        },
        "feat-beta": {
            "current_phase": None,
            "phase_transitions": [],
            "rework_cycles": 0,
            "plan_progress": None,
        },
    }


def _render(state: DashboardState) -> str:
    """Render base.html with the given state, returning the HTML string."""
    return templates.env.get_template("base.html").render(state=state, request=_fake_request())


def _render_partial(name: str, **context: object) -> str:
    """Render a panel partial directly, mirroring how the matching ``/partials/*``
    route handler renders it.

    Since the 2026-05-18 htmx redesign, base.html only ships empty section shells
    and loads each panel's real content at runtime via ``hx-get="/partials/..."``.
    Direct-render tests therefore target the partial, not base.html. ``request`` is
    always supplied to match the handlers' context contract (the handlers pass it
    unconditionally even though these partial bodies don't read it)."""
    return templates.env.get_template(name).render(request=_fake_request(), **context)


class TestSessionPanel(unittest.TestCase):
    """Tests for session_panel.html inclusion."""

    def test_shows_session_id_when_overnight_present(self):
        state = DashboardState()
        state.overnight = _make_overnight_fixture()
        state.feature_states = _make_feature_states_fixture()
        html = _render_partial("session_panel.html", state=state, last_session=None)
        self.assertIn("test-session-001", html)

    def test_shows_current_round(self):
        state = DashboardState()
        state.overnight = _make_overnight_fixture()
        state.feature_states = _make_feature_states_fixture()
        html = _render_partial("session_panel.html", state=state, last_session=None)
        # Redesign emits the round as the "round · N" stream-line token rather than
        # the pre-redesign "Round N" heading.
        self.assertIn("round · 2", html)

    def test_shows_no_active_session_when_overnight_absent(self):
        state = DashboardState()
        # state.overnight is None by default
        html = _render_partial("session_panel.html", state=state, last_session=None)
        # Redesign empty-state copy is lowercase with no trailing period.
        self.assertIn("no active session", html)

    def test_merged_badge_appears_when_feature_merged(self):
        state = DashboardState()
        state.overnight = _make_overnight_fixture()
        state.feature_states = _make_feature_states_fixture()
        html = _render(state)
        self.assertIn("merged", html)


class TestPipelinePanel(unittest.TestCase):
    """Tests for pipeline_panel.html inclusion."""

    def test_shows_feature_name_when_pipeline_present(self):
        state = DashboardState()
        state.pipeline = {
            "phase": "executing",
            "features": [{"name": "my-pipeline-feature", "status": "implementing"}],
        }
        html = _render(state)
        self.assertIn("my-pipeline-feature", html)

    def test_shows_no_active_pipeline_when_absent(self):
        state = DashboardState()
        # state.pipeline is None by default
        html = _render_partial("pipeline_panel.html", state=state)
        # Redesign empty-state copy replaced "No active pipeline." with this string.
        self.assertIn("no pipeline · refinement queue empty", html)

    def test_shows_phase(self):
        state = DashboardState()
        state.pipeline = {
            "phase": "executing",
            "features": [{"name": "feat", "status": "implementing"}],
        }
        html = _render(state)
        self.assertIn("executing", html)


class TestFeatureCards(unittest.TestCase):
    """Tests for feature_cards.html inclusion."""

    def test_shows_dash_for_none_plan_progress(self):
        state = DashboardState()
        state.overnight = _make_overnight_fixture()
        state.feature_states = {
            "feat-alpha": {
                "current_phase": None,
                "phase_transitions": [],
                "rework_cycles": 0,
                "plan_progress": None,
            },
            "feat-beta": {
                "current_phase": None,
                "phase_transitions": [],
                "rework_cycles": 0,
                "plan_progress": None,
            },
        }
        html = _render(state)
        self.assertIn("—", html)

    def test_shows_task_ratio_when_plan_progress_present(self):
        state = DashboardState()
        state.overnight = _make_overnight_fixture()
        state.feature_states = {
            "feat-alpha": {
                "current_phase": "implement",
                "phase_transitions": [],
                "rework_cycles": 0,
                "plan_progress": (3, 5),
            },
            "feat-beta": {
                "current_phase": None,
                "phase_transitions": [],
                "rework_cycles": 0,
                "plan_progress": None,
            },
        }
        html = _render_partial("feature_cards.html", state=state)
        # Redesign renders the plan ratio spaced as "N / M tasks" (was "N/M tasks").
        self.assertIn("3 / 5 tasks", html)

    def test_shows_feature_slug(self):
        state = DashboardState()
        state.overnight = _make_overnight_fixture()
        state.feature_states = _make_feature_states_fixture()
        html = _render_partial("feature_cards.html", state=state)
        self.assertIn("feat-alpha", html)
        self.assertIn("feat-beta", html)

    def test_shows_no_features_active_when_overnight_absent(self):
        state = DashboardState()
        html = _render_partial("feature_cards.html", state=state)
        # Redesign empty-state copy replaced "No features active." with this string.
        self.assertIn("no features in play · awaiting next round", html)


class TestRoundHistory(unittest.TestCase):
    """Tests for round_history.html inclusion."""

    def test_shows_round_number_in_table(self):
        state = DashboardState()
        overnight = _make_overnight_fixture()
        overnight["round_history"] = [
            {
                "round_number": 1,
                "started_at": "2026-02-26T09:00:00+00:00",
                "completed_at": "2026-02-26T10:00:00+00:00",
                "features_merged": ["feat-alpha"],
                "features_paused": [],
                "features_deferred": [],
            }
        ]
        state.overnight = overnight
        state.feature_states = _make_feature_states_fixture()
        html = _render_partial("round_history.html", state=state)
        # Redesign renders the round number as an "R{n}" id span, not a bare "<td>1</td>".
        self.assertIn('<span class="round-id">R1</span>', html)

    def test_shows_merged_count(self):
        state = DashboardState()
        overnight = _make_overnight_fixture()
        overnight["round_history"] = [
            {
                "round_number": 1,
                "started_at": "2026-02-26T09:00:00+00:00",
                "completed_at": "2026-02-26T10:00:00+00:00",
                "features_merged": ["feat-alpha", "feat-beta"],
                "features_paused": [],
                "features_deferred": [],
            }
        ]
        state.overnight = overnight
        state.feature_states = _make_feature_states_fixture()
        html = _render_partial("round_history.html", state=state)
        # Redesign renders the merged count inside a round-cell span ("2 · <slugs>"),
        # not a bare "<td>2</td>".
        self.assertIn('class="round-cell round-cell--good">2 · ', html)

    def test_shows_no_completed_rounds_when_history_empty(self):
        state = DashboardState()
        overnight = _make_overnight_fixture()
        overnight["round_history"] = []
        state.overnight = overnight
        state.feature_states = _make_feature_states_fixture()
        html = _render_partial("round_history.html", state=state)
        # Redesign empty-state copy replaced "No completed rounds yet." with this string.
        self.assertIn("no rounds cleared yet", html)

    def test_shows_no_completed_rounds_when_overnight_absent(self):
        state = DashboardState()
        html = _render_partial("round_history.html", state=state)
        # Redesign empty-state copy replaced "No completed rounds yet." with this string.
        self.assertIn("no rounds cleared yet", html)


class TestStructuralElements(unittest.TestCase):
    """Tests that verify required structural elements are present."""

    def test_round_history_section_exists(self):
        state = DashboardState()
        html = _render(state)
        self.assertIn('id="round-history"', html)

    def test_session_panel_section_exists(self):
        state = DashboardState()
        html = _render(state)
        self.assertIn('id="session-panel"', html)

    def test_pipeline_panel_section_exists(self):
        state = DashboardState()
        html = _render(state)
        self.assertIn('id="pipeline-panel"', html)

    def test_feature_cards_section_exists(self):
        state = DashboardState()
        html = _render(state)
        self.assertIn('id="feature-cards"', html)


class TestBacklogPanelBackendGate(unittest.TestCase):
    """backlog_panel.html renders a backend-aware 3-way (R5, R6c)."""

    def test_none_backend_renders_placeholder(self):
        state = DashboardState()
        state.backlog_backend = "none"
        # Populated counts must be IGNORED on the non-local arm.
        state.backlog_counts = {"backlog": 2, "complete": 1}
        html = _render_partial("backlog_panel.html", state=state)
        self.assertIn("backlog tracking disabled", html)
        self.assertNotIn("items tracked", html)
        self.assertNotIn("stack-bar", html)

    def test_external_backend_names_the_backend(self):
        state = DashboardState()
        state.backlog_backend = "github-issues"
        state.backlog_counts = {"backlog": 2}
        html = _render_partial("backlog_panel.html", state=state)
        self.assertIn("tracked externally via", html)
        self.assertIn("github-issues", html)
        self.assertNotIn("stack-bar", html)

    def test_cortex_backlog_populated_arm_unchanged(self):
        # R6c: the default arm's rendered output is byte-for-byte today's.
        state = DashboardState()
        state.backlog_backend = "cortex-backlog"
        state.backlog_counts = {"backlog": 2, "complete": 1}
        html = _render_partial("backlog_panel.html", state=state)
        self.assertIn("3 items tracked", html)
        self.assertIn("stack-bar", html)

    def test_cortex_backlog_empty_arm_unchanged(self):
        state = DashboardState()
        state.backlog_backend = "cortex-backlog"
        state.backlog_counts = {}
        html = _render_partial("backlog_panel.html", state=state)
        self.assertIn("no backlog items found", html)


class TestSiblingTemplateTitleFallback(unittest.TestCase):
    """feature_cards.html / escalations_panel.html slug-fallback under the
    title-clear — the deliberate spec.md:69 behavior change. Pins the two
    sibling consumers of state.backlog_titles cleared by the non-local poller
    arm so the fallback render is guarded, not just verbally acknowledged."""

    def test_feature_cards_falls_back_to_slug_when_titles_cleared(self):
        state = DashboardState()
        state.overnight = _make_overnight_fixture()
        state.feature_states = _make_feature_states_fixture()
        state.backlog_titles = {}  # the non-local arm clears this
        html = _render_partial("feature_cards.html", state=state)
        self.assertIn("feat-alpha", html)  # raw slug shown, no error

    def test_feature_cards_shows_title_when_present(self):
        # Contrast: a populated title IS shown — proves the fallback is
        # title-when-present / slug-when-cleared, not slug-always.
        state = DashboardState()
        state.overnight = _make_overnight_fixture()
        state.feature_states = _make_feature_states_fixture()
        state.backlog_titles = {"feat-alpha": "Alpha Human Title"}
        html = _render_partial("feature_cards.html", state=state)
        self.assertIn("Alpha Human Title", html)

    def test_escalations_panel_falls_back_to_slug_when_titles_cleared(self):
        state = DashboardState()
        state.open_questions_total = 1
        state.overnight = {"features": {"feat-alpha": {"status": "running"}}}
        state.feature_escalations = {
            "feat-alpha": [
                {
                    "question": "Blocked on X?",
                    "escalation_id": "esc-1",
                    "ts": "2026-06-24T10:00:00+00:00",
                }
            ]
        }
        state.backlog_titles = {}  # the non-local arm clears this
        html = _render_partial("escalations_panel.html", state=state)
        self.assertIn("feat-alpha", html)  # raw slug shown, no error


# ---------------------------------------------------------------------------
# Triage board (templates/triage_board.html)
# ---------------------------------------------------------------------------
#
# Two helpers below carry the weight of this section: one builds the board's
# input by writing markdown and reading it back through the real feed, and one
# parses the rendered fragment into a tree. The parse is deliberate — ``grep -c``
# counts matching *lines*, so a substring assertion over rendered HTML is
# sensitive to where the template happens to break lines, and "this row shows
# its reason" is a statement about one element's content, not about the
# document. Assertions therefore run over parsed elements or over template
# source, never over the rendered string as if it were a file.

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
_BOARD_TEMPLATE = _TEMPLATE_DIR / "triage_board.html"

# The badge classes base.html actually defines. Anything else — a CSS custom
# property lifted from backlog_panel.html's map, or a run-outcome class from
# the badge(status=…) path — emits markup matching no rule.
_BADGE_CLASS_RE = re.compile(r"^badge-(red|amber|gray|green|blue|purple)$")

# Attributes that would take the operator somewhere else. Dead placeholder
# links are the defect this panel's epic cites, so their absence is asserted
# rather than assumed.
#
# `hx-get` was on this list while the board had no reader at all, when any
# fetch on a row could only have been a stub. It is off the list now that the
# row lazy-loads its own description in place: that request renders into the
# open row and moves nobody anywhere, which is the opposite of the defect
# being guarded. The guard did not weaken — `test_row_fetch_targets_a_live_
# route` below asserts the thing the old blanket ban was standing in for,
# namely that a row's fetch resolves to a real endpoint rather than "#".
#
# `href` is scoped to <summary> only, below, rather than dropped: a live link
# there would compete with the <details> disclosure toggle for the click. R19
# adds exactly one href outside <summary> — the link out to this ticket's own
# /tickets/{id} page — which `test_row_links_out_to_its_own_ticket_page`
# below asserts lands there and nowhere else.
_NAVIGATION_ATTRS = ("href", "hx-push-url", "onclick")

# One corpus exercising most of the board's joins at once, so the joins are
# tested against a single realistic snapshot rather than one contrived per
# assertion: an epic with two children (one tag-deferred at an eligible
# status, one blocked by a live sibling), a status-deferred item the readiness
# partition rejects, an item whose only blocker is already complete, and an
# item whose status, type, and priority are all outside the documented
# vocabularies. Terminal item 200 never reaches item_order but does resolve as
# a blocker, which is exactly why it is written as an ordinary sibling.
_BOARD_CORPUS = (
    {"id": 410, "title": "Command station", "type": "epic", "status": "backlog",
     "priority": "high"},
    {"id": 411, "title": "Ticket feed", "status": "backlog", "priority": "high",
     "parent": "410", "tags": ["deferred"]},
    {"id": 412, "title": "Triage board", "status": "backlog", "parent": "410",
     "blocked_by": ["411"], "lifecycle_phase": "implement"},
    {"id": 156, "title": "Shelved work", "status": "deferred"},
    {"id": 200, "title": "Landed already", "status": "complete"},
    {"id": 201, "title": "Freed by a complete blocker", "status": "backlog",
     "blocked_by": ["200"]},
    {"id": 300, "title": "Odd vocabulary", "status": "needs-triage",
     "type": "architecture", "priority": "contingent", "lifecycle_phase": "none"},
)

# Void elements never take an end tag, so the parser must not push them.
_VOID_TAGS = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
})


class _Element:
    """One parsed element: its tag, its attributes, and its ordered children.

    Children are ``_Element`` instances and ``str`` text runs, interleaved in
    document order.
    """

    __slots__ = ("tag", "attrs", "children")

    def __init__(self, tag: str, attrs: list | None = None):
        self.tag = tag
        # HTMLParser hands attributes over as (name, value) pairs, with value
        # None for a valueless attribute.
        self.attrs = {name: value or "" for name, value in attrs or []}
        self.children: list = []

    @property
    def classes(self) -> list[str]:
        return (self.attrs.get("class") or "").split()

    @property
    def text(self) -> str:
        """Whitespace-collapsed text of this element and its descendants.

        Children are joined with a space so adjacent elements never fuse into
        a token that neither of them rendered.
        """
        parts = [
            child if isinstance(child, str) else child.text
            for child in self.children
        ]
        return " ".join(" ".join(parts).split())

    def find_all(self, tag: str | None = None, css_class: str | None = None) -> list:
        """Return every descendant element matching *tag* and/or *css_class*."""
        found = []
        for child in self.children:
            if isinstance(child, str):
                continue
            tag_ok = tag is None or child.tag == tag
            class_ok = css_class is None or css_class in child.classes
            if tag_ok and class_ok:
                found.append(child)
            found.extend(child.find_all(tag, css_class))
        return found


class _FragmentParser(HTMLParser):
    """Build an ``_Element`` tree from a rendered partial."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Element("#fragment")
        self._stack = [self.root]

    def handle_starttag(self, tag, attrs):
        element = _Element(tag, attrs)
        self._stack[-1].children.append(element)
        if tag not in _VOID_TAGS:
            self._stack.append(element)

    def handle_startendtag(self, tag, attrs):
        self._stack[-1].children.append(_Element(tag, attrs))

    def handle_endtag(self, tag):
        # Close the nearest matching open element. A stray end tag is ignored
        # rather than unwinding the stack, so one malformed span cannot
        # silently reparent every element after it.
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag == tag:
                del self._stack[index:]
                return

    def handle_data(self, data):
        self._stack[-1].children.append(data)


def _parse(html: str) -> _Element:
    """Return the parsed root of a rendered fragment."""
    parser = _FragmentParser()
    parser.feed(html)
    parser.close()
    return parser.root


def _board_snapshot(items) -> dict:
    """Return the shipped feed's snapshot over a corpus written to disk.

    The corpus is markdown under a throwaway tree and comes back through
    ``ticket_feed.build_backlog_snapshot`` — the same call the slow poll makes,
    with the same title scan — so what these tests render is what the poller
    commits. The temporary tree is discarded once the snapshot exists; the
    snapshot itself holds no file handles.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        backlog_fixtures.write_corpus(root, items)
        backlog_dir = root / "cortex" / "backlog"
        lifecycle_dir = root / "cortex" / "lifecycle"
        return build_backlog_snapshot(
            backlog_dir,
            lifecycle_dir,
            dict(parse_backlog_titles(backlog_dir).by_id),
            backlog_fixtures.POLLED_TS,
        )


def _render_board(snapshot: dict | None) -> str:
    """Render triage_board.html for *snapshot*, mirroring the route handler."""
    state = DashboardState()
    state.backlog_snapshot = snapshot
    return _render_partial("triage_board.html", state=state)


def _row_map(element: _Element) -> dict:
    """Return ``{ticket id: row element}`` for the rows inside *element*.

    Scoped rather than global on purpose: "the child renders its title" is a
    claim about the row inside that epic's section, and a document-wide lookup
    would be satisfied by the same ticket rendering correctly somewhere else.
    """
    return {
        row.attrs.get("id", "").removeprefix("ticket-"): row
        for row in element.find_all("details", "ticket-row")
    }


def _rows(html: str) -> dict:
    """Return ``{ticket id: row element}`` across a whole rendered fragment."""
    return _row_map(_parse(html))


def _row_ids(element: _Element) -> list:
    """Return every row's ticket id in document order, duplicates kept."""
    return [
        row.attrs.get("id", "").removeprefix("ticket-")
        for row in element.find_all("details", "ticket-row")
    ]


def _badges(element: _Element) -> list:
    """Return every badge span inside *element*."""
    return element.find_all("span", "badge")


class TestTriageBoardRows(unittest.TestCase):
    """Row selection and the per-row joins into ``items`` (R3, R4, R6, R7)."""

    @classmethod
    def setUpClass(cls):
        cls.snapshot = _board_snapshot(_BOARD_CORPUS)
        cls.html = _render_board(cls.snapshot)
        cls.dom = _parse(cls.html)
        cls.rows = _row_map(cls.dom)
        # Rows scoped to the one epic's section: a child that renders blank
        # under its epic while rendering correctly in the flat list below is
        # the exact failure an unconverted child-id lookup produces.
        cls.epic_rows = _row_map(cls.dom.find_all("div", "epic-group")[0])

    def test_every_active_item_reaches_a_row(self):
        # R4: the row set is item_order, not ready. ready and ineligible
        # classify rows; they do not select them — a ready-only board would
        # drop every deferred and blocked item from the picture entirely.
        self.assertEqual(set(self.rows), set(self.snapshot["item_order"]))
        self.assertTrue(self.snapshot["ineligible"], "fixture must exercise ineligible")
        for entry in self.snapshot["ineligible"]:
            self.assertIn(entry["id"], self.rows)

    def test_each_active_item_renders_exactly_one_row(self):
        # Element ids must stay unique: base.html's sessionStorage restore
        # keys on d.id, so a ticket rendered twice — once under its epic and
        # once in the flat list — makes the restore ambiguous. An epic is the
        # case that used to break this: it is nobody's child, so it landed in
        # the flat list on top of heading its own group. The epic's row now
        # IS that heading, which is what keeps the count at exactly one.
        rendered = _row_ids(self.dom)
        self.assertEqual(sorted(rendered), sorted(self.snapshot["item_order"]))

    def test_an_epic_renders_once_as_its_group_head(self):
        # Regression: #410 rendered twice — as the epic-group heading and
        # again as an "Unparented" row for the same ticket, which also
        # asserted the falsehood that a group-heading epic has no parent.
        epic_rows = self.dom.find_all("details", "epic-head")
        self.assertEqual(len(epic_rows), 1)
        self.assertEqual(epic_rows[0].attrs.get("id"), "ticket-410")
        self.assertEqual(_row_ids(self.dom).count("410"), 1)
        flat = self.dom.find_all("div", "flat-group")[0]
        self.assertNotIn("410", _row_ids(flat))

    def test_epic_head_keeps_the_epics_own_classification(self):
        # Promoting the row to the heading must not cost the epic its own
        # status/priority/type badges — the old <h3> heading carried none of
        # them, which is why the duplicate flat row existed at all.
        epic_row = self.dom.find_all("details", "epic-head")[0]
        labels = [badge.text for badge in _badges(epic_row.find_all("summary")[0])]
        self.assertIn("epic", labels)
        self.assertIn("2 active", epic_row.find_all("summary")[0].text)

    def test_ineligible_rows_display_their_reason(self):
        # R4: the reason is the whole point of showing a rejected item.
        for entry in self.snapshot["ineligible"]:
            with self.subTest(item=entry["id"]):
                self.assertIn(entry["reason"], self.rows[entry["id"]].text)

    def test_ready_rows_are_marked_ready(self):
        self.assertTrue(self.snapshot["ready"], "fixture must exercise ready")
        for item_id in self.snapshot["ready"]:
            with self.subTest(item=item_id):
                self.assertIn("ready", self.rows[item_id].text)

    def test_epic_child_renders_title_and_status_text(self):
        # R6: child records carry id as int while items is str-keyed, so an
        # unconverted lookup yields a Jinja Undefined that renders blank
        # instead of raising. Asserting on visible text is what catches it.
        child_row = self.epic_rows["411"]
        self.assertIn("Ticket feed", child_row.text)
        self.assertIn("backlog", child_row.text)

    def test_child_display_fields_come_from_the_items_map(self):
        # R7: a child record carries only {id, spec, status, title}, so
        # priority and the deferral flags exist nowhere but items[str(id)].
        child_row = self.epic_rows["411"]
        self.assertIn("high", child_row.text)
        self.assertIn("tag · deferred", child_row.text)

    def test_rows_read_normalized_phase_not_raw_lifecycle_phase(self):
        # R7: items carries both lifecycle_phase (raw, still the literal
        # string "none" for some items) and phase (null-normalized).
        self.assertIn("phase · implement", self.epic_rows["412"].text)
        self.assertNotIn("phase", self.rows["300"].text)

    def test_rows_are_disclosures_with_summaries(self):
        # R13: rows are non-navigational <details>/<summary> disclosures.
        for item_id, row in self.rows.items():
            with self.subTest(item=item_id):
                self.assertEqual(row.tag, "details")
                self.assertTrue(row.find_all("summary"))


class TestTriageBoardEpicMap(unittest.TestCase):
    """Epic grouping and its envelope (R5, R8, R15)."""

    def test_one_epic_renders_one_section_and_no_schema_version(self):
        # R5: build_epic_map returns {"schema_version", "epics"}, so iterating
        # the outer dict yields those two literal keys and zero epic ids. A
        # board that read the envelope would render a "schema_version" group.
        snapshot = _board_snapshot(_BOARD_CORPUS)
        html = _render_board(snapshot)
        groups = _parse(html).find_all("div", "epic-group")
        self.assertEqual(len(groups), 1)
        self.assertIn("Command station", groups[0].text)
        self.assertNotIn("schema_version", html)

    def test_grouping_shape_is_identical_at_one_and_six_epics(self):
        # R8: presence selects the layout, never a count threshold. Six epics
        # is the same shape as one, repeated — not a different view.
        def shape(epic_count: int) -> tuple:
            items = []
            for index in range(epic_count):
                epic_id = 500 + index * 10
                items.append({"id": epic_id, "title": f"Epic {index}",
                              "type": "epic", "status": "backlog"})
                items.append({"id": epic_id + 1, "title": f"Child {index}",
                              "status": "backlog", "parent": str(epic_id)})
            items.append({"id": 900, "title": "Unparented", "status": "backlog"})
            dom = _parse(_render_board(_board_snapshot(items)))
            return (
                len(dom.find_all("div", "epic-group")),
                len(dom.find_all("div", "flat-group")),
            )

        self.assertEqual(shape(1), (1, 1))
        self.assertEqual(shape(6), (6, 1))

    def test_unparented_items_land_in_the_flat_list(self):
        # R8: every item_order id that is neither somebody's child nor an epic
        # heading its own group renders below. Epics are excluded because they
        # already render once above, as their group's head row — #410 is the
        # epic here, and it belongs to the epic group, not to "Unparented".
        html = _render_board(_board_snapshot(_BOARD_CORPUS))
        dom = _parse(html)
        flat = dom.find_all("div", "flat-group")
        self.assertEqual(len(flat), 1)
        self.assertEqual(set(_row_ids(flat[0])), {"156", "201", "300"})
        epic_group = dom.find_all("div", "epic-group")[0]
        self.assertEqual(set(_row_ids(epic_group)), {"410", "411", "412"})

    def test_live_child_of_a_closed_epic_renders_in_its_group(self):
        # #458: the rendered symptom. build_epic_map detects an epic by
        # scanning the list it is handed for `type: epic`, so feeding it the
        # active slice made the closed epic invisible as an epic — and its live
        # child dropped through the child-id exclusion into "Standalone",
        # asserting it had no parent when it plainly does.
        snapshot = _board_snapshot([
            {"id": 600, "title": "Closed epic", "type": "epic",
             "status": "complete"},
            {"id": 601, "title": "Late child", "status": "backlog",
             "parent": "600"},
            {"id": 900, "title": "Genuinely unparented", "status": "backlog"},
        ])
        dom = _parse(_render_board(snapshot))

        groups = dom.find_all("div", "epic-group")
        self.assertEqual(len(groups), 1)
        # The heading IS the epic's own row, so both ids live in the group.
        self.assertEqual(set(_row_ids(groups[0])), {"600", "601"})
        self.assertIn("Closed epic", groups[0].text)

        flat = dom.find_all("div", "flat-group")[0]
        self.assertEqual(set(_row_ids(flat)), {"900"})

    def test_closed_epic_without_live_children_renders_no_group(self):
        # The other half of #458's gate. Detection widened to the whole corpus;
        # the rendered set did not. Every finished epic would otherwise open a
        # "no active children" group — 34 of them on this repo.
        snapshot = _board_snapshot([
            {"id": 610, "title": "Finished and empty", "type": "epic",
             "status": "complete"},
            {"id": 611, "title": "Also done", "status": "complete",
             "parent": "610"},
            {"id": 901, "title": "Unparented", "status": "backlog"},
        ])
        dom = _parse(_render_board(snapshot))

        self.assertEqual(snapshot["epics"]["epics"], {})
        self.assertEqual(len(dom.find_all("div", "epic-group")), 0)
        self.assertEqual(set(_row_ids(dom.find_all("div", "flat-group")[0])), {"901"})

    def test_epic_with_zero_active_children_says_so(self):
        # R15: build_epic_map seeds its map with every epic id, zero-child
        # ones included, so this is reachable the moment a non-terminal epic's
        # last active child completes. No sampled repo exercises it.
        snapshot = _board_snapshot([
            {"id": 500, "title": "Lonely epic", "type": "epic", "status": "backlog"},
        ])
        self.assertEqual(list(snapshot["epics"]["epics"]), ["500"])
        html = _render_board(snapshot)
        groups = _parse(html).find_all("div", "epic-group")
        self.assertEqual(len(groups), 1)
        self.assertIn("no active children", groups[0].text)

    def test_unjoinable_epic_key_renders_under_its_raw_key(self):
        # Edge case: an epic key that is non-numeric or absent from items
        # renders under the raw key with no title, and the rest of the board
        # is unaffected — never a swallowed exception that degrades the whole
        # map to empty, which is indistinguishable from "no epics".
        snapshot = _board_snapshot([
            {"id": 600, "title": "Flat one", "status": "backlog"},
        ])
        snapshot["epics"]["epics"]["not-an-id"] = {"children": []}
        html = _render_board(snapshot)
        groups = _parse(html).find_all("div", "epic-group")
        self.assertEqual(len(groups), 1)
        self.assertIn("#not-an-id", groups[0].text)
        self.assertIn("600", _rows(html))


class TestTriageBoardBadges(unittest.TestCase):
    """Badge vocabulary and the two deferral flags (R9, R10, R12)."""

    def test_every_badge_uses_a_base_html_badge_class(self):
        # R9: backlog_panel.html's map holds CSS custom properties consumed as
        # an inline --c, so reusing it would emit class="badge var(--…)",
        # matching no rule; and badge(status=…) resolves the unrelated
        # feature/run-outcome vocabulary.
        html = _render_board(_board_snapshot(_BOARD_CORPUS))
        badges = _badges(_parse(html))
        self.assertTrue(badges, "fixture must render at least one badge")
        for badge in badges:
            with self.subTest(badge=badge.text):
                modifiers = [c for c in badge.classes if c != "badge"]
                self.assertTrue(
                    any(_BADGE_CLASS_RE.match(c) for c in modifiers),
                    f"badge {badge.text!r} carries {modifiers!r}",
                )
                self.assertNotIn("var(--", badge.attrs.get("class", ""))

    def test_unknown_status_type_and_priority_render_verbatim(self):
        # R10: all three vocabularies are open in practice (the item-creation
        # verb applies no choices=), and status: deferred appears in no
        # documented enum. Raw passthrough follows generate_index.py.
        html = _render_board(_board_snapshot(_BOARD_CORPUS))
        row = _rows(html)["300"]
        labels = {badge.text: badge.classes for badge in _badges(row)}
        for value in ("needs-triage", "architecture", "contingent"):
            with self.subTest(value=value):
                self.assertIn(value, labels)
                self.assertTrue(
                    any(_BADGE_CLASS_RE.match(c) for c in labels[value]),
                    f"{value!r} rendered without a fallback badge class",
                )

    def test_status_deferred_renders_as_a_status_badge(self):
        # R12: deferred_status is a status; the live case is #156 and #295.
        row = _rows(_render_board(_board_snapshot(_BOARD_CORPUS)))["156"]
        self.assertIn("deferred", [badge.text for badge in _badges(row)])

    def test_tag_deferred_is_a_flag_not_a_badge(self):
        # R12: the two flags are independent — a tag-deferred item at an
        # eligible status legitimately appears in ready — and the tag flag
        # must never be mistakable for the unrelated overnight-run outcome of
        # the same name, so it carries no badge- class at all.
        snapshot = _board_snapshot([
            {"id": 700, "title": "Tag deferred", "status": "backlog",
             "tags": ["deferred"]},
        ])
        self.assertIn("700", snapshot["ready"])
        html = _render_board(snapshot)
        row = _rows(html)["700"]
        self.assertIn("tag · deferred", row.text)
        self.assertNotIn("deferred", [badge.text for badge in _badges(row)])
        self.assertNotIn("badge-amber", html)


class TestTriageBoardBlockedState(unittest.TestCase):
    """Blocked is derived from the readiness partition (R11)."""

    def test_blocked_only_by_a_complete_item_is_not_blocked(self):
        # R11: triage.py badges blocked on any non-empty blocked_by, which is
        # over-inclusive — blockers pointing only at terminal items resolve
        # silently, so #201 is genuinely ready here.
        snapshot = _board_snapshot(_BOARD_CORPUS)
        self.assertIn("201", snapshot["ready"])
        row = _rows(_render_board(snapshot))["201"]
        self.assertNotIn("blocked", [badge.text for badge in _badges(row)])

    def test_blocked_by_a_live_item_shows_the_blocker_id_and_status(self):
        row = _rows(_render_board(_board_snapshot(_BOARD_CORPUS)))["412"]
        self.assertIn("blocked", [badge.text for badge in _badges(row)])
        self.assertIn("#411 (backlog)", row.text)

    def test_blocker_without_a_title_still_renders_id_and_status(self):
        # Edge case: title is frequently null in live data — the title scan is
        # non-recursive, so an archived blocker resolves to a status with no
        # title. The row must read "#<ref> (<status>)", never a blank.
        snapshot = _board_snapshot([
            {"id": 501, "title": "Waits on archived", "status": "backlog",
             "blocked_by": ["502"]},
            {"id": 502, "title": "Archived blocker", "status": "backlog",
             "archived": True},
        ])
        self.assertIsNone(snapshot["blocked_why"]["501"][0]["title"])
        row = _rows(_render_board(snapshot))["501"]
        self.assertIn("#502 (backlog)", row.text)


class TestTriageBoardRowIdentity(unittest.TestCase):
    """Ticket-derived ids, the summary-only navigation rule (R13), and the
    link out to the ticket page (R19)."""

    def test_row_ids_are_ticket_derived_and_survive_reordering(self):
        # item_order re-sorts on any priority or status change, so an
        # index-derived id would reopen the wrong rows after a morph — the
        # sessionStorage restore in base.html keys on the element id.
        snapshot = _board_snapshot(_BOARD_CORPUS)
        html = _render_board(snapshot)
        self.assertIn('id="ticket-412"', html)

        reordered = {**snapshot, "item_order": list(reversed(snapshot["item_order"]))}
        reordered_html = _render_board(reordered)
        self.assertIn('id="ticket-412"', reordered_html)

        forward, backward = list(_rows(html)), list(_rows(reordered_html))
        self.assertEqual(set(forward), set(backward))
        # Guard the guard: if the reversal changed nothing, the assertion
        # above would pass for a positional id too.
        self.assertNotEqual(forward, backward)

    def test_summary_carries_no_navigation_affordance(self):
        # A live link inside <summary> would compete with the <details>
        # disclosure toggle for the click — the exact defect this panel's
        # epic cites. The summary reads in place or not at all; it never
        # moves the operator to another surface.
        html = _render_board(_board_snapshot(_BOARD_CORPUS))
        for item_id, row in _rows(html).items():
            summary = row.find_all("summary")[0]
            for element in [summary, *summary.find_all()]:
                with self.subTest(item=item_id, tag=element.tag):
                    for attr in _NAVIGATION_ATTRS:
                        self.assertNotIn(attr, element.attrs)

    def test_row_links_out_to_its_own_ticket_page(self):
        # R19: the board connects to the per-ticket reader. The link lives in
        # the expanded area, never in <summary> (covered above), and it is
        # the row's only href — carrying that row's own id, never another's.
        html = _render_board(_board_snapshot(_BOARD_CORPUS))
        rows = _rows(html)
        self.assertTrue(rows, "fixture must render at least one row")
        self.assertIn('href="/tickets/412"', html)
        for item_id, row in rows.items():
            with self.subTest(item=item_id):
                hrefs = [
                    element.attrs["href"]
                    for element in row.find_all()
                    if "href" in element.attrs
                ]
                self.assertEqual(hrefs, [f"/tickets/{item_id}"])

    def test_row_fetch_targets_a_live_route(self):
        # What the blanket hx-get ban was really standing in for: a fetch on a
        # row must resolve to a real endpoint carrying the row's own id, never
        # a placeholder. "#" or an id-less path would reproduce the dead-link
        # defect through htmx instead of through href.
        html = _render_board(_board_snapshot(_BOARD_CORPUS))
        rows = _rows(html)
        self.assertTrue(rows, "fixture must render at least one row")
        for item_id, row in rows.items():
            targets = [
                element.attrs["hx-get"]
                for element in [row, *row.find_all()]
                if "hx-get" in element.attrs
            ]
            with self.subTest(item=item_id):
                self.assertEqual(
                    targets,
                    [f"/partials/ticket/{item_id}"],
                    f"row {item_id} must carry exactly one fetch, at its own id",
                )

    def test_row_description_target_survives_a_morph(self):
        # The board re-renders every 30s and the description is lazy-loaded, so
        # the placeholder the poll re-emits would overwrite loaded prose in an
        # open row unless the target is both id-addressable and preserved.
        html = _render_board(_board_snapshot(_BOARD_CORPUS))
        for item_id, row in _rows(html).items():
            holders = [
                element
                for element in row.find_all()
                if element.attrs.get("id") == f"ticket-desc-{item_id}"
            ]
            with self.subTest(item=item_id):
                self.assertEqual(len(holders), 1)
                self.assertEqual(holders[0].attrs.get("hx-preserve"), "true")


class TestTriageBoardStates(unittest.TestCase):
    """Never-polled, polled-and-empty, and stale (R14, R16)."""

    def setUp(self):
        self.never_polled = _render_board(None)
        empty_snapshot = _board_snapshot([])
        self.empty = _render_board(empty_snapshot)
        self.stale = _render_board({**empty_snapshot, "stale": True})

    def test_three_states_render_three_different_strings(self):
        # backlog_snapshot is None is "never polled" (or a non-local backend);
        # an empty item_order is a polled, itemless corpus; stale is data that
        # may be days old behind a last_updated stamp another loop rewrites
        # every 2s. Collapsing any two hides a real fact.
        renders = [self.never_polled, self.empty, self.stale]
        self.assertEqual(len(set(renders)), 3)

    def test_every_state_keeps_the_section_label(self):
        # R14: no state self-hides — every panel renders its shell and swaps
        # only inner content, and the morph swap replaces the shell's own
        # label on first load. The number is § 02 rather than § 11 since the
        # board became the Backlog view's second section instead of the
        # overnight page's eleventh; the register is per-view.
        for name, html in (
            ("never polled", self.never_polled),
            ("empty", self.empty),
            ("stale", self.stale),
        ):
            with self.subTest(state=name):
                self.assertIn("§ 02", html)
                self.assertIn("triage", html)

    def test_never_polled_renders_a_loading_state(self):
        self.assertIn("loading triage board", self.never_polled)
        self.assertNotIn("polled and empty", self.never_polled)

    def test_polled_and_empty_renders_an_empty_state(self):
        self.assertIn("corpus polled and empty", self.empty)
        self.assertNotIn("loading triage board", self.empty)

    def test_stale_renders_a_visible_indication(self):
        self.assertIn("stale", self.stale)
        self.assertNotIn("stale", self.empty)

    def test_fragment_carries_no_section_wrapper(self):
        # The polled section shell lives in base.html; a fragment that shipped
        # its own <section> would nest one inside the other on every morph.
        for html in (self.never_polled, self.empty, self.stale):
            self.assertEqual(_parse(html).find_all("section"), [])

    def test_doc_line_carries_the_refresh_cadence(self):
        # R16: the polled-panel doc-line convention — a .stream-line whose
        # trailing ml-auto span states the cadence, following backlog_panel's
        # 30s instance.
        stream_lines = _parse(self.empty).find_all("div", "stream-line")
        self.assertEqual(len(stream_lines), 1)
        self.assertIn("refresh · 30s", stream_lines[0].text)


class TestTriageBoardTemplateSource(unittest.TestCase):
    """Source-level guards that no render can express (R8, R16).

    Rendered output cannot show that a template *avoided* an idiom, so these
    two read the template file. Both mirror acceptance criteria phrased as
    greps over template source, which is the one place a grep is sound.
    """

    @classmethod
    def setUpClass(cls):
        cls.source = _BOARD_TEMPLATE.read_text(encoding="utf-8")

    def test_no_forbidden_design_patterns(self):
        # DESIGN.md's forbidden-patterns table: the panel uses design tokens
        # rather than raw hex, gray utility classes, or pixel styles.
        for label, pattern in (
            ("raw hex color", r"#[0-9a-fA-F]{3,6}\b"),
            ("gray utility class", r"(bg|text)-gray-"),
            ("inline pixel value", r'style="[^"]*[0-9]+px'),
        ):
            with self.subTest(pattern=label):
                self.assertEqual(re.findall(pattern, self.source), [])

    def test_no_count_threshold_selects_the_layout(self):
        # R8: grouping is presence-based. 45% of a sampled repo's active
        # non-epic items have no epic parent, so the flat list is a primary
        # view at scale rather than a small-set fallback — no length-versus-
        # literal comparison may choose between layouts. (len() is unbound in
        # Jinja, so the | length filter is the reachable idiom.)
        self.assertEqual(
            re.findall(r"\| *(?:length|count) *[<>]=? *[0-9]", self.source), []
        )


# ---------------------------------------------------------------------------
# Ticket page (templates/ticket_page.html, templates/ticket_artifact.html)
# ---------------------------------------------------------------------------
#
# Unlike the triage-board section above, these tests render against a
# hand-written dict rather than a real ``load_ticket_page`` call: the loader
# itself (the two-key artifact join, the epic-child corpus scan) is Task 5's
# composite-loader coverage in ``test_data.py``. What is tested here is the
# template's own contract — given the loader's documented shape, does the
# page render the right badges, the right panels, and the right gate.


def _ticket_page_fixture(**overrides) -> dict:
    """Return a minimal ``load_ticket_page()``-shaped dict for rendering tests."""
    base = {
        "id": "42",
        "title": "Sample ticket",
        "status": "open",
        "priority": "high",
        "type": "feature",
        "parent": None,
        "areas": [],
        "body": {
            "id": "42",
            "title": "Sample ticket",
            "html": "<p>Body prose.</p>",
            "truncated": False,
        },
        "artifacts": [],
        "children": None,
    }
    base.update(overrides)
    return base


class TestTicketPageBadgeStrip(unittest.TestCase):
    """The frontmatter badge strip uses backlog_badges.html's map, not the
    overnight feature-pipeline vocabulary (R7)."""

    def test_status_priority_type_render_as_badges(self):
        ticket = _ticket_page_fixture(status="wontfix", priority="critical", type="epic")
        html = _render_partial(
            "ticket_page.html", item_id="42", ticket=ticket, backend="cortex-backlog"
        )
        badge_texts = [b.text for b in _badges(_parse(html))]
        self.assertIn("wontfix", badge_texts)
        self.assertIn("critical", badge_texts)
        self.assertIn("epic", badge_texts)

    def test_parent_and_areas_render_when_present(self):
        ticket = _ticket_page_fixture(parent="7", areas=["dashboard", "backlog"])
        html = _render_partial(
            "ticket_page.html", item_id="42", ticket=ticket, backend="cortex-backlog"
        )
        self.assertIn("#7", html)
        self.assertIn("dashboard", html)
        self.assertIn("backlog", html)

    def test_parent_and_areas_absent_when_unset(self):
        ticket = _ticket_page_fixture()
        html = _render_partial(
            "ticket_page.html", item_id="42", ticket=ticket, backend="cortex-backlog"
        )
        self.assertNotIn("parent ·", html)
        self.assertNotIn("areas ·", html)


class TestTicketPageArtifactPanels(unittest.TestCase):
    """One lazily-fetched <details> panel per present artifact kind (R9, R10)."""

    def test_one_details_panel_per_present_kind(self):
        ticket = _ticket_page_fixture(artifacts=["spec", "plan"])
        html = _render_partial(
            "ticket_page.html", item_id="42", ticket=ticket, backend="cortex-backlog"
        )
        panels = {
            d.attrs.get("id"): d
            for d in _parse(html).find_all("details", "ticket-artifact")
        }
        self.assertEqual(set(panels), {"spec", "plan"})
        for kind, panel in panels.items():
            with self.subTest(kind=kind):
                fetchers = [e for e in panel.find_all() if "hx-get" in e.attrs]
                self.assertEqual(len(fetchers), 1)
                self.assertEqual(
                    fetchers[0].attrs["hx-get"], f"/partials/ticket/42/artifact/{kind}"
                )
                self.assertEqual(
                    fetchers[0].attrs.get("hx-trigger"), "toggle once from:closest details"
                )

    def test_absent_kinds_render_no_panel(self):
        ticket = _ticket_page_fixture(artifacts=["spec"])
        html = _render_partial(
            "ticket_page.html", item_id="42", ticket=ticket, backend="cortex-backlog"
        )
        self.assertNotIn('id="plan"', html)
        self.assertNotIn('id="research"', html)
        self.assertNotIn('id="review"', html)

    def test_no_artifacts_renders_no_artifacts_section(self):
        ticket = _ticket_page_fixture(artifacts=[])
        html = _render_partial(
            "ticket_page.html", item_id="42", ticket=ticket, backend="cortex-backlog"
        )
        self.assertNotIn("ticket-artifact", html)

    def test_page_renders_no_artifact_prose_before_expansion(self):
        # R10: opening the page issues no artifact render. The body's own
        # "prose ticket-prose" block is the sole one on the page; each
        # artifact panel holds a loading placeholder, never the fetched
        # fragment ticket_artifact.html itself would render.
        ticket = _ticket_page_fixture(artifacts=["spec", "plan"])
        html = _render_partial(
            "ticket_page.html", item_id="42", ticket=ticket, backend="cortex-backlog"
        )
        prose_blocks = _parse(html).find_all("div", "ticket-prose")
        self.assertEqual(len(prose_blocks), 1)
        self.assertIn("loading spec", html)
        self.assertIn("loading plan", html)


class TestTicketPageEpicChildren(unittest.TestCase):
    """Epic children render as links to their own /tickets/{id} pages (R14)."""

    def test_children_render_as_links(self):
        ticket = _ticket_page_fixture(
            type="epic",
            children=[
                {"id": 5, "spec": None, "status": "open", "title": "Child A"},
                {"id": 9, "spec": None, "status": "backlog", "title": None},
            ],
        )
        html = _render_partial(
            "ticket_page.html", item_id="42", ticket=ticket, backend="cortex-backlog"
        )
        self.assertIn('href="/tickets/5"', html)
        self.assertIn('href="/tickets/9"', html)
        self.assertIn("Child A", html)

    def test_non_epic_has_no_children_section(self):
        ticket = _ticket_page_fixture(type="feature", children=None)
        html = _render_partial(
            "ticket_page.html", item_id="42", ticket=ticket, backend="cortex-backlog"
        )
        self.assertNotIn("Epic", html)
        self.assertNotIn("§ 03", html)

    def test_epic_with_no_active_children_renders_empty_state(self):
        ticket = _ticket_page_fixture(type="epic", children=[])
        html = _render_partial(
            "ticket_page.html", item_id="42", ticket=ticket, backend="cortex-backlog"
        )
        self.assertIn("no active children", html)


class TestTicketPageBackendGate(unittest.TestCase):
    """ticket_page.html renders a backend-aware 3-way — gated / not-found /
    found (R5, R13), in the style of TestBacklogPanelBackendGate."""

    def test_none_backend_renders_placeholder(self):
        html = _render_partial("ticket_page.html", item_id="1", ticket=None, backend="none")
        self.assertIn("backlog tracking disabled", html)
        self.assertNotIn("ticket not found", html)

    def test_external_backend_names_the_backend(self):
        html = _render_partial(
            "ticket_page.html", item_id="1", ticket=None, backend="github-issues"
        )
        self.assertIn("tracked externally via", html)
        self.assertIn("github-issues", html)
        self.assertNotIn("ticket not found", html)

    def test_missing_ticket_under_local_backend_renders_not_found(self):
        html = _render_partial(
            "ticket_page.html", item_id="999999", ticket=None, backend="cortex-backlog"
        )
        self.assertIn("ticket not found", html)
        self.assertNotIn("tracking disabled", html)
        self.assertNotIn("tracked externally", html)


class TestTicketArtifactBackendGate(unittest.TestCase):
    """ticket_artifact.html's single `artifact is None` arm covers a
    non-local backend the same way ticket_body.html's `ticket is None` arm
    does (R13) — see the template's own docstring for why the cases collapse."""

    def test_artifact_none_renders_unavailable(self):
        html = _render_partial("ticket_artifact.html", artifact=None)
        self.assertIn("artifact unavailable", html)

    def test_artifact_present_renders_prose(self):
        artifact = {"kind": "spec", "html": "<p>Spec prose.</p>", "truncated": False}
        html = _render_partial("ticket_artifact.html", artifact=artifact)
        self.assertIn("Spec prose.", html)
        self.assertIn("ticket-prose", html)

    def test_artifact_truncated_shows_the_notice(self):
        artifact = {"kind": "spec", "html": "<p>Spec prose.</p>", "truncated": True}
        html = _render_partial("ticket_artifact.html", artifact=artifact)
        self.assertIn("truncated", html)


if __name__ == "__main__":
    unittest.main()
