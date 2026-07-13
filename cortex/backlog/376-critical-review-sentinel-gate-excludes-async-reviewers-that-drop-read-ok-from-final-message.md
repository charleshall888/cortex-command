---
schema_version: "1"
uuid: b53e47d8-305e-4a5f-bada-21f3db9ad5b8
title: Critical-review sentinel gate excludes async reviewers that drop READ_OK from final message
status: in_progress
priority: medium
type: bug
created: 2026-07-10
updated: 2026-07-13
areas: ['skills']
lifecycle_phase: research
lifecycle_slug: critical-review-sentinel-gate-excludes-async
complexity: complex
criticality: high
spec: cortex/lifecycle/critical-review-sentinel-gate-excludes-async/spec.md
---
## Why

During item 373's spec critical-review (2026-07-10), all four parallel reviewer agents completed their analysis with verbatim evidence quotes from the pinned artifact, but none carried the `READ_OK` sentinel in their final message — the only output the orchestrator receives from an async agent. `cortex-critical-review check-artifact-stable` excluded all four (`EXCLUDED absent`), tripping the total-failure path for a pass with zero actual drift (artifact SHA verified unchanged). Recovery required resuming each agent with a re-attestation instruction, which then passed cleanly.

## Role

The reviewer-prompt contract or the gate accounts for the async-agent delivery model: the sentinel requirement binds to the final message explicitly (reviewer-prompt.md currently says only "before the first ## heading"), or the gate distinguishes sentinel-omission from drift so the recovery path is a cheap re-attestation rather than a full invalidated pass.

## Touch points

- `skills/critical-review/references/reviewer-prompt.md` — sentinel placement instruction
- `skills/critical-review/references/verification-gates.md` — Step 2c.5 exclusion routing
- `cortex_command/critical_review` check-artifact-stable — first-50-lines sentinel scan