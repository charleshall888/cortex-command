# Research: fix-api-key-helper-reference

## Clarified Intent

Fix the broken `apiKeyHelper` reference in `claude/settings.json` that causes a startup error for new installers — without breaking the overnight pipeline's API key resolution.

## Codebase Analysis

### The broken reference

`claude/settings.json:3` — symlinked to `~/.claude/settings.json`:
```json
"apiKeyHelper": "~/.claude/get-api-key.sh"
```

The script `~/.claude/get-api-key.sh` does not exist in the repo (git log shows no history), is not created by `just setup`, and is not documented in `docs/setup.md`. When Claude Code reads `settings.json` at session startup and finds `apiKeyHelper`, it attempts to execute the script. If the file doesn't exist, Claude Code throws "No such file or directory" immediately — blocking all interactive usage, not just overnight.

### How apiKeyHelper is actually used

Three places in the codebase consume `apiKeyHelper`:

**1. Claude Code itself (interactive sessions):** Reads `apiKeyHelper` from `~/.claude/settings.json` at startup to resolve `ANTHROPIC_API_KEY`. Subscription users don't need it — `/login` handles auth. This is the source of the reported error.

**2. `claude/overnight/runner.sh:46-65`:** At overnight launch, if `ANTHROPIC_API_KEY` is not set, reads `apiKeyHelper` from `~/.claude/settings.json` and runs the script to populate the env var for SDK subagents. Falls back gracefully if absent:
```
echo "Warning: apiKeyHelper returned empty — overnight subagents will use subscription billing"
```
No failure — subagents just use subscription billing.

**3. `claude/overnight/smoke_test.py:167-188`:** Checks `settings.local.json` (per-project, not global `settings.json`) for `apiKeyHelper`. If present and set, prints OK. If empty string, prints OK (subscription mode). If absent, warns. This confirms the smoke test was designed assuming `apiKeyHelper` lives in `settings.local.json`, not global settings.

### Why global settings.json is the wrong place

- `apiKeyHelper` is machine-specific: each user has their own key, their own retrieval mechanism, their own path
- `claude/settings.json` is shared, symlinked from the repo — it goes to all users who fork/clone
- `smoke_test.py` checks `settings.local.json` (per-machine, not committed), signaling the intended home for this setting
- Subscription users never need `apiKeyHelper` at all
- The referenced file `~/.claude/get-api-key.sh` was never in the repo and no setup step creates it

### The broken doc reference

`docs/sdk.md:133`:
```
`apiKeyHelper` resolves `ANTHROPIC_API_KEY` for subagent spawning in the Python overnight pipeline. See `claude/get-api-key.sh`.
```
`claude/get-api-key.sh` doesn't exist — the reference is broken.

### Impact of removing apiKeyHelper from settings.json

- **Interactive users (subscription):** Error goes away. `/login` handles auth as before.
- **Interactive users (API key):** Need to set `ANTHROPIC_API_KEY` in their environment, or configure `apiKeyHelper` in their own `settings.local.json`.
- **Overnight pipeline (subscription):** No change — `runner.sh` falls back to subscription billing with a warning if `ANTHROPIC_API_KEY` is absent.
- **Overnight pipeline (API key):** `runner.sh` reads from `~/.claude/settings.json`, so removing it there means the runner won't find the helper. These users need `ANTHROPIC_API_KEY` set in their environment before launching overnight.

## Open Questions

None — the research resolves the open questions from Clarify:

- **What triggers the error?** Claude Code startup, not pipeline runtime. Any session launch with a missing `apiKeyHelper` script errors immediately.
- **Can `apiKeyHelper` be safely removed from settings.json?** Yes — `runner.sh` falls back gracefully; subscription users are unaffected; API key users need a documented alternative.
- **Better location for this setting?** `settings.local.json` (per-machine, not committed) — consistent with how `smoke_test.py` already checks for it.

## Fix Options

**Option A: Remove `apiKeyHelper` from `settings.json` + document alternatives**
- Delete the `apiKeyHelper` line from `claude/settings.json`
- Add a note in `docs/setup.md` under the Claude Code section explaining: subscription users need nothing; API key users should create `~/.claude/get-api-key.sh` themselves or set `ANTHROPIC_API_KEY` in their environment
- Fix the broken `docs/sdk.md` reference

**Option B: Documentation only (no settings.json change)**
- Add a note in `docs/setup.md` that `~/.claude/get-api-key.sh` must be created manually if using API key billing
- Fix `docs/sdk.md` broken reference
- Does not fix the error for subscription users who clone the repo as-is

Option A is strictly better: it fixes the error at root cause, requires no user action for the majority case (subscription), and documents the path for API key users.

## Affected Files

| File | Change |
|------|--------|
| `claude/settings.json` | Remove `apiKeyHelper` line |
| `docs/setup.md` | Add note: subscription users need nothing; API key users configure `apiKeyHelper` in `settings.local.json` or set env var |
| `docs/sdk.md` | Fix broken reference ("See `claude/get-api-key.sh`" → accurate explanation) |
