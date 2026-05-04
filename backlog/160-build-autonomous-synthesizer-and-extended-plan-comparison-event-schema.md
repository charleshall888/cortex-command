---
schema_version: "1"
uuid: 8bd85abf-abca-4a85-b0d7-c961213e269b
title: "Build autonomous synthesizer + extended plan_comparison event schema"
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

The autonomous synthesizer is the core deliverable of epic #158. It takes 2-3 plan variants produced by §1b's parallel dispatch, applies anti-sway scaffolding (modeled on `plugins/cortex-interactive/skills/critical-review/SKILL.md` Steps 2c.5 + 2d), and emits a single chosen variant with structured rationale. Wiring into the two call sites is in #161 (interactive) and #162 (overnight).

The synthesizer must be call-site-agnostic — interactive `plan.md` §1b and overnight `orchestrator-round.md` Step 3b both invoke the same component with the same contract.

## What this ticket delivers

A reusable synthesis component (likely a Python helper plus a shared prompt fragment, callable from both Skill prompts and Python orchestrator code) that:

- Takes 2-3 plan-variant artifacts as input (as file paths or content, per the file-based handoff pattern described in research.md's Anthropic article notes)
- Applies position-bias mitigations per research.md DR-4: blinded variant labels, randomized order, swap-and-require-agreement
- Produces structured output: `selection_rationale`, `selector_confidence`, `position_swap_check_result`, `axis_routing` (when DR-3 axes are wired in)
- Defers to morning (returns a "low-confidence" sentinel) when swap-check disagrees or candidates are too close on the calibrated rubric
- Logs an extended `plan_comparison` event per research.md DR-5 — additive fields, backward-compatible with the v1 schema documented at `plugins/cortex-interactive/skills/lifecycle/references/plan.md:113-115`
- Carries the DR-7 epistemic caveat in code comments and/or skill-prompt context: synthesizer must be a fresh agent that produced none of the variants

## Value

The §1b user-pick step is currently the only resolution mechanism for critical-tier dual-plan output. This component replaces it with a reusable autonomous synthesizer that interactive (#161) and overnight (#162) both consume. Without it, neither surface can ship autonomous synthesis. Without the extended event schema, the synthesis decision is unauditable post-hoc.

## Scope

- New Python helper (likely `cortex_command/lifecycle/plan_synthesizer.py` or similar — exact path TBD during implementation)
- Synthesizer prompt template (likely a shared markdown fragment or composed inline, called from both Skill and Python contexts)
- Extended `plan_comparison` event schema additive over current shape at `plugins/cortex-interactive/skills/lifecycle/references/plan.md:113-115`
- Tests against synthetic variant inputs (no live §1b dispatch needed at this stage)

## Out of scope

- Wiring into §1b interactive flow (in #161)
- Wiring into overnight orchestrator-round.md Step 3b (in #162)
- Calibration probes against real-world plans (in #163)
- Hybrid/graft composition — research.md DR-2 commits to rank-and-pick only at this stage; B-prime is documented as pre-cleared next-step but not in scope here

## Anti-sway protections (load-bearing — derived from research.md)

- **Forced per-axis commitment in JSON envelope** (analog to /critical-review's class-tag envelope): synthesizer cannot output a winner without recording per-axis scores
- **Swap-and-require-agreement** (DR-4): run the selector twice with variant order swapped; declare a winner only if both orders agree
- **Blinded labels**: strip "Plan A / Plan B" framing before presenting to selector; use neutral tokens
- **Fresh-agent role separation** (DR-7 + Anthropic article finding): synthesizer must not be the same agent that produced any variant
- **Defer-to-morning sentinel** when swap disagrees or confidence is below a calibrated threshold (threshold tuning is in #163)

## Notes

The synthesizer is itself susceptible to scope-expansion bias documented in `research/critical-review-scope-expansion-bias/research.md`. Apply that prior research's structural protections (envelope extraction, B-only refusal gate analog, anchor checks) — research.md "Codebase Analysis: Anti-sway scaffolding in /critical-review" enumerates which protections transfer directly and which need adaptation.
