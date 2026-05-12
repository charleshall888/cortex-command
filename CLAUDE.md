# Cortex Command Project Instructions

## What This Repo Is

An opinionated AI workflow framework for Claude Code. Provides skills (slash commands), hooks (event handlers), an autonomous overnight runner, a web dashboard, a lifecycle state machine, and backlog management. Ships as a CLI (`uv tool install git+https://github.com/charleshall888/cortex-command.git@v0.1.0`) plus plugins installed via `/plugin install` in Claude Code; `cortex init` additionally registers the repo's `cortex/` umbrella path in `~/.claude/settings.local.json`'s `sandbox.filesystem.allowWrite` array so interactive sessions and the overnight runner can write under it without sandbox prompts.

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

- Always commit using the `/cortex-core:commit` skill -- never run `git commit` manually
- Commit messages: imperative mood, capitalized, no trailing period, max 72 chars subject
- A shared hook validates commit messages automatically
- New skills go in `skills/` with `name` and `description` frontmatter; `when_to_use:` is optional and concatenated to `description:` for routing.
- Agent-specific config goes in `claude/`
- Settings JSON must remain valid JSON
- Hook/notification scripts must be executable (`chmod +x`)
- New global utilities ship via the `cortex-core` plugin's `bin/` directory; see `just --list` for available recipes.
- Run `just setup-githooks` after clone to enable the dual-source drift pre-commit hook.
- Use `cortex-jcc <recipe>` to invoke cortex-command recipes from any directory. The wrapper (shipped in `plugins/cortex-core/bin/`) runs recipes in this repo's directory context, so it's suitable for repo-specific operations (`cortex-jcc backlog-index`, `cortex-jcc validate-commit`), not for operations that should act on another repo's files (use `cortex-update-item`, `cortex-generate-backlog-index`, etc. for those — also shipped via the cortex-core plugin's `bin/`).
- Overnight docs source of truth: `docs/overnight-operations.md` owns the round loop and orchestrator behavior, `docs/internals/pipeline.md` owns pipeline-module internals, and `docs/internals/sdk.md` owns SDK model-selection mechanics. When editing overnight-related docs, update the owning doc and link from the others rather than duplicating content.

## MUST-escalation policy (post-Opus 4.7)

Default to soft positive-routing phrasing for new authoring under epic #82's post-4.7 harness adaptation; pre-existing MUST language is grandfathered until specifically audited (per #85). To add a new MUST/CRITICAL/REQUIRED escalation, you must include in the commit body OR PR description a link to one evidence artifact: (a) `cortex/lifecycle/<feature>/events.log` path + line of an F-row showing Claude skipped the soft form, OR (b) a commit-linked transcript URL or quoted excerpt. Without one of these artifact links, the escalation is rejected at review.

Before adding or restoring a MUST, run a dispatch with `effort=high` (and `effort=xhigh` if effort=high also fails) on a representative case and record the result. Escalate to MUST only when effort=high (and xhigh) demonstrably fail to resolve the observed failure. Record the effort attempt in the escalation note: cite the events.log entry showing the effort=high run + outcome, OR paste the transcript excerpt. If the dispatch path does not currently expose `effort` as a tunable parameter, cite the specific dispatch path file and file a separate wiring ticket — do not escalate to MUST as a workaround.

OQ3's escalation rule applies to all observed-failure types: correctness, control-flow, routing, latency, format-conformance, tool-selection, hallucination, and any other behavior-correctness failure mode. The single exception is **tone perception** — failures where the complaint is about Claude's voice, conciliatoriness, validation phrasing, or emoji usage rather than an action Claude omitted, mis-routed, or mis-executed. Tone perception is governed by the OQ6 policy below; all other failure types are OQ3-eligible escalation triggers.

Re-evaluation triggers: (a) Anthropic publishes guidance reversing the 'soften MUST' posture for any future model; (b) the dispatch-path effort parameter exposed by the SDK changes shape such that R3's effort-first clause is no longer applicable. Cross-refs: ticket #91 (this policy), epic #82, audit #85.
Tone/voice policy: see docs/policies.md
