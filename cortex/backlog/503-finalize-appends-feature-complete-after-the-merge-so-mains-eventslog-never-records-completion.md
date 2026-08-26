---
schema_version: "1"
uuid: 37ee3ec0-093a-4418-a904-eedaf08da174
title: finalize appends feature_complete after the merge, so main's events.log never records completion
status: wontfix
priority: medium
type: bug
created: 2026-08-25
updated: 2026-08-25
tags: ['lifecycle', 'events-log', 'complete']
areas: ['tooling']
blocked-by: []
blocks: []
---
Filed from wild-light, 2026-08-25, during a memory audit that asked which recorded traps should be tool fixes instead.

## Why

Complete's ordering guarantees the **last lifecycle event misses its own merge**.

Step 5 opens the PR and pauses. The merge happens. **Then** `cortex-lifecycle-finalize` runs and
appends `feature_complete` to `cortex/lifecycle/<slug>/events.log`. That append is by construction
*after* the merge commit, so it lands on the feature branch and `main` never receives it — unless
someone pushes a second follow-up PR carrying one line.

## Measured consequence

On `main`, a completed lifecycle's `events.log` ends at `pr_opened`. Every reader that reduces phase
from the event log therefore sees an unfinished lifecycle for work that shipped. This is silent and
permanent: nothing errors, and the branch that holds the truth is usually deleted after the merge.

It also compounds the SessionStart "incomplete lifecycles" prompt, which offers finished features as
resumable work.

## Suggested fix

Either:

1. **Emit `feature_complete` before the merge** — at PR-open time with a `pending` qualifier that the
   merge resolves, so the event is on the branch that gets merged; or
2. **Have finalize write to `main` directly** rather than to the current branch, since by definition
   it runs after the merge and the branch is about to disappear; or
3. **Reduce completion from the backlog item's terminal `status:`** rather than from the event log,
   and treat a missing `feature_complete` as normal.

Whichever way it goes, the current shape cannot be made correct by the caller — a human cannot append
the event to a branch that has already merged without opening a second PR for one line, which is what
wild-light has been doing.

---

## Resolution — 2026-08-25: refuted by the corpus, closed unbuilt

The claim is that on `main` a completed lifecycle's `events.log` ends at
`pr_opened`. Measured over every event log in this repo:

```
logs=369  with_feature_complete=322  ending_at_pr_opened=0
```

Zero of 369 logs end at `pr_opened`, and 322 carry `feature_complete`. The
mechanism the ticket assumes is not the one in place:

- `finalize` resolves `events.log` through `log_resolver.resolve_events_log`,
  which anchors to the **main repo root** — not to the invoking worktree. The
  append lands in the primary checkout, not on a branch about to be deleted.
  (Its docstring records #490, which fixed exactly the opposite bug: the
  idempotency scan reading the cwd log while `log_event` wrote the main-root one.)
- `complete.md` Step 11a then commits the finalization artifacts from that tree,
  so the row reaches `main` in the ordinary flow rather than needing a follow-up PR.

Suggestion 3 (reduce completion from the backlog item's terminal `status:`) is
still an idea worth having, but it is not this bug and has no measured cost
behind it here.
