---
schema_version: "1"
uuid: 8bd85abf-abca-4a85-b0d7-c961213e269b
title: "Build shared synthesizer for critical-tier dual-plan flow (interactive + overnight)"
status: open
priority: high
type: feature
created: 2026-05-04
updated: 2026-05-04
parent: "158"
blocked-by: []
tags: [competing-plan-synthesis, lifecycle, plan, synthesizer, overnight]
discovery_source: research/competing-plan-synthesis/research.md
---

## Background

The §1b "Competing Plans (Critical Only)" flow at `plugins/cortex-interactive/skills/lifecycle/references/plan.md:21-119` currently presents a comparison table to the operator and asks them to pick a variant. The autonomous overnight plan-gen path at `cortex_command/overnight/prompts/orchestrator-round.md:201-273` Step 3b dispatches a single plan-gen sub-agent without consulting feature criticality — so critical-tier features picked up unattended bypass the dual-plan branch entirely.

This ticket builds an autonomous synthesizer (with operator-override capability in interactive mode), ships it into both surfaces, and extends the `plan_comparison` event schema. Single ticket because the synthesizer is a pure function over plan variants — call-site-agnostic by design — and merging the build with both consumers avoids speculative infrastructure (per project requirements: *"Complexity: Must earn its place by solving a real problem that exists now"*).

## What this ticket delivers

Four coupled changes that together close the critical-tier dual-plan loop in both attended and unattended modes:

1. **Reusable synthesizer component** — Python helper plus a shared prompt fragment, callable from both Skill prompts and Python orchestrator code. Takes 2-3 plan-variant artifacts as file paths or content. Returns a chosen variant plus structured rationale (`selection_rationale`, `selector_confidence`, `position_swap_check_result`, `axis_routing` if axes are wired in). Returns a "low-confidence / defer" sentinel when swap-check disagrees or candidates are too close.

2. **Wiring into interactive §1b** — `plan.md` §1d-§1f rewritten so that after variants are generated, the synthesizer runs and presents its recommendation. Default action is rubber-stamp; explicit override requires the operator to type a different variant label. When confidence is low or swap-check disagrees, present the full comparison table as today and flag the synthesizer's uncertainty.

3. **Wiring into overnight `orchestrator-round.md` Step 3b** — add a criticality branch to the plan-gen dispatcher at lines 201-273. When the eligible item's frontmatter `priority` (or equivalent criticality field — exact field TBD during implementation, per research.md Open Questions) marks it critical-tier, dispatch 2-3 plan-gen sub-agents in parallel (matching §1b's variant count), invoke the synthesizer on the variants, and either accept the winner or route to `deferred/` on the low-confidence sentinel. Non-critical-tier items continue using the existing single-agent path.

4. **Extended `plan_comparison` event schema** — additive over the v1 shape at `plugins/cortex-interactive/skills/lifecycle/references/plan.md:113-115`. New fields capture both the synthesizer's choice and (when available) the operator's final disposition. Overnight runs emit the same schema with disposition omitted.

## Acceptance: validation gate before unattended shipping

The interactive wiring (item 2) MUST be validated against ≥1 real critical-tier feature dispatch — operator runs `/cortex-interactive:lifecycle plan` on a genuinely critical-tier ticket, exercises the synthesizer's choice path, and exercises the override path — before the overnight wiring (item 3) is enabled in production. This gate can be satisfied as task ordering inside this ticket's lifecycle: implement and test item 2, validate against a real dispatch, then enable item 3. Document the validation dispatch in `events.log` so the gate is auditable.

## Value

The §1b user-pick step is the current resolution mechanism for critical-tier dual-plan output, and the overnight path has no critical-tier branch at all. This change gives interactive operators a recommended choice with rationale plus override capability, and gives overnight runs a coherent way to handle critical-tier features instead of bypassing the dual-plan branch silently.

## Anti-sway protections (load-bearing — derived from research.md)

- **Forced per-axis commitment in JSON envelope** (analog to `/critical-review`'s class-tag envelope at `plugins/cortex-interactive/skills/critical-review/SKILL.md:119-134`): synthesizer cannot output a winner without recording per-axis scores
- **Swap-and-require-agreement** (research.md DR-4): run the selector twice with variant order swapped; declare a winner only if both orders agree
- **Blinded labels**: strip "Plan A / Plan B" framing before presenting to selector; use neutral tokens
- **Fresh-agent role separation** (research.md DR-7 + Anthropic article finding): synthesizer must not be the same agent that produced any variant
- **Defer-to-morning sentinel** when swap disagrees or confidence is low — wired through to operator-presentation in interactive mode (full table shown, synthesizer flagged uncertain) and to `deferred/` in overnight mode

## Tests (built into this ticket — not a separate calibration ticket)

- **Identical-variants tie test**: present the same plan as two variants — synthesizer must return tie or low-confidence sentinel
- **Position-swap consistency**: present the same two variants in both orders — agreement rate above the published `Claude-3.5-Sonnet 82%` baseline from `[Judging the Judges, arXiv:2406.07791]`
- **Planted-flaw probe**: take a real plan from the `lifecycle/*/plan.md` corpus, inject a structural defect (circular `Depends on`, file referenced in Verification but not in Files) into one variant — synthesizer must select the non-flawed variant

These are unit tests, not a calibration epic. The `selector_confidence` threshold ships with a sane default (swap-disagreement → defer); empirical tuning happens against production operator-disposition data, not pre-shipment.

## Scope

- New Python helper (likely `cortex_command/lifecycle/plan_synthesizer.py` or similar — exact path TBD during implementation)
- Synthesizer prompt template (shared markdown fragment or composed inline, called from both Skill and Python contexts)
- `plan.md` §1d-§1f rewrite for synthesizer + operator-override flow
- `cortex_command/overnight/prompts/orchestrator-round.md:201-273` rewrite to add criticality branch
- Extended `plan_comparison` event schema additive over current shape
- Test suite covering the three probe types above

## Out of scope

- Prompt tightening (in #159)
- Hybrid/graft composition — research.md DR-2 commits to rank-and-pick only at this stage; B-prime is documented as pre-cleared next-step but not in scope here
- Async-notify-with-timeout — research.md DR-6 remains valid as a complementary tier but not bundled here
