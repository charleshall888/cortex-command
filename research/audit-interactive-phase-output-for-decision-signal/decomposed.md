# Decomposition: audit-interactive-phase-output-for-decision-signal

## Epic
- **Backlog ID**: 66
- **Title**: Suppress non-decision output in interactive lifecycle phases

## Work Items

| ID | Title | Priority | Size | Depends On |
|----|-------|----------|------|------------|
| 67 | Restructure critical-review Step 4 to suppress Dismiss output | high | S | — |
| 68 | Suppress Dismiss-rationale leak in lifecycle clarify critic | high | S | — |
| 69 | Suppress internal narration in lifecycle specify phase | high | M | — |

## Suggested Implementation Order

All three tickets are independent. Suggested order by blast radius:

1. **#067** (critical-review Step 4) — affects standalone `/critical-review` use AND spec §3b. Smallest change, highest per-session visibility. Good first candidate to validate the "eliminate Dismiss requirement" approach before applying to other phases.
2. **#068** (clarify critic) — affects every lifecycle feature start. Once Step 4 behavior is validated in #067, this applies the same principle to the clarify phase.
3. **#069** (specify phase) — broadest file scope (two files, four locations). The fix-agent report absorption in orchestrator-review.md is the most structural change. Best done last once the simpler suppression patterns are validated.

## Key Design Decisions

- **Consolidation**: Specify §2a and §2b were originally proposed as separate items but share `specify.md` as their primary file → merged into ticket #069 along with the §3a/orchestrator-review.md location.
- **Mechanism note**: These fixes target the *requirement surface* (what the instructions require the orchestrator to output), not format-tightening. "Compact summary" already failed as a format instruction; removing the Dismiss output requirement is the structural approach.
- **Out-of-scope follow-up**: `/refine` Step 6 completion announcement has the same "summarize everything" pattern as critical-review Step 4. Out of commissioned scope for this epic; worth a separate ticket if the pattern recurs.

## Created Files

- `backlog/066-suppress-non-decision-output-in-interactive-phases-epic.md` — Epic
- `backlog/067-restructure-critical-review-step4-suppress-dismiss-output.md` — critical-review Step 4
- `backlog/068-suppress-dismiss-rationale-leak-in-lifecycle-clarify-critic.md` — clarify critic Dismiss-rationale
- `backlog/069-suppress-internal-narration-in-lifecycle-specify-phase.md` — specify phase narration
