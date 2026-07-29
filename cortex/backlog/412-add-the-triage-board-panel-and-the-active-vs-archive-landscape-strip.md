---
schema_version: "1"
uuid: c5abd455-85fa-457b-8087-c99ccfd55566
title: Add the triage board panel
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

## Update — reconciled at spec time (#412)

Research and critical review falsified five claims made above and dropped the second of the two
surfaces this ticket bundled. The original text is left intact as the record of what was believed at
authoring time; this section states what replaced it.

1. **"170 of 177 top-level lifecycle dirs" does not reproduce.** The Why's headline count is wrong on
   both terms — measured 178 top-level lifecycle dirs, of which 167 match the archiver predicate. The
   direction of the observation survives; the figure does not.

2. **The "morning-report flooding" precedent was already fixed at the consumer.** The Why cites #294,
   which is `status: complete`: its session-scope gates at `report.py:924` and `report.py:1341` stop
   the unswept mass from reaching the report. The cited operator noise is therefore historical, not
   standing, and cannot motivate a new surface.

3. **"No standing sweep" is false.** `cortex/lifecycle/archive/.archive-manifest.jsonl` carries an
   entry dated 2026-07-27. Further, 111 of its 145 entries landed inside one 7-minute window on
   2026-04-27, which `justfile:191` documents as an incident where `just lifecycle-archive --dry-run`
   ran destructively — so the archive the strip would have reported against is largely residue from
   that incident rather than evidence of accumulation.

4. **The Integration's "active/archive split the feed already computes" is a *backlog* split.** It is
   8 active / 0 archived in this repo and describes ticket state, not lifecycle directories; it could
   never have sourced a lifecycle landscape. The claim is moot now that the surface is dropped.

5. **The Edges list inverts #306.** It names "standalone" among what #306 rejected. #306:53 blessed
   the opposite — "a gitignored, regenerate-on-demand, standalone index" over indexing "every live
   lifecycle" — and required that the settled-corpus question be reconsidered *jointly* with the
   archive verb (B4), since "keep history + index it" vs "archive it" is one design decision.

Additionally, the touch point `justfile:150-152` resolves to the training-deck server recipe, not the
archive recipe; `lifecycle-archive` begins at `justfile:184`.

**The active-vs-archive landscape strip is dropped from this ticket**, and the `title:` above was
amended to match. Its evidence did not survive the corrections in 1–3: the noise it cited is fixed at
the consumer, archiving is not standing down, and the corpus it would report against is `--dry-run`
residue. Beyond that, its third term would count conformance with a shipped instruction
(`skills/build/references/complete.md:53`: "Preserve `cortex/lifecycle/{slug}/` as project history"),
and it is un-actionable in consumer repos — none of the three sampled has a `justfile` at all, so
`lifecycle-archive` does not exist there. #306's revival clause requires the settled-corpus question
be taken up with the archive verb in a paired ticket rather than split from it. This ticket is the
board: the panel, its data joins, badge vocabulary, and tests. No lifecycle-directory scan and no
`lifecycle_landscape` state field ship with it.