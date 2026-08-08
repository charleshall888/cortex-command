---
schema_version: "1"
uuid: 53ea7e79-7754-4708-ae4f-ebeae99abdc0
title: No sound join between tickets and lifecycles, so no tier analysis is currently trustworthy
status: wontfix
priority: medium
type: bug
created: 2026-08-06
updated: 2026-08-08
tags: ['lifecycle', 'backlog', 'measurement']
areas: ['lifecycle']
lifecycle_phase: wontfix
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

## Resolution: wontfix (2026-08-08, refuted at Clarify)

Every claim in the Why was re-measured at refine. The premise does not hold; no work was done.

**The join is sound.** Over the 322 tickets that entered refine (`complexity:` present): `lifecycle_slug` on 159 (49%), joinable via the `spec:` path on a further 134 (42%) — **91% forward-joinable**, not 34%. The reverse direction is 555/758 lifecycle dirs (73%) through `index.md`'s `parent_backlog_uuid`/`parent_backlog_id`, and it is not hypothetical: `cortex_command/lifecycle/wontfix_cli.py:66-73` executes that join today, and `create_index.py:144,290` writes the keys. So "the reverse join is impossible" is false, and carrying a backlog key on `lifecycle_start` would add a third redundant key.

**The gating measurement never needed the join.** `cortex/lifecycle/nearly-all-work-is-rated-complex/research.md` Open Question 1 — the line this ticket cites as "the measurement this gates" — states it is "answerable by an existing-tools reduction over backlog frontmatter." Taken here in one script: **260/320 = 81.2% complex** on the backlog-ticket denominator (that OQ recorded 75%). The Why's claim that it "has not been taken, because it cannot be taken on this corpus" contradicts its own citation.

**Absence is a handled fallback, not a break.** `backlog/resolve_item.py:113` documents the chain `lifecycle_slug` → spec/research dirname → `slugify(title)`, and every consumer is null-tolerant: `overnight/backlog.py:337` (`or None`), `dashboard/data.py:1520` (`_opt_field`), `hooks/scan_lifecycle.py:279` (`.get`). Nothing turns red when the field is missing, so under `project.md`'s Deletion bias the surface carries the presumption of removal — writing it more often is unearned machinery.

**Scope errors, for the record.** The header "Measured across `cortex-command`, `wild-light`, …" is false for the first three bullets: 153/449, 200/353 and 185 rows are all cortex-command alone (the source research says "in this repo"); five-repo figures are 310/1044, 449/758 and 672. Bullets 1 and 2 are one measurement — 353 − 153 = 200 is its arithmetic complement. The YAML bullet's "nobody has measured what is in them" is answered by `cortex/requirements/project.md:65`, which holds the line census *and* fixes the reader remedy; only 20 of the 79 files are wholly YAML (59 are mixed and partly read), and the tier-relevant loss is 25 of 697 `lifecycle_start` rows (~3.6%). Integration piece 1 already exists: `cortex_command/lifecycle/start_sync.py:110-112`. The Touch point below is also wrong — `_cmd_emit_lifecycle_start` begins at `refine.py:528`; 430-523 is inside `_cmd_reconcile_clarify`.

**What is real but not worth a ticket.** `cortex-refine start` does not perform the `lifecycle_slug` write-back that `cortex-lifecycle-enter` does, so per-month coverage fell from 79% (April) to 5% (August) as refine displaced `enter`. Harmless given the fallback chain and the 91% join. Sibling ticket `#459` was refuted at refine the same day on the same premise.

## Touch points

- `cortex_command/refine.py:430-523` — `_cmd_emit_lifecycle_start`, where a backlog key would be carried
- `skills/backlog/references/schema.md:14` — `lifecycle_slug`, the documented join key
- `cortex/lifecycle/nearly-all-work-is-rated-complex/research.md:114` — Open Question 1, the measurement this gates
- `cortex/lifecycle/the-tier-seed-is-a-placeholder/research.md` — the corpus-integrity measurements above
