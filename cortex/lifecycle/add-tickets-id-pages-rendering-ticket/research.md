# Research: Add a deep-linkable /tickets/{id} dashboard page rendering ticket bodies and lifecycle artifacts

> Refine research, 2026-08-06. Sizing: complexity `moderate`, criticality `medium` (2-agent core wave, no adversarial — the clarify critic had already run an adversarial pass returning 9 findings). Requirements context loaded: `cortex/requirements/project.md`, `cortex/requirements/glossary.md`, `cortex/requirements/observability.md`.

Scope anchor (clarified intent): add a deep-linkable `/tickets/{id}` page that makes lifecycle artifacts readable from the dashboard for the first time, with a frontmatter badge strip, the rendered body, lazily-loaded inline artifacts, epic children linkified, and the dead placeholder links in `feature_cards.html` retired.

Settled at Clarify, not re-litigated here: full page (the board keeps its expandable row), artifacts inline-but-lazy, `spec:` frontmatter as the id→lifecycle join.

## Epic Reference

Parent epic 410's discovery research is at `cortex/research/dashboard-command-station/research.md` (RQ4 covers this ticket). It is background spanning all five children and is deliberately not copied here.

**Two of its Decision Records are now stale against shipped code** and must not be carried into the spec:

- Its **Sanitizer** record ("No nh3 … the surface is loopback-bound") describes a posture the code does not take. `data.py:1236-1304` ships `_TicketBodySanitizer`, a render-then-filter allowlist-tag rebuilder — genuine XSS hardening, the opposite of the recorded decision.
- Its **Stale docs** record lists `observability.md:107` and `app.py:11` as claiming a `0.0.0.0` bind. Sibling #415 fixed both; `observability.md:107` now states both launch paths bind `127.0.0.1`, matching `cortex_command/cli.py:517`.

## Codebase Analysis

**The premise needs restating.** Sibling #412 already shipped ticket-*body* reading: `GET /partials/ticket/{item_id}` [app.py:459-478] → `load_ticket_body` [data.py:1315-1404] → `ticket_body.html`, wired into expandable board rows at [triage_board.html:159-166]. The ticket's Why ("cannot be read from the dashboard at all") is false. The real gap is lifecycle artifacts (zero coverage), deep-linking, the badge strip, and epic-child linkification.

**What `load_ticket_body` already does** (reuse, do not duplicate): validates `item_id` as `\d{1,9}` before any filesystem call [data.py:1339]; padding-agnostic id match over `[0-9]*-*.md` [data.py:1350-1360]; `archive/` fallback [data.py:1362]; containment re-check against `backlog_dir` [data.py:1369-1373]; frontmatter strip extracting **only** `title` [data.py:1378-1390]; truncation at `TICKET_BODY_MAX_CHARS = 64_000` [data.py:1312]; markdown + sanitize. **What it does not do:** surface any other frontmatter field, or touch lifecycle artifacts at all. The badge strip and artifact panels need a separate loader.

**Precedents.** `/sessions/{session_id}` [app.py:312-333] is the page shape: list route registered before detail route, `status_code = 404 if detail is None else 200` with a not-found branch in the template rather than a raise [app.py:326-327; session_detail.html:9-15], `{% extends "base.html" %}` + `{% block page_main %}`. Nav is hand-edited at [base.html:2642-2645], but `/sessions/{id}` is itself absent from nav — a detail page reached by link, so `/tickets/{id}` should not add a nav entry either.

**HTMX lazy pattern** [triage_board.html:159-166]: `hx-trigger="toggle once from:closest details"` fires once when a `<details>` opens. It generalizes to four artifact panels by wrapping each in its own `<details>` — four independent triggers, structurally identical. `hx-preserve="true"` is needed on the board only because the 30s poller morphs that row; a full page has no competing poll and does not need it.

**Route ordering.** Current order: `/health`, `/`, `/backlog`, `/sessions`, `/sessions/{session_id}`, eleven literal `/partials/*`, then `/partials/ticket/{item_id}` last [app.py:279-478]. No collision exists for `/tickets/{id}` today; the constraint is forward-looking — any future `/tickets` list route must register before it.

**The id→lifecycle join, measured.** A second key exists that Clarify missed: some tickets carry `lifecycle_slug:` instead of `spec:` (confirmed: ticket 169). Measured across 448 backlog files against 342 artifact-bearing lifecycle dirs:

