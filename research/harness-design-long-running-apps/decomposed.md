# Decomposition: harness-design-long-running-apps

## Epic
- **Backlog ID**: 018
- **Title**: Improve overnight execution quality through spec improvements and harness maintainability

## Work Items
| ID | Title | Priority | Size | Depends On |
|----|-------|----------|------|------------|
| 022 | Fix non-atomic state writes in overnight runner | high | S | — |
| 019 | Tighten lifecycle spec template and plan.md verification requirements | high | S | — |
| 023 | Replace spec dump with JIT loading in implement prompt | high | M | — |
| 020 | Add harness component pruning checklist | medium | M | — |
| 021 | Define evaluator rubric for software features (spike) | low | S | 019 |

## Suggested Implementation Order
1. **022** first — concrete crash-risk bugs, no design decisions needed.
2. **019** and **023** in parallel — both high-value, independent. 019 improves spec quality upstream; 023 reduces context load per round.
3. **020** after — uses the load-bearing analysis from the deep investigation to populate the checklist.
4. **021** last, after 019 has run in overnight sessions — evidence-driven. Only build the evaluator rubric once you can observe what failures 019 didn't prevent.

## Created Files
- `backlog/018-harness-quality-improvements-epic.md` — epic
- `backlog/019-tighten-spec-template-and-plan-verification-requirements.md` — tighten spec template and plan.md verification requirements
- `backlog/020-add-harness-component-pruning-checklist.md` — harness component pruning checklist (updated with specific candidates)
- `backlog/021-define-evaluator-rubric-for-software-features.md` — evaluator rubric spike
- `backlog/022-fix-non-atomic-state-writes-in-overnight-runner.md` — fix crash-risk state write bugs
- `backlog/023-replace-spec-dump-with-jit-loading-in-implement-prompt.md` — eliminate context bloat in worker and brain prompts
