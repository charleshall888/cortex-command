---
schema_version: "1"
uuid: 94d53134-9112-4416-99fb-a052faef07c8
title: Overhaul the dashboard into a read-only project command station
status: complete
priority: medium
type: epic
created: 2026-07-21
updated: 2026-08-06
discovery_source: cortex/research/dashboard-command-station/research.md
tags: ['dashboard-command-station', 'dashboard']
areas: ['dashboard']
---
## Why

Running the project currently means stitching together four disjoint, ephemeral surfaces — a triage dump re-generated in a token-metered session each time it is consulted, a three-line statusline, a session-start context injection, and the overnight status/morning report — while the persistent dashboard shows the backlog as a single aggregate distribution bar. Tickets, blockers, deferrals, epic groupings, and lifecycle artifacts cannot be seen or read anywhere persistent; the dashboard's feature cards render artifact references as dead placeholder links.

## Role

Parent scope for the read-only command-station overhaul that makes the existing dashboard the one persistent, zero-token place to see what is in progress, ready, blocked, or deferred — and to read any ticket and its lifecycle artifacts in place.

## Integration

Children sequence: ticket feed (with upstream blocker-key hygiene) first, then the triage board with the landscape strip, then the ticket reader, with seed-fixture enrichment and docs/requirements reconciliation alongside. Every backlog-reading child sits behind the existing backend gate.

## Edges

- The dashboard remains a read-only observability surface: no browser-side mutation, no index-cache writes from the read path, no auth changes.
- No npm or build tooling enters the stack; file-based state only.
- Each child names its own specific evidence in its Why per the front-door evidence bar.

## Touch points

- `cortex/research/dashboard-command-station/research.md` — full research artifact (decision records, measured bounds, helper-shape verification)
- `cortex/research/dashboard-command-station/brief.md` — approval-gate brief