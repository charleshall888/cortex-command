---
schema_version: "1"
uuid: e7f9b367-c3d5-414b-8de4-dd813cdf3908
title: "Collect 4.7 baseline rounds and snapshot the aggregated data"
status: wontfix
priority: medium
type: feature
created: 2026-04-18
updated: 2026-04-21
parent: "82"
tags: [opus-4-7-harness-adaptation, capability-adoption]
discovery_source: research/opus-4-7-harness-adaptation/research.md
blocked-by: []
---

# Collect 4.7 baseline rounds and snapshot the aggregated data

## Closure note (2026-04-21)

Closed as wontfix. At n<30 per bucket this baseline is directional only — not conclusive enough to attribute prompt-change regressions to the prompt rather than variance. The 2–3 rounds of operator attention plus prompt-freeze discipline is not justified unless we plan to execute #092 and #090 with rigorous before/after comparison, which we're not currently prioritizing. Commit A (pipeline instrumentation + lifecycle artifacts + marker item #099) was reverted in `2b88932`. If we later want real measurement, re-open with a larger sample plan or a different comparison design.

## Motivation

DR-4 requires a clean 4.7 baseline before any Wave-1 prompt changes ship. Without a snapshot that can be compared against, downstream measurement (scaffolding removal in #92, matrix recalibration later) has nothing to anchor against.

Originally this ticket bundled baseline collection and scaffolding removal into one two-phase ticket. After critical-review (2026-04-18) that composite structure was split: this ticket is Phase 1 (baseline only); #92 is Phase 2 (scaffolding removal). The split gives DR-4's ordering cross-ticket `blocked-by` enforcement: #92 cannot start until #88 reaches terminal status, which requires the baseline artifact to exist.

## Research context

From `research/opus-4-7-harness-adaptation/research.md`:

- **DR-4 ordering requirement**: "(1) ship 4.7 with existing prompts → (2) collect 2–3 rounds of baseline data → (3) only then ship Wave-1 prompt changes → (4) revisit matrix recalibration decision." This ticket is step 2.

## Deliverable

- Run 2–3 overnight rounds on 4.7 with current prompts (no other changes in the window)
- Collect `num_turns` and `cost_usd` data per tier via #087's instrumentation
- Aggregate into a snapshot and commit the snapshot to git at `research/opus-4-7-harness-adaptation/4-7-baseline-snapshot.md` (exact path — #92 consumes this)
- Report format: per-tier mean and p95 `num_turns`, per-tier mean and max `cost_usd`, escalation frequency, rate-limit incidents
- Completion criterion: snapshot artifact is committed, contains data from at least 2 overnight rounds, and passes basic sanity checks (non-zero entries per tier that had dispatches)

## Dependencies

- Blocked by #087 (aggregation pipeline must exist)
- Gates #092 (scaffolding removal) and #090 (Wave-2 xhigh adoption) via the snapshot artifact

## Scope bounds

- **No prompt changes during the measurement window.** Ordering discipline is the entire point — ship 4.7 with existing prompts, collect data, then stop.
- If one round shows anomalous data (e.g., rate-limit incident skews cost), run an extra round to ensure ≥2 clean rounds in the snapshot
