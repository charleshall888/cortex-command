# Decomposition: overnight-plan-building

## Work Items
| ID | Title | Priority | Size | Depends On |
|----|-------|----------|------|------------|
| 048 | Trim and instrument overnight plan-gen prompt | low | S | — |

## Key Design Decisions

**Combined two items into one ticket**: Conditional prompt inclusion and trigger instrumentation both touch the plan-gen prompt boundary (runner.sh template filling and orchestrator-round.md). Splitting them would create two S-sized tickets modifying overlapping files with no independent delivery value for the instrumentation alone.

## Suggested Implementation Order

Single ticket — no ordering needed.

## Created Files
- `cortex/backlog/048-trim-and-instrument-overnight-plan-gen-prompt.md` — Conditional prompt trimming + plan-gen trigger event logging
