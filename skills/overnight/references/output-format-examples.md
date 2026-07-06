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
| 2 | Add export to CSV | #038 | feature | medium | plan ready |

## Execution Strategy

- **Rounds**: 2
- **Throttle**: tier-based adaptive (round size determined by conflict tiers)
- **Features**: 2 (1 per round)

## Not Ready

| Feature | Reason |
|---------|--------|
| Add dark mode | Missing spec (`cortex/lifecycle/<feature-slug>/spec.md` not present) |

## Risk Assessment

- Round 2 depends on Round 1 completing successfully (export reads auth state)

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
    "add-export-to-csv"
  ]
}
```
