---
schema_version: "1"
uuid: 2f6c1172-fb64-4ee3-a622-a20eacea07eb
title: Review has no recovery path for a reviewer that wrote no artifact at all
status: refined
priority: medium
type: bug
created: 2026-08-06
updated: 2026-08-07
tags: ['lifecycle', 'review', 'robustness']
areas: ['lifecycle']
complexity: moderate
criticality: high
spec: cortex/lifecycle/review-has-no-recovery-path-for/spec.md
---
## Why

Nothing in the interactive review chain checks that the reviewer actually wrote `review.md`. The two
verbs the phase calls are both blind to it:

- `cortex_command/lifecycle/register_artifact.py:96-130` appends `review` to `index.md`'s `artifacts:`
  array and returns `registered` at exit 0. It never stats the artifact.
- `cortex_command/lifecycle/advance.py:427-435` (`advance review-verdict`) validates only that
  `--verdict` and `--drift` are in their enums. It never stats the artifact either.

So an interactive review can reach `complete` having produced nothing, with an orchestrator-supplied
verdict and an `artifacts:` array that claims a review exists.

`skills/build/references/review.md` §3 is technically reachable for this case — an absent file does
"lack `## Requirements Drift`" — but its remediation prompt is *"read the existing file and append
it"*, which is incoherent for a file that was never written. Nothing routes the orchestrator down that
arm, because nothing detects the state.

**Evidence.** Observed in a consumer lifecycle 2026-08-05: the review agent went idle having done the
work, `review.md` never written, and the orchestrator had to notice by hand. This is not a one-off —
the same failure recurred **twice on 2026-08-07** during this ticket's own Clarify phase: a dispatched
`general-purpose` critic did the analysis, emitted only an idle notification, and returned no artifact,
across two chases (the second explicitly waiving the output envelope). The pattern is routine enough to
clear the front-door evidence bar in `cortex/requirements/project.md` (Deletion bias) on observed
failure, not hypothesis.

A second consequence is unstated in the original report: per `cortex_command/lifecycle/review_brief.py:35-37`,
a missing `review.md` makes `common.py`'s phase detection fall through to the plan-based step and report
`review` instead of `implement-rework` — so the failure can also mis-route the following cycle.

## Role

Give the **interactive** review phase a deterministic response to "the reviewer finished but wrote
nothing": a verb-level gate that refuses to advance past a missing artifact, plus sanction in §2's
single-writer rule for resuming the idle reviewer rather than re-deriving its analysis by fresh
dispatch.

## Integration

The gate belongs in a wheel verb, not in reference prose — `CLAUDE.md` prefers structural separation
over prose-only enforcement for sequential gates, and `skills/build/references/` has **zero** ratchet
headroom (pin 57175, measured 57175), so added prose there needs an offsetting trim or a documented
`# raised:` exception. Candidate homes are `register_artifact` (a new `artifact-missing` state; covers
research/spec/plan too) and `advance review-verdict` (review-only, but it is the actual advance point).
Choosing between them, and bounding the blast radius of a `KNOWN_STATES` change on existing callers, is
the research question.

Resumption itself needs no machinery: it is `SendMessage` to the still-live reviewer, which already
exists. What is missing is permission — §2 enumerates the permitted writers as a closed list of three
re-dispatches, so resuming is currently not a move the protocol has.

## Non-goals

- **The overnight path is out of scope.** ADR-0015 (accepted) already gives it a complete, deliberate
  response: `parse_verdict` detects the state, the positive `could_not_run` discriminator routes it, the
  merge is preserved, the integration PR is marked degraded, and the systemic breaker counts it under
  `review_no_artifact`. The only thing overnight lacks is recovery of the idle agent's work, and that is
  **unbuildable there** — there is no agent-resumption affordance anywhere in `cortex_command/` (no
  `--resume`/`--continue`; review dispatch is a one-shot subprocess bounded by `max_turns`). Scoping this
  ticket to the interactive path means ADR-0015's discriminants are untouched by construction.

## Edges

- **A retry cap must still exist** for the fallback path, or a reviewer that reliably fails to write
  becomes an unbounded loop. Resumption is bounded by orchestrator judgment; when it falls through to
  re-dispatch, §3's existing cap governs.
- **`register_artifact` is shared across phases.** A new refusal state changes a contract that
  `finalize.py` and `enter.py` also depend on.
- **Cycle-independent.** Applies at review cycle 1 exactly as at cycle 2. Split out of #455 for that
  reason — #455 is about what a *second* review reads; this is about a review producing nothing at any
  cycle.
- **Corrected from the original report:** "no artifact" and "artifact with no Verdict JSON" are *not*
  distinguishable today, and the second is *not* "already partly handled". `parse_verdict`
  (`review_dispatch.py:205-217`) returns the identical `_ERROR_RESULT` sentinel for a missing file, a
  missing JSON block, and malformed JSON. Consequently ADR-0015's `review_no_artifact` cause class fires
  for all three despite its name. Behavior is correct (all three should preserve-and-flag); only the
  label is imprecise, and correcting it is deliberately **not** in this ticket.

## Touch points

- `cortex_command/lifecycle/register_artifact.py` — `register_artifact` :96-130, `KNOWN_STATES` :61
- `cortex_command/lifecycle/advance.py` — `review-verdict` arm :427-435; note the legacy-fallback
  carve-out :1054-1069, which a new refusal must not re-break
- `skills/build/references/review.md` — §2 single-writer rule (:23), §3 verdict processing (:31-37)
- `skills/build/references/size-pin.txt` — zero headroom; governs any prose change above
- `cortex/adr/0035-*.md` — whether a new served refusal state moves `PROTOCOL_VERSION` and
  `skills/build/references/protocol-expectation.txt`

## Provenance

Split out of #455 during its Clarify phase, 2026-08-06. Body rewritten 2026-08-07 during this ticket's
own Clarify phase, which found the overnight half unbuildable, the resumption half already available,
and the detection gap located in the verbs rather than the prose. Original scope claimed both paths and
a new recovery mechanism; measured scope is one gate plus one prose amendment.
