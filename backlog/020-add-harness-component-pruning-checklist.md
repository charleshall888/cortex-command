---
schema_version: "1"
uuid: d3e4f5a6-b7c8-9012-defa-123456789012
id: "020"
title: "Add harness component pruning checklist"
type: feature
status: backlog
priority: medium
parent: "018"
blocked-by: []
tags: [overnight, harness, maintenance, quality]
created: 2026-04-03
updated: 2026-04-03
discovery_source: research/harness-design-long-running-apps/research.md
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
