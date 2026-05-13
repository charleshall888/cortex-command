# Requirements: cortex-command

> Last gathered: 2026-04-01 (updated 2026-05-12)

## Overview

Agentic workflow toolkit for AI-assisted software development on Claude Code: skills, lifecycle state machine, pipeline orchestrator, overnight execution. North star: autonomous multi-hour development — Claude works from a plan, spins up teams, reports afterward. Ships CLI-first as a non-editable wheel: `uv tool install git+<url>@<tag>`.

## Philosophy of Work

**Day/night split**: Daytime is iterative collaboration; overnight is handoff; morning is strategic review, not debugging.

**Handoff readiness**: A feature isn't overnight-ready until the spec has no open questions, criteria are agent-verifiable from zero context, artifacts self-contained.

**Failure handling**: Surface failures in the morning report; keep working unless blocked.

**Daytime work**: Research before asking; don't fill unknowns with assumptions.

**Complexity**: Must earn its place by solving a real problem now. When in doubt, simpler wins.

**Solution horizon**: Long-term project — fixes reflect that. Before suggesting a fix, ask: do I already know this needs redoing (follow-up planned, patch applies in multiple known places, sidesteps a known constraint)? If yes, propose the durable version or surface both with tradeoff. If no, **Complexity** applies. A scoped phase of a multi-phase lifecycle is not a stop-gap (stop-gap means unplanned-redo). Test: current knowledge, not prediction.

**Quality bar**: Tests pass; the feature works as specced. ROI matters — ship faster, not be a project.

## Architectural Constraints

- **File-based state**: Lifecycle, backlog, pipeline, sessions in plain files (markdown/JSON/YAML). No database.
- **Per-repo sandbox registration**: `cortex init` additively adds the repo's `cortex/` umbrella to `~/.claude/settings.local.json` `sandbox.filesystem.allowWrite` — the only write cortex-command makes in `~/.claude/`. `fcntl.flock` serialized.
- **SKILL.md-to-bin parity enforcement**: `bin/cortex-*` scripts wire through an in-scope SKILL.md/requirements/docs/hooks/justfile/tests reference. `bin/cortex-check-parity` blocks drift; exceptions at `bin/.parity-exceptions.md`.
- **SKILL.md size cap**: 500 lines (`tests/test_skill_size_budget.py`). Exceptions via in-file `<!-- size-budget-exception: ... -->`. Default fix: extract to `skills/<name>/references/`.
- **Skill-helper modules**: when a SKILL.md dispatch ceremony invites paraphrase, collapse it into atomic `cortex_command/<skill>.py` subcommands fusing validation+mutation+telemetry. New events register in `bin/.events-registry.md`.

## Quality Attributes

- **Graceful partial failure**: Tasks may fail. The system retries, optionally hands off to a fresh agent, fails gracefully — completing the rest.
- **Maintainability through simplicity**: Complexity is managed by iteratively trimming skills/workflows.
- **Iterative improvement**: Architecture tolerates exploratory development; design emerges through use.
- **Defense-in-depth for permissions**: `settings.json` ships minimal allow, comprehensive deny, sandbox on. For sandbox-excluded commands (git, gh, WebFetch) the allow/deny list is sole enforcement — keep global allows read-only. Overnight runs `--dangerously-skip-permissions`; sandbox is the critical surface.
- **Destructive operations preserve uncommitted state**: Cleanup scripts removing user-visible artifacts (worktrees, branches, sessions) SKIP on uncommitted state. Inline destructive sequences extract into named scripts.

## Project Boundaries

### In Scope

- AI workflow orchestration (skills, lifecycle, pipeline). Discovery and backlog are documented inline (no area docs): `skills/discovery/SKILL.md`, `cortex/backlog/index.md`.
- Overnight execution: framework, sessions, scheduled launch, morning report
- Dashboard (~1800 LOC FastAPI), conflict resolution pipeline (~2500 LOC), remote access (Tailscale/mosh/tmux/Cloudflare Tunnel)
- Observability (statusline, notifications, metrics, cost); global agent config
- Multi-agent: parallel dispatch, worktrees, Haiku/Sonnet/Opus selection

### Out of Scope

- Dotfiles, machine configuration, setup automation for new machines — belong in machine-config
- Application code or libraries — belong in their own repos
- Published packages or reusable modules for others — out of scope; cortex ships as a non-editable wheel

### Deferred

- Migration from file-based state if complexity demands it
- Cross-repo work in one overnight session

## Conditional Loading

- statusline/dashboard/notifications → cortex/requirements/observability.md
- pipeline/overnight runner/conflict resolution/deferral → cortex/requirements/pipeline.md
- remote access/tmux/mosh/Tailscale → cortex/requirements/remote-access.md
- agent spawning/parallel dispatch/worktrees/model selection → cortex/requirements/multi-agent.md

## Optional

Content here is prunable under token pressure — skip without losing spec-required guidance.

- **Sandbox preflight gate**: `bin/cortex-check-parity` validates `cortex/lifecycle/{feature}/preflight.md` on sandbox-source diffs; fails on missing/invalid preflight or `claude --version` drift.
- **Two-mode gate pattern**: pre-commit gates pair `--staged` (diff schema) with `--audit` (time/repo-wide, `just <recipe>-audit`). See `bin/cortex-check-events-registry`.
- **Workflow trimming**: unearned workflows are removed wholesale. Retirements in `CHANGELOG.md`.
