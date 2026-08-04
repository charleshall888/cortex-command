---
schema_version: "1"
uuid: dfeb6b8c-7b48-4de6-a3ef-61e4328e7ae2
title: Nearly all work is rated complex, so the tier axis cannot relieve ceremony
status: backlog
priority: high
type: feature
created: 2026-08-04
updated: 2026-08-04
tags: ['lifecycle', 'tiering', 'ceremony']
areas: ['lifecycle']
complexity: complex
criticality: high
---
## Why

The tier split (`e3ee3b4c`) and the tier-scoped review depth that followed (`c6528012`) both assume work is distributed across `simple | moderate | complex`. Measured on a 212-lifecycle consumer corpus (wild-light, `cortex/lifecycle/*/events.log`, reduced through `lifecycle_start` plus `complexity_override`), it is not.

`moderate` appears **1 time in 212 lifecycles, ever**. The complex share has climbed steadily and is not a small-sample artifact:

| month | n | complex share |
|-------|---|---------------|
| 2026-03 | 6 | 33% |
| 2026-05 | 43 | 67% |
| 2026-06 | 90 | 89% |
| 2026-07 | 55 | 98% |
| 2026-08 | 14 | 93% |

Tier already dominates whether Review runs — 3% at the lower tiers versus 89% at complex — while criticality is the weak predictor (66% at medium, 88% at high). So the gate wiring is not what forces ceremony. **The tier assessment is.** Any further gate re-cut on the tier axis is rate-limited by a denominator that is ~95% one value.

This is the trap #449 named in its own Edges and then fell into: it argued from the gate tables at n=0 and proposed re-cutting them. The tables were read correctly; the population they act on was never checked. The depth change shipped in `c6528012` is correct but binds on the single below-complex-at-high-criticality lifecycle in the corpus.

## Role

Establish whether ~95% `complex` reflects the work or the rubric, and if the rubric, re-cut §5.2 so the middle tier is reachable.

## Integration

The tier is decided at Clarify (`skills/refine/references/clarify.md` §5.2). Its `complex` definition — "a decision code-reading will not settle: competing designs, a blast radius you cannot enumerate, or a precedent others follow" — plausibly admits most non-trivial feature work, since almost anything sets some precedent. `moderate` is "needs orientation, but no real design fork — most work lands here", a claim the corpus falsifies by 211 to 1.

## Edges

- **The rubric may be right and the work genuinely complex.** A prior audit of eight post-split calls found all eight earned. Settle this before touching the definitions; re-cutting a correct rubric to hit a distribution is the quota-filling failure #447 warned against.
- "When torn, take the lower tier" already exists in §5.2 and is not producing lower tiers. Understand why before adding more prose telling the assessor the same thing — that is prose-only enforcement of a judgment, the weakest available lever.
- The escalator (`cortex-complexity-escalator`) **writes nothing** — it prints a one-line recommendation and exits, and the tier only moves if the assessor records a `complexity_override` themselves. But its advice is one-*directional*: it fires only when the feature is **not already `complex`**, so it can never suggest going down. That asymmetry is a candidate contributor; a mechanical ratchet it is not.
- Do not measure success by the tier distribution alone. The observable is which phases actually ran, which the 20-line reduction over `events.log` used here already answers without new instrumentation.
- Sample: one consumer repo, game/graphics work, Feb–Aug 2026. cortex-command's own corpus is explicitly not representative and should not be substituted.

## Touch points

- `skills/refine/references/clarify.md` §5.2 — the tier definitions
- `cortex_command/lifecycle/complexity_escalator.py` — the one-directional advisory
- `skills/build/SKILL.md` — the criticality gate table the tier feeds
- Commits `e3ee3b4c` (split), `c6528012` (depth), `b854bbf3` (the underfounded narrowing, reverted)
