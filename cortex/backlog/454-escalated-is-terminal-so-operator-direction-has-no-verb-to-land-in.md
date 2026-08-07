---
schema_version: "1"
uuid: 090b867c-c631-4b46-9df6-8e6784b723eb
title: escalated is terminal, so operator direction has no verb to land in
status: refined
priority: high
type: bug
tags: ['lifecycle', 'review', 'escalation', 'state-machine']
areas: ['lifecycle']
complexity: complex
criticality: high
updated: 2026-08-06
spec: cortex/lifecycle/escalated-is-terminal-so-operator-direction/spec.md
---
## Why

`review-verdict` routes `CHANGES_REQUESTED` at cycle ≥ 2 (and `REJECTED` at any cycle) to **`escalated`**.
`cortex-lifecycle-next` then serves that state with `"terminal": true` and `"outgoing": []`.

The build skill's own instruction for it is *"present the findings and await direction; do not
auto-advance."* The first half is supported. **The second half has nowhere to go:** when the direction
arrives, no verb consumes it. `cortex-lifecycle-advance review-verdict` will not move the state, and
re-running that arm with `APPROVED` would mean recording a review verdict no reviewer wrote — laundering an
operator decision into a fabricated assessment, which is precisely what the escalation exists to prevent.

What is left is hand-appending to `events.log`:

```bash
cortex-lifecycle-event log --event escalation_override --feature <slug> --set decision=... --set reason=...
cortex-lifecycle-event phase-transition --feature <slug> --from escalated --to complete --tier <tier>
```

That works — the state machine picks it up and `cortex-lifecycle-complete-route` classifies normally — but
it is exactly the hand-authoring the event verbs exist to remove. It is two non-atomic writes outside the
arm's flock, the event name is invented at the call site so nothing can aggregate on it, the reason is
optional in practice, and there is no idempotent replay: a re-run appends a second override and a second
transition.

The escalation itself is working as designed. The gap is that a lifecycle can enter a state it can only
leave by writing raw events.

## Role

Give operator direction a verb, so resolving an escalation is recorded rather than improvised — and so the
escalation stays legible in the log afterwards.

## Integration

A resolution arm alongside the existing ones, owning its ordered emissions and their idempotent replay the
way `review-verdict` and `implement-transition` already do:

```
cortex-lifecycle-advance escalation-resolve --feature <slug> --decision <...> --reason "<one line>"
```

`--reason` mandatory, for the same reason `criticality-override` carries one: an outcome recorded without
its rationale leaves the next reader re-deriving it from artifacts. The verb emits the resolution event and
the routed transition under one flock, and returns the new `state` for the caller to route on exactly like
every other arm.

## Edges

- **The resolution must not erase the escalation.** The `review_verdict` and the `phase_transition` into
  `escalated` stay in the log; the resolution is an additional row, never a rewrite. A reader six months on
  needs to see that a reviewer refused and a human overrode, not a clean approval.
- **Which target states are legal is the real design question**, and it is not obviously "complete only".
  Plausible decisions: proceed to Complete (issues were addressed outside the review loop), return to
  Implement for another rework pass (the cap was wrong for this feature), return to Plan or Spec (the
  reviewer's `REJECTED` recommendation), or cancel. Each has a different legal target, and allowing an
  arbitrary `--to` reintroduces the hand-authoring this ticket removes.
- **A resolve verb is a rubber-stamp risk by construction.** It must be reachable only from `escalated`,
  and it should be hard to invoke without a human in the loop — the skill's pause machinery already models
  relayed consent and is the natural place to gate it.
- **Idempotent replay matters more here than elsewhere**, because a resolution is likely to be re-run after
  a context loss: the operator gave direction, the session died, the next session re-reads a state that is
  no longer `escalated` and must not append a second resolution.
- `REJECTED` and cycle-≥2 `CHANGES_REQUESTED` reach the same state from different intents (the first
  recommends returning to plan or spec, the second is a rework cap). The resolution verb probably wants to
  know which, and the reducer already has it.

## Touch points

- `cortex_command/` — the `advance` arm dispatch and the state-machine edge table that currently yields
  `"outgoing": []` for `escalated`
- `cortex-lifecycle-next` — the served `path_overview` / `guards.edges` for the state
- `skills/build/SKILL.md` — § Advance-verb routing, whose `escalated` row currently ends at "await
  direction"
- `skills/build/references/review.md` — § 3/§ 4, which owns verdict processing
- `cortex-lifecycle-event` — the `log` subcommand currently absorbing the improvised event

## Provenance

Hit in a consumer lifecycle, 2026-08-05: a cycle-2 review returned `CHANGES_REQUESTED` over two findings
that were then fixed and committed; the operator directed close-out, and there was no verb to record it.
Resolved by hand-appending an `escalation_override` row plus a `phase_transition`, which is the workaround
this ticket exists to replace.
