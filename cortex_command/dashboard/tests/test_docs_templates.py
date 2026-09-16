"""Direct-Jinja tests for the Docs view templates.

Renders ``doc_page.html``, ``docs_index.html``, ``doc_cited_by.html`` and the
map fragment through ``templates.env.get_template`` with a corpus and a
layout built by hand — no disk, no route — and asserts each arm draws what
the route contract says it draws: the not-found arm, the edit arm with the
operator's text and the hash preserved, the superseded banner naming the
successor, and a map node carrying the attributes the hover card reads.

The route-level counterpart (status codes, the real TemplateResponse path,
the POST verb) is in ``test_routes_smoke.py``.
"""

from __future__ import annotations

import types
from pathlib import Path

from cortex_command.dashboard.app import templates
from cortex_command.dashboard.docs.corpus import Backlinks, LifecycleRef, TicketRef
from cortex_command.dashboard.docs.edit import EditView, SaveResult
from cortex_command.dashboard.docs.model import (
    MAP_NH,
    MAP_NW,
    Corpus,
    DocEdge,
    DocNode,
    MapEdge,
    MapLabel,
    MapLayout,
    MapNode,
)
from cortex_command.dashboard.docs.render import Rendered, TocEntry


def _request(path: str = "/docs") -> types.SimpleNamespace:
    return types.SimpleNamespace(url=types.SimpleNamespace(path=path))


def _main(html: str) -> str:
    """The page body only. base.html's stylesheet and script name every docs
    class and several register numbers, so an absence assertion against the
    whole page would match the CSS rather than the section it is about."""
    start = html.index("<main")
    end = html.index("</main>")
    return html[start:end]


def _corpus() -> Corpus:
    nodes = {
        "CLAUDE.md": DocNode(path="CLAUDE.md", kind="constitution", title="Project instructions", governing=True),
        "cortex/requirements/project.md": DocNode(
            path="cortex/requirements/project.md", kind="root", title="Project requirements",
            governing=True, last_gathered="2026-07-16",
        ),
        "cortex/adr/0006-old.md": DocNode(
            path="cortex/adr/0006-old.md", kind="adr", title="The old decision", governing=True,
            adr_number=6, status="superseded", superseded_by="cortex/adr/0008-new.md",
        ),
        "cortex/adr/0008-new.md": DocNode(
            path="cortex/adr/0008-new.md", kind="adr", title="The new decision", governing=True,
            adr_number=8, status="accepted", decision_date="2026-05-01", origin_ticket="#42",
        ),
    }
    edges = [
        DocEdge(src="CLAUDE.md", dst="cortex/requirements/project.md", kind="cites"),
        DocEdge(src="cortex/adr/0008-new.md", dst="cortex/adr/0006-old.md", kind="supersedes"),
        DocEdge(src="cortex/requirements/project.md", dst="cortex/adr/0008-new.md", kind="cites", count=3),
        DocEdge(src="CLAUDE.md", dst="cortex/adr/0008-new.md", kind="cites"),
    ]
    return Corpus(root=Path("/nowhere"), nodes=nodes, edges=edges)


def _layout(*, empty: bool = False) -> MapLayout:
    if empty:
        return MapLayout(width=0, height=0, verdict="1 doc · nothing to draw", empty=True)
    return MapLayout(
        width=600, height=200,
        nodes=[
            MapNode(
                path="CLAUDE.md", x=10, y=40, short="CLAUDE.md", title="Project instructions",
                kind="constitution", status=None, state="constitution", href="/docs/CLAUDE.md",
                focus="here", in_count=0, out_count=1,
            ),
            MapNode(
                path="cortex/adr/0006-old.md", x=300, y=40, short="ADR-0006", title="The old decision",
                kind="adr", status="superseded", state="superseded", href="/docs/cortex/adr/0006-old.md",
                focus="far", in_count=1, out_count=0,
            ),
        ],
        edges=[MapEdge(src="CLAUDE.md", dst="cortex/adr/0006-old.md", kind="cites", d="M 230 68 H 300", focus="out")],
        labels=[
            MapLabel(x=10, y=20, text="CONSTITUTION", role="column"),
            MapLabel(x=300, y=120, text="+3 more", role="more", href="?expand=CLAUDE.md"),
        ],
        marker_id="arw-docs-test",
        verdict="2 docs · 1 edge",
        drawn=2, total=4,
    )


def _page(doc_path: str | None, **overrides) -> str:
    corpus = _corpus()
    doc = corpus.get(doc_path) if doc_path else None
    ctx = {
        "request": _request(f"/docs/{doc_path or 'nope.md'}"),
        "repo_query": "",
        "doc": doc,
        "path": doc_path or "nope.md",
        "corpus": corpus,
        "rendered": Rendered(
            html='<h2 id="decision">Decision</h2><p>Body prose.</p>',
            toc=[TocEntry(level=2, id="decision", text="Decision")],
        ),
        "strip": _layout(empty=True),
        "words": 12,
        "hover_data": {},
        "edit": False,
        "edit_view": None,
        "conflict": None,
        "save_error": None,
    }
    ctx.update(overrides)
    return templates.env.get_template("doc_page.html").render(**ctx)


