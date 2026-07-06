---
schema_version: "1"
uuid: 1a162236-8dc9-4451-90f1-afb75a17ef6e
title: 'Skill value scorecard follow-through: verified trims and offloads'
status: complete
priority: medium
type: epic
tags: ['skill-value-scorecard']
areas: [skills]
discovery_source: cortex/research/skill-value-scorecard/report.html
created: 2026-07-02
updated: 2026-07-06
---
## Why
The 2026-07 skill value scorecard audit (cortex/research/skill-value-scorecard/) scored all 528 sections of the four core skill clusters plus transitive loads: 137k weighted hot-path tokens, 265 trim candidates, 96 verified safe by adversarial refutation with named preconditions. Eight verified COMPRESS verdicts with the narrowest blast radius were applied directly on branch skill-value-trims (marked applied_in_commit in master_candidates.json); the remaining verified work is larger, structural, or editorially sensitive and belongs in lifecycle-managed tickets.

## Scope
Children group the remaining work by blast radius rather than by file: the implement.md deep trim (highest weighted cost, dispatch-multiplied), the commit skill restructure, the research skill single-sourcing, the project.md compression pass, the lifecycle.config normalization deletion with its template-asset parity coupling, and a verify-at-execution sweep over the provisional tail.

## Shared discipline
Every child consumes its verdicts from cortex/research/skill-value-scorecard/master_candidates.json — each candidate carries a keep-list of pinned tokens, test cites, and preconditions that research phases should re-validate rather than re-derive. Rank execution by weighted resident tokens, not bytes on disk (epic 340 discipline). Line anchors in master_candidates.json for the six inline-trimmed files predate the trim commit — locate sections by heading and pinned tokens. Regenerate the cortex-core plugin mirror in the same commit as any canonical skill edit.

## Out of scope
Re-proposing ideas killed by the 2026-06-30 audit (backend-routing dedup, decompose regex dedup, demo-selection offload). The 5 verified-refuted candidates. Anything overlapping tickets 343/345.

## Completion check
When the last child closes, re-run the audit measurement (the mapping and per-file weighting, not the full verification) against the new baseline and record the achieved hot-path reduction next to the predicted 24-35 percent band. Only then decide whether a designed progressive-disclosure architecture pass is warranted for whatever remains — epic 340 declined the per-phase context-isolation rewrite on the record, so a new architecture effort needs the post-trim numbers to justify reopening that question.
