# Decomposition: overnight-merge-conflict-prevention

## Epic
- **Backlog ID**: 014
- **Title**: Overnight conflict prevention and visibility improvements

## Work Items
| ID | Title | Priority | Size | Depends On |
|----|-------|----------|------|------------|
| 015 | Surface conflict details inline in morning report | high | S | — |
| 016 | Add recovery guidance to morning report for conflicted features | high | S | 015 |
| 017 | Add `areas:` field to backlog items for conflict-aware round scheduling | medium | M | 015, 016 |

## Suggested Implementation Order

1. **015 first** — establishes the event log join (feature name normalization verified), surfaces conflict details. Lowest risk, highest immediate user value.
2. **016 second** — builds on 015's event log join to add recovery guidance. Also report.py only.
3. **017 last** — the scheduling root-cause fix. More complex (algorithm inversion in `group_into_batches()`), limited reliability on net-new projects. Ships after the visibility/recovery improvements provide near-term mitigation.

## Created Files
- `backlog/014-overnight-conflict-visibility-epic.md` — Epic: overnight conflict prevention and visibility improvements
- `backlog/015-surface-conflict-details-in-morning-report.md` — Surface conflict details inline in morning report
- `backlog/016-add-recovery-guidance-to-morning-report.md` — Add recovery guidance to morning report for conflicted features
- `backlog/017-areas-field-conflict-aware-scheduling.md` — Add `areas:` field to backlog items for conflict-aware round scheduling
