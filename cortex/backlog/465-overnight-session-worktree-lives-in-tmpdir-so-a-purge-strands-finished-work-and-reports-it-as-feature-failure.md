---
schema_version: "1"
uuid: 4d90ab14-c32d-4c17-b52d-48007767d9d6
title: Overnight session worktree lives in $TMPDIR, so a purge strands finished work and reports it as feature failure
status: should-have
priority: low
type: bug
created: 2026-08-07
updated: 2026-08-07
---
## Why

Overnight session `overnight-2026-08-07-0252` (wild-light) reported **0/6 features
completed, 2 failed**. All three features that ran had in fact finished and committed
their work. The reported failure for both "failed" features was identical:

```
unexpected exception: [Errno 2] No such file or directory:
PosixPath('/var/folders/vl/8mmg3_854bx23pr_rjk7ns5h0000gn/T/overnight-worktrees/overnight-2026-08-07-0252')
```

The session's own integration worktree had disappeared out from under the runner. Work
committed fine on the per-feature `pipeline/*` branches; the **merge into the integration
branch** is what failed, because its target directory no longer existed. The integration
branch was left byte-identical to its 20-commits-stale base, and a PR was never created.

`cortex_command/overnight/plan.py:380` roots the session worktree at
`Path(os.environ.get("TMPDIR", "/tmp")) / "overnight-worktrees" / session_id`. On macOS
`$TMPDIR` is a per-user `/var/folders/...` path subject to periodic purge; anything there
is disposable by OS policy, and the session ran 01:52–03:48, comfortably long enough to be
swept. The runner treats that directory as durable session state for the whole run.

The severity is not the lost directory — it is that **finished work was reported as
failed**. Three features' output (33 files, +3075/−849, including two ADRs and a
511-line probe extraction) was stranded on unmerged branches, and the morning report
attributed it to feature failure with "Review learnings, retry or investigate" as the
suggested next step. Following that advice would have meant re-running work that was
already done. Recovery took a manual branch audit during morning review; nothing in the
report pointed at it.

## Role

Two separable fixes:

1. **Don't put durable session state on a purgeable path.** Root the session worktree
   somewhere with the lifetime of the session — alongside the repo (as the per-feature
   `.claude/worktrees/` already are), or an explicitly-managed dir — rather than
   `$TMPDIR`.
2. **Distinguish "work failed" from "merge target vanished."** An infrastructure fault
   between commit and merge must not be reported as feature failure. The report should
   name the stranded branches and say the work exists, so the operator's next step is a
   merge rather than a re-run.

## Integration

- `cortex_command/overnight/plan.py:378-380`, `:444-445` — worktree root
- `cortex_command/overnight/runner.py:2218` — same `$TMPDIR` assumption
- `cortex_command/overnight/report.py` — failure classification and next-step wording
- `cortex_command/overnight/gc_demo_worktrees.py` — already assumes `$TMPDIR` is sweepable
  for *demo* worktrees, which is correct there; the contrast is the point

Worth considering: a pre-merge existence check that re-creates the worktree from the
integration branch rather than raising, since the branch ref survives even when the
checkout does not.

## Edges

- **Non-goal**: recovering session `overnight-2026-08-07-0252`. Already merged by hand
  (wild-light PR #30).
- **Non-goal**: changing where *demo* worktrees live — `$TMPDIR` is right for those.
- The per-feature `pipeline/*` worktrees under `.claude/worktrees/` survived the same
  window, which is direct evidence the repo-adjacent location is the durable one.
- A fix must not assume the worktree disappearing is rare or detectable in advance; the
  OS gives no notice.

## Touch-points

- Source incident: wild-light `overnight-2026-08-07-0252`; morning report
  `cortex/lifecycle/sessions/overnight-2026-08-07-0252/morning-report.md`; recovery in
  wild-light PR #30
- Related: cortex-command #464 (ADR/backlog number collisions from the same session)
- Related: backlog #002 (morning report — surface failure root cause inline); this is a
  concrete case where the surfaced cause actively misled
