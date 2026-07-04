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

This test drives ``GET /``, ``/sessions``, ``/health``, and each of the ten
``/partials/*`` routes and asserts 200, plus ``GET /sessions/{missing}`` -> 404
(the ``status_code`` path). On the dev venv (Starlette 0.52.1) both call forms
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

import pytest
from starlette.testclient import TestClient

from cortex_command.dashboard.app import app

# The ten HTMX partial routes, in the order documented by the spec.
PARTIAL_ROUTES = [
    "/partials/fleet-panel",
    "/partials/alerts-banner",
    "/partials/session-panel",
    "/partials/feature-cards",
    "/partials/round-history",
    "/partials/escalations",
    "/partials/activity-stream",
    "/partials/backlog",
    "/partials/metrics",
    "/partials/swim-lane",
]

# Page + health routes that must render 200.
PAGE_ROUTES = ["/", "/sessions", "/health"]

ALL_OK_ROUTES = PAGE_ROUTES + PARTIAL_ROUTES


@pytest.fixture
def fixture_root(tmp_path, monkeypatch):
    """Build a tmp cortex project root and point ``CORTEX_REPO_ROOT`` at it.

    Creates ``.claude/`` (required by the lifespan's ``RuntimeError`` guard at
    ``app.py``; ``_resolve_user_project_root`` returns ``CORTEX_REPO_ROOT``
    verbatim and does not itself require ``.claude/``) and an empty
    ``cortex/lifecycle/`` so the dashboard data parsers resolve cleanly.
    """
    (tmp_path / ".claude").mkdir()
    (tmp_path / "cortex" / "lifecycle").mkdir(parents=True)
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
