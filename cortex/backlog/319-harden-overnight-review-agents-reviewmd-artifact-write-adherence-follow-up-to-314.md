---
schema_version: "1"
uuid: 4d5d2d7c-e8a6-49ad-b81e-16962af95815
title: 'Harden overnight review agent''s review.md artifact-write adherence (follow-up to #314)'
status: complete
priority: medium
type: bug
created: 2026-06-23
updated: 2026-06-23
complexity: complex
criticality: high
spec: cortex/lifecycle/harden-overnight-review-agents-reviewmd-artifact/spec.md
areas: ['overnight-runner']
---
## Why

Follow-up to **#314**. The #314 fix made the overnight review *gate* robust to a
missing/unparseable `review.md`: a could-not-run review (agent completed
`success=True` but produced no usable verdict) now **preserves** the merge and
flags it for human re-review instead of reverting. That contains the blast
radius — but the *root contributing cause* is unaddressed.

In the wild-light incident (`overnight-2026-06-23-0605`, feature
`occlusion-field-max-ray-steps24-under`) the Sonnet review agent reached
`end_turn` after 17 turns (`dispatch_complete stop_reason=end_turn`, ~3.2m) and
**never wrote the `review.md` JSON verdict block** the prompt requires — it
likely emitted its review as a final chat message instead of writing the
artifact. The artifact write is the contract but is not enforced or verified on
the *agent* side. Reducing how often the agent fails to write the artifact would
reduce how often the could-not-run path fires at all.

## Scope / role

Improve the review agent's adherence so it reliably writes `review.md` before
ending its turn. Candidate directions to **research, not prescribe**:
- Strengthen the reviewer prompt's artifact-write instruction (positive
  routing) so the verdict block is written, not chatted.
- A late-turn self-check that the verdict block was actually written to disk
  before `end_turn`.
- A structured-output / required-final-write affordance for the verdict.
- Evaluate whether an `effort` bump (high → xhigh) or a model escalation for the
  review dispatch measurably reduces non-adherence — subject to the
  MUST-escalation policy (try `effort=high`/`xhigh` and record the result
  before any imperative escalation).

## Boundary (do NOT re-open)

This is **review-agent adherence only**. The gate-side robustness — preserve +
report annotation + integration-PR marker + systemic breaker under
`review_no_artifact` — already shipped in #314 and remains the safety net
regardless of this work. Do not re-open or weaken the gate behavior here; see
ADR 0015 (review could-not-run vs dispatch-crash split).

## Touch-points

- Reviewer prompt template: `skills/lifecycle/references/review.md` (and any
  overnight review dispatch prompt in `cortex_command/pipeline/review_dispatch.py`).
- Editing `skills/` requires its own lifecycle.
- Related: #314 (gate robustness), lifecycle `overnight-review-gate-reverts-a-clean`,
  ADR `cortex/adr/0015-review-could-not-run-vs-dispatch-crash-split.md`.

## Evidence

`overnight-2026-06-23-0605`, feature `occlusion-field-max-ray-steps24-under`:
review `dispatch_complete stop_reason="end_turn"`, `num_turns=17`, ~3.2m, no
`review.md` written anywhere (absent in both worktree and main-repo lifecycle
dir) while a dozen sibling features in the same worktree had one.