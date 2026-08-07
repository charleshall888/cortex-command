"""FastAPI application for the agent monitoring dashboard.

Creates the FastAPI app with a Jinja2 template engine and a background polling
loop started via the lifespan context manager.

Routes:
    GET /health  -- returns {"status": "ok"}
    GET /        -- renders base.html with current dashboard state

Entry point (uvicorn):
    uv run uvicorn cortex_command.dashboard.app:app --host 127.0.0.1 --port 8080
"""

from __future__ import annotations

import asyncio
import atexit
import importlib.resources
import os
from contextlib import ExitStack, asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from cortex_command.common import _resolve_user_project_root
from cortex_command.lifecycle_config import resolve_backlog_backend
from cortex_command.dashboard.data import (
    build_swim_lane_data,
    load_ticket_artifact,
    load_ticket_body,
    load_ticket_page,
    parse_last_session,
    parse_session_detail,
    parse_session_list,
)
from cortex_command.dashboard.poller import DashboardState, run_polling

# ---------------------------------------------------------------------------
# Module-level singletons: created at import time so routes can reference them
# ---------------------------------------------------------------------------

state: DashboardState = DashboardState()


def _root() -> Path:
    """Resolve the user's cortex project root at request time.

    Spec R3c forbids module-level capture of `_resolve_user_project_root()`;
    every consumer must invoke this function so the user's project root is
    resolved at the moment the path is needed.
    """
    return _resolve_user_project_root()

# ---------------------------------------------------------------------------
# Jinja2 templates
# ---------------------------------------------------------------------------

_template_resource_stack = ExitStack()
atexit.register(_template_resource_stack.close)
# Resolve templates/ through the REGULAR ``cortex_command.dashboard`` package,
# never as the ``...dashboard.templates`` package name: templates/ has no
# __init__.py, so naming it directly makes importlib treat it as a namespace
# package and ``as_file`` extract every template to a TemporaryDirectory. That
# temp dir is owned by this module-level stack — and a module reload (e.g.
# tests re-resolving the PID path) rebinds the stack, so the orphaned old one
# is torn down at the next cyclic GC, deleting the extraction out from under
# every ``templates`` reference captured before the reload (TemplateNotFound).
# The parent package is a real filesystem directory in every supported install
# (wheels unpack; nothing runs zipped), so as_file returns the stable real
# path and the stack holds no temp state.
_templates_dir = _template_resource_stack.enter_context(
    importlib.resources.as_file(
        importlib.resources.files("cortex_command.dashboard") / "templates"
    )
)
templates = Jinja2Templates(directory=str(_templates_dir))

# ---------------------------------------------------------------------------
# Jinja2 helper filters
# ---------------------------------------------------------------------------

_BADGE_CLASS_MAP = {
    "merged": "badge-green",
    "spec-done": "badge-green",
    "plan-done": "badge-green",
    "plan-approved": "badge-green",
    "running": "badge-blue",
    "implementing": "badge-blue",
    "failed": "badge-red",
    "paused": "badge-amber",
    "deferred": "badge-amber",
    "pending": "badge-gray",
}

_STATUS_ICON_MAP = {
    "merged": "✓",
    "spec-done": "✓",
    "plan-done": "✓",
    "plan-approved": "✓",
    "running": "●",
    "implementing": "●",
    "failed": "✕",
    "paused": "⚠",
    "deferred": "⚠",
    "pending": "○",
}


def _format_elapsed(iso_str: str | None) -> str:
    """Return 'Xs ago', 'Xm ago', or 'Xh Ym ago' elapsed since *iso_str* (ISO-8601) to now."""
    if not iso_str:
        return "—"
    try:
        start = datetime.fromisoformat(iso_str)
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - start
        total_seconds = int(delta.total_seconds())
        if total_seconds < 60:
            return f"{total_seconds}s ago"
        total_minutes = total_seconds // 60
        hours, minutes = divmod(total_minutes, 60)
        return f"{hours}h {minutes}m ago" if hours else f"{minutes}m ago"
    except (ValueError, TypeError):
        return "—"


