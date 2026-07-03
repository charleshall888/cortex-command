---
schema_version: "1"
uuid: 3b24f21f-de4f-46e4-b1f3-bd40d613cb24
title: 'Sweep provisional tail: cortex/requirements area files (editorial)'
status: refined
priority: low
type: chore
tags: ['skill-value-scorecard']
areas: ['docs']
discovery_source: cortex/research/skill-value-scorecard/report.html
created: 2026-07-02
updated: 2026-07-02
parent: "357"
complexity: complex
criticality: medium
spec: cortex/lifecycle/sweep-provisional-tail-cortex-requirements-area/spec.md
---
## Why
Child of #357's decomposition (the parent umbrella carrying the provisional tail of the skill-value audit). This child owns the cortex/requirements/ area-file slice: 32 provisional candidates (~3.3k weighted tokens) across backlog.md (11), pipeline.md (6), observability.md (6), remote-access.md (5), and multi-agent.md (4). These files load via the load-requirements selection path, so trims here are editorial (like #351), not mechanical pin-verification. None were adversarially verified.

## Role
The verification bar for this batch is pin-hit verification, single-pass: for each candidate, its listed pin hits are read and the trimmed span is confirmed to be non-load-bearing before the trim applies, honoring the keep-list; refuted candidates are recorded so they are not re-proposed. Because these are requirements prose that loads selectively, the confirmation is editorial judgment against the load-requirements selection path rather than a grep against test anchors. Ledger status write-back is deferred to a single reconciliation commit shared across the #357 children, so parallel sessions never contend on master_candidates.json.

## Integration
master_candidates.json rows are filtered to status unverified, file under cortex/requirements/, and no overlaps_ticket or reproposal_of flag. No dup_groups.json group spans these files, so no cross-file single-sourcing applies to this batch. Line anchors may predate recent commits — sections locate by heading and pinned token, not line number.

## Edges
- Several cortex/requirements/ files load selectively, not always; a trim's realized cost tracks how often its file loads.
- Editorial mode distinguishes this child from the pin-verification mode of the sibling skill-cluster children (#357-b/c/d).
- No plugins/cortex-core mirror covers cortex/requirements/ (mirrors are skills/hooks/bin), so this batch commits no mirror change.

## Touch points
- cortex/requirements/{backlog,pipeline,observability,remote-access,multi-agent}.md
- cortex/research/skill-value-scorecard/master_candidates.json (deferred reconciliation)