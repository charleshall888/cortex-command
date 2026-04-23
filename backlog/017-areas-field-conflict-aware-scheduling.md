---
schema_version: "1"
uuid: e6f7a8b9-c0d1-2345-ef01-678901234567
id: 017
title: "Investigate and solve conflict-aware round scheduling in overnight runner"
type: spike
status: complete
priority: medium
parent: 014
blocked-by: []
tags: [overnight, merge-conflicts, scheduling, backlog]
created: 2026-04-03
updated: 2026-04-03
discovery_source: research/overnight-merge-conflict-prevention/research.md
session_id: null
lifecycle_phase: plan
lifecycle_slug: investigate-and-solve-conflict-aware-round-scheduling-in-overnight-runner
complexity: complex
criticality: high
spec: lifecycle/investigate-and-solve-conflict-aware-round-scheduling-in-overnight-runner/spec.md
areas: [overnight-runner]
---

# Investigate and solve conflict-aware round scheduling in overnight runner

## Problem

The overnight runner assigns features to rounds using tag similarity — features with overlapping tags land in the same batch and execute in parallel. This works well for grouping related work, but actively clusters the most conflict-prone features together. For a fresh project where all tickets come from a single discovery, they share tags and modify the same new files — the algorithm produces the worst possible scheduling for conflict avoidance.

No overlap detection of any kind exists at scheduling time. The `_detect_risks()` function in `plan.py` flags shared parent epics and overlapping tags as post-hoc warnings, but doesn't enforce separation and is structurally checking the wrong thing (tag overlap *across* batches, while the grouper creates tag overlap *within* batches).

## Research Context

Prior discovery: `research/overnight-merge-conflict-prevention/research.md`

Key findings from that research:
- `group_into_batches()` (`cortex_command/overnight/backlog.py:869`) receives only `BacklogItem` metadata — no lifecycle spec or plan files are ever read at scheduling time
- Tag-grouping and conflict-prevention are opposite objectives for same-discovery feature sets
- File-level conflict prediction before implementation is an unsolved problem; no established standard exists at the work-item scheduling level
- One candidate approach: declaring areas of impact on the backlog item itself, used as a separation constraint at scheduling time — but this has a fundamental limitation on net-new projects where file structure doesn't yet exist
- Serialization approaches (run potentially-conflicting features sequentially rather than in parallel) would prevent conflicts but reduce throughput

## What to investigate

The goal is to find the best practical approach to reducing merge conflicts from parallel overnight execution. The right solution is not obvious — this needs deep investigation before any implementation decisions are made.

Questions to answer:
- What signals are actually available at scheduling time that could predict conflict risk?
- Is declaration-based (human/AI annotated) or automatic inference more reliable in practice?
- What are the throughput trade-offs of serialization vs. separation vs. detection-and-retry?
- How does the existing tag-grouping objective interact with any conflict-separation objective? Can they coexist, or does one need to replace the other?
- What would `_detect_risks()` need to become to be useful rather than contradictory?
- Are there simpler interventions — e.g., defaulting to serial execution for features that share a parent epic — that capture most of the benefit with less complexity?
