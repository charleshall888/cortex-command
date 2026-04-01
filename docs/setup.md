[← Back to README](../README.md)

# Machine Setup Guide

**For:** Users setting up this repo on a new machine (macOS, Windows, or Linux).  **Assumes:** Basic git and terminal familiarity; a working Claude Code installation.

Detailed setup instructions for all components in this repo, with rationale for each tool choice and callouts for sections that require per-machine customization.

---

## Symlink Architecture

Every piece of config in this repo is deployed via symlinks: the file lives in the repo and a symlink at the system location points back to it. Editing the repo copy changes the active config immediately. This pattern makes config version-controlled, portable, and easy to audit — there is never a question of which copy is current.

The general pattern for every setup section below is:

```bash
ln -sf "$(pwd)/repo-file" ~/system-location
```

On Windows, the equivalent uses `New-Item -ItemType SymbolicLink`. When the `docs/` directory does not exist or a parent directory is missing, create it with `mkdir -p` (macOS/Linux) or `New-Item -ItemType Directory -Force` (Windows) before creating the symlink.

---

## Shell

### macOS/Linux (Zsh)

Zsh is the default shell on macOS (since Catalina) and is widely available on Linux. This config provides a consistent environment across both platforms: aliases, PATH setup, tool initialization (nvm, deno, Android SDK), and prompt integration with Starship.

```bash
ln -sf "$(pwd)/shell/zshrc" ~/.zshrc
ln -sf "$(pwd)/shell/zprofile" ~/.zprofile
source ~/.zshrc
```

> **Customize**: `shell/zshrc` contains a tool-loading section for nvm, deno, and the Android SDK. Keep only the tools you have installed and remove the rest — loading tools that are not present produces shell startup errors.

### Windows (PowerShell)

The PowerShell profile provides Windows-equivalent shell configuration. It mirrors the macOS setup where possible so the environment feels consistent across machines.

```powershell
New-Item -ItemType Directory -Path (Split-Path $PROFILE) -Force
New-Item -ItemType SymbolicLink -Path $PROFILE -Target (Resolve-Path shell\Microsoft.PowerShell_profile.ps1)
. $PROFILE
```

---

## Starship Prompt

Starship is a cross-platform, minimal prompt written in Rust. It renders consistently across Zsh, Bash, Fish, and PowerShell, so the same prompt config works on macOS and Windows without translation. It is fast enough to not add perceptible shell startup latency.

### Install

```bash
# macOS
brew install starship

# Windows
winget install Starship.Starship
```

### Config (optional)

```bash
# macOS/Linux
mkdir -p ~/.config && ln -sf "$(pwd)/starship/starship.toml" ~/.config/starship.toml

# Windows
New-Item -ItemType SymbolicLink -Path $env:USERPROFILE\.config\starship.toml -Target (Resolve-Path starship\starship.toml)
```

The current config uses defaults and serves as a template. Starship works out of the box without linking this file.

---

## Git

### Global Gitignore

A global gitignore prevents editor artifacts, OS metadata, and tool-specific files from appearing as untracked files in every repository on the machine. This is preferable to adding them to each project's `.gitignore` individually.

```bash
mkdir -p ~/.config/git
ln -sf "$(pwd)/git/ignore" ~/.config/git/ignore
```

---

## Ghostty Terminal (macOS)

Ghostty is a native macOS terminal with first-class notification support and GPU-accelerated rendering. The config here sets FiraCode Nerd Font (required for Starship glyphs and skill UI symbols) and enables bell notifications — title icon, dock bounce, and border flash — so missed agent output is visually surfaced when working across windows.

```bash
mkdir -p ~/Library/Application\ Support/com.mitchellh.ghostty
ln -sf "$(pwd)/ghostty/config" ~/Library/Application\ Support/com.mitchellh.ghostty/config
```

Features enabled by this config:
- FiraCode Nerd Font
- Bell notifications (title icon, dock bounce, border flash)

