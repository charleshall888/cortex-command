[← Back to README](../README.md)

# Setup Guide

**For:** Users setting up cortex-command on a new machine.  **Assumes:** Claude Code is installed and working; basic git and terminal familiarity.

> **Machine-level config** (shell, terminal, git, starship, tmux, caffeinate) lives in the [machine-config](https://github.com/charleshall888/machine-config) repo. This guide covers only cortex-command — the agentic layer.

---

## Prerequisites

Before installing cortex-command, make sure you have:

- **[uv](https://docs.astral.sh/uv/)** — Python package manager. Install with `brew install uv`.
- **[Claude Code CLI](https://docs.claude.com/en/docs/claude-code/overview)** — the `claude` binary on your `PATH`.

---

## Install

Cortex-command ships as a Python CLI plus a set of Claude Code plugins. Installation is three steps: clone the repo, install the CLI, and enable the plugins from inside Claude.

### 1. Install the `cortex` CLI

```bash
curl -fsSL https://raw.githubusercontent.com/charleshall888/cortex-command/main/install.sh | sh
```

This puts the `cortex` binary on your `PATH`. It clones the repo to `$HOME/.cortex` (or wherever `install.sh` places it), and is the surface you use for per-repo setup (see step 3).

### 2. Add and install the plugins from inside Claude Code

Launch `claude`, then run:

```
/plugin marketplace add charleshall888/cortex-command
/plugin install cortex-interactive@cortex-command
```

`cortex-interactive` is the core plugin (skills, hooks, statusline). If you plan to run overnight sessions, also install the optional integration plugin:

```
/plugin install cortex-overnight-integration@cortex-command
```

Additional opt-in plugins (UI design stack, pr-review, etc.) live in [cortex-command-plugins](https://github.com/charleshall888/cortex-command-plugins). See that repo's README for the authoritative plugin list.

### 3. Per-repo setup

Run `cortex init` once in each repo where you want to use the overnight runner or interactive dashboard; this scaffolds `lifecycle/`, `backlog/`, `retros/`, `requirements/` templates and registers the repo's `lifecycle/sessions/` path in your sandbox allowWrite list.

```bash
cortex init
```

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

The runner uses `apiKeyHelper` when present (work), and falls back to the OAuth token file when not (personal). See [docs/overnight-operations.md](overnight-operations.md#auth-resolution-apikeyhelper-and-env-var-fallback-order) for the full precedence chain.

---

## Customization

### Recommended `~/.claude/settings.json` entries

Cortex-command no longer ships a `settings.json` into your user scope — you own that file. The maintainer's personal template (allow list, model, env vars, attribution, etc.) is opinionated and not a good default for others. The entries below are the load-bearing generic pieces cortex-command actually depends on; everything else (the `permissions.allow` list, `env`, `model`, `effortLevel`, `attribution`, `enableAllProjectMcpServers`, `alwaysThinkingEnabled`, `skipDangerousModePermissionPrompt`, `skipAutoPermissionPrompt`) is personal preference — compose your own.

**`sandbox.excludedCommands`**

```json
"sandbox": {
  "excludedCommands": ["gh:*", "git:*", "WebFetch", "WebSearch"]
}
```

Critical. `git` and `gh` need to run unsandboxed so GPG signing works and so commit hooks can spawn child processes (e.g., `gpg-agent`) without hitting sandbox denials. Changing this list breaks the sandbox-excluded command contract that cortex-command's git integration relies on.

**`sandbox.autoAllowBashIfSandboxed`**

```json
"sandbox": {
  "autoAllowBashIfSandboxed": true
}
```

Required for the overnight runner. Without it, every sandboxed Bash call requires interactive approval, which defeats unattended execution.

**`sandbox.network.allowedDomains`**

```json
"sandbox": {
  "network": {
    "allowedDomains": [
      "api.github.com",
      "raw.githubusercontent.com",
      "registry.npmjs.org",
      "*.anthropic.com"
    ]
  }
}
```

The minimum set cortex-command needs: GitHub API for `gh` operations, raw.githubusercontent.com for the install bootstrap, npm registry for plugin installs, and Anthropic endpoints for the SDK. Add more domains as your own workflows require.

**`sandbox.filesystem.allowWrite`**

You do not need to hand-edit this. Run `cortex init` (ticket 119) in each repo where you want cortex-command active — it appends the per-repo overnight-session write paths automatically. Hand-editing is error-prone because the paths are repo-scoped and resolve relative to each project.

**`statusLine.command`** (optional)

```json
"statusLine": {
  "command": "$HOME/.cortex/claude/statusline.sh"
}
```

Point to the `statusline.sh` inside your cortex-command clone (adjust the absolute path if you cloned somewhere other than `$HOME/.cortex`). This is optional — it shows cortex-specific session state in the Claude Code statusline. Skip it if you don't want that coupling.

**`permissions.deny`**

A conservative deny list is a useful safety baseline: `sudo`, destructive `rm -rf` patterns, `git push --force` against protected branches, reads of secrets directories (`~/.ssh`, `~/.aws`, etc.). Cortex-command does not prescribe a specific list — compose your own. For a starting template, see the pre-117 version of `claude/settings.json` in this repo's git history (it contains roughly 80 curated entries). Do not paste that list blindly; review each rule against your own threat model.

For the exact historical template including the maintainer's personal allow list, see `git show HEAD:claude/settings.json` on the pre-117 commit.

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

## Per-repo permission scoping

Claude Code's settings merge is strictly additive: `permissions.allow` arrays concatenate across all scopes, `permissions.deny` is monotonic, and there is no subtraction mechanism. If you want a repo to ignore your global allow list, layering alone cannot deliver it. The supported workaround is `CLAUDE_CONFIG_DIR`, an alternate user-scope directory Claude Code reads at launch — by launching from a repo with `CLAUDE_CONFIG_DIR` set to a shadow copy of `~/.claude`, that repo gets its own user scope. Watch upstream issues [#12962](https://github.com/anthropics/claude-code/issues/12962) and [#26489](https://github.com/anthropics/claude-code/issues/26489) for a first-class per-project permissions feature; until one of those lands, this is the recommended workaround.

### How it works

`CLAUDE_CONFIG_DIR` points Claude Code at an alternate user-scope directory instead of `~/.claude`. The value is read at launch time, so a relaunch is required to pick up a new value — direnv loading on `cd` does not affect an already-running session.

### Setup with direnv

1. Copy `~/.claude` to a shadow location: `cp -R ~/.claude ~/.claude-shadow`.
2. Write `.envrc` in your repo root:

   ```
   export CLAUDE_CONFIG_DIR=$HOME/.claude-shadow
   ```

3. Run `direnv allow` once in the repo.
4. Quit and relaunch Claude Code from the repo. direnv reloads `.envrc` on each `cd`, but Claude Code only reads `CLAUDE_CONFIG_DIR` at launch.

If you don't use direnv, a shell alias (`alias cc-shadow='CLAUDE_CONFIG_DIR=$HOME/.claude-shadow claude'`) or a `./bin/claude` wrapper script work equivalently.

### Limitations and foot-guns

**Cortex-command foot-guns.** Each of the following is a known failure mode this pattern surfaces. None of them are managed automatically — treat each as a rule to follow, not a problem the shadow resolves for you:

- **Evolve, auto-memory, audit-doc, and count-tokens walk from host**: these tools fall back to `~/.claude` rather than `$CLAUDE_CONFIG_DIR`. Auto-memory under a shadow writes to the host scope. Treat their output as host-scoped.
- **Concurrent sessions and scope confusion**: Claude Code's `/context` (an upstream bug) shows the host path even when a shadow is active, so you cannot verify the live scope from inside a session. Run `echo $CLAUDE_CONFIG_DIR` in your shell before launching each session.

**Upstream Claude Code partial-support bugs.** Even with `CLAUDE_CONFIG_DIR` set, several Claude Code subsystems do not fully honor it:

- [#36172](https://github.com/anthropics/claude-code/issues/36172) — skills in `$CLAUDE_CONFIG_DIR/skills/` are not reliably resolved. Most consequential for cortex-command because it undermines the "swap the entire user scope" mental model.
- [#38641](https://github.com/anthropics/claude-code/issues/38641) — `/context` displays the host path regardless of `CLAUDE_CONFIG_DIR`.
- [#42217](https://github.com/anthropics/claude-code/issues/42217) — MCP servers from `.mcp.json` are not loaded under a shadow.
- [#34800](https://github.com/anthropics/claude-code/issues/34800) — IDE lock files always write to `~/.claude/ide/` regardless of the env var.

For the full decision record and failure-mode inventory, see `research/user-configurable-setup/research.md`.

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
