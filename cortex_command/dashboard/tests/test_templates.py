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
  - ticket_page.html badge strip, epic children, and per-artifact panels
  - ticket_page.html / ticket_artifact.html non-local-backend gate

The triage board this file used to cover has been retired. Its surface — the
whole active slice, rendered read-only — is now the backlog navigator's § 03,
and its tests moved with it to ``test_navigator_render.py``, which keeps the
build-the-corpus-on-disk discipline the board's tests established: the risk is
in the joins between snapshot collections, and a snapshot transcribed by hand
would assert only that the transcription matches itself.
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


class TestMorphSwapIsWiredCorrectly(unittest.TestCase):
    """The two defects that made ``hx-swap="morph"`` a lie for its whole life.

    Both were invisible together and only became visible when the first was
    fixed, which is why they are pinned together.

    1. The extension was loaded from ``htmx-ext-idiomorph``, a package that has
       never existed on npm (the real one is ``idiomorph``). The URL 404'd, so
       ``window.Idiomorph`` was undefined, htmx found no extension claiming
       "morph", and every panel silently fell through to ``defaultSwapStyle``,
       which is innerHTML.

    2. With the extension actually loaded, a bare ``morph`` is *outerHTML*
       morphing: it matches the incoming content against the polled element
       itself. Every partial here returns inner content rather than a root
       matching its host, so idiomorph replaced each host outright — taking
       ``hx-get`` and ``hx-trigger`` with it. The dashboard rendered once and
       then never polled again.

    Both assertions are about a machine token whose absence fails silently:
    nothing errors, nothing logs, and the page looks right until you wait.
    """

    def test_the_morph_extension_is_not_the_package_that_does_not_exist(self):
        html = _render(DashboardState())
        self.assertNotIn("htmx-ext-idiomorph", html)

    def test_the_morph_extension_is_actually_loaded(self):
        html = _render(DashboardState())
        self.assertIn("idiomorph", html)

    def test_no_polled_element_uses_bare_outerhtml_morph(self):
        """A bare ``morph`` destroys the element carrying the poll attributes."""
        for template in ("base.html", "backlog.html"):
            with self.subTest(template=template):
                source = (
                    Path(__file__).resolve().parents[1] / "templates" / template
                ).read_text()
                self.assertNotIn('hx-swap="morph"', source)

    def test_the_polled_elements_still_declare_a_morph_swap(self):
        """Non-vacuity guard for the assertion above.

        Without this, deleting every ``hx-swap`` on the dashboard would make
        the absence test pass while turning off morphing entirely.
        """
        source = (
            Path(__file__).resolve().parents[1] / "templates" / "base.html"
        ).read_text()
        self.assertGreater(source.count('hx-swap="morph:innerHTML"'), 5)


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
# Fragment parsing helpers
# ---------------------------------------------------------------------------
#
# A rendered partial is parsed into an element tree rather than grepped.
# ``grep -c`` counts matching *lines*, so a substring assertion over rendered
# HTML is sensitive to where the template happens to break lines, while "this
# panel shows its prose" is a statement about one element's content and not
# about the document. Assertions therefore run over parsed elements or over
# template source, never over the rendered string as if it were a file.

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



def _badges(element: _Element) -> list:
    """Return every badge span inside *element*."""
    return element.find_all("span", "badge")



# ---------------------------------------------------------------------------
# Ticket page (templates/ticket_page.html, templates/ticket_artifact.html)
# ---------------------------------------------------------------------------
#
# Unlike the navigator's render tests, these render against a
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


class TestTicketPageSectionRegister(unittest.TestCase):
    """The § register counts the sections that rendered.

    Children and artifacts are both conditional, and a non-epic ticket has no
    children section at all — the ordinary case. Against fixed ordinals that
    page printed § 01 · § 02 · § 04, and a hole in a numbered register reads
    as a section that failed to draw.
    """

    @staticmethod
    def _ordinals(html: str) -> list[int]:
        return [int(n) for n in re.findall(r"§\s*0*(\d+)</strong>", html)]

    def _render(self, **overrides) -> str:
        return _render_partial(
            "ticket_page.html", item_id="42",
            ticket=_ticket_page_fixture(**overrides), backend="cortex-backlog",
        )

    def test_a_non_epic_ticket_with_artifacts_has_no_gap(self):
        html = self._render(artifacts=["spec"], children=None)
        self.assertEqual([1, 2, 3], self._ordinals(html))

    def test_an_epic_with_artifacts_numbers_all_four(self):
        # The complement: a counter must not satisfy the above by collapsing.
        html = self._render(
            type="epic", artifacts=["spec", "plan"],
            children=[{"id": 5, "spec": None, "status": "open", "title": "Child"}],
        )
        self.assertEqual([1, 2, 3, 4], self._ordinals(html))

    def test_a_bare_ticket_numbers_the_two_it_draws(self):
        self.assertEqual([1, 2], self._ordinals(self._render()))


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
        # Scoped to <main>, not to the whole document. The page extends
        # base.html, whose masthead nav links out to the peer views by name —
        # so a bare substring search for "Epic" over the rendered document
        # matches the navigation and asserts nothing about this page's body.
        body = _parse(html).find_all("main")[0]
        self.assertNotIn("Epic", body.text)
        self.assertNotIn("§ 03", body.text)

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


