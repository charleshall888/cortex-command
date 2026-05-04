---
schema_version: "1"
uuid: 27465f0f-6937-4209-b465-8cf0024d6873
title: "Wire synthesizer into overnight orchestrator-round.md Step 3b (criticality branch)"
status: open
priority: medium
type: feature
created: 2026-05-04
updated: 2026-05-04
parent: "158"
blocked-by: ["160"]
tags: [competing-plan-synthesis, overnight, plan, orchestrator]
discovery_source: research/competing-plan-synthesis/research.md
---

## Background

`cortex_command/overnight/prompts/orchestrator-round.md` Step 3b (lines 201-273) currently dispatches a single-agent plan-gen sub-agent for any feature whose `plan_path` is missing on disk. The dispatch template at lines 236-260 is a bare "design and write plan.md" prompt that does not consult the feature's criticality field.

When a critical-tier feature with `criticality: critical` enters Step 3b (e.g., a `/refine` output reaching overnight without a plan), the current behavior produces a single-agent plan rather than the §1b dual-plan-then-synthesize flow that the lifecycle skill applies in interactive mode. This ticket adds the criticality branch that invokes the shared synthesizer from #160 in that case.

Per research.md DR-1.5, this is the **last** child to ship: interactive validation (#161) and calibration (#163) gate this work. Overnight is unattended, so the synthesizer must be empirically sound on real plans before it ships there.

## What this ticket delivers

A revised Step 3b in `orchestrator-round.md` where:

- For features with `criticality != critical`: existing single-agent plan-gen behavior unchanged
- For features with `criticality: critical`: dispatch the §1b dual-plan flow (2-3 sonnet agents in parallel), then invoke the shared synthesizer from #160
- The synthesizer's chosen variant is written to `{{feature_plan_path}}`; the extended `plan_comparison` event is logged
- When the synthesizer returns the "low-confidence / defer-to-morning" sentinel, the feature is marked `deferred` (existing Step 3c behavior for ambiguous specs) with the synthesizer's reason in the deferral file

## Value

Without this branch, a critical-tier feature that hits Step 3b (currently dormant in production but live in the dispatch wiring) gets a single-agent plan that ignores the criticality signal — losing the dual-plan diversity that the `criticality: critical` setting is supposed to invoke. With it, the same feature gets the same dual-plan + synthesizer treatment it would receive interactively, with the operator-override step replaced by the synthesizer's decision (and defer-to-morning fallback when uncertain).

## Scope

- `cortex_command/overnight/prompts/orchestrator-round.md` Step 3b — add criticality branch around the existing dispatch template
- Update the orchestrator's read of `state.features[<slug>]` to surface the criticality field (likely already there per `cortex_command/overnight/state.py`; verify and use)
- Wire the synthesizer call site (per #160's helper) into the orchestrator's Python dispatch path or sub-agent prompt
- Update the deferral file format to handle synthesizer-defer cases (likely additive to the existing `deferred/{slug}-plan-q001.md` schema)

## Out of scope

- The synthesizer itself (in #160)
- Interactive wiring (in #161)
- Calibration probes (in #163)
- Path-building infrastructure — the path exists per research.md Q4 (revised post-conversation); this is wiring only

## Pre-shipment gate

Per research.md DR-1.5 and project requirements *"Defense-in-depth for permissions: …The overnight runner bypasses permissions entirely (`--dangerously-skip-permissions`)…"*, this ticket should not ship until #161 (interactive) has accumulated operator-disposition data and #163 (calibration) has passed. Overnight bypasses operator review by design — the synthesizer's misfire surface is unprotected here.
