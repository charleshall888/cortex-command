# Specification: Overnight Runner OAuth Token Support

## Problem Statement

The overnight runner spawns `claude -p` subprocesses that fail with "Not logged in" when no `ANTHROPIC_API_KEY` is set and the macOS Keychain OAuth token has expired. Users operate in two modes — work repos (API key via `apiKeyHelper`) and personal repos (OAuth subscription) — but the runner only supports the API key path. This makes overnight sessions unreliable for personal repos. The fix adds `CLAUDE_CODE_OAUTH_TOKEN` support so both modes work reliably.

## Requirements

1. **Token file storage**: A personal OAuth token can be stored at `~/.claude/personal-oauth-token` with mode 600 permissions.
   - AC: File exists with mode 600 (`stat -f '%Lp' ~/.claude/personal-oauth-token` = `600`); runner reads it successfully.

2. **Runner auth resolution — API key path (existing)**: When `apiKeyHelper` is configured in settings.json, runner exports `ANTHROPIC_API_KEY` from the helper output. No change to this path.
   - AC: `grep -c 'apiKeyHelper' claude/overnight/runner.sh` >= 1; the apiKeyHelper code path (lines 50-66) is preserved unmodified.

3. **Runner auth resolution — OAuth fallback (new)**: When no `apiKeyHelper` is configured and `CLAUDE_CODE_OAUTH_TOKEN` is not already in the environment, the runner reads `~/.claude/personal-oauth-token` and exports `CLAUDE_CODE_OAUTH_TOKEN`.
   - AC: `grep -c 'CLAUDE_CODE_OAUTH_TOKEN' claude/overnight/runner.sh` >= 1; `grep -c 'personal-oauth-token' claude/overnight/runner.sh` >= 1. Interactive/session-dependent: full end-to-end verification (runner → claude -p → authenticated) requires a valid token and running Claude Code subprocess.

4. **Runner auth resolution — env var precedence**: If `ANTHROPIC_API_KEY` is already set in the environment, the runner skips all resolution (existing). If `CLAUDE_CODE_OAUTH_TOKEN` is already set in the environment, the runner uses it without reading the file.
   - AC: Observable in code: the `ANTHROPIC_API_KEY` guard at line 50 (`if [[ -z "${ANTHROPIC_API_KEY:-}" ]]`) short-circuits before OAuth resolution. The `CLAUDE_CODE_OAUTH_TOKEN` guard checks the env var before reading the file. `grep -c 'CLAUDE_CODE_OAUTH_TOKEN:-' claude/overnight/runner.sh` >= 1.

5. **dispatch.py env propagation**: `CLAUDE_CODE_OAUTH_TOKEN` is forwarded to SDK subagents alongside `ANTHROPIC_API_KEY` in the `_env` dict.
   - AC: `grep -c 'CLAUDE_CODE_OAUTH_TOKEN' claude/pipeline/dispatch.py` >= 1; env var propagates to subagents.

6. **smoke_test.py auth reporting**: `_check_auth_pre_flight()` recognizes `CLAUDE_CODE_OAUTH_TOKEN` as a valid auth method. When `CLAUDE_CODE_OAUTH_TOKEN` is set, reports "OK" regardless of apiKeyHelper state — OAuth env var takes precedence over the apiKeyHelper="" empty-string check. `_check_worktree_auth()` error message (line 250) updated to not mislead OAuth users into chasing settings.local.json issues.
   - AC: Running smoke test with `CLAUDE_CODE_OAUTH_TOKEN` set and no apiKeyHelper → output contains "[auth] OK". `grep -c 'CLAUDE_CODE_OAUTH_TOKEN' claude/overnight/smoke_test.py` >= 1 in both `_check_auth_pre_flight` and the worktree failure message context.

7. **docs/overnight.md auth section**: New "Authentication" section documenting three auth modes (API key via apiKeyHelper, OAuth token via file, OAuth token via env var), with setup instructions for each.
   - AC: `grep -c 'Authentication' docs/overnight.md` >= 1; section covers all three modes.

8. **docs/setup.md auth section**: New section in the machine setup guide covering overnight auth setup — how to choose between API key and OAuth, and how to configure each.
   - AC: `grep -c 'apiKeyHelper\|CLAUDE_CODE_OAUTH_TOKEN' docs/setup.md` >= 1.

## Non-Requirements

- **count-tokens / audit-doc**: These use the Anthropic Python SDK directly, which requires `ANTHROPIC_API_KEY` (not `CLAUDE_CODE_OAUTH_TOKEN`). Their existing behavior — error on personal subscription repos — is correct and unchanged.
- **Token format validation**: The runner reads the file contents as-is. If the token is malformed, `claude -p` will report the auth error — no duplicate validation.
- **Settings.json changes**: `CLAUDE_CODE_OAUTH_TOKEN` is environment-variable-based. No new settings.json fields.
- **merge_settings.py changes**: The setup-merge skill handles `apiKeyHelper` merging. OAuth tokens are env-var-only and don't need merge logic.
- **Automated token creation**: `claude setup-token` requires a browser. The setup docs explain the manual steps; `just setup` does not attempt to create the token.

## Edge Cases

- **Token file missing**: Runner prints a warning ("No OAuth token file found at ~/.claude/personal-oauth-token — claude -p will use Keychain auth if available") and falls through. Not a fatal error.
- **Token file empty**: Same as missing — the read returns empty string, no `CLAUDE_CODE_OAUTH_TOKEN` is exported, warning printed.
- **Both ANTHROPIC_API_KEY and CLAUDE_CODE_OAUTH_TOKEN set**: `ANTHROPIC_API_KEY` takes precedence per Claude Code's auth precedence. Runner doesn't need to arbitrate — Claude Code handles it.
- **apiKeyHelper returns empty**: Existing behavior — falls through to OAuth token check (new), then to warning.
- **Token file has trailing newline**: Runner strips whitespace before exporting.

## Changes to Existing Behavior

- MODIFIED: `runner.sh` auth resolution block (lines 50-73) → adds OAuth token file read after apiKeyHelper check falls through
- MODIFIED: `dispatch.py` `_env` dict (lines 401-403) → adds `CLAUDE_CODE_OAUTH_TOKEN` forwarding
- MODIFIED: `smoke_test.py` `_check_auth_pre_flight()` (lines 167-188) → recognizes OAuth token env var as valid auth; OAuth env var takes precedence over apiKeyHelper="" check
- MODIFIED: `smoke_test.py` `_check_worktree_auth()` failure message (line 250) → updated to mention OAuth env-var-based auth as an alternative to settings.local.json
- MODIFIED: `runner.sh` warning message (line 70) → updated to mention OAuth token file as an option
- ADDED: `docs/overnight.md` Authentication section
- ADDED: `docs/setup.md` overnight auth section

## Technical Constraints

- `CLAUDE_CODE_OAUTH_TOKEN` is recognized by Claude Code CLI (`claude -p`, `claude_agent_sdk`) only — not by the Anthropic Python SDK. Utilities calling the SDK directly still need `ANTHROPIC_API_KEY`.
- Token generated by `claude setup-token` is valid for 1 year. Users must regenerate before expiry.
- The runner runs outside the Claude Code sandbox (in tmux). Sandbox restrictions don't affect token file reads.
- `~/.claude/` is the standard Claude Code config directory and is not on the sandbox deny list for reads.

## Open Decisions

None — all decisions resolved during spec.