class TestStylesheetReachesTheMarkup(unittest.TestCase):
    """No rule in base.html is scoped to a class no template renders.

    Two defects share this shape and neither is visible from any render
    assertion, because both fail silently — the wrong-scoped rule simply never
    matches, and the page looks *plausible* without it:

      - Rules for a panel that has since been retired sit in the sheet
        forever. ``DESIGN.md`` tells the next author to reuse an existing
        pattern before writing new CSS, so a dead ``.ticket-row`` family is
        not merely weight; it is a trap that reads as precedent.
      - A live class styled only under a dead ancestor. Every
        ``.ticket-prose`` table rule was written as ``.ticket-desc
        .ticket-prose table``; ``.ticket-desc`` belonged to the retired board,
        so every markdown table on the ticket page and in the four artifact
        panels rendered at the browser default against the dark ground.

    The check is on the LEFTMOST class of each selector branch — the one that
    has to exist in the DOM for anything to the right of it to matter.
    """

    # Classes composed at render time as `prefix{{ value }}`, which no literal
    # scan of the templates can see. Every entry corresponds to a real
    # `class="…{{ … }}"` site; kept as an explicit list so a newly-dead family
    # cannot hide behind a broad pattern.
    #
    #   grep -rno 'class="[^"]*{{[^"]*"' cortex_command/dashboard/templates/
    #
    # is what regenerates it when a new interpolated class ships.
    DYNAMIC_PREFIXES = (
        "alert-badge-", "badge-", "edge--", "egroup--", "ekid--",
        "feature-row--", "lane-status-", "nav-list__row--", "node--",
    )

    @classmethod
    def setUpClass(cls) -> None:
        base = Path(__file__).resolve().parents[1] / "templates" / "base.html"
        text = base.read_text(encoding="utf-8")
        cls.sheet = text[text.find("<style"):text.find("</style>")]
        cls.rendered = set()
        for path in (base.parent).rglob("*.html"):
            body = path.read_text(encoding="utf-8")
            if path.name == "base.html":
                # base.html's own stylesheet is the thing under test; only the
                # markup and script below <body> count as usage.
                body = body[text.find("<body"):]
            for attr in re.findall(r'class="([^"]*)"', body):
                cls.rendered.update(
                    token for token in re.split(r"[\s{}%|'\"()]+", attr) if token
                )
            # Class names assembled in the delegated handlers in base.html.
            cls.rendered.update(re.findall(r"classList\.\w+\(['\"]([\w-]+)", body))
        # Class names the Python side hands to a template as a value rather
        # than writing into markup — ``app._BADGE_CLASS_MAP`` is the live case.
        for module in (base.parents[1]).rglob("*.py"):
            cls.rendered.update(
                re.findall(r"""["']([a-z][\w-]*-[\w-]+)["']""", module.read_text(encoding="utf-8"))
            )

    def _leftmost_classes(self) -> list[tuple[str, str]]:
        """(selector, leftmost class) for every rule in the sheet."""
        out = []
        for match in re.finditer(r"(?m)^\s*([^\n{}]*?)\s*\{", self.sheet):
            selector = match.group(1).strip()
            if not selector or selector.startswith("@") or selector.startswith("/*"):
                continue
            for branch in selector.split(","):
                first = re.search(r"\.([A-Za-z][\w-]*)", branch)
                if first:
                    out.append((selector, first.group(1)))
        return out

    def test_the_scan_found_the_stylesheet(self):
        # Guard: every assertion below passes vacuously against an empty sheet.
        self.assertGreater(len(self._leftmost_classes()), 200)
        self.assertIn("ticket-prose", {c for _, c in self._leftmost_classes()})

    def test_every_rule_is_reachable_from_some_template(self):
        orphans = sorted({
            "%s  (.%s)" % (selector, cls)
            for selector, cls in self._leftmost_classes()
            if cls not in self.rendered
            and not cls.startswith(self.DYNAMIC_PREFIXES)
        })
        self.assertEqual(
            [], orphans,
            "stylesheet rules scoped to classes no template renders — delete "
            "them, or re-scope them onto the class the markup carries:\n  "
            + "\n  ".join(orphans),
        )


if __name__ == "__main__":
    unittest.main()