# ---------------------------------------------------------------------------
# doc_page.html
# ---------------------------------------------------------------------------


def test_not_found_arm_names_the_path_and_links_back():
    html = _main(_page(None))

    assert "Document not found" in html
    assert "nope.md" in html
    assert 'href="/docs"' in html
    # The register mark is the dash, not a number: nothing rendered to count.
    assert "§ —" in html
    assert "§ 01" not in html


def test_read_arm_renders_body_toc_and_header_facts():
    html = _page("cortex/adr/0008-new.md")

    assert "The new decision" in html
    assert '<h2 id="decision">Decision</h2>' in html
    assert 'href="#decision"' in html
    # ADR status → the badge picked by rendered result (accepted paints blue).
    assert "badge-green" in html
    assert "decided · 2026-05-01" in html
    assert 'href="/tickets/42"' in html
    assert "12 words" in html
    # Read mode offers the edit link and the cited-by panel's lazy fetch.
    assert "?edit=1" in html
    assert 'hx-get="/partials/docs/cited-by/cortex/adr/0008-new.md"' in html
    assert 'hx-trigger="toggle once from:closest details"' in html


def test_read_arm_omits_the_map_section_for_an_empty_strip():
    html = _main(_page("CLAUDE.md", strip=_layout(empty=True)))

    assert "Neighbourhood" not in html
    # Sections still count contiguously: document, body, cited by.
    assert "§ 01" in html and "§ 02" in html and "§ 03" in html
    assert "§ 04" not in html


def test_read_arm_draws_the_strip_when_it_has_nodes():
    html = _page("CLAUDE.md", strip=_layout())

    assert "Neighbourhood" in html
    assert 'id="docmap-wrap"' in html
    assert "<svg" in html


def test_superseded_banner_names_the_successor():
    html = _page("cortex/adr/0006-old.md")

    assert "doc-banner--superseded" in html
    assert 'href="/docs/cortex/adr/0008-new.md"' in html
    assert "ADR-0008" in html
    assert "(accepted)" in html
    # The successor also rides inline in the index row; here it is the
    # banner, and the badge is the faint one.
    assert "badge-gray" in html


def test_accepted_doc_has_no_banner():
    html = _main(_page("cortex/adr/0008-new.md"))

    assert "doc-banner--superseded" not in html
    assert "doc-banner--deprecated" not in html


def test_edit_arm_replaces_the_body_with_the_form():
    view = EditView(path="CLAUDE.md", text="# Hello\n\nbody text\n", sha="abc123def456789")
    html = _main(_page("CLAUDE.md", edit=True, edit_view=view, rendered=None))

    assert 'action="/docs/CLAUDE.md"' in html
    assert 'name="sha" value="abc123def456789"' in html
    assert "body text" in html
    assert 'name="content"' in html
    # The body section is gone; the edit section took its slot.
    assert "doc-prose" not in html
    assert ">Body<" not in html
    assert "Edit" in html
    # No edit link on the page that is already the editor.
    assert "?edit=1" not in html


def test_conflict_arm_keeps_the_operators_text_and_shows_disk():
    view = EditView(path="CLAUDE.md", text="MY EDIT\n", sha="freshsha")
    result = SaveResult(ok=False, reason="conflict", sha="freshsha", disk_text="DISK VERSION\n")
    html = _page("CLAUDE.md", edit=True, edit_view=view, rendered=None, conflict=result)

    assert "doc-banner--conflict" in html
    assert "MY EDIT" in html
    assert "DISK VERSION" in html
    assert 'name="sha" value="freshsha"' in html


def test_refused_arm_shows_the_reason():
    view = EditView(path="CLAUDE.md", text="x\n", sha="s")
    html = _page("CLAUDE.md", edit=True, edit_view=view, rendered=None, save_error="save refused · symlink")

    assert "doc-banner--refused" in html
    assert "save refused · symlink" in html


def test_repo_query_travels_on_every_link():
    html = _page("cortex/adr/0006-old.md", repo_query="?repo=alpha")

    assert 'href="/docs/cortex/adr/0008-new.md?repo=alpha"' in html
    assert 'hx-get="/partials/docs/cited-by/cortex/adr/0006-old.md?repo=alpha"' in html
    # The edit link joins with & (autoescaped) because ?edit=1 already opened the query.
    assert "?edit=1&amp;repo=alpha" in html
    assert 'href="/docs?repo=alpha"' in html


def test_masthead_reads_the_docs_register():
    html = _page("CLAUDE.md")

    assert "governing docs · read + edit" in html
    assert "cortex <em>docs</em>" in html
    assert 'href="/docs" class="nav-link nav-link-active"' in html


# ---------------------------------------------------------------------------
# _doc_map.svg.html
# ---------------------------------------------------------------------------


