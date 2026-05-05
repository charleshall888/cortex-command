---
schema_version: "1"
uuid: 23e7753d-b28a-4413-b5ab-34354f98568a
title: "Build shared autonomous synthesis for critical-tier dual-plan flow (interactive + overnight)"
status: complete
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

Discovery `competing-plan-synthesis` (research artifact: `research/competing-plan-synthesis/research.md`) resolved to **shape (3): a shared autonomous synthesizer wired into both surfaces** — interactive §1b and overnight `cortex_command/overnight/prompts/orchestrator-round.md` Step 3b. The discovery's events.log records the resolution at `research/competing-plan-synthesis/events.log:discovery_conversation_resolved`.

## Scope

A reusable synthesizer component (extracted prompt fragment + Python helper) plus wiring into both call sites — interactive §1b and overnight `orchestrator-round.md` Step 3b. The synthesizer is a pure function over plan variants (call-site-agnostic by design), so the build and both consumers ship in one ticket. Within that ticket the interactive surface is exercised against ≥1 real critical-tier dispatch before the overnight branch is enabled (validation gate as task ordering, not as a ticket boundary).

## Children

- **#159** Tighten §1b plan-agent prompt to require strategy-level distinction (DR-3 Option 4) — independent quick win, parallel-shippable
- **#160** Build shared synthesizer for critical-tier dual-plan flow (interactive + overnight) (DR-2 + DR-4 + DR-5 + DR-7) — synthesizer + interactive wiring + overnight wiring + extended event schema + unit tests + validation-gate acceptance criterion

## Suggested implementation order

Per research.md DR-1.5: #159 and #160 in parallel. Inside #160, the validation gate (interactive surface exercised against ≥1 real critical-tier dispatch) is the task-ordering boundary between the interactive wiring and the overnight wiring.

## Out of scope

- Architecture B (unbounded hybrid composition) — research.md DR-2 rejects this on formal grounds
- B-prime (constrained graft) — pre-cleared as next-step architecture but not in this epic; n=1 corpus evidence does not justify shipping it now
- Architecture C (sequential GAN replacement of §1b) — research.md DR-2 rejects this on diversity-loss grounds
- Path-building epics (`cortex overnight start --include-unrefined` or similar) — the discovery surfaced the path already exists at `orchestrator-round.md:201-273` Step 3b; this epic is wiring, not new infrastructure
- Async-notify-with-timeout — research.md DR-6 remains valid as a complementary tier but not bundled into this epic
- Standalone calibration epic — synthesizer's basic probes (identical-variants, swap-consistency, planted-flaw) are unit tests inside #160; empirical threshold tuning happens against production operator-disposition data, not pre-shipment

## Conditional next-step (not part of epic)

If post-shipment data shows graft-needed cases recurring in the synthesizer's defer-to-morning output stream, **B-prime** (rank-and-pick + constrained graft against the typed plan schema, bounded under research.md Appendix invariants 1-4) is the pre-cleared follow-on. Track in research.md DR-2.
