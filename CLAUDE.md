# Cortex Command Project Instructions

## What This Repo Is

An opinionated AI workflow framework for Claude Code. Provides skills (slash commands), hooks (event handlers), an autonomous overnight runner, a web dashboard, a lifecycle state machine, and backlog management. Ships as a CLI (`uv tool install git+https://github.com/charleshall888/cortex-command.git@v0.1.0`) plus plugins installed via `/plugin install` in Claude Code; `cortex init` additionally writes one entry per repo into `~/.claude/settings.local.json`'s `sandbox.filesystem.allowWrite` array to unblock interactive session writes to `lifecycle/sessions/`.

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
- `bin/` - Global CLI utilities; canonical source mirrored into the `cortex-interactive` plugin's `bin/` via dual-source enforcement

## Distribution

Cortex-command ships as a CLI installed via `uv tool install git+https://github.com/charleshall888/cortex-command.git@v0.1.0` plus plugins installed via `/plugin install`. It no longer deploys symlinks into `~/.claude/`.

## Commands

Run `just` to see all available recipes. Key commands:

- Generate backlog index: `just backlog-index`
- Validate commit hook: `just validate-commit`
- Run tests: `just test`

## Dependencies

- [just](https://github.com/casey/just) -- command runner (`brew install just`)
- Python 3 -- required for hooks, backlog tooling, and overnight runner
- [uv](https://docs.astral.sh/uv/) -- Python package manager (`brew install uv`)

## Conventions

- Always commit using the `/cortex-interactive:commit` skill -- never run `git commit` manually
- Commit messages: imperative mood, capitalized, no trailing period, max 72 chars subject
- A shared hook validates commit messages automatically
- New skills go in `skills/` with `name` and `description` frontmatter
- Agent-specific config goes in `claude/`
- Settings JSON must remain valid JSON
- Hook/notification scripts must be executable (`chmod +x`)
- New global utilities ship via the `cortex-interactive` plugin's `bin/` directory; see `just --list` for available recipes.
- Run `just setup-githooks` after clone to enable the dual-source drift pre-commit hook.
- Use `cortex-jcc <recipe>` to invoke cortex-command recipes from any directory. The wrapper (shipped in `plugins/cortex-interactive/bin/`) runs recipes in this repo's directory context, so it's suitable for repo-specific operations (`cortex-jcc backlog-index`, `cortex-jcc validate-commit`), not for operations that should act on another repo's files (use `cortex-update-item`, `cortex-generate-backlog-index`, etc. for those — also shipped via the cortex-interactive plugin's `bin/`).
- Overnight docs source of truth: `docs/overnight-operations.md` owns the round loop and orchestrator behavior, `docs/pipeline.md` owns pipeline-module internals, and `docs/sdk.md` owns SDK model-selection mechanics. When editing overnight-related docs, update the owning doc and link from the others rather than duplicating content.
