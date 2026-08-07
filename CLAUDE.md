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

Run `just` to see all recipes — key ones: `just backlog-index`, `just validate-commit`, `just test`. Dependencies: [just](https://github.com/casey/just), Python 3, [uv](https://docs.astral.sh/uv/). Run `just setup-githooks` after clone to enable the dual-source hooks — skipping it means your commits land canonical-source edits without their regenerated plugin mirrors. `cortex-jcc <recipe>` runs recipes from any directory in this repo's context (repo-specific operations only; for another repo's files use the item verbs like `cortex-update-item`). It is not a console script and `bin/` is not on PATH by default — it needs `CORTEX_COMMAND_ROOT` exported and `bin/` added to PATH in your shell profile, otherwise use `just` from the repo root.

## Conventions

- Always commit using the `/cortex-core:commit` skill — never run `git commit` manually. A shared hook validates messages (imperative mood, capitalized, no trailing period, max 72-char subject); if it rejects a commit, fix the message rather than bypassing it via `git commit -F` or an editor, which the hook cannot see.
- **Release-type markers** drive this repo's auto-release semver bump on every push to `main` (default **patch**). Put `[release-type: minor]` (backward-compatible feature) or `[release-type: major]` (breaking change) alone on its own line in the commit body — matched by `(?im)^\s*\[release-type:\s*(major|minor)\s*\]\s*$`, so an indented or inline marker is ignored. Precedence across commits since the last tag is `major` > `minor` > `patch`; a column-0 `BREAKING:` / `BREAKING CHANGE:` token forces major as a backstop. Preview with `cortex-auto-bump-version --dry-run` (read-only, exits 0 even on `no-bump`).
- Editing `skills/`, `hooks/`, `claude/hooks/`, `bin/cortex-*`, `cortex_command/common.py`, `plugins/cortex-pr-review/`, or `plugins/cortex-ui-extras/` is lifecycle-gated — run `/cortex-core:dev` first, which routes to `/cortex-core:refine` or `/cortex-core:build` depending on the ticket's status. Edit canonical sources only; the `plugins/cortex-core/{skills,hooks,bin}/` mirrors are rebuilt from your staged blobs by the pre-commit hook and folded into the commit, so never stage them by hand — and expect the commit to contain mirror paths you did not name.
- Prefer structural separation over prose-only enforcement for sequential gates; prose-only is appropriate only where occasional deviation is cheap.
- No tests pinning skill prose. A test must not assert that a phrase, sentence, or instruction *appears* in a SKILL.md or `references/` body, nor pin prose layout (proximity, ordering, occurrence counts, section placement) — such tests pass only by keeping the words where they are, so every trim becomes a failure and adding prose is the cheapest way to stay green. Fine: reading skill markdown as structure (frontmatter fields, size pins, path resolution, mirror parity, generated-file freshness); *absence* assertions, which keep a removal removed; and a bare existence assertion on a machine token whose omission fails silently, with that failure named in the docstring. To pin a behavior, move it into a CLI verb and test the verb. Elaboration: `docs/policies.md`.
- Resolve `${CLAUDE_SKILL_DIR}` only in a SKILL.md body, then propagate the absolute path to references and subagent prompts — enforced by the `cortex-check-skill-path` lint; rationale in `cortex/adr/0009-skill-path-resolution-for-plugin-distributed-skills.md`.
- Settings JSON must remain valid JSON; hook/notification scripts must be executable (`chmod +x`). Agent-specific config goes in `claude/`.
- Before authoring or editing skills, hooks, phase templates, overnight docs, dashboard behavior, or dashboard docs, read `docs/policies.md` — it owns the skill/phase authoring guidelines (kept-pauses affordances, What/Why-not-How, L1 surface budgets), the MUST-escalation policy, the overnight docs ownership map, the dashboard docs source of truth, and the tone policy.
- Shipped surfaces (`skills/`, `plugins/`) carry no cortex-command-repo governance — they install into consumer repos where this repo's clauses don't exist. Directions for working on the harness itself belong here, in `docs/policies.md`, or in `cortex/requirements/`.
- Backlog tickets follow the front-door evidence bar: a ticket adding harness machinery names specific evidence in its Why (measured cost or observed failure, not a hypothetical), and an efficiency-framed ticket states its expected net effect on the surface it claims to shrink. Canonical statement: Deletion bias, `cortex/requirements/project.md`.

## Solution horizon

This is a long-term project; before proposing a fix, ask whether you already know it will need to be redone — a follow-up is already planned, the same patch would apply in multiple known places you can name, or it sidesteps a constraint you can already name. If yes, propose the durable version, or surface both choices with the tradeoff. If no, the simpler fix is correct — anchor on current knowledge, not prediction. A deliberately-scoped phase of a multi-phase lifecycle is not a stop-gap. Canonical statement and its reconciliation with the simplicity defaults: `cortex/requirements/project.md`, Philosophy of Work.
