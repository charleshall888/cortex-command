---
schema_version: "1"
uuid: 0bcb4676-db5a-48b3-bcb6-c8976c5c9868
title: The tier split cannot reduce ceremony, because plan and review are gated on criticality rather than tier
status: complete
priority: high
type: bug
created: 2026-08-04
updated: 2026-08-04
tags: ['lifecycle', 'tiering', 'gates', 'ceremony']
areas: ['lifecycle']
---
## Why

The tier split (`e3ee3b4c`, 2026-08-03) was made to reduce ceremony on lighter work. **It cannot deliver that on its own, because the two most expensive phases are gated on criticality, not tier.**

Per the gate table in `plugins/cortex-core/skills/build/SKILL.md`, `criticality: high` sets Review to **"forced regardless of tier"** and Planning to "single plan". Separately, `/cortex-core:critical-review` auto-triggers for **Complex + medium/high/critical**. So:

- a `moderate` ticket at `high` criticality still gets a full plan and a full review;
- a `complex` ticket at `medium` criticality still gets the adversarial fan-out;
- at `complex`, the only criticality that avoids critical-review is `low`.

Both halves measured on a consumer corpus, not inferred:

- **The only `moderate` ticket in the post-split window** (`moderate`/`high`) still produced a `plan.md` and ran a full review. What it *did* save was real but narrower: research fan-out dropped 8 agents to 3 (`skills/research/references/fanout.md` tier x criticality table), and no `critical-review-residue.json` was written.
- **a `complex`/`medium` ticket** — correctly `medium` under the rubric, isolated probe tooling with no downstream consumers — still pulled critical-review (`critical-review-residue.json` present).

Compounding this, the criticality rubric makes `medium` nearly unreachable for production code: `clarify.md` defines it as *"recoverable, isolated **tooling** with no downstream consumers"*. A non-trivial change to shipped product code cannot satisfy "isolated tooling", so it lands `high` almost by definition. Eight of the nine post-split tickets in that corpus went `medium -> high` at `clarify_reconcile`.

The consequence for any distribution goal: **raising the moderate share would not, by itself, reduce felt ceremony.** The metric would move and the roads would not.

Note the gate table predates the split (`983c98ae`, 2026-07-18, "Gate every lifecycle phase fork on one criticality/tier predicate"), so nothing has ever reconciled the two.

## Role

Decide whether ceremony reduction should be delivered on the criticality axis, the tier axis, or their interaction — and make the shipped gates match the stated goal.

## Integration

Two independent predicates produce the effect: the criticality gate table in `build/SKILL.md` (Review "forced regardless of tier" at `high`), and the critical-review trigger condition (`Complex + medium/high/critical`). Either could be re-cut; so could the `medium` criticality definition in `clarify.md`. These are competing designs with different blast radii, which is why this is a decision ticket rather than an edit.

## Edges

- `high` forcing review is defensible on its own terms — it exists so hard-to-reverse work is not shipped unreviewed. The question is whether "significant or hard to reverse" is the right bar, not whether the gate should exist.
- Widening `medium` to admit production code is the highest-leverage single change and also the riskiest: it lowers the review bar for exactly the class of work most likely to need review. Do not treat it as the obvious answer.
- The research fan-out saving (8 -> 3 agents) is genuine and already working; whatever is decided should not cost that.
- Do not measure success by the tier distribution alone — that is the trap this ticket describes. The observable is which *phases actually ran*, which the distribution instrument would make countable.
- Sample caveat: the nine-ticket window was drawn from one two-day span of multiplayer-netcode and render-look work, and an independent audit found all eight `complex` calls **earned**. This ticket is about the gate structure, which is provable by reading the tables at n=0 — it is deliberately **not** a claim that tiering is mis-calibrated.

## Touch points

- `plugins/cortex-core/skills/build/SKILL.md` — criticality gate table; "forced regardless of tier" rows
- `plugins/cortex-core/skills/refine/references/clarify.md` — the `medium` criticality definition
- `plugins/cortex-core/skills/critical-review/SKILL.md` — the `Complex + medium/high/critical` trigger
- `plugins/cortex-core/skills/research/references/fanout.md` — the tier x criticality fan-out table (the one saving that does work)
- Commits `983c98ae` (gate predicates, 2026-07-18) and `e3ee3b4c` (tier split, 2026-08-03) — never reconciled
