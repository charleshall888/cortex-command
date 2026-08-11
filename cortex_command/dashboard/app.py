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
from cortex_command.dashboard.backlog.view import build_epic_map, build_navigator
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
from cortex_command.dashboard.repos import (
    Repo,
    RepoRegistry,
    build_registry,
    resolve_roots,
)

# ---------------------------------------------------------------------------
# Module-level singletons: created at import time so routes can reference them
# ---------------------------------------------------------------------------

#: The tracked repos and their per-repo state. Populated by the lifespan,
#: which is also where the polling loops are started — one per repo.
registry: RepoRegistry = RepoRegistry()

#: The default repo's state, kept as a module attribute because it is the
#: single-repo answer and several helpers still want a zero-argument view.
#: Every *route* resolves its state per request instead; see `_state()`.
state: DashboardState = DashboardState()


def _root() -> Path:
    """Resolve the user's cortex project root at request time.

    Spec R3c forbids module-level capture of `_resolve_user_project_root()`;
    every consumer must invoke this function so the user's project root is
    resolved at the moment the path is needed.

    Still the *default* root, and still env-resolved when the registry is
    empty — which is what direct-template tests and any importer that never
    ran the lifespan get.
    """
    default = registry.default
    return default.root if default is not None else _resolve_user_project_root()


def _repo(request: Request) -> Repo | None:
    """Resolve which repo a request addressed, from its ``repo`` query param.

    The parameter travels on the page URL and on every htmx partial the page
    polls, so a fragment can never be rendered against a different root than
    the shell that asked for it.
    """
    return registry.resolve(request.query_params.get("repo"))


def _state(request: Request) -> DashboardState:
    """Return the polled state belonging to *request*'s repo."""
    repo = _repo(request)
    if repo is None:
        return state
    return registry.state_for(repo)


def _root_of(request: Request) -> Path:
    """Return the filesystem root belonging to *request*'s repo."""
    repo = _repo(request)
    return repo.root if repo is not None else _root()


def _ctx(request: Request, **extra: object) -> dict:
    """The template context every page and fragment is rendered with.

    Centralised so the repo a request addressed reaches the template on every
    route by construction. Threading it per call site is the version where one
    forgotten route renders the switcher against the default repo while its
    panels show another, and that page looks correct.
    """
    context: dict = {"request": request, "state": _state(request)}
    context.update(_repo_context(request))
    context.update(extra)
    return context


def _repo_context(request: Request) -> dict:
    """The switcher's view-model, carried by every page and fragment.

    ``repo_query`` is the suffix a template appends to an ``hx-get`` so the
    30s poll keeps asking about the repo the operator is looking at. It is
    empty in the single-repo case, which keeps every existing URL byte-identical
    and the rendered page unchanged for repos that track one checkout.
    """
    current = _repo(request)
    return {
        "repos": registry.repos,
        "repo": current,
        "repo_multi": registry.multi,
        "repo_query": (
            "?repo=%s" % current.slug if registry.multi and current else ""
        ),
    }

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

    global registry, state

    roots = resolve_roots(_resolve_user_project_root())
    registry = build_registry(roots)

    # The primary root keeps the strict check: a process started against a
    # directory that is not a cortex checkout is misconfigured and should say
    # so at startup rather than serve empty panels. Additional roots do not
    # get it — they are opt-in extras, and one bad entry in a tracked list
    # must not take the whole dashboard down with it.
    primary = registry.default
    if primary is None or not (primary.root / ".claude").exists():
        raise RuntimeError(
            f"Dashboard lifecycle root appears wrong: "
            f"{primary.root if primary else '<none>'}. "
            "Check module installation."
        )

    _pid_file.write_text(str(os.getpid()), encoding="utf-8")

    # Remove the PID file only when it still names *this* process.
    #
    # Unconditional removal is a live bug when two servers overlap: uvicorn
    # runs the lifespan before it binds, so a second launch on a taken port
    # writes its pid, fails to bind, and its atexit hook then deletes the file
    # belonging to the server that is still serving. Measured: after one such
    # collision the PID file was gone entirely while the original process was
    # still listening — so every liveness reader (the overnight probe, the
    # justfile recipe, `--background`'s idempotency check) concluded nothing
    # was running.
    owner_pid = os.getpid()

    def _release_pid_file() -> None:
        try:
            if _pid_file.read_text(encoding="utf-8").strip() == str(owner_pid):
                _pid_file.unlink(missing_ok=True)
        except OSError:
            pass

    atexit.register(_release_pid_file)

    for repo in registry.repos:
        repo_state = registry.state_for(repo)
        # Resolve the backlog backend synchronously so the first served render
        # reflects the real backend. The slow poller is fire-and-forget (the
        # task below runs after `yield`), so without this a non-local repo
        # would render the default cortex-backlog arm until the first 30s poll.
        repo_state.backlog_backend = resolve_backlog_backend(repo.root)
        # One loop per repo, each writing only into its own state. Sharing a
        # loop would serialise every repo behind the slowest disk, and a slow
        # 30s backlog scan under one checkout would stall the 1s event tail of
        # the one the operator is actually watching.
        asyncio.create_task(run_polling(repo_state, repo.root))

    # The module attribute stays bound to the default repo's state so the
    # single-repo view of this module is unchanged.
    previous_state = state
    state = registry.state_for(primary)
    try:
        yield
    finally:
        # The lifespan owns the registry's lifetime, so shutdown returns the
        # module to how it was found. Leaving a populated registry behind means
        # every later consumer resolves roots against whatever this process was
        # started with — in-process that is a stale root pointing at a torn-down
        # temp directory, and the pages it serves are not empty, they are wrong.
        registry = RepoRegistry()
        state = previous_state


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
    last_session = parse_last_session(_root_of(request) / "cortex" / "lifecycle")
    return templates.TemplateResponse(
        request,
        "base.html",
        _ctx(request, last_session=last_session),
    )


