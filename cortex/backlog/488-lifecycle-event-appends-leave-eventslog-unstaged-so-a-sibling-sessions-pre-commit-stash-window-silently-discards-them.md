---
schema_version: "1"
uuid: 8e6028c5-170a-4561-b83b-2fef31a5d0d7
title: Lifecycle event appends leave events.log unstaged, so a sibling session's pre-commit stash window silently discards them
status: complete
priority: high
type: bug
created: 2026-08-13
updated: 2026-08-19
tags: ['lifecycle', 'events-log', 'concurrency', 'pre-commit']
areas: ['lifecycle']
blocked-by: []
blocks: []
---
Filed from wild-light, 2026-08-13. This is the upstream half of wild-light's
`488-concurrent-sessions-lose-lifecycle-eventslog-writes-to-pre-commits-stash-window`; the hook-scoping
half stays downstream in the consumer repo that configures its own pre-commit set.

## Why

`pre-commit` stashes unstaged **tracked** changes before running hooks and restores them afterwards.
When a sibling session commits while this session has just appended to
`cortex/lifecycle/{slug}/events.log`, that append is unstaged and tracked, so it goes into the sibling's
stash and does not come back. The tree returns **clean and matching HEAD with an empty `git stash list`**
— no conflict, no error, nothing to notice.

`events.log` is the sole reduction source for phase, criticality, tier and pause state. A dropped append
silently rewinds the state machine, and the verb that wrote it already reported success.

`_append_event_atomic` writes and flocks the file but never stages it. Pre-commit's stash spares
**staged** content, so a `git add` of the resolved path in the same process as the append closes the
window without any locking.

## Evidence

wild-light #476 implement + review, 2026-08-06:

- Two advance-verb emissions — a `plan-decision` `phase_transition` and a `batch_dispatch` — each
  returned `{"advanced": true, "emitted": [...]}` and then **vanished from `events.log`**. The next
  `cortex-lifecycle-advance` refused with *"an active feature_paused (slug='plan-approval') is
  unresolved"* for a pause that had already been cleared.
- **4 of 8** builder subagents in one wave hit edit-reversion in the same window; one file reverted four
  times.

wild-light #495, 2026-08-12: `cortex-lifecycle-advance implement-transition --mode transition` returned
`{"advanced": true, "emitted": ["phase_transition"]}` and the event existed in **no** log on disk,
verified by `grep -rl` across all four worktrees holding that lifecycle dir.

wild-light backlog sweep, 2026-08-12: the restore leg can **duplicate rather than discard**. After
re-applying clobbered edits and committing, pre-commit's own restore
(`[INFO] Restored changes from …/patch1786556835-8395`) re-applied a pre-clobber copy *on top of* the
re-applied version, committing two byte-identical copies of the same content. This matters to the fix
because the standard defence — "verify on disk, don't trust the success line" — **passes** against a
duplicated append: the row is present and the frontmatter is well-formed. Only counting occurrences
catches it. A staged `events.log` is outside the stash entirely and so is immune to both legs, which is
the argument for staging over any detect-and-repair approach.

## Not #135

#135 (`shared-git-index-race`, wontfix 2026-04-29) declined an advisory-`flock` fix for the **index**
race, on three grounds that do not carry here:

- *"Bug observed once"* — this one has recurred across #476, #495 and #538, in independent sessions.
- *"Lock-based fix is incomplete ... `just build-plugin` writes into the shared working tree regardless"*
  — this asks for no lock. It is a `git add` of one path at append time.
- *"~250 LOC plus tests"* — the surface here is `_append_event_atomic` plus its callers.

#135's conclusion that per-agent worktree isolation is the right architecture is not contradicted by
this; it is the cheap guard for the state file until that lands, and #484 has since shown worktree
isolation carries its own anchor hazards.

## Role

Ensure a lifecycle event append survives a sibling session's pre-commit stash window, without
introducing a lock.

## Edges

- **Staging has side effects.** `git add` on the resolved `events.log` leaves content staged that the
  session did not choose to stage, which changes what a subsequent bare `git commit` picks up. Consumers
  are already told to use `git commit --only -- <pathspec>`; confirm that assumption before relying on it.
