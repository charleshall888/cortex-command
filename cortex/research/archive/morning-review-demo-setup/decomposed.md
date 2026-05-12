# Decomposition: morning-review-demo-setup

## Single Ticket (no epic)

One work item produced. No epic created.

## Work Items

| ID | Title | Priority | Size | Depends On |
|----|-------|----------|------|------------|
| 071 | Auto-launch demo at morning review via lifecycle.config.md demo-command | medium | M | — |

## Consolidation Applied

The `demo-command` template schema update (S) was merged into the main morning-review skill ticket because it has no standalone value — the field exists only to be read by the skill. Rule (b) applied: prerequisite with no independent deliverable value merged into the item it enables.

## Suggested Implementation Order

Single ticket — implement `demo-command` schema addition and morning review Step 2.5 together in one lifecycle run. The spec phase should resolve the open questions (per-repo vs. per-feature, mode detection, cleanup contract) before planning.

## Created Files

- `cortex/backlog/071-auto-launch-demo-at-morning-review.md` — Auto-launch demo at morning review via lifecycle.config.md demo-command
