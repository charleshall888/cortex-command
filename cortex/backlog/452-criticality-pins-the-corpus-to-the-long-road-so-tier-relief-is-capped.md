---
schema_version: "1"
uuid: 3edd8d05-bce5-4b4e-9a8b-b82599c9962d
title: Criticality pins the corpus to the long road, so tier relief is capped
status: refined
priority: medium
type: feature
created: 2026-08-04
updated: 2026-08-06
tags: ['lifecycle', 'tiering', 'ceremony', 'criticality']
areas: ['lifecycle', 'skills']
complexity: complex
criticality: high
spec: cortex/lifecycle/criticality-pins-the-corpus-to-the/spec.md
---
## Why

Measured 2026-08-04 while researching #451. The short road is `criticality ∈ {high, critical} OR tier == complex` (`cortex/requirements/project.md:40`) — an **OR**, so criticality alone can pin a lifecycle to the long road no matter what the tier says.

It does, overwhelmingly:

| | criticality alone pins it |
|---|---|
| wild-light (n=211) | **43%** |
| cortex-command (n=164) | **69%** |
| post-fix sample (n=8) | **7 of 8** |

The decisive case: **the one correct `moderate` call in 375 lifecycles across two repos was made at `criticality: high`, and took the long road anyway.** It saved a narrower research fan-out (8 agents → 3) and no critical-review — real, but not Plan or Review. The middle tier was used exactly as designed and could not relieve ceremony.

Consequence: re-tiering *every* `complex` lifecycle to `moderate` would move only ~23% (cortex-command) to ~43% (wild-light) onto the short road. **That is the ceiling on the tier axis, under perfect re-tiering.** Any ceremony work targeting tier is bounded by it. #451 addresses tier assessment and is worth doing on its own terms, but it cannot exceed this bound.

## Role

Decide whether ceremony relief should come from the criticality axis, and if so how — given that the obvious move has already been considered and rejected once.

## Integration

The criticality rubric is `skills/refine/references/clarify.md` §5.3. Its `high` definition is *"significant or hard to reverse, **or any change to shared skills / workflow infrastructure / overnight runner / hooks — the appropriate default for most agentic-layer changes**"*. That second clause makes essentially all harness self-work `high` by definition, which is why cortex-command sits at 69%.

There is a structural gap: `low` is "trivially reversible, no downstream deps", `medium` is "recoverable, isolated **tooling** with no downstream consumers". Ordinary production code that is recoverable but has consumers has **no home below `high`** — it lands there by elimination, not by judgment.

## Edges

- **Widening `medium` to admit production code was considered and explicitly rejected twice** — in #449 and in `c6528012` — as *"the highest-leverage single change and also lowers the review bar for exactly the work most likely to need review."* Reopening it needs an argument those did not have, not a restatement.
- `c6528012` already split part of the predicate: criticality decides *whether* Review runs, tier decides *how deep* (Stage 2 complex-only). Its effect is unmeasured. Harvest that before building more.
- `b854bbf3` is the cautionary case: narrowing critical-review to `complex + high/critical` removed gate eligibility from 35% of the corpus on the strength of n=1, and was reverted the same day. A coverage cut needs a coverage argument.
- Fully decoupling the predicate means editing the wheel-owned transition table (`transition_table.py:385,409,465,482`) and a ratified constraint (`project.md:40`), per ADR-0024. Highest cost, lowest reversibility, and the only route that beats the ceiling above.
- **Do not measure success by tier distribution.** The observable is which phases actually ran, from the existing `events.log` reduction. Baseline: 181/211 = 85.8% long road.
- Sample caveat: two repos, one of them (cortex-command) explicitly the least representative corpus available.

## Touch points

- `skills/refine/references/clarify.md` §5.3 — the criticality rubric and the agentic-layer default clause
- `cortex/requirements/project.md:40` — "The short road", the ratified OR predicate
- `cortex_command/lifecycle/transition_table.py:385,409,465,482` — the guards
- `skills/build/SKILL.md` — the criticality gate table
- `cortex/lifecycle/nearly-all-work-is-rated-complex/research.md` — the measurement
- Commits `c6528012` (partial split), `b854bbf3` (reverted narrowing), `#449`
