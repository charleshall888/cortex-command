# Requirements: cortex-command

> Last gathered: 2026-04-01

## Overview

Agentic workflow toolkit for AI-assisted software development. Defines the global skills, lifecycle state machine, pipeline orchestrator, and overnight execution framework for Claude Code. The north star is autonomous multi-hour development: send Claude to work with a plan, let it spin up its own teams, and review results afterward. Primarily personal tooling, shared publicly for others to clone or fork. Favors a highly customized, iteratively improved system over generic solutions.

## Philosophy of Work

### The Day/Night Split

Work is organized around two distinct modes of collaboration:

**Daytime** is close, iterative collaboration. The human guides direction — refining requirements, researching problems, speccing features. Claude follows the human's lead, proposes options, and surfaces gaps. This is where goals are defined and understood. Neither party should rush toward implementation before the goal is clear.

**Overnight** is full handoff. Once a spec is solid, Claude takes over for technical planning and execution without human intervention. The human steps back completely. The goal is to wake up to finished work.

**Morning** is review and steering. The human reviews what was built, answers any deferred questions, and decides what goes next. This is not debugging sessions — it's strategic review.

The long-term direction is fully autonomous: describe a goal, Claude builds it. Trust is earned incrementally as the system proves reliable.

### Handoff Readiness

A feature isn't ready for overnight execution until:

- The spec has no open questions
- Success criteria are explicit and verifiable by an agent that has never seen the conversation
- All lifecycle artifacts are fully self-contained — assume zero shared context between the human and the overnight agent

The spec is the entire communication channel. If the agent can't determine what "done" looks like from the written artifact alone, the spec isn't ready.

### Failure Handling

Overnight failures should not stop the session. When a task fails:

- Keep going on other tasks and features
- Surface every failure clearly in the morning report — no silent skips
- Mark failed features and tasks appropriately so morning review is efficient
- Only stop if the failure blocks all remaining work in the session

Failures are data. They feed back into future specs and plans. They are not reasons to make the system more conservative — they are reasons to spec better.

### Daytime Work Quality

Claude should not fill unknowns with assumptions. When something is unclear:

1. Research it first
2. Ask only if research doesn't resolve it

Jumping to detailed solutions before the problem is understood produces wasted work. The right order is: understand the goal → identify unknowns → resolve them → then specify.

### Complexity

Complexity must earn its place by solving a real problem that exists now. Anticipated complexity, built for hypothetical future needs, will be cut. When in doubt, the simpler solution is correct.

### Quality Bar

The bar for merging overnight work is pragmatic: tests pass and the feature works as specced. This is productivity infrastructure — ROI matters. The system exists to make shipping faster, not to be a project in itself.

## Core Feature Areas

1. **Skills & workflow engine**: Lifecycle state machine, pipeline orchestrator, discovery system, dev routing, backlog management. Defines how Claude plans, researches, specifies, implements, reviews, and completes features — with increasing autonomy over time.
2. **Remote access**: Prompt Claude from Android via Tailscale/mosh with tmux persistence. Enables monitoring and steering autonomous work from anywhere. (Shared concern with machine-config, which owns the underlying dotfiles and terminal setup.)
3. **Observability**: Statusline dashboard, cross-platform notifications (macOS, Android, Windows). Know when Claude needs attention or finishes work.
4. **Multi-agent support**: Claude Code is primary. Cursor, Gemini, Copilot get shared instructions via Agents.md but are rarely used. Parity is nice-to-have, not a requirement. Claude Code's own parallel agent spawning (Agent tool, worktree isolation, team mode) is operational and in production.

## Architectural Constraints

- **File-based state**: Lifecycle artifacts, backlog items, pipeline state, and session tracking all use plain files (markdown, JSON, YAML frontmatter). No database or server. May evolve if complexity warrants it, but simplicity is preferred.

## Quality Attributes

- **Graceful partial failure**: Individual tasks in an autonomous plan may fail. The system should retry, potentially hand off to a fresh agent with clean context, and fail that task gracefully if unresolvable — while completing the rest. Full plan failure is not acceptable; partial task failure is.
- **Maintainability through simplicity**: Complexity is managed by iteratively trimming skills and workflows. The system should remain navigable by Claude even as it grows.
- **Iterative improvement**: The architecture must tolerate exploratory development. Not everything is planned upfront — some design will be discovered through use.

## Project Boundaries

### In Scope

- AI workflow orchestration (skills, lifecycle, pipeline, discovery, backlog)
- Overnight execution framework and session management
- Remote access integration (Tailscale, mosh, tmux, Cloudflare Tunnel)
- Observability (statusline, notifications, metrics)
- Multi-agent instructions and hooks
- Global agent configuration (settings, hooks, reference docs)

### Out of Scope

- Dotfiles and machine configuration (terminals, shells, prompts, fonts, git) — those belong in machine-config
- Application code or libraries — those belong in their own repos
- Published packages or reusable modules for others
- Multi-agent feature parity — Claude Code is primary, others get best-effort
- Setup automation for new machines (owned by machine-config)

### Deferred

- Migration from file-based state if/when complexity demands it
- Cross-repo work in a single overnight session

## Open Questions

- How will the autonomous overnight workflow handle cross-repo work (e.g., Claude working across multiple projects in one plan)?
- At what complexity threshold should file-based state migrate to something more structured?
- How should skills and workflows be versioned or rolled back if an iteration makes things worse?
