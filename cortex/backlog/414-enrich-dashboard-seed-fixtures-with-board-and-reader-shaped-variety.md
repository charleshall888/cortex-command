---
schema_version: "1"
uuid: 3d7da067-8be9-4a37-98b9-70ab47ed7a4d
title: Enrich dashboard seed fixtures with board- and reader-shaped variety
status: in_progress
priority: medium
type: chore
created: 2026-07-21
updated: 2026-07-28
discovery_source: cortex/research/dashboard-command-station/research.md
parent: "410"
tags: ['dashboard-command-station', 'dashboard']
areas: ['dashboard', 'backlog', 'tests', 'docs']
complexity: complex
criticality: high
spec: cortex/lifecycle/enrich-dashboard-seed-fixtures-with-board/spec.md
---
## Why

The five seeded backlog items carry one-line placeholder bodies and no blockers, parents, tags, or lifecycle links, so neither a ticket board nor a ticket reader can be visually developed or judged against fixtures — every command-station state the new views must render has zero fixture coverage today.

## Role

A fixture vocabulary wide enough to exercise every command-station state: rich markdown bodies (headings, fences, tables), a blocked chain, an epic with children, both deferral forms, and lifecycle-linked slugs whose artifact files exist.

## Integration

Extends the existing seed writer and its symmetric cleaner; couples to the ticket feed's reserved-ID policy so seeded items and live data stay distinguishable.

## Edges

- Stays inside the reserved seed ID range.
- Writer/cleaner symmetry with the existing delete-guard convention is preserved.
- Non-goal: per-phase test additions — those belong to each feature ticket, not here.

## Touch points

- `cortex_command/dashboard/seed.py:1010-1073` — backlog item fixtures
- `cortex_command/dashboard/seed.py:470-589` — lifecycle feature-file writer to cross-link
- `cortex_command/dashboard/seed.py:1221-1227` — reserved-range cleaner