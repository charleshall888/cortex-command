# Research: Prevent agents from writing their own completion evidence

## Epic Reference

Background context from `research/harness-design-long-running-apps/research.md` — the epic discovery research identified this as Instance 1 in the "Declaring victory prematurely" findings. The self-sealing log entry failure mode is distinct from ticket 019 (weak verification) and ticket 022 (non-atomic state writes). This ticket addresses verification provenance specifically.

## Codebase Analysis

### Confirmed instance (already fixed)

`lifecycle/non-destructive-claude-md-strategy/plan.md` Task 1: originally had the agent write a `req1_verified` event and then check for it. Fixed to require a pre-existing event written by a human in a prior session. The verification field now explicitly states: "The agent did not create this entry."

### Key distinction: benign self-check vs harmful self-sealing

Two categories of "agent checks artifact it created":

1. **Benign self-check**: Task creates file X (the deliverable), verification confirms X exists and has correct content. The task's purpose IS to create X. Example: "Create `requirements/observability.md` — verify file exists with required sections." This is post-write validation of the intended deliverable.

2. **Harmful self-sealing**: Task is supposed to verify condition Y, so it writes an artifact claiming Y is true, then checks for the artifact. The artifact is not the deliverable — it is manufactured evidence. The `req1_verified` event was exactly this.

The enforcement mechanism must distinguish these cases. Principle: **verification evidence must be observable state that the executing agent did not create for the purpose of satisfying verification**.

### Files that will change

| File | Change | Purpose |
|------|--------|---------|
| `skills/lifecycle/references/plan.md` | Add Prohibited item + Constraints row | Convention at plan-authoring time |
| `skills/lifecycle/references/orchestrator-review.md` | Add P7 checklist item | Enforcement at plan-review time |
| `skills/lifecycle/references/implement.md` | Add builder guardrail instruction | Backstop at implementation time |
| `claude/overnight/prompts/orchestrator-round.md` | Inline prohibition in Step 3b prompt | Close overnight plan-generation gap |

### Existing patterns to build on

- **Plan Prohibited list** (`plan.md` lines 56-65): already prohibits function bodies, import statements, prose-only verification. A new item fits naturally.
- **Orchestrator review Post-Plan Checklist** (`orchestrator-review.md` lines 148-157): P1-P6 evaluate plan quality before user approval. P7 would follow the same `| P# | Item | Criteria |` table format.
- **Ticket 019** (tighten-spec-template-and-plan-verification-requirements): already enforced binary-checkable verification (a/b/c format). Orthogonal — ensures verification steps are runnable and binary, but does not address who runs them or who wrote the checked artifact.
- **Provenance concept**: `extract_spec_section()` in `claude/overnight/plan.py` writes provenance headers on extracted specs. The concept exists for spec extraction but not for verification evidence.
- **Commit-existence check** (`batch_runner.py` lines 1251-1272): the one existing gate that cannot be self-sealed — checks whether a completed feature produced actual git commits. Only checks existence, not correctness.

### Integration points

1. **Plan authoring flow**: `plan.md` reference is read at plan-write time by both the interactive lifecycle skill and competing-plan sub-agents. Changes propagate to all new interactive plans.
2. **Orchestrator review**: Post-Plan Checklist is a hard gate between plan authoring and user approval.
3. **Overnight plan generation gap**: Step 3b of `orchestrator-round.md` dispatches sub-agents to write plans. The sub-agent receives a verbatim prompt — it does NOT read `plan.md` reference file. The Prohibited list must be inlined in the Step 3b prompt to propagate to overnight-generated plans.
4. **Builder dispatch**: `implement.md` tells agents to verify via the Verification field. If a verification step is self-sealing, this instruction directly causes the false positive.

### Pipeline trust model finding

The `verification_passed` field in builder exit reports is **never read by any Python code**. `_read_exit_report()` in `batch_runner.py` extracts only `action`, `reason`, and `question`. An agent can report `verification_passed: false` and the pipeline will still mark the task complete if `action == "complete"`. The exit report mechanism is architecturally identical to the `req1_verified` event — the agent writes evidence, the pipeline reads it — except exit reports are a designed protocol element. This is an accepted architectural property, not a bug to fix in this ticket.