def test_map_nodes_carry_hover_attributes_and_classes():
    html = templates.env.get_template("_doc_map.svg.html").render(layout=_layout(), repo_query="")

    assert 'viewBox="0 0 600 200"' in html
    assert f'width="{MAP_NW}" height="{MAP_NH}"' in html
    assert 'class="dn dn--constitution dn--here js-doc"' in html
    assert 'class="dn dn--adr dn--superseded dn--far js-doc"' in html
    assert 'data-doc="cortex/adr/0006-old.md"' in html
    assert 'data-d-short="ADR-0006"' in html
    assert 'data-d-status="superseded"' in html
    assert 'data-d-in="1"' in html and 'data-d-out="0"' in html
    assert 'class="dedge dedge--cites dedge--out"' in html
    assert 'marker-end="url(#arw-docs-test-ochre)"' in html
    assert 'class="dlabel dlabel--column"' in html
    assert "2 docs · 1 edge" in html


def test_map_more_label_is_a_link_that_swaps_the_wrapper():
    html = templates.env.get_template("_doc_map.svg.html").render(layout=_layout(), repo_query="?repo=alpha")

    assert 'href="?expand=CLAUDE.md&amp;repo=alpha"' in html
    # The fragment URL rides as data for the delegated handler, not as an
    # hx-get: htmx never cancels an SVG anchor's navigation.
    assert 'class="js-map-more"' in html
    assert 'data-map-get="/partials/docs/map?expand=CLAUDE.md&amp;repo=alpha"' in html
    assert "hx-get" not in html
    assert 'href="/docs/CLAUDE.md?repo=alpha"' in html


def test_empty_map_prints_the_verdict_and_no_svg():
    html = templates.env.get_template("_doc_map.svg.html").render(layout=_layout(empty=True), repo_query="")

    assert "nothing to draw" in html
    assert "<svg" not in html


def test_importing_the_macro_file_does_not_draw():
    """The fragment arm is inert on import: a page that imports the macros
    without a ``layout`` in context gets no stray svg from the module body."""
    html = templates.env.get_template("_doc_map.svg.html").render(repo_query="")

    assert "<svg" not in html
    assert "epic-verdict" not in html


# ---------------------------------------------------------------------------
# docs_index.html
# ---------------------------------------------------------------------------


def test_index_groups_rows_and_marks_the_successor():
    corpus = _corpus()
    groups = [
        ("instructions", [corpus.get("CLAUDE.md")]),
        ("requirements", [corpus.get("cortex/requirements/project.md")]),
        ("decisions", [corpus.get("cortex/adr/0006-old.md"), corpus.get("cortex/adr/0008-new.md")]),
    ]
    html = templates.env.get_template("docs_index.html").render(
        request=_request("/docs"), repo_query="", corpus=corpus, groups=groups, ladder=_layout(),
    )

    assert "instructions" in html and "decisions" in html
    assert 'data-doc-id="ADR-0006"' in html
    assert 'data-doc-status="superseded"' in html
    assert 'href="/docs/cortex/adr/0008-new.md">ADR-0008</a>' in html
    # Counts citing edges, not folded mentions: project.md has one citer,
    # ADR-0008 has two (project.md with count=3 is still one edge).
    assert "cited by 1" in html
    assert "cited by 2" in html
    assert "cited by 3" not in html
    assert "2026-07-16" in html
    # The filter ships hidden until JS shows it; the map wrapper is present.
    assert 'id="docs-filter" hidden' in html
    assert 'id="docmap-wrap"' in html
    assert "4 docs" in html


# ---------------------------------------------------------------------------
# doc_cited_by.html
# ---------------------------------------------------------------------------


def test_cited_by_renders_three_groups_with_links():
    corpus = _corpus()
    links = Backlinks(
        docs=[(corpus.get("CLAUDE.md"), "Conventions", 2)],
        tickets=[TicketRef(id="42", title="Do the thing", status="complete", path="cortex/backlog/42-x.md")],
        lifecycles=[
            LifecycleRef(slug="do-the-thing", kinds=("spec", "plan"), ticket_id="42"),
            LifecycleRef(slug="orphan", kinds=("research",), ticket_id=None),
        ],
    )
    html = templates.env.get_template("doc_cited_by.html").render(
        request=_request(), repo_query="", doc=corpus.get("cortex/requirements/project.md"), backlinks=links,
    )

    assert 'href="/docs/CLAUDE.md"' in html
    assert "§ Conventions" in html and "2×" in html
    assert 'href="/tickets/42"' in html and "Do the thing" in html
    assert 'href="/tickets/42#spec"' in html and "spec · plan" in html
    assert "orphan" in html
    assert 'href="/tickets/None' not in html


def test_cited_by_unavailable_arm():
    html = templates.env.get_template("doc_cited_by.html").render(
        request=_request(), repo_query="", doc=None, backlinks=None,
    )

    assert "citations unavailable" in html
