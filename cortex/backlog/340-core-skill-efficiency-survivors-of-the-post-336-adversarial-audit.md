---
schema_version: "1"
uuid: ccbb7f99-da2e-4e2d-802d-3016b916f7a6
title: Core-skill efficiency survivors of the post-#336 adversarial audit
status: backlog
priority: low
type: epic
created: 2026-06-30
updated: 2026-06-30
tags: ['skill-efficiency-remaining-work']
discovery_source: cortex/research/skill-efficiency-remaining-work/research.md
---
## Why
A 2026-06-30 adversarial audit re-examined where core-skill token trimming and offloading still pay off after epic #336 completed the deterministic-procedure-to-CLI offloads. Six opportunity-finders proposed cuts; a symmetric trio (defense-of-current, mechanism-failure, neutral cost-model) plus an architecture probe then stress-tested them. Most were killed: repeated backend-routing prose is not dedupable (the blocks route different actions with site-specific arms), the morning-review demo-selection prose is an intentional model-judgment affordance shipped as #072, and decompose's repetition is a test-enforced guard. Three targeted changes survived as genuine net wins and one ambitious idea was deliberately declined. This epic groups the survivors so the shared discipline — rank by hot-path resident-tokens and clarity-harm, not bytes-on-disk — is applied consistently.

## Scope
Children:
- plan-phase reference slimming — extract the critical-only competing-plans block to a lazily-loaded reference (highest token value)
- morning-review close-ordering correctness fix — remove a live contradiction over a destructive action (highest priority)
- dev-router triage relocation — gate the triage block to the one branch that uses it (smallest)
- phase-isolation decision record — a wontfix that records why the context-architecture rewrite is declined

Shared discipline every child carries: preserve every test-pinned and overnight-cited heading verbatim, leaving a pointer stub rather than deleting it; justify each change by hot-path resident-token reduction or clarity-harm removal, not raw byte count.

## Out of scope
- Backend-routing prose dedup, demo-selection offload, and decompose regex/grouping dedup — all evaluated and rejected (see research.md).
- ~~The event-migration of the clarify-critic and plan-comparison sites — contested by a dual-producer parity argument; default-dropped pending that question.~~ **The plan-comparison half of this is unblocked (2026-07-17).** #391 deleted the `orchestrator-round.md` emitter, so `plan_comparison` has exactly **one** producer left (`skills/lifecycle/references/competing-plans.md` §g) — the dual-producer parity argument that parked it no longer has two producers to be about. It also has zero production readers (its registry consumers are marked `tests-only`), so the live question is now deletion, not migration. The clarify-critic half is untouched and stays parked.

> **PREMISE NEEDS A RULING (2026-07-17).** This epic's whole thesis is resident-prose trimming, and `cortex/requirements/project.md` now says the levers are `turns × context` — session length, turn count, fan-out width — and explicitly **"not resident-prose micro-trims"** (cache is already ~98% effective). The 2026-07-16 token audit measured the resident axis as small, and the batch that closed #382/#389/#391 moved **−4 lines** of `skills/` across four commits while the real lever (#389's turn cap) added prose rather than cutting it. This epic's own discipline — "rank by hot-path resident-tokens and clarity-harm, **not bytes-on-disk**" — survives that finding and is arguably vindicated by it. But "is this epic still worth running at all?" is now an open question rather than an assumption. Rule on it before picking up a child; the **morning-review close-ordering correctness fix** is a clarity-harm/correctness item and stands on its own merits regardless of the token verdict.

## Touch points
- cortex/research/skill-efficiency-remaining-work/research.md
- skills/lifecycle/references/plan.md
- skills/morning-review/SKILL.md
- skills/dev/SKILL.md