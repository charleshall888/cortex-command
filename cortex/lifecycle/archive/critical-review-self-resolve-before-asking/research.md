# Research: critical-review-self-resolve-before-asking

## Codebase Analysis

### Current Step 4 Framework

Critical Review's Step 4 (Apply Feedback) has three dispositions:

- **Apply**: Fix is clear and unambiguous — fix without asking
- **Dismiss**: Objection already addressed, misreads constraints, or expands scope — state reason briefly. Anchor check: if dismissal reason lives only in conversation memory (not pointable-to in artifact text), treat as Ask instead.
- **Ask**: Not for orchestrator to decide unilaterally — (a) preference/scope decisions, (b) genuine uncertainty, (c) consequential tie-breaks

**Apply bar**: "Apply when and only when the fix is unambiguous and confidence is high. Uncertainty is a legitimate reason to Ask — do not guess and apply. For inconsequential tie-breaks, pick one and apply. For consequential tie-breaks, Ask."

Step 4 runs in the **main orchestrator context** — the same anchored context that produced the artifact. The `consolidate-devils-advocate-critical-review` research flagged this as a known limitation: anchoring bias from the generation context bleeds into disposition decisions.

### Affected Files

1. **`skills/critical-review/SKILL.md`** — primary change target (Step 4, lines 176–193)
2. **`skills/lifecycle/references/clarify-critic.md`** — downstream dependent. Lines 60–68 reproduce the disposition framework verbatim with comment: "Apply/Dismiss/Ask framework below matches `/critical-review` Step 4 — reproduced here to avoid silent drift." Requires parallel update.

### Callsites (3 execution paths)

| Callsite | File | Artifact | Gate |
|----------|------|----------|------|
| Spec review | `skills/lifecycle/references/specify.md:144` | `spec.md` | Complex tier only |
| Plan review | `skills/lifecycle/references/plan.md:237` | `plan.md` | Complex tier only |
| Discovery research | `skills/discovery/references/research.md:128` | `research.md` | Unconditional |

All callsites invoke the skill and rely on SKILL.md's Step 4 prose — no callsite defines its own disposition logic. Changing Step 4 affects all three identically.

### Existing "Try Before Asking" Precedents

**1. Overnight Orchestrator Step 0 (strongest analog)**
`claude/overnight/prompts/orchestrator-round.md` — reads spec/plan context, attempts to answer worker escalations before creating deferrals. If resolvable: writes `orchestrator-note.md`. If not: writes deferral for morning review. Cycle-breaker: if same question recurs, skips to deferral.

**2. Orchestrator Review (fix before presenting)**
`skills/lifecycle/references/orchestrator-review.md` — checks artifact against checklist, dispatches fix agents (up to 2 cycles), only escalates to user when fixes fail.

**3. Clarify Critic (resolve then merge)**
`skills/lifecycle/references/clarify-critic.md` — fresh critic challenges assessment, Apply fixes are incorporated automatically, remaining Ask items fold into consolidated Q&A. Explicit "resolve what you can, then ask about only what you can't."

**4. Diagnose skill (team investigation before escalation)**
`skills/diagnose/SKILL.md:190-241` — after 3+ failed fixes, spawns parallel investigator agents, finds convergence, then escalates to user with synthesized findings.

### Overnight Gap

Critical-review has **no overnight awareness**. When running during overnight (spec/plan gate on complex features), Ask items have nowhere to go — the skill "holds for a consolidated message" to a human who isn't present. The overnight escalation infrastructure exists in the runner but critical-review does not hook into it.

### Historical Ask Patterns

From clarify-critic events (best proxy — critical-review Step 4 doesn't log Ask items):

1. Format/output channel decisions ("never specifies format")
2. Integration pattern decisions ("new skill vs. morning-review integration")
3. Ambiguous source material scope (narrow vs. broad reading)
4. Unresolved dependencies on other tickets
5. Contradiction detection semantics
6. Architectural constraint application

**Pattern**: Every historical Ask item is a genuine preference/design question — "which of two valid approaches?" or "what does this ambiguous thing mean?" None are resolvable by reading more files or reasoning harder. They are true human decisions. This is important: it suggests the current Ask bar is already well-calibrated and most Ask items are genuinely unresolvable by the agent alone.

## Web Research

### Anthropic Evaluator Pattern (referenced article)

Key insights from "Harness Design for Long-Running Agentic Applications":

**Separation of generation and evaluation**: "Tuning a standalone evaluator to be skeptical turns out to be far more tractable than making a generator critical of its own work." Evaluators work better as fresh agents without anchoring to the generation context.

**Explicit rubrics**: Evaluation criteria must be specific, gradable, and have hard thresholds. Vague criteria produce vague judgments. Each criterion had "a hard threshold, and if any one fell below it, the sprint failed."

**Calibration through iteration**: "The tuning loop was to read the evaluator's logs, find examples where its judgment diverged from mine, and update the QA's prompt to solve for those issues." Self-resolution quality improves through observed failure → prompt revision cycles.

**Pre-execution contracts**: Before building, generator and evaluator negotiate a "sprint contract" agreeing on what done looks like. This front-loads ambiguity resolution.

**File-based communication**: Multi-agent systems use files for state, not message passing. Persistence creates clarity about transitions.

**Relevant tension**: The article's evaluator pattern is about grading completed work against criteria, not about resolving ambiguous questions. The pattern that most closely maps to self-resolution is the **sprint contract negotiation** — agents attempting to resolve ambiguities by reasoning from existing artifacts before executing.

## Open Questions

- ~~Should the self-resolution step run in a fresh agent (avoiding anchoring, consistent with the skill's reviewer design) or inline in the orchestrator context (simpler, but anchored)?~~
  **Resolved: use a fresh agent.** Three evidence points: (1) critical-review already dispatches fresh agents for each reviewer angle specifically to avoid anchoring — inline resolution would be inconsistent with the skill's own design; (2) the `consolidate-devils-advocate` research flagged anchoring bias in Step 4 (main orchestrator context) as a known limitation, so inline resolution would compound the problem this feature is trying to solve; (3) the referenced Anthropic article states "tuning a standalone evaluator to be skeptical turns out to be far more tractable than making a generator critical of its own work," which directly supports a fresh, context-isolated agent for the self-resolution step.
