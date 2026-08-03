---
schema_version: "1"
uuid: c54dea44-b9f4-45aa-a2f6-e132bf79368e
title: Surface work parked by status, and unwedge the epics it blocks
status: backlog
priority: high
type: bug
created: 2026-08-03
updated: 2026-08-03
parent: "434"
tags: ['staged-epic-gate-tickets']
discovery_source: cortex/research/staged-epic-gate-tickets/research.md
---
## Why

An item parked by setting its status is invisible to the surfacing feature built for parked work, which inspects only tags. Worse, because that value sits in neither the terminal set nor the normalization map, a single parked child prevents its parent epic from ever closing — three epics in a sibling repo are held open this way with every other child finished.

## Role

Makes parked work visible where parked work is meant to be visible, and stops a parked child silently holding its parent open forever.

## Integration

Extends the deferred-item predicate the index renderer already consults, so a status-parked item annotates the same way a tag-parked one does. The parent-closing cascade reads the same normalized status, so the wedge clears without a separate fix.

## Edges

- Leaves two mechanisms expressing one concept — the tag and the status — and deliberately does not choose between them. Collapsing them is a migration that would have to reach repos this change cannot.
- Must not treat parked as terminal. A parked item is genuinely unfinished, and marking it terminal would close parents that legitimately have work outstanding.
- The schema currently directs authors to park via a non-eligible status, so the status-side spelling is sanctioned usage rather than author error.

## Touch points

- `cortex_command/backlog/generate_index.py:74-76` — the deferred predicate, tags-only today.
- `cortex_command/backlog/update_item.py:333` — the all-siblings-terminal check that the parked value never satisfies.
- Observed: wild-light epics 236, 284 and 263 sit open with complete-plus-parked children.