- **The resolved path is the main root now** (`log_resolver.resolve_events_log`, #484), so from a worktree
  the `git add` must run against the main root's index, not the worktree's.
- **Failure must be visible.** If the stage fails, the append should say so rather than reporting the same
  success it reports today — silence is what made the original loss undetectable.
- **This does not cover the other artifacts** lost in the same window (`plan.md` task checkpoints were
  also dropped in #476). Scope is `events.log`; whether `plan.md` deserves the same treatment is a
  separate call.

## Touch-points

- `cortex_command/lifecycle_event.py` — `_append_event_atomic` and its callers
- `cortex_command/lifecycle/log_resolver.py` — `resolve_events_log`, `resolve_flock_path`
- `cortex_command/lifecycle/advance.py` — the emitting verb that reports `advanced: true`
- `cortex/backlog/135-shared-git-index-race-between-parallel-claude-sessions-causes-wrong-files-to-land-in-commits.md`
  — the wontfix this must be read against

---

## Amendment 2026-08-19 — `cortex/backlog/*.md` belongs in this ticket's scope, not the consumer's

Routed here from wild-light on a re-read of the 2026-08-13 split. That split left "the
`cortex/backlog/*.md` reversion class" downstream on the reasoning that staging `events.log` upstream
would not help backlog status flips. True as far as it goes — but it does not follow that the fix is
downstream. **Those files are written by this codebase**, by `cortex_command/backlog/update_item.py`,
and no production write path in `cortex_command/backlog/` or `cortex_command/lifecycle/` calls
`git add` (grepped 2026-08-19; the only hits are in `tests/`). A consumer repo has nothing to change.
It is the same defect as `events.log`, on a different file family, with the same remedy.

**It is the worse of the two, and that inverts the usual priority argument.** An `events.log` loss
self-announces: the next `advance` contradicts reality and refuses. A lost `status:` flip announces
nothing. The ticket stays `backlog`, keeps surfacing in `cortex-backlog-ready`, and reads as
never-triaged. The only detector is re-reading frontmatter after the window closes, and nothing prompts
that. Original evidence: nine backlog items reverted wholesale in one session, `git status` clean,
mtimes identical (wild-light #488, Amendment 2026-08-12).

**Scope note, not a demand to widen this ticket.** If staging is the chosen mechanism it should be one
mechanism applied at each write site, rather than a special case in `_append_event_atomic`. The Edges
above carry over unchanged — staging has side effects, the resolved path may be the main root, and a
failed stage must be loud. `generate_index.py` writes `cortex/backlog/index.{md,json}` in the same
breath as a mutation, so a backlog stage that covers the item but not the index leaves the pair
inconsistent in the index rather than in the working tree.

Splitting this off into its own ticket is a reasonable call. What is not reasonable is leaving it
downstream, where the code does not live.

---

## Resolution, 2026-08-19 — one `stage_path` helper, applied at both write families

`common.stage_path(path)` runs `git add` with `cwd` set to the file's own directory, so the index it
stages into is the one that actually owns the file — the Edge's point, and it matters post-#484 because
the resolved `events.log` is the *main root's* even when the session's CWD is a worktree. Staging into
the worktree's index would protect nothing. Pinned by a real `git worktree add` test, not reasoned about.

Applied at `_append_event_atomic` (this ticket) and at both backlog item writers, `create_item` and
`update_item` (the amendment). One mechanism, as the amendment asked, not a special case in the append.

Edges, answered:

- **Failure is loud.** A stage that fails writes to stderr rather than reporting the same success. Two
  cases are silently fine because neither can be stashed: the file is outside a git repository, and the
  file is ignored — `pre-commit` stashes *tracked* changes, so an untracked file was never at risk.
- **Staging has side effects,** and the assumption was confirmed rather than relied on: this repo's
  commit skill uses `git commit --only -- <pathspec>`, so content staged but not named is not swept.
- **Staging runs outside the flock.** It is a separate git process and does not need the append lock;
  holding the lock across a subprocess would widen the window every other appender waits on.

**Cost, and one thing it broke.** The first implementation classified before staging — is this a repo, is
the file ignored — at three git invocations per append. That is real overhead on a frequent operation, and
it broke `test_merge_sha_capture` outright: `patch.object(review_dispatch.subprocess, "run", …)` patches
the attribute on the shared `subprocess` module, so a command-blind stub handed its queued HEAD SHAs to
the new `git add` calls and collapsed the before/after pair the rework circuit-breaker compares. The
classification now runs only when there is a failure to explain, so the happy path is **one subprocess,
~10ms**, and the stub was made command-aware — it should never have been answering calls it was not
written for.

**`generate_index.py` deliberately not wired.** `index.{md,json}` are gitignored here, so staging them is
a no-op, and where a consumer tracks them a stale index is self-healing: the next mutation regenerates it.
Three more git calls per regeneration is not worth a transient the tool already repairs.

**Not covered.** `plan.md` task checkpoints were lost in the same window (#476) and are still unstaged.
Whether artifact writes deserve the same treatment is a separate call, exactly as the Edges say.
