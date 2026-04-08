# Specification: verify-subagent-model-env-var-priority

## Problem Statement

The implementation approach for epic 044 (route interactive subagents to Sonnet) depends on knowing whether `CLAUDE_CODE_SUBAGENT_MODEL` env var overrides per-invocation `Agent(model: ...)` params or vice versa. This priority order was disputed across multiple sources. Without verification, the wrong approach could be implemented — either losing Opus escalation capability (if env var wins and we set it) or adding unnecessary complexity (if per-invocation wins and we don't use the simpler env var approach).

## Requirements

1. **Per-invocation model params work**: Spawning with `model: "sonnet"` produces a Sonnet agent; `model: "opus"` produces Opus. Acceptance criteria: Interactive/session-dependent — verified empirically by spawning agents and checking their self-reported model identity.

2. **Env var priority order documented**: The official Claude Code documentation confirms the resolution order. Acceptance criteria: `grep -c "Env var overrides all per-invocation params" research/subagent-model-routing/research.md` >= 1

3. **DR-1 recommendation updated**: The epic research artifact's DR-1 reflects the verified priority order with approach A ruled out and approach D confirmed. Acceptance criteria: `grep -c "NOT VIABLE" research/subagent-model-routing/research.md` >= 1

## Non-Requirements

- This spike does NOT implement model routing in any skills
- This spike does NOT set the `CLAUDE_CODE_SUBAGENT_MODEL` env var
- This spike does NOT modify CLAUDE.md/Agents.md with model guidance

## Edge Cases

- **Env var can't be tested in-session**: Env vars set in bash subprocesses don't propagate to the parent Claude Code process. Official documentation is used as authoritative source for the env var priority order instead.

## Changes to Existing Behavior

- [MODIFIED: research/subagent-model-routing/research.md] → RQ3, override mechanisms, feasibility table, and DR-1 updated with verified priority order

## Technical Constraints

- Claude models reliably self-report their model identity from system metadata
- Official Claude Code docs (sub-agents page, "Choose a model" section) are the authoritative source for priority order

## Open Decisions

None — all decisions are resolved by the empirical findings and documentation.
