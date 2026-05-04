# Decomposition: competing-plan-synthesis

## Single Ticket (no epic)

The discovery resolved to a single work item per operator decision (events.log:critical_review, 2026-05-04, "Pause for roadmap conversation"). No epic — the conversation is the only deliverable; downstream implementation tickets are gated on its outcome and intentionally not filed yet.

## Work Items

| ID | Title | Priority | Size | Depends On |
|----|-------|----------|------|------------|
| 158 | Roadmap conversation: scope autonomous overnight critical-tier plan-phase invocation | high | S | — |

## Suggested Implementation Order

Single ticket; no order needed. Hold the conversation. Outcome determines whether follow-on tickets get filed for:

- (a) Path-building epic (`cortex overnight start --include-unrefined` or similar) → followed by synthesis-design tickets gated on observed events
- (b) Async-notify-with-timeout for existing interactive flow only → DR-6 from research.md becomes a single S-M ticket
- (c) Synthesis-via-async-operator-decision → DR-3 Option 4 + DR-4 + DR-5 from research.md become tickets, but no autonomous selector and no path-building

## Key Design Decisions

- **No epic filed.** The discovery surfaced enough internal contradictions (per `research/competing-plan-synthesis/events.log` critical_review entry) that filing implementation tickets prematurely would commit scope the team hasn't chosen. The single-ticket-roadmap-conversation form lets the next backlog wave aim correctly.
- **research.md preserved with all conditional DRs.** DR-2 through DR-7 remain valid as conditional recommendations that activate post-conversation if the path-building or synthesis-via-async-operator outcomes are chosen. This avoids re-running discovery.
- **No flagged items.** The single Value claim is grounded in `plan.md:107-109` (where the problem manifests) and `requirements/pipeline.md` (where the solution lands as a requirement); research.md Q4 substantiates with `[file:line]` citations.

## Created Files

- `backlog/158-roadmap-conversation-scope-autonomous-overnight-critical-tier-plan-phase-invocation.md` — Roadmap conversation: scope autonomous overnight critical-tier plan-phase invocation
