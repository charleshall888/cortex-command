---
schema_version: "1"
uuid: 9fb784e1-cd80-4887-94df-c675ab12904b
title: "Fix _get_next_id in cortex-create-backlog-item to ignore IDs >=990 (seed fixture range)"
status: complete
priority: low
type: chore
tags: [backlog, cli, dashboard-seed, hygiene]
created: 2026-05-16
updated: 2026-05-17
complexity: simple
criticality: medium
areas: [backlog]
spec: cortex/lifecycle/fix-get-next-id-in-cortex/spec.md
session_id: null
lifecycle_phase: plan
---

# Fix _get_next_id in cortex-create-backlog-item to ignore IDs >=990 (seed fixture range)

## Problem

`cortex_command/backlog/create_item.py:_get_next_id` selects the next available backlog ID with a naive `max(ids) + 1` across every `[0-9]*-*.md` file in `cortex/backlog/`. The dashboard-seed fixture generator (which lives somewhere under `cortex_command/dashboard/` or a `just` recipe — needs confirmation) writes test items at IDs 990-994 (`990-seed-feature-alpha.md` through `994-seed-feature-epsilon.md`) directly into `cortex/backlog/`. These fixtures are untracked but persist in the working tree across sessions.

When `cortex-create-backlog-item` is invoked with the seeds present, the next ID jumps from the natural ~230 range to 995, leaving a huge gap in the real backlog ID sequence.

Encountered during the #228 daytime-dispatch lifecycle: a new release-gate ticket was created as 995, then renumbered manually to 230 with file rename + reference sweep + index regen.

## Two viable fixes

**Fix A (cheap, defensive)**: Update `_get_next_id` to exclude IDs in the seed-fixture range (e.g., 990 ≤ id ≤ 999) from the max computation. One-line predicate addition. Documents the reservation as a comment.

```python
ids = [
    int(m.group(1))
    for p in backlog_dir.glob("[0-9]*-*.md")
    if (m := re.match(r"^(\d+)-", p.name))
    if not (990 <= int(m.group(1)) <= 999)  # reserved for dashboard-seed fixtures
]
```

**Fix B (proper, structural)**: Move dashboard-seed output out of `cortex/backlog/` into a separate fixture directory like `cortex/fixtures/dashboard-seed/` or `tests/fixtures/backlog-items/`. Update the dashboard reader to merge fixture + real backlog at read time when running in seeded mode. Larger surface change; requires audit of every backlog reader to confirm none assumes the canonical `cortex/backlog/` path.

Recommend Fix A as a defensive guard plus a follow-up Fix-B ticket if dashboard-seed grows beyond test scaffolding.

## Acceptance

- `cortex-create-backlog-item --title ... --status backlog --type chore` invoked with `cortex/backlog/990-*.md` through `994-*.md` present allocates an ID in the natural-sequence range (max-real-id + 1), not 995+.
- Existing tests for `cortex-create-backlog-item` still pass (`pytest tests/test_create_backlog_item.py -v` or equivalent).
- If Fix B is chosen: dashboard-seed recipe writes to the new fixture dir; existing dashboard tests still pass.

## References

- Defect surfaced during: `cortex/lifecycle/wire-daytime-dispatch-through-cortex-cli/` (the #228 lifecycle's release-gate split into ticket #230).
- Source: `cortex_command/backlog/create_item.py:_get_next_id` (approx line 36-44, naive max+1).
- Seed fixture origin: untracked files matching `cortex/backlog/99[0-4]-seed-feature-*.md` — produced by `just dashboard-seed` or equivalent. Recipe path TBD by implementer.
