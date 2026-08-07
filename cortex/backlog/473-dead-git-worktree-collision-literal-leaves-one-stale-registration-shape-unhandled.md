---
schema_version: "1"
uuid: 542b7b55-bf88-4fc9-a990-94d867bff7e9
title: Dead git worktree collision literal leaves one stale-registration shape unhandled
status: backlog
priority: low
type: bug
created: 2026-08-07
updated: 2026-08-07
tags: ['worktree-recovery']
areas: ['overnight-runner']
---
## Why

`_ensure_worktree` in `cortex_command/overnight/outcome_router.py` recovers a failed
`git worktree add` by matching git's stderr. One of the two literals it matches is dead, and a third
collision shape matches neither — so that shape falls through to the unknown-failure `RuntimeError`,
which `_merge_target_repo_path` turns into `None`, which defers the feature as
`integration worktree unresolved`. That is a recoverable session taking the unrecoverable path.

**Probed directly against git 2.55.0** (#465 review cycle 2), all four shapes:

| Shape | git 2.55 stderr |
|---|---|
| branch live in another worktree, ask for a different path | `'<branch>' is already used by worktree at '<path>'` |
| branch checked out in the main repo, ask for a worktree | `'<branch>' is already used by worktree at '<path>'` |
| worktree dir deleted (stale), ask for a **different** path | `'<branch>' is already used by worktree at '<dead path>'` |
| worktree dir deleted (stale), ask for the **same** path back | `'<path>' is a missing but already registered worktree; use 'add -f' …` |

- **`"already checked out at"` matches none of them.** It is dead on current git. This is
  pre-existing — before #465 it was the *entire* guard (`git show dac36ef8~1`). #465 added
  `or "already registered"`, which is the only reason in-place re-creation works today.
- **`is already used by worktree at` is handled nowhere**, so the prune-and-retry arm never fires
  for the stale-different-path shape.

Not a regression: behaviour is identical to HEAD before #465. Filed because the recovery arm two
comments describe has silently never run, and because the comments will mislead the next reader.

## Role

Match the wordings git actually emits, so stale-registration recovery fires for every shape it
claims to cover.

## Integration

- `cortex_command/overnight/outcome_router.py` — `_ensure_worktree`'s stderr matching and the
  comment at the different-path arm (~`:198-200`) that names the dead literal.
- `cortex_command/overnight/tests/test_outcome_router.py` — `TestHomeMergeWorktreeCollision`.
  (The docstring in `test_purged_home_worktree_recreated_in_place` was already corrected in
  `bc0ba5c5`; the `outcome_router.py` comment was left for this ticket.)

## Edges

- **Whether prune-and-retry is even right for the different-path shape is the design question, not a
  given.** `git worktree prune` clears a *dead* registration; if the registration is live, retrying
  the same add will fail again. Decide per shape rather than widening one match arm.
- These strings are version-specific. Pin them somewhere a git upgrade will surface, or match on a
  looser invariant — do not add a third bare literal.
- Reachability of the stale-different-path shape in this codebase is **unquantified**. The lazy path
  is deterministic per repo+session and the branch changes with the session, so it may be rare. Worth
  measuring before investing in the recovery arm — the comment fix stands regardless.
- Removing the dead `"already checked out at"` literal is safe on git 2.55 but would break any
  older git that does emit it; check the supported floor before deleting rather than keeping.

## Touch-points

Every overnight session that re-creates an integration worktree, cross-repo (`_effective_merge_repo_path`)
and home (`_merge_target_repo_path`) alike — both call `_ensure_worktree`.

## Evidence trail

`cortex/lifecycle/overnight-session-worktree-lives-in-tmpdir/review.md`, cycle 2, Issue 2 — holds the
full probe table and the `dac36ef8~1` provenance check.
