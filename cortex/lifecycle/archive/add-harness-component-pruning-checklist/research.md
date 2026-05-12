# Research: add-harness-component-pruning-checklist

## Epic Reference

Epic research lives at `research/harness-design-long-running-apps/research.md`. That document covers the full harness design question (evaluator agents, spec quality gates, context resets, load-bearing vs. compensation audit) across all tickets in the epic. This ticket is scoped to DR-4 of that research: the component pruning ritual.

---

## Codebase Analysis

### Overnight runner component inventory

All components live in `claude/overnight/` (Python modules) and `claude/overnight/prompts/` (prompt templates), plus `claude/pipeline/` for dispatch and retry logic.

| Component | File | Role | Classification |
|-----------|------|------|----------------|
| Round loop | `runner.sh` | Outer safety loop; spawns fresh orchestrator per round; enforces wall-clock limits, circuit breakers | Load-bearing |
| Orchestrator prompt | `prompts/orchestrator-round.md` | Per-round orchestrator: reads state → selects features → writes batch plan → exits | Load-bearing (thin pattern) |
| Batch runner | `batch_runner.py` | Parallel feature dispatch via Agent SDK; parses batch plan, manages retry budget, auto-merges | Load-bearing |
| Batch plan hand-off | `batch_plan.py` + `orchestrator-round.md` §6 | Orchestrator writes plan as markdown file; batch runner parses it | Pruning candidate — file-based hand-off adds a parse boundary; direct function call may suffice |
| Retry loop | `claude/pipeline/retry.py` | Fresh agent per attempt + accumulated learnings injection; failure classification routing | Pruning candidate — fresh-process isolation compensates for context degradation; worth testing continued-conversation retry |
| Brain agent | `brain.py` | Post-retry triage: SKIP/DEFER/PAUSE after retry exhaustion; fallback to PAUSE on brain failure | Pruning candidate — worker exit reports already carry structured SKIP/DEFER/PAUSE signal |
| Throttle manager | `throttle.py` | Subscription-aware concurrency; detects rate limits and reduces concurrency dynamically | Load-bearing |
| Deferral system | `deferral.py` | Routes questions needing human input to `deferred/{feature}-q{N}.md`; severity-ranked | Load-bearing |
| State management | `state.py` | OvernightState dataclass; atomic save/load; phase transition tracking | Load-bearing |
| Backlog selection | `backlog.py` | Scores and filters backlog items for session; dependency graph, priority, tag scoring | Load-bearing |
| Morning report | `report.py` | Collects session data, renders executive summary and per-feature sections | Load-bearing |
| Integration recovery | `integration_recovery.py` | Flaky guard re-run + repair agent after integration branch test failure | Worth evaluating — added to handle a specific failure mode; worth checking if still triggered |
| Session plan | `plan.py` | Renders session plan from SelectionResult; validates repos; bootstraps state | Load-bearing |
| Status display | `status.py` | Live status snapshot during session | Load-bearing |
| Event logging | `events.py` | JSONL session event log | Load-bearing |
| Interrupt handler | `interrupt.py` | Graceful pause on signal | Load-bearing |
| Smoke tests | `smoke_test.py` | Pre-execution validation | Load-bearing |

### Component rationale in source code

Component rationale IS documented in module docstrings and inline comments (confirmed by codebase exploration):
- `brain.py` docstring: "replaces judgment.py with a unified SKIP/DEFER/PAUSE decision model; operates post-retry-exhaustion"
- `retry.py` docstring: failure classification strategy with explicit routing per type (timeout→retry, refusal→pause, confused→escalate)
- `throttle.py` docstring: "Subscription-aware concurrency management with adaptive rate limit backoff"
- `deferral.py` docstring: "Questions requiring human input deferred rather than blocking the session"
- `integration_recovery.py` docstring: "When integration branch tests fail after merging a feature, performs flaky guard re-run + repair agent dispatch"

**Design implication**: The skill can instruct Claude to read module docstrings at evaluation time to anchor the "original rationale" column — this keeps the skill self-maintaining without baking stale rationale into SKILL.md text.

### Existing skill patterns

Skills live in `skills/{name}/SKILL.md`. Required frontmatter: `name` and `description`. Optional: `inputs`, `outputs`, `preconditions`, `argument-hint`, `disable-model-invocation`.

For a skill with no structured outputs (prints to terminal), no inputs, and no preconditions, the minimal form works:

```yaml
---
name: harness-review
description: ...
---
```

`disable-model-invocation: true` is for procedural-only skills (e.g., ones that just run bash). Since this skill invokes Claude to do the evaluation, it should NOT set this flag.

### Morning-review skill

Exists at `skills/morning-review/SKILL.md`. Uses `disable-model-invocation: true` and walks report sections procedurally. Does NOT belong in morning-review: (a) it's already procedurally-driven and adding evaluation logic would violate its scope, (b) the user confirmed standalone skill is preferred.

### Skill deployment

New skill goes in `skills/harness-review/SKILL.md`. It will be globally symlinked to `~/.claude/skills/harness-review/SKILL.md` by the existing symlink architecture. No additional deployment steps needed (`just setup` or `just check-symlinks` covers it). When run from a project without overnight runner files, the skill will simply find nothing to evaluate — graceful degradation.

## Open Questions

- None. Component inventory, output format (printed to terminal), trigger (user-invoked on demand), and scope (all components) are resolved by Clarify. The pruning rubric definition ("what makes a component no longer load-bearing?") is the core design work for the Spec phase — not a research gap.
