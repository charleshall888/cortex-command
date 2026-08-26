---
schema_version: "1"
uuid: eae6ad03-f93f-4277-a73a-b50e30a19319
title: Lifecycle verbs disagree on repo root inside a worktree, splitting one event log across two trees
status: wontfix
priority: medium
type: bug
created: 2026-08-25
updated: 2026-08-25
tags: ['lifecycle', 'worktree', 'repo-root']
areas: ['tooling']
blocked-by: []
blocks: []
---
Filed from wild-light, 2026-08-25, during a memory audit that asked which recorded traps should be tool fixes instead.

## Why

Lifecycle verbs do not agree on which repository they are operating on when the caller is inside a
`git worktree`. Two wild-light memories exist purely to work around this, and three separate sessions
hit it independently on 2026-08-12 (#489, #495, #483).

**The split:** `advance` and the phase reducer anchor to the **primary checkout**, while `event`,
`register-artifact` and `record-pr-opened` resolve from **cwd**. The result is one lifecycle whose
event log is split across two `cortex/` trees, with neither half complete.

`cortex-lifecycle-complete-route` has the same root cause with a worse symptom: run from the primary
worktree it answers about the **primary's current branch**, so when the primary happens to sit on
`main` it returns `on_main -> step9` — "finalize now, no PR" — for a feature that is not on main at
all. Confirmed on #425 (2026-08-13): `first_run` from the worktree and `on_main` from the primary, in
the same minute.

## Measured consequence

The documented workaround is for the human to `export CORTEX_REPO_ROOT="$PWD"` at the start of any
lifecycle work in a worktree. That is a real mitigation for the event-log split, but it does **not**
fix `complete-route` — that verb's `on_main` branch reads the cwd tree's current branch regardless of
the env var, so exporting it changes nothing.

A wrong `complete-route` answer skips the PR and finalizes a branch that was never merged.

## Suggested fix

Resolve the repo root **once**, in one place, and have every verb use it — honouring
`CORTEX_REPO_ROOT` uniformly when set. Then make `complete-route` answer about the **lifecycle's own**
branch (the one carrying its artifacts), not about whatever branch the resolved tree happens to have
checked out.

A cheap intermediate: have any verb that resolves a repo root print it in its JSON envelope, so a
split is visible in the transcript instead of only in the damage.

---

## Resolution — 2026-08-25: already fixed here, closed unbuilt

Verified against this repo's code, not against the wild-light install the ticket
was filed from. Both halves of the Why are closed:

- **The event-log split** was closed by **#484**. `cortex_command/lifecycle/log_resolver.py`
  now pins **one** main-root-anchored, worktree-aware resolver that every appending
  verb uses, and its module docstring names this exact incident as the motivating
  failure. `detect_split_log` is the reporting half: an already-split lifecycle is
  surfaced rather than merely prevented going forward.
- **`complete-route`'s `on_main` arm** is no longer branch-only. It is gated on
  `_find_slug_worktree(slug) is None` — when a worktree for the slug exists the
  route falls through to the orphan probe, which converges on "go create the PR"
  or refuses retryably. The precise failure the ticket describes (finalize a
  branch that was never merged, because the primary happened to sit on `main`)
  cannot be reached.

`cortex_command/lifecycle/tests/test_worktree_log_anchor.py` pins both, and its
docstring records the same observed failure.

The one thing NOT verified is which released wheel wild-light is running — if it
predates #484/#487 the symptoms there are real and the fix is to upgrade, not to
build anything.
