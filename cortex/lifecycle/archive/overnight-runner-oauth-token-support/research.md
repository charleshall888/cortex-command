# Research: Overnight Runner OAuth Token Support

## Problem Statement

The overnight runner's `claude -p` subprocesses fail with "Not logged in" when no `ANTHROPIC_API_KEY` is set and the macOS Keychain OAuth token has expired. The user operates in two modes: work repos (API key via `apiKeyHelper`) and personal repos (OAuth subscription). The runner needs to support both reliably.

## Codebase Analysis

### Component Map — Auth Touch Points

#### 1. runner.sh (lines 50-73) — PRIMARY

The runner's API key resolution block. Currently:
- Checks `ANTHROPIC_API_KEY` env var
- If not set, looks for `apiKeyHelper` in settings.json/settings.local.json
- Executes the helper and exports result as `ANTHROPIC_API_KEY`
- Falls through with warning if no helper configured

**Change needed**: In the fallback path (no apiKeyHelper), read a stored OAuth token and export `CLAUDE_CODE_OAUTH_TOKEN`. This is where the dual-mode selection happens — `apiKeyHelper` present = work, absent = personal OAuth.

#### 2. dispatch.py (lines 397-403) — SECONDARY

The SDK env propagation block. Currently constructs `_env` with `CLAUDECODE=""` and conditionally adds `ANTHROPIC_API_KEY`. The SDK merges `_env` on top of `os.environ` (per comment at line 398-399).

**Change needed**: Add `CLAUDE_CODE_OAUTH_TOKEN` forwarding alongside `ANTHROPIC_API_KEY`. Although the token would propagate via `os.environ` inheritance, explicit forwarding is consistent with the existing pattern and makes the auth contract visible.

#### 3. smoke_test.py (lines 167-188) — MESSAGING ONLY

`_check_auth_pre_flight()` reports auth status based on `apiKeyHelper` in settings.local.json. Currently doesn't recognize OAuth token as a valid auth method.

**Change needed**: Update status messages to recognize `CLAUDE_CODE_OAUTH_TOKEN` as a valid auth path. When apiKeyHelper is empty/missing AND `CLAUDE_CODE_OAUTH_TOKEN` is set, report "OK: OAuth token configured" instead of a warning.

#### 4. bin/count-tokens and bin/audit-doc (lines 23-69) — NO CHANGE

Both use `resolve_api_key()` which talks to the Anthropic Python SDK directly. The SDK uses `ANTHROPIC_API_KEY`, NOT `CLAUDE_CODE_OAUTH_TOKEN`. OAuth tokens can't be used as API keys for direct SDK calls.

Current behavior when `apiKeyHelper == ""` (personal repo): exits with "Personal subscription repo — token counting requires an API key." This is correct — these utilities genuinely need an API key. No change needed.

#### 5. bin/overnight-start — NO CHANGE

Simple tmux launcher. Env vars from the caller's shell propagate into the tmux session and then to runner.sh. No auth logic of its own.

#### 6. docs/overnight.md — DOCUMENTATION NEEDED

No auth section exists. Mentions "subscription tier" in the concurrency context but doesn't document how authentication works for the runner.

**Change needed**: Add an "Authentication" section explaining:
- Work repos: `apiKeyHelper` in settings.json → API key
- Personal repos: `claude setup-token` → store in `~/.claude/personal-oauth-token` → runner reads it
- How tokens propagate through runner → `claude -p` → orchestrator

#### 7. docs/setup.md — DOCUMENTATION NEEDED

No auth section. Doesn't mention API keys or OAuth tokens.

**Change needed**: Add auth setup instructions to the machine setup guide.

### Components That DON'T Need Changes

| Component | Reason |
|-----------|--------|
| `batch_runner.py` | Calls `dispatch_task()` — auth handled by dispatch.py |
| `settings.json` | OAuth token is env-var-based, not a settings field |
| `merge_settings.py` | Only handles `apiKeyHelper` merging — OAuth is env-var-only |
| `cortex-worktree-create.sh` | Auth propagates via env inheritance, not worktree setup |
| `orchestrator-round.md` | Orchestrator prompt — doesn't handle auth |

## Token Storage Design

### Options Considered

1. **Shell profile (`~/.zshrc`)** — Simple but the token is visible in shell config, loaded into every shell session
2. **File with 600 permissions (`~/.claude/personal-oauth-token`)** — Analogous to `work-api-key` pattern. Readable only by owner. Runner reads it on demand.
3. **macOS Keychain via `security` CLI** — Most secure but adds complexity and platform-specific code
4. **`apiKeyHelper`-style script** — Flexible but overengineered for a static token

### Recommendation: File with 600 permissions

Store at `~/.claude/personal-oauth-token` (mode 600). Runner reads it when no apiKeyHelper is configured. This matches the existing `work-api-key` pattern in `~/.claude/`, keeps the token out of shell profiles, and works cross-platform.

## Auth Precedence in Runner

The runner's auth resolution should follow Claude Code's own precedence:

```
1. ANTHROPIC_API_KEY already in env → use it (work context, manually set)
2. apiKeyHelper configured → execute, export ANTHROPIC_API_KEY (work repos)
3. CLAUDE_CODE_OAUTH_TOKEN already in env → use it (personal, manually set)
4. ~/.claude/personal-oauth-token file exists → read, export CLAUDE_CODE_OAUTH_TOKEN
5. None of the above → warn, fall through to subscription (fragile)
```

Steps 1-2 are the existing behavior. Steps 3-4 are new.

## Key Insight: CLAUDE_CODE_OAUTH_TOKEN vs ANTHROPIC_API_KEY

These serve different consumers:
- `CLAUDE_CODE_OAUTH_TOKEN` → recognized by **Claude Code CLI** (`claude -p`, `claude_agent_sdk`)
- `ANTHROPIC_API_KEY` → recognized by **Anthropic Python SDK** (direct API calls)

The overnight runner spawns Claude Code processes (via `claude -p` and the Agent SDK), so `CLAUDE_CODE_OAUTH_TOKEN` is the correct variable. Standalone utilities that call the Anthropic SDK directly (count-tokens, audit-doc) still need `ANTHROPIC_API_KEY` and are not affected by this change.

## Open Questions

- None — all questions resolved during research.
