---
schema_version: "1"
uuid: dfeb6b8c-7b48-4de6-a3ef-61e4328e7ae2
title: Tier assessment has three upward forces and no downward path
status: refined
priority: high
type: feature
created: 2026-08-04
updated: 2026-08-04
tags: ['lifecycle', 'tiering', 'ceremony']
areas: ['lifecycle']
complexity: complex
criticality: high
lifecycle_slug: nearly-all-work-is-rated-complex
spec: cortex/lifecycle/nearly-all-work-is-rated-complex/spec.md
---
## Why

**Rewritten 2026-08-04 after research invalidated this ticket's original evidence.** The prior version argued from a distribution ("`moderate` appears once in 212 lifecycles; complex reached 98%"). All three of its evidentiary legs failed — see `cortex/lifecycle/nearly-all-work-is-rated-complex/research.md`. Briefly: `moderate` did not exist for 203 of those 212 lifecycles; the `simple` those rows escalate *from* is a rank-floor placeholder in 186 of 211 cases, so the transitions record a first assessment rather than drift; and lifecycles exclude `simple` work by construction, so the population was selected for the thing being measured. **Do not re-cite those numbers, or the "rubric's own output was 11%" figure from `d2e5394b`, which has the same placeholder contamination.**

What survives is structural, provable by reading, and needs no distribution at all: **every mechanism that can move a tier moves it up.**

| Mechanism | Direction | Why it can only go up |
|---|---|---|
| `clarify-critic` | up only | Its prompt is one-sided by design: *"find where the ratings are poorly supported — not to be balanced"*, *"Return objections only"*, *"One-sided: focus on what's wrong, not balanced coverage"* (`clarify-critic.md:18,48,55`). It has no way to argue a tier is too high. Its Apply dispositions feed the §5 tier call. |
| `complexity_escalator` | up only | Returns early when the tier is already `complex`, so it can only ever suggest raising (`complexity_escalator.py`). Advisory — it writes nothing. |
| `reconcile-clarify` | up only | Appends only when `_TIER_RANK[desired] > _TIER_RANK[current]` (`refine.py:276`). Structural, not prose. |

No mechanism anywhere argues a tier *down*. `complexity-override` can lower one, but it is a verb an assessor must choose deliberately; nothing prompts it and nothing suggests it.

Corroborating but **confounded** (state it as such): critic Apply dispositions 1–2 → 62% complex (n=21); 3+ → 91% (n=167). Genuinely complex work naturally generates more findings, so this is equally consistent with the critic *detecting* complexity. The structural asymmetry is the argument; the correlation is not.

The companion defect — that the *seed* those mechanisms start from is a placeholder, so a filer's view never reaches it — is **#453**. Split out because its remedy is a new field and a routing decision, sharing nothing with this one but the diagnosis.

## Role

Give the tier assessment a downward path: some mechanism, somewhere, must be able to argue that a tier is rated too high.

## Integration

The critic is the highest-leverage site: it runs on every lifecycle and its Apply dispositions feed the §5 tier call directly. The change is *symmetry*, not weighting — let it surface over-rating alongside under-support, without preferring either.

The escalator is the same shape and cheaper — its early return is one condition — but see the Edges: making it bidirectional may be actively worse than leaving it one-way, so treat the two as separable rather than a pair.

**The design fork this ticket exists to settle:** how a deliberately one-sided reviewer gains the ability to argue *down* without that becoming a thumb on the scale in the other direction. The constraint is stated; the mechanism is not, and it is not obvious.

## Edges

- **Symmetry, never a thumb on the scale.** Tuning the critic to *produce* lower tiers is quota-filling. The evidenced harm is real: forced distributions cost Ford a $10.5M age-discrimination settlement and GE abandoned the vitality curve, both via target substitution. The goal is a mechanism that *can* argue down, not one that prefers to.
- **Do not move the rank-floor default.** `e3ee3b4c` records why: any higher default ratchets every legitimately-simple feature up one tier the first time reconcile runs. Make the floor *legible* — `from_seeded` and `seeded` already do — not different. The floor itself is #453's territory.
- **A downward-capable escalator may be worse than none.** Its own docstring concedes a bullet count "measures how much uncertainty got written down, which is not the same as how hard the work is." A low count is *weaker* evidence of easiness than a high count is of hardness — equally consistent with thin research. "Consider moderate, only 2 open questions" is a worse inference than the one it mirrors.
- **The rubric is probably fine; do not re-cut §5.2.** An independent audit agreed 8/8 on the full post-split population, and the "a precedent others follow" clause is not the driver (competing designs 10, blast radius 3, precedent 2, never sole). One real misapplication does appear in written justifications — a **"1-3-file ceiling"** that §5.2 explicitly disclaims ("size is not the test") — which is a candidate for a same-size-or-smaller clarification, nothing larger.
- **Everything post-fix rests on n=8.** Wilson CI 0.53–0.98; this sample cannot distinguish a 95%-complex world from a 60% one. Structural changes are justified by the structure, not by the rate. Any claim about the *rate* waits for n≥30.
- **Expected net effect** (Deletion bias, efficiency prong): the share of lifecycles taking the long road, measured by the existing `events.log` reduction — explicitly not a tier quota. Baseline 181/211 = 85.8%. Honest caveat: criticality alone pins 43–69% of the corpus, so the reachable ceiling on this axis is bounded and small; see #452.
- **Measure over backlog tickets, not lifecycles.** Lifecycles exclude routed-out `simple` work by construction. This is the error that sank the original ticket.
- Do **not** build observability for suppressed downgrades. Across 211 lifecycles zero downgrade overrides have ever been recorded, and the suppression can only fire on a second reconcile, which has never occurred.

## Touch points

- `skills/refine/references/clarify-critic.md` — the one-sided prompt (lines 18, 48, 55) and the Disposition section feeding §5
- `cortex_command/lifecycle/complexity_escalator.py` — the already-complex early return
- `cortex_command/refine.py:276` — the monotonic-up reconcile
- `cortex/lifecycle/nearly-all-work-is-rated-complex/research.md` — full six-angle record, including what invalidated the original
