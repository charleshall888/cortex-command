---
schema_version: "1"
uuid: fab85f4c-2aa9-4b6f-ae21-3c9f3e7c94c9
title: 'Sweep provisional tail: critical-review cluster'
status: backlog
priority: low
type: chore
tags: ['skill-value-scorecard']
areas: [skills]
discovery_source: cortex/research/skill-value-scorecard/report.html
created: 2026-07-02
updated: 2026-07-02
parent: "357"
---
## Why
Child of #357's decomposition (the parent umbrella carrying the provisional tail of the skill-value audit). This child owns the critical-review cluster: 26 provisional candidates (~4.9k weighted tokens) across SKILL.md (8), references/angle-menu.md (6), references/synthesizer-prompt.md (4), references/reviewer-prompt.md (3), references/verification-gates.md (2), references/residue-write.md (2), and references/fallback-reviewer-prompt.md (1). The a-to-b-downgrade-rubric candidates are excluded (they overlap #300). None were adversarially verified.

## Role
The verification bar for this batch is pin-hit verification, single-pass: for each candidate, its listed pins/mech_pins are read and the trimmed span is confirmed non-load-bearing and unreferenced at the pinned sites before the trim applies, honoring the keep-list; refuted candidates are recorded so they are not re-proposed. Ledger status write-back is deferred to a single reconciliation commit shared across the #357 children, so parallel sessions never contend on master_candidates.json.

## Integration
master_candidates.json rows are filtered to status unverified, file under skills/critical-review/, and no overlaps_ticket or reproposal_of flag. Two intra-cluster dup_groups (fallback-reviewer-prompt with synthesizer-prompt, and fallback-reviewer-prompt with reviewer-prompt) can be single-sourced opportunistically since all their files are in this batch. Line anchors may predate recent commits — sections locate by heading and pinned token, not line number.

## Edges
- Prompt-template files (reviewer-prompt, synthesizer-prompt, fallback-reviewer-prompt) multiply by reviewer count and feed the synthesizer's parsing; a trim is verified against the synthesizer's parsing expectations before it applies.
- This child carries the cross-site parity residual from #353 Batch 1: the cortex-resolve-model failure-cause enumeration still lives in critical-review/SKILL.md and completes while that file is open; the parallel copy in skills/lifecycle/references/implement.md stays with #348.

## Touch points
- skills/critical-review/ (SKILL.md + references/)
- plugins/cortex-core mirrors (same commits)
- cortex/research/skill-value-scorecard/master_candidates.json and dup_groups.json (deferred reconciliation)