def _format_duration(start_iso: str | None, end_iso: str | None) -> str:
    """Return 'Xh Ym' or 'Nm' duration between two ISO-8601 timestamps."""
    if not start_iso or not end_iso:
        return "—"
    try:
        start = datetime.fromisoformat(start_iso)
        end = datetime.fromisoformat(end_iso)
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        delta = end - start
        total_minutes = int(delta.total_seconds() // 60)
        hours, minutes = divmod(total_minutes, 60)
        return f"{hours}h {minutes}m" if hours else f"{minutes}m"
    except (ValueError, TypeError):
        return "—"


def _format_elapsed_no_suffix(iso_str: str | None) -> str:
    """Return 'Xh Ym' or 'Nm' elapsed since *iso_str* (ISO-8601) to now, without 'ago' suffix."""
    if not iso_str:
        return "—"
    try:
        start = datetime.fromisoformat(iso_str)
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - start
        total_seconds = int(delta.total_seconds())
        if total_seconds < 60:
            return f"{total_seconds}s"
        total_minutes = total_seconds // 60
        hours, minutes = divmod(total_minutes, 60)
        return f"{hours}h {minutes}m" if hours else f"{minutes}m"
    except (ValueError, TypeError):
        return "—"


def _format_duration_secs(secs: int | None) -> str:
    """Return 'Xm Ys' (e.g. '7m 23s') or '—' for None/0."""
    if not secs:
        return "—"
    try:
        total = int(secs)
        minutes, seconds = divmod(total, 60)
        return f"{minutes}m {seconds}s"
    except (ValueError, TypeError):
        return "—"


def _badge_class(status: str | None) -> str:
    """Map a feature/pipeline status string to a CSS badge class name."""
    return _BADGE_CLASS_MAP.get(status or "", "badge-gray")


def _badge_icon(status: str | None) -> str:
    """Map a feature/pipeline status string to a semantic Unicode icon character."""
    return _STATUS_ICON_MAP.get(status or "", "○")


def _format_date(iso_str: str | None) -> str:
    """Parse an ISO-8601 string and return 'Feb 26 2026 · 21:29'. Returns '—' on failure."""
    if not iso_str:
        return "—"
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%b %-d %Y · %H:%M")
    except (ValueError, TypeError):
        return "—"


templates.env.filters["format_elapsed"] = _format_elapsed
templates.env.filters["format_elapsed_no_suffix"] = _format_elapsed_no_suffix
templates.env.filters["format_duration"] = _format_duration
templates.env.filters["format_duration_secs"] = _format_duration_secs
templates.env.filters["badge_class"] = _badge_class
templates.env.filters["badge_icon"] = _badge_icon
templates.env.filters["format_date"] = _format_date
# Canonical wire-format → human-readable phase label, shared with the
# SessionStart hook so paused features render as "Implement — paused"
# consistently across surfaces.
from cortex_command.phase_labels import phase_label as _phase_label_filter
templates.env.filters["phase_label"] = _phase_label_filter

# ---------------------------------------------------------------------------
# PID file path (XDG-compliant)
# ---------------------------------------------------------------------------


def _resolve_pid_path() -> Path:
    """Return the XDG-compliant dashboard PID-file path.

    Honors ``XDG_CACHE_HOME`` when set, falling back to ``~/.cache``. The
    parent directory (``<cache>/cortex/``) is created if missing so callers
    can write the PID without first probing for the directory's existence.

    This resolver is the single source of truth shared across the
    ``cortex dashboard`` verb (cli.py), the FastAPI app (this module), the
    overnight runner's liveness probe (skills/overnight/SKILL.md L208), and
    the contributor-facing ``just dashboard`` recipe (justfile).
    """
    cache_home = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    pid_dir = Path(cache_home) / "cortex"
    pid_dir.mkdir(parents=True, exist_ok=True)
    return pid_dir / "dashboard.pid"


_pid_file: Path = _resolve_pid_path()


# ---------------------------------------------------------------------------
# Lifespan: start background polling loop on startup
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Note: no port pre-bind check here — uvicorn binds the port itself in
    # the parent process before the lifespan runs, so a lifespan-time
    # ``socket.bind()`` would collide with uvicorn's already-held socket.
    # Pre-bind availability checks belong in the verb (cli.py) before
    # ``uvicorn.run()`` is invoked.

    root = _root()
    if not (root / ".claude").exists():
        raise RuntimeError(
            f"Dashboard lifecycle root appears wrong: {root}. "
            "Check module installation."
        )

    _pid_file.write_text(str(os.getpid()), encoding="utf-8")
    atexit.register(lambda: _pid_file.unlink(missing_ok=True))

    # Resolve the backlog backend synchronously at startup so the first served
    # render reflects the real backend. The slow poller is fire-and-forget
    # (the task below runs after `yield`), so without this a non-local repo
    # would render the default cortex-backlog arm until the first 30s poll.
    state.backlog_backend = resolve_backlog_backend(root)

    asyncio.create_task(run_polling(state, root))
    yield


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health() -> JSONResponse:
    """Return a simple health-check response."""
    return JSONResponse({"status": "ok"})


@app.get("/")
async def index(request: Request):
    """Render the main dashboard page."""
    last_session = parse_last_session(_root() / "cortex" / "lifecycle")
    return templates.TemplateResponse(
        request,
        "base.html",
        {"request": request, "state": state, "last_session": last_session},
    )


@app.get("/backlog")
async def backlog_view(request: Request):
    """Render the backlog view — the ledger and triage board as a peer page.

    Both panels are served by the existing ``/partials/backlog`` and
    ``/partials/triage-board`` fragments, so this handler only supplies the
    page shell; the 30s HTMX poll fills it exactly as it did when the two
    sections sat at the bottom of the overnight page.
    """
    return templates.TemplateResponse(
        request,
        "backlog.html",
        {"request": request, "state": state},
    )


@app.get("/sessions")
async def sessions_list(request: Request):
    """Render the session history list page."""
    sessions = parse_session_list(_root() / "cortex" / "lifecycle")
    return templates.TemplateResponse(
        request,
        "sessions_list.html",
        {"request": request, "sessions": sessions},
    )


@app.get("/sessions/{session_id}")
async def session_detail(session_id: str, request: Request):
    """Render the detail page for a single session."""
    detail = parse_session_detail(session_id, _root() / "cortex" / "lifecycle")
    status_code = 404 if detail is None else 200
    return templates.TemplateResponse(
        request,
        "session_detail.html",
        {"request": request, "detail": detail},
        status_code=status_code,
    )


@app.get("/tickets/{item_id}")
def ticket_page(request: Request, item_id: str):
    """Render the deep-linkable reading page for one backlog ticket.

    Declared ``def``, not ``async def`` — every other handler in this file
    is a coroutine, but this one and the artifact partial below deliberately
    are not (requirement 11 / ADR-0026). Starlette dispatches a non-coroutine
    handler to the threadpool (``starlette/routing.py:request_response``),
    which is what keeps this handler's disk reads and markdown render (worst
    measured 38ms) off the four polling loops instead of blocking them on
    the event loop.

    Stands down under a non-local backlog backend rather than reading the
    filesystem; ``backend`` travels into the template so it can render the
    gated arm instead of the not-found one. See ``ticket_page.html`` for the
    three-arm body this feeds.
    """
    root = _root()
    backend = resolve_backlog_backend(root)
    ticket = (
        load_ticket_page(item_id, root / "cortex" / "backlog", root / "cortex" / "lifecycle")
        if backend == "cortex-backlog"
        else None
    )
    status_code = 404 if ticket is None else 200
    return templates.TemplateResponse(
        request,
        "ticket_page.html",
        {"request": request, "item_id": item_id, "ticket": ticket, "backend": backend},
        status_code=status_code,
    )


@app.get("/partials/fleet-panel")
async def fleet_panel(request: Request):
    """Return the agent fleet panel HTML fragment for HTMX polling."""
    return templates.TemplateResponse(
        request,
        "fleet-panel.html",
        {"request": request, "state": state},
    )


@app.get("/partials/alerts-banner")
async def alerts_banner(request: Request):
    """Return the alerts banner HTML fragment for HTMX polling."""
    return templates.TemplateResponse(
        request,
        "alerts_banner.html",
        {"request": request, "state": state},
    )


@app.get("/partials/session-panel")
async def session_panel(request: Request):
    """Return the session panel HTML fragment for HTMX polling."""
    last_session = parse_last_session(_root() / "cortex" / "lifecycle")
    return templates.TemplateResponse(
        request,
        "session_panel.html",
        {"request": request, "state": state, "last_session": last_session},
    )


@app.get("/partials/feature-cards")
async def feature_cards(request: Request):
    """Return the feature cards HTML fragment for HTMX polling."""
    return templates.TemplateResponse(
        request,
        "feature_cards.html",
        {"request": request, "state": state},
    )


@app.get("/partials/round-history")
async def round_history(request: Request):
    """Return the round history HTML fragment for HTMX polling."""
    return templates.TemplateResponse(
        request,
        "round_history.html",
        {"request": request, "state": state},
    )


@app.get("/partials/escalations")
async def escalations_panel(request: Request):
    """Return the escalations / open-questions panel for HTMX polling."""
    return templates.TemplateResponse(
        request,
        "escalations_panel.html",
        {"request": request, "state": state},
    )


@app.get("/partials/activity-stream")
async def activity_stream(request: Request):
    """Return the recent overnight events stream panel for HTMX polling."""
    return templates.TemplateResponse(
        request,
        "activity_stream.html",
        {"request": request, "state": state},
    )


@app.get("/partials/backlog")
async def backlog_panel(request: Request):
    """Return the backlog ledger panel for HTMX polling."""
    return templates.TemplateResponse(
        request,
        "backlog_panel.html",
        {"request": request, "state": state},
    )


@app.get("/partials/metrics")
async def metrics_baseline(request: Request):
    """Return the phase-baseline metrics panel for HTMX polling."""
    return templates.TemplateResponse(
        request,
        "metrics_baseline.html",
        {"request": request, "state": state},
    )


@app.get("/partials/swim-lane")
async def swim_lane(request: Request):
    """Return the swim lane timeline HTML fragment for HTMX polling."""
    swim_data = build_swim_lane_data(
        state.overnight,
        state.overnight_events,
        state.feature_states,
        _root() / "cortex" / "lifecycle",
    )
    return templates.TemplateResponse(
        request,
        "swim-lane.html",
        {
            "request": request,
            "lanes": swim_data["lanes"],
            "summary_mode": swim_data["summary_mode"],
            "total_elapsed_secs": swim_data["total_elapsed_secs"],
            "ticks": swim_data["ticks"],
        },
    )


@app.get("/partials/triage-board")
async def triage_board(request: Request):
    """Return the triage board panel for HTMX polling."""
    return templates.TemplateResponse(
        request,
        "triage_board.html",
        {"request": request, "state": state},
    )


@app.get("/partials/ticket/{item_id}")
async def ticket_body(request: Request, item_id: str):
    """Return one ticket's rendered description.

    Fetched when a board row is first expanded, not carried in the 30s
    snapshot — see ``load_ticket_body`` for why. Sits behind the same backend
    gate as every other backlog read: under a non-local backend there is no
    ``cortex/backlog/`` to read and the panel stands down rather than
    reporting a missing file as an error.
    """
    root = _root()
    if resolve_backlog_backend(root) != "cortex-backlog":
        ticket = None
    else:
        ticket = load_ticket_body(item_id, root / "cortex" / "backlog")
    return templates.TemplateResponse(
        request,
        "ticket_body.html",
        {"request": request, "ticket": ticket},
    )


@app.get("/partials/ticket/{item_id}/artifact/{kind}")
def ticket_artifact_partial(request: Request, item_id: str, kind: str):
    """Return one lifecycle artifact's rendered prose for a lazily-opened panel.

    Declared ``def``, not ``async def`` — see ``ticket_page`` above for why.

    Always 200, never a status code: a fragment landing inside a panel the
    operator opened reports "unavailable" the way ``ticket_body`` above does,
    whether the cause is a non-local backend, an unresolved ticket, an
    unresolved artifact directory, or a missing kind — see
    ``ticket_artifact.html``.
    """
    root = _root()
    if resolve_backlog_backend(root) != "cortex-backlog":
        artifact = None
    else:
        artifact = load_ticket_artifact(
            item_id, kind, root / "cortex" / "backlog", root / "cortex" / "lifecycle"
        )
    return templates.TemplateResponse(
        request,
        "ticket_artifact.html",
        {"request": request, "artifact": artifact},
    )
