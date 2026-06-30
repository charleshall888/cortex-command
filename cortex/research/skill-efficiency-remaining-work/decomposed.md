# Decomposition: skill-efficiency-remaining-work

## Epic
- **Backlog ID**: 340
- **Title**: Core-skill efficiency survivors of the post-#336 adversarial audit

## Work Items
| ID | Title | Priority | Size | Depends On |
|----|-------|----------|------|------------|
| 341 | Extract the critical-only competing-plans block to a lazy reference | high | S–M | — |
| 342 | Fix morning-review pre-merge auto-close ordering bug | high | S | — |
| 343 | Relocate dev-router triage logic to a branch-gated reference | medium | S–M | — |
| 344 | Record per-phase context isolation as declined (wontfix) | low | — | — |

## Suggested Implementation Order
1. **#342** first — it is a live correctness bug (two contradictory orderings of a destructive action); a contradiction misleads the model on every read, so fixing it has the highest value-per-effort despite near-zero bytes.
2. **#341** next — the largest resident-token reduction (~10.9KB off ~98% of plan reads) on the hottest interactive path, low risk.
3. **#343** — the smallest; removes dilution from four of five dev-router branches.
4. **#344** ships as a wontfix decision record — no build.

The four are independent (different skills, no shared seam, no inter-ticket dependencies), so order is by value, not by dependency.

## Created Files
- `cortex/backlog/340-core-skill-efficiency-survivors-of-the-post-336-adversarial-audit.md` — epic
- `cortex/backlog/341-extract-the-critical-only-competing-plans-block-to-a-lazy-reference.md`
- `cortex/backlog/342-fix-morning-review-pre-merge-auto-close-ordering-bug.md`
- `cortex/backlog/343-relocate-dev-router-triage-logic-to-a-branch-gated-reference.md`
- `cortex/backlog/344-record-per-phase-context-isolation-as-declined.md`

## Dropped / Declined at audit (not ticketed, recorded for provenance)
- **Backend-routing prose dedup** — net negative; the ~12 blocks route different actions with site-specific arms, the canonical block is write-back-specific, and standalone skills don't load it, so a pointer forces a larger read than it saves.
- **Demo-selection prose offload** — the demo-selection logic is an intentional model-judgment affordance shipped as #072, not bloat.
- **decompose.md regex/grouping dedup** — the repetition is a test-enforced anti-silent-mutation guard; the regex examples are scanner calibration; rarest path.
- **clarify-critic / plan-comparison event migration** — contested: `plan_comparison` has two deliberately parity-visible producers; migrating one severs that for a downstream metrics consumer, for ~1 line saved. Default-dropped pending the parity question (carried in research.md Open Questions).
