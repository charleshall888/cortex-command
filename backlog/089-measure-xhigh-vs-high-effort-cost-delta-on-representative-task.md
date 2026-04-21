---
schema_version: "1"
uuid: 84821b29-13db-4677-bd07-0c66465ca5e8
title: "Measure xhigh vs high effort cost delta on representative task"
status: wontfix
priority: low
type: spike
created: 2026-04-18
updated: 2026-04-20
parent: "82"
tags: [opus-4-7-harness-adaptation, spike]
discovery_source: research/opus-4-7-harness-adaptation/research.md
blocked-by: []
session_id: null
lifecycle_phase: complete
lifecycle_slug: measure-xhigh-vs-high-effort-cost-delta-on-representative-task
complexity: complex
criticality: high
---

# Measure xhigh vs high effort cost delta on representative task

## Motivation

DR-3 Wave 2 proposes adopting `xhigh` effort as the default for overnight lifecycle implement tasks. Anthropic's migration guide describes `xhigh` as "the best setting for most coding and agentic use cases," but its cost delta vs `high` on our workload is unknown. Before shipping Wave 2 (#090), measure the delta.

## Research context

From `research/opus-4-7-harness-adaptation/research.md` Open Question 2:

> Should overnight's effort default be high or xhigh? Anthropic says xhigh is "the best setting for most coding and agentic use cases" and requires max_tokens ≥ 64k. Our current SDK calls in claude/pipeline/dispatch.py may not set effort explicitly. Needs: (a) confirm SDK wiring supports effort passing, (b) measure actual cost delta between effort tiers on a representative task.

## Deliverable

A short report covering:
- Does `claude/pipeline/dispatch.py` support passing `effort` through `ClaudeAgentOptions`? If not, what wiring is missing?
- On a representative lifecycle-implement task (pick one in-flight or synthetic), what's the cost delta between `high` and `xhigh`?
- What's the turn-count delta? (Often correlated with cost but not always.)
- What's the qualitative output-quality delta? (Subjective; worth a paragraph.)

## Dependencies

- Blocked by #087 (need instrumentation to measure turn/cost reliably)
- Feeds #090 (adoption decision): if cost delta is small and quality delta is meaningful, ship; if cost blows up with marginal quality gain, defer or use `xhigh` only for complex+critical

## Scope

- Single representative task — not a full benchmark suite
- Don't change defaults as part of this ticket; it's measurement only
