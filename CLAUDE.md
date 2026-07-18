# Cortex Command Project Instructions

## What This Repo Is

An opinionated AI workflow framework for Claude Code: skills (slash commands), hooks (event handlers), an autonomous overnight runner, a web dashboard, a lifecycle state machine, and backlog management. Ships as a CLI (`uv tool install "cortex-command[all] @ git+https://github.com/charleshall888/cortex-command.git@<latest-tag>"`, where `<latest-tag>` is the highest `vX.Y.Z` ref from `git ls-remote --tags`, and the `[all]` extra pulls the dashboard + overnight stacks that live behind optional extras — full snippet in `docs/setup.md`) plus plugins installed via `/plugin install`; no symlinks into `~/.claude/`. `cortex init` registers the repo's `cortex/` umbrella path in `~/.claude/settings.local.json`'s `sandbox.filesystem.allowWrite` array so interactive sessions and the overnight runner can write under it without sandbox prompts.

## Repository Structure

- `skills/` - Skills (commit, pr, lifecycle, etc.)
- `hooks/` - Hooks (commit validation, lifecycle scanning, notifications)
- `claude/` - Claude Code config (settings, statusline, hooks)
- `cortex/` - Tool-managed umbrella (lifecycle, backlog, requirements, research, retros, debug)
  - `cortex/backlog/` - Project backlog items (YAML frontmatter markdown files)
  - `cortex/requirements/` - Project and area-level requirements (vision, priorities, scope)
  - `cortex/lifecycle/` - Feature lifecycle tracking (research, spec, plan, implementation)
- `docs/` - Documentation (setup guide, agentic layer, overnight, skills reference)
- `tests/` - Automated test suite for skills, hooks, and overnight runner
- `bin/` - Global CLI utilities; canonical source mirrored into the `cortex-core` plugin's `bin/` via dual-source enforcement

## Commands

Run `just` to see all recipes — key ones: `just backlog-index`, `just validate-commit`, `just test`. Dependencies: [just](https://github.com/casey/just), Python 3, [uv](https://docs.astral.sh/uv/). Run `just setup-githooks` after clone to enable the dual-source drift pre-commit hook. `cortex-jcc <recipe>` runs recipes from any directory in this repo's context (repo-specific operations only; for another repo's files use the item verbs like `cortex-update-item`).

## Conventions

- Always commit using the `/cortex-core:commit` skill — never run `git commit` manually. A shared hook validates messages (imperative mood, capitalized, no trailing period, max 72-char subject).
- Editing `skills/`, `hooks/`, `claude/hooks/`, `bin/cortex-*`, `cortex_command/common.py`, `plugins/cortex-pr-review/`, or `plugins/cortex-ui-extras/` is lifecycle-gated — run `/cortex-core:lifecycle` first. Edit canonical sources only; the `plugins/cortex-core/{skills,hooks,bin}/` mirrors regenerate via the pre-commit hook.
- Prefer structural separation over prose-only enforcement for sequential gates; prose-only is appropriate only where occasional deviation is cheap.
- Resolve `${CLAUDE_SKILL_DIR}` only in a SKILL.md body, then propagate the absolute path to references and subagent prompts — enforced by the `cortex-check-skill-path` lint; rationale in `cortex/adr/0009-skill-path-resolution-for-plugin-distributed-skills.md`.
- Settings JSON must remain valid JSON; hook/notification scripts must be executable (`chmod +x`). Agent-specific config goes in `claude/`.
- Before authoring or editing skills, hooks, phase templates, or overnight docs, read `docs/policies.md` — it owns the skill/phase authoring guidelines (kept-pauses affordances, What/Why-not-How, L1 surface budgets), the MUST-escalation policy, the overnight docs ownership map, and the tone policy.

## Solution horizon

This is a long-term project; before proposing a fix, ask whether you already know it will need to be redone — a follow-up is already planned, the same patch would apply in multiple known places you can name, or it sidesteps a constraint you can already name. If yes, propose the durable version, or surface both choices with the tradeoff. If no, the simpler fix is correct — anchor on current knowledge, not prediction. A deliberately-scoped phase of a multi-phase lifecycle is not a stop-gap. Canonical statement and its reconciliation with the simplicity defaults: `cortex/requirements/project.md`, Philosophy of Work.
