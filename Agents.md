# Cortex Command Project Instructions

## What This Repo Is

An opinionated AI workflow framework for Claude Code. Provides skills (slash commands), hooks (event handlers), an autonomous overnight runner, a web dashboard, a lifecycle state machine, and backlog management. All config is deployed via symlinks from this repo to their system locations.

## Repository Structure

- `skills/` - Skills (commit, pr, lifecycle, etc.)
- `hooks/` - Hooks (commit validation, lifecycle scanning, notifications)
- `claude/` - Claude Code config (settings, statusline, hooks)
- `backlog/` - Project backlog items (YAML frontmatter markdown files)
- `requirements/` - Project and area-level requirements (vision, priorities, scope)
- `lifecycle/` - Feature lifecycle tracking (research, spec, plan, implementation)
- `docs/` - Documentation (setup guide, agentic layer, overnight, skills reference)
- `tests/` - Automated test suite for skills, hooks, and overnight runner
- `retros/` - Session retrospectives (dated problem-only logs)
- `bin/` - Global CLI utilities (deployed to `~/.local/bin/`)

## Symlink Architecture

Files in this repo are symlinked to system locations — always edit the repo copy (the symlink target), never create files at the destination.

Key symlinks:
- `skills/*` -> `~/.claude/skills/*`
- `hooks/*` -> `~/.claude/hooks/*`
- `hooks/notify.sh` -> `~/.claude/notify.sh` (direct — settings.json references this path)
- `claude/settings.json` -> `~/.claude/settings.json`
- `claude/Agents.md` -> `~/.claude/CLAUDE.md` (global cross-project instructions)
- `claude/reference/*` -> `~/.claude/reference/*`
- `claude/statusline.sh` -> `~/.claude/statusline.sh`

## Commands

Run `just` to see all available recipes. Key commands:

- Full setup: `just setup`
- Generate backlog index: `just backlog-index`
- Validate commit hook: `just validate-commit`
- Check symlinks: `just check-symlinks`
- Run tests: `just test`

## Dependencies

- [just](https://github.com/casey/just) -- command runner (`brew install just`)
- Python 3 -- required for hooks, backlog tooling, and overnight runner
- [uv](https://docs.astral.sh/uv/) -- Python package manager (`brew install uv`)

## Conventions

- Always commit using the `/commit` skill -- never run `git commit` manually
- Commit messages: imperative mood, capitalized, no trailing period, max 72 chars subject
- A shared hook validates commit messages automatically
- New skills go in `skills/` with `name` and `description` frontmatter
- Agent-specific config goes in `claude/`
- Settings JSON must remain valid JSON
- Hook/notification scripts must be executable (`chmod +x`)
- New global utilities follow the deploy-bin pattern: logic goes in `bin/`, deployed to `~/.local/bin/` via `just deploy-bin`, skills invoke the binary by name (not a relative path). Run `just setup` to deploy all global agentic layer components at once.
- Use `jcc <recipe>` (deployed to `~/.local/bin/jcc`) to invoke cortex-command recipes from any directory. The wrapper runs recipes in this repo's directory context, so it's suitable for repo-specific operations (`jcc deploy-bin`, `jcc validate-commit`), not for operations that should act on another repo's files (use `update-item`, `generate-backlog-index`, etc. for those).
