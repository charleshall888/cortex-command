# Specification: add-tickets-id-pages-rendering-ticket

> Parent epic 410's discovery research is at `cortex/research/dashboard-command-station/research.md`. Two of its Decision Records are stale against shipped code and are not carried into this spec — see `research.md` § Epic Reference.

## Problem Statement

Lifecycle artifacts — research, spec, plan, review — cannot be read from the dashboard at all. Sibling #412 shipped ticket-*body* reading as an expandable board row, so the epic's original "tickets cannot be read" framing is now half-solved; what remains unreadable is the artifact set, which is where the reasoning behind a ticket actually lives. Reading any of it means opening an editor or spending session tokens having it summarized, which is the cost epic 410 exists to remove. The dashboard's own feature cards still advertise `spec.md` and `plan.md` links that go nowhere — the epic's named evidence, currently unowned by any sibling ticket. Underneath both, the rendering path that would display artifacts silently deletes content: 5% of artifacts contain a bare `<slug>`-style placeholder that the sanitizer drops without a trace.

## Phases

- **Phase 1: Lossless rendering** — make the markdown path preserve placeholder tokens, so artifacts can be displayed without corruption.
- **Phase 2: The ticket page** — the deep-linkable `/tickets/{id}` reading surface with lazily-loaded artifacts.
- **Phase 3: Inbound links** — retire the dead placeholder links and the seed defect that would mask them.

## Requirements

1. **Unrecognized angle-bracket tokens survive rendering as literal text.** Rendering the string `cortex/lifecycle/<slug>/research.md` through the ticket-body markdown path produces output containing an escaped `<slug>` token; it currently produces `cortex/lifecycle//research.md`. Grounding: `cortex_command/dashboard/data.py:1236-1304`. **Phase**: Lossless rendering
2. **Tag filtering is not weakened by requirement 1.** The existing sanitization tests in `cortex_command/dashboard/tests/test_data.py` (`TestLoadTicketBody`, from line 1586) pass unchanged, and a body containing a `<script>` element yields no executable script element in the output. **Phase**: Lossless rendering
3. **No double-escaping regression.** Rendering the ten largest artifacts under `cortex/lifecycle/` produces zero occurrences of `&amp;lt;`, `&amp;gt;`, or `&amp;amp;` in the output. **Phase**: Lossless rendering
4. **Placeholder-drop coverage is asserted at the data layer, not assumed.** `cortex_command/dashboard/tests/test_data.py`'s `TestLoadTicketBody` class (`cortex_command/dashboard/tests/test_data.py:1586`) gains test coverage for two cases: a bare unrecognized token such as `<slug>` rendered outside any code span, asserted to appear as an escaped literal in `got["html"]`; and the same token written inside a fenced code block, asserted to appear unescaped-as-code (i.e. still rendered via the existing code-block path) in `got["html"]`. Both cases are covered by distinct test methods so one cannot regress without failing its own assertion. `pytest cortex_command/dashboard/tests/test_data.py -k TestLoadTicketBody` exits 0. **Phase**: Lossless rendering
5. **The new reading surfaces get the same four test layers already used elsewhere in the dashboard test suite.** Concretely:
   - Route smoke: `/tickets/{id}` and the artifact partial route are added to `cortex_command/dashboard/tests/test_routes_smoke.py`'s route lists (`PARTIAL_ROUTES`, lines 40-57; `PAGE_ROUTES`, line 62) or an equivalent parametrized case, and pass under `test_route_renders_200` (lines 93-99); an unseeded id returns 404 under a case following `test_missing_session_returns_404`'s pattern (lines 102-105).
   - Template/structural: `cortex_command/dashboard/tests/test_templates.py` gains assertions for the badge strip and artifact panel elements, in the style of `TestStructuralElements` (line 293), and an assertion that both new routes stand down under a non-local backlog backend, in the style of `TestBacklogPanelBackendGate` (line 317).
   - Composite-loader: `cortex_command/dashboard/tests/test_data.py` gains a test class for the new artifact-join loader (requirement 9), covering the found-path, the `spec:`-missing/`lifecycle_slug`-fallback path, and the neither-key path, in the style of `tests/test_sessions.py`'s `TestSessionDetail` (line 117).

   `pytest cortex_command/dashboard/tests/` exits 0 with all of the above present. **Phase**: The ticket page
