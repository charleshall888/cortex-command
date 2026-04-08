# Debug Session: claude -p "Not logged in" failure
Date: 2026-04-08
Status: Resolved

## Phase 1 Findings

### Observed behavior
`claude -p` fails with "Not logged in · Please run /login" (exit code 1). Reported as blocking the overnight runner, which spawns orchestrator agents via `claude -p "$PROMPT" --dangerously-skip-permissions --max-turns 50` (runner.sh:629).

### Evidence gathered

**Auth state diagnosis:**
- `claude auth status` (inside Claude Code sandbox) → `{"loggedIn": false, "authMethod": "none"}`
- `claude auth status` (outside sandbox / from tmux) → `{"loggedIn": true, "authMethod": "claude.ai", "subscriptionType": "max"}`
- `claude -p "say hello"` (inside sandbox) → "Not logged in" (exit 1)
- `claude -p "say hello"` (outside sandbox) → "Hello!" (exit 0)
- `claude -p` from a tmux session → works correctly

**Keychain investigation:**
- `security list-keychains` (inside sandbox) → only System.keychain visible
- `security list-keychains` (outside sandbox) → login.keychain-db + System.keychain
- Keychain entry "Claude Code-credentials" exists: account=charlie.hall, created=2026-04-06, modified=2026-04-08 11:52:43Z
- Keychain entry "Claude Safe Storage" exists: created=2026-03-07

**Version timeline:**
- 2.1.92 (Apr 4) — version running during Apr 7 overnight session at 00:14
- 2.1.94 (Apr 7 17:22) — upgrade after the overnight session
- 2.1.96 (Apr 8 00:55) — current version

**Settings:** No `apiKeyHelper` configured. No `ANTHROPIC_API_KEY` env var set. Sandbox enabled in settings.json.

### Root cause

**Two compounding issues:**

1. **Primary: Claude Code's process sandbox blocks macOS Keychain access.** When `claude -p` is spawned from within a sandboxed Claude Code session (via the Bash tool or `!` command), the sandbox prevents the child process from accessing the login keychain. The `security list-keychains` API only returns the System keychain inside the sandbox. Since OAuth credentials are stored in the login keychain, the child `claude -p` process reports "Not logged in."

2. **Secondary: OAuth token expiration.** The user likely observed the failure from a normal terminal too, because the OAuth token (created April 6) had expired by April 8. Starting the current interactive Claude Code session triggered a browser re-auth, refreshing the credentials (mdat updated to April 8 11:52). After refresh, `claude -p` from tmux works again.

**Why it worked on April 7:** The OAuth token was ~6 hours old (created April 6 18:18, used April 7 00:14), still within its validity window.

**Why it broke:** Either (a) the token expired naturally (~30 hours later), or (b) the version upgrade from 2.1.92 to 2.1.94/2.1.96 changed the credential format or invalidated the old token.

### Dead-ends
- `~/.claude/work-api-key` (109 bytes) — not referenced anywhere in the codebase, unrelated
- No `.credentials.json` file exists (macOS uses Keychain, not file-based storage)
- No Keychain entries found under service names "claude" or "anthropic" — the actual service name is "Claude Code-credentials"

## Phase 2 Findings

### Auth precedence (from official docs)
1. Cloud provider credentials (Bedrock/Vertex/Foundry)
2. `ANTHROPIC_AUTH_TOKEN` env var
3. `ANTHROPIC_API_KEY` env var
4. `apiKeyHelper` script output
5. Subscription OAuth credentials from `/login` (stored in macOS Keychain)

`claude -p` non-interactive mode uses the same precedence. OAuth (#5) works for `claude -p` if the Keychain is accessible and the token hasn't expired.

### Overnight runner auth flow
- runner.sh (lines 50-73) checks for `apiKeyHelper` in settings.json
- No `apiKeyHelper` configured → falls through with warning "subagents will use subscription billing"
- "Subscription billing" = OAuth credentials from Keychain = works from tmux, fails from sandbox

## Current State

Root cause identified: sandbox blocks Keychain access for in-session testing; OAuth token expiration causes real overnight failures if the token has aged.

**The overnight runner itself (launched via `overnight-start` → tmux) is NOT affected by the sandbox** — it runs outside Claude Code. The user's test from within Claude Code was the misleading signal. The real risk is token expiration between login and overnight session start.

**For reliability**, the runner needs either:
- Fresh OAuth login shortly before launching the overnight session
- `CLAUDE_CODE_OAUTH_TOKEN` env var (reported as valid for 1 year)
- `apiKeyHelper` that reads from a stable credential source