## Web Research

### Generator/Evaluator separation (prior art)

- **Planner-Generator-Evaluator (PGE)** pattern: divides work into three roles with enforced separation. Key mechanism: prompt isolation and independent context windows prevent context contamination.
- **Google's Generator-Critic pattern**: separate critic agent evaluates against predefined criteria. Positioned for "tasks where outputs must conform to strict constraints."
- **Agent-as-a-Judge** (arXiv): judge agents can "independently verify the agent's result by executing code or querying databases." Using different base models reduces familiarity bias.

### Self-evaluation bias (empirical evidence)

- **Self-Attribution Bias** (arXiv 2603.04582, March 2026): models rate their own outputs as "safer and more correct than identical actions presented under neutral attribution." Self-attribution bias makes monitors **5x more likely to approve** their own outputs. Proposed mitigations: avoid self-attributing prompt formats, pull actions into fresh contexts for evaluation.
- **"Self-congratulation machine"**: having an AI verify its own work "verifies its own assumptions rather than user intent." Memory feedback loops compound: agent writes positive state, next iteration reads it and reinforces false confidence.

### Supply chain provenance patterns

- **SLSA**: the entity that builds must not be the entity that signs provenance. Ephemeral build environments, isolated signing infrastructure, and cryptographic attestations enforce separation.
- **Maker-checker (four-eyes) principle**: "a maker cannot call the approve endpoint for their own request." Enforcement is at the API level, not the convention level.
- **Tautological testing**: a well-documented anti-pattern where tests mirror the implementation. Applied to agents: checking an artifact you just wrote tests your ability to write files, not the correctness of the work.

## Requirements & Constraints

### Architectural constraints that apply

- **File-based state** (`requirements/project.md`): no database or server. Enforcement must work within files.
- **No agent self-spawning** (`requirements/multi-agent.md`): only the orchestrator dispatches agents. A verification agent would need orchestrator dispatch.
- **Repair attempt caps fixed** (`requirements/pipeline.md`): max 2 attempts for test failures, single Sonnet→Opus escalation for merge conflicts. Any added verification dispatch must coexist with these budgets.
- **Simplicity** (`requirements/project.md`): "Complexity must earn its place by solving a real problem that exists now. When in doubt, the simpler solution is correct."

### Existing verification patterns to build on

- **Smoke test gate** (`smoke_test.py`): external code, not agent-generated evidence.
- **SHA comparison circuit breaker**: `before_sha == after_sha` detection. Objective state comparison.
- **Read-only observability subsystems** (`requirements/observability.md`): "All three subsystems are read-only with respect to session state files." Strong precedent for separation of read/write roles.
- **Test gates after conflict resolution**: code-based checks, not agent self-reports.

### Scope boundaries

- Handoff readiness requires "success criteria verifiable by an agent with zero prior context" — but does not specify which agent performs verification.
- No requirements explicitly address verification provenance. This is a gap the feature fills.
- The feature status transition to `merged` is the critical enforcement point.

## Tradeoffs & Alternatives

### Approaches evaluated

| Approach | Effort | Catches authoring-time? | Catches runtime? | False positive risk | Verdict |
|----------|--------|------------------------|-------------------|--------------------|---------| 
| A. Lint/validation (static analysis) | M | Yes (obvious cases) | No | High (legitimate self-checks flagged) | Useful first-pass but limited by static analysis gap |
| B. Convention in plan template | S | Yes (if followed) | No | None | Necessary but not sufficient — no enforcement |
| C. Review checklist item | S | No (post-implementation) | No | Low | Wrong primary enforcement point — too late |
| D. Runtime plan parser rejection | M | No | Yes (dispatch-time) | High (harsh rejection from heuristics) | Sound mechanism, fragile implementation |
| E. Post-execution cross-check | M | No | Yes | Low | Solves different problem (agent lying) not fundamental self-sealing |
| F. Separate verifier agent | L | No | Yes | Medium | Overkill — doubles per-task token cost |
| G. Provenance-tracked artifacts | L | No | Yes | Low | Architecturally elegant, over-engineered for the failure mode |
| **H. Hybrid: Convention + P7 + Builder guardrail** | **S** | **Yes** | **Partial (builder backstop)** | **Low** | **Recommended** |

