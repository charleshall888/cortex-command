---
schema_version: "1"
uuid: 0e9d4947-446d-4bae-9597-d8ee9956816c
title: 'complete-route Branch 1 is dead code: wontfix_cli archives the directory before appending feature_wontfix'
status: backlog
priority: medium
type: bug
created: 2026-08-13
updated: 2026-08-13
tags: ['lifecycle', 'complete-route', 'wontfix', 'dead-code']
areas: ['lifecycle']
---
Split out of #487, which found it while verifying that ticket's own premise.

## Why

`complete_route.py:566` Branch 1 routes `wontfix` when the working-tree `events.log` carries a `feature_wontfix` row. Its real producer cannot put one there: `wontfix_cli.py` calls `_archive_move(src, dst)` and only then `_append_wontfix_row(dst / "events.log", ...)` (`:194-196`), so the row lands in `cortex/lifecycle/archive/{slug}/events.log` — a path `classify()` never reads, since the directory it does read no longer exists.

`wontfix_cli.py:176-182` additionally refuses to run from a worktree without `CORTEX_REPO_ROOT`, so the split #487 was filed about cannot be produced by this writer either.

## Evidence

Corpus measured 2026-08-13: `feature_wontfix` appears in **0** of the live `cortex/lifecycle/*/events.log` files and **19** archived ones. The only way to get a live row is the untyped `cortex-lifecycle-event log --event feature_wontfix` escape hatch, which no skill prose invokes.

## Role

Decide whether Branch 1 earns its place. Under Deletion bias the burden sits on keeping: a branch whose producer cannot reach it needs positive evidence of a live caller, or it goes.

## Edges

- Check the escape hatch before deleting — an operator running the untyped `log` form by hand is the one path that still reaches it. That is a real usage pattern, not a hypothetical, so confirm rather than assume.
- `common.py:344,390` and `scan_lifecycle.py:1024` also read `feature_wontfix`, from paths that may or may not have the same problem. Do not assume Branch 1's deadness generalizes to them.

## Touch-points

- `cortex_command/lifecycle/complete_route.py:524,554,566` — Branch 1
- `cortex_command/lifecycle/wontfix_cli.py:129,172,176-182,194-196` — the real producer
