---
schema_version: "1"
uuid: bab7b000-469c-4d8b-a3eb-ef0ec9d4d881
title: Make an epic's recorded outcome and membership reflect reality
status: complete
priority: medium
type: bug
created: 2026-08-03
updated: 2026-08-03
parent: "434"
tags: ['staged-epic-gate-tickets']
discovery_source: cortex/research/staged-epic-gate-tickets/research.md
---
## Why

An epic records success regardless of how its children actually ended — one reads as delivered although its final child was closed as won't-fix, and the commit that did it wrote that the story was complete. A closed epic silently absorbs children added afterwards, with no signal and no timestamp change; one absorbed a child thirty-nine days after closing. And because the epic map is built from a view that drops finished items, it currently sees one epic out of thirty-four, so none of this is observable.

## Role

Makes an epic's recorded outcome follow from its children's real outcomes, makes a late-arriving child audible rather than silent, and makes the epic corpus measurable at all.

## Integration

Feeds the epic map that triage and the dashboard both group by, and the parent-closing cascade that fires on any terminal child transition.

## Edges

- The parent write is triggered by a child and is read-modify-write with no compare-and-swap, so automatic reopening could undo a deliberate human close under concurrency. Recording and surfacing the late arrival is the safer shape.
- No vocabulary exists for an epic whose children ended differently from one another, so outcome derivation applies only where they agree; the mixed case stays out of scope.
- Must not change what the index treats as active. The epic map needs the fuller corpus; the ready list must not widen with it.
- The visibility arm is what makes the corpus measurable, so it gates any later claim about how often epics grow or close wrongly.

## Touch points

- `cortex_command/backlog/update_item.py:299-301` (bails on an already-closed parent) and `:337` (hardcodes the parent's outcome).
- `cortex_command/backlog/generate_index.py:157` — drops terminal items from the view the epic map reads.
- `cortex_command/backlog/build_epic_map.py:140-163` — needs type and parent on the fuller record set.
- Pinned by `tests/test_build_epic_map.py`, `tests/test_generate_backlog_index.py`, `tests/test_triage_render.py`.

## What shipped (2026-08-03)

**Visibility.** `collect_items` now builds the full record for every non-archived item, not just active ones, and `generate_index` writes `cortex/backlog/index-full.json` beside `index.json`. `build_epic_map` and triage read the full corpus; `index.json` still means "what is still open", so the ready list did not widen. Epics visible to the map went from **2 of 35 to 35 of 35** (183 children mapped). Index generation stays at ~0.09s because terminal items skip live phase detection and take their recorded `lifecycle_phase` verbatim.

**Outcome.** The cascade no longer hardcodes `complete`; `_derive_parent_outcome` normalizes the children's statuses and, where they all agree, closes the parent with that outcome. Mixed outcomes keep `complete` per the Edge above.

**Late arrival.** Both paths now speak: `create_item` warns when filing under an already-closed epic, and the cascade says so rather than returning silently when a child finishes under a closed parent. Neither reopens the parent — the read-modify-write race in the Edges is the reason.

**Regression found and fixed en route.** Widening the map exposed a latent bug pinned in `tests/test_triage_render.py` as a deliberate known hole: triage derived `child_ids` from *every* epic in the map, so a ready child of an epic not rendered in Block 1 was suppressed from Block 2 and appeared nowhere. With closed epics now in the map — and a closed epic never in the ready set — that would have hidden every ready child of every closed epic, which is exactly the late-arriving child this ticket exists to surface. `child_ids` is now derived only from the epics actually rendered.

## Measured gap (2026-08-03)

The census this ticket's visibility arm enables was run as soon as it landed. This repo: 0 outcome mismatches, 0 closed-but-growing, 0 parked-wedged. wild-light: epic 12 records `abandoned` with all children `complete`; epic 103 is `wontfix` with an open child; epics 236 and 284 are parked-wedged (#440).

**The Why's own example is out of scope by the Edges.** Six epics here — 49, 82, 113, 126, 303, 315 — record `complete` while carrying dropped children (82 has five `wontfix` children). That is the "reads as delivered although its final child was closed as won't-fix" case, and outcome derivation cannot touch it because those children disagree with each other. Filed as #442.
