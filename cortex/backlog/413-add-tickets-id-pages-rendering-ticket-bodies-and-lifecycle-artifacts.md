---
schema_version: "1"
uuid: 112a84c9-3321-43f7-acc5-ef15c6b759d3
title: Add /tickets/{id} pages rendering ticket bodies and lifecycle artifacts
status: backlog
priority: medium
type: feature
created: 2026-07-21
updated: 2026-07-21
discovery_source: cortex/research/dashboard-command-station/research.md
parent: "410"
tags: ['dashboard-command-station', 'dashboard']
areas: ['dashboard']
blocked-by: 411
---
## Why

Tickets and their research/spec/plan/review artifacts cannot be read from the dashboard at all — feature cards render artifact references as inert placeholder links — so reading any of it means opening files in an editor or spending session tokens to have them summarized.

## Role

The deep-linkable reading surface for a single ticket: frontmatter as a badge strip, the markdown body rendered, lifecycle artifacts presented alongside, epic children linkified.

## Integration

Resolves one item from ticket-feed state, reads the body and lifecycle artifacts from disk per request following the sessions-detail page precedent (archive paths included), and renders through the one existing markdown pipeline. Board rows and epic-child links arrive here.

## Edges

- No sanitizer — contingent on the loopback bind, so the docs-reconciliation sibling ticket's bind-address and docstring correction lands no later than this ticket.
- Up to five markdown documents per request, measured near sixty milliseconds worst-realistic: lazy per-artifact loading or executor offload is a plan-phase decision, not an afterthought.
- Literal routes register before the id catch-all route.
- Renders generically off H2 structure — no per-body-generation branching; only the frontmatter badge strip and epic children lists are special-cased.
- Ships dedicated found and missing route tests backed by a seeded fixture file.
- Computed per-request, never cached in dashboard state.

## Touch points

- `cortex_command/dashboard/app.py:306-316` — sessions-detail route precedent (404-on-missing)
- `cortex_command/dashboard/data.py:938-946` — existing markdown pipeline
- `cortex_command/dashboard/templates/feature_cards.html:226-228` — the inert artifact links
- `cortex_command/dashboard/tests/test_routes_smoke.py:94-97` — missing-id test pattern