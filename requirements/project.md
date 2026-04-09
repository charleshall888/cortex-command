# Requirements: cortex-command

> Last gathered: 2026-04-01 (updated 2026-04-03)

## Overview

Agentic workflow toolkit for AI-assisted software development. Defines the global skills, lifecycle state machine, pipeline orchestrator, and overnight execution framework for Claude Code. The north star is autonomous multi-hour development: send Claude to work with a plan, let it spin up its own teams, and review results afterward. Primarily personal tooling, shared publicly for others to clone or fork. Favors a highly customized, iteratively improved system over generic solutions.

## Philosophy of Work

**Day/night split**: Daytime is close, iterative collaboration — define goals, research, spec. Overnight is full handoff — Claude plans and executes without intervention. Morning is strategic review — not debugging sessions.

**Handoff readiness**: A feature isn't ready for overnight until the spec has no open questions, success criteria are verifiable by an agent with zero prior context, and all lifecycle artifacts are fully self-contained. The spec is the entire communication channel.

**Failure handling**: Surface all failures in the morning report. Keep working on other tasks. Stop only if the failure blocks all remaining work in the session.

**Daytime work quality**: Research before asking. Don't fill unknowns with assumptions — jumping to solutions before understanding the problem produces wasted work.

**Complexity**: Must earn its place by solving a real problem that exists now. When in doubt, the simpler solution is correct.

**Quality bar**: Tests pass and the feature works as specced. ROI matters — the system exists to make shipping faster, not to be a project in itself.

## Architectural Constraints

- **File-based state**: Lifecycle artifacts, backlog items, pipeline state, and session tracking all use plain files (markdown, JSON, YAML frontmatter). No database or server. May evolve if complexity warrants it, but simplicity is preferred.

## Quality Attributes

- **Graceful partial failure**: Individual tasks in an autonomous plan may fail. The system should retry, potentially hand off to a fresh agent with clean context, and fail that task gracefully if unresolvable — while completing the rest.
- **Maintainability through simplicity**: Complexity is managed by iteratively trimming skills and workflows. The system should remain navigable by Claude even as it grows.
- **Iterative improvement**: The architecture must tolerate exploratory development. Not everything is planned upfront — some design will be discovered through use.

## Project Boundaries

### In Scope

- AI workflow orchestration (skills, lifecycle, pipeline, discovery, backlog)
- Overnight execution framework, session management, scheduled launch, and morning reporting
- Dashboard (~1800 LOC FastAPI): real-time web monitoring of overnight sessions
- Conflict resolution pipeline (~2500 LOC): classifies conflicts, dispatches repair agents, retries merges
- Remote access integration (Tailscale, mosh, tmux, Cloudflare Tunnel)
- Observability (statusline, notifications, metrics, cost tracking)
- Multi-agent orchestration: parallel dispatch, worktree isolation, Haiku/Sonnet/Opus model selection matrix
- Global agent configuration (settings, hooks, reference docs)

### Out of Scope

- Dotfiles and machine configuration (terminals, shells, prompts, fonts, git) — those belong in machine-config
- Application code or libraries — those belong in their own repos
- Published packages or reusable modules for others
- Setup automation for new machines (owned by machine-config)

### Deferred

- Migration from file-based state if/when complexity demands it
- Cross-repo work in a single overnight session

## Conditional Loading

Working on statusline, dashboard, or notifications → requirements/observability.md
Working on pipeline, overnight runner, conflict resolution, or deferral → requirements/pipeline.md
Working on remote access, tmux, mosh, or Tailscale → requirements/remote-access.md
Working on agent spawning, parallel dispatch, worktrees, or model selection → requirements/multi-agent.md
