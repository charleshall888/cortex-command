---
schema_version: "1"
uuid: f084a030-b273-41f8-b9f6-d269097b762c
title: 'Sweep provisional tail: discovery + backlog-author clusters'
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
Child of #357's decomposition (the parent umbrella carrying the provisional tail of the skill-value audit). This child owns the discovery and backlog-author skill clusters: 43 provisional candidates (~7.0k weighted tokens) across backlog-author/SKILL.md (9), discovery/SKILL.md (7), discovery/references/research.md (7), discovery/references/clarify.md (6), backlog-author/references/body-template.md (6), discovery/references/decompose.md (6), and discovery/references/orchestrator-review.md (2). None were adversarially verified — the six decompose.md dedup reproposals are already excluded.

## Role
The verification bar for this batch is pin-hit verification, single-pass: for each candidate, its listed pins/mech_pins are read and the trimmed span is confirmed non-load-bearing and unreferenced at the pinned sites before the trim applies, honoring the keep-list; refuted candidates are recorded so they are not re-proposed. Ledger status write-back is deferred to a single reconciliation commit shared across the #357 children, so parallel sessions never contend on master_candidates.json.

## Integration
master_candidates.json rows are filtered to status unverified, file under skills/discovery/ or skills/backlog-author/, and no overlaps_ticket or reproposal_of flag. dup_groups.json groups whose files are already open in this batch can be single-sourced opportunistically. Line anchors may predate recent commits — sections locate by heading and pinned token, not line number.

## Edges
- backlog-author/SKILL.md carries the sole provisional candidate touching SKILL.md frontmatter (description/when_to_use); if that trim survives verification, the L1 surface ratchet applies — a description trim needs a budget-row update in tests/test_l1_surface_ratchet.py plus a documented rationale and lifecycle-id.
- One cross-cluster dedup group (discovery/references/clarify.md and refine/references/clarify.md, ~86 tokens) spans this child and #357-d; it is opportunistic-only, so it is left alone or the single edit coordinates with whichever child runs second.

## Touch points
- skills/discovery/ (SKILL.md + references/), skills/backlog-author/ (SKILL.md + references/body-template.md)
- plugins/cortex-core mirrors (same commits)
- cortex/research/skill-value-scorecard/master_candidates.json and dup_groups.json (deferred reconciliation)