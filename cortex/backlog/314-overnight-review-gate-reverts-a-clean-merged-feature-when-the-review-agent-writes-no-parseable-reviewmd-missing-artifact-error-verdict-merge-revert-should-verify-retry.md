---
schema_version: "1"
uuid: 5d53b7ec-f758-4ebf-bee2-03e1fa24143a
title: overnight review gate reverts a clean merged feature when the review agent writes no parseable review.md (missing artifact -> ERROR verdict -> merge revert; should verify + retry)
status: in_progress
priority: high
type: bug
created: 2026-06-23
updated: 2026-06-23
lifecycle_phase: research
lifecycle_slug: overnight-review-gate-reverts-a-clean
complexity: complex
criticality: high
---
## Summary

The overnight review gate **reverts a correctly-built, already-merged feature** when the review agent finishes normally but does not emit a parseable `review.md`. `parse_verdict()` defaults a missing/malformed file to `verdict="ERROR"`, and `outcome_router` classifies any `ERROR` verdict as `review_dispatch_crashed` / `could_not_run` and reverts the merge. A tooling/model-adherence miss (the agent didn't write the artifact) is thereby allowed to discard verified, merged work — and it is mislabeled as a "crash" even though the dispatch completed cleanly.

## Impact

A feature that built, passed its hooks, and merged to the integration branch can be silently rolled back because the review *agent* failed to produce the review artifact — not because the code had any problem. The work is only recoverable on its `pipeline/<feature>` branch; the integration branch loses it and the run reports it as deferred/crashed. Distinct from #313 (Sonnet+xhigh effort) and arguably more damaging because it discards already-verified work.

## Observed (wild-light overnight-2026-06-23-0605, feature `occlusion-field-max-ray-steps24-under`)

- Implement succeeded: 3 tasks, 3 commits (`bb164400`, `1f780510`, `529ad598`), all exit-reports `action: complete`. `feature_merged` to `overnight/overnight-2026-06-23-0605` at 08:07:55Z.
- Review dispatched (`pipeline-events.log`): `dispatch_start skill="review" model="sonnet" effort="high" max_turns=30`.
- Review completed **normally**: `dispatch_complete stop_reason="end_turn", num_turns=17, duration_ms=189930 (~3.2m), cost_usd=0.65`. No crash, no timeout, no turn/budget exhaustion.
- Sandbox was not restricting it: the review spawn's deny-list `feature-occlusion-...-review-attempt1.json` has `deny_paths: []`.
- **No `review.md` was written** anywhere for this feature (absent in both the worktree and the main-repo lifecycle dir), while a dozen other features in the same worktree have one.
- Result event: `feature_deferred {"review_verdict":"ERROR","review_cycle":0,"merge_reverted":true,"review_dispatch_crashed":true,"could_not_run":true}` → the clean merge was reverted.

## Root cause (cortex_command)

1. `pipeline/review_dispatch.py:60` `parse_verdict()` — docstring: *"Returns `{"verdict":"ERROR",...}` if the file does not exist or the JSON block is malformed."* Needs a fenced ```json {...}``` block.
2. `pipeline/review_dispatch.py:131` `dispatch_review()` step (5): `verdict_str = verdict_dict.get("verdict", "ERROR")`. It calls `parse_verdict()` **without checking the `dispatch_task` result** (`stop_reason`/success) or **whether `review.md` was actually written**. A normally-completed agent that wrote no artifact is indistinguishable from a genuine verdict.
3. `overnight/outcome_router.py` (~1144/1156, ~1468/1480): `if rr.verdict == "ERROR": deferred_details["review_dispatch_crashed"]=True; deferred_details["could_not_run"]=True; ... _record_review_crash_systemic(...)`, and the merge is reverted. "No artifact" is conflated with "review found a blocking error," and the penalty is reverting verified merged code + feeding the systemic circuit breaker.

## Why the agent wrote nothing (contributing)

The Sonnet review agent reached `end_turn` after 17 turns without emitting the `review.md` JSON verdict block the prompt requires (likely produced its review as a final chat message instead of writing the artifact). The artifact write is the contract but isn't enforced/verified. Hardening the review prompt/skill for artifact-write robustness on Sonnet would reduce occurrences, but the gate must be robust to it regardless.

## Suggested fixes (any/all)

1. **Verify the artifact before treating absence as a verdict.** In `dispatch_review`, after `dispatch_task`, check `result` (success/`stop_reason`) AND `review_md_path.exists()` with a parseable verdict block. Distinguish "no artifact produced" (tooling/adherence failure) from a real verdict.
2. **Retry / escalate on a missing artifact** instead of returning `verdict="ERROR"` — re-dispatch the review (optionally escalate Sonnet→Opus) up to N times; only then surface a deferral.
3. **Never revert an already-merged, otherwise-passing feature solely because the review tooling failed to produce a file.** Preserve the merge and surface a clear "review could-not-run — needs human re-review" deferral that does NOT discard verified work (and reconsider feeding a tooling no-op into `_record_review_crash_systemic`).
4. **Rename the signal** — `review_dispatch_crashed` is misleading when `dispatch_complete stop_reason="end_turn"`; separate "agent crashed" from "agent produced no parseable verdict."
5. Minor: the review was dispatched with `complexity="complex"` though the feature is `simple` — fix the dispatch metadata to use the feature's actual complexity.

## References

Same run as #313 (overnight-2026-06-23-0605). Related: #043 (wire review phase), #076 (extract outcome_router), #308/#309 (undiagnosable failures / no-exit-report). Env: cortex-command 2.28.1, claude-code 2.1.186.