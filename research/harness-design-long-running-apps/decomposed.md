# Decomposition: harness-design-long-running-apps

## Epic
- **Backlog ID**: 018
- **Title**: Improve overnight execution quality through spec improvements and harness maintainability

## Work Items
| ID | Title | Priority | Size | Depends On |
|----|-------|----------|------|------------|
| 019 | Tighten lifecycle spec template and plan.md verification requirements | high | S | — |
| 020 | Add harness component pruning checklist | medium | M | — |
| 021 | Define evaluator rubric for software features (spike) | low | S | 019 |

## Suggested Implementation Order
1. **019** first — highest leverage, lowest effort, no dependencies. Directly reduces overnight deferrals and improves self-evaluation quality.
2. **020** in parallel or after — independent of 019; schedule when there's capacity for a maintenance task.
3. **021** last, after 019 has run in overnight sessions — evidence-driven. Only build the evaluator rubric once you can observe what failures 019 didn't prevent.

## Created Files
- `backlog/018-harness-quality-improvements-epic.md` — epic
- `backlog/019-tighten-spec-template-and-plan-verification-requirements.md` — tighten spec template and plan.md verification requirements
- `backlog/020-add-harness-component-pruning-checklist.md` — harness component pruning checklist
- `backlog/021-define-evaluator-rubric-for-software-features.md` — evaluator rubric spike
