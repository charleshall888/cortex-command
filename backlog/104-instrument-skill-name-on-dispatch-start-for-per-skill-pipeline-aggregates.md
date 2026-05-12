---
schema_version: "1"
uuid: 70d0865d-4d7d-4627-ae59-08a0d41ec8a3
title: "Instrument skill-name on dispatch_start for per-skill pipeline aggregates"
status: complete
priority: high
type: feature
parent: "101"
blocked-by: []
tags: [harness, observability, pipeline]
created: 2026-04-21
updated: 2026-04-28
discovery_source: cortex/research/extract-scripts-from-agent-tool-sequences/research.md
session_id: null
lifecycle_phase: complete
lifecycle_slug: instrument-skill-name-on-dispatch-start-for-per-skill-pipeline-aggregates
complexity: complex
criticality: high
spec: cortex/lifecycle/archive/instrument-skill-name-on-dispatch-start-for-per-skill-pipeline-aggregates/spec.md
areas: [overnight-runner]
---

# Instrument skill-name on dispatch_start for per-skill pipeline aggregates

## Context from discovery

`dispatch_start` events in `cortex_command/pipeline/dispatch.py:446` record model, tier, feature, task — but not which skill initiated the sub-agent dispatch. Per-skill pipeline cost aggregates are therefore not computable today. This blocks data-driven ranking of pipeline-side extraction candidates (C8, C9) and makes post-ship ROI validation impossible for anything the pipeline dispatches.

## Research context

- Observability floor section of `research/extract-scripts-from-agent-tool-sequences/research.md`.
- Existing aggregator: `python3 -m cortex_command.pipeline.metrics --report tier-dispatch`.
- This complements but does NOT replace ticket 103 (DR-7) — 104 covers pipeline sub-agent dispatches, 103 covers interactive-session tool calls. Different surfaces.

## Scope

- Add `skill` field to `dispatch_start` event schema in `cortex_command/pipeline/dispatch.py:446`.
- Extend `cortex_command/pipeline/metrics.py` with a secondary aggregator keyed on `(skill, tier)` over `agent-activity.jsonl`.
- New CLI report mode: `python3 -m cortex_command.pipeline.metrics --report skill-tier-dispatch`.

## Out of scope

- Interactive tool-call instrumentation (handled by ticket 103).
- Retrofitting historical event logs.
