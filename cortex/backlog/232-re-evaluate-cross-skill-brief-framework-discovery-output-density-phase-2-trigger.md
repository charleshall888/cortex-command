---
schema_version: "1"
uuid: b3a82a40-4c42-494f-8002-031733975a43
title: "Re-evaluate cross-skill brief framework — discovery-output-density Phase 2 trigger"
status: backlog
priority: low
type: feature
tags: [phase2-trigger]
review_date: 2026-11-16
created: 2026-05-17
updated: 2026-05-17
complexity: simple
areas: [discovery, lifecycle]
---

# Re-evaluate cross-skill brief framework — discovery-output-density Phase 2 trigger

## Context

The `discovery-output-density-investigate-author-centric` feature (shipped Phase 1) chose a narrow scope: wire a gate-brief generator at the discovery research→decompose gate only. Per spec Req 15 and CLAUDE.md Solution Horizon, the durable lever (cross-skill framework) was explicitly deferred — not silently dropped — with an operational arming mechanism at merge time.

This ticket is that mechanism. It is scheduled for evaluation at `review_date: 2026-11-16` (merge date + 6 months).

## Phase 2 candidates surfaced by the spec

- **Candidate C — Cross-skill brief framework (Req 15)**: The gate-brief generator wired for discovery could be extended to lifecycle research / spec / plan artifacts, which exhibit the same density patterns. Trigger condition: any documented complaint (backlog ticket, retro note, conversation transcript) about lifecycle artifact density surfacing between merge and review date.

- **Candidate G — Output lint over research artifacts (Req 9 quarterly check)**: A quarterly corpus regression check (`python3 -m cortex_command.discovery score-corpus cortex/research/`) reports pattern counts over live produced briefs. Trigger condition: ≥ 1 pattern reproducing across the live corpus at a quarterly check after Phase 1 merge.

## Evaluation criteria at review date

At `review_date`, the operator should:

1. Run `python3 -m cortex_command.discovery score-corpus cortex/research/` and note pattern counts.
2. Scan retro notes and backlog tickets filed since merge for lifecycle artifact density complaints.
3. Decide: ship Candidate C (cross-skill framework), ship Candidate G (output lint), both, or neither.

If the answer is neither (no density complaints, corpus score clean), close this ticket as resolved-no-action. If one or both candidates warrant work, create lifecycle tickets referencing this one as parent.

## References

- Spec Req 15: `cortex/lifecycle/discovery-output-density-investigate-author-centric/spec.md` (Phase 2 trigger arming mechanism)
- Phase 2 triggers section: same spec file, "Phase 2 triggers (Solution Horizon — narrow scope chosen)"
- CLAUDE.md Solution Horizon: canonical statement of "named trigger with discoverable arming" vs silent deferral
