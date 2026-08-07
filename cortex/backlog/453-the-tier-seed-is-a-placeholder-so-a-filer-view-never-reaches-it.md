---
schema_version: "1"
uuid: 35e98229-e90a-4874-8e23-2655a215b4fa
title: The tier seed is a placeholder, so a filer view never reaches it
status: wontfix
priority: medium
type: feature
created: 2026-08-04
updated: 2026-08-06
tags: ['lifecycle', 'tiering', 'backlog-verbs']
areas: ['backlog']
complexity: complex
criticality: high
---
## Why

The value every tier mechanism starts from is usually not an assessment. When a ticket carries no `complexity:` key, `cortex_command/refine.py:_read_backlog_frontmatter` writes the `simple` rank floor — measured at **186 of 211 lifecycles** in a consumer corpus.

There is no path by which a filer's view could reach that seed even when they have one. `cortex-create-backlog-item --help` exposes `--title/--status/--type/--priority/--rework-of/--parent/--tags/--areas/--body` and no complexity flag; `skills/backlog-author/SKILL.md` explicitly disclaims frontmatter ("frontmatter belongs to `cortex-create-backlog-item --body`"). So the floor is not a default that filers decline to override — it is the only reachable value.

The measured consequence: **165 of 166** observable complexity transitions read `simple -> complex`, and **zero** read `moderate -> complex`, because nothing ever sits at `moderate` to escalate from. Every first assessment is indistinguishable in shape from an escalation.

Split from **#451** (the assessment has no downward path). Same diagnosis, unrelated remedy.

## Role

Let a filer record a complexity estimate that is distinct from Clarify's assessment, so the seed carries signal — and decide whether anything is allowed to route on it.

## Integration

A field separate from `complexity`, written at creation. `complexity` stays Clarify's output; the estimate is the filer's input, and the two are comparable rather than competing.

`#450` (wontfix) established the constraint: a tier reaching frontmatter without an assessment is indistinguishable downstream from an earned one, and its explicit warning was *"Do not simply add `--complexity`/`--criticality` flags to the filing verb. That would legitimise the bypass rather than close it."* A separate field satisfies that at the **data** layer — nothing can mistake an estimate for an assessment.

**The design decision this ticket exists to settle is at the routing layer, where the same objection reappears.** If `skills/dev/SKILL.md` Step 1.4 routes triage on the estimate, then a filer writing `simple` sends work straight to direct implementation and Clarify never runs — which is #450's bypass relocated from the record into control flow. Options, none obviously right:

- **Advisory only** — the estimate seeds the lifecycle and is never routed on. Safest; delivers legibility and calibration data but no triage saving.
- **Routes only downward-safely** — an estimate may raise ceremony but never skip Clarify.
- **Routes fully** — cheapest triage, and reopens the bypass on purpose, with a stated argument for why a filer's call is trustworthy there.

## Edges

- **Calibration comes free.** Estimate versus assessment, compared, is the divergence data nothing currently produces — obtained as a byproduct rather than as built machinery. `#447` was closed wontfix because its instrument needed a denominator it could not observe; this one does not have that problem, but must not become a reason to build a report.
- **Do not change the rank-floor value.** `e3ee3b4c` records why: any higher default ratchets every legitimately-simple feature up one tier the first time reconcile runs. This ticket adds a *source* for the seed, never a different default when the source is absent.
- The `seeded` / `from_seeded` markers (`3a64142b` + follow-up) already make an absent estimate legible. They are complementary, not a substitute: they say "this was a placeholder", not "here is what the filer thought".
- **An estimate is not a tier.** Whatever it is called, it must not be read by anything that expects Clarify's vocabulary contract, and it must not satisfy the `#450` detector (a tier present with no corresponding event).
- Deletion bias, efficiency prong — expected net effect: the share of lifecycles whose seed is a placeholder, currently 186/211 = 88%. Note this is legibility, not ceremony reduction; any triage saving depends entirely on the routing decision above.
- Adds a field to every ticket. The evidence bar is met by the 186/211 measurement, but the field must earn its place at creation time, where it costs a filer a decision they may not want to make.

## Touch points

