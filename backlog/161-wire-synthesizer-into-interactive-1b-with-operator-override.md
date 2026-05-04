---
schema_version: "1"
uuid: 146278b8-9913-45e7-9e3f-6290d844c539
title: "Wire synthesizer into interactive §1b (replace user-pick with operator-override)"
status: open
priority: high
type: feature
created: 2026-05-04
updated: 2026-05-04
parent: "158"
blocked-by: ["160"]
tags: [competing-plan-synthesis, lifecycle, plan]
discovery_source: research/competing-plan-synthesis/research.md
---

## Background

§1b currently presents a comparison table to the operator and asks them to pick a variant or reject all (`plugins/cortex-interactive/skills/lifecycle/references/plan.md:96-119`). With the autonomous synthesizer from #160 available, the interactive flow can replace the user-pick step with auto-synthesis — while preserving operator-override capability for cases where the operator wants to inspect the variants directly.

Per research.md DR-1.5, interactive shipping is the validation step before overnight wiring (#162). Operators can see the synthesizer's choices and override misfires; the data flows into #163's calibration; only after that does overnight ship.

## What this ticket delivers

A revised §1b flow where:

- After variants are generated (current §1c), the synthesizer from #160 runs
- The synthesizer's chosen variant is presented to the operator with rationale (selection_rationale, selector_confidence, swap-check result)
- The operator can accept the synthesizer's choice (default), override to a different variant, or reject all (existing fallback)
- The extended `plan_comparison` event records both the synthesizer's choice and the operator's final disposition

## Value

Operators currently spend time comparing 3-column variant tables on every critical-tier feature. The synthesizer gives them a recommended choice with rationale; they can rubber-stamp or override. The override capability preserves operator judgment for cases where the synthesizer misfires — and the operator-disposition data is the validation signal for the calibration in #163.

## Scope

- `plugins/cortex-interactive/skills/lifecycle/references/plan.md` §1d-§1f — replace user-pick with synthesizer-output-then-operator-confirm flow
- Wire the synthesizer call site into the skill protocol
- Update the comparison-table presentation to include the synthesizer's recommended choice prominently
- Update the `plan_comparison` event log call to capture both synthesizer-choice and operator-disposition

## Out of scope

- The synthesizer itself (in #160)
- Overnight wiring (in #162)
- Calibration probes (in #163)
- Prompt tightening (in #159)

## Operator-override design notes

The override surface is operator-facing, not autonomous. Specifically: when the synthesizer's selector_confidence is high and swap-check passes, present the recommendation with a one-line rationale; when confidence is low or swap-check disagrees, present the full comparison table as today and flag the synthesizer's uncertainty. Default action is rubber-stamp the recommendation; explicit override requires the operator to type a different variant label.
