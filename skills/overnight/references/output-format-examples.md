# Output Format Examples

## overnight-plan.md

```markdown
# Overnight Session Plan

**Session ID**: overnight-2025-11-14-2230
**Generated**: 2025-11-14 22:30:15
**Throttle**: tier-based adaptive
**Time Limit**: 6h

## Selected Features

| Round | Feature | Backlog | Type | Priority | Pre-work |
|-------|---------|---------|------|----------|----------|
| 1 | Add user authentication | #042 | feature | high | plan needed |
| 1 | Fix pagination bug | #051 | bug | high | plan ready |
| 1 | Tighten login rate-limit | #053 | bug | high | plan ready |
| 2 | Add export to CSV | #038 | feature | medium | plan ready |
| 2 | Wire up audit log writer | #044 | feature | medium | plan ready |
| 2 | Backfill missing user timestamps | #046 | chore | medium | plan ready |
| 3 | Add admin-only dashboard route | #049 | feature | medium | plan ready |
| 3 | Document the auth flow | #055 | chore | low | plan ready |

## Execution Strategy

- **Rounds**: 3
- **Throttle**: tier-based adaptive (round size determined by conflict tiers)
- **Features**: 8 (3 in Round 1, 3 in Round 2, 2 in Round 3)

## Not Ready

| Feature | Reason |
|---------|--------|
| Add dark mode | Missing spec (`lifecycle/<feature-slug>/spec.md` not present) |

## Risk Assessment

- No file overlap detected within any round's features
- Round 2 depends on Round 1 completing successfully (audit log writer reads auth state)
- Round 3 is independent but scheduled after Round 2 to keep dashboard work off a churning auth surface

## Stop Conditions

- Zero progress in a round (all features fail or defer)
- Time limit reached (6h)
```

## session.json

```json
{
  "session_id": "overnight-2025-11-14-2230",
  "type": "overnight",
  "started": "2025-11-14T22:30:15Z",
  "features": [
    "add-user-authentication",
    "fix-pagination-bug",
    "add-export-to-csv"
  ]
}
```
