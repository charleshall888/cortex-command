---
schema_version: "1"
uuid: 393849ba-1fb9-4a40-bf86-e6a5525cce65
title: 'Sweep provisional tail: refine cluster + transitive tail'
status: complete
priority: low
type: chore
tags: ['skill-value-scorecard']
areas: ['skills']
discovery_source: cortex/research/skill-value-scorecard/report.html
created: 2026-07-02
updated: 2026-07-03
parent: "357"
complexity: complex
criticality: high
spec: cortex/lifecycle/sweep-provisional-tail-refine-cluster-transitive/spec.md
---
## Why
Child of #357's decomposition (the parent umbrella carrying the provisional tail of the skill-value audit). This child owns the refine cluster plus the transitive tail no sibling child owns: 42 provisional candidates (~7.9k weighted tokens) across refine/SKILL.md (8), cortex/adr/README.md (6), research/references/fanout.md (5), refine/references/specify.md (5), refine/references/clarify.md (5), pr/SKILL.md (4), refine/references/clarify-critic.md (2), overnight/prompts/plan-synthesizer.md (2), skills/backlog/SKILL.md (2), commit/SKILL.md (1), research/SKILL.md (1), and interview/references/loop.md (1). None were adversarially verified.

## Role
The verification bar for this batch is pin-hit verification, single-pass: for each candidate, its listed pins/mech_pins are read and the trimmed span is confirmed non-load-bearing and unreferenced at the pinned sites before the trim applies, honoring the keep-list; refuted candidates are recorded so they are not re-proposed. Ledger status write-back is deferred to a single reconciliation commit shared across the #357 children, so parallel sessions never contend on master_candidates.json.

## Integration
master_candidates.json rows are filtered to status unverified, file under skills/refine/ or the transitive set, and no overlaps_ticket or reproposal_of flag. dup_groups.json single-sourcing is opportunistic; the refine and lifecycle plan.md group touches lifecycle files owned by #348/#353 and stays out of this child. Line anchors may predate recent commits — sections locate by heading and pinned token, not line number.

## Edges
- The transitive slice is a grab-bag of unrelated single files (adr/README, fanout, pr, commit, skills/backlog, interview loop, plan-synthesizer) rather than a cohesive cluster; each verifies against its own pins independently.
- One cross-cluster dedup group (refine/references/clarify.md and discovery/references/clarify.md, ~86 tokens) spans this child and #357-b; it is opportunistic-only.
- plan-synthesizer.md is an overnight prompt, not a skill, so no plugins/cortex-core mirror covers it.

## Touch points
- skills/refine/, skills/pr/, skills/commit/, skills/backlog/, skills/research/ (SKILL.md + references/fanout.md), skills/interview/references/loop.md, cortex/adr/README.md, cortex_command/overnight/prompts/plan-synthesizer.md
- plugins/cortex-core mirrors (skills only, same commits)
- cortex/research/skill-value-scorecard/master_candidates.json and dup_groups.json (deferred reconciliation)