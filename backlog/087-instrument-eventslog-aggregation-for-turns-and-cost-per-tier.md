---
schema_version: "1"
uuid: 7e43f9c7-b4ce-4e39-b5fc-5299e8bcc483
title: "Instrument events.log aggregation for turns and cost per tier"
status: in_progress
priority: medium
type: feature
created: 2026-04-18
updated: 2026-04-20
parent: "82"
tags: [opus-4-7-harness-adaptation, instrumentation]
discovery_source: research/opus-4-7-harness-adaptation/research.md
session_id: 04606665-8548-4bdf-8a52-e0b33b18c048
lifecycle_phase: implement
lifecycle_slug: instrument-eventslog-aggregation-for-turns-and-cost-per-tier
complexity: complex
criticality: medium
---

# Instrument events.log aggregation for turns and cost per tier

## Motivation

DR-4 in the research artifact says "no model-matrix recalibration without data." The `events.log` schema already carries `num_turns` and `cost_usd` per dispatch, but we lack an aggregation pipeline that answers questions like "for complex+high tasks in the past month, what's the 95th percentile turn usage?" or "what's the actual vs budgeted cost per tier?"

## Research context

From `research/opus-4-7-harness-adaptation/research.md` Open Question 4:

> What instrumentation do we need to empirically validate turn/budget limits? Current events.log schema carries num_turns and cost_usd per dispatch, but we lack an aggregation pipeline...

And from DR-4:

> Add a backlog item to instrument turn usage and cost per tier from events.log; revisit after 2-3 overnight rounds on 4.7.

## Deliverable

A small script, CLI tool, or dashboard widget that aggregates per-dispatch events to produce per-tier summaries:
- Mean and p95 `num_turns` per complexity tier (trivial/simple/complex)
- Mean and max `cost_usd` per tier, compared against current budget caps ($5/$25/$50)
- Escalation frequency per error type
- Rate-limit incident count + concurrency reduction duration

Output format, location, and invocation ergonomics (CLI vs dashboard) are for the implementer to decide.

## Dependencies

- None to start implementation
- Produces the **baseline measurement surface** that #088, #089, and DR-4's eventual matrix recalibration all depend on
- Must land and be running **before** #088 ships, per DR-4's ordering requirement

## Not blocked

Can start any time; independent of audit work.
