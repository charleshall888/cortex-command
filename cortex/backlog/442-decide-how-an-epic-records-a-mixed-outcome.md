---
schema_version: "1"
uuid: 93eb087a-438d-4462-ad99-c15ab2c6b097
title: Decide how an epic records a mixed outcome
status: complete
priority: medium
type: spike
created: 2026-08-03
updated: 2026-08-03
parent: "434"
tags: ['staged-epic-gate-tickets']
complexity: simple
---
## Why

Six epics in this repo record `complete` while carrying a child that was dropped — epic 82 has five `wontfix` children, 113 has three, 303 has two. This is the exact damage #438's Why described ("an epic reads as delivered although its final child was closed as won't-fix"), and #438 could not address it: its outcome derivation applies only where every child agrees, and these are mixed by definition. The count is now measurable because #438's visibility arm landed; before it, one epic of thirty-five was visible.

## Role

Decides how an epic whose children ended differently from one another should record its outcome, and implements that decision.

## Integration

Rides the same parent-closing cascade #438 changed — `_derive_parent_outcome` already receives the full sibling status list and currently discards the mixed case by returning `complete`.

## Edges

- The blocker is vocabulary, not mechanism. There is no status meaning "delivered, with scope dropped", so this ticket either introduces one, records the detail somewhere other than `status`, or rules that `complete` is correct and the information belongs in the epic body.
- Introducing a status value is expensive: it must reach `TERMINAL_STATUSES`, the alias map, the doc table, the pickup gate's non-intersection invariant, and every consumer repo. #434's Edges rule out new status values, so a successor to that decision would be needed.
- The cheap alternative is a report, not a field: the census that now runs over `index-full.json` can list mixed-outcome epics without changing what any epic records.
- Retroactive correction is a separate question from what future closes do. The six existing epics are already closed and nothing will revisit them.

## Touch points

- `cortex_command/backlog/update_item.py` — `_derive_parent_outcome`, the `return "complete"` that discards the mixed case.
- Observed here: epics 49, 82, 113, 126, 303, 315.
- `cortex/backlog/index-full.json` — the full-corpus view that makes the census possible.

## Decision

**Keep `complete`; report the dropped children.** No new status value. `_derive_parent_outcome`
still collapses a mixed set to `complete`, but the close now emits a note naming each child
that did not ship and its status.

Introducing a vocabulary for "delivered, with scope dropped" was rejected on this ticket's
own second Edge — it would have to reach `TERMINAL_STATUSES`, the alias map, the doc table,
the pickup gate's non-intersection invariant, and every consumer repo, and #434's Edges rule
out new status values. The note carries the same information at the one moment it is known
for free.

Retroactive correction of the six already-closed epics (49, 82, 113, 126, 303, 315) stays out
of scope, as the ticket's fourth Edge states.
