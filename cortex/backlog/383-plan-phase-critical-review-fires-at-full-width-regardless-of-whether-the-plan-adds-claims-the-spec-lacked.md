---
schema_version: "1"
uuid: 3f7a61bc-69b1-406a-8c07-f85b5eb8a8be
title: Plan-phase critical-review fires at full width regardless of whether the plan adds claims the spec lacked
status: backlog
priority: low
type: chore
created: 2026-07-16
updated: 2026-07-16
tags: ['token-efficiency', 'critical-review', 'gating']
areas: ['skills', 'lifecycle']
---
## Why

The critical-review gate condition is identical at both boundaries — `tier = complex AND criticality IN {medium, high, critical}` — so a plan review dispatches the same reviewer count as a spec review (`skills/lifecycle/references/plan.md` 3b, `skills/refine/references/specify.md` 3b, both routing through the same `angle-menu.md` count). But a plan is often a mechanical decomposition of a spec that the same gate has *already* interrogated, so its marginal yield can be much lower for identical cost.

One observation (wild-light #362, 2026-07-16), offered as a hypothesis rather than proof:

- **Spec review**: 4 reviewers, **7 A-class findings**, all ratified by the Opus synthesizer with zero downgrades. It caught two vacuous leak guards (both green in exactly the world they existed to catch), an acceptance test that would have asserted `4 == 16` and blocked its own landing, a font requirement that reduced legibility while buying zero density, and a transposed measurement that had driven the owner scope decision. The gate paid for itself many times over.
- **Plan review** (same tier/criticality, same width): **zero A-class**. The density mechanism was confirmed; the findings were framing corrections to inherited narrative. Useful, but a fraction of the yield for the same spend.

## Proposed direction

Scale plan-phase width to **plan novelty** rather than to the spec tier:

- Cheap proxy: does the plan introduce claims, mechanisms, or verification approaches the spec did not contain? (New test strategies, new seams, new measured figures.) If it is a faithful decomposition, run a reduced-width pass; if it introduces novel claims, run full width.
- Alternative framing: keep full width but narrow the *angles* to plan-specific failure modes (task executability, dependency/race hazards, guard non-vacuity) and skip re-litigating the spec design, which the spec gate already covered.

## Role

A gating-policy refinement, not a mechanism change. Distinct from #382 (which cuts payload size at constant breadth): this cuts breadth where breadth has low yield.

## Integration

- **Gated on #392** (`cortex-session-tokens`), which supersedes #381 — #381's own premise and figures measured false; see its superseded box. The evidence here is n=1 and should not be acted on from a single anecdote. Decide from per-phase telemetry (dispatch count vs A-class yield across real runs), not from this ticket's story. **This ticket's discipline was correct and is the model for the others** — it is the only one of the three that refused to act on its own anecdote.
- Sibling: #382 (rescoped 2026-07-16 to a correctness fix — the reviewer envelope has no field for probe/measurement evidence; its token framing was worth ~5%), #340 (resident-prose efficiency), #389 (bound dispatched agents).
- **Verified 2026-07-16 — every claim in this ticket holds.** Gate conditions are byte-identical at `plan.md:105` and `specify.md:128`. `angle-menu.md` has **no criticality or phase matrix at all** — the count keys only off artifact length ("< 10 lines: minimum 2 angles. Otherwise: target 3-4 angles"), so criticality gates only *whether* review runs, never *how wide*. The "same width at both boundaries" claim is therefore true, though by a different mechanism than the ticket implies.
- The adjacent question — whether to cut reviewer count generally — is open and worth ~4.7% of total spend. It is not settled by doctrine; the same telemetry that answers this ticket answers that one.

## Edges

- **Low priority and deliberately so.** Fan-out breadth is what caught every real defect in the observed run; a wrong cut here buys a cheaper harness that ships broken plans. If the telemetry does not show a consistent yield gap, close this as wontfix — that is a legitimate outcome.
- The plan gate did catch a real inherited-framing defect in the observed run (a "grey plate" premise that a probe falsified — `CheckButton` disabled/hover_pressed are already `StyleBoxEmpty` in the stock 4.7 theme, so the change was visually inert for reasons the plan never verified). Reduced width must not mean zero adversarial coverage: framing defects inherited from an approved spec are precisely what a fresh-eyes plan pass catches, since the spec gate has already anchored on them.
- One data point may reflect *this* plan being unusually derivative (4 tasks over 2 lines of production code) rather than a general property of plan reviews. A plan that invents a migration strategy or a new test harness is a different animal.

## Touch points

- skills/lifecycle/references/plan.md (3b critical-review gate)
- skills/refine/references/specify.md (3b — the sibling gate this would diverge from)
- skills/critical-review/references/angle-menu.md (angle count matrix)
- skills/lifecycle/references/critical-review-gate.md