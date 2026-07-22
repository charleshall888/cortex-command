---
schema_version: "1"
uuid: 47ae0d5b-f2bc-42b1-9bd5-97b3409915f5
title: Add the dashboard ticket feed with upstream blocker-key hygiene
status: in_progress
priority: high
type: feature
created: 2026-07-21
updated: 2026-07-22
discovery_source: cortex/research/dashboard-command-station/research.md
parent: "410"
tags: ['dashboard-command-station', 'dashboard']
areas: ['dashboard', 'backlog']
lifecycle_phase: research
lifecycle_slug: add-the-dashboard-ticket-feed-with
complexity: complex
criticality: high
spec: cortex/lifecycle/add-the-dashboard-ticket-feed-with/spec.md
---
## Why

The dashboard already re-reads the whole backlog every thirty seconds yet keeps only status counts and title strings, so no view can show a single ticket's priority, epic, blockers, or deferral — that picture exists only in session commands that cost tokens every time they run. And the blocker data such a feed would surface is silently lossy today: one live backlog file records its blocker under the underscore key spelling while every reader keys on the hyphenated form, so the recorded dependency vanishes from the generated index, readiness resolution, and the overnight scheduler with no warning.

## Role

The single in-memory snapshot of backlog truth — active items, epic map, readiness partition, deferred markers, and blocked-why joins — that every command-station view reads, standing on a parse boundary that warns loudly on unrecognized blocker-key variants instead of dropping them.

## Integration

Fixes the stray key and adds the warn guard at the shared parse boundary first (index generation, the readiness partition, and the overnight ready-filter all inherit the correction), then imports the same producer helpers the CLI verbs use inside the slow poll's existing backend-gate block. Retains the two existing counts/titles scans, whose terminal-corpus consumers the active-only helpers cannot serve. Never writes the index cache.

## Edges

- Intra-ticket order: the hygiene fix and warn guard land before the feed wires in.
- Strictly read-only: no writes into the cortex tree from the read path; warn, don't auto-rewrite — frontmatter mutation stays with writer verbs.
- Stands down under non-local backlog backends, matching the existing gate discipline.
- Helper returns are label-poor by design (no titles for terminal items, tags invisible to readiness, fixed-literal blocker reason): display labels are feed-layer joins, not helper re-implementations.
- Takes an explicit position on the reserved seed-ID range before the board renders live data.
- Breaks if the collector's return shape changes — the coupling is API-level and no schema-stability promise exists yet.
- Non-goal: widening the frontmatter-quote allowlist.

## Touch points

- `cortex/backlog/230-release-gate-empirical-from-claude-session-smoke-test-for-228-daytime-dispatch.md:14` — the underscore-key file
- `cortex_command/backlog/generate_index.py:85-146,197` — collect_items and the hyphen-key read
- `cortex_command/overnight/backlog.py:328` — second hyphen-key reader
- `cortex_command/dashboard/poller.py:62-119,353-384` — DashboardState and the backend-gated slow poll
- `cortex_command/backlog/build_epic_map.py:93-173` — epic map helper
- `cortex_command/backlog/readiness.py:89-213` — readiness partition and reason strings