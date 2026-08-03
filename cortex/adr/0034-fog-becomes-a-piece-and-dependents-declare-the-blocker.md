---
status: accepted
---

# Fog becomes a piece, and its dependents declare the blocker

## Context

When a mid-epic ticket invalidates the understanding its siblings were written against, nothing stops those siblings being worked as written. Re-authoring is not the gap — ticket bodies are freely editable and re-authoring is in active use (`research.md:29`, and 86 of 198 epic children carry 2+ commits). The gap is that nothing structurally prevents expensive work starting on a premise that has already changed.

The census (possible only after #438 made closed epics visible to the epic map) found 6 of 198 epic children carrying an explicit re-authoring commit. Three of them — #411, #412, #415 — are children of one epic, and in all three the **refine phase ran before the reconciliation**. #411's spec was written against claims later found false (`Reconcile #411's falsified claims without erasing what was believed`). The unit of loss is therefore a wasted research-and-spec cycle, not a missing rewrite. The 6 is a floor: detection matched commit subjects, so quiet reconciliations inside larger commits are invisible to it.

DR-3 (`cortex/research/staged-epic-gate-tickets/research.md:95`) established that this is a **sequential-gate failure**, a class `CLAUDE.md` and `docs/policies.md:11` say to solve structurally rather than by prompting — prose-only enforcement is admitted only where occasional deviation is cheap, and here the deviation is the reported failure itself. That ruling defeats "remind the operator to reconcile" but does not choose a mechanism.

Two mechanisms were charted and both are rejected here; see Alternatives considered.

## Decision

Uncertainty is named as work at planning time rather than discovered mid-epic.

When the research phase authors `### Pieces` and cannot state a piece precisely — applying wayfinder's fog test, *whether the question can be stated precisely now, not whether it can be answered* (`research.md:57`) — the uncertainty itself becomes a piece: a research or requirements piece whose deliverable is to clear that fog. Pieces that depend on the answer record that dependency in `### How they connect`.

Decompose then packages the fog piece like any other and wires the dependency it already reads from `### How they connect`, so dependent tickets are authored carrying `blocked-by` the fog ticket **at the moment they are written**.

Every ticket is still created in one flow, and the piece set is still complete.

A fog piece names how it will be cleared, because fog comes in two kinds and they are answered by different instruments:

- **Intent fog** — the question is what we want, or where the boundary sits. Cleared by `/cortex-core:requirements` (which writes `cortex/requirements/{project|area}.md`) or `/cortex-core:interview` (which produces a brief). Note that `requirements` carries `disable-model-invocation: true`: an agent cannot resolve intent fog on its own initiative, which is the correct constraint rather than an obstacle.
- **Fact fog** — the question is how the codebase or the world actually behaves. Cleared by `/cortex-core:research`, which writes a `research.md`.

**The routes compose; they are not exclusive.** Intent fog routinely needs a research pass first, because an unresearched question wastes the human's turn: "how should we prevent stale tickets?" is unanswerable, while "the census shows 6 of 198, three in one epic, each costing a refine — is that enough to act on?" is answerable in one sentence. A fog piece may therefore carry a research step whose output exists to sharpen the questions the interview then asks. This decision itself was taken that way.

Each route terminates in an artifact, which gives the fog ticket a definition of done that a status flip alone cannot satisfy — wayfinder's observation that resolution is *"a produced artifact plus an explicit handoff step, not a status flip"* (`research.md:57`). The artifact is what the dependent tickets are reconciled against once the blocker lifts.

**Calibration: fog is what more than one sibling rests on.** A fact only one ticket depends on is not fog — the refine phase checks it as a matter of course, locally and cheaply. It becomes fog when several pieces are authored against the same unverified assumption, because that is when being wrong multiplies. Epic #434 is the worked example, and it predates this decision: #435 and #436 shipped with contradictory claims about a single fact (whether the parent-closing cascade normalizes status — it does not, `update_item.py:33`). That one unchecked fact made #436's unwedge arm unachievable as scoped, made #437's narrowing unsafe on grounds its own Edges misidentified, and made #438's touch-points understate the work. One grep, unasked, cost three mid-flight rewrites.

## Trade-off

Enforcement is structural and already live: a ticket with an unresolved `blocked-by` is absent from the ready list, from triage recommendations, and from overnight eligibility. Nothing new enforces anything, and nobody has to remember anything later — the blocker is written when the ticket is written.

The costs are real:

- **Fog must be recognized at planning time.** A piece confidently mis-stated during research produces no fog piece and no blocker, and this decision does nothing for it. It converts a reconciliation problem into a recognition problem; it does not eliminate the failure.
- **A stalled fog ticket stalls its dependents.** That is the mechanism working as designed, but an epic can now be held by one unresolved question in a way it could not before.
- **Over-application is a real failure mode.** Naming fog too eagerly produces long blocker chains and an epic that looks unworkable. The fog test is the guard, and it is judgment.

The accepted residual: this prevents work against a *known-uncertain* premise, not against a *wrongly-confident* one.

## Three-criteria gate clearance

- **Hard to reverse**: reversing means coordinated changes across the research-phase Architecture template and its fog test, `skills/discovery/references/decompose.md`'s dependency wiring, `skills/discovery/SKILL.md`, and the discovery test suite — all of which would encode the fog-piece mental model and would have to move together.
- **Surprising without context**: a contributor meeting an epic whose children are `blocked-by` a spike sibling would reasonably read it as over-engineering and propose flattening the chain, particularly since ADR-0007 documents a clean piece→ticket mapping and #196's revert reads as a rejection of anything that staggers ticket availability. Neither is contradicted here, but that is not evident from the artifacts alone.
- **Real trade-off**: two credible alternatives were considered and rejected for stated reasons, and the decision carries a named cost — it converts reconciliation into recognition and can stall an epic on one question.

## Alternatives considered

- **Retroactive blocking (rejected).** When a ticket is found to have invalidated its siblings, set `blocked-by` on them at that moment. Same enforcement surface, and cheap to build — the terminal-status cascade already writes other items' `blocked-by` arrays (`update_item.py:199`). Rejected on operator judgment: it locks tickets after the fact, and the trigger is a human noticing the invalidation and acting on it, which returns the mechanism to the prose-only enforcement DR-3 rejected. Recognition moves to planning time instead, where it is a declaration rather than an intervention.
- **Withholding authorship (rejected).** Do not author downstream tickets until the fog resolves; an unwritten ticket cannot go stale, so decay becomes impossible by construction. Rejected because it contradicts ADR-0007, requires discovery to emit a deliberately incomplete piece set that `decompose.md:9` classifies as a research defect, and reopens the axis #196 was reverted on — where the operator's stated preference was that discovery create the epic and its tickets in one flow. That preference was reconfirmed when this decision was taken, with the pain no longer hypothetical.
- **Reminder to reconcile downstream tickets (rejected upstream).** Ruled out by DR-3 before this decision: prose-only enforcement of a sequential gate, where the deviation is the failure being prevented.

## Cross-references

- Spike: #439 (`cortex/backlog/439-decide-how-to-prevent-work-against-a-superseded-understanding.md`).
- Research: `cortex/research/staged-epic-gate-tickets/research.md` — DR-3, the fog/ticket test at `:57`, both arms costed at P5/P6.
- Compatible with ADR-0007: the analytical piece set stays complete and research-owned; grouping is untouched.
- Prerequisite: #438 (epic visibility), which made the deciding census possible.
- Implementation: #443.
