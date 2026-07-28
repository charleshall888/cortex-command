---
schema_version: "1"
uuid: 47ae0d5b-f2bc-42b1-9bd5-97b3409915f5
title: Add the dashboard ticket feed
status: complete
priority: high
type: feature
created: 2026-07-21
updated: 2026-07-27
discovery_source: cortex/research/dashboard-command-station/research.md
parent: "410"
tags: ['dashboard-command-station', 'dashboard']
areas: ['dashboard', 'backlog']
lifecycle_phase: complete
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

## Update — reconciled at spec time (#411)

Research and adversarial review falsified three claims made above. The original text is left intact
as the record of what was believed at authoring time; this section states what replaced it.

1. **There is no shared parse boundary, so no correction is inherited.** Role and Integration assert
   a single boundary whose fix three readers pick up. Six independent frontmatter parsers were
   verified instead — `generate_index.py:46`, `resolve_item.py:76`, `load_parent_epic.py:113`,
   `overnight/backlog.py:232`, and two hand-rolled regex scans at `dashboard/data.py:971,1028`.
   Nothing inherits anything. Unifying them is an explicit non-goal of the spec.

2. **The warn guard is not built.** Role and Edges promise a boundary that warns loudly on
   unrecognized blocker-key variants. A runtime guard in a surface that ships to other repos polices
   a corpus whose maintainer never reads the log, which the shipped-surfaces rule forbids; a
   corpus test in `tests/` is not in the wheel and so is unreachable from any consumer repo. Neither
   ships. The one live occurrence is corrected directly in `cortex/backlog/230-*.md:14` and is inert
   — that item is terminal and skipped before the key is read.

3. **The seed-ID range position was reversed, to no filter at all.** Edges promised an explicit
   position on the reserved range before the board renders live data. The operator resolved it on
   2026-07-21 the other way: no `_BACKLOG_UUIDS` import, no `dashboard-seed` tag filter, no 990–999
   ID-range filter. The feed renders seed fixtures exactly as every other panel already does. The
   `#231` tag-collision hazard that motivated filtering was checked and found wrong — #231 is
   `status: complete` and is dropped before its tags are read.

Consequently the second half of this ticket collapsed from a parse-boundary change plus a guard to
a single frontmatter line, and the `title:` above was amended to match what the work actually is.
The Why paragraph's account of the lossy blocker key remains accurate as written; what it does not
convey is that the loss is currently unobserved in practice.