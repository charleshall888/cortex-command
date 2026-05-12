# Decomposition: gpg-signing-claude-code-sandbox

> **Correction (2026-04-13):** #081 was closed without implementing the decomposition below. The premise was wrong — `sandbox.excludedCommands` in `claude/settings.json` already excluded `git:*` from Seatbelt, so `git commit -S` always reached `~/.gnupg/` via the standard socket. The entire signing scaffolding was dead code and got deleted instead. See `research.md` top-of-file correction note for full context. The suggestions below describe the abandoned fix approach and should not be acted on.

## Single Ticket (no epic)

| ID | Title | Priority | Size | Depends On |
|----|-------|----------|------|------------|
| 081 | Fix GPG sandbox signing with stable gnupghome path and read-only options | high | S | — |

## Consolidation Note

Two distinct file changes (hook + commit skill) were consolidated into one ticket. Neither delivers working GPG signing in isolation — both path changes must be consistent to restore end-to-end signing behavior.

## Suggested Implementation Order

Single ticket, implement as one lifecycle run:
1. Fix hook: remove TMPDIR sandbox detection, change gnupghome path to `$HOME/.local/share/gnupg/claude-gnupghome`, add `no-random-seed-file`/`no-auto-check-trustdb`/`lock-never` to gpg.conf, remove diagnostic logging
2. Fix commit skill step 5: update `test -f` path to `$HOME/.local/share/gnupg/claude-gnupghome/S.gpg-agent`
3. Verify end-to-end: start a new session, confirm gnupghome is created, confirm `git commit` signs successfully

## Created Files
- `cortex/backlog/081-fix-gpg-sandbox-signing-stable-gnupghome-path.md` — Fix GPG sandbox signing with stable gnupghome path and read-only options
