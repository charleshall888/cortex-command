# Decomposition: critical-review scope-expansion bias

## Single Ticket

No epic — discovery produced exactly one high-value, high-confidence work item.

## Work Items

| ID | Title | Priority | Size | Depends On |
|----|-------|----------|------|------------|
| 132 | Classify /critical-review findings by class and add B-class action surface | high | M | — |

## Suggested Implementation Order

Ship ticket 132 via `/lifecycle` when ready. Validate classifier accuracy on at least one historical /critical-review output before merging to surface LLM-classification noise before it becomes a production regression.

## Created Files

- `backlog/132-classify-critical-review-findings-and-add-b-class-action-surface.md` — primary ticket
- `backlog/132-classify-critical-review-findings-and-add-b-class-action-surface.events.jsonl` — sidecar

## Key Design Decisions

- **FP1+FP2+B-class action surface bundled into one ticket.** Per research DR-4, FP1 has no standalone deliverable value — it produces typed findings that nothing consumes. Per DR-1, the B-class action surface is a required acceptance criterion; it is not a deferred design question. Splitting these three into separate tickets would produce artificial dependencies and risk shipping FP1 without the guard FP2 needs, or FP2 without the dismissal-guard mechanism that Q6 requires.

- **FP3 (Apply-bar tightening), FP4 (operator preamble), FP6 (input framing), H6 (convergence signal fate) — dropped from this decomposition.** Applied the user's high-value/high-confidence filter:
  - FP3 — last-mile routing rule; the Kotlin failure was operator interpretation, not auto-apply of C-class, so low leverage
  - FP4 — research itself labels this low-efficacy ("a preamble is the fix you ship when you don't want to ship the fix")
  - FP6 — addresses C-class synthesis emergence, a related but distinct failure mode from documented Kotlin B→A promotion; speculative until that mode is observed
  - H6 — hygiene cleanup of unused convergence-signal output; doesn't address scope-expansion bias

  Each remains documented in research.md and can be promoted to a ticket if a new failure mode surfaces that maps to it.

- **FP5 (architectural-pattern anchor) — not ticketed.** Per research DR-6, FP5 does not address the documented Kotlin failure (B-class adjacent-gap findings, not C-class wrong-layer objections) and carries false-anchor risk that would make things worse if pattern identification misfires. Remains documented in research.md for future promotion if a C-class-reviewer-objection failure is documented.

- **Base-rate telemetry, straddle-case protocol, class-count derivation — deferred to plan-time.** The research's Open Questions surface these as unresolved; ticket 132's acceptance criteria require them to be addressed during planning rather than being skipped or back-filled after ship.