@app.get("/backlog")
async def backlog_view(request: Request):
    """Render the backlog navigator — surface A, as a peer page.

    Shell only. All four navigator sections arrive from
    ``/partials/navigator`` on the same 30s poll the panels used when they sat
    at the bottom of the overnight page. The separate ledger panel is gone —
    graft G5 folded it into the § 04 census, on the grounds that a distribution
    bar states its counts further from the glyphs that explain them. The census
    is not a like-for-like replacement and does not claim to be: it describes
    the active slice, where the bar described every file in ``cortex/backlog/``
    by frontmatter status. What that drops is the terminal tail — records
    closed in place, which the census counts as neither active nor archived and
    says so in its own copy. Deliberate: summing the two into a repo total
    would print a number wrong by an order of magnitude.
    """
    return templates.TemplateResponse(
        request,
        "backlog.html",
        _ctx(request),
    )


@app.get("/epics")
async def epics_view(request: Request):
    """Render the epic map — surface B, a peer page of the navigator.

    Shell only, for the same reason ``/backlog`` is: the frames are geometry
    computed from the 30s snapshot, so they belong to the polled fragment and
    not to a page render that would freeze them until a reload.
    """
    return templates.TemplateResponse(
        request,
        "epics.html",
        _ctx(request),
    )


@app.get("/sessions")
async def sessions_list(request: Request):
    """Render the session history list page."""
    sessions = parse_session_list(_root_of(request) / "cortex" / "lifecycle")
    return templates.TemplateResponse(
        request,
        "sessions_list.html",
        _ctx(request, sessions=sessions),
    )


@app.get("/sessions/{session_id}")
async def session_detail(session_id: str, request: Request):
    """Render the detail page for a single session."""
    detail = parse_session_detail(session_id, _root_of(request) / "cortex" / "lifecycle")
    status_code = 404 if detail is None else 200
    return templates.TemplateResponse(
        request,
        "session_detail.html",
        _ctx(request, detail=detail),
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
    root = _root_of(request)
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
        _ctx(request, item_id=item_id, ticket=ticket, backend=backend),
        status_code=status_code,
    )


@app.get("/partials/fleet-panel")
async def fleet_panel(request: Request):
    """Return the agent fleet panel HTML fragment for HTMX polling."""
    return templates.TemplateResponse(
        request,
        "fleet-panel.html",
        _ctx(request),
    )


@app.get("/partials/alerts-banner")
async def alerts_banner(request: Request):
    """Return the alerts banner HTML fragment for HTMX polling."""
    return templates.TemplateResponse(
        request,
        "alerts_banner.html",
        _ctx(request),
    )


@app.get("/partials/session-panel")
async def session_panel(request: Request):
    """Return the session panel HTML fragment for HTMX polling."""
    last_session = parse_last_session(_root_of(request) / "cortex" / "lifecycle")
    return templates.TemplateResponse(
        request,
        "session_panel.html",
        _ctx(request, last_session=last_session),
    )


@app.get("/partials/feature-cards")
async def feature_cards(request: Request):
    """Return the feature cards HTML fragment for HTMX polling."""
    return templates.TemplateResponse(
        request,
        "feature_cards.html",
        _ctx(request),
    )


