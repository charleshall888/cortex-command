---
schema_version: "1"
uuid: 0e9d4947-446d-4bae-9597-d8ee9956816c
title: 'complete-route Branch 1 is dead code: wontfix_cli archives the directory before appending feature_wontfix'
status: complete
priority: medium
type: bug
created: 2026-08-13
updated: 2026-08-19
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

---

## Verdict on close, 2026-08-19 — Branch 1 earns its place; it was reading the wrong path

Deletion was the wrong call, and the ticket's own framing ("a branch whose producer cannot reach it")
inverted once the fall-through was measured rather than reasoned about. Running the real verb on a real
wontfix'd slug from the primary on `main`:

```
$ cortex-lifecycle-complete-route add-platform-abstraction-package-for-windows
{"route":"on_main","terminal":false,"continue_to":"step9",...}
```

`step9` is **Finalize**. Deleting Branch 1 would have made that the permanent behaviour: the abandoned
feature's backlog item marked complete and a `feature_complete` row emitted. Off `main` the same
fall-through lands on `first_run`/`step1` and restarts the lifecycle. Both are worse than a dead branch,
so the fix is to make the branch reachable, not to remove it.

`classify()` now falls back to `cortex/lifecycle/archive/{slug}/events.log` when the live directory is
gone — live-first, so a lifecycle re-entered under a reused slug never consults its archived predecessor.

Corpus re-measured 2026-08-19 and unchanged: 0 live `feature_wontfix` rows, 19 archived. The escape hatch
was checked and left alone — the live scan still runs first, so an operator's hand-run
`cortex-lifecycle-event log --event feature_wontfix` still reaches Branch 1.

**Wider than the ticket scoped, deliberately.** The same fallback feeds Branch 2, so the 134 archived
lifecycles carrying `feature_complete` now route `already_complete` instead of `on_main`/`step9`. That is
the same defect on the same line — a reader anchored at a path the writer no longer uses — and fixing
one half would have left `complete-route` re-finalizing the other 134.
