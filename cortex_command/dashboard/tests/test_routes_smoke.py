"""Route-level smoke test exercising the real ``TemplateResponse`` render path.

The sibling ``test_templates.py`` renders Jinja directly via
``templates.env.get_template(...).render(...)``, which bypasses Starlette's
``TemplateResponse``. That direct-Jinja path CANNOT catch the name-first vs.
request-first ``TemplateResponse`` signature break: on Starlette >= 1.0 the
removed positional ``TemplateResponse(name, context)`` form binds the context
dict into the ``name`` slot, which reaches Jinja's hashable cache key and
raises ``TypeError: unhashable type: 'dict'`` -> HTTP 500. Only a route test
that drives each handler through the real ASGI app + ``TemplateResponse`` layer
can guard against that regression.

This test drives ``GET /``, ``/sessions``, ``/health``,
``/tickets/{id}``, and each of the ``/partials/*`` routes and asserts 200, plus
``GET /sessions/{missing}`` -> 404 and ``GET /tickets/{missing}`` -> 404 (the
``status_code`` path). On the dev venv (Starlette 0.52.1) both call forms
return 200, so locally this proves only well-formedness; it becomes
discriminating on a fresh Starlette >= 1.0 resolve (the CI step), where the
pre-rewrite name-first form 500s.

Lifespan management: the fixture builds a tmp project root and drives the app
via a ``TestClient`` WITHOUT entering the lifespan, so the four ``while True``
background poller tasks (``run_polling``) and the PID file are never created --
the most deterministic way to guarantee the suite neither hangs nor leaks. The
real ASGI handlers and ``TemplateResponse`` render path are exercised regardless
of whether the lifespan ran; the lifespan only starts background polling, which
is orthogonal to render correctness. (Entering the lifespan was rejected for
this test: ``app.py`` captures the PID-file path in a module-level singleton at
import time, so a per-test ``XDG_CACHE_HOME`` cannot redirect the lifespan's
PID write, leaving no clean way to isolate it without monkeypatching internals.)
"""

from __future__ import annotations

import json
import re

import pytest
from starlette.testclient import TestClient

from cortex_command.dashboard.app import app

# The HTMX partial routes, in the order documented by the spec.
PARTIAL_ROUTES = [
    "/partials/fleet-panel",
    "/partials/alerts-banner",
    "/partials/session-panel",
    "/partials/feature-cards",
    "/partials/round-history",
    "/partials/escalations",
    "/partials/activity-stream",
    "/partials/metrics",
    "/partials/swim-lane",
    # The two navigator surfaces. Both rebuild a graph, a ranking and a band
    # partition per request, and both must render their empty arm against a
    # fixture root whose poller never ran — the snapshot is None there, which
    # is the same state a non-local backlog backend leaves behind.
    "/partials/navigator",
    # Path-parameterised. Renders its "description unavailable" arm against the
    # fixture root, which has no cortex/backlog/ — a missing ticket is a normal
    # render, not a status code, because the fragment lands inside a row the
    # operator merely expanded.
    "/partials/ticket/1",
    # The artifact partial is always 200 regardless of whether the artifact
    # resolves — see ticket_artifact_partial's docstring. Ticket 1 and its
    # spec.md are seeded by fixture_root below.
    "/partials/ticket/1/artifact/spec",
    # The modal card the board and the epic maps open. Always 200 for the same
    # reason the body partial is: the fragment lands inside a <dialog> the
    # operator has already opened, so a status code there would only give htmx
    # a reason to leave it empty. Listed here because this route was once
    # deleted for having no caller anywhere — "not in a template, not in a
    # test, not in the route smoke list" — and the smoke list is the cheapest
    # of those three to keep honest.
    "/partials/ticket-card/1",
    # The Docs view's two fragments. The cited-by panel is always 200 for the
    # same reason the artifact partial is — it lands inside a <details> the
    # operator opened. The map fragment is what a shelf's `more` link swaps
    # in; against the fixture root it draws the two-node ladder CLAUDE.md
    # and project.md make.
    "/partials/docs/cited-by/CLAUDE.md",
    "/partials/docs/map",
]

# Page + health routes that must render 200. These are full pages — peers, not
# fragments — so they go through the same TemplateResponse path this module
# exists to guard. ``/`` and ``/backlog`` both serve the navigator (the backlog
# is the landing page, and the older path is kept for existing links and
# bookmarks), so both are listed: a regression that broke only the alias would
# otherwise render every in-page "back to backlog" link a 404. ``/overnight``
# is the session view that used to sit at ``/``. ``/tickets/1`` is the seeded
# ticket from fixture_root below.
PAGE_ROUTES = [
    "/", "/backlog", "/overnight", "/sessions", "/health", "/tickets/1",
    # The Docs view: the index and the reader for the CLAUDE.md fixture_root
    # seeds. A path segment with a slash in it (`/docs/{path:path}`) is the
    # one shape no other page route has, so the reader is listed by name.
    "/docs", "/docs/CLAUDE.md", "/docs/cortex/requirements/project.md",
]

