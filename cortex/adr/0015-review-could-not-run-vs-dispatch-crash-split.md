---
status: accepted
---

# Review gate: could-not-run vs dispatch-crash split

## Context

A prior lifecycle (`overnight-review-gate-crashes-to-cycle`) deliberately chose to revert any
unreviewed merge — including a "could-not-run/crashed review with verdict ERROR" — so no unreviewed
code remains on the integration branch, and to feed all such cases into the systemic circuit breaker.
The integration branch is auto-published as a non-draft "N features merged" PR, so that revert was
load-bearing: it kept the PR trustworthy. Operationally the revert also discards verified,
already-merged work whenever the review *agent* completes but fails to write a parseable verdict (a
tooling/adherence miss), and mislabels it a "crash."

## Decision

Split the single `ERROR` outcome into two. A **genuine dispatch crash** (`DispatchResult.success ==
False`) retains the revert + systemic-breaker behavior under the `review_dispatch_crash` cause-class.
A **could-not-run review** (`success == True`, no usable verdict) **preserves** the merge, surfaces
an "unreviewed merge preserved — needs human re-review" deferral on the morning report **and a
degraded/unreviewed marker on the integration PR**, and feeds the systemic breaker under a distinct
`review_no_artifact` cause-class (aggregate threshold; label for diagnosis) so a systemic adherence
failure still pauses the batch without discarding individual work.

## Trade-off

The prior "nothing unreviewed survives" guarantee was enforced in code (SHA-anchored revert under
`ctx.lock`). This decision relocates that boundary: unreviewed code may remain on the overnight
integration branch in the could-not-run case, and safety now rests on three surfaces — the
morning-report annotation, the **integration-PR degraded marker** (so the merge-decision surface
itself warns the operator, not just the report; advisory, with draft-on-marker-write-failure as the
fallback), and the systemic breaker (trips at `SYSTEMIC_FAILURE_THRESHOLD` under cause-class
`review_no_artifact`) that halts a batch-wide review-tooling failure. The morning-merge gate is
operator-discipline rather than a code-enforced revert; the PR marker is what keeps that discipline
honest. We accept this in exchange for not discarding verified, hook-passing, merged work over a
tooling miss, and because the integration branch is not `main`.

This **supersedes the relevant clause of the prior revert-all-unreviewed posture** from the
`overnight-review-gate-crashes-to-cycle` work: that posture reverted every ERROR-verdict merge
unconditionally; under this decision only the genuine-crash branch reverts, while the could-not-run
branch preserves and flags.

## Consequences

- The could-not-run case keeps verified, hook-passing, merged work on the integration branch instead
  of discarding it over a review-tooling/adherence miss.
- The positive `could_not_run=True` discriminator (never inferred from `merge_reverted=False`, which a
  crash with a failed revert also produces) is what the morning report and the integration-PR marker
  key on.
- The systemic breaker still pauses a batch-wide review-tooling failure: crash + no-artifact failures
  count in aggregate against `SYSTEMIC_FAILURE_THRESHOLD`, with both cause-class labels surfaced in
  the emitted `pipeline_systemic_failure` event for diagnosis.
- Safety for unreviewed-but-preserved code is no longer code-enforced; it depends on the operator
  acting on the report annotation and the integration-PR marker before merging to `main`.

Background and the documented contract live in
[docs/internals/pipeline.md](../../docs/internals/pipeline.md) (Review gate: could-not-run vs dispatch
crash) and [cortex/requirements/pipeline.md](../requirements/pipeline.md) (Post-Merge Review); this
ADR is the canonical home for the decision and its trade-off.