6. **`GET /tickets/{id}` renders a page for a known id and 404s for an unknown one.** Against the seeded fixture corpus, a request for a seeded ticket id returns 200 and a request for an unseeded numeric id returns 404, following the not-found-branch pattern of `cortex_command/dashboard/app.py:326-327` rather than raising. **Phase**: The ticket page
7. **The page renders a frontmatter badge strip using a badge mapping of its own, not the existing feature-status vocabulary.** Status, priority, type, and — where present — parent and areas appear as badges. The existing `_BADGE_CLASS_MAP` / `_STATUS_ICON_MAP` (`cortex_command/dashboard/app.py:83-94` and `:96-107`) key on the overnight feature-pipeline vocabulary (`merged`, `spec-done`, `plan-done`, `plan-approved`, `running`, `implementing`, `failed`, `paused`, `deferred`, `pending`) and must not be reused for backlog ticket statuses, whose vocabulary differs (observed in the corpus: `complete`, `wontfix`, `abandoned`, `superseded`, `backlog`, `refined`, `done`, `deferred`, `in_progress`, `ready`, among others). A backlog-status badge is styled by a mapping defined for backlog statuses, distinct from `_BADGE_CLASS_MAP`/`_STATUS_ICON_MAP`. **Phase**: The ticket page
8. **The page renders the ticket body by reusing the shipped loader.** `load_ticket_body` (`cortex_command/dashboard/data.py:1315`) supplies the body; no second frontmatter-stripping or body-rendering implementation is introduced. **Phase**: The ticket page
9. **Artifacts are discovered by a two-key join.** The `spec:` frontmatter value's parent directory is tried first, then a `lifecycle_slug` fallback probing both `cortex/lifecycle/<slug>/` and `cortex/lifecycle/archive/<slug>/`. Verified against the corpus: the two-key join resolves 286 tickets where `spec:` alone resolves 259. **Phase**: The ticket page
10. **Each artifact loads in its own request, on expansion.** Opening the page issues no artifact render; expanding one artifact panel fetches and renders exactly that artifact. Observable as one request per expanded panel in the dashboard process log. **Phase**: The ticket page
11. **The new route handlers are declared synchronous.** Both the page route and the artifact partial route are plain `def`, not `async def`, so Starlette dispatches them to the threadpool. Grounding: `starlette/routing.py:request_response`. **Phase**: The ticket page
12. **Artifacts have their own size cap.** A constant distinct from `TICKET_BODY_MAX_CHARS` (`cortex_command/dashboard/data.py:1312`) governs artifact truncation, sized with headroom above the measured 63,707-char maximum. Truncation is reported to the reader, not silent. **Phase**: The ticket page
13. **Both new routes stand down under a non-local backlog backend.** Each calls `resolve_backlog_backend(root)` and renders an unavailable state rather than raising, matching `cortex_command/dashboard/app.py:470`. **Phase**: The ticket page
14. **Epic children are linkified.** On a ticket that is an epic, child ids render as links to their own `/tickets/{id}` pages. **Phase**: The ticket page
15. **Route registration order keeps `/tickets/{id}` safe against a future list route.** In `cortex_command/dashboard/app.py`, no `@app.get(...)` line declaring a literal route under a given path prefix appears below the `@app.get(...)` line declaring a path-parameterized route sharing that prefix — the file's existing routes already hold this invariant (`/sessions`, line 312, precedes `/sessions/{session_id}`, line 323; the eleven literal `/partials/*` routes, lines 336-450, precede `/partials/ticket/{item_id}`, line 459). `/tickets/{id}` preserves it: as of this ticket, no literal `/tickets` route exists, so `/tickets/{id}` may be declared anywhere relative to unrelated routes; the requirement binds on any *future* literal `/tickets` route, which must be declared above `/tickets/{id}` in the file. A reader confirms the invariant by reading `@app.get(...)` declaration order top-to-bottom in `cortex_command/dashboard/app.py` and checking that no literal-prefix route appears after a path-parameterized route sharing its prefix — true today, and this ticket's addition of `/tickets/{id}` does not break it. **Phase**: The ticket page
16. **The feature-card artifact links resolve.** `backlog_id` links to `/tickets/{id}`; `spec_path` links to the spec artifact on that page. `plan_path` links only when `backlog_id` is present, and stays inert otherwise. Grounding: `cortex_command/dashboard/templates/feature_cards.html:226-228`, `cortex_command/overnight/state.py:106-108`. **Phase**: Inbound links
17. **The seed writes a numeric `backlog_id`.** `cortex_command/dashboard/seed.py:145-158` currently writes a slug string against a declared `Optional[int]`; after the fix, every seeded feature card's backlog link resolves under the seed corpus. **Phase**: Inbound links
18. **The seed corpus exercises the primary artifact path.** At least one seeded ticket carries a resolvable join key pointing at a directory containing all four artifact kinds, so the found-path is covered end to end rather than only the missing-path. **Phase**: Inbound links
19. **The board links out to the page.** A board row offers navigation to that ticket's `/tickets/{id}` page, so the expandable row and the page are connected surfaces rather than two disconnected readers. **Phase**: Inbound links

