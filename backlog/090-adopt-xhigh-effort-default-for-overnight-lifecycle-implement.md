---
schema_version: "1"
uuid: 16d4061e-a90c-480e-947b-d08458d40e1a
title: "Adopt xhigh effort default for overnight lifecycle implement"
status: backlog
priority: low
type: feature
created: 2026-04-18
updated: 2026-04-18
parent: "82"
tags: [opus-4-7-harness-adaptation, capability-adoption]
discovery_source: research/opus-4-7-harness-adaptation/research.md
blocked-by: [88, 89]
---

# Adopt xhigh effort default for overnight lifecycle implement

## Motivation

Wave 2 capability adoption from DR-3. Per Anthropic's migration guide, `xhigh` is "the best setting for most coding and agentic use cases." Once #089 quantifies the cost delta and #088 has completed scaffolding-removal measurement, adoption becomes an informed choice.

## Research context

From `research/opus-4-7-harness-adaptation/research.md` DR-3 Wave 2 and Open Question 2. This ticket is gated on two prerequisites both landing first.

## Deliverable

- Configure `xhigh` effort as the default for overnight lifecycle implement-phase dispatches
- Ensure `max_tokens ≥ 64k` is set alongside (required by `xhigh` per Anthropic docs)
- Document the choice rationale (cite the #089 measurement)
- Monitor the next 2–3 overnight rounds for regressions; roll back if cost or quality anomalies appear

## Dependencies

- Blocked by #088 (progress-update scaffolding removal must complete so effort-level change isn't compounded)
- Blocked by #089 (cost-delta measurement informs whether this is worth shipping)

## Scope bounds

- Applies only to lifecycle implement phase, not every dispatch — per DR-3's scoping
- If #089's cost delta is prohibitive, this ticket should be closed as wontfix or downscoped to "use xhigh only for complex+critical criticality tier"