### Recommended approach: H — Three-layer prompt defense

1. **Convention (authoring time)**: Add Prohibited item to `plan.md`: "Verification steps must not reference artifacts that the executing task creates. Completion evidence must be independently observable."
2. **P7 checklist item (plan review time)**: Add to orchestrator-review Post-Plan Checklist: "No task's Verification field references artifacts that the same task creates in its Files list."
3. **Builder prompt guardrail (implementation time)**: Add instruction to `implement.md`: "Do not write files solely to satisfy your own verification check. Flag self-sealing verification as a question in your exit report."
4. **Overnight gap closure**: Inline the Prohibited items in `orchestrator-round.md` Step 3b prompt so overnight-generated plans inherit the convention.

All four changes are prompt/documentation edits. No new Python code, no parser changes, no new subsystems. Proportional to a personal tooling project where the failure mode was observed once.

## Adversarial Review

### The benign/harmful distinction is unreliable for LLM evaluation

The distinction between "task creates deliverable file, verification confirms content" (benign) and "task writes manufactured evidence" (harmful) collapses at the boundary. Consider: "Check that `lifecycle/{feature}/events.log` contains a `phase_transition` event" — the task might append this event as protocol, not manufactured evidence. An LLM evaluating P7 cannot easily distinguish "protocol-mandated state write" from "manufactured evidence write" without deep context. The P7 checklist item must be specific enough to give the LLM a mechanical check rather than a judgment call.

### The three-layer approach has a category mismatch

P7 evaluates plan text (static analysis). Self-sealing is a runtime behavior problem. A builder agent can deviate from the plan and write its own evidence at runtime. A builder agent can write `verification_passed: true` without running the verification command. P7 catches self-sealing **in the plan**, not self-sealing **in execution**.

### Overnight plan generation is the highest-risk surface

Step 3b sub-agents receive a verbatim prompt string and do NOT read `plan.md` reference. These plans are generated overnight with no human review. Adding the convention to plan.md alone does not propagate to this path. The prohibition must be inlined in the Step 3b prompt.

### `verification_passed` is dead code

The field is collected by every builder agent but never read by any Python code. Exit reports feed completion decisions via the `action` field only. Whether to fix this is a separate decision, but the research should acknowledge that the primary trust surface (exit report → task completion) is already self-sealing by design.

### "Only one confirmed instance" understates the exposure

The search covered existing lifecycle plan files. Overnight-generated plans (Step 3b) are not preserved in the lifecycle directory after execution. Self-sealing in those plans would pass undetected. Simple-tier/low-criticality features skip both orchestrator review and critical review, so self-sealing in simple features has zero detection surface today.

### Simpler runtime options were dismissed prematurely

Two lightweight runtime options were overlooked by the tradeoffs analysis:
1. **Read `verification_passed` from exit reports** (~10 lines of Python): if false but action is "complete", log a warning or pause.
2. **Post-task verification re-execution**: parse the plan's Verification field command and re-run it independently after the builder exits. The plan parser already extracts task fields. The merge gate already runs `test_command`. Running one more command is marginal.

Neither requires new agents, new state files, or architectural changes.

### Recommended adversarial mitigations

1. Make P7 specific and mechanical: "Does any task's Verification field reference a file or log entry that the same task's Files/What field creates? If yes, is the referenced content a deliverable or manufactured evidence?"
2. Inline Prohibited items in Step 3b prompt (not optional — this is the highest-risk surface).
3. Consider reading `verification_passed` as a future hardening step (separate ticket).
4. Acknowledge exit report self-sealing as an accepted architectural property, not something this ticket fixes.

## Open Questions

- Should `verification_passed` in exit reports be read and acted on? This is a ~10-line Python change that addresses a broader trust gap than plan-level self-sealing. It may warrant its own ticket rather than being folded into this one.
- The P7 checklist item relies on LLM judgment to distinguish benign self-checks from harmful self-sealing. How reliable is this in practice? The answer is empirical — it depends on how specific the checklist item is and how often the boundary case arises.
