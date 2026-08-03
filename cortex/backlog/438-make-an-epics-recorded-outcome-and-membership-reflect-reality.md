---
schema_version: "1"
uuid: bab7b000-469c-4d8b-a3eb-ef0ec9d4d881
title: Make an epic's recorded outcome and membership reflect reality
status: backlog
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
