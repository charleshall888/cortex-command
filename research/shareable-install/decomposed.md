# Decomposition: shareable-install

## Epic
- **Backlog ID**: 003
- **Title**: Make cortex-command shareable without overwriting users' global Claude settings

## Work Items
| ID | Title | Priority | Size | Depends On |
|----|-------|----------|------|------------|
| 004 | Prep hooks and apiKeyHelper for sharing | high | M | — |
| 005 | Non-destructive CLAUDE.md strategy | medium | M | — |
| 006 | Make `just setup` additive by default | high | M | 004 |
| 007 | Build `/setup-merge` local skill | medium | L | 004, 006 |

## Suggested Implementation Order

1. **004 and 005 in parallel** — both are independent. 004 is the atomic hook rename + apiKeyHelper stub; 005 is the `~/.claude/rules/` verification and Agents.md split. Both must complete before downstream work begins.
2. **006** — additive `just setup` can be built once hook names are finalized (004). Note: if 005 takes the `@import` fallback, 006's scope expands slightly (CLAUDE.md becomes a merge target).
3. **007** — the `/setup-merge` skill requires finalized hook names (004) and the conflict list output from `just setup` (006).

## Created Files
- `backlog/003-shareable-install-epic.md` — Epic: Make cortex-command shareable
- `backlog/004-prep-hooks-and-apikey-for-sharing.md` — Rename hooks + apiKeyHelper stub
- `backlog/005-non-destructive-claude-md-strategy.md` — Verify rules/ + split Agents.md
- `backlog/006-make-just-setup-additive.md` — Additive install + setup-force
- `backlog/007-build-setup-merge-skill.md` — /setup-merge local skill