@app.get("/partials/round-history")
async def round_history(request: Request):
    """Return the round history HTML fragment for HTMX polling."""
    return templates.TemplateResponse(
        request,
        "round_history.html",
        _ctx(request),
    )


@app.get("/partials/escalations")
async def escalations_panel(request: Request):
    """Return the escalations / open-questions panel for HTMX polling."""
    return templates.TemplateResponse(
        request,
        "escalations_panel.html",
        _ctx(request),
    )


@app.get("/partials/activity-stream")
async def activity_stream(request: Request):
    """Return the recent overnight events stream panel for HTMX polling."""
    return templates.TemplateResponse(
        request,
        "activity_stream.html",
        _ctx(request),
    )


@app.get("/partials/metrics")
async def metrics_baseline(request: Request):
    """Return the phase-baseline metrics panel for HTMX polling."""
    return templates.TemplateResponse(
        request,
        "metrics_baseline.html",
        _ctx(request),
    )


@app.get("/partials/swim-lane")
async def swim_lane(request: Request):
    """Return the swim lane timeline HTML fragment for HTMX polling."""
    swim_data = build_swim_lane_data(
        state.overnight,
        state.overnight_events,
        state.feature_states,
        _root_of(request) / "cortex" / "lifecycle",
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


@app.get("/partials/navigator")
def navigator_panel(request: Request):
    """Return surface A — the pick, its alternates, the board and the census.

    Declared ``def``, not ``async def``, for the reason ``ticket_page`` gives:
    Starlette dispatches a non-coroutine handler to the threadpool, and this
    one rebuilds a dependency graph, a ranking and an eleven-band partition
    over the whole active slice on every 30s poll for every open tab. That is
    pure CPU with no await in it, so on the event loop it would block the four
    polling loops for its whole duration.

    Sits behind the same backend gate as every other backlog read: the poller
    clears the snapshot to ``None`` under a non-local backend, and the
    view-model carries the resolved backend so the fragment renders the gated
    arm rather than an empty board it never looked at.
    """
    return templates.TemplateResponse(
        request,
        "navigator.html",
        _ctx(request, nav=build_navigator(_state(request), _root_of(request),
                                 link_suffix=_repo_context(request)["repo_query"])),
    )


@app.get("/partials/epic-map")
def epic_map_panel(request: Request):
    """Return surface B — the epic frames and the tail table.

    Declared ``def`` for the same reason as ``navigator_panel`` above: the
    layout for every frame on the page is computed here, per poll.
    """
    return templates.TemplateResponse(
        request,
        "epic_map.html",
        _ctx(request, epics=build_epic_map(_state(request), _root_of(request),
                                link_suffix=_repo_context(request)["repo_query"])),
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
    root = _root_of(request)
    if resolve_backlog_backend(root) != "cortex-backlog":
        ticket = None
    else:
        ticket = load_ticket_body(item_id, root / "cortex" / "backlog")
    return templates.TemplateResponse(
        request,
        "ticket_body.html",
        {"request": request, "ticket": ticket},
    )


@app.get("/partials/ticket-card/{item_id}")
def ticket_card(request: Request, item_id: str):
    """Return one ticket as a modal card for the epic map.

    Declared ``def``, not ``async def``, for the reason ``ticket_page`` gives:
    ``load_ticket_page`` does disk reads and a markdown render, and Starlette
    dispatches a non-coroutine handler to the threadpool, which is what keeps
    that work off the four polling loops.

    Composes the *same* ``load_ticket_page`` the deep-link page composes rather
    than a lighter loader of its own. Two loaders would be two answers about
    one ticket, and the cheaper one would be the one that drifts.

    Always 200. The fragment lands inside a dialog the operator has already
    opened, and its three arms — gated, not-found, found — each render a
    readable card; a 404 status here would only give htmx a reason to leave the
    dialog empty. The deep-link route keeps its 404, because that one is a
    page you can bookmark.
    """
    root = _root_of(request)
    backend = resolve_backlog_backend(root)
    ticket = (
        load_ticket_page(
            item_id, root / "cortex" / "backlog", root / "cortex" / "lifecycle"
        )
        if backend == "cortex-backlog"
        else None
    )
    return templates.TemplateResponse(
        request,
        "_ticket_card.html",
        {
            "request": request,
            "item_id": item_id,
            "ticket": ticket,
            "backend": backend,
        },
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
    root = _root_of(request)
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
