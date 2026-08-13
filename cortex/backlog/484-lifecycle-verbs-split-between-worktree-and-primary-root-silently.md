---
schema_version: "1"
uuid: 3d7c9a41-52be-4f08-9c6d-1a8e2f0b7c53
title: Lifecycle verbs split between the worktree and the primary root, silently
status: complete
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

## Resolution (2026-08-12)

**One anchor.** `cortex-lifecycle-event` (both the typed subcommands and generic `log`) and
`cortex-lifecycle-review-brief` now resolve `events.log` through
`cortex_command/lifecycle/log_resolver.resolve_events_log` — the same main-root-anchored resolver
`next` and `advance` already use, and the same one `advance_contract.anchor: "main-root"` names.
`log_resolver`'s own module docstring had recorded the CWD/main-root divergence as "the live hazard"
while deliberately leaving these two verbs on the CWD side; that carve-out is gone.

**Artifacts stay on the CWD**, and this is the one place the two anchors legitimately differ:
`review.md` is written by the reviewer where the work is and staged from there by
`stage-artifacts` (itself CWD-anchored), so `review-brief` splits its roots — main-root for the log
it derives the cycle from, CWD for the artifact directory and for the `git rev-parse`/`git diff`
that supply the baseline. Anchoring the artifacts at the main root too would have stranded them
outside the worktree being committed.

**Silence closed.** Every append now names its file on stderr (`wrote {event} ({feature}) → {path}`),
and `review-brief` closes with `cycle N · {mode} · log {path} · archived {name}` — emitted after any
`DEGRADED:` line so that contract's leading token is unchanged.

**Existing splits are reported, not just prevented.** `log_resolver.detect_split_log` returns the
CWD-anchored path a legacy caller *would* have written when it exists and diverges; both verbs warn
on it by name. Preventing new splits does not heal the one already on disk, and the worktree copy is
tracked — committing it merges a forked history.

### Also observed, resolved elsewhere

The `cortex-lifecycle-enter` / guard-R11 half is **not** fixed here — it is #475
(`cortex-auto-ensure0-cannot-be-honoured-inside-a-worktree`), which owns the unreachable
`CORTEX_AUTO_ENSURE=0` opt-out and the self-contradictory diagnostic. This ticket's evidence
(the guard pushing callers toward the primary root) is corroboration that `main-root` is the intended
anchor, which is what it was used for.

### A pre-existing test-isolation leak this exposed

`overnight/runner.py:2902` sets `os.environ["CORTEX_REPO_ROOT"]` in its own process — correct for a
runner, but under pytest that process is the whole suite, so the export outlived the test and every
later test inherited a root pointing at a deleted `tmp_path`. It went unnoticed because the verbs
reachable from those tests either ignored the variable (`_resolve_user_project_root_from_cwd`) or
pinned it themselves. Moving the lifecycle verbs onto the env-honouring resolver made 14 tests in
`test_review_brief_content.py` derive their log from the leaked path. Fixed at the source with an
autouse snapshot/restore fixture in `cortex_command/overnight/tests/conftest.py` — snapshot-and-restore
rather than deleting named keys, so the next export the runner adds is contained without anyone
remembering to.

### Verification

`cortex_command/lifecycle/tests/test_worktree_log_anchor.py` (new, 6 tests) drives both verbs from a
worktree CWD. Mutation-checked: reverting `resolve_events_log` to CWD resolution fails 5 of the 6.
Plus `detect_split_log` coverage in `test_log_resolver.py`, and `TestCwdResolution` in
`cortex_command/tests/test_lifecycle_event.py` rewritten — it pinned the *old* contract (CWD beats
`CORTEX_REPO_ROOT`), which is precisely the behaviour that split the log. Full suite: 5060 passed,
2 pre-existing failures unchanged (the #467-wontfix `.venv` symlink pair).
