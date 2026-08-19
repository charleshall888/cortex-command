---
schema_version: "1"
uuid: 52629531-6334-4e75-a5c6-4fe1408b421c
title: finalize reads its idempotency scan from the CWD log while log_event writes feature_complete to the main root
status: complete
priority: high
type: bug
created: 2026-08-13
updated: 2026-08-19
tags: ['lifecycle', 'worktree', 'events-log', 'finalize']
areas: ['lifecycle']
---
Split out of #487, which found it but scoped it out.

## Why

`finalize.py:185` resolves `root = _resolve_user_project_root_from_cwd()` and reads `events_log = feature_dir / "events.log"` for both `_feature_complete_exists` (`:195`) and `count_rework_cycles`, while `log_event` (`:198`) writes `feature_complete` through the pinned main-root resolver. Post-#484 those are two different files.

Its own docstring (`finalize.py:56-58`) still states the counters, the idempotency scan, and `log_event`'s write target "all resolve against the same physical tree" — false as written.

## Evidence

Observed while researching #487, not hypothetical: from a worktree, `_feature_complete_exists` reads an empty CWD log, never sees the row it just wrote, and so **re-emits `feature_complete` on every re-run** — the idempotency guard is inert for the whole worktree population. `tasks_total` and `rework_cycles` on those rows are computed from a partial log.

## Role

Make finalize read and write one log, and correct the docstring.

## Edges

- #487 deliberately scoped this out: same root cause (#484 pinned only the `log_event` path), different verb, own blast radius.
- Decide the anchor per artifact as #487 did — the counters and the scan are lifecycle state, so they follow the write target.

## Touch-points

- `cortex_command/lifecycle/finalize.py` — `:56-58` docstring, `:185` root, `:192-195` counters and scan, `:198` write
