---
schema_version: "1"
uuid: e7f9b367-c3d5-414b-8de4-dd813cdf3908
title: "Collect 4.7 baseline rounds then remove progress-update scaffolding"
status: backlog
priority: medium
type: feature
created: 2026-04-18
updated: 2026-04-18
parent: "82"
tags: [opus-4-7-harness-adaptation, capability-adoption]
discovery_source: research/opus-4-7-harness-adaptation/research.md
blocked-by: [87]
---

# Collect 4.7 baseline rounds then remove progress-update scaffolding

## Motivation

Anthropic's 4.7 guidance says built-in progress updates in long agentic traces are now more regular and higher-quality; explicit "summarize after every N tool calls" scaffolding in our prompts should become counterproductive. DR-3 schedules this as Wave 1 — but DR-4 requires a clean 4.7 baseline first to avoid confounding the measurement.

## Research context

Two coupled decisions in `research/opus-4-7-harness-adaptation/research.md`:

- **DR-3**: "Remove progress-update scaffolding. Must not ship until DR-4 has collected 2–3 overnight rounds of clean 4.7 baseline data."
- **DR-4 ordering requirement**: "(1) ship 4.7 with existing prompts → (2) collect 2–3 rounds of baseline data → (3) only then ship Wave-1 prompt changes → (4) revisit matrix recalibration decision."

Ask-1 resolution (2026-04-18): gate on DR-4 baseline (user's choice, research's recommendation).

## Deliverable

Two phases in one ticket:

**Phase 1 — Baseline collection**:
- Run 2–3 overnight rounds on 4.7 with current prompts (no scaffolding changes)
- Collect `num_turns` and `cost_usd` data per tier via #087's instrumentation
- Snapshot the aggregated baseline for comparison

**Phase 2 — Scaffolding removal**:
- Identify prompts with progress-update scaffolding (e.g., "summarize after every N tool calls", "every 3 turns provide a status update")
- Remove or soften the scaffolding per Anthropic best-practices §4.7
- Run another 2–3 overnight rounds post-change
- Compare against Phase 1 baseline; report delta in turn usage, cost, and qualitative progress-update quality

## Dependencies

- Blocked by #087 (instrumentation must exist before Phase 1 starts)
- Gates Wave 2: #090 (xhigh adoption) is blocked by this ticket's completion

## Scope bounds

- No other prompt changes in the same window — ordering discipline is the entire point
- If Phase 2's results show regression (e.g., native progress updates are thinner than our scaffolding), revert and keep the scaffolding
