---
schema_version: "1"
uuid: e2df1e3f-95eb-4aff-ad57-7ab1da050879
title: Record per-phase context isolation as declined
status: wontfix
priority: low
type: spike
created: 2026-06-30
updated: 2026-06-30
parent: "340"
tags: ['skill-efficiency-remaining-work']
discovery_source: cortex/research/skill-efficiency-remaining-work/research.md
---
## Why
The audit asked whether the interactive lifecycle should isolate each phase into a fresh context the way the overnight runner isolates each feature, to shed the resident phase-reference prose that accumulates over a long single session. A dedicated probe verified the accumulation ceiling is real (roughly 51K tokens worst case) but concluded the change is not worth it: the heavy work is already dispatched to fresh sub-agents, so only instruction prose accumulates; the mandatory human pauses and the complete-phase process split already shed most of it in the normal flow; the harness has no API to drop a reference once its phase is done (context only grows); and full isolation fights the interactive lifecycle's defining human-in-the-loop, single-thread property at large rewrite risk. This ticket records that decision so the idea is not re-proposed without new information.

## Role
Stand as the durable wontfix record for per-phase context isolation. It captures the verified accumulation ceiling, the harness "no shed API" constraint that kills selective reference-shedding, and the redirect: resident-prose reduction should be pursued by trimming the fat phase references (the sibling plan-phase slimming child is the first instance), not by a context-architecture rewrite.

## Integration
This is a decision record, not a build. It pairs with the plan-phase slimming child as the chosen alternative lever. If a future harness exposes a context-eviction API, or measurements show auto-compaction failing to bound the ceiling in practice, that is the new information that would reopen it.

## Edges
- Reopen only on new information: a harness context-eviction capability, or evidence that auto-compaction does not bound the accumulation in real sessions.
- Does not block or depend on the sibling efficiency children.

## Touch points
- cortex/research/skill-efficiency-remaining-work/research.md (the probe findings and decision records)
- skills/lifecycle/SKILL.md (the orchestrator whose context model was assessed)
- cortex_command/overnight/feature_executor.py (the fresh-per-task contrast)