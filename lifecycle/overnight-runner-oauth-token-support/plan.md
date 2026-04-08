# Plan: Overnight Runner OAuth Token Support

## Overview

Add `CLAUDE_CODE_OAUTH_TOKEN` support to the overnight runner auth chain. The runner reads a stored OAuth token from `~/.claude/personal-oauth-token` when no `apiKeyHelper` is configured, exports it as an env var, and all downstream components (dispatch.py, smoke_test.py) propagate or recognize it. Documentation explains both auth modes so users can choose.

## Tasks

### Task 1: Update runner.sh auth resolution to support OAuth token
- **Files**: `claude/overnight/runner.sh`
- **What**: Add OAuth token resolution after the apiKeyHelper fallback path. When apiKeyHelper is not configured and `CLAUDE_CODE_OAUTH_TOKEN` is not already in env, read `~/.claude/personal-oauth-token`, strip whitespace, and export as `CLAUDE_CODE_OAUTH_TOKEN`. Update the warning message to mention the token file.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Current auth block at lines 50-73. The existing structure: outer guard checks `ANTHROPIC_API_KEY` (line 50), inner Python block resolves apiKeyHelper (lines 51-65), conditional export (lines 67-68), else warning (line 70). The new OAuth block goes inside the `else` branch at line 69 — after apiKeyHelper fails but before the warning. Read the file, strip whitespace, check non-empty, export. Token file path: `$HOME/.claude/personal-oauth-token`. The outer `ANTHROPIC_API_KEY` guard already short-circuits before this code runs.
- **Verification**: `grep -c 'CLAUDE_CODE_OAUTH_TOKEN' claude/overnight/runner.sh` >= 2 (env check + export) — pass if count >= 2. `grep -c 'personal-oauth-token' claude/overnight/runner.sh` >= 1 — pass if count >= 1.
- **Status**: [x] done

### Task 2: Update dispatch.py to forward OAuth token to SDK subagents
- **Files**: `claude/pipeline/dispatch.py`
- **What**: Add `CLAUDE_CODE_OAUTH_TOKEN` to the `_env` dict alongside `ANTHROPIC_API_KEY`, following the same pattern (check os.environ, add if present).
- **Depends on**: none
- **Complexity**: trivial
- **Context**: The `_env` dict at lines 401-403. Pattern: `if _api_key := os.environ.get("ANTHROPIC_API_KEY"): _env["ANTHROPIC_API_KEY"] = _api_key`. Add identical pattern for `CLAUDE_CODE_OAUTH_TOKEN` immediately after.
- **Verification**: `grep -c 'CLAUDE_CODE_OAUTH_TOKEN' claude/pipeline/dispatch.py` >= 1 — pass if count >= 1.
- **Status**: [x] done

### Task 3: Update smoke_test.py pre-flight auth check for OAuth
- **Files**: `claude/overnight/smoke_test.py`
- **What**: Update `_check_auth_pre_flight()` to recognize `CLAUDE_CODE_OAUTH_TOKEN` as valid auth. When the env var is set, print "[auth] OK: CLAUDE_CODE_OAUTH_TOKEN is set — OAuth token mode" and return early, before the apiKeyHelper checks. This gives OAuth env var precedence over apiKeyHelper="" empty-string check.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `_check_auth_pre_flight()` at lines 167-188. Currently: reads `settings.local.json`, checks `apiKeyHelper` value, prints status. Add an early check at the top of the function: if `os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")`, print OK and return. This must come before the `local_settings` file read (line 173) so it takes precedence.
- **Verification**: `grep -c 'CLAUDE_CODE_OAUTH_TOKEN' claude/overnight/smoke_test.py` >= 1 — pass if count >= 1. `grep -n 'CLAUDE_CODE_OAUTH_TOKEN' claude/overnight/smoke_test.py` shows the check appears before line 173 (the settings file read) — pass if line number < 173.
- **Status**: [x] done

### Task 4: Update smoke_test.py worktree auth error message
- **Files**: `claude/overnight/smoke_test.py`
- **What**: Update the `_check_worktree_auth()` failure message (around line 250 in the caller, or line 204 in the function itself) to mention that OAuth-based auth uses env vars, not settings.local.json. So OAuth users aren't misled into chasing a settings.local.json fix.
- **Depends on**: [3]
- **Complexity**: trivial
- **Context**: `_check_worktree_auth()` at lines 191-205. The failure path at line 204 prints: `"[auth] FAIL: settings.local.json exists in repo but was NOT copied to worktree ({dest})"`. The caller at the smoke test entry point (~line 248-251) prints: `"FAIL: settings.local.json was not copied to worktree — subscription auth misconfigured"` and exits. Add a note: if `CLAUDE_CODE_OAUTH_TOKEN` is set, this check is informational only (OAuth propagates via env vars, not files).
- **Verification**: `grep 'CLAUDE_CODE_OAUTH_TOKEN\|OAuth' claude/overnight/smoke_test.py | grep -i 'worktree\|env'` — pass if at least one line matches showing OAuth awareness in worktree context.
- **Status**: [x] done

