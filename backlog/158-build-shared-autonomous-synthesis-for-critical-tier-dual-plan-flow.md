---
schema_version: "1"
uuid: 23e7753d-b28a-4413-b5ab-34354f98568a
title: "Build shared autonomous synthesis for critical-tier dual-plan flow (interactive + overnight)"
status: open
priority: high
type: epic
created: 2026-05-04
updated: 2026-05-04
blocked-by: []
tags: [competing-plan-synthesis, lifecycle, plan, overnight]
discovery_source: research/competing-plan-synthesis/research.md
---

## Background

The §1b "Competing Plans (Critical Only)" flow at `plugins/cortex-interactive/skills/lifecycle/references/plan.md:21-119` dispatches 2-3 sonnet agents in parallel for critical-tier features and asks the operator to pick one (or reject all). The user-pick step is friction in interactive mode and structurally unsupported in overnight mode where plan-gen could fire on critical-tier features without an operator present.

Discovery `competing-plan-synthesis` (research artifact: `research/competing-plan-synthesis/research.md`) resolved to **shape (3): a shared autonomous synthesizer wired into both surfaces** — interactive §1b and overnight `orchestrator-round.md` Step 3b. The discovery's events.log records the resolution at `research/competing-plan-synthesis/events.log:discovery_conversation_resolved`. (Note: this ticket originally framed a roadmap-conversation question; it was repurposed as the epic when the conversation resolved within the discovery itself.)

## Scope

A reusable synthesis component (extracted prompt fragment + Python helper) plus wiring into both call sites:

- **Interactive surface**: `plan.md` §1b — replace the user-pick step (currently §1d-§1e) with auto-synthesis that produces a single chosen plan (or hybrid graft when shipped per DR-2's B-prime path) plus operator-override capability for cases where the operator wants to inspect.
- **Overnight surface**: `cortex_command/overnight/prompts/orchestrator-round.md` Step 3b — add a criticality branch that invokes the shared synthesizer when the feature's criticality is `critical`. Currently Step 3b runs single-agent regardless of criticality.

The synthesizer applies the anti-sway scaffolding identified in research.md DR-2/3/4/7: per-axis JSON envelopes, swap-and-require-agreement against position bias, fresh-agent role separation (synthesizer ≠ any plan-generator), defer-to-morning fallback when selector confidence is low, and the meta-recursion epistemic note from DR-7.

## Children

- **#159** Tighten §1b plan-agent prompt to require strategy-level distinction (DR-3 Option 4)
- **#160** Build the autonomous synthesizer + extended `plan_comparison` event schema (DR-2 + DR-4 + DR-5 + DR-7)
- **#161** Wire synthesizer into interactive §1b (replaces user-pick with operator-override)
- **#162** Wire synthesizer into overnight `orchestrator-round.md` Step 3b (criticality branch)
- **#163** Calibration probes: planted-flaw, identical-variants tie, position-swap consistency

## Suggested implementation order

Per research.md DR-1.5: 159 (parallel) + 160 → 161 → 163 → 162. Interactive ships first to validate the design under operator supervision; calibration probes gate the overnight wiring; overnight wiring is the last surface to receive the synthesizer.

## Out of scope

- Architecture B (unbounded hybrid composition) — research.md DR-2 rejects this on formal grounds
- B-prime (constrained graft) — pre-cleared as next-step architecture but not in this epic; n=1 corpus evidence does not justify shipping it now
- Architecture C (sequential GAN replacement of §1b) — research.md DR-2 rejects this on diversity-loss grounds
- Path-building epics (`cortex overnight start --include-unrefined` or similar) — the discovery surfaced the path already exists; this epic is wiring, not new infrastructure
- Async-notify-with-timeout — research.md DR-6 remains valid as a complementary tier but not bundled into this epic

## Conditional next-step (not part of epic)

If post-shipment data shows graft-needed cases recurring in the synthesizer's "low confidence → defer to morning" output stream, **B-prime** (rank-and-pick + constrained graft against the typed plan schema, bounded under research.md Appendix invariants 1-4) is the pre-cleared follow-on. Track in research.md DR-2.