### Windows Terminal Equivalent

Ghostty is macOS only. On Windows, configure FiraCode Nerd Font in Windows Terminal's `settings.json`:

```json
{
  "profiles": {
    "defaults": {
      "font": {
        "face": "FiraCode Nerd Font"
      }
    }
  }
}
```

---

## macOS Sleep Prevention (macOS only)

Long-running Claude Code sessions and overnight pipeline runs are interrupted when the Mac auto-sleeps or locks the screen. This polling daemon watches for active tmux sessions or Claude processes and keeps the machine awake for the duration using `caffeinate -d -i`. It runs as a launchd service and starts automatically at login — no manual intervention needed between sessions.

```bash
chmod +x "$(pwd)/mac/caffeinate-monitor.sh"
mkdir -p ~/.local/bin
ln -sf "$(pwd)/mac/caffeinate-monitor.sh" ~/.local/bin/caffeinate-monitor.sh
mkdir -p ~/Library/LaunchAgents
ln -sf "$(pwd)/mac/local.caffeinate-monitor.plist" ~/Library/LaunchAgents/local.caffeinate-monitor.plist
launchctl load ~/Library/LaunchAgents/local.caffeinate-monitor.plist
```

### Cleanup (existing installs)

If you previously used the old tmux caffeinate-check.sh approach, remove the dangling symlink and reload tmux config:

```bash
rm -f ~/.config/tmux/caffeinate-check.sh
tmux source ~/.tmux.conf
```

---

## Claude Code

Claude Code is the primary AI coding agent used in this setup. The configuration here provides global agent instructions, permission rules, hooks for commit validation and lifecycle state injection, a statusline integration, and symlinked skills so they are available in every project directory without per-project setup.

### Customize for Your Machine

After forking, update these files before linking anything to `~/`:

| File | What to change |
|------|----------------|
| `shell/zshrc` | Update the tool-loading section — keep only the tools you actually have (nvm, deno, Android SDK, etc.) and remove the rest |
| `claude/settings.json` | Update MCP plugin permissions (`allow`/`deny` patterns) for your own tools; add your patterns and remove ones for tools you don't use |
| `remote/SETUP.md` | Replace the hostname examples with your own Tailscale hostname |

> **Customize**: `claude/settings.json` contains MCP plugin `allow`/`deny` permission patterns. These are personal — they reference specific tool names and path patterns. Review and update them for the tools you use; remove entries for tools you don't have installed.

### Full Setup (macOS)

```bash
# Global agent instructions
ln -sf "$(pwd)/claude/Agents.md" ~/.claude/CLAUDE.md

# Settings (includes hooks, model preferences, permissions)
ln -sf "$(pwd)/claude/settings.json" ~/.claude/settings.json

# Statusline
ln -sf "$(pwd)/claude/statusline.sh" ~/.claude/statusline.sh

# Shared hooks
mkdir -p ~/.claude/hooks
ln -sf "$(pwd)/hooks/validate-commit.sh" ~/.claude/hooks/validate-commit.sh
ln -sf "$(pwd)/hooks/scan-lifecycle.sh" ~/.claude/hooks/scan-lifecycle.sh
ln -sf "$(pwd)/hooks/notify.sh" ~/.claude/notify.sh
brew install terminal-notifier

# Claude-only hooks
ln -sf "$(pwd)/claude/hooks/sync-permissions.py" ~/.claude/hooks/sync-permissions.py

# Skills (all — symlink every skill directory)
mkdir -p ~/.claude/skills
for s in skills/*/; do ln -sf "$(pwd)/$s" ~/.claude/skills/$(basename "$s"); done
```

### Windows Setup

```powershell
# Statusline
New-Item -ItemType SymbolicLink -Path $env:USERPROFILE\.claude\statusline.ps1 -Target (Resolve-Path claude\statusline.ps1)
```

Add to `%USERPROFILE%\.claude\settings.json`:

