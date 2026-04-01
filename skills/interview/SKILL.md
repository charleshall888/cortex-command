---
name: interview
description: 'Interview the user about their plan to surface gaps and refine requirements. Use when: (1) user says "interview me" or "ask me questions about the plan", (2) user has written a plan and wants validation, (3) before implementing a complex feature that needs clarification.'
inputs:
  - "plan-path: string (optional) — path to plan file (e.g. lifecycle/{feature}/plan.md); if omitted, the skill locates it or asks"
outputs:
  - "refined spec or summary written to conversation (no file written unless user requests)"
  - "unanswered questions and edge cases surfaced in the conversation thread"
preconditions:
  - "A plan or feature description exists to interview against"
  - "Run from project root"
argument-hint: "[plan-path=lifecycle/<feature>/plan.md]"
disable-model-invocation: true
---

# /interview

Ad-hoc plan review through targeted user questioning. Surfaces gaps, unspoken assumptions, and missing requirements in any plan — without requiring an active lifecycle feature. The user answers; the skill synthesizes answers into a refined output.

Plan path (if provided): $ARGUMENTS

## Scope Distinction: /interview vs. /refine Clarify Phase

These serve different contexts and are not interchangeable:

- **/interview** — ad-hoc, on-demand plan review. Use it any time a plan exists and the user wants to pressure-test it through questions. Not tied to a backlog item or lifecycle. The output is a conversation-level summary or spec, not a lifecycle artifact.
- **/refine Clarify phase** — structured intent gate that runs before Research in the lifecycle pipeline. It asks ≤5 targeted questions to confirm scope and complexity, align with `requirements/`, and aim research. It is bounded (≤5 questions, specific purpose), feeds directly into Research and Spec, and writes back to lifecycle artifacts.

Use `/interview` for exploratory, open-ended plan review outside the lifecycle. Use `/refine` (and its Clarify phase) to prepare a backlog item for overnight execution.

## Step 1: Locate the Plan

If `$ARGUMENTS` contains a `plan-path`, use it. Otherwise:

1. Check `lifecycle/*/plan.md` for recently modified files — present any candidates to the user.
2. If no plan file is found, ask the user to provide the path or paste the plan content.

Read the full plan before generating any questions.

## Step 2: Map Question Areas

After reading the plan, identify coverage gaps across these areas. Not all areas will apply to every plan — only ask about areas where the plan is thin or silent.

**Technical implementation**
- How will X interact with Y?
- What library or approach handles Z?
- Where does this code live and how does it get called?

**UI/UX decisions** (if applicable)
- What does the user see when the happy path succeeds?
- What does the user see when an error occurs?
- Is any new UI needed, or is this purely backend?

**Edge cases and error handling**
- What happens when input is empty, malformed, or outside expected range?
- What is the recovery path if a downstream service fails?
- Are there concurrent access or race condition concerns?

**Trade-offs and alternatives**
- Was a simpler approach considered and rejected? Why?
- Is this the minimal implementation that solves the problem?
- What is the cost of the chosen approach compared to alternatives?

**Security and performance**
- Is any user-supplied data involved? How is it sanitized or validated?
- Are there latency or throughput constraints this plan must respect?
- Does this introduce new attack surface (auth, file access, network calls)?

**Scope and completeness**
- Are there adjacent features this touches that are out of scope?
- What is the explicit stopping point for this implementation?
- What must be true for this to be "done"?

## Step 3: Volume and Sequencing

Ask questions using the AskUserQuestion tool. Apply these volume guidelines:

- **Baseline**: 3–5 questions per pass — enough to surface gaps without overwhelming.
- **Simple plans**: 3–4 questions total; stop earlier if gaps are resolved.
- **Complex plans**: up to 8–10 questions across two passes if the first pass reveals new gaps.
- **Do not ask about areas the plan already covers clearly.** If implementation details are present, skip those questions.

Ask the most important questions first. Prioritize questions whose answers would change the design, not just fill in details.

## Step 4: Stopping Condition

Stop asking when one of the following is true:

1. All high-impact gaps are resolved (implementation path is clear, edge cases are addressed, scope is bounded).
2. The user signals they have answered enough ("that's all", "looks good", "proceed").
3. Two full passes of questions have completed without surfacing new material gaps.

Do not continue asking for completeness. Once the plan is unambiguous enough to act on, stop.

## Step 5: Synthesize and Output

After the interview is complete, produce a synthesis in the conversation:

```markdown
## Interview Summary

### Decisions Made
- [Key decision]: [What was confirmed or clarified]
...

### Gaps Resolved
- [Gap]: [Resolution]
...

### Remaining Open Questions
- [Question]: [Why it remains open; who resolves it]
...

### Refined Requirements
1. [Requirement with acceptance criteria]
...
```

If the user requests a file output, write the synthesis to `lifecycle/{feature}/plan.md` only if a lifecycle directory already exists for the feature. Otherwise write it as `plan-refined.md` in the current directory or at a user-specified path.

## Question Quality Rules

- Ask "why" and "what if" questions, not just "what"
- Probe unstated assumptions — if the plan says "use the existing auth system", ask which specific mechanism and how failure is handled
- Identify missing requirements — a plan that says nothing about error states is incomplete
- Challenge optimistic scope — if the plan seems to assume the happy path, ask about failure modes
- One question per bullet; do not bundle multiple questions in a single ask