| join | tickets resolved |
|---|---|
| `spec:` alone | 259 |
| `spec:` → `lifecycle_slug` fallback | **286** |
| stale `spec:` pointing at a missing dir | 5 |

28 non-archive dirs holding a `research.md` are unreachable from any ticket — several are Context-B ad-hoc refines with no backing ticket at all, so they are correctly unreachable rather than a join defect.

**The three dead links** [feature_cards.html:226-228] read from `state.overnight.features[slug]`, straight out of `overnight-state.json` — `OvernightFeatureStatus` [state.py:106-108], not dashboard-computed.

- `feat.backlog_id` → `/tickets/{id}`. Clean.
- `feat.spec_path` → `/tickets/{backlog_id}#spec`. Clean, but needs `backlog_id` for the id.
- `feat.plan_path` → **cannot always resolve.** It is a bare lifecycle-relative path carrying a *slug*, while the route is keyed on an *id*. It resolves only through `backlog_id`, which [state.py:83] documents as legitimately `None` for features not sourced from numbered backlog files.

**Seed defect found.** `seed.py:145-158` writes `"backlog_id": slug` — a string — against `backlog_id: Optional[int]` [state.py:108]. Because the loader requires `\d{1,9}`, every "backlog #N" link would 404 under the seed corpus while working in a real deployment.

**Backend gating.** `resolve_backlog_backend(root) != "cortex-backlog"` gates every backlog read: lifespan [app.py:266], the ticket partial [app.py:470], the slow poll [poller.py:383]. Both new routes read `cortex/backlog/` and `cortex/lifecycle/` and must each gate inline and stand down rather than raise. No shared decorator exists; follow the one-liner-per-route pattern.

**Tests, four layers.** Route smoke [tests/test_routes_smoke.py]: `PARTIAL_ROUTES` (40-57), `PAGE_ROUTES` (62), `test_route_renders_200` (93-99), `test_missing_session_returns_404` (102-105) as the 404 template. Template/structural [tests/test_templates.py]: `TestStructuralElements` (293), `TestBacklogPanelBackendGate` (317) for the gate assertion. Data unit [tests/test_data.py]: `TestLoadTicketBody` (1586) is the direct sibling. Composite-loader precedent [tests/test_sessions.py]: `TestSessionDetail` (117).

**Seed gaps.** No seeded ticket has both a `spec:` field and a real dir carrying all four artifacts — #4 `seed-feature-delta` has `lifecycle_slug` and a real dir but no `spec:` [seed.py:1308]; #13 already covers "spec: present, file missing" [seed.py:1413]; #6/#7/#8 cover epic children.

## Rendering & Concurrency

**A real content-dropping bug blocks inline artifact rendering.** The sanitizer is render-then-filter: markdown first, then `_TicketBodySanitizer` walks the HTML keeping an allowlist and escaping text nodes. Fenced code, inline code and tables are handled correctly — 68 real artifacts checked for double-escaping artifacts, **zero found**, so the design's stated goal holds.

But Python-Markdown passes a bare `<word>` through as raw inline HTML, and the allowlist then drops it silently. Verified directly:

```
input     : cortex/lifecycle/<slug>/research.md
sanitized : cortex/lifecycle//research.md
```

No error, no fallback, no indication to the reader. Instrumented across all 694 canonical artifacts: **35 files (5.0%) drop at least one token**, 38 drops total, most common `path`, `url`, `slug`, `ts`, `topic`, `line`, `repo`, `id`. One real file — `offload-completemd-pr-state-routing-and/research.md` — additionally leaks a stray literal backtick into a rendered table cell.

**This is pre-existing, not new.** The same instrumentation over 451 ticket bodies finds drops in 5 files (1.1%). The bug is already live on #412's shipped reader; artifacts merely hit it ~4.5x more often, because the bare-placeholder convention is a prose habit of specs and plans rather than of ticket bodies.

**Cost profile — lazy is confirmed correct.** Per-artifact render (markdown + sanitize) over a 58-file spread: min 2.08ms, **median 7.48ms**, p90 12.70ms, max 17.45ms. Over the 10 largest artifacts: median 20.72ms, p90 24.46ms, **max 38.16ms**. Against the 77.8ms measured for rendering all five documents eagerly in one request, a lazy per-artifact fetch is 2-4x cheaper in the worst case and ~10x in the typical case.

