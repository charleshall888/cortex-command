# Cortex Command Project Instructions

## What This Repo Is

An opinionated AI workflow framework for Claude Code. Provides skills (slash commands), hooks (event handlers), an autonomous overnight runner, a web dashboard, a lifecycle state machine, and backlog management. Ships as a CLI (`uv tool install git+https://github.com/charleshall888/cortex-command.git@<latest-tag>`, where `<latest-tag>` resolves to the highest `vX.Y.Z` ref from `git ls-remote --tags` — see `docs/setup.md` for the full snippet) plus plugins installed via `/plugin install` in Claude Code; `cortex init` additionally registers the repo's `cortex/` umbrella path in `~/.claude/settings.local.json`'s `sandbox.filesystem.allowWrite` array so interactive sessions and the overnight runner can write under it without sandbox prompts.

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

Cortex-command ships as a CLI installed via `uv tool install git+https://github.com/charleshall888/cortex-command.git@<latest-tag>` (resolve `<latest-tag>` via `git ls-remote --tags --refs`; see `docs/setup.md` Quickstart) plus plugins installed via `/plugin install`. It no longer deploys symlinks into `~/.claude/`.

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
- Overnight docs source of truth: `docs/overnight-operations.md` owns the round loop and orchestrator behavior, `docs/internals/pipeline.md` owns pipeline-module internals, `docs/internals/sdk.md` owns SDK model-selection mechanics, and `docs/internals/auto-update.md` owns the plugin/CLI auto-update flow (two-layer architecture, component map, release ritual). When editing overnight-related docs, update the owning doc and link from the others rather than duplicating content.

## Skill / phase authoring guidelines

Before classifying a phase boundary or gate as ceremonial, identify the user-facing affordance that boundary protects. A pause that looks redundant from the agent's perspective may be the only point where a human can redirect, reject, or reshape the work before the lifecycle advances. If the affordance genuinely provides no blocking value — because internals already enforce the constraint — document that reasoning explicitly rather than silently removing the boundary.

The concrete inventory of kept user pauses lives in `skills/lifecycle/SKILL.md` under the "Kept user pauses" section. The parity test at `tests/test_lifecycle_kept_pauses_parity.py` verifies that the implementation matches that inventory. When modifying phase sequencing, update both the SKILL.md inventory and the parity test together.

Prefer structural separation over prose-only enforcement for sequential gates. A gate encoded in skill control flow is harder to accidentally bypass than one that relies on the model reading and following a prose instruction. Prose-only enforcement is appropriate only for guidelines where the cost of occasional deviation is low.

## Solution horizon

This is a long-term project, and proposed fixes should reflect that. Before suggesting a fix, ask whether you already know it will need to be redone — because a follow-up is already planned, the same patch would apply in multiple known places you can name, or it sidesteps a constraint you can already name. If yes, propose the durable version, or surface both choices with the tradeoff. If no, the simpler fix is correct — anchor on current knowledge, not prediction. A deliberately-scoped phase of a multi-phase lifecycle is not a stop-gap. The canonical statement of this principle, and its reconciliation with the simplicity defaults, lives in `cortex/requirements/project.md` under Philosophy of Work.

## Design principle: prescribe What and Why, not How

When authoring skills, hooks, lifecycle templates, or any harness instruction, describe decisions to be made, gates to enforce, output shapes required, and the intent behind each (the What and Why). Resist prescribing step-by-step method (the How).

The reasoning: capable models (Opus 4.7 and later) determine method themselves given clear decision criteria and intent. Spelling out procedure wastes tokens, constrains agent judgment on details the spec author cannot fully anticipate, and tends to produce brittle rails that break when model behavior evolves.

This principle is the conceptual partner to the MUST-escalation policy below: both protect against over-specification — the escalation policy guards against over-constraining model behavior with imperative language; this principle guards against over-constraining it with procedural narration.

## MUST-escalation policy (post-Opus 4.7)

Default to soft positive-routing phrasing for new authoring under epic #82's post-4.7 harness adaptation; pre-existing MUST language is grandfathered until specifically audited (per #85). To add a new MUST/CRITICAL/REQUIRED escalation, you must include in the commit body OR PR description a link to one evidence artifact: (a) `cortex/lifecycle/<feature>/events.log` path + line of an F-row showing Claude skipped the soft form, OR (b) a commit-linked transcript URL or quoted excerpt. Without one of these artifact links, the escalation is rejected at review.

Before adding or restoring a MUST, run a dispatch with `effort=high` (and `effort=xhigh` if effort=high also fails) on a representative case and record the result. Escalate to MUST only when effort=high (and xhigh) demonstrably fail to resolve the observed failure. Record the effort attempt in the escalation note: cite the events.log entry showing the effort=high run + outcome, OR paste the transcript excerpt. If the dispatch path does not currently expose `effort` as a tunable parameter, cite the specific dispatch path file and file a separate wiring ticket — do not escalate to MUST as a workaround.

OQ3's escalation rule applies to all observed-failure types: correctness, control-flow, routing, latency, format-conformance, tool-selection, hallucination, and any other behavior-correctness failure mode. The single exception is **tone perception** — failures where the complaint is about Claude's voice, conciliatoriness, validation phrasing, or emoji usage rather than an action Claude omitted, mis-routed, or mis-executed. Tone perception is governed by the OQ6 policy below; all other failure types are OQ3-eligible escalation triggers.

Re-evaluation triggers: (a) Anthropic publishes guidance reversing the 'soften MUST' posture for any future model; (b) the dispatch-path effort parameter exposed by the SDK changes shape such that R3's effort-first clause is no longer applicable. Cross-refs: ticket #91 (this policy), epic #82, audit #85.
Tone/voice policy: see docs/policies.md
