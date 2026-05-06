# Decomposition: session-window-naming

## Work Items

| ID | Title | Priority | Size | Depends On |
|----|-------|----------|------|------------|
| 008 | Auto-rename Claude Code session to active lifecycle feature name | medium | S | anthropics/claude-code#34243 (blocked) |

## Notes

- Item: "Skill suggests /rename" — rejected by user. Only fully automatic naming is worth implementing.
- Item: "Set Ghostty window title via /dev/tty in SessionStart hook" — rejected by user.
- Item: "Shell prompt segment for persistent Ghostty window titles" — rejected (machine-config scope, user not interested).
- Ghostty has no concept of a window name distinct from the tab title. OSC 0/2 set the surface title which surfaces as both the tab title and the macOS window bar title. No independent window-level naming exists.

## Suggested Implementation Order

When anthropics/claude-code#34243 ships, implement 008. No action until then.

## Created Files

- `backlog/008-auto-rename-claude-session-to-lifecycle-feature.md` — Auto-rename Claude Code session to active lifecycle feature name (blocked)
