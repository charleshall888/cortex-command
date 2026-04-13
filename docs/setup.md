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

## Limited / Custom installation

`just setup` is the default and deploys the full agentic layer. Most customization happens via `/setup-merge` after `just setup` — it prompts individually for three optional hooks (`cortex-setup-gpg-sandbox-home.sh`, `cortex-notify.sh`, `cortex-notify-remote.sh`). The one thing `/setup-merge` does NOT surface is the UI skills bundle — if you're not building UIs, those six skills are safe to skip.

This section covers only the things that compose cleanly when omitted. Finer pruning isn't documented because the dependency graph between skills, hooks, bin utilities, and reference docs is too interconnected to hand-curate without reading the underlying sources.

### What's safely skippable

- **UI skills** (`ui-a11y`, `ui-brief`, `ui-check`, `ui-judge`, `ui-lint`, `ui-setup`) — self-contained frontend design enforcement stack (ESLint, Stylelint, Playwright, axe-core, Claude Vision). Skip unless you're building a UI. All six are a bundle — `/ui-check` orchestrates `/ui-lint` and `/ui-a11y`, so install all six or none.
- **Optional hooks** (prompted individually by `/setup-merge`):
  - `cortex-setup-gpg-sandbox-home.sh` — macOS-only sandbox commit signing. Skip on Linux/Windows or if you don't sign commits in sandboxed sessions.
  - `cortex-notify.sh` — `terminal-notifier` desktop notifications. macOS-only (requires `brew install terminal-notifier`). Skip if you don't want attention pings.
  - `cortex-notify-remote.sh` — Tailscale/Android remote notifications. Skip unless you have the `cortex-notify-remote` infrastructure deployed on a phone.

Everything else in `just setup` is assumed required. Partial installs beyond the four items above break silently at runtime because of skill→hook, skill→bin, and skill→reference-doc dependencies that are not worth documenting exhaustively at this project's size.

### Skipping the UI bundle

The simplest path is to run the full install, then remove the six UI skill symlinks:

```bash
just setup
rm ~/.claude/skills/ui-a11y ~/.claude/skills/ui-brief ~/.claude/skills/ui-check ~/.claude/skills/ui-judge ~/.claude/skills/ui-lint ~/.claude/skills/ui-setup
```

`rm` removes only the symlinks in `~/.claude/skills/`; the source files in the repo are untouched. To restore the UI skills later, re-run `just setup`.

For an agent-driven version that asks before touching the UI bundle:

> Run `just setup`. After it completes, ask me whether to keep the UI skills (`ui-a11y`, `ui-brief`, `ui-check`, `ui-judge`, `ui-lint`, `ui-setup`). If I say no, `rm` the six `~/.claude/skills/ui-*` symlinks.

### Skipping optional hooks

Run `/setup-merge` from Claude Code in the cortex-command directory. It iterates `OPTIONAL_HOOK_SCRIPTS` (the three hooks listed above) and prompts individually — answer `n` to each one you don't want. Re-run it any time to revisit the answers.

### Skipping the three optional hooks AND the UI bundle

