# Decomposition: subagent-model-routing

## Epic
- **Backlog ID**: 044
- **Title**: Route interactive subagents to Sonnet by default

## Work Items
| ID | Title | Priority | Size | Depends On |
|----|-------|----------|------|------------|
| 045 | Verify CLAUDE_CODE_SUBAGENT_MODEL priority order | high | S | — |
| 046 | Implement Sonnet default for interactive subagents | high | M | 045 |

## Suggested Implementation Order

1. **045** first — 5-minute empirical test that determines the implementation approach for 046
2. **046** after spike resolves — the approach (env var vs per-skill params) depends entirely on the spike result

## Created Files
- `backlog/044-route-interactive-subagents-to-sonnet-epic.md` — Epic: Route interactive subagents to Sonnet by default
- `backlog/045-verify-subagent-model-env-var-priority.md` — Spike: Verify CLAUDE_CODE_SUBAGENT_MODEL priority order
- `backlog/046-implement-sonnet-default-for-interactive-subagents.md` — Feature: Implement Sonnet default for interactive subagents
