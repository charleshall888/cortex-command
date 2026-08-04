---
schema_version: "1"
uuid: dfab1253-db48-4eb7-ad1c-16edf64b8ef1
title: complexity_override records no rationale, and the seeded simple tier is indistinguishable from an assessed one
status: complete
priority: medium
type: feature
created: 2026-08-04
updated: 2026-08-04
tags: ['lifecycle', 'tiering', 'auditability']
areas: ['lifecycle']
---
## Why

Every tier decision is recorded as an outcome with no reasoning, so tiering is unauditable without re-reading the whole artifact set.

`complexity-override` and its `criticality-override` sibling both accept only `--from` and `--to` (`cortex_command/lifecycle_event.py`, subcommand table). The emitted event is `{"event": "complexity_override", "from": ..., "to": ..., "gate": "clarify_reconcile"}` — no "why". The justification for the call exists only implicitly, scattered across `research.md` and `spec.md`.

Measured cost: auditing nine post-split tier calls on a consumer project required a full read of nine `research.md`/`spec.md`/`plan.md` sets to reconstruct reasoning that the assessment had already done and discarded. Every override written today degrades the dataset any distribution evaluation will need (see the tier-distribution instrument ticket).

A second, compounding defect: `lifecycle_start` seeds `tier: "simple"` as the **rank-floor default**, deliberately, so the monotonic-up-only reconcile ratchet stays inert on an absent value (`e3ee3b4c` states this explicitly for `_read_backlog_frontmatter`). That default is a placeholder, not a judgment — but it is indistinguishable from one in the log. The observable consequence is that *every* escalation reads `simple -> complex`, even when the assessment never considered `simple`. Verified across four consecutive lifecycles in a consumer corpus: all four start `tier: simple, criticality: medium`, and three jump straight to `complex`. On that record, `moderate` looks skipped whether or not it was ever weighed.

## Role

Make the tier record self-explaining: an override carries the one-line reason it was taken, and a seeded placeholder is distinguishable from an assessed value.

## Integration

The subcommand table in `lifecycle_event.py` maps each verb to its accepted flags; adding an optional field there is additive and does not change the reducer, since `cortex-lifecycle-state` reduces on `from`/`to` and would ignore an extra key. The `simple` seed is written by the `lifecycle_start` path, which reads backlog frontmatter that is legitimately absent at that point.

## Edges

- The rationale must be optional-but-prompted, not required. A hard-required flag invites a filler string, which is worse than absent — it looks like evidence.
- Do **not** move the reconcile default off the rank floor. `e3ee3b4c` records why: any higher default ratchets every legitimately-simple feature up one tier the first time reconcile runs. The fix is to make the seed *legible* (e.g. an explicit `seeded: true` or a distinct sentinel), not to change its value.
- One line, not a paragraph. The full argument belongs in `research.md`; this is the pointer that makes the artifact findable.
- Retrofitting reasons onto historical overrides is out of scope and would be fabrication — this improves the record going forward only.

## Touch points

- `cortex_command/lifecycle_event.py` — subcommand table; `criticality-override` / `complexity-override` entries take only `--from`/`--to`
- `plugins/cortex-core/skills/refine/references/clarify.md` §5.2 — where the reasoning is produced and currently discarded
- `plugins/cortex-core/skills/build/SKILL.md` — `cortex-lifecycle-state` reduction semantics (extra keys ignored)
- Commit `e3ee3b4c` — records why the reconcile default must stay at the rank floor