## Non-Requirements

- **Converting the other sixteen `async def` routes to sync `def`.** All of them block the event loop today; that is a pre-existing cost unrelated to this ticket's problem, touches every route with no test asserting current behavior, and belongs in its own ticket citing the 306ms-vs-52ms measurement in `research.md`.
- **Reaching the 28 artifact-bearing lifecycle directories that no ticket references.** Several are Context-B ad-hoc refines with no backing ticket, so they are correctly unreachable from an id-keyed route. A slug-keyed entry point is a different feature.
- **Slide-over or in-board artifact presentation.** Deferred by the epic research as a strict enhancement; the board keeps its existing expandable body row unchanged.
- **A markdown sanitizer dependency (nh3 or equivalent).** The shipped allowlist sanitizer is retained and repaired, not replaced.
- **Caching rendered artifacts in dashboard state.** Everything on this page is computed per request.
- **A nav-bar entry for the page.** It is a detail page reached by link, matching `/sessions/{id}`, which is likewise absent from nav.

## Edge Cases

- **`spec:` points at a directory that no longer exists** (5 tickets in the current corpus): fall through to the `lifecycle_slug` probe, then render "no artifacts" — never a 500.
- **Ticket has neither join key** (150 of 448): the page renders body and badges with an empty artifact section.
- **Join key resolves but the directory holds only some artifact kinds**: only the present kinds get panels; absent kinds are not rendered as empty shells.
- **Artifact exceeds the cap**: truncate and tell the reader, matching the existing body behavior rather than failing.
- **`item_id` is not a bare integer**: rejected before any filesystem call, per `data.py:1339`.
- **`feat.backlog_id` is `None`** (legitimate for features not sourced from numbered backlog files, `state.py:83`): the backlog and plan links stay inert rather than rendering a broken target.
- **Non-local backlog backend**: both routes render unavailable; no filesystem read is attempted.
- **A ticket whose body is frontmatter-only**: the existing "no description" branch of `ticket_body.html` is reused.
- **An artifact containing a bare token inside a fenced code block**: the token is preserved by the existing code-block path and must not be double-escaped by the requirement-1 fix.

## Changes to Existing Behavior

- **MODIFIED** — `_TicketBodySanitizer` (`data.py:1236-1304`) stops dropping unrecognized angle-bracket start tags and escapes them as literal text. This changes what #412's already-shipped `/partials/ticket/{item_id}` renders for the 5 ticket bodies (1.1%) currently affected: content that silently vanished now appears.
- **MODIFIED** — `feature_cards.html:226-228` artifact links gain real targets in place of `href="#"`.
- **MODIFIED** — `seed.py:145-158` writes `backlog_id` as an integer.
- **ADDED** — a `/tickets/{id}` page route, an artifact partial route, their templates, and their data loaders.

## Technical Constraints

- Read-only: no writes to backlog, lifecycle, or session state (`cortex/requirements/observability.md`).
- No database; in-memory cache only; the existing four polling loops are not extended (`observability.md:103`).
- The dashboard binds `127.0.0.1` on both launch paths (`cortex_command/cli.py:517`, `observability.md:107`).
- Per-artifact render cost is 7.5ms median, 38.2ms worst measured — acceptable only off the event loop, which requirement 11 secures.
- `cortex_command/dashboard/` is not lifecycle-gated (`CLAUDE.md:27`), but `docs/policies.md` owns dashboard behavior and docs.
- Templates resolve via `importlib.resources`; never add `__init__.py` under `templates/`.
- `test_routes_smoke.py` is a blocking CI gate.

## Open Decisions

None.

## Proposed ADR

### Proposed ADR: 0026-sync-def-for-non-awaiting-dashboard-routes

Every one of the dashboard's seventeen route handlers is declared `async def`, yet the package contains no `await` expression — each performs synchronous disk reads and markdown rendering directly on the event loop thread, blocking the four polling loops for its full duration. Measured: a 300ms handler starved a 50ms-tick loop to a 306ms gap as `async def`, versus 52ms as sync `def`, because Starlette wraps non-coroutine handlers in `run_in_threadpool` (`starlette/routing.py:request_response`). This ticket's routes are the first to render artifact-sized documents, so they are the first where the difference is user-visible. The decision is to declare handlers that await nothing as plain `def`, accepting that the codebase will temporarily hold both conventions rather than converting all seventeen routes in a ticket whose problem statement is unrelated. The trade-off is a mixed convention until a follow-up ticket converts the rest — chosen over both a repo-wide conversion here (unbounded blast radius, no covering tests) and matching the existing `async def` default (knowingly shipping the starvation this ticket measured).
