---
schema_version: "1"
uuid: ac7c0919-1eb4-4729-98b4-0a6d39177f03
title: "Fix morning report accuracy when post-merge steps fail"
status: backlog
priority: medium
type: bug
tags: [overnight-runner, report, morning-review]
areas: [overnight-runner, report]
created: 2026-04-11
updated: 2026-04-11
lifecycle_slug: null
lifecycle_phase: null
session_id: null
blocks: []
blocked-by: []
---

## Problem

When a feature merges successfully but a post-merge step (e.g. `dispatch_review`) throws an uncaught exception, the overnight runner marks the feature `failed` in state. The morning report then presents it as a genuine failure — same wording, same suggested action ("investigate and retry") — indistinguishable from a feature that never ran. This is misleading and causes unnecessary investigation work.

Observed in session `overnight-2026-04-11-1443`: both features merged to the integration branch but were reported as failed due to a `dispatch_review` crash (since fixed with a try/except). The report showed "0/2 completed, 2 failed" when the reality was "2/2 merged, post-merge processing crashed."

## Root Cause

Three gaps compound to produce the misleading report:

1. **No durable merge record before post-merge steps** — `_accumulate_result` in `batch_runner.py` does not write a `feature_merged` event to `overnight-events.log` immediately after `merge_result.success`. If post-merge code crashes, the events log has no evidence the merge occurred.

2. **`report.py` doesn't cross-check the integration branch** — `render_failed_features()` reads only `OvernightFeatureState.status`. It never checks whether a failed feature's commits actually landed on the integration branch. A post-merge crash looks identical to a pre-merge crash in the report.

3. **Morning review walkthrough (Section 4) has no branch check** — The walkthrough presents failed features and asks about investigation tickets with no awareness of the integration branch. The suggested action ("investigate and retry") is wrong when the feature merged.

## Acceptance Criteria

- AC1: After `merge_result.success` in `_accumulate_result`, a `feature_merged` event is written to `overnight-events.log` before any post-merge steps run. If post-merge processing then crashes, the events log correctly reflects the merge.
- AC2: `render_failed_features()` in `report.py` cross-references failed features against the integration branch (via merge commit inspection or events log). Features marked failed whose commits appear on the integration branch are annotated: `"merged to integration branch — failure in post-merge processing"` with a distinct suggested action.
- AC3: The morning review walkthrough (Section 4 in `~/.claude/skills/morning-review/references/walkthrough.md`) checks the integration branch for each failed feature before presenting it. If the feature is present, it is annotated as "merged — failure was post-merge" and the suggested action reflects this.
- AC4: Existing tests pass; no regression in the happy path (successful merge → no spurious annotation).
