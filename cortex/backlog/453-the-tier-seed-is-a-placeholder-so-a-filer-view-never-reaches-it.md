---
schema_version: "1"
uuid: 35e98229-e90a-4874-8e23-2655a215b4fa
title: The tier seed is a placeholder, so a filer view never reaches it
status: backlog
priority: medium
type: feature
created: 2026-08-04
updated: 2026-08-04
tags: ['lifecycle', 'tiering', 'backlog-verbs']
areas: ['backlog']
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
