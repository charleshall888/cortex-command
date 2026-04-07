# Requirements: multi-agent

> Last gathered: 2026-04-03

**Parent doc**: [requirements/project.md](project.md)

## Overview

The multi-agent area covers how the system spawns, isolates, and coordinates multiple Claude agents working in parallel. This includes the go/no-go criteria for parallel dispatch, per-feature worktree isolation, model selection based on task characteristics, and error recovery escalation. These capabilities underpin the overnight runner's ability to work on multiple features simultaneously without interference.

## Functional Requirements

### Agent Spawning

- **Description**: Individual agents are spawned via the Claude Agent SDK (`claude_agent_sdk.query()`) with per-dispatch configuration controlling model, turn limit, budget, and tool access.
- **Inputs**: Task description, complexity tier, criticality level, worktree path, feature context
- **Outputs**: Agent execution result (exit report), stderr lines (capped at 100), cost accumulation
- **Acceptance criteria**:
  - Each agent receives its own working directory (worktree), tool allowlist, and system prompt
  - Agent stderr is captured and included in learnings for subsequent retry attempts
  - Agent budget exhaustion halts the current session (no new features dispatched) without crashing
  - Permission mode is always `bypassPermissions` for overnight agents
- **Priority**: must-have

### Worktree Isolation

- **Description**: Each feature executes in an isolated git worktree, providing independent file state and a dedicated branch to prevent interference between parallel agents.
- **Inputs**: Feature slug, repository root, session ID
- **Outputs**: Git worktree at `.claude/worktrees/{feature}/` (default repo) or `$TMPDIR/overnight-worktrees/{session_id}/{feature}/` (cross-repo); branch `pipeline/{feature}` (with collision suffix `-2`, `-3` if needed)
- **Acceptance criteria**:
  - Worktree creation is idempotent (returns existing valid worktree if already present)
  - Feature branch naming follows `pipeline/{feature}` convention with automatic collision detection
  - Stale index locks (`.git/worktrees/{feature}/index.lock`) are removed if no process holds them
  - Worktree cleanup is idempotent and removes both the worktree directory and the branch after merge
  - Cross-repo features get their own integration worktrees in `$TMPDIR` (not in the home repo)
- **Priority**: must-have

### Parallel Dispatch

- **Description**: Multiple features execute concurrently within an overnight session, subject to the tier-based concurrency limit managed by `ConcurrencyManager` and a circuit breaker that halts dispatch when repeated failures occur.
- **Inputs**: Feature list for the current round, tier-based concurrency limit (from `ConcurrencyManager`), circuit breaker state
- **Outputs**: Per-feature execution results; updated session state; batch result accumulation
- **Acceptance criteria**:
  - Features execute concurrently via `asyncio.gather()` with semaphore-based slot enforcement
  - Concurrency limit is 1–3 agents, adaptive: reduces by 1 after 3 rate-limit errors within 5 minutes, restores after 10 consecutive successes
  - Circuit breaker fires after 3 consecutive feature pauses, preventing further dispatches in the session
  - One feature's failure does not abort other in-flight features (fail-forward model)
  - Features with `intra_session_blocked_by` dependencies are excluded from dispatch until all named blockers reach `merged` status — this filtering happens at round-planning time (orchestrator prompt), not at dispatch time
- **Priority**: must-have

### Model Selection Matrix

- **Description**: The model assigned to a feature task is determined by a two-dimensional matrix (task complexity × feature criticality), with an escalation ladder for recovery scenarios.
- **Inputs**: Task complexity (trivial / simple / complex), feature criticality (low / medium / high / critical)
- **Outputs**: Selected model (haiku / sonnet / opus), turn limit (15 / 20 / 30), budget cap ($5 / $25 / $50)
- **Acceptance criteria**:
  - Model selection follows the matrix: trivial+low → haiku; simple/trivial+high/critical → sonnet; complex+high/critical → opus
  - On `agent_test_failure` or `agent_confused` error: escalate model one tier (haiku → sonnet → opus); if already at opus, pause for human
  - On `agent_timeout` or `task_failure`: retry with same model
  - On `agent_refusal` or `infrastructure_failure`: pause for human triage (no retry)
  - On `budget_exhausted` or `api_rate_limit`: pause the entire session (no new dispatches)
- **Priority**: must-have

## Non-Functional Requirements

- **Idempotency**: Sessions that resume after interruption skip features already merged (plan hash + task ID used as idempotency tokens)
- **Context hygiene**: Each retry appends learnings (test output, agent output) to `lifecycle/{feature}/learnings/progress.txt`; subsequent agents receive this history to avoid repeating failed approaches
- **Resource constraints**: Agent stderr capped at 100 lines; learnings entries truncated to 2000 chars; worktrees cleaned up after merge to reclaim disk space

## Architectural Constraints

- Parallelism decisions are made by the overnight orchestrator, not by individual agents — agents do not spawn peer agents.
- The tier-based concurrency limit (1–3 workers) is a hard limit enforced by `ConcurrencyManager`; it is not overridable at runtime by agents.
- Worktrees for the default repo are created inside the repo at `.claude/worktrees/`; cross-repo worktrees go to `$TMPDIR` to avoid sandbox restrictions.
- The escalation ladder is fixed: haiku → sonnet → opus. There is no downgrade path within a session.

## Dependencies

- Claude Agent SDK (`claude_agent_sdk.query()`, `ClaudeAgentOptions`)
- git (worktree management: `git worktree add`, `git worktree remove`, `git worktree prune`)
- `lsof` (stale lock detection in worktree cleanup)
- `ANTHROPIC_API_KEY` environment variable (forwarded to each agent)

## Edge Cases

- **Worktree already exists at target path**: Create handles "already exists" git error and returns existing path
- **Branch collision**: `pipeline/{feature}-2`, `-3` suffixes used when the primary name is taken
- **TMPDIR cleared between sessions**: Stale git tracking for cross-repo worktrees is detected and pruned on next access
- **All features in a round pause**: Circuit breaker fires; session halts; morning report surfaces the reason
- **Feature blocked by unmerged dependency**: Excluded from round; reconsidered in next round if blockers merge

## Open Questions

- None
