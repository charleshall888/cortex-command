---
schema_version: "1"
uuid: 1a50e528-0277-4078-8ae6-b1d0bf2f4d66
title: A rework re-review re-reads the whole spec with no way to scope it
status: complete
priority: medium
type: feature
tags: ['lifecycle', 'review', 'rework', 'cost']
areas: ['lifecycle', 'skills']
complexity: complex
criticality: high
updated: 2026-08-07
spec: cortex/lifecycle/a-rework-re-review-re-reads/spec.md
lifecycle_phase: complete
---
## Why

`skills/build/references/review.md` has **no cycle awareness**. Its Stage 1 / Stage 2 split keys on tier
and criticality only, so a cycle-2 review after a rework is specified identically to cycle 1: read every
requirement in the spec, rate each PASS / FAIL / PARTIAL, then code quality.

But cycle 2's actual question is much narrower — *did the flagged issues get closed, and did any fix break
something?* — and its input is a small, enumerable diff bounded by the previous cycle's `issues` array.
Re-reading a 25-requirement spec to answer it is mostly waste, and the waste is not marginal: at
`criticality: high|critical` review is **forced at every tier**, so every rework pays it.

The cost is real enough that it gets improvised around. In one observed run the operator asked for "a
lighter review this time" and the orchestrator hand-scoped the reviewer brief — deciding on the fly what to
check, what to skip, and how to describe the baseline. That improvisation is where a re-review quietly
stops covering things, and nothing in the protocol records what was skipped.

## Role

Make "check the fixes, not the whole spec" a supported mode with stated limits, rather than something each
orchestrator re-invents per rework.

## Integration

A rework-scoped review keyed on `cycle ≥ 2`, taking the previous cycle's `issues` array as its checklist
and the rework diff as its reading scope. Its output stays the same shape — per-issue disposition, new
problems found, `## Requirements Drift`, Verdict JSON — so downstream parsing is unchanged.

The one thing it must carry that cycle 1 does not: **requirements rated in cycle 1 and untouched by the
rework keep their rating by reference**, stated explicitly rather than silently re-asserted. A cycle-2
review that prints PASS for a requirement it never re-read is worse than one that says "unchanged since
cycle 1, not re-read."

## Edges

- **A scoped review is a rubber stamp unless it can still escalate on something outside the checklist.**
  The scoping is about where it *reads*, never about what it is allowed to *conclude*.
- **Fixes do introduce new problems, so "new problems from the fixes" is the load-bearing half, not a
  formality.** In the observed run a correct fix widened a name-pin so that it tripped an unrelated
  registry test, and the resulting red was caught only by a full suite run afterwards — not by the fix's
  own scoped verification.
- **Cycle-≥2 `CHANGES_REQUESTED` escalates rather than looping**, so a scoped reviewer needs that told to
  it: findings that belong in a follow-up ticket go in the review body, not in a verdict that halts the
  lifecycle — and equally it must not approve to dodge the escalation. Related: the escalation-resolution
  gap filed separately.
- **The baseline handoff is where scoping most easily goes wrong.** § 1 says to re-run the test command if
  commits land after the baseline. On a rework that is *always* true, and a re-run of a long suite may or
  may not be warranted depending on whether the rework touched source at all — the protocol should say how
  to decide rather than leaving it to judgement.
- **Adjacent robustness gap worth folding in:** § 3 handles a reviewer that produced a *partial* artifact
  (missing `## Requirements Drift` → re-dispatch once), but not one that produced **no artifact at all**.
  In the observed run the reviewer went idle having done the work with `review.md` never written; detecting
  that and resuming the same agent — rather than dispatching a fresh one that re-derives everything — was
  left to the orchestrator to notice.

## Touch points

- `skills/build/references/review.md` — §§ 1–4, which currently describe one review shape
- `skills/build/SKILL.md` — § Criticality, whose table maps criticality/tier to review depth with no cycle
  axis
- `cortex-lifecycle-next` — already serves `cycle` in its `evidence_trace`, so the discriminant exists
- `cortex-lifecycle-advance review-verdict` — `--cycle`, already threaded

## Provenance

Observed in a consumer lifecycle, 2026-08-05: a 12-issue rework at `criticality: critical` / `tier: complex`
whose cycle-2 review was hand-scoped to the rework diff because the protocol offered no scoped mode.