Combine the two paths: run `just setup`, run `/setup-merge` (answering `n` to any optional hooks you don't want), then `rm` the six UI skill symlinks if applicable.

### Why no finer-grained presets?

An earlier version of this section documented a 4-preset dependency matrix (Minimal / Overnight / Daytime / Full) with per-component dependency columns. A critical review found the matrix drifted from the underlying code — phantom dependencies, missing dependencies, and presets that shipped skills whose own declared dependencies contradicted the preset. Keeping such a matrix accurate against evolving skills is a maintenance burden this project doesn't need at its current size. The UI skills bundle and the three optional hooks are the only components that compose cleanly when omitted, so they're all that's documented.

---

## What `just setup` Does

The setup recipe deploys the full agentic layer via symlinks:

| Recipe | What it deploys | Target |
|--------|----------------|--------|
| `deploy-bin` | CLI utilities (`jcc`, `count-tokens`, `audit-doc`, `overnight-start`, etc.) | `~/.local/bin/` |
| `deploy-reference` | Reference docs for conditional loading | `~/.claude/reference/` |
| `deploy-skills` | All skill directories | `~/.claude/skills/` |
| `deploy-hooks` | Hook scripts + notification handler | `~/.claude/hooks/`, `~/.claude/notify.sh` |
| `deploy-config` | Settings (copy), statusline, agent rules | `~/.claude/settings.json` (copy), `~/.claude/statusline.sh`, `~/.claude/rules/` |
| `python-setup` | Python venv + dependencies | `.venv/` |

If any target already exists and is not a symlink pointing into this repo, the recipe skips it and reports a conflict. Run `/setup-merge` in Claude Code to resolve conflicts interactively.

---

## Symlink Architecture

Config files are symlinked to their system locations. Editing the repo copy changes the active config immediately. This pattern keeps config version-controlled and auditable.

```
cortex-command/skills/commit/        →  ~/.claude/skills/commit/
cortex-command/hooks/cortex-*.sh     →  ~/.claude/hooks/cortex-*.sh
cortex-command/bin/jcc               →  ~/.local/bin/jcc
```

Exception: `settings.json` is copied (not symlinked) so `/setup-merge` can merge repo defaults into your personalized settings. Run `/setup-merge` after pulling repo changes to update.

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

The runner uses `apiKeyHelper` when present (work), and falls back to the OAuth token file when not (personal). See [docs/overnight-operations.md](overnight-operations.md#auth-resolution-apikeyhelper-and-env-var-fallback-order) for the full precedence chain.

---

## Customization

### settings.json

`claude/settings.json` is tracked in the repo and copied on first install to `~/.claude/settings.json`. Run `/setup-merge` to pull updated defaults. After forking, review and adjust:

- **Permissions**: The `allow`/`deny` lists reference specific tool names and path patterns. Update for your tools.
- **MCP plugins**: Add or remove plugins in `enabledPlugins`.
- **Sandbox**: `sandbox.enabled: true` is the default. Adjust `allowWrite` paths if your projects live outside the default locations.

Use `settings.local.json` in any project for per-machine overrides (e.g., `apiKeyHelper`).

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

1. Copy `~/.claude` to a shadow location: `cp -R ~/.claude ~/.claude-shadow`. Read the symlink warning below before running this.
2. Remove the host-shared symlinks from the shadow (see the next section for the exact commands).
3. Write `.envrc` in your repo root:

   ```
   export CLAUDE_CONFIG_DIR=$HOME/.claude-shadow
   ```

4. Run `direnv allow` once in the repo.
5. Quit and relaunch Claude Code from the repo. direnv reloads `.envrc` on each `cd`, but Claude Code only reads `CLAUDE_CONFIG_DIR` at launch.

If you don't use direnv, a shell alias (`alias cc-shadow='CLAUDE_CONFIG_DIR=$HOME/.claude-shadow claude'`) or a `./bin/claude` wrapper script work equivalently.

### Limitations and foot-guns

**The `cp -R` symlink trap (most severe).** On macOS, four files under `~/.claude/` are symlinks back into your cortex-command repo: `settings.json`, `statusline.sh`, `notify.sh`, and `CLAUDE.md`. `cp -R` preserves symlinks by default, so a naive shadow copy shares those four files with the host — mutating the shadow mutates the host. Immediately after `cp -R`, remove each symlink in the shadow before making any changes:

```
rm ~/.claude-shadow/settings.json
rm ~/.claude-shadow/statusline.sh
rm ~/.claude-shadow/notify.sh
rm ~/.claude-shadow/CLAUDE.md
```

Then write a fresh minimal `settings.json` in the shadow (or deliberately re-symlink them to wherever you want). Do not reach for the `-L` flag on `cp` as a shortcut — dereferencing all symlinks produces a frozen snapshot that won't pick up repo updates, which is the wrong default for a living cortex-command install.

**Cortex-command foot-guns.** Each of the following is a known failure mode this pattern surfaces. None of them are managed automatically — treat each as a rule to follow, not a problem the shadow resolves for you:

- **`/setup-merge` hardcodes `~/.claude`**: do not run `/setup-merge` from a shadowed shell — it silently writes to the host scope, bypassing the shadow. Run it from a non-shadowed shell, then re-copy the updated files into your shadow.
- **`just setup` hardcodes `~/.claude`**: same shape — run `just setup` from a non-shadowed shell, then refresh the shadow with `cp -R --update`.
- **Notify hook fires from the host literal path**: `claude/settings.json` references `~/.claude/notify.sh` literally in hook commands. Under a shadow, notifications fire from the host path (or fail silently if the host install is missing). Keep a working host install alongside any shadow.
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
