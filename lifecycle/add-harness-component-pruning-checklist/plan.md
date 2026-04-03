# Plan: add-harness-component-pruning-checklist

## Overview

Create `skills/harness-review/SKILL.md` — a single file that contains the component inventory, the 4-question rubric, and the runtime scan + evaluation protocol. The existing symlink architecture deploys it automatically; no additional wiring is needed.

## Tasks

### Task 1: Create skills/harness-review/SKILL.md
- **Files**: `skills/harness-review/SKILL.md`
- **What**: Write the full harness-review skill file containing frontmatter, the curated component inventory (17 entries), the runtime scan protocol, the 4-question rubric, and the output format. This is the entire implementation.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Follow the skill pattern established by `skills/commit/SKILL.md` (simplest example) and `skills/morning-review/SKILL.md` (domain-specific evaluation). Required frontmatter: `name: harness-review` and `description:` (both required per lifecycle.config.md review criteria). Do NOT set `disable-model-invocation: true` — this skill invokes Claude for evaluation. No inputs, outputs, preconditions, or argument-hint frontmatter is needed.

  The SKILL.md body must contain:

  **Section 1 — Component inventory table**: All 17 overnight runner components with file path, one-line original rationale, and initial classification. Use a markdown table. The 17 components are:

  | Component | File | Original rationale | Initial classification |
  |---|---|---|---|
  | Round loop | `claude/overnight/runner.sh` | Safety loop that spawns fresh orchestrators per round; enforces wall-clock limits and circuit breakers | load-bearing |
  | Orchestrator prompt | `claude/overnight/prompts/orchestrator-round.md` | Thin orchestrator prevents context saturation across rounds — reads state only, does not accumulate implementation details | load-bearing |
  | Batch runner | `claude/overnight/batch_runner.py` | Parallel feature dispatch; manages retry budget per task; auto-merges to main | load-bearing |
  | Batch plan hand-off | `claude/overnight/batch_plan.py` + orchestrator prompt §6 | Orchestrator writes batch plan as markdown file; batch runner parses it; adds a parse boundary between planning and execution | pruning-candidate |
  | Retry loop | `claude/pipeline/retry.py` | Fresh agent per attempt prevents context degradation across retries; routes failure types to different strategies | pruning-candidate |
  | Brain agent | `claude/overnight/brain.py` | Post-retry triage when retry budget exhausted; produces SKIP/DEFER/PAUSE verdict | pruning-candidate |
  | Throttle manager | `claude/overnight/throttle.py` | Subscription-aware concurrency; detects rate limits at runtime and reduces concurrency dynamically | load-bearing |
  | Deferral system | `claude/overnight/deferral.py` | Routes questions needing human input to deferred/ directory; prevents questions from blocking the session | load-bearing |
  | State management | `claude/overnight/state.py` | OvernightState dataclass with atomic save/load; phase transition tracking | load-bearing |
  | Backlog selection | `claude/overnight/backlog.py` | Scores and filters backlog items for session; dependency graph, priority, and tag scoring | load-bearing |
  | Morning report | `claude/overnight/report.py` | Collects session data and renders executive summary and per-feature sections | load-bearing |
  | Integration recovery | `claude/overnight/integration_recovery.py` | Flaky guard re-run + repair agent after integration branch test failure | pruning-candidate |
  | Session plan | `claude/overnight/plan.py` | Renders session plan from SelectionResult; validates repos; bootstraps state | load-bearing |
  | Status display | `claude/overnight/status.py` | Live status snapshot during session | load-bearing |
  | Event logging | `claude/overnight/events.py` | JSONL session event log; enforces event type validation | load-bearing |
  | Interrupt handler | `claude/overnight/interrupt.py` | Graceful pause on signal (SIGINT/SIGTERM) | load-bearing |
  | Smoke tests | `claude/overnight/smoke_test.py` | Pre-execution validation before session starts | load-bearing |

  **Section 2 — Protocol**: Step-by-step instructions for Claude. Must include these steps in order:

  1. **Output disclaimer** (first line of output): "Note: this assessment reflects model judgment only — no empirical session data was consulted. Treat verdicts as structured hypotheses, not conclusions."
  2. **Runtime scan**: List all `.py` and `.sh` files in `claude/overnight/` and `claude/pipeline/` and compare against the inventory table. Report: "Evaluated N components from inventory; found M additional unlisted files: [list]." If M = 0, state "No unlisted files detected."
  3. **Docstring check**: For each listed component, read its module-level docstring and compare against the inventory rationale. Note mismatches.
  4. **Rubric evaluation**: For each component (no exemptions based on initial classification), answer the 4 questions and assign a verdict.
  5. **Candidates for Review** section: list all `experiment-candidate` and `likely-deprecated` components, ordered lowest-blast-radius first. If none: "Candidates for Review: none — all components evaluated as load-bearing."

  **Section 3 — The 4-question rubric** (embed verbatim):
  1. What model limitation did this component compensate for? (Read the module docstring — quote the rationale.)
  2. Is that limitation still real at Claude's current baseline? (This is a model judgment call — state confidence level explicitly: high / medium / low.)
  3. What would fail or degrade if this component were removed from the runner?
  4. Verdict: `load-bearing` (non-negotiable, removal causes real breakage), `experiment-candidate` (worth empirically testing removal), or `likely-deprecated` (limitation appears solved; removal is low-risk).

  **Section 4 — Edge case handling** (instruct Claude explicitly):
  - If `claude/overnight/` is not found: print "No overnight runner found at expected path" and exit.
  - If a listed component file is missing from disk: note "not found at path" and skip rubric evaluation, flag as maintenance item.
  - If a module has no docstring: fall back to reading inline comments in the first 30 lines. If no rationale found: note "rationale undocumented" and flag.

- **Verification**: `skills/harness-review/SKILL.md` exists and contains `name: harness-review` and `description:` in frontmatter. `just check-symlinks` exits 0 (symlink auto-registered). Invoke `/harness-review` from the cortex-command repo root and confirm: (a) disclaimer line appears first, (b) coverage statement appears, (c) at least one component verdict is printed, (d) "Candidates for Review" section appears at the end. Commit using `/commit`.
- **Status**: [ ] pending

## Verification Strategy

Run `/harness-review` from the cortex-command repo root. Confirm:
1. Output opens with the model-judgment disclaimer
2. Coverage statement lists N=17 evaluated, M=0 unlisted (or flags any genuinely new files)
3. All 17 components receive a verdict entry with answers to all 4 rubric questions
4. "Candidates for Review" summary appears at end listing at minimum `retry.py`, `brain.py`, and `batch_plan.py` (the three named candidates from discovery research)
5. `just check-symlinks` exits 0
