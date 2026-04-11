---
id: 48
title: Trim and instrument overnight plan-gen prompt
status: refined
priority: low
type: chore
tags: [overnight, orchestrator, plan-gen]
created: 2026-04-09
updated: 2026-04-11
discovery_source: research/overnight-plan-building/research.md
session_id: null
lifecycle_phase: research
lifecycle_slug: trim-and-instrument-overnight-plan-gen-prompt
complexity: simple
criticality: high
spec: lifecycle/trim-and-instrument-overnight-plan-gen-prompt/spec.md
areas: [overnight-runner]
---

## Context from discovery

The overnight orchestrator prompt includes ~46 lines of plan-gen instructions (Steps 3a-3e) that have never triggered in production — every feature enters with a pre-built `plan.md` from `/refine` or `/lifecycle plan`. The instructions are processed as input tokens every round regardless.

Discovery research confirmed the current architecture already achieves clean three-way context isolation (orchestrator, plan-gen sub-agents, implementors). Extracting plan-gen to a pre-round Python module was rejected due to a state mutation ordering bug (escalation resolution must precede plan generation) and SDK dispatch integration gaps.

## What this delivers

Two small improvements to the plan-gen fallback path:

1. **Conditional prompt inclusion**: `runner.sh` checks if any features in this round have missing `plan_path` before filling the orchestrator template. If none are missing, exclude Steps 3a-3e — eliminates ~46 lines of input tokens in the common case.

2. **Trigger instrumentation**: Log a distinct event when Steps 3a-3e actually dispatch plan-gen sub-agents (not just when they run as no-ops). Provides data to revisit the extraction decision if plan-gen frequency changes.

## Acceptance criteria

- When all features have existing `plan_path` files, the orchestrator prompt does not contain Steps 3a-3e
- When any feature is missing its `plan_path`, the orchestrator prompt includes Steps 3a-3e as today
- A new event type is logged when plan-gen sub-agents are dispatched during Steps 3a-3e
- No behavioral change to the plan-gen fallback itself
