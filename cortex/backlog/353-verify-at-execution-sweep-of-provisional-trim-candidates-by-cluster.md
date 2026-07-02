---
schema_version: "1"
uuid: 04e4c3bd-52fb-4b70-aa21-2c1f41ffdb27
title: Verify-at-execution sweep of provisional trim candidates by cluster
status: backlog
priority: low
type: chore
tags: ['skill-value-scorecard']
areas: [skills]
discovery_source: cortex/research/skill-value-scorecard/report.html
created: 2026-07-02
updated: 2026-07-02
parent: "347"
---
## Why
The audit left 164 candidates provisional: scored and mechanically pin-scanned but never adversarially verified (session limits killed the verifier waves, and re-running them all was poor value — 32 have zero pin hits anywhere, 132 have grep hits that may be incidental token matches). Individually small, they sum to roughly 15k weighted tokens of potential savings that should not be lost, but none is safe to execute on scorer say-so alone.

## Role
Work through the provisional candidates cluster by cluster — plan.md, complete.md, review.md, competing-plans.md and criticality-matrix in lifecycle; clarify, specify, and clarify-critic in refine; decompose and research in discovery; verification-gates, the downgrade rubric, angle-menu, and the prompt templates in critical-review — verifying each candidate against its listed pin hits before applying, and recording refuted ones so they are not re-proposed. The reviewer-prompt s9 verdict is already batch-verified and carries an asymmetric precondition: the straddle-rationale population instruction is the sole one repo-wide and must be kept or relocated.

## Integration
master_candidates.json carries per-candidate mechanical pin hits as grep starting points. One lifecycle per cluster batch is the intended granularity — not one per candidate, not one for all four clusters.

## Edges
- Prompt-template files in critical-review multiply by reviewer count; verify against the synthesizer parsing expectations before trimming.
- Candidates flagged as overlapping open tickets or killed ideas are excluded.

## Touch points
- skills/lifecycle/references/, skills/refine/references/, skills/discovery/references/, skills/critical-review/references/
- plugins/cortex-core mirrors (same commits)
- cortex/research/skill-value-scorecard/master_candidates.json (candidate list and pin hits)