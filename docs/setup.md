[← Back to README](../README.md)

# Setup Guide

**For:** Users setting up cortex-command on a new machine.  **Assumes:** Claude Code is installed and working; basic git and terminal familiarity.

> **Machine-level config** (shell, terminal, git, starship, tmux, caffeinate) lives in the [machine-config](https://github.com/charleshall888/machine-config) repo. This guide covers only cortex-command — the agentic layer.

---

## Before You Start

`just setup` creates symlinks that **replace** existing files in `~/.claude/`. If you already have Claude Code configured, back up these files first:

```bash
# Back up existing Claude Code config
cp -r ~/.claude/settings.json ~/.claude/settings.json.backup 2>/dev/null
cp -r ~/.claude/settings.local.json ~/.claude/settings.local.json.backup 2>/dev/null
cp -r ~/.claude/statusline.sh ~/.claude/statusline.sh.backup 2>/dev/null
cp -r ~/.claude/skills ~/.claude/skills.backup 2>/dev/null
cp -r ~/.claude/hooks ~/.claude/hooks.backup 2>/dev/null
```

`just setup` does **not** create or modify `~/.claude/CLAUDE.md` — it deploys rules to `~/.claude/rules/` only. Your existing `CLAUDE.md` is safe.

---

## Quick Setup

```bash
git clone https://github.com/charleshall888/cortex-command.git ~/cortex-command
cd ~/cortex-command
just setup
```

Then add to your shell profile (`.zshrc`, `.bashrc`, etc.):

```bash
export CORTEX_COMMAND_ROOT="$HOME/cortex-command"
```

Restart your shell and run `just check-symlinks` to verify.

---

## What `just setup` Does

The setup recipe deploys the full agentic layer via symlinks:

| Recipe | What it deploys | Target |
|--------|----------------|--------|
| `deploy-bin` | CLI utilities (`jcc`, `count-tokens`, `audit-doc`, `overnight-start`, etc.) | `~/.local/bin/` |
| `deploy-reference` | Reference docs for conditional loading | `~/.claude/reference/` |
| `deploy-skills` | All skill directories | `~/.claude/skills/` |
| `deploy-hooks` | Hook scripts + notification handler | `~/.claude/hooks/`, `~/.claude/notify.sh` |
| `deploy-config` | Settings, statusline, agent rules | `~/.claude/settings.json`, `~/.claude/statusline.sh`, `~/.claude/rules/` |
| `python-setup` | Python venv + dependencies | `.venv/` |

If any target already exists and is not a symlink pointing into this repo, the recipe skips it and reports a conflict. Run `/setup-merge` in Claude Code to resolve conflicts interactively.

---

## Symlink Architecture

Every config file lives in this repo and is symlinked to its system location. Editing the repo copy changes the active config immediately. This pattern keeps config version-controlled and auditable.

```
cortex-command/claude/settings.json  →  ~/.claude/settings.json
cortex-command/skills/commit/        →  ~/.claude/skills/commit/
cortex-command/hooks/cortex-*.sh     →  ~/.claude/hooks/cortex-*.sh
cortex-command/bin/jcc               →  ~/.local/bin/jcc
```

Always edit the repo copy (the symlink target), never create files at the destination.

---

## Authentication

The overnight runner and some CLI utilities need API credentials. There are two modes depending on your account type.

### Option A: API Key (Console / Organization billing)

For work repos billed through the Anthropic Console:

1. Create an API key at [platform.claude.com](https://platform.claude.com)
2. Store it securely:
   ```bash
   printf '%s' 'sk-ant-api03-...' > ~/.claude/work-api-key
   chmod 600 ~/.claude/work-api-key
   ```
3. Add `apiKeyHelper` to `~/.claude/settings.local.json`:
   ```json
   {
     "apiKeyHelper": "cat ~/.claude/work-api-key"
   }
   ```

This path also enables `count-tokens` and `audit-doc`, which call the Anthropic API directly.

### Option B: OAuth Token (Claude Pro / Max subscription)

For personal repos using your Claude subscription:

1. Generate a long-lived token (valid 1 year):
   ```bash
   claude setup-token
   ```
   This opens a browser for OAuth authentication and prints the token.

2. Store the token:
   ```bash
   printf '%s' 'sk-ant-oat01-...' > ~/.claude/personal-oauth-token
   chmod 600 ~/.claude/personal-oauth-token
   ```

The overnight runner reads this file automatically when no `apiKeyHelper` is configured. No settings.json changes needed.

> **Note:** `CLAUDE_CODE_OAUTH_TOKEN` is recognized by Claude Code CLI (`claude -p`, Agent SDK) but **not** by the Anthropic Python SDK. Standalone utilities like `count-tokens` and `audit-doc` require an API key (Option A).

### Using Both

If you work on both personal and work repos, configure both:
- Set `apiKeyHelper` in the work repo's `.claude/settings.local.json`
- Store the OAuth token at `~/.claude/personal-oauth-token`

The runner uses `apiKeyHelper` when present (work), and falls back to the OAuth token file when not (personal). See [docs/overnight.md](overnight.md#authentication) for the full precedence chain.

---

## Customization

### settings.json

`claude/settings.json` is tracked and symlinked to `~/.claude/settings.json`. After forking, review and adjust:

- **Permissions**: The `allow`/`deny` lists reference specific tool names and path patterns. Update for your tools.
- **MCP plugins**: Add or remove plugins in `enabledPlugins`.
- **Sandbox**: `sandbox.enabled: true` is the default. Adjust `allowWrite` paths if your projects live outside the default locations.

Use `settings.local.json` in any project for per-machine overrides (e.g., `apiKeyHelper`) without modifying the tracked file.

### Adding an MCP Server

Add a `mcpServers` block to `claude/settings.json`:

```json
{
  "mcpServers": {
    "server-name": {
      "command": "npx",
      "args": ["-y", "@scope/server-package"]
    }
  }
}
```

Then add `"mcp__server-name__*"` to the `permissions.allow` list.

---

## macOS Notifications

For desktop notifications when Claude Code needs attention:

1. Install terminal-notifier: `brew install terminal-notifier`
2. Enable in **System Settings > Notifications**:
   - **terminal-notifier**: Allow notifications
   - **Your terminal app**: Allow notifications + enable "Badge app icon"

---

## Dependencies

| Tool | Install |
|------|---------|
| [just](https://just.systems/) | `brew install just` |
| Python 3.12+ | Pre-installed / `brew install python` |
| [uv](https://docs.astral.sh/uv/) | `brew install uv` |
| [gh](https://cli.github.com/) (GitHub CLI) | `brew install gh` |
| tmux | `brew install tmux` |
| terminal-notifier (macOS) | `brew install terminal-notifier` |
| jq (optional) | `brew install jq` |
