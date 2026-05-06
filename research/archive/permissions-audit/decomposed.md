# Decomposition: permissions-audit

## Epic
- **Backlog ID**: 054
- **Title**: Harden settings.json permissions for public distribution

## Work Items
| ID | Title | Priority | Size | Depends On |
|----|-------|----------|------|------------|
| 055 | Verify escape hatch bypass mechanism | high | S | -- |
| 056 | Apply confirmed-safe permission tightening | high | M | -- |
| 057 | Remove interpreter escape hatch commands | medium | S | 055 |
| 058 | Close exfiltration channels in sandbox-excluded commands | high | M | -- |

## Key Design Decisions

**Consolidation**: Merged 7 S-sized items (DR-1, DR-3, DR-4, DR-5, DR-6, DR-7, unused entry removal) into ticket 056 — all modify the same file (`claude/settings.json`), all confirmed-safe, no dependencies between them. Ticket 056 subsumes backlog 047.

**WebFetch approach (Option A)**: Remove from allow list (prompt-based approval in interactive sessions), keep in `excludedCommands` (sandbox doesn't block when approved). Context7 and Perplexity handle most research; direct WebFetch is rare.

**Framing**: Template optimizes for public safety. Power-user additions go to `settings.local.json`.

## Suggested Implementation Order

1. **055 + 056 + 058 in parallel** — the spike (055), confirmed-safe changes (056), and exfiltration fixes (058) are all independent
2. **057 after 055** — escape hatch removal depends on spike results

056 and 058 both modify `claude/settings.json` but touch different sections (allow/deny list vs. sandbox config + gh patterns), so they can be implemented in parallel or sequentially.

## Created Files
- `backlog/054-harden-settingsjson-permissions-for-public-distribution.md` — Epic
- `backlog/055-verify-escape-hatch-bypass-mechanism.md` — Spike: test bash -c bypass
- `backlog/056-apply-confirmed-safe-permission-tightening.md` — Remove Read(~/**), wildcards, expand deny list, etc.
- `backlog/057-remove-interpreter-escape-hatch-commands.md` — Remove bash/sh/python/node wildcards (blocked by 055)
- `backlog/058-close-exfiltration-channels-in-sandbox-excluded-commands.md` — Narrow gh, prompt WebFetch, deny git remote add
