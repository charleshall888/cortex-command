---
schema_version: "1"
uuid: d5da4a87-f3c9-4ad1-987f-b85b115379bc
id: "043"
title: "Wire review phase into overnight runner"
type: feature
status: complete
priority: medium
parent: "021"
blocked-by: []
tags: [overnight, review, quality, evaluator]
areas: [overnight-runner]
created: 2026-04-08
updated: 2026-04-08
session_id: null
lifecycle_phase: complete
lifecycle_slug: wire-review-phase-into-overnight-runner
complexity: complex
criticality: high
spec: lifecycle/wire-review-phase-into-overnight-runner/spec.md
---

# Wire review phase into overnight runner

## Origin

Spike 021 (define evaluator rubric) investigated whether an independent evaluator rubric was needed for overnight-built features. The investigation found that the existing review phase — designed to verify spec compliance via an independent agent — is never dispatched during overnight execution. The review infrastructure exists (`skills/lifecycle/references/review.md`), the gating matrix is defined (`skills/lifecycle/references/implement.md`), but `batch_runner.py` treats merged features as complete without consulting either.

## The structural gap

1. **`batch_runner.py`** merges features after implementation and marks them `status: "merged"` in overnight-state.json. It never checks the tier/criticality gating matrix and never dispatches a review agent.
2. **Morning review skill** (`walkthrough.md` section 2b) unconditionally batch-writes synthetic `review_verdict: APPROVED` events with `cycle: 0` for all merged features — no `review.md` produced, no spec compliance check performed.
3. **3 of 6 features** in the first post-019 overnight session (April 7-8, 2026) were complex-tier and should have been reviewed per the gating matrix, but were auto-approved without evaluation.

## What to implement

Add a post-merge review dispatch to the overnight pipeline for features that qualify per the existing gating matrix:

| Criticality | simple | complex |
|-------------|--------|---------|
| low         | skip   | review  |
| medium      | skip   | review  |
| high        | review | review  |
| critical    | review | review  |

The review agent already exists. The dispatch should:
- Read the feature's tier and criticality from events.log
- Consult the gating matrix
- If review is required: dispatch a fresh review agent per `skills/lifecycle/references/review.md`, producing a `review.md` artifact and logging a real `review_verdict` event
- If review is skipped: proceed to complete as today
- Bound the review with a cycle cap (max 2 cycles, matching the lifecycle convention) and a timeout

## Scope boundaries

- The morning review skill's synthetic approval events should become conditional: only write synthetic events for features that were intentionally not reviewed (simple/low), not for features that should have been reviewed but weren't
- Do not change the review phase criteria themselves — that is a separate concern (Alternative C from spike 021 research)
- Do not add a new evaluator agent — the existing review agent is sufficient
- The skepticism tuning protocol defined in spike 021's research.md should be applied after this ticket ships and produces real review data
