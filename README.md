# Cortex Command

An opinionated AI workflow framework for [Claude Code](https://docs.anthropic.com/en/docs/claude-code). Skills, hooks, an autonomous overnight runner, a web dashboard, a lifecycle state machine, and backlog management -- all deployed via symlinks.

## Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI
- [just](https://just.systems/) command runner (`brew install just`)
- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager (`brew install uv`)

## Quick Start

```bash
git clone https://github.com/charlie-hall/cortex-command.git ~/cortex-command
cd ~/cortex-command
just setup
```

> **Important:** Add the following to your shell profile (`.zshrc`, `.bashrc`, etc.):
>
> ```bash
> export CORTEX_COMMAND_ROOT="$HOME/cortex-command"
> ```
>
> Several components (the `jcc` wrapper, overnight runner) require this variable.
> If you clone to a different location, update the path accordingly and also edit
> `claude/settings.json` to update the `allowWrite` path under `sandbox.filesystem`.

### Backup Warning

`just setup` creates symlinks that **replace** existing files in `~/.claude/`. If you already have Claude Code configured, back up these files first:

- `~/.claude/settings.json`
- `~/.claude/CLAUDE.md`
- `~/.claude/statusline.sh`
- Any custom skills in `~/.claude/skills/`
- Any custom hooks in `~/.claude/hooks/`

The setup recipe will warn before overwriting non-symlink files at these locations.

## What's Inside

| Component | Description |
|-----------|-------------|
| `skills/` | Slash commands -- `/commit`, `/pr`, `/lifecycle`, `/overnight`, `/discovery`, and more |
| `hooks/` | Event handlers -- commit validation, lifecycle state injection, desktop notifications |
| `claude/overnight/` | Autonomous overnight runner -- plans work, executes in parallel, writes a morning report |
| `claude/dashboard/` | FastAPI web dashboard for monitoring overnight sessions |
| `lifecycle/` | Feature state machine -- research, specify, plan, implement, review, complete |
| `backlog/` | YAML-frontmatter backlog items with overnight readiness gates |
| `claude/reference/` | Reference docs loaded conditionally by agent instructions |
| `bin/` | CLI utilities deployed to `~/.local/bin/` |

## Customization

`claude/settings.json` ships with the author's preferences:

- `model: opus[1m]` -- model selection
- `cleanupPeriodDays: 365` -- session retention
- `alwaysThinkingEnabled: true` -- extended thinking
- Experimental environment variables for agent teams

Review and adjust these for your own setup. Use `settings.local.json` in any project for per-machine overrides without modifying the tracked file.

## OS Compatibility

| Component | macOS | Linux | Windows |
|-----------|:-----:|:-----:|:-------:|
| Skills | Yes | Yes | Yes |
| Hooks (commit, lifecycle) | Yes | Yes | Yes |
| Overnight runner | Yes | Yes | -- |
| Dashboard | Yes | Yes | -- |
| Notifications (`notify.sh`) | Yes | -- | -- |
| Statusline (shell) | Yes | Yes | -- |
| Statusline (PowerShell) | -- | -- | Yes |

## Commands

Run `just` to see all recipes. Key commands:

```
just setup                 # Full install (symlinks + Python deps)
just check-symlinks        # Verify all symlinks are intact
just test                  # Run all test suites
just overnight-run         # Run overnight in foreground
just overnight-start       # Run overnight in detached tmux
just overnight-status      # Live status display
just dashboard             # Start the web dashboard
just validate-commit       # Test commit message hook
just validate-skills       # Check skill frontmatter
```

## License

[MIT](LICENSE)
