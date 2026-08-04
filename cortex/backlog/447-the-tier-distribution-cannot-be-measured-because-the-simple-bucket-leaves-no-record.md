---
schema_version: "1"
uuid: d7749b8a-3332-4463-b900-781a10abf051
title: The tier distribution cannot be measured, because the simple bucket leaves no record
status: wontfix
priority: medium
type: feature
created: 2026-08-04
updated: 2026-08-04
tags: ['lifecycle', 'tiering', 'telemetry']
areas: ['lifecycle']
---

## Why

A project can set a target distribution across `simple | moderate | complex` (the split landed
2026-08-03, `e3ee3b4c` + `d2e5394b`, to push more work onto lighter roads). **No such target is
falsifiable today**, because the bucket it most depends on leaves no record.

`simple` means "handle it directly, no lifecycle" — routed out by dev Step 1.4 and refine's Step 2
stop. So simple work produces no lifecycle directory, and often no backlog ticket at all. Any
distribution computed from `cortex/lifecycle/` or from backlog frontmatter is therefore conditioned on
*having entered the lifecycle*, which excludes the simple bucket by construction.

Measured on a consumer corpus over the first two days post-split: nine tickets entered the lifecycle,
one `moderate` and eight `complex`. Exactly two tickets were recorded `complexity: simple` in the same
window — and **both were written at close-out commits, not at Clarify**, i.e. recorded retroactively
when someone happened to. In this repo's own backlog, `complexity: moderate` appears **0 times across
438 tickets**.

Without an instrument, the question stays unanswerable and the same "too early to tell, sample too
small" conversation repeats indefinitely with no better data.

## Role

A report that counts what the tier assessment actually decided — including work that never entered the
lifecycle — so a distribution target can be evaluated against a denominator that includes the simple
bucket.

## Integration

The tier is decided at Clarify (`skills/refine/references/clarify.md` §5.2) and written back per refine
SKILL.md Step 2. Work routed out as `simple` never reaches the write-back, so the decision is made but
not recorded anywhere durable. The natural capture point is the assessment itself, not the backlog: a
Clarify concluding `simple` should still emit a counted record even though it creates no lifecycle
directory.

`cortex/lifecycle/sessions/<session-id>/bin-invocations.jsonl` already exists as a per-session
telemetry sink and may be a cheaper host than a new store.

## Edges

- The denominator is the hard part, not the counting. Work handled directly with no ticket and no verb
  invocation is invisible to any tooling; the report must state what it cannot see rather than silently
  presenting a biased ratio as the ratio.
- A distribution over lifecycle-entering tickets only is a **different metric** and must not be
  presented as the whole-population one — conditioning on entry changes the expected moderate-vs-complex
  split.
- **The target ratio itself is consumer calibration, not a harness universal.** It belongs in a
  consumer's `cortex/lifecycle.config.md` or CLAUDE.md. This ticket ships the *instrument*, never a
  built-in target.
- Sample selection dominates at small n. A window drawn from one narrow span of similar work is not
  representative; a report that does not expose the time window and work-type mix invites the
  over-reading it is meant to prevent.
- Retroactively-written tiers (recorded at close-out rather than at Clarify) are a different
  measurement than a Clarify-time decision and should be distinguishable in the output.
- Measurement only. It must not change routing, and must not become a reason to nudge an assessment
  toward a target — a tier is a judgment about the work, not a quota to fill.

## Touch points

- `plugins/cortex-core/skills/refine/references/clarify.md` §5.2 — where the tier is decided
- `plugins/cortex-core/skills/refine/SKILL.md` Step 2 — canonical write-back (and the `simple` stop)
- `plugins/cortex-core/skills/dev/SKILL.md` Step 1.4 — the other `simple` routing-out point
- `cortex_command/lifecycle_event.py` — `lifecycle_start`, `complexity_override` writers
- `cortex/lifecycle/sessions/<session-id>/bin-invocations.jsonl` — existing per-session telemetry sink
