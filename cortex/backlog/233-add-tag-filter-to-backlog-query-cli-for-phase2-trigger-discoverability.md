---
schema_version: "1"
uuid: 1288aefd-5f4a-4007-b8b6-8b999eb4b45d
title: "Add `--tag` filter to backlog query CLI for phase2-trigger discoverability"
status: refined
priority: low
type: chore
tags: [tooling-gap]
created: 2026-05-17
updated: 2026-05-18
complexity: complex
areas: [backlog,cli]
criticality: medium
spec: cortex/lifecycle/add-tag-filter-to-backlog-query/spec.md
---

# Add `--tag` filter to backlog query CLI for phase2-trigger discoverability

## Problem

`cortex-backlog-ready` (canonical: `cortex_command/backlog/ready.py`) does not support a `--tag` filter. Spec Req 15 for `discovery-output-density-investigate-author-centric` requires that the phase2-trigger backlog ticket appear in `cortex-backlog list --tag phase2-trigger` queries. Since the filter does not exist, the tag is present in the frontmatter but not queryable via CLI.

Per spec Req 15 acceptance: "if `cortex-backlog` does not currently support `--tag` filtering, file a separate wiring ticket rather than dropping this requirement."

## What to build

Add `--tag <tag>` (or `--tag <tag> [<tag>...]`) argument to `cortex-backlog-ready` (and/or a `cortex-backlog list` alias if one exists). When provided, filter output to items whose `tags` frontmatter array contains all specified tags.

Acceptance:
- `cortex-backlog-ready --tag phase2-trigger` returns at least ticket #232 (`discovery-output-density Phase 2 trigger`).
- `cortex-backlog-ready --tag tooling-gap` returns this ticket (#233) and any others tagged `tooling-gap`.
- Existing `--include-blocked` behavior is unaffected.
- Tests in `tests/test_backlog_ready.py` (or equivalent) cover `--tag` filtering.

## References

- Wiring gap surfaced by: `discovery-output-density-investigate-author-centric` spec Req 15
- Phase 2 trigger ticket requiring discoverability: `cortex/backlog/232-re-evaluate-cross-skill-brief-framework-discovery-output-density-phase2-trigger.md`
- Source to modify: `cortex_command/backlog/ready.py` — `_parse_args` and filtering logic
