---
schema_version: "1"
uuid: b77ea33f-4397-4945-be86-4ad4fb861253
title: "Overnight review gate crashes to cycle-0 ERROR and leaves deferred/errored code merged"
status: in_progress
priority: high
type: bug
created: 2026-06-09
updated: 2026-06-09
complexity: complex
criticality: high
spec: cortex/lifecycle/overnight-review-gate-crashes-to-cycle/spec.md
areas: ['overnight-runner']
lifecycle_phase: plan
---
Observed in wild-light overnight run `overnight-2026-06-09-0222` (2/4 features deferred, but their code shipped on the integration branch).

## Bug A — review sub-agent crashes on dispatch (systemic)
The review sub-agent exits 1 ~134-176ms after `dispatch_start`, before writing `review.md`. `dispatch_review()` then calls `parse_verdict(<missing review.md>)` which returns the sentinel `_ERROR_RESULT = {"verdict":"ERROR","cycle":0,"issues":[]}` (`pipeline/review_dispatch.py:48,70-71`). Two independent features (#206 perf, #202 climb) produced byte-identical crashes → systemic review-agent dispatch failure, NOT per-feature. Evidence: `pipeline-events.log:657` and `:1079` (`ProcessError: Command failed with exit code 1`). `cycle:0` is the sentinel for "no review happened" — it should not be treated as a normal verdict.

## Bug B — merge-then-defer never rolls back
`outcome_router.py:984` merges the feature into the integration branch BEFORE review runs (`:1006`). The deferred/ERROR path (`:1019-1040`) emits FEATURE_DEFERRED and cleans up the worktree but never reverts the merge. The only auto-revert is test-failure-scoped inside `merge_feature` (`pipeline/merge.py:301-323`); `revert_merge()` (`merge.py:335`) is never called on a review verdict. Result: a crashed/deferred review leaves unreviewed (and possibly incomplete/broken) code on the branch — it then ships in the session PR.

## Impact
In this run the combination shipped runtime-broken #202 climb (called a world_root API that was never implemented) + incomplete #206 perf onto the PR with a green-looking summary.

## Suggested fixes
1. Diagnose the review subprocess exit-1 (auth token / CLI invocation / prompt-or-spec path unreadable in the detached runner); on a review-dispatch error, FAIL LOUD or retry rather than silently defer.
2. Either call `revert_merge()` when `rr.deferred`/ERROR, or move the merge to AFTER an APPROVED verdict so non-approved features never linger on the integration branch.