ALL_OK_ROUTES = PAGE_ROUTES + PARTIAL_ROUTES


@pytest.fixture
def fixture_root(tmp_path, monkeypatch):
    """Build a tmp cortex project root and point ``CORTEX_REPO_ROOT`` at it.

    Creates ``.claude/`` (required by the lifespan's ``RuntimeError`` guard at
    ``app.py``; ``_resolve_user_project_root`` returns ``CORTEX_REPO_ROOT``
    verbatim and does not itself require ``.claude/``) and an empty
    ``cortex/lifecycle/`` so the dashboard data parsers resolve cleanly.

    Also seeds one backlog ticket (id 1) with a resolvable ``spec.md`` under
    ``cortex/lifecycle/`` — ``PAGE_ROUTES``/``PARTIAL_ROUTES`` above hardcode
    ``/tickets/1`` and its artifact partial, so this ticket must exist for
    every test that drives ``client`` through this fixture.
    """
    (tmp_path / ".claude").mkdir()
    (tmp_path / "cortex" / "lifecycle").mkdir(parents=True)
    (tmp_path / "cortex" / "backlog").mkdir(parents=True)
    (tmp_path / "cortex" / "backlog" / "1-smoke-test-ticket.md").write_text(
        "---\n"
        "title: Smoke test ticket\n"
        "status: open\n"
        "priority: medium\n"
        "type: feature\n"
        "lifecycle_slug: smoke-test-ticket\n"
        "---\n\n"
        "Ticket body used by the route smoke suite.\n",
        encoding="utf-8",
    )
    lifecycle_feature_dir = tmp_path / "cortex" / "lifecycle" / "smoke-test-ticket"
    lifecycle_feature_dir.mkdir()
    (lifecycle_feature_dir / "spec.md").write_text(
        "# Spec\n\nSpec artifact prose used by the route smoke suite.\n",
        encoding="utf-8",
    )
    # The smallest governing set the Docs view can map: the constitution and
    # the root requirements doc, with one citation between them so the
    # ladder has an edge to draw. `/docs/CLAUDE.md` and the edit-verb tests
    # below hardcode these two paths.
    (tmp_path / "CLAUDE.md").write_text(
        "# Smoke project\n\nRead `cortex/requirements/project.md` first.\n",
        encoding="utf-8",
    )
    (tmp_path / "cortex" / "requirements").mkdir(parents=True)
    (tmp_path / "cortex" / "requirements" / "project.md").write_text(
        "# Project\n\n> Last gathered: 2026-01-01\n\n## Vision\n\nA tiny root doc.\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CORTEX_REPO_ROOT", str(tmp_path))
    return tmp_path


@pytest.fixture
def client(fixture_root):
    """A ``TestClient`` that does NOT enter the lifespan.

    Driving the app without the lifespan context manager exercises the real
    ASGI handlers and ``TemplateResponse`` render path while creating no
    background poller tasks and no PID file -- so the suite cannot hang or leak.
    """
    return TestClient(app)


@pytest.mark.parametrize("route", ALL_OK_ROUTES)
def test_route_renders_200(client, route):
    """Every page, health, and partial route returns 200 via the real render path."""
    response = client.get(route)
    assert response.status_code == 200, (
        f"{route} returned {response.status_code}, expected 200"
    )


def test_missing_session_returns_404(client):
    """``GET /sessions/{missing-id}`` returns 404 (the status_code path, not 500)."""
    response = client.get("/sessions/this-session-id-does-not-exist")
    assert response.status_code == 404


def test_missing_ticket_returns_404(client):
    """``GET /tickets/{unseeded-numeric-id}`` returns 404, not 500."""
    response = client.get("/tickets/999999")
    assert response.status_code == 404


def test_a_non_utf8_ticket_file_does_not_500(fixture_root):
    """A stray byte in one item is a legibility problem, not a 500.

    Every text read in ``data.py`` sat under ``except OSError``, and
    ``UnicodeDecodeError`` is a ``ValueError`` — so one file under
    ``cortex/backlog/`` that is not valid UTF-8 escaped the guard and
    ``/tickets/{id}`` returned 500 for it. Asserted at the route level
    because that is where the failure was visible; the corpus-scan half of
    the same defect is pinned in ``tests/test_backlog_corpus_encoding.py``.
    """
    (fixture_root / "cortex" / "backlog" / "7-latin1.md").write_bytes(
        "---\nid: 7\ntitle: \"caf\N{PLUS-MINUS SIGN}\"\nstatus: open\n"
        "priority: medium\ntype: feature\n---\n\nBody.\n".encode("latin-1")
    )
    client = TestClient(app)

    assert client.get("/tickets/7").status_code == 200
    assert client.get("/partials/ticket/7").status_code == 200
    # The replacement character reached the page, which is the point: the
    # item renders, visibly wrong in exactly the byte that is wrong.
    assert "\N{REPLACEMENT CHARACTER}" in client.get("/tickets/7").text


