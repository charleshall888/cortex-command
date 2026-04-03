---
schema_version: "1"
uuid: d3e4f5a6-b7c8-9012-defa-123456789012
id: "020"
title: "Add harness component pruning checklist"
type: feature
status: in_progress
priority: medium
parent: "018"
blocked-by: []
tags: [overnight, harness, maintenance, quality]
created: 2026-04-03
updated: 2026-04-03
discovery_source: research/harness-design-long-running-apps/research.md
session_id: 3285e4f8-66fe-4126-9860-d11c3786d0e4
lifecycle_phase: plan
lifecycle_slug: add-harness-component-pruning-checklist
complexity: simple
criticality: medium
---

# Add harness component pruning checklist

## Context from discovery

The harness design article ends with a discipline recommendation: as models improve, harness assumptions become stale. Scaffolding added to compensate for model limitations becomes dead weight once those limitations improve. Regularly stress-testing whether each component is still load-bearing prevents the system from accumulating complexity that no longer earns its place.

Cortex-command has no practice for this. The morning report creates follow-up backlog items for failures, but nothing surfaces unnecessary complexity. The gaps:
- No scheduled or triggered review asking "would we build this component today?"
- No definition of what "load-bearing" means for each component
- No rubric for evaluating whether a component's rationale still holds

## What this should produce

A lightweight checklist — either added to the morning-review skill or as a standalone `harness-review` skill — that:

1. Lists overnight runner components with their original rationale
2. Asks for each: "Given today's Claude baseline, is this component still compensating for a real limitation?"
3. Outputs human-review candidates, not auto-created tickets
4. Includes the pruning rubric as part of the checklist itself (not deferred)

**Important**: The ritual's cost is S. Acting on its output (actually removing a component from the 800-line overnight runner) is M-L and should be treated as a separate backlog item when triggered. The checklist output is advisory; a human makes the pruning call.

## Specific candidates identified by deep research

A load-bearing vs. compensation audit identified three components as top candidates for the checklist to evaluate first:

**1. Fresh-process-per-retry isolation (`retry.py`)**
Added explicitly because accumulated failed-attempt context degrades model performance on subsequent tries. This is the purest model-limitation compensation in the codebase. Worth empirically testing whether the same model can retry in a continued conversation turn with learnings injected, rather than spawning a new process. The retry budget cap and circuit breaker (identical diffs = stop) are genuinely load-bearing and should be kept regardless.

**2. Brain agent post-retry triage (`brain.py`)**
Added because the implementing worker is presumed unable to reliably self-assess its own failure type. Worker exit reports already capture a structured SKIP/DEFER/PAUSE signal — the question is whether that signal is now reliable enough to use directly for most cases, reserving the brain agent call for cases where the exit report is ambiguous or missing.

**3. Thin orchestrator + batch plan file hand-off (runner.sh + orchestrator-round.md)**
The split where the orchestrator generates a batch plan file and exits, then Python parses and executes it, adds a parse boundary and a file format both sides must agree on. The process boundary and session checkpoint between rounds are load-bearing; whether the hand-off needs to be file-based vs. a direct function call is worth evaluating.

The audit confirmed these are load-bearing and should NOT be candidates: circuit breaker, watchdog, throttle manager, idempotency tokens, exit report protocol, atomic state writes.
