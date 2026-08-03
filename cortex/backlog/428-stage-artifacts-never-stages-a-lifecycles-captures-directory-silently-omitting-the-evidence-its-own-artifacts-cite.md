---
schema_version: "1"
uuid: a56a1b6c-3e28-4bed-81c2-dcd6edc50bfd
title: stage-artifacts never stages a lifecycle's captures/ directory, silently omitting the evidence its own artifacts cite
status: backlog
priority: medium
type: bug
created: 2026-08-03
updated: 2026-08-03
tags: ['lifecycle', 'cli', 'git', 'evidence']
areas: ['lifecycle']
---
## Why

`cortex-lifecycle-stage-artifacts` builds a **fixed candidate list** per phase and never stages anything
else under the lifecycle directory. From `cortex_command/lifecycle/stage_artifacts.py:273-283` (refine):

```python
elif phase == "refine":
    submode = _detect_refine_submode(...)
    candidates.append(f"{lifecycle_rel}/research.md")
    if submode != "cancel":
        candidates.append(f"{lifecycle_rel}/spec.md")
    candidates.append(f"{lifecycle_rel}/index.md")
    candidates.append(f"{lifecycle_rel}/events.log")
    backlog_name = _resolve_backlog_filename(slug, root)
    ...
```

The `plan` and `complete` branches are the same shape — named `*.md` files plus `events.log`. **No phase
stages `cortex/lifecycle/{slug}/captures/`**, or any other subdirectory or file a phase legitimately
creates.

That matters because consumer repos are explicitly instructed to put durable evidence there. wild-light's
`CLAUDE.md` says, of frame captures: *"Copy PNG + manifest into `cortex/lifecycle/<slug>/captures/` if it
needs to outlive the day (`/tmp` is GC'd in 24h)."* The same directory is the convention for probe output,
measurement series, and baselines — e.g.
`cortex/lifecycle/rework-simulate-host-disconnect-loopback-harness/captures/post-fix-series.md`, which a
later ticket's spec cites as its provenance model.

So the verb silently omits exactly the artifacts a phase produced as *evidence*, while faithfully staging
the prose that cites them.

**Observed 2026-08-03 (wild-light #432 refine).** `stage-artifacts --phase refine` returned
`signal: "staged"` with five paths, omitting
`cortex/lifecycle/survivor-enet-detection-skew-up-to/captures/` — which held the probe dump and README
that the spec's decisive requirement (R4) is built on, and which the spec cites by path. Had the
orchestrator committed `staged_paths` as instructed, the spec would have shipped citing a capture file
that was never committed, and the evidence would have been GC'd from `/tmp` within a day.

This is **not** #417 (complete). That was the inverse defect — `staged_paths` derived from the whole git
index, over-reporting a concurrent session's files. This is under-staging of the verb's own lifecycle
directory, and #417's fix (deriving the report from the verb's own paths) makes it *more* likely to bite,
because the reported set is now exactly the hardcoded list.

## Role

Decide whether the per-phase candidate list should remain an allowlist of named files, or whether the
lifecycle directory should be staged as a unit with an explicit deny-list.

Candidate directions (none pre-selected):

- Stage `{lifecycle_rel}/` wholesale, minus a deny-list (`.session`, scratch/temp patterns). Simplest, and
  matches the "the lifecycle dir is the phase's output" mental model consumers already have — but the
  module's docstring advertises a deliberate "no-directory-glob discipline", so this reverses a stated
  design choice and needs that rationale re-read first.
- Keep the allowlist and add `captures/**` at every phase.
- Keep the allowlist and have the verb *report* unstaged files under the lifecycle dir (a
  `unstaged_in_lifecycle_dir` field), leaving the decision to the caller. Non-breaking; makes the omission
  visible instead of silent, which is the actual harm.

## Integration

- `cortex_command/lifecycle/stage_artifacts.py` — `_candidates()` (the three phase branches) and `stage()`.
- The module docstring's "no-directory-glob discipline" claim — whichever direction wins, reconcile it.
- Consumers that act on `staged_paths`: `skills/refine/SKILL.md` Step 5, `skills/build/references/complete.md`.

## Edges

- **The no-directory-glob discipline exists for a reason** — read it before reversing it. A wholesale
  directory add risks sweeping a `.session` marker or a concurrent session's scratch file into a commit,
  which is the #417 harm re-introduced from the other side.
- A capture directory can be large (PNGs). Wholesale staging changes commit sizes materially in
  render-heavy repos; that may be desirable (evidence outlives `/tmp`) but should be a decision, not a
  side effect.
- The `cancel` submode omits `spec.md` deliberately; any directory-level approach must preserve that.

## Touch points

- `cortex_command/lifecycle/stage_artifacts.py:260-290` (candidate construction), `:300+` (`stage()`)
- `cortex/backlog/417-stage-artifacts-reports-the-whole-git-index-as-its-own-staged-set.md` (the inverse
  defect, complete — read for the discipline rationale)
