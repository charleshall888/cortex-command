# Decomposition: competing-plan-synthesis

## Resolution

The discovery's roadmap question resolved to **shape (3): shared mechanism wired into both interactive §1b and overnight Step 3b** (events.log:discovery_conversation_resolved, 2026-05-04). An earlier decomposition attempt produced a single roadmap-conversation ticket (#158); the conversation happened within the discovery itself and #158 was repurposed as the epic.

## Epic

- **Backlog ID**: 158
- **Title**: Build shared autonomous synthesis for critical-tier dual-plan flow (interactive + overnight)

## Work Items

| ID | Title | Priority | Size | Depends On |
|----|-------|----------|------|------------|
| 159 | Tighten §1b plan-agent prompt to require strategy-level distinction | high | S | — |
| 160 | Build autonomous synthesizer + extended plan_comparison event schema | high | M-L | — |
| 161 | Wire synthesizer into interactive §1b (operator-override) | high | M | 160 |
| 162 | Wire synthesizer into overnight orchestrator-round.md Step 3b | medium | M | 160 |
| 163 | Calibration probes for synthesizer selector confidence | medium | M | 160 |

## Suggested Implementation Order

Per research.md DR-1.5: interactive ships first to validate the synthesizer under operator supervision; calibration gates the overnight wiring.

1. **#159** (tighten prompt) and **#160** (build synthesizer) — independent of each other, can run in parallel
2. **#161** (interactive wiring) — operator can override misfires; data flows into #163
3. **#163** (calibration) — empirical pass-fail gate before overnight ships
4. **#162** (overnight wiring) — last surface; runs unattended, must clear calibration first

## Key Design Decisions

- **Repurposed #158 from "roadmap conversation" to "epic"**: the conversation happened within the discovery (events.log:discovery_conversation_resolved); the original ticket was an artifact of that conversation. ID and UUID preserved; filename renamed; type changed to epic; body rewritten. Git history retains the original framing.
- **Five children, no further consolidation**: per decompose protocol §3, considered merging #163 (calibration) into #160 (synthesizer build) — rejected because calibration is a separate testing deliverable that gates #162 (overnight wiring), not part of the synthesizer's build acceptance criteria. Keeping calibration as its own ticket makes the gate explicit. Considered merging #159 (prompt tightening) into the epic body since it's a one-line edit — kept separate because it's independently shippable in parallel with #160.
- **No flagged items**: each child's Value claim is grounded in `[file:line]` citations to either `plan.md`, `orchestrator-round.md`, or research.md. No `[premise-unverified]` markers in the supporting research sections.
- **B-prime (constrained graft) deferred**: research.md DR-2 documents B-prime as pre-cleared next-step but not in scope for the epic. Conditional follow-on if post-shipment data shows graft-needed cases recurring.

## Created/Modified Files

- `backlog/158-build-shared-autonomous-synthesis-for-critical-tier-dual-plan-flow.md` — Epic (renamed from `158-roadmap-conversation-...`, body rewritten)
- `backlog/159-tighten-1b-plan-agent-prompt-to-require-strategy-level-distinction.md` — Child T1
- `backlog/160-build-autonomous-synthesizer-and-extended-plan-comparison-event-schema.md` — Child T2
- `backlog/161-wire-synthesizer-into-interactive-1b-with-operator-override.md` — Child T3
- `backlog/162-wire-synthesizer-into-overnight-orchestrator-round-step-3b-criticality-branch.md` — Child T4
- `backlog/163-calibration-probes-for-synthesizer-selector-confidence.md` — Child T5