**Concurrency — sync `def` is sufficient; no executor needed.** From installed source, `starlette/routing.py:request_response`:

```python
f = func if is_async_callable(func) else functools.partial(run_in_threadpool, func)
```

A sync `def` handler is dispatched to a worker thread automatically; an `async def` handler is awaited on the loop thread and nothing moves its body off it. Measured against a 50ms-tick background loop with a 300ms blocking handler: `async def` starved the tick to a **306ms** max gap; sync `def` held it at **52ms**.

**Every existing route is affected.** There are **zero `await` expressions anywhere in `app.py`** — all 17 routes are `async def` doing purely synchronous disk work, so each already blocks the shared loop for its render duration. No test asserts routes are coroutines. The all-`async def` convention is an unexamined default, not a load-bearing choice.

**`TICKET_BODY_MAX_CHARS` is the wrong cap for artifacts.** Artifact length over n=694: median 19,166, mean 20,637, p90 32,740, p99 51,068, **max 63,707**. Zero would truncate at 64,000 today — but the largest sits at **99.5% of the cap**. The constant was sized against a ticket-body corpus whose mean is ~3.6KB; the artifact mean is ~5.7x that. Today's 0% is a near-miss, not designed margin.

## Open Questions

- **Does the sanitizer placeholder-drop get fixed inside this ticket?** *Resolved: yes.* Shipping artifact rendering onto a path that silently deletes content from 1 in 20 artifacts would be knowingly shipping corruption, and this ticket is what multiplies the incidence 4.5x. The fix — reconstruct unrecognized `<...>`-shaped start tags as escaped literal text instead of dropping them — also repairs the shipped ticket-body path as a byproduct. If the spec phase judges this too large to carry, the fallback is to render artifacts as links only, since the ticket's Role cannot honestly be met over a lossy renderer.
- **Which join key does the artifact loader use?** *Resolved:* `spec:` dirname first, `lifecycle_slug` fallback probing both `cortex/lifecycle/<slug>` and `cortex/lifecycle/archive/<slug>`, then degrade to "no artifacts". Recovers 27 tickets over `spec:` alone and must tolerate the 5 stale `spec:` values.
- **What cap do artifacts get?** *Resolved:* their own constant, not `TICKET_BODY_MAX_CHARS`. Size it off the p99 (~51KB) with real headroom rather than the current near-miss.
- **Sync or async handlers for the new routes?** *Resolved:* plain `def`. Sufficient on measurement, requires no `run_in_executor`, and is what the framework prescribes for handlers that await nothing.
- **Does `feat.plan_path` get a link?** *Resolved:* only when `feat.backlog_id` is present; otherwise it stays inert, since no id exists to route on. The spec states this limit rather than implying all three links are fixed.
- **Do the other 16 `async def` routes get converted to sync `def`?** *Deferred* — out of scope. They are a pre-existing latent cost unrelated to this ticket's Why, converting them touches every route in the app with no test coverage asserting current behavior, and this ticket's own routes are correct on their own. Worth its own ticket citing the 306ms-vs-52ms measurement above.
- **Do the 28 artifact-bearing dirs unreachable from any ticket get a path?** *Deferred* — several are Context-B ad-hoc refines with no backing ticket, so they are correctly unreachable from an id-keyed route. A slug-keyed entry point is a different feature.

## Considerations Addressed

- **Epic "in place" vs a separate page** — addressed. #412's expandable row [triage_board.html:159-166] continues to satisfy in-place body reading; the page adds deep-linking and artifacts, which a morph-polled row structurally cannot host. Research confirms the board must link out to the new page so the two surfaces connect rather than diverge; the `/sessions/{id}` precedent shows a detail page is not a departure from the design.
- **The unowned `feature_cards.html` grievance** — addressed, and found to be partly unfixable as stated. `backlog_id` and `spec_path` resolve cleanly to the new page; `plan_path` carries a slug against an id-keyed route and resolves only when `backlog_id` is present [state.py:83]. The seed's string-vs-int `backlog_id` [seed.py:145-158] must be fixed alongside, or the links 404 in exactly the environment they are developed in.
