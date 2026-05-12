---
schema_version: "1"
uuid: d88b8d0f-df9f-4f14-98f3-1bfcc994c475
title: "Consolidate common.py:read_tier and overnight/report.py:_read_tier"
status: complete
priority: low
type: chore
created: 2026-05-11
updated: 2026-05-11
tags: [refactor, lifecycle, deduplication]
complexity: complex
criticality: medium
spec: cortex/lifecycle/consolidate-commonpyread-tier-and-overnight-reportpy-read-tier/spec.md
areas: [overnight-runner]
session_id: null
---

# Consolidate common.py:read_tier and overnight/report.py:_read_tier

## Problem

Two implementations of the canonical-tier-read rule live in the codebase post-#190:

- `cortex_command/common.py:read_tier` — public API, lru_cache wrapped, callers include `outcome_router.py:830`.
- `cortex_command/overnight/report.py:_read_tier` — private to the overnight module.

Both implement the same `lifecycle_start.tier → complexity_override.to` semantic. #190 explicitly out-of-scoped the consolidation ("no changes to Python writer code", "this ticket modifies one reader, not the broader module structure"). The pre-commit `cortex-audit-tier-divergence` gate added in #190 Task 4 makes them safer (any future change to either is detected against the corpus), but the duplication is real.

## Why it matters

- One semantic change requires two edits, both audit-gated.
- Future maintainers may not realize the gate exists and edit only one.
- `_read_tier` has no caching; if it gains a hot caller it duplicates the perf work #190 already did.

## Constraints

- `outcome_router.py:830` (only production consumer of `common.py:read_tier`) must continue to route review-gating correctly.
- `report.py:_read_tier` callers in the overnight module must continue to work.
- Pre-commit audit gate must continue to enforce parity until the consolidation lands.

## Hooks for research

- Move the canonical implementation into a single function (likely in `common.py`).
- Update `report.py:_read_tier` callers to import from `common.py` instead.
- Once one implementation remains, decide whether to retire `cortex-audit-tier-divergence` or repurpose it as a corpus-data audit (rather than a divergence-vs-Python audit).

## Source

Surfaced during #190 research and explicitly out-of-scoped per Non-Requirements. See `lifecycle/promote-lifecycle-state-out-of-eventslog-full-reads/spec.md` line 29.
