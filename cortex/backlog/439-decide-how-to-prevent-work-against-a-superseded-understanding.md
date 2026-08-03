---
schema_version: "1"
uuid: da03c46d-4b4c-45f7-af17-ea65f6e7c0ab
title: Decide how to prevent work against a superseded understanding
status: complete
priority: medium
type: spike
created: 2026-08-03
updated: 2026-08-03
parent: "434"
tags: ['staged-epic-gate-tickets']
blocked-by: []
discovery_source: cortex/research/staged-epic-gate-tickets/research.md
---
## Why

When a mid-epic ticket invalidates the plan its siblings were written against, nothing prevents those siblings being worked as written. The downstream tickets are re-authorable and in fact are re-authored routinely, so the gap is not capability — nothing structurally stops work proceeding on an understanding that has already changed.

## Role

Settles which of two structural mechanisms the harness adopts, and on what evidence — producing the decision and its rationale, not the implementation.

## Integration

Both candidates ride surfaces that already exist: the blocking relationship the readiness predicate enforces at every selection surface, and the piece-set contract the decompose phase consumes. The decision consumes the epic census that becomes possible once closed epics are visible to the epic map.

## Edges

- A reminder to reconcile downstream tickets is not a candidate. Prose-only enforcement of a sequential gate is admitted only where occasional deviation is cheap, and here the deviation is the reported failure itself.
- Interrupting the work leaves the piece set complete and the tickets materialized up front, so it disturbs neither the accepted piece-to-ticket decision nor the prior ruling that discovery creates the epic and its tickets in one flow. Its limit is that it guarantees a stop, not a rewrite.
- Withholding authorship contradicts the accepted decision governing the piece-to-ticket mapping and would need a successor. It also reopens ground a prior ticket was reverted on, whose stated rationale — that the pain was hypothetical — no longer holds.
- The deliverable is a decision. Any implementation is a separate ticket that should exist only if the decision calls for one.
- Blocked until epic visibility lands, because the census is the intended tiebreaker and cannot be taken before then.

## Decision (2026-08-03)

**Neither charted arm was adopted. → ADR-0034.**

The census landed once #438 made the epic corpus visible: 6 of 198 epic children carry an explicit re-authoring commit, three of them in one epic, and in all three the refine phase ran *before* the reconciliation — #411's spec was written against claims later found false. The unit of loss is a wasted research-and-spec cycle. The 6 is a floor: detection matched commit subjects, so quiet reconciliations are invisible to it.

Both charted arms were rejected on operator judgment. Interrupting locks tickets after the fact and depends on someone noticing the invalidation, which returns it to the prose-only enforcement DR-3 rejected. Withholding authorship was rejected again on the same ground as #196 — the preference that discovery create the epic and its tickets in one flow was reconfirmed, now with the pain no longer hypothetical.

What was adopted is the third option the research had already surfaced but this ticket never charted: the fog/ticket test at `research.md:57`. Uncertainty becomes a *piece* at planning time, so it is visible work rather than an assumption baked into siblings; dependent pieces record the dependency in `### How they connect`, and their tickets are therefore authored already carrying `blocked-by`. Enforcement is structural and already live at every selection surface, and no one has to remember anything later, because the blocker is written when the ticket is written.

Rationale, costs, and the rejected alternatives are in ADR-0034 — not restated here, per the ADR no-content-duplication rule.

### Correction, same day: the adopted mechanism already existed

ADR-0034 was deprecated hours after it was written, before anything was built, and #443 was closed unimplemented. Reviewing it against the harness showed every part already shipped:

- Decompose already emits an operator-only question as its own piece with its blocker declared at authoring time. **This ticket is the proof** — decompose wrote it as `type: spike`, `blocked-by: [438]`, deliverable a decision. The mechanism was demonstrated by the very artifact that proposed it.
- `decompose.md:45` already writes `blocked-by: [<ids>]` at creation; `:25` already sources them from `### How they connect`.
- Keeping human-bound work out of unattended runs is the curation gate's job (ADR-0021), which deliberately rejects the deterministic marker considered here.

The deeper error was in this ticket's framing, not only in the answer. The Why asserts that nothing structurally stops work proceeding on a changed understanding, and the evidence offered for it — #411, #412, #415 — does not show that. #411's falsified claims were two unverified facts about the codebase and one point of intent already settled six days earlier. The failure across every examined case is a ticket asserting facts nobody checked, which is a verification defect, not an uncertainty one, and no fog mechanism addresses it.

**The standing answer to this ticket's question is therefore: the structure already exists, and the real exposure is unverified claims — tracked at #429 and #444.**

Both correction and deprecation are recorded rather than erased, on the same principle as this epic's other reversals.
