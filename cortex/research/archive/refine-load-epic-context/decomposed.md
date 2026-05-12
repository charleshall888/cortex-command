# Decomposition: refine-load-epic-context

## Single ticket (no epic)

The discovery produced one work item. Per discovery decompose protocol §4, no epic needed for a single ticket.

## Work Items

| ID | Title | Priority | Size | Depends On |
|----|-------|----------|------|------------|
| 161 | Add parent-epic alignment check to refine's clarify-critic | medium | S | — |

## Dropped Items

| Title | Reason | Originating context |
|-------|--------|---------------------|
| Author measurement plan for refine epic-context loader ROI | Process overhead disproportionate to the change; the rollback criterion is in the research artifact itself; post-deployment audit happens organically through use | Round 1 / round 2 decomposition |
| Bidirectional epic + sibling write-back design | Too much overhead for observed drift rate; would be the natural next step only if clarify-critic alignment proves insufficient | Conversation late-stage redesign |

## Suggested Implementation Order

Single ticket — implement directly via `/cortex-interactive:lifecycle 161`.

## Key Design Decisions

The discovery went through three round-and-redirect cycles before landing on this implementation shape:

1. **Round 1**: Recommended inline epic-context loading at Clarify worker phase with a new `bin/cortex-load-epic-context` script and Spec-phase fallback fire. Rejected after user redirect on over-anchoring concerns; `arxiv 2412.06593` (Nguyen & Lyu) confirmed framing-mitigation instructions are largely ineffective at countering anchoring bias.

2. **Round 2-F (initial)**: Recommended adding S7 epic-alignment item to refine's `orchestrator-review.md` checklist. Rejected on critical-review because (a) `orchestrator-review.md` mandates main-context execution, defeating the fresh-reviewer separation cited as motivation, and (b) binary pass/flag + full-rewrite fix-dispatch + 2-cycle cap has no workable disposition for deliberate-descope (C3) cases like ticket 064.

3. **Round 2-α**: Recommended adding "Epic alignment" angle to `/cortex-interactive:critical-review`'s auto-fire from `specify.md §3b`. Defensible — critical-review actually dispatches fresh parallel agents and supports per-objection Apply / Dismiss / Ask. Stale during user-led conversation that surfaced sibling-driven evolution as a deeper concern.

4. **Final (this ticket)**: Place the alignment check at clarify-critic instead of critical-review. Earlier catch (pre-research) has smaller blast radius. Uses an already-fresh-agent surface. Cheapest implementation. Honest about not addressing sibling-driven drift / stale epics / write-back hygiene — those are explicit out-of-scope decisions the user accepted to keep overhead proportional to observed drift rate.

## Created Files

- `cortex/backlog/161-add-parent-epic-alignment-check-to-refine-clarify-critic.md` — the implementation ticket
