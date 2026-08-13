---
schema_version: "1"
uuid: 8ea6b22d-954f-48df-af80-98fd42203d94
title: scan_lifecycle reads a CWD-anchored events.log for the awaiting-merge badge
status: backlog
priority: medium
type: bug
created: 2026-08-13
updated: 2026-08-13
tags: ['lifecycle', 'worktree', 'statusline', 'hooks', 'observability']
areas: ['observability', 'lifecycle']
---
Split out of #487, whose Req 3 shifts what this hook sees.

## Why

`hooks/scan_lifecycle.py:832` anchors `lifecycle_dir = cwd / "cortex" / "lifecycle"` — strictly the process CWD, with no worktree awareness — and `:1017-1027` promotes a feature to `complete:awaiting-merge` only when that log carries `pr_opened` (and neither `feature_complete` nor `feature_wontfix`).

#487 moves the `pr_opened` append from a CWD-anchored path to the pinned main-root log. The badge therefore moves with it: worktree sessions stop showing `complete:awaiting-merge`, main-root sessions start.

## Evidence

Corpus measured 2026-08-13: **5** live `events.log` files carry a `pr_opened` row, 0 archived. #487 records the shift in its Changes to Existing Behavior and pins it with a test, but deliberately does not re-anchor this reader — it is an observability surface with its own area doc.

## Role

Decide whether the statusline badge should follow the pinned log like the other readers, or stay CWD-anchored by design.

## Edges

- **Depends on #487 landing** — before it, the row is written CWD-anchored and this reader agrees with its writer. Do not start until #487 is merged, or the premise is wrong.
- `cortex/requirements/observability.md` governs how a phase is rendered; `lifecycle.md` governs the state. This is a rendering question about a state artifact, so check both.
- The hook runs on every prompt, so it must stay git-free and fast — the worktree-aware walk parses a gitfile rather than shelling out, but confirm the cost before adding it to this path.

## Touch-points

- `cortex_command/hooks/scan_lifecycle.py:832` root, `:1017-1027` promotion
- `cortex/lifecycle/complete-route-reads-a-cwd-anchored/spec.md` — the Changes entry recording the shift
