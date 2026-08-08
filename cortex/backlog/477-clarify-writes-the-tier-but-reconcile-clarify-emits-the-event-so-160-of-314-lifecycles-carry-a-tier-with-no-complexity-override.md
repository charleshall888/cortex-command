---
schema_version: "1"
uuid: 4cdc489b-1d76-4de5-8d26-e7a34ebfe834
title: Clarify writes the tier but reconcile-clarify emits the event, so 160 of 314 lifecycles carry a tier with no complexity_override
status: backlog
priority: medium
type: bug
created: 2026-08-08
updated: 2026-08-08
tags: ['lifecycle', 'tiering', 'telemetry']
areas: ['lifecycle']
---
## Why

`#450` states its detector plainly: a tier at `backlog` status is not the signal, *"absence of a corresponding event is."* That detector cannot be used as written, and the cause is in the sanctioned in-lifecycle path rather than in any bypass.

`cortex-update-item --complexity` writes frontmatter and emits nothing. Refine writes the tier back at **Step 2 (Clarify)**, but the only `complexity_override` emitters are `cortex-lifecycle-event complexity-override` and `refine.py`'s `reconcile-clarify`, which runs at **Step 4 (Specify entry)**. Every lifecycle that stops before Specify — and every one whose tier was never re-assessed after research — therefore carries a tier with no event, having been assessed correctly.

Measured 2026-08-08 over `cortex/lifecycle/**/events.log` including `archive/`: **314 lifecycles carry a `lifecycle_start`; 154 also carry a `complexity_override`; 160 do not.** The detector is ~51% false-positive on properly-tracked work alone, before any bypass is considered.

This is the finding that `#459` misattributed to dev rule 4. Rule 4's footprint is ~11 tickets; this is 160, and it is the harness's own path.

## Role

Make "a tier with no corresponding event" mean something, so `#450`'s detector is usable — or retire the detector as unbuildable and say so in `#450`.

## Integration

The natural capture point is Clarify's write-back itself: the moment the tier is decided is the moment it could be recorded, rather than deferring to a reconcile step that half of lifecycles never reach. `refine.py`'s `reconcile-clarify` already appends `to`-keyed `complexity_override` rows and owns the closed clause-tag vocabulary for `reason`, so the emitter exists and the question is where it fires, not whether it needs building.

Weigh against Deletion bias before adding an emission: `#447` (wontfix) concluded the simple bucket is unmeasurable, and no consumer currently reads a backlog `complexity:` except `refine.py:141`'s seed. If nothing reads the event either, retiring `#450`'s detector claim is the cheaper answer and should be priced first.

## Edges

- Do not backfill the 160 historical lifecycles. Their tiers were assessed; only the record's shape is inconsistent, and a retroactive sweep over unknown provenance is the unbounded clause `#459` was trimmed of.
- A Clarify-time emission fires on lifecycles that stop at `simple` and never proceed, which is the majority case — check that this does not just move the noise rather than remove it.
- `#450` remains wontfix on its own (filing-time) grounds regardless of what lands here; this ticket touches only its detector sentence.

## Touch points

- `cortex_command/refine.py:409` — the `complexity_override` row, emitted at reconcile-clarify
- `skills/refine/SKILL.md` Step 2 vs Step 4 — where the tier is written vs where the event fires
- `cortex_command/backlog/update_item.py:625` — writes `complexity:`, emits nothing
- `cortex/backlog/450-*.md` — the detector sentence this either rescues or retires
