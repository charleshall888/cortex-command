---
schema_version: "1"
uuid: 53ea7e79-7754-4708-ae4f-ebeae99abdc0
title: No sound join between tickets and lifecycles, so no tier analysis is currently trustworthy
status: backlog
priority: medium
type: bug
created: 2026-08-06
updated: 2026-08-06
tags: ['lifecycle', 'backlog', 'measurement']
areas: ['lifecycle']
---
## Why

Four independent defects mean any analysis correlating a backlog ticket with its lifecycle is computed over a non-random third of the corpus, at best. Measured across `cortex-command`, `wild-light`, `pixel-art-generator`, `gaggimate-barista`, `Team-Builder-Bot`:

- `lifecycle_slug` is populated on **153 of 449** tickets (34%). Where present it resolves cleanly once `archive/` is included, so the field works — it is simply not written most of the time.
- **200 of 353** lifecycle directories have no ticket pointing at them.
- The reverse join is impossible: across 185 `lifecycle_start` rows the key set is `{ts, event, feature, tier, criticality, schema_version, entry_point, seeded, note}` — **no backlog key exists**.
- **78 lifecycle event logs** (14 wild-light, 61 cortex-command, 3 gaggimate) are in a **legacy YAML format** that the JSONL reader every current analysis uses cannot parse. They are silently excluded from every count. Nobody has measured what is in them.

This is not hypothetical harm. It has already produced wrong conclusions twice: `#451`'s evidence was invalidated post-hoc as era-mixed and placeholder-contaminated, and `#453`'s headline figure (186/211) proved unreproducible — the corrected cohort was n=21. `cortex/lifecycle/nearly-all-work-is-rated-complex/research.md:114` states the un-conditioned measurement "should gate any further tier work rather than block this ticket." It has not been taken, because it cannot be taken on this corpus.

## Role

Make ticket↔lifecycle attribution sound enough that a tier question can be answered once, correctly, instead of re-litigated each time someone measures.

## Integration

Roughly independent pieces, each useful alone:

- Write `lifecycle_slug` back to the ticket reliably at lifecycle start, rather than leaving it to whatever wrote it in the 34% of cases that have it.
- Carry a backlog key on `lifecycle_start` so the reverse join exists.
- Decide the legacy-YAML logs' fate: convert, or read them with a compat shim (there is precedent — `project.md` records the historical-compatibility shim pattern), or declare them out of the corpus explicitly rather than dropping them silently.
- The 200 orphan lifecycle dirs are partly legitimate (Context B ad-hoc refines never get a ticket) — distinguish those from lost attribution before treating the number as pure defect.

## Edges

- Silent exclusion is the real defect in the YAML case. A reader that skips 78 files at exit 0 is worse than one that fails, because every downstream number looks clean.
- Not every lifecycle should have a ticket. Context B is a supported path; do not "fix" orphans by inventing tickets for them.
- Backfilling 200 dirs and 296 tickets may not be worth it — going-forward correctness plus an honest statement of the pre-fix cutoff may be the cheaper and equally useful outcome.
- Deletion bias: this is measurement infrastructure and must clear the same bar. Its evidence is the two invalidated analyses above, not a hypothetical future one.

## Touch points

- `cortex_command/refine.py:430-523` — `_cmd_emit_lifecycle_start`, where a backlog key would be carried
- `skills/backlog/references/schema.md:14` — `lifecycle_slug`, the documented join key
- `cortex/lifecycle/nearly-all-work-is-rated-complex/research.md:114` — Open Question 1, the measurement this gates
- `cortex/lifecycle/the-tier-seed-is-a-placeholder/research.md` — the corpus-integrity measurements above
