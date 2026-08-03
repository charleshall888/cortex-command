---
status: deprecated
---

# Fog becomes a piece, and its dependents declare the blocker

> **DEPRECATED the day it was written (2026-08-03), before any implementation.** Every behavior it
> decides already exists, and the decision was reached without checking that. Kept rather than
> deleted so the next person to propose this mechanism finds the reason it is unnecessary instead of
> re-deriving it.
>
> - **"Uncertainty becomes its own piece."** Decompose already does this. #439 — the spike that
>   produced this ADR — was itself emitted by decompose as `type: spike` with `blocked-by: [438]`:
>   a question only the operator could answer, materialized as a piece, blocker declared at
>   authoring time, terminating in a decision artifact. The archetype existed before the decision.
> - **"Dependents declare `blocked-by` when authored."** `decompose.md:45` already writes
>   `blocked-by: [<ids>]` from Integration-shape dependencies at creation, and `:25` already
>   captures those dependencies from `### How they connect`.
> - **"Human-bound work must not run unattended."** Owned by the curation gate — ADR-0021, whose
>   title is *"suitability is not a selection gate"*, has the LLM set poor unattended candidates
>   aside with per-item reasons at a gate where a human is present, and explicitly rejects a
>   deterministic marker because *"a Python matcher would be brittle"*. A `needs-operator` field was
>   considered here and contradicts that.
>
> The motivating evidence did not fit either. #411's three "falsified claims" were two facts about
> the codebase (six frontmatter parsers where the ticket asserted one shared boundary; a warn guard
> the shipped-surfaces rule forbids) and one point of operator intent that had already been resolved
> six days before the reconciliation. #436 contradicted research that was correct at
> `research.md:31`. None of these is uncertainty; all are claims asserted without verification.
> That defect is real and is tracked at #429 and #444.
>
> Naming, for the record, needs no new type: DR-1 forbids one, research Q4 found *"nothing that
> survives inspection"* distinguishes a decision ticket from `spike`, and `requirements` is already
> taken by `cortex/requirements/` and `/cortex-core:requirements`.

## Context

When a mid-epic ticket invalidates the understanding its siblings were written against, nothing stops those siblings being worked as written. Re-authoring is not the gap — ticket bodies are freely editable and re-authoring is in active use (`research.md:29`, and 86 of 198 epic children carry 2+ commits). The gap is that nothing structurally prevents expensive work starting on a premise that has already changed.

The census (possible only after #438 made closed epics visible to the epic map) found 6 of 198 epic children carrying an explicit re-authoring commit. Three of them — #411, #412, #415 — are children of one epic, and in all three the **refine phase ran before the reconciliation**. #411's spec was written against claims later found false (`Reconcile #411's falsified claims without erasing what was believed`). The unit of loss is therefore a wasted research-and-spec cycle, not a missing rewrite. The 6 is a floor: detection matched commit subjects, so quiet reconciliations inside larger commits are invisible to it.

DR-3 (`cortex/research/staged-epic-gate-tickets/research.md:95`) established that this is a **sequential-gate failure**, a class `CLAUDE.md` and `docs/policies.md:11` say to solve structurally rather than by prompting — prose-only enforcement is admitted only where occasional deviation is cheap, and here the deviation is the reported failure itself. That ruling defeats "remind the operator to reconcile" but does not choose a mechanism.

Two mechanisms were charted and both are rejected here; see Alternatives considered.

## Decision

Uncertainty is named as work at planning time rather than discovered mid-epic.

When the research phase authors `### Pieces` and cannot state a piece precisely — applying wayfinder's fog test, *whether the question can be stated precisely now, not whether it can be answered* (`research.md:57`) — and the missing answer is one only the operator can give, the uncertainty itself becomes a piece whose deliverable is to clear that fog. Pieces that depend on the answer record that dependency in `### How they connect`.

Decompose then packages the fog piece like any other and wires the dependency it already reads from `### How they connect`, so dependent tickets are authored carrying `blocked-by` the fog ticket **at the moment they are written**.

Every ticket is still created in one flow, and the piece set is still complete.

**Fog is only ever a question the research phase cannot answer itself.** In practice that means one thing: the answer belongs to a human who is not in the room. `/cortex-core:requirements` carries `disable-model-invocation: true` and `/cortex-core:interview` needs a live counterpart — an agent cannot settle what we *want* on its own initiative, and that is the correct constraint rather than an obstacle. A dependency on someone outside the run is what a blocker is for.

A fog piece therefore names its clearing route and terminates in an artifact — a `cortex/requirements/{project|area}.md` or an interview brief — which gives it a definition of done a status flip alone cannot satisfy (`research.md:57`: resolution is *"a produced artifact plus an explicit handoff step, not a status flip"*). That artifact is what the dependents are reconciled against once the blocker lifts.

Reaching the human is usually worth a research pass first, because an unresearched question wastes their turn: "how should we prevent stale tickets?" is unanswerable, while "the census shows 6 of 198, three in one epic, each costing a refine — enough to act on?" is answerable in a sentence. That research is part of clearing the fog, not a separate piece. This decision was taken that way.

**Questions of fact are not fog and must not become tickets.** How the codebase behaves is exactly what the research phase's fan-out exists to establish, and it is reachable during the run. Deferring a fact into its own ticket buys a blocker, a lifecycle pass, and per-ticket ceremony — the friction ADR-0007's Context already names — to answer something a grep settles now. Where research genuinely cannot establish a fact its pieces rest on, that is a research defect and `decompose.md:9` already routes it: surface it and return to research rather than materializing a placeholder.

Epic #434 is the evidence for that exclusion, not against it. Its tickets shipped disagreeing about whether the parent-closing cascade normalizes status — and there was no fog. `research.md:31` had established it correctly, with line numbers (*"reads **raw, unnormalized** status (`:299`, `:333`)"*); #435 and #437 quoted it accurately; #436's Integration asserted the opposite and cost three mid-flight rewrites. The failure was a ticket body contradicting its own source, which no amount of extra research would have prevented. Tracked as its own defect — see Cross-references.

## Trade-off

Enforcement is structural and already live: a ticket with an unresolved `blocked-by` is absent from the ready list, from triage recommendations, and from overnight eligibility. Nothing new enforces anything, and nobody has to remember anything later — the blocker is written when the ticket is written.

Scope is deliberately narrow. Fog is only what an agent cannot settle during the run, which in practice means questions for a human. That keeps the mechanism from becoming per-ticket ceremony: a blocker is spent on a genuine external dependency, never on work the research phase could have done in the same pass.

The costs are real:

- **Fog must be recognized at planning time.** A piece confidently mis-stated during research produces no fog piece and no blocker, and this decision does nothing for it. It converts a reconciliation problem into a recognition problem; it does not eliminate the failure.
- **It does not address bodies that contradict their own research.** That is the failure epic #434 actually suffered, and it is a fidelity problem in decompose, not an uncertainty problem. A separate defect.
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
- Excluded and tracked separately: #444 — a decompose body contradicting its source research, which is a fidelity defect rather than uncertainty, and is what epic #434 actually suffered.
