---
schema_version: "1"
uuid: b940697b-2bfc-483f-97b4-0d9daf92e221
title: Adversarially-verified trim of critical-review reference files
status: complete
priority: medium
type: chore
created: 2026-06-10
updated: 2026-06-13
complexity: complex
criticality: high
spec: cortex/lifecycle/adversarially-verified-trim-of-critical-review/spec.md
areas: ['skills']
---
## Why

skills/critical-review/references/ (~45KB beyond SKILL.md) is loaded by the orchestrator TWICE per complex+medium-or-higher lifecycle (pre-spec and pre-plan auto-triggers). The harness-token-efficiency-trim feature trimmed critical-review SKILL.md's restatements (~2.5KB) but left the references unmapped — no adversarially-verified trim map exists for them.

## Role

Produce verified trim maps for the critical-review reference files and apply the safe subset. Realistic targets: verification-gates.md (10,565B — orchestrator-side protocol with heavy How-narration), a-to-b-downgrade-rubric.md (5,307B — 8 worked examples; evaluate whether 4 suffice), residue-write.md, angle-menu.md.

## Edges (CRITICAL — exclusion list, measured in the prior feature)

These are dispatched-verbatim into fresh sub-agent prompts and CANNOT be replaced by pointers (sub-agents cannot resolve skill paths): reviewer-prompt.md, fallback-reviewer-prompt.md, synthesizer-prompt.md — whole files substituted verbatim at dispatch. The a-to-b rubric is INLINED into the synthesizer prompt at runtime (SKILL.md Step 2d), so trimming it directly shrinks every synthesizer dispatch — highest leverage per byte, but the trigger definitions and reclassification-note format are load-bearing contract text.

## Integration

The SKILL.md steps now point to verification-gates.md as the canonical contract (drift pair killed in harness-token-efficiency-trim) — trims to verification-gates.md must preserve the exit-code route tables (0/3/4 semantics) and the record-exclusion/check-synth-stable invocation contracts (E101 lint enforces flags). Events: sentinel_absence/synthesizer_drift shapes are registered in bin/.events-registry.md.

## Touch-points

- skills/critical-review/references/{verification-gates,a-to-b-downgrade-rubric,residue-write,angle-menu}.md (+ mirrors)
- skills/critical-review/SKILL.md (pointer integrity)
- bin/.events-registry.md (event shapes)
