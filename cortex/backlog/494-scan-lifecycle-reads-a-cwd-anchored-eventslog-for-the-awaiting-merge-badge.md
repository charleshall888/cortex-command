---
schema_version: "1"
uuid: 8ea6b22d-954f-48df-af80-98fd42203d94
title: scan_lifecycle reads a CWD-anchored events.log for the awaiting-merge badge
status: complete
priority: medium
type: bug
created: 2026-08-13
updated: 2026-08-19
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

---

## Decision on close, 2026-08-19 — the badge follows the pinned log, and it could not be fixed alone

**Decision: follow the pinned log.** The statusline describes the session's lifecycle state, and post-#484
that state lives in the main-root `events.log`. A worktree's copy is a committed snapshot no verb writes
to any more, so leaving the reader CWD-anchored means rendering a phase from a file that stopped changing.

**The badge was not a separable unit.** Scoping this to `:1017-1027` would have produced a worse state
than either anchor alone: the badge decorates `encoded`, which comes from `resolve_lifecycle_phase`
(`:991`) — and that resolver reads events from the same CWD-anchored `feature_dir`. `_is_stale` (`:464`)
and `_events_log_meta` (`:332`) read it too. Fixing the badge alone would have gated a main-root-derived
promotion on a worktree-derived phase.

So the fix is two-anchor throughout the scan, matching the convention rather than inventing one:
directories stay CWD-anchored (they are tracked artifacts — plan progress must come from the tree being
worked in), while every `events.log` read takes an explicit path. `resolve_lifecycle_phase` and
`_phase_from_machine_rows` gained an optional `events_log` argument defaulting to
`feature_dir / "events.log"`, so all nine existing callers are unchanged.

Two things found while building it, neither in the ticket:

- **The resolver must walk from the payload `cwd`, not the process CWD.** `resolve_main_repo_root()`
  starts at `Path.cwd()`, which is not the session's tree when the hook is invoked from elsewhere; using
  it dropped a fresh lifecycle out of the scan entirely (`test_staleness_filter_drops_old_lifecycles`).
  The helper parses the worktree gitfile from `cwd` instead.
- **`CORTEX_REPO_ROOT` is deliberately not consulted here.** The statusline names the tree the session is
  in; an env pin left over from another context would relabel it.

Cost, measured on the repo's own benchmark (90 candidates, 10 iterations): p50 6ms → 6ms, p99 6ms → 7ms.
Still git-free — the gitfile pointer is parsed in pure Python — and `None` in a primary checkout, where
the two anchors coincide and no path is built at all.
