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
1. **019 and 022 in parallel** — both have no dependencies (`blocked-by: []`). Note the evidentiary asymmetry: 019 has three confirmed real failure instances; 022 is a crash-risk fix with no observed occurrence in session history. Either can go first; they do not block each other.
2. **023** — independent of 019/022; reduces context load per round and deserves signal-distribution analysis before the brain truncation piece is implemented.
3. **020** after — uses the load-bearing analysis from the deep investigation to populate the checklist.
4. **021** last, after 019 has run in overnight sessions — only build the evaluator rubric once you can observe what failures 019 didn't prevent.

## Created Files
- `cortex/backlog/018-harness-quality-improvements-epic.md` — epic
- `cortex/backlog/019-tighten-spec-template-and-plan-verification-requirements.md` — tighten spec template and plan.md verification requirements
- `cortex/backlog/020-add-harness-component-pruning-checklist.md` — harness component pruning checklist (updated with specific candidates)
- `cortex/backlog/021-define-evaluator-rubric-for-software-features.md` — evaluator rubric spike
- `cortex/backlog/022-fix-non-atomic-state-writes-in-overnight-runner.md` — fix crash-risk state write bugs
- `cortex/backlog/023-replace-spec-dump-with-jit-loading-in-implement-prompt.md` — eliminate context bloat in worker and brain prompts
