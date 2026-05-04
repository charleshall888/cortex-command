# Decomposition: competing-plan-synthesis

## Resolution

The discovery's roadmap question resolved to **shape (3): shared mechanism wired into both interactive §1b and overnight Step 3b** (events.log:discovery_conversation_resolved, 2026-05-04). An earlier decomposition attempt produced a single roadmap-conversation ticket (#158); the conversation happened within the discovery itself and #158 was repurposed as the epic. A second iteration of the decomposition (events.log:decomposition_consolidated) consolidated five children to three after a critical-review pass questioned whether all five tickets earned their place.

## Epic

- **Backlog ID**: 158
- **Title**: Build shared autonomous synthesis for critical-tier dual-plan flow (interactive + overnight)

## Work Items

| ID | Title | Priority | Size | Depends On |
|----|-------|----------|------|------------|
| 159 | Tighten §1b plan-agent prompt to require strategy-level distinction | high | S | — |
| 160 | Build autonomous synthesizer and ship into interactive §1b | high | L | — |
| 162 | Wire synthesizer into overnight orchestrator-round.md Step 3b | medium | M | 160 |

## Suggested Implementation Order

1. **#159** (tighten prompt) and **#160** (build synthesizer + ship interactively) — independent of each other, ship in parallel
2. **#162** (overnight wiring) — extends #160's synthesizer to unattended path; gated on operator-disposition data accumulated from #160 in production

## Key Design Decisions

- **Repurposed #158 from "roadmap conversation" to "epic"**: the conversation happened within the discovery (events.log:discovery_conversation_resolved); the original ticket was an artifact of that conversation. ID and UUID preserved; filename renamed; type changed to epic; body rewritten.
- **Consolidated 5 children → 3 after critical-review (events.log:decomposition_consolidated)**:
  - Original #163 ("calibration probes for synthesizer selector confidence") deleted. Its three probe types (identical-variants tie, position-swap consistency, planted-flaw) are unit tests of the synthesizer, not separate calibration infrastructure — absorbed into #160's test suite. The "documented baseline + threshold recommendation" framing was project-in-itself work; empirical threshold tuning happens against production operator-disposition data, not pre-shipment.
  - Original #161 ("wire synthesizer into interactive §1b with operator-override") merged into #160. Building a synthesizer with no consumer is speculative; per project requirements *"Complexity: Must earn its place by solving a real problem that exists now,"* synthesizer ships with its first consumer in one ticket.
  - Kept #159 standalone — independent quick win that benefits operators even without auto-synthesis (architecturally-distinct variants are easier to compare manually too).
  - Kept #162 standalone — different file (`orchestrator-round.md`), different runtime context (Python orchestrator, deferral handling, criticality state field), and a different gate (interactive validation must precede unattended).
- **No flagged items**: each child's Value claim is grounded in `[file:line]` citations to either `plan.md`, `orchestrator-round.md`, or research.md. No `[premise-unverified]` markers in the supporting research sections.
- **B-prime (constrained graft) deferred**: research.md DR-2 documents B-prime as pre-cleared next-step but not in scope for the epic. Conditional follow-on if post-shipment data shows graft-needed cases recurring.

## Created/Modified Files

- `backlog/158-build-shared-autonomous-synthesis-for-critical-tier-dual-plan-flow.md` — Epic
- `backlog/159-tighten-1b-plan-agent-prompt-to-require-strategy-level-distinction.md` — Child
- `backlog/160-build-autonomous-synthesizer-and-extended-plan-comparison-event-schema.md` — Child (filename retained from prior iteration; title updated to reflect merged scope)
- `backlog/162-wire-synthesizer-into-overnight-orchestrator-round-step-3b-criticality-branch.md` — Child