```json
{
  "statusLine": {
    "type": "command",
    "command": "powershell.exe -ExecutionPolicy Bypass -File %USERPROFILE%\\.claude\\statusline.ps1",
    "padding": 0
  }
}
```

### macOS Permissions

For notifications to work, enable in **System Settings > Notifications**:

1. **terminal-notifier**: Allow notifications
2. **Ghostty**: Allow notifications + enable "Badge app icon"

---

## Gemini CLI

Gemini CLI is an alternative AI coding agent from Google. This setup shares the same `Agents.md` project instruction file used by Claude Code — one source of truth, no format translation, the same conventions apply in both agents.

```bash
mkdir -p ~/.gemini
ln -sf "$(pwd)/claude/Agents.md" ~/.gemini/GEMINI.md
```

---

## Cursor

Cursor is an AI-first code editor that supports the same skill and hook system used by Claude Code. The shared skills and hooks in this repo work in Cursor without modification — same `SKILL.md` format, same hook scripts, same commit validation.

### Setup (This Repo)

This repo includes `.cursor/skills/` and `.cursor/hooks.json` as committed symlinks. No additional setup needed — Cursor reads them automatically.

### Setup (Other Projects)

To use the shared skills and hooks in other projects:

```bash
# Skills (symlink the subset of cross-agent skills from this repo)
mkdir -p .cursor/skills
for skill in commit dev interview lifecycle morning-review pr requirements pr-review skill-creator ui-brief ui-judge; do
  ln -sf "/path/to/cortex-command/skills/$skill" ".cursor/skills/$skill"
done

# Hooks
ln -sf /path/to/cortex-command/cursor/hooks.json .cursor/hooks.json
```

### Features

**Shared Skills** (via `.cursor/skills/`):
- `commit` — Create well-formatted git commits
- `dev` — Routing hub for development requests
- `interview` — Interview user about plans to surface gaps
- `lifecycle` — Structured feature development lifecycle
- `morning-review` — Walk through the morning report after an overnight session
- `pr` — Create GitHub pull requests with template support
- `requirements` — Gather project/area-level requirements
- `pr-review` — Multi-agent PR review pipeline
- `skill-creator` — Guide for creating new skills
- `ui-brief` — Generate DESIGN.md + theme tokens
- `ui-judge` — Visual quality scorecard via Claude Vision

**Shared Hooks** (via `.cursor/hooks.json`):
- Commit message validation (beforeShellExecution)
- Lifecycle state context injection (sessionStart)
- Desktop notifications on task completion (stop)

---

## Shared Features

### Commit Validation Hook

Both Claude Code and Cursor use `hooks/validate-commit.sh` to validate commit messages before execution. The hook detects which agent is calling it from the input JSON shape and adapts its output format accordingly. Enforces:
- Imperative mood, capitalized subject
- No trailing period, max 72 characters
- Blank line before body

### Lifecycle State Awareness

Both agents use `hooks/scan-lifecycle.sh` to detect active lifecycle features and inject state into the conversation context at session start. This gives the agent awareness of in-progress features without manual prompting.

### Desktop Notifications (macOS)

`hooks/notify.sh` sends macOS notifications via terminal-notifier when agents complete tasks or need attention. Works with both Claude Code's Stop/Notification hooks and Cursor's stop hook.

> **Note**: Notifications only appear when Ghostty is not the focused app.

### Skills

All skills in `skills/` use unified frontmatter and agent-neutral markdown bodies. See `skills/` for the authoritative current list.

| Skill | Purpose | Agent Support |
|-------|---------|---------------|
| `commit` | Git commit workflow | All agents |
| `pr` | GitHub pull request workflow | All agents |
| `interview` | Plan interview to surface gaps | All agents |
| `lifecycle` | Structured feature development | All agents |
| `skill-creator` | Guide for creating new skills | All agents |
| `serena-memory` | Serena memory creation | Claude Code only |

---

## WezTerm Integration (Windows)

