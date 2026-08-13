---
schema_version: "1"
uuid: 3d7c9a41-52be-4f08-9c6d-1a8e2f0b7c53
title: Lifecycle verbs split between the worktree and the primary root, silently
status: backlog
priority: high
type: bug
created: 2026-08-12
updated: 2026-08-12
tags: ['lifecycle', 'worktree', 'events-log', 'cli']
areas: ['lifecycle']
---
Filed from wild-light, 2026-08-12, during `/cortex-core:build` on ticket #478
(`wet-sand-darkening-on-the-terrain`), run entirely from a git worktree.

## Why

**Different lifecycle verbs disagree about which `cortex/lifecycle/{feature}/events.log` is authoritative,
and neither warns.** Run from a worktree:

- `cortex-lifecycle-next` and `cortex-lifecycle-advance` use the **primary root**. `next`'s own
  `advance_contract.log_path` says so explicitly, with `"anchor": "main-root"`.
- `cortex-lifecycle-event` (all subcommands) and `cortex-lifecycle-review-brief` use the **worktree**.

So a lifecycle driven from a worktree writes half its history to one file and half to another. Both files
exist, both look plausible, and nothing reports a split.

## What it actually cost, twice in one session

**1. A cycle-2 review was labelled cycle 1, and the prior review was not archived.**
`cortex-lifecycle-review-brief` computes the cycle from the worktree's `events.log`, which is only the
committed copy and therefore stale — it had **zero** `review_verdict` rows while the primary's had cycle
1's `CHANGES_REQUESTED`. The brief came back `cycle 1 · full review` and did **not** archive the existing
`review.md`.

Dispatching on that brief would have (a) overwritten cycle 1's findings with no copy anywhere, and
(b) led the caller to pass `--cycle 1` to `cortex-lifecycle-advance review-verdict`, which routes
CHANGES_REQUESTED back to rework instead of escalating at the cap. **A lifecycle at its rework cap can
loop indefinitely and nothing looks wrong.** Caught only because the operator's agent hand-checked the
primary's log; the prior review was preserved by a manual `cp`.

**2. Three closing events vanished into the wrong file.** `cortex-lifecycle-event log`,
`phase-transition` and `feature-complete`, run from the worktree, appended to the worktree's copy. The
authoritative log still ended at `escalated`. All three commands **exited silently with no output**, so
there was no signal at all — the split was found only by tailing the primary's file directly. They had to
be re-run from the primary root.

## Also observed, same family

`cortex-lifecycle-enter` **refuses outright** inside a worktree — `cortex-lifecycle-init-ensure` guard R11
fires before anything else, including before the documented `CORTEX_AUTO_ENSURE=0` opt-out, which is
therefore unreachable. Its diagnostic prints the primary root as *both* the offending worktree and the
remedy ("invoked inside a git worktree (/path); run from the primary worktree (/path)"), which reads as a
contradiction. The workaround is to run `enter` from the primary — which is correct, and is evidence the
anchor is *meant* to be main-root everywhere.

## Role

Make every lifecycle verb resolve the same anchor, and fail loudly rather than silently when it cannot.

## Edges

- **`main-root` looks like the intended anchor** — `next` names it, `advance` uses it, and `enter`'s guard
  pushes you toward it. The verbs that use CWD are the outliers.
- **Silence is the sharpest part of the bug.** Both failures produced zero output. A verb that appends to
  a lifecycle log should say which file it wrote.
- **A split log is not self-healing.** The worktree copy is tracked, so committing it merges a divergent
  history into the repo, and reducers that read the "wrong" one report a plausible but false state
  (`cortex-lifecycle-state` returned only `criticality`/`tier` while the escalation was invisible to it).
- **The cycle counter is safety-critical**, because the rework cap is what stops an unbounded
  review/rework loop. Deriving it from a possibly-stale log removes that stop.

## Touch points

- `cortex_command/lifecycle/` — the `event`, `review-brief`, `next`, `advance` and `init_ensure` entry
  points, wherever the log path is resolved
- The `advance_contract.log_path` / `anchor: main-root` contract that `next` already emits — the other
  verbs should honour it rather than re-deriving
