# Decomposition: dashboard-command-station

## Epic
- **Backlog ID**: 410
- **Title**: Overhaul the dashboard into a read-only project command station

## Work Items
| ID | Title | Priority | Size | Depends On |
|----|-------|----------|------|------------|
| 411 | Add the dashboard ticket feed with upstream blocker-key hygiene | high | M | — |
| 412 | Add the triage board panel and the active-vs-archive landscape strip | medium | M | 411 |
| 413 | Add /tickets/{id} pages rendering ticket bodies and lifecycle artifacts | medium | M | 411 |
| 414 | Enrich dashboard seed fixtures with board- and reader-shaped variety | medium | M | — |
| 415 | Reconcile dashboard docs and observability requirements with reality | medium | S | — |

## Suggested Implementation Order

411 first (hygiene fix inside it lands before the feed wires in), then 412 and 413 in either order (413's no-sanitizer stance requires 415's bind-address/docstring correction to land no later than 413), with 414 alongside 412/413 to supply fixtures for visual development, and 415's second stage (the observability.md regather) completing after 412 lands.

## Grouping Notes
- **Ticket 411** ← pieces "Hygiene guard" + "Ticket feed". The hygiene fix is the parse-boundary correctness the feed consumes. Intra-group order: hygiene fix + warn guard → feed wiring (internal phase boundary, not a cross-ticket dependency).
- **Ticket 412** ← pieces "Triage board" + "Landscape strip". Both are pure renderings of the same feed state at the same cadence. Intra-group order: board → strip.
- Pieces "Ticket reader", "Fixture & test surface", and "Docs & requirements reconciliation" map 1:1 to tickets 413/414/415. Per-phase test additions from the fixture piece are carried as edges on each feature ticket rather than pooled.

## Consolidation Notes
- Pieces 1+2 (previous-batch numbering) merged into surviving ticket 1 → backlog 411; revised role: in-memory backlog snapshot standing on a warn-guarded parse boundary. Rationale: the feed has no correct output while the blocker-key landmine stands, and both touch the same parse boundary.
- Pieces 3+5 (previous-batch numbering) merged into surviving ticket 2 → backlog 412; revised role: the two read-only renderings of feed state (decision panel + settled-corpus strip). Rationale: same data source, same cadence, one PR in practice.
- Both consolidations user-directed at the decompose-commit gate ("Try to consolidate", revision round 1), approved at round 2.

## Created Files
- `cortex/backlog/410-overhaul-the-dashboard-into-a-read-only-project-command-station.md` — Overhaul the dashboard into a read-only project command station (epic)
- `cortex/backlog/411-add-the-dashboard-ticket-feed-with-upstream-blocker-key-hygiene.md` — Add the dashboard ticket feed with upstream blocker-key hygiene
- `cortex/backlog/412-add-the-triage-board-panel-and-the-active-vs-archive-landscape-strip.md` — Add the triage board panel and the active-vs-archive landscape strip
- `cortex/backlog/413-add-tickets-id-pages-rendering-ticket-bodies-and-lifecycle-artifacts.md` — Add /tickets/{id} pages rendering ticket bodies and lifecycle artifacts
- `cortex/backlog/414-enrich-dashboard-seed-fixtures-with-board-and-reader-shaped-variety.md` — Enrich dashboard seed fixtures with board- and reader-shaped variety
- `cortex/backlog/415-reconcile-dashboard-docs-and-observability-requirements-with-reality.md` — Reconcile dashboard docs and observability requirements with reality
