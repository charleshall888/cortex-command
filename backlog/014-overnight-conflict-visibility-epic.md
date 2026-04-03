---
schema_version: "1"
uuid: b3e1a2c4-d5f6-7890-abcd-ef1234567890
id: 014
title: "Overnight conflict prevention and visibility improvements"
type: epic
status: complete
priority: high
tags: [overnight, merge-conflicts, morning-report, scheduling]
created: 2026-04-03
updated: 2026-04-03
discovery_source: research/overnight-merge-conflict-prevention/research.md
---

# Overnight conflict prevention and visibility improvements

## Context from discovery

When a user ran `/discovery` on a net-new project, `/refine` on 10 tickets, then `/overnight`, the session produced 2 rounds and failed with widespread merge conflicts. Three gaps were identified:

1. **Scheduling**: Round grouping is purely tag-based. For a fresh project where all tickets share tags and modify the same new files, the algorithm actively clusters conflicting features into the same round. No file-level or area-level overlap detection exists.

2. **Visibility**: When conflicts occur, `conflict_summary` and `conflicted_files` are captured in the event log but never surfaced in the morning report. Users see paused features with generic error strings and must manually trace logs.

3. **Recovery**: Feature branches are left intact and the base branch is cleanly aborted after a conflict — the state is recoverable — but no guidance is written anywhere the user sees.

## Research artifact

`research/overnight-merge-conflict-prevention/research.md`

## Children

- 015 — Surface conflict details inline in morning report
- 016 — Add recovery guidance to morning report for conflicted features
- 017 — Add `areas:` field to backlog items for conflict-aware scheduling
