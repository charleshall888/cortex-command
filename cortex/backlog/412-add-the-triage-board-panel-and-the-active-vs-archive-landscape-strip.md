---
schema_version: "1"
uuid: c5abd455-85fa-457b-8087-c99ccfd55566
title: Add the triage board panel and the active-vs-archive landscape strip
status: refined
priority: medium
type: feature
created: 2026-07-21
updated: 2026-07-27
discovery_source: cortex/research/dashboard-command-station/research.md
parent: "410"
tags: ['dashboard-command-station', 'dashboard']
areas: ['dashboard']
blocked-by: 411
complexity: complex
criticality: high
spec: cortex/lifecycle/add-the-triage-board-panel-and/spec.md
---
## Why

Deciding what to pick up means re-running the dev-skill triage in a session every time it is needed; the dashboard's only backlog surface is an aggregate bar with no rows, so ready-vs-blocked-vs-deferred state and epic structure are invisible at a glance. The settled side of the corpus is equally invisible: 170 of 177 top-level lifecycle dirs have already ended complete with no standing sweep — the one-time archive sweep re-accumulated within two and a half months, and the unswept mass has produced real operator noise before (morning-report flooding).

## Role

The persistent "what should I work on, what's blocked and why" panel — epic-grouped children with refined/blocked/deferred badges plus a flat ready list, degrading to a plain list when the active set is small — paired with the honest one-line home for the settled-corpus story: active vs archived vs completed-but-unswept.

## Integration

Both surfaces are pure renderings of ticket-feed state on their own slow trigger: eligibility and epic grouping come from the feed's imported helpers, display labels from the feed's joins, and the strip from the active/archive split the feed already computes. Every board row links into the ticket reader.

## Edges

- Intra-ticket order: board first, strip second.
- Read-only: no drag affordances implying write-back the surface cannot perform.
- Semantic sections and lists; no grid-widget ARIA pattern.
- No dependency graph at current edge density; blocked state renders as badge plus reason.
- Renders honestly at both extremes: near-empty (no padded chrome) and a few-hundred-item active set.
- The backlog-status badge vocabulary is new; the feature-status badge maps stay untouched.
- Keeps the three deferred vocabularies (backlog status, backlog tag, overnight run outcome) visually distinct.
- The strip stays in the abandoned cross-lifecycle-index ticket's blessed fallback shape: dashboard-internal, in-memory, no persisted artifact, no morning-report wiring, no auto-archiver — scope creep toward a committed or standalone index re-proposes exactly what that ticket rejected.

## Touch points

- `cortex_command/dashboard/templates/base.html:2151-2208` — panel section registration
- `cortex_command/dashboard/DESIGN.md:83-92` — data-table macro forward-reference
- `cortex_command/dashboard/tests/test_routes_smoke.py:40-51` — PARTIAL_ROUTES list
- `cortex_command/backlog/triage.py` (`render`) — decision-information baseline to meet (the rules moved here from the retired dev-skill triage reference)
- `cortex/backlog/306-generate-a-cross-lifecycle-phase-index-wired-to-morning-review.md:44-53` — close-out constraints the strip honors
- `justfile:150-152` — manual lifecycle-archive recipe (the absent standing sweep)