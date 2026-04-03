---
schema_version: "1"
uuid: e6f7a8b9-c0d1-2345-ef01-678901234567
id: 017
title: "Add `areas:` field to backlog items for conflict-aware round scheduling"
type: feature
status: backlog
priority: medium
parent: 014
blocked-by: [015, 016]
tags: [overnight, merge-conflicts, scheduling, backlog]
created: 2026-04-03
updated: 2026-04-03
discovery_source: research/overnight-merge-conflict-prevention/research.md
---

# Add `areas:` field to backlog items for conflict-aware round scheduling

## Context from discovery

The overnight runner's round assignment (`group_into_batches()` in `claude/overnight/backlog.py:869`) groups features by tag similarity — items with high tag overlap land in the same batch. For a fresh project where 10 tickets all share tags and modify the same new files, this actively clusters the most conflict-prone features into the same round.

No file-level or area-level overlap detection exists. The `_detect_risks()` function in `plan.py` flags shared epics and overlapping tags post-hoc as warnings, but does not enforce separation.

## Findings

The root cause is that tag-grouping and conflict-prevention are opposite objectives for this population of work items. To address this:

- Add an `areas:` field to the backlog item YAML frontmatter (e.g., `areas: [auth, users]`)
- `group_into_batches()` receives only `BacklogItem` instances (function signature: `list[tuple[BacklogItem, float]]`) — it never reads lifecycle spec or plan files. The field must live on the backlog item itself, not only in the lifecycle spec.
- The scheduler needs a new constraint layer: area overlap must be treated as a **separation constraint** (force different rounds), not a grouping attractor. This directly conflicts with the existing tag-grouping behavior for items that share both tags and areas. The algorithm must define priority: area-overlap separation takes precedence over tag-similarity grouping.
- `/refine` and `/lifecycle` plan phase should be responsible for populating `areas:` when writing the spec or plan.

## Limitation

Area declarations are hardest to write precisely on net-new projects (no established module boundaries) — exactly where conflicts are most likely. On established projects with clear structure, declarations are easier but conflicts are already less common. This approach delivers most value incrementally over time. For net-new project sessions, tickets 015 and 016 (visibility and recovery) are the primary mitigation.

## Notes

- Blocked by 015 and 016: those should ship first as the primary near-term mitigation
- The `_detect_risks()` function in `plan.py` may need updating to check area overlap in addition to tag overlap once this field exists
- Open question: should `/refine` populate `areas:` from spec content, or should `/lifecycle` plan phase populate it from the plan (later, with more concrete file information)?
