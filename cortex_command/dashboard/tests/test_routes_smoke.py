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
]

# Page + health routes that must render 200. ``/backlog`` is
# the two navigator pages — peers of ``/``, not fragments — so they go through
# the same TemplateResponse path this module exists to guard. ``/tickets/1`` is the
# seeded ticket from fixture_root below.
PAGE_ROUTES = ["/", "/backlog", "/sessions", "/health", "/tickets/1"]

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
