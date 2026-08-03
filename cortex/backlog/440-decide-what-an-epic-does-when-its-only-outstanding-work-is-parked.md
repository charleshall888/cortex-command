---
schema_version: "1"
uuid: 249c5e09-d2ad-4d38-bc2e-40240ad60237
title: Decide what an epic does when its only outstanding work is parked
status: complete
priority: medium
type: feature
created: 2026-08-03
updated: 2026-08-03
parent: "434"
tags: ['staged-epic-gate-tickets']
complexity: simple
---
## Why

A child parked by status is non-terminal by design, so the all-siblings-terminal check never fires and its parent epic stays open forever. Two wild-light epics are held this way with every other child finished — 236 (parked children 247, 257) and 284 (286, 287). Splitting this from #436 because the premise recorded there was wrong: normalization cannot clear the wedge on its own.

## Role

Decides and implements what an epic should do when the only work outstanding is parked, without making parked read as terminal anywhere else.

## Integration

Rides the all-siblings-terminal check in the parent-closing cascade, which fires on any terminal child transition and is the single place the parent's status is derived from its children's.

## Edges

- Must not add parked to the terminal set. Every other reader consults that set, and widening it would make parked work read as finished in the index, in triage, and in readiness.
- The cascade compares raw frontmatter, not normalized status — `update_item.py:33` imports `TERMINAL_STATUSES` without `normalize_status`. Any rule added here must decide explicitly whether to normalize first, and #435's alias fix does not reach this code path.
- The parent write is read-modify-write with no compare-and-swap, so a rule that closes automatically inherits the concurrency hazard #438 already flags on the same function.
- Closing an epic whose remaining work is merely parked may be the wrong answer; surfacing it as "closeable except for parked children" is the alternative and needs no write.

## Touch points

- `cortex_command/backlog/update_item.py:333` — the all-siblings-terminal check the parked value never satisfies.
- `cortex_command/backlog/update_item.py:300` — the already-closed-parent bail, same raw read.
- Census method: group children by parent, exclude epics whose non-terminal children are not all parked.

## Decision

**Surface, do not auto-close.** When every non-terminal child of an epic is parked,
`_check_and_close_parent` now prints a note naming those children and still returns
`None`; the epic is not written.

Auto-closing was rejected because it would make deliberately deferred work read as
delivered — the exact class of defect epic #434 exists to remove. Surfacing also sidesteps
this ticket's third Edge: no write means no exposure to the read-modify-write race, and it
matches the shape already used one branch above for the already-closed-parent case.

Parked-ness is read through `generate_index._is_deferred`, so both sanctioned spellings
(`status: deferred` and `tags: [deferred]`) count and the vocabulary stays in one place.
`TERMINAL_STATUSES` is untouched.
