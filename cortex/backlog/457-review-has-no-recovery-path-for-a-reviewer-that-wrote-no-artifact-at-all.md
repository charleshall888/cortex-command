---
schema_version: "1"
uuid: 2f6c1172-fb64-4ee3-a622-a20eacea07eb
title: Review has no recovery path for a reviewer that wrote no artifact at all
status: backlog
priority: medium
type: bug
created: 2026-08-06
updated: 2026-08-06
tags: ['lifecycle', 'review', 'robustness', 'overnight']
areas: ['lifecycle']
---
## Why

`skills/build/references/review.md` §3 recovers from a *partial* reviewer artifact — `review.md` present but
missing `## Requirements Drift` → re-dispatch once — and §3a caps drift-apply re-dispatches at 2. Neither
covers the reviewer that produced **no artifact at all**.

Observed in a consumer lifecycle, 2026-08-05: the review agent went idle having done the work, with
`review.md` never written. Nothing in the protocol detects that state, so the orchestrator had to notice it
by hand. The recovery it reached for — resuming the same agent, which still held the analysis — is also not
a move the protocol has: every recovery path in §§2–3a is a *re-dispatch*, and §2's single-writer rule
enumerates the permitted writers as a closed list ("this sub-task plus §3's missing-drift re-dispatch and
§3a's cap-2 re-dispatches"). A fresh dispatch re-derives everything the idle agent already produced.

The overnight path already has a ruling here, so the gap is interactive-only. ADR-0015 (accepted) splits a
**genuine dispatch crash** (`DispatchResult.success == False` → revert + `review_dispatch_crash`) from a
**could-not-run review** (the agent completed but produced no parseable verdict → *preserve* the merge, flag
the integration PR degraded, feed the systemic breaker under the distinct `review_no_artifact` cause class).
`cortex_command/pipeline/review_dispatch.py` implements it via the `_ERROR_RESULT` sentinel
(`{"verdict": "ERROR", "cycle": 0, "issues": []}`). That is a defined and deliberate outcome — but it still
discards the work the idle agent did, and the interactive path has no equivalent ruling at all.

So this ticket is: give the interactive path a defined response, and add recovery-of-the-work to both —
without disturbing ADR-0015's discriminants, which are load-bearing for the systemic breaker.

## Role

Give the review phase a defined response to "the reviewer finished but wrote nothing", on both the
interactive and overnight paths — detection first, and a recovery that prefers resuming the agent that holds
the analysis over re-dispatching a fresh one.

## Integration

A post-dispatch existence check on `cortex/lifecycle/{feature}/review.md` before §3 parses it, with its own
recovery arm added to the §2 single-writer list. The verdict-processing contract downstream is unchanged —
this only governs how a usable `review.md` comes to exist.

## Edges

- **Distinguish "no artifact" from "artifact with no Verdict JSON".** They have different causes (agent
  never wrote vs. agent wrote malformed output) and the second is already partly handled.
- **Resuming an agent is a different mechanism from re-dispatching one**, not a branch of it — the
  single-writer rule and the retry caps both assume dispatch. Whether resumption is available at all depends
  on the harness, and differs between interactive and overnight.
- **A retry cap must still exist**, or an agent that reliably fails to write becomes an unbounded loop.
- **Cycle-independent.** This applies at review cycle 1 exactly as at cycle 2. Split out of #455 for that
  reason — #455 is about what a *second* review reads, this is about a review producing nothing at any cycle.

## Touch points

- `skills/build/references/review.md` — §2 single-writer rule, §3 verdict processing
- `cortex_command/pipeline/review_dispatch.py` — `parse_verdict` / `_ERROR_RESULT` handling around :177-200, :400
- `cortex/adr/0015-review-could-not-run-vs-dispatch-crash-split.md` — accepted, binding; its `could_not_run`
  discriminator and `review_no_artifact` cause class must survive any change here
- `cortex/requirements/pipeline.md` § Post-Merge Review — states the overnight contract this must not break
- `skills/build/SKILL.md` — Advance-verb routing, if a new escalation arm is needed

## Provenance

Split out of #455 during its Clarify phase, 2026-08-06, on the operator's decision that it is orthogonal to
cycle scoping. Same observed run as #455: a 12-issue rework at `criticality: critical` / `tier: complex`.
