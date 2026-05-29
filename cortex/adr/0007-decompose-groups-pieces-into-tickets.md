---
status: accepted
---

# `/discovery` decompose groups pieces into tickets

## Context

`/discovery` decompose has implicitly mapped one research-phase piece to one backlog ticket: each `### Pieces` bullet from the approved Architecture became exactly one ticket candidate, and §4 "Determine Grouping" only branched on the piece *count* without ever merging pieces. Ticket #247 (shipped) deliberately kept consolidation *user-driven* — the manual R15 `consolidate-pieces` action, with no detector — after rejecting an automatic detector as unjustified on a thin corpus. The recurring operator friction is that when the research-phase Architecture over-splits, decompose lands many small tickets (e.g. ~10 where ~3 larger ones were the right cut), and each then drags through full `/cortex-core:lifecycle` ceremony — so the cost is per-ticket overhead, not reading. The only lever on ticket count was the manual `consolidate-pieces` action at the final R15 gate, which requires the operator to spot the false boundaries unaided. (Feature #268.)

## Decision

decompose §4 now *auto-groups* the grossly over-split, architecture-visible cases into single tickets (M pieces → 1 ticket) before bodies are drafted, using coupling signals *inferred* from the emitted Architecture content (`### Pieces` roles + `### How they connect` connection/boundary prose, plus dependency relationships). A new `split-piece <N>` re-derivation is added at the existing R15 gate, which rebuilds a wrongly-grouped ticket's constituent pieces from the retained, unmodified Architecture source. Grouping coarsens only ticket *packaging*; the analytical `### Pieces` set remains research-owned and unchanged.

## Trade-off

This reverses the implicit 1:1 piece-to-ticket contract and part of #247's user-driven posture, accepting a *residual* anchoring risk — a wrong auto-grouping the operator might rubber-stamp at R15.

The risk is **reduced, not eliminated**:

- Grouping fires only on clear architecture-level coupling (gross over-splitting), never on subtle, body-only couplings.
- Each group's rationale is surfaced at the user-blocking R15 gate, so the operator sees *why* a merge was made.
- `split-piece` lets the operator rebuild a wrong grouping from the authoritative Architecture source — the same source the no-grouping path would have used.

The accepted residual: a tired operator who does not notice a bad grouping at R15 is not fully protected.

## Three-criteria gate clearance

- **Hard to reverse**: reversing the decision means coordinated changes across `skills/discovery/references/decompose.md` (§2/§3/§4/§5/§6 prose + the R15 gate + Constraints), the `_RESPONSE_VALUES` frozenset in `cortex_command/discovery.py`, the `skills/discovery/SKILL.md` gate-option inventory, and the discovery test suite — all of which encode the new grouping mental model and would have to move together.
- **Surprising without context**: a contributor encountering decompose for the first time would reasonably expect the documented one-piece-per-ticket mapping (and would find #247's user-driven posture in the offer-consolidation-clusters lifecycle), and would likely propose reverting the auto-grouping as a regression on that prior decision unless they knew why.
- **Real trade-off**: at least one credible alternative was considered and rejected for stated reasons — see Alternatives considered below — and the decision carries a real, named cost (residual anchoring risk vs. reduced per-ticket ceremony).

## Alternatives considered

- **After-the-fact body-scanning detector before R15 (rejected)**: scan drafted ticket *bodies* for couplings just before the R15 gate. This is #268-as-written and is equivalent to the Alternative A that #247 already rejected. Rejected because it aims at the wrong altitude — the ticket count is locked upstream at decompose §4 before any body is drafted, so a body-level detector arrives too late; it re-introduces the anchoring it was meant to fix; and it contradicts the frozen-piece-set invariant.
- **Recalibrate research-phase decomposition granularity (rejected)**: tune the research phase's "Why N pieces" gate so the Architecture emits fewer, larger pieces in the first place. Rejected as a more diffuse change that the operator did not select; it would shift the granularity decision back into research rather than packaging tickets at the decompose boundary where the friction is observed.

## Cross-references

- Feature: #268 (`cortex/lifecycle/auto-consolidation-pass-in-discovery-decompose/`).
- Prior decision: #247 (`cortex/lifecycle/offer-consolidation-clusters-before-r15-gate/`), which shipped the manual `consolidate-pieces` R15 fallback this decision retains.
