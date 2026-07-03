---
schema_version: "1"
uuid: 04e4c3bd-52fb-4b70-aa21-2c1f41ffdb27
title: Sweep remaining verified and provisional trim candidates by cluster
status: in_progress
priority: low
type: chore
tags: ['skill-value-scorecard']
areas: [skills]
discovery_source: cortex/research/skill-value-scorecard/report.html
created: 2026-07-02
updated: 2026-07-02
parent: "347"
lifecycle_phase: research
lifecycle_slug: sweep-remaining-verified-and-provisional-trim
---
## Why
This ticket sweeps everything the audit found that no sibling ticket owns — three distinct remainders. First, 52 already-verified candidates in cluster files without a dedicated ticket, ~8.8k weighted tokens: the lifecycle SKILL.md body sections (four candidates, ~2.2k), backlog-writeback s3/s5, complete.md, competing-plans.md, criticality-matrix, plan.md, review.md, orchestrator-review (including the s7 fix-agent-template lazy-ref and the s13 verified DELETE), refine-delegation, load-requirements, critical-review-gate, complexity-escalation, the remaining discovery-bootstrap and post-refine-commit sections, and the small parallel-execution, kept-pauses, concurrent-sessions, and wontfix stragglers. Second, the provisional tail: 162 candidates, ~26.4k weighted, scored and mechanically pin-scanned but never adversarially verified (the corpus has 164 unverified, but commit SKILL s6 and research SKILL s15 belong to tickets 349 and 350 under the file rule; 21 of the rest carry overlap or reproposal flags and are excluded at execution). The tail includes the provisional candidates in the three cluster SKILL.md bodies (refine, discovery, critical-review) and a transitive-file slice — 64 candidates, ~6.5k weighted — across files no other ticket owns: the cortex/requirements area files (pipeline, observability, backlog, multi-agent, remote-access), the backlog-author skill and its body-template reference, fanout.md itself, the ADR README, the pr skill, skills/backlog/SKILL.md, the interview skill's loop reference, and the overnight plan-synthesizer prompt.

## Role
Work through the remainder in batches by cluster or file family. Verified candidates apply directly, honoring each verdict keep-list. Provisional candidates get verified against their listed pin hits first, recording refuted ones so they are not re-proposed. The reviewer-prompt s9 verdict is already batch-verified and carries an asymmetric precondition: the straddle-rationale population instruction is the sole one repo-wide and must be kept or relocated. The cross-file duplication groups in dup_groups.json (nine groups, ~830 tokens; the largest pair competing-plans with plan and plan with specify) can be single-sourced opportunistically when their files are already open in a batch — three groups span implement.md, ticket 348's file, so coordinate that seam with 348 so each edit happens exactly once.

## Integration
master_candidates.json carries per-candidate verdicts, keep-lists, and mechanical pin hits as grep starting points; the eight inline-applied candidates are marked applied_in_commit, and line anchors for the six inline-trimmed files predate that commit — locate sections by heading and pinned tokens, not line numbers. One lifecycle per batch is the intended granularity — not one per candidate, not one for everything. The verified lifecycle-cluster remainder is the natural first batch (largest, already de-risked).

## Edges
- Prompt-template files in critical-review multiply by reviewer count; verify against the synthesizer parsing expectations before trimming.
- The cortex/requirements area files load via the load-requirements selection path; trims there are editorial like ticket 351, not mechanical.
- Candidates flagged as overlapping open tickets or killed ideas are excluded.

## Touch points
- skills/lifecycle/ (SKILL.md + references/), skills/refine/references/, skills/discovery/references/, skills/critical-review/references/
- cortex/requirements/ area files, skills/backlog-author/, skills/pr/, skills/research/references/fanout.md, cortex/adr/README.md, cortex_command/overnight/prompts/plan-synthesizer.md
- plugins/cortex-core mirrors (same commits)
- cortex/research/skill-value-scorecard/master_candidates.json and dup_groups.json