### Task 5: Add Authentication section to docs/overnight.md
- **Files**: `docs/overnight.md`
- **What**: Add a new "## Authentication" section after the "Per-repo Overnight" section (~line 63). Document three auth modes: (1) API key via apiKeyHelper for work repos, (2) OAuth token via file for personal repos, (3) OAuth token via env var for manual override. Include `claude setup-token` instructions for generating the token and file storage at `~/.claude/personal-oauth-token`.
- **Depends on**: none
- **Complexity**: simple
- **Context**: docs/overnight.md has no auth section. The section should go after "Per-repo Overnight" (ends ~line 63) and before "Prerequisites" (starts ~line 65). Reference the auth precedence: ANTHROPIC_API_KEY > apiKeyHelper > CLAUDE_CODE_OAUTH_TOKEN env var > token file > Keychain fallback. Explain that count-tokens/audit-doc still need ANTHROPIC_API_KEY (different consumer).
- **Verification**: `grep -c '## Authentication' docs/overnight.md` = 1 — pass if count = 1. `grep -c 'CLAUDE_CODE_OAUTH_TOKEN' docs/overnight.md` >= 1 — pass if count >= 1. `grep -c 'apiKeyHelper' docs/overnight.md` >= 1 — pass if count >= 1.
- **Status**: [x] done

### Task 6: Add auth setup section to docs/setup.md
- **Files**: `docs/setup.md`
- **What**: Add a new section covering overnight runner auth setup. Explain how to choose between API key (work) and OAuth (personal), with step-by-step setup for each. Include file permissions, token generation command, and where the token file lives.
- **Depends on**: none
- **Complexity**: simple
- **Context**: docs/setup.md is a machine setup guide organized by component (Shell, Symlinks, etc.). Add the auth section where it logically fits — likely after the main symlink/deployment sections. Keep it focused on the overnight runner auth, not general Claude Code auth. Reference `claude setup-token`, `~/.claude/personal-oauth-token`, and `apiKeyHelper` in settings.json/settings.local.json.
- **Verification**: `grep -c 'CLAUDE_CODE_OAUTH_TOKEN\|personal-oauth-token' docs/setup.md` >= 1 — pass if count >= 1. `grep -c 'apiKeyHelper' docs/setup.md` >= 1 — pass if count >= 1.
- **Status**: [x] done

### Task 7: Store the user's OAuth token
- **Files**: `~/.claude/personal-oauth-token`
- **What**: Write the user's generated OAuth token to `~/.claude/personal-oauth-token` with mode 600. The token was generated via `claude setup-token` during the diagnostic session.
- **Depends on**: none
- **Complexity**: simple
- **Context**: The token value was provided by the user. File must have mode 600 (owner read/write only). Use `printf '%s'` to avoid trailing newline (the runner strips whitespace anyway, but clean storage is better).
- **Verification**: `stat -f '%Lp' ~/.claude/personal-oauth-token` = `600` — pass if mode is 600. `wc -c < ~/.claude/personal-oauth-token` shows non-zero byte count — pass if > 0.
- **Status**: [x] done

### Task 8: End-to-end verification
- **Files**: none (verification only)
- **What**: Verify the full auth chain works: runner reads token → exports env var → `claude -p` authenticates. Run `claude -p "say hello"` from a tmux session with `CLAUDE_CODE_OAUTH_TOKEN` set from the file.
- **Depends on**: [1, 7]
- **Complexity**: simple
- **Context**: Interactive/session-dependent: requires running `claude -p` with the token set, which needs a live Claude Code process and valid token.
- **Verification**: Interactive/session-dependent: full end-to-end verification requires spawning a `claude -p` subprocess with `CLAUDE_CODE_OAUTH_TOKEN` set and confirming it authenticates successfully. Cannot be verified by grep alone.
- **Status**: [x] done

## Verification Strategy

After all tasks complete:
1. `grep -c 'CLAUDE_CODE_OAUTH_TOKEN' claude/overnight/runner.sh claude/pipeline/dispatch.py claude/overnight/smoke_test.py` — all three files should have >= 1 match
2. `grep -c 'personal-oauth-token' claude/overnight/runner.sh` >= 1
3. `grep -c '## Authentication' docs/overnight.md` = 1
4. `stat -f '%Lp' ~/.claude/personal-oauth-token` = 600
5. End-to-end: from tmux, run `CLAUDE_CODE_OAUTH_TOKEN=$(cat ~/.claude/personal-oauth-token) claude -p "say hello"` — should authenticate and respond
6. `just test` — all existing tests still pass
