---
name: harness-review
description: Evaluate overnight runner components against a curated inventory using a 4-question rubric to classify each as load-bearing, experiment-candidate, or likely-deprecated. Use when user says "/harness-review", "review the harness", "audit overnight components", or "check for pruning candidates".
---

# Harness Review

Evaluate each overnight runner component against its original rationale using the 4-question rubric below. Produce a structured verdict for all 17 inventory components, then list candidates for removal or experimentation.

## Section 1 — Component Inventory

| Component | File | Original rationale | Initial classification |
|---|---|---|---|
| Round loop | `cortex_command/overnight/runner.sh` | Safety loop that spawns fresh orchestrators per round; enforces wall-clock limits and circuit breakers | load-bearing |
| Orchestrator prompt | `cortex_command/overnight/prompts/orchestrator-round.md` | Thin orchestrator prevents context saturation across rounds — reads state only, does not accumulate implementation details | load-bearing |
| Batch runner | `cortex_command/overnight/batch_runner.py` | Parallel feature dispatch; manages retry budget per task; auto-merges to main | load-bearing |
| Batch plan hand-off | `cortex_command/overnight/batch_plan.py` + orchestrator prompt §6 | Orchestrator writes batch plan as markdown file; batch runner parses it; adds a parse boundary between planning and execution | pruning-candidate |
| Retry loop | `cortex_command/pipeline/retry.py` | Fresh agent per attempt prevents context degradation across retries; routes failure types to different strategies | pruning-candidate |
| Brain agent | `cortex_command/overnight/brain.py` | Post-retry triage when retry budget exhausted; produces SKIP/DEFER/PAUSE verdict | pruning-candidate |
| Throttle manager | `cortex_command/overnight/throttle.py` | Subscription-aware concurrency; detects rate limits at runtime and reduces concurrency dynamically | load-bearing |
| Deferral system | `cortex_command/overnight/deferral.py` | Routes questions needing human input to deferred/ directory; prevents questions from blocking the session | load-bearing |
| State management | `cortex_command/overnight/state.py` | OvernightState dataclass with atomic save/load; phase transition tracking | load-bearing |
| Backlog selection | `cortex_command/overnight/backlog.py` | Scores and filters backlog items for session; dependency graph, priority, and tag scoring | load-bearing |
| Morning report | `cortex_command/overnight/report.py` | Collects session data and renders executive summary and per-feature sections | load-bearing |
| Integration recovery | `cortex_command/overnight/integration_recovery.py` | Flaky guard re-run + repair agent after integration branch test failure | pruning-candidate |
| Session plan | `cortex_command/overnight/plan.py` | Renders session plan from SelectionResult; validates repos; bootstraps state | load-bearing |
| Status display | `cortex_command/overnight/status.py` | Live status snapshot during session | load-bearing |
| Event logging | `cortex_command/overnight/events.py` | JSONL session event log; enforces event type validation | load-bearing |
| Interrupt handler | `cortex_command/overnight/interrupt.py` | Graceful pause on signal (SIGINT/SIGTERM) | load-bearing |
| Smoke tests | `cortex_command/overnight/smoke_test.py` | Pre-execution validation before session starts | load-bearing |

## Section 2 — Protocol

Follow these steps in order. Do not skip steps.

### Step 1: Output disclaimer

The very first line of your output must be:

> Note: this assessment reflects model judgment only — no empirical session data was consulted. Treat verdicts as structured hypotheses, not conclusions.

### Step 2: Runtime scan

List all `.py` and `.sh` files in `cortex_command/overnight/` and `cortex_command/pipeline/`. Compare against the inventory table above.

Report exactly: "Evaluated N components from inventory; found M additional unlisted files: [list]." If M = 0, state "No unlisted files detected."

### Step 3: Docstring check

For each listed component, read its module-level docstring and compare against the inventory rationale. Note any mismatches between the docstring and the rationale in the table.

### Step 4: Rubric evaluation

For each component in the inventory (no exemptions based on initial classification), apply the 4-question rubric in Section 3 and assign a verdict. Display each component's evaluation inline as you work through them.

### Step 5: Candidates for Review section

After all verdicts, output a "Candidates for Review" section that lists all components with verdict `experiment-candidate` or `likely-deprecated`, ordered lowest-blast-radius first.

If no components received those verdicts, output: "Candidates for Review: none — all components evaluated as load-bearing."

## Section 3 — The 4-Question Rubric

Apply these four questions to every component. No component is exempt.

1. What model limitation did this component compensate for? (Read the module docstring — quote the rationale.)
2. Is that limitation still real at Claude's current baseline? (This is a model judgment call — state confidence level explicitly: high / medium / low.)
3. What would fail or degrade if this component were removed from the runner?
4. Verdict: `load-bearing` (non-negotiable, removal causes real breakage), `experiment-candidate` (worth empirically testing removal), or `likely-deprecated` (limitation appears solved; removal is low-risk).

## Section 4 — Edge Case Handling

Handle these conditions explicitly:

- **`cortex_command/overnight/` not found**: Print "No overnight runner found at expected path" and stop. Do not attempt to evaluate any components.
- **Listed component file missing from disk**: Note "not found at path" next to that component, skip rubric evaluation for it, and flag it as a maintenance item in a separate "Maintenance Items" section at the end.
- **Module has no docstring**: Fall back to reading inline comments in the first 30 lines of the file. If no rationale is found there either, note "rationale undocumented" and flag the component.
