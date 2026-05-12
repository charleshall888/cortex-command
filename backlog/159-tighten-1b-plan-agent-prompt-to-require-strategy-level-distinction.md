---
schema_version: "1"
uuid: 38ad783b-8ad4-4e57-97d2-2d21970bad6c
title: "Tighten §1b plan-agent prompt to require strategy-level distinction"
status: complete
priority: high
type: chore
created: 2026-05-04
updated: 2026-05-04
parent: "158"
blocked-by: []
tags: [competing-plan-synthesis, lifecycle, plan]
discovery_source: cortex/research/competing-plan-synthesis/research.md
complexity: complex
criticality: high
spec: cortex/lifecycle/archive/tighten-1b-plan-agent-prompt-to-require-strategy-level-distinction/spec.md
areas: [skills, lifecycle]
session_id: null
lifecycle_phase: complete
---

## Background

The §1b plan-agent prompt at `plugins/cortex-interactive/skills/lifecycle/references/plan.md:47` currently reads: *"explore a different architectural strategy, decomposition, **or ordering** than the obvious default."* The "or ordering" admission is permissive — it allows variants to differ only in task ordering, not in architectural strategy. Q7 of the discovery research (`research/competing-plan-synthesis/research.md`) documents that the historical corpus (4 events) shows variants empirically differing on ordering and granularity (16/14/13 tasks; "bottom-up" vs "events-registry-first" vs "runner-first") rather than on architectural strategy. Decompositions, not architectures.

The synthesizer being built in #160 has more leverage when the variants it ranks are genuinely architecturally distinct. Tightening the prompt is the simplest intervention (per project requirements: *"Complexity: Must earn its place by solving a real problem that exists now. When in doubt, the simpler solution is correct."*) and is independent of the synthesizer build, so it can ship in parallel.

## What this ticket delivers

A revised §1b plan-agent prompt that requires each variant to inhabit a named architectural-pattern category — forbidding ordering-only differentiation. The exact taxonomy of permissible categories is open (see research.md Open Questions) and resolves during implementation.

## Value

Without strategy-level distinction, the synthesizer downstream is ranking near-duplicates and the position-bias literature (research.md Q5) shows position-bias is worst when candidates are similar. Tightening the upstream prompt directly addresses the diversity problem that motivated DR-3 Option 4 in the research artifact.

## Scope

- `plugins/cortex-interactive/skills/lifecycle/references/plan.md:47` — the prompt-template line
- May add a brief taxonomy or examples elsewhere in the §1b reference if needed for the plan-agents to apply the constraint
- Plugin mirror at `plugins/cortex-interactive/skills/lifecycle/references/plan.md` (canonical = the plugin source per CLAUDE.md dual-source rules — same file)

## Out of scope

- The synthesizer itself (in #160)
- Wiring into either interactive or overnight surfaces (in #161, #162)
- Calibration probes (in #163)

## Conditional follow-on

If post-tightening empirical observation shows variants still converge on near-duplicate strategies, escalate to research.md DR-3 Option 3 (routing-agent layer that pre-assigns architectural axes to each plan agent). Per DR-3, Option 3 is the conditional next step, not the primary fix.
