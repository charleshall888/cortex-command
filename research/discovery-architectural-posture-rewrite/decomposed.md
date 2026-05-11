# Decomposition: discovery-architectural-posture-rewrite

## Single ticket (no epic)

Per `decompose.md` §4 (augmented under DR-1 with single-piece branch — eating the protocol's own dog food): research surfaced one coordinated architectural change spanning three skill files. Pieces ship together by construction; the work is one ticket.

## Work Items

| ID | Title | Priority | Size | Depends On |
|----|-------|----------|------|------------|
| 195 | Reframe discovery to principal-architect posture | high | L | — |

## Architecture (as the research artifact would have produced it under the refined protocol)

### Pieces

1. **Clarify scope-envelope surface** — role: pre-research scope-lock in clarify output
2. **Research architecture-summary + bundling-justification surface** — role: structural-pieces summary in research output template, with conditional bundling-justification when piece count exceeds threshold
3. **Research→decompose approval gate** — role: phase-boundary user-checkpoint on the architecture-summary
4. **Decompose protocol trim + uniform ticket template** — role: ticket-derivation engine consuming the approved architecture-summary, replacing value-grounding-and-per-item-ack machinery
5. **Section-partitioned prescriptive-prose check** — role: pre-commit lexical safety net at ticket level, partitioned on the optional touch-points section
6. **Events instrumentation** — role: skip-rate audit trail for the three new soft gates

### Integration

Pieces 2 → 3 → 4 form the load-bearing chain (architecture-summary feeds approval gate; approved summary feeds decompose). Piece 1 (clarify scope-envelope) feeds research as pre-condition. Piece 5 (prescriptive-prose check) is a pre-commit gate inside the decompose-protocol piece. Piece 6 (events) is cross-cutting — emits on every fire of pieces 2, 3, and 5.

### Edges

- Architecture-summary may legitimately be empty (signals zero-piece exit branch in decompose §4)
- Approval gate "Revise" path must loop cleanly back to research authoring; refine and lifecycle do not see this loop
- Section-partitioned check must apply uniformly to meta-tickets (skill-modifying tickets) — section indices are path-equivalent and live in touch-points only
- Bundling-justification fires only when piece count exceeds threshold; under threshold, the surface is omitted
- Events instrument soft gates; skip behavior is countable but does not auto-escalate — MUST-escalation requires the evidence-of-failure path in CLAUDE.md policy

### Why 1 piece (consolidation rationale)

The architectural pieces above are six in count, but they ship as one coordinated change because (i) trimming the decompose protocol without adding the architecture-summary leaves §2 with nothing to consume, (ii) adding the architecture-summary without trimming preserves the value-grounding rules that push toward path:line mechanism, (iii) the approval gate without the architecture-summary has nothing to approve, (iv) the prescriptive-prose check operates on the new ticket template that only the trimmed §2 produces, (v) the events instrument gates that only exist after the trim. §3(a) same-file overlap drives the consolidation: pieces 3-6 live in `decompose.md`; piece 2 lives in `research.md`; piece 1 in `clarify.md` — but the three files are read together as the discovery-skill reference set and only ship coherent as a unit. Per the augmented §4: single piece, single ticket, no epic.

## Suggested Implementation Order

One ticket, no ordering. Within the ticket's spec.md, the spec-phase re-walk obligation runs before code changes — load-bearing empirical validation step per `discovery_source` DR-1.

## Created Files

- `backlog/195-reframe-discovery-to-principal-architect-posture.md` — the ticket

## Notes

- No children, no epic — `decompose.md` §4's "single-piece → no epic" branch (which this ticket itself will introduce when implemented)
- DR-2 (refine-side strengthening) deferred per research; surface as follow-up only if novel-piece vagueness persists
- Spec phase MUST re-walk the refined shape against `research/vertical-planning/` plus one alternative corpus before implementation lands — codified in the ticket's edges