WezTerm is a cross-platform GPU-accelerated terminal with a Lua configuration API. This integration provides visual notifications when Claude Code needs attention on Windows — a tab color change and screen flash that mirrors the Ghostty bell behavior on macOS. It fills the gap left by terminal-notifier, which is macOS only.

| File | Description |
|------|-------------|
| `wezterm/claude-notify.lua` | Tab highlighting for unseen output |
| `claude/hooks/bell.ps1` | Visual bell trigger script |

### Setup (Windows)

1. Copy the notification module:
```powershell
mkdir $env:USERPROFILE\.wezterm -Force
Copy-Item wezterm\claude-notify.lua $env:USERPROFILE\.wezterm\
```

2. Copy the bell hook:
```powershell
mkdir $env:USERPROFILE\.claude\hooks -Force
Copy-Item claude\hooks\bell.ps1 $env:USERPROFILE\.claude\hooks\
```

3. Update `.wezterm.lua` (add near top):
```lua
local claude_notify = require('claude-notify')
claude_notify.setup()
```

4. Restart WezTerm to load changes.

### Behavior

- **Visual Bell**: Screen flashes orange when Claude needs input
- **Tab Indicator**: Tab turns orange until focused (auto-clears)
- **Toast Notification**: Windows toast continues working alongside

---

## Remote Access (macOS + Android)

> **Customize**: `remote/SETUP.md` contains hostname examples using a specific Tailscale machine name. Replace these with your own Tailscale hostname before following the steps.

The remote setup uses Tailscale (mesh VPN) + tmux (session persistence) + mosh (resilient mobile shell) + ntfy (push notifications) to control Claude Code sessions on a Mac from an Android phone. Full step-by-step instructions are in [`remote/SETUP.md`](../remote/SETUP.md).

---

## OS Compatibility

| Component | macOS | Linux | Windows | Notes |
|-----------|:-----:|:-----:|:-------:|-------|
| Skills (`skills/`) | ✅ | ✅ | ✅ | Agent-agnostic, cross-platform |
| `hooks/validate-commit.sh` | ✅ | ✅ | ✅ | Core hook, cross-platform |
| `hooks/scan-lifecycle.sh` | ✅ | ✅ | ✅ | Core hook, cross-platform |
| `claude/statusline.sh` | ✅ | ✅ | — | Shell statusline |
| `claude/statusline.ps1` | — | — | ✅ | PowerShell statusline (Windows) |
| Git config (`git/ignore`) | ✅ | ✅ | ✅ | Cross-platform gitignore |
| Starship prompt | ✅ | ✅ | ✅ | Cross-platform prompt |
| `hooks/notify.sh` | ✅ | — | — | macOS only; requires `terminal-notifier` |
| `mac/` directory | ✅ | — | — | macOS only (launchd, caffeinate) |
| Ghostty config (`ghostty/`) | ✅ | — | — | macOS only terminal |
| WezTerm integration | — | — | ✅ | Windows alternative for visual notifications |
| PowerShell profile | — | — | ✅ | Windows shell config |

---

## Dependencies

| Tool | macOS | Windows |
|------|-------|---------|
| just | `brew install just` | `winget install Casey.Just` |
| Python 3 | Pre-installed / `brew install python` | `winget install Python.Python.3` |
| gh (GitHub CLI) | `brew install gh` | `winget install GitHub.cli` |
| tmux | `brew install tmux` | N/A |
| Starship | `brew install starship` | `winget install Starship.Starship` |
| FiraCode Nerd Font | [nerdfonts.com](https://www.nerdfonts.com/font-downloads) | Same |
| jq (optional) | `brew install jq` | `choco install jq` |
| NVM | `brew install nvm` | [nvm-windows](https://github.com/coreybutler/nvm-windows) |
| Deno | `brew install deno` | `irm https://deno.land/install.ps1 \| iex` |
| terminal-notifier | `brew install terminal-notifier` | N/A |