def test_history_row_shows_the_session_duration(fixture_root):
    """``GET /sessions`` renders a real duration, not the em-dash placeholder.

    Regression, and the reason this assertion lives at the route level rather
    than beside ``parse_session_list``: the data layer was never wrong. It
    emitted ``duration_secs`` and the template read ``duration_str | default('—')``,
    so a Jinja undefined took the default arm for every row of every session
    and the Duration column could not display a value on any corpus. A
    data-layer test passes against that bug; only a render assertion fails.
    """
    session_dir = fixture_root / "cortex" / "lifecycle" / "sessions" / "overnight-2026-01-02-2200"
    session_dir.mkdir(parents=True)
    (session_dir / "overnight-state.json").write_text(
        json.dumps({
            "session_id": "overnight-2026-01-02-2200",
            "started_at": "2026-01-02T22:00:00Z",
            "updated_at": "2026-01-03T04:51:00Z",
            "features": {"feat-a": {"status": "merged"}},
        }),
        encoding="utf-8",
    )

    body = TestClient(app).get("/sessions").text

    assert "6h 51m" in body


def test_landing_page_is_the_backlog_not_the_overnight_view(fixture_root):
    """``/`` serves the navigator; the session view moved to ``/overnight``.

    Asserted on rendered markup rather than on the route table, because the
    failure this guards is a page that still returns 200 while showing the
    wrong view — which is exactly what a route-registration mistake looks like
    from the outside.
    """
    client = TestClient(app)

    landing = client.get("/").text
    overnight = client.get("/overnight").text

    # The navigator's shell carries the navigator panel; the overnight shell
    # carries the session panel. Neither id appears in the other template.
    assert 'id="navigator-panel"' in landing
    assert 'id="session-panel"' in overnight
    assert 'id="session-panel"' not in landing
    assert 'id="navigator-panel"' not in overnight


def test_backlog_alias_serves_the_same_page_as_the_landing_route(fixture_root):
    """Existing links, bookmarks, and open tabs point at ``/backlog``."""
    client = TestClient(app)

    assert client.get("/backlog").status_code == 200
    assert 'id="navigator-panel"' in client.get("/backlog").text


# ---------------------------------------------------------------------------
# The Docs view: the 404 arm and the edit verb's three answers.
# ---------------------------------------------------------------------------

_SHA_FIELD = re.compile(r'name="sha" value="([0-9a-f]{64})"')


def _open_editor(client: TestClient, path: str) -> str:
    """Open the edit form and return the content hash it was filled with."""
    page = client.get(f"/docs/{path}?edit=1")
    assert page.status_code == 200
    match = _SHA_FIELD.search(page.text)
    assert match, "the edit form carries no sha field"
    return match.group(1)


def test_unknown_doc_returns_404(client):
    """A path outside the governing set is 404, whether or not it exists."""
    assert client.get("/docs/nope.md").status_code == 404


def test_existing_file_outside_the_governing_set_returns_404(client, fixture_root):
    """The corpus is the rail: a ticket file exists on disk and is still 404."""
    assert (fixture_root / "cortex" / "backlog" / "1-smoke-test-ticket.md").exists()
    assert client.get("/docs/cortex/backlog/1-smoke-test-ticket.md").status_code == 404


def test_save_with_a_stale_sha_is_409_and_writes_nothing(client, fixture_root):
    target = fixture_root / "CLAUDE.md"
    before = target.read_text(encoding="utf-8")
    sha = _open_editor(client, "CLAUDE.md")

    response = client.post(
        "/docs/CLAUDE.md",
        data={"content": "# Overwritten\n", "sha": "0" * 64},
        follow_redirects=False,
    )

    assert response.status_code == 409
    assert target.read_text(encoding="utf-8") == before
    # The operator's text survives, the disk version is shown, and the form
    # now carries the disk hash so a second save is an informed one.
    assert "# Overwritten" in response.text
    assert "Smoke project" in response.text
    assert f'name="sha" value="{sha}"' in response.text


def test_save_with_the_current_sha_is_303_and_changes_the_file(client, fixture_root):
    target = fixture_root / "CLAUDE.md"
    sha = _open_editor(client, "CLAUDE.md")

    response = client.post(
        "/docs/CLAUDE.md",
        data={"content": "# Smoke project\r\n\r\nEdited through the form.", "sha": sha},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/docs/CLAUDE.md"
    # CRLF normalised, exactly one trailing newline.
    assert target.read_text(encoding="utf-8") == "# Smoke project\n\nEdited through the form.\n"
    assert "Edited through the form." in client.get("/docs/CLAUDE.md").text


def test_save_to_a_non_governing_path_is_refused(client, fixture_root):
    """POST to a path the corpus does not list renders the 404 arm and writes nothing."""
    stray = fixture_root / "cortex" / "backlog" / "1-smoke-test-ticket.md"
    before = stray.read_text(encoding="utf-8")

    response = client.post(
        "/docs/cortex/backlog/1-smoke-test-ticket.md",
        data={"content": "x\n", "sha": "0" * 64},
        follow_redirects=False,
    )

    assert response.status_code == 404
    assert stray.read_text(encoding="utf-8") == before
