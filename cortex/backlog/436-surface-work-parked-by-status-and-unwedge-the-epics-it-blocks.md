---
schema_version: "1"
uuid: c54dea44-b9f4-45aa-a2f6-e132bf79368e
title: Surface work parked by status
status: complete
priority: high
type: bug
created: 2026-08-03
updated: 2026-08-03
parent: "434"
tags: ['staged-epic-gate-tickets']
discovery_source: cortex/research/staged-epic-gate-tickets/research.md
---
## Why

An item parked by setting its status is invisible to the surfacing feature built for parked work, which inspects only tags. The schema itself directs authors to park this way, so the surfacing feature misses the spelling its own documentation recommends.

## Role

Makes parked work visible where parked work is meant to be visible, regardless of which of the two sanctioned spellings its author used.

## Integration

Extends the deferred-item predicate the index renderer and triage already consult, so a status-parked item annotates and suppresses the same way a tag-parked one does.

## Edges

- Leaves two mechanisms expressing one concept — the tag and the status — and deliberately does not choose between them. Collapsing them is a migration that would have to reach repos this change cannot.
- Must not treat parked as terminal. A parked item is genuinely unfinished, and marking it terminal would close parents that legitimately have work outstanding.
- The schema currently directs authors to park via a non-eligible status, so the status-side spelling is sanctioned usage rather than author error.
- Non-goal: unwedging the epics a parked child holds open. That was originally scoped here on a mistaken premise (see below) and is now #440.

## Touch points

- `cortex_command/backlog/generate_index.py:74-76` — the deferred predicate, tags-only today.
- `skills/backlog/references/schema.md:11` — the line directing authors to "park via a non-eligible `status` instead".
- Observed: wild-light carries 8 `status: deferred` items the tag-only predicate treated as unparked.

## Correction (2026-08-03)

Two claims in the original body were wrong and have been removed:

- **"The parent-closing cascade reads the same normalized status."** It does not. `update_item.py:33` imports `TERMINAL_STATUSES` but never `normalize_status`; the checks at `:300`, `:333` and `:470` compare raw frontmatter. #435's Edges states the opposite and is the correct one.
- **"Three epics ... are held open this way."** Two. A full census of wild-light finds only epics 236 (children 247, 257) and 284 (children 286, 287) held open *solely* by parked children. Epic 263 has six `backlog` children and is genuinely open.

It also follows that normalization alone cannot clear the wedge: this ticket's own second Edge requires parked to stay non-terminal, and a non-terminal sibling blocks the close by construction. Unwedging needs an explicit rule, which is #440.