- `cortex_command/backlog/create_item.py` — argparse surface and frontmatter construction
- `cortex_command/refine.py:_read_backlog_frontmatter` — where the rank floor is written
- `skills/dev/SKILL.md` Step 1.4 — the triage route, and the locus of the routing decision
- `skills/backlog-author/SKILL.md` — currently disclaims frontmatter ownership
- `cortex/backlog/450-*.md` — the wontfix whose constraint this must respect
- `cortex/lifecycle/nearly-all-work-is-rated-complex/research.md` — the 186/211 and 165-of-166 measurements

## Resolution — wontfix (2026-08-06)

Closed at refine, after research. Full derivation: `cortex/lifecycle/the-tier-seed-is-a-placeholder/research.md`.

**The value this ticket wants to improve is inert.** Every fork that reads the lifecycle tier seed tests `tier == "complex"` only — `common.py:1084`, `spec_approve.py:152`, `implement_transition.py:172`. `simple` and `moderate` take the identical branch everywhere. The one tier-keyed consumer that distinguishes them is the research fan-out matrix, which `fanout.md:8-11` declares is "an upper bound on breadth, not a quota." Seeding `moderate` instead of `simple` changes a string in an events row and one advisory ceiling.

**Both Why-section claims failed re-measurement.**

- *186/211 = 88% placeholder seeds* is unreproducible. The `seeded` instrumentation landed at `3a64142b` on 2026-08-04; 638 of 654 all-time `lifecycle_start` rows predate it, where "no seeded key" means *cannot tell*, not *not seeded*. On the only valid cohort: 16/21 = 76%, n=21, spanning two days. This repo independently measures 56% over 302 lifecycles.
- *"Every first assessment is indistinguishable in shape from an escalation"* is refuted. 82.7% of 509 override events already carry a `gate` field that discriminates them, and `research_open_questions` overrides never fire before the clarify→research transition (0/77). This lifecycle's own reconcile emitted `simple -> complex` with both `gate: clarify_reconcile` and `from_seeded: true`.
- The *zero `moderate -> complex`* figure is an era artifact. The three-tier vocabulary landed at `e3ee3b4c` on 2026-08-03; post-era, `moderate` is used in 17.9% of assessed tickets.

**The remedy already shipped and the corrective mechanism already works.** `refine.py:354,369` stamp `from_seeded: true` on the override row, and the comment at `refine.py:327-333` states this ticket's rationale verbatim. Of 169 lifecycles started at the floor, 132 (78%) were subsequently overridden; the residual is 25 lifecycles (8.3% of all), every one of which is `simple` + low/medium criticality on the short road — the intended cheap path. No lifecycle was named where the seed produced a wrong outcome.

**Calibration, the stated bonus, is unobtainable as designed.** Clarify reads backlog frontmatter (`refine.py:75-161`), so an estimate stored there anchors the assessment it is meant to be compared against — an effect demonstrated in software estimation specifically and shown to persist in developers trained to recognize it. The comparison would measure anchor propagation while corrupting the tier signal invisibly. Only a blind-then-reveal design escapes it, and that forecloses both routing options by construction.

**All three routing options fail the front-door bar.** (a) advisory has no consumer that fails on its removal, so it is born presumed-deletable under `project.md:23`; (b) has no precedent in any tracker or disclosure program surveyed and adds a fourth upward force to the asymmetry `#451` was filed about; (c) is dominated by `dev/SKILL.md:17` rule 4, which makes the same call better-informed, and has nowhere legal to live under `backlog.md:102`.

**Corrections this ticket's research contributed**, independent of the outcome: `#451`'s selection-effect gap could not be reproduced; the prior research's 91% "preceded by `clarify_critic`" discriminator is a false lead (it fires ~98% for both classes); and the un-conditioned complex share is 79.8% (n=634) against the ~89–95% lifecycle-denominator figures.

**Filed instead:** `#459` (dev rule 4 writes an unearned complexity, correcting `#450`'s channel hypothesis), `#460` (no sound ticket↔lifecycle join), `#461` (an omitted plan `Complexity` field silently under-resources every task — the same defect as this ticket, on a surface where the value is not inert).

**Reopen if:** a fork reads `moderate` differently from `simple`; a named lifecycle among the 25 ran on an unexamined floor seed to a wrong outcome; a material share of tickets turn out to be filed by a human rather than by discovery/morning-review through backlog-author; or a blind-then-reveal design is costed below the field it replaces.
