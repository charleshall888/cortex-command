---
schema_version: "1"
uuid: 0440fa4a-dd66-436d-9f9f-07910e87163a
title: 'dev rule 4 writes an unearned complexity, reopening #450 on the harness''s own happy path'
status: complete
priority: medium
type: bug
created: 2026-08-06
updated: 2026-08-08
tags: ['lifecycle', 'tiering', 'skills']
areas: ['skills']
complexity: simple
criticality: high
---
## Why

`skills/dev/SKILL.md:17` (Step 1 rule 4) instructed, for any simple change: implement it here, commit, and close the item with

    cortex-update-item {slug} --status complete --complexity simple

That writes a `complexity:` into backlog frontmatter with no lifecycle directory and no assessment event. The write has **no reader**: the sole consumer of a backlog `complexity:` value in wheel code is `cortex_command/refine.py:141` (the refine seed), which is unreachable for a ticket already at `status: complete`, and silently seeds `"simple"` when the value is absent — so removing the write turns nothing red. The dashboard reads `complexity` from *events* (`complexity_override`, pipeline dispatch), never from frontmatter. Under `project.md`'s Deletion bias the presumption of removal is undischarged.

**Correction — this ticket's original Why was wrong on all three of its evidence items.** Re-measured 2026-08-08 during refine:

- *"154 of 303 tickets carrying an assessed `complexity:` have no `lifecycle_slug` at all."* Replicates as 159/318, but `lifecycle_slug` absence is a field-era artifact, not assessment bypass: **134 of those 159 carry a `spec:` field**, i.e. they went through a lifecycle. Restricting to tier + no `spec:` + no lifecycle directory gives **26 of 317 (8%)**, not ~51%.
- *"No assessment event can be located for any of them."* False for the majority — **72 of the 134** have a `complexity_override` row in the `events.log` at their own spec's directory.
- *"The channel is dev rule 4"* / *"rule 4 and `cortex-update-item` are the only reachable writers."* Rule 4 emits only `--complexity simple`, so it cannot have produced the **127 `complex`** values in that population. A third writer is demonstrable: commit `c8110de5` ("Relocate cortex-command artifacts under cortex/ umbrella") introduced the tier on 6 of the 26 by bulk file move. Rule 4's true footprint is ~11 tickets, all from 2026-08-03 on.

The claimed contamination direction does not exist either: the no-`lifecycle_slug` population is 16.4% `simple` and the with-`lifecycle_slug` population 15.7% — within 0.7 points.

`#450`'s wontfix therefore stands. Its evidence was `complexity: complex` + `criticality: high` written **at filing time** on a `status: backlog` ticket; rule 4 writes `simple` alone, at close time, with no criticality. The two shapes differ on every axis #450 named, so this ticket's ground for reopening it is refuted rather than merely unproven.

**The real defect this surfaced is separate and larger.** `cortex-update-item --complexity` emits no event, and refine's Step 2 write-back runs at Clarify while `complexity_override` is only emitted at Step 4 (`reconcile-clarify`). So "tier present, no event" is produced by the sanctioned in-lifecycle path too: **160 of 314 lifecycles carrying a `lifecycle_start` have no `complexity_override` event**. `#450`'s stated detector is ~51% false-positive on properly-tracked work, independent of rule 4. Filed separately.

## Role

Stop rule 4 writing a tier that has no reader, so the write does not have to be made attributable at all.

## Edges

- Rule 4's judgment is not the problem — it fires *after* an agent has read the ticket and the repo. Recording it is the problem, because nothing reads the record.
- Do not add `--complexity` to the filing verb. `#450`'s standing warning still applies and is unaffected.
- `#447` (wontfix) already concluded the simple bucket is unmeasurable, so dropping the write forfeits no instrument that exists.

## Resolution

Removed `--complexity simple` from rule 4 (`skills/dev/SKILL.md:17`), leaving `--status complete`. `#450` stays wontfix. The `complexity_override` timing gap is `#477`.

## Touch points

- `skills/dev/SKILL.md:17` — rule 4, the write
- `cortex_command/refine.py:141` — the sole reader of a backlog `complexity:`, unreachable at `status: complete`
- `cortex/lifecycle/the-tier-seed-is-a-placeholder/research.md` — origin of the 154/303 figure corrected above
