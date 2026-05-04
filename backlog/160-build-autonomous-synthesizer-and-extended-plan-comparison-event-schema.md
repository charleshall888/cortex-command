---
schema_version: "1"
uuid: 8bd85abf-abca-4a85-b0d7-c961213e269b
title: "Build autonomous synthesizer and ship into interactive §1b"
status: open
priority: high
type: feature
created: 2026-05-04
updated: 2026-05-04
parent: "158"
blocked-by: []
tags: [competing-plan-synthesis, lifecycle, plan, synthesizer]
discovery_source: research/competing-plan-synthesis/research.md
---

## Background

The §1b "Competing Plans (Critical Only)" flow at `plugins/cortex-interactive/skills/lifecycle/references/plan.md:21-119` currently presents a comparison table to the operator and asks them to pick a variant. This ticket replaces the user-pick step with an autonomous synthesizer (with operator-override capability) and ships it in the interactive surface — which provides the validation needed before extending to overnight in #162.

The synthesizer is designed to be call-site-agnostic so #162 can wire it into the overnight `orchestrator-round.md` Step 3b path without a refactor.

## What this ticket delivers

Three coupled changes that together let an operator running `/cortex-interactive:lifecycle plan` on a critical-tier feature receive an autonomously-chosen variant with rationale, defaulting to rubber-stamp acceptance with explicit override available:

1. **Reusable synthesizer component** — Python helper plus a shared prompt fragment, callable from both Skill prompts and Python orchestrator code. Takes 2-3 plan-variant artifacts as file paths or content. Returns a chosen variant plus structured rationale (`selection_rationale`, `selector_confidence`, `position_swap_check_result`, `axis_routing` if axes are wired in). Returns a "low-confidence / defer" sentinel when swap-check disagrees or candidates are too close.

2. **Wiring into interactive §1b** — `plan.md` §1d-§1f rewritten so that after variants are generated, the synthesizer runs and presents its recommendation. Default action is rubber-stamp; explicit override requires the operator to type a different variant label. When confidence is low or swap-check disagrees, present the full comparison table as today and flag the synthesizer's uncertainty.

3. **Extended `plan_comparison` event schema** — additive over the v1 shape at `plugins/cortex-interactive/skills/lifecycle/references/plan.md:113-115`. New fields capture both the synthesizer's choice and the operator's final disposition.

## Value

The §1b user-pick step is currently the only resolution mechanism for critical-tier dual-plan output. Operators spend time comparing 3-column variant tables on every critical-tier feature. This change gives them a recommended choice with rationale plus override capability — and produces the operator-disposition data stream that the overnight extension in #162 needs as a validation signal before it ships into the unattended path.

## Anti-sway protections (load-bearing — derived from research.md)

- **Forced per-axis commitment in JSON envelope** (analog to `/critical-review`'s class-tag envelope at `plugins/cortex-interactive/skills/critical-review/SKILL.md:119-134`): synthesizer cannot output a winner without recording per-axis scores
- **Swap-and-require-agreement** (research.md DR-4): run the selector twice with variant order swapped; declare a winner only if both orders agree
- **Blinded labels**: strip "Plan A / Plan B" framing before presenting to selector; use neutral tokens
- **Fresh-agent role separation** (research.md DR-7 + Anthropic article finding): synthesizer must not be the same agent that produced any variant
- **Defer-to-morning sentinel** when swap disagrees or confidence is low — wired through to operator-presentation in interactive mode (full table shown, synthesizer flagged uncertain) and through to `deferred/` in overnight mode (when #162 ships)

## Tests (built into this ticket — not a separate calibration ticket)

- **Identical-variants tie test**: present the same plan as two variants — synthesizer must return tie or low-confidence sentinel
- **Position-swap consistency**: present the same two variants in both orders — agreement rate above the published `Claude-3.5-Sonnet 82%` baseline from `[Judging the Judges, arXiv:2406.07791]`
- **Planted-flaw probe**: take a real plan from the `lifecycle/*/plan.md` corpus, inject a structural defect (circular `Depends on`, file referenced in Verification but not in Files) into one variant — synthesizer must select the non-flawed variant

These are unit tests, not a calibration epic. The selector_confidence threshold ships with a sane default (swap-disagreement → defer); empirical tuning happens against operator-disposition data accumulated in production, not pre-shipment.

## Scope

- New Python helper (likely `cortex_command/lifecycle/plan_synthesizer.py` or similar — exact path TBD during implementation)
- Synthesizer prompt template (likely a shared markdown fragment or composed inline, called from both Skill and Python contexts; reused unchanged by #162)
- `plan.md` §1d-§1f rewrite for synthesizer + operator-override flow
- Extended `plan_comparison` event schema additive over current shape
- Test suite covering the three probe types above

## Out of scope

- Overnight wiring (in #162)
- Prompt tightening (in #159)
- Hybrid/graft composition — research.md DR-2 commits to rank-and-pick only at this stage; B-prime is documented as pre-cleared next-step but not in scope here
