# Orchestrator Phase Review

Quality gate between phase artifact write and user presentation. The orchestrator reviews the artifact against phase-specific checklists, dispatches fixes for flagged issues, and only surfaces the artifact to the user once it passes or the cycle cap is reached.

Discovery has no applicability skip rule — orchestrator review always runs for every discovery topic regardless of complexity or criticality.

## Protocol

### 1. Identify Phase and Checklist

Determine which phase just completed and select the corresponding checklist below.

### 2. Execute Review

Evaluate the artifact against every item in the checklist. For each item, assign a verdict:

- **pass**: The item is satisfied. No action needed.
- **flag**: The item is not satisfied or is materially weak. Requires a fix before user presentation.

This review executes in the main conversation context. Do not dispatch a subagent for the review itself — the artifact is already in context.

### 3. Handle Verdict

**On pass**: Show the user a one-line assessment summarizing what was checked and the result. Example formats:

- "Research solid: all questions answered with concrete findings, feasibility grounded in codebase analysis."

Then proceed to user presentation or the next phase as normal.

**On flag**: Check the cycle counter. If this is cycle 3 or beyond, go to Escalation (step 5). Otherwise, proceed to Fix Dispatch (step 4).

### 4. Fix Dispatch

For each flagged issue, determine the appropriate fix mode:

**Fresh subagent** (via Task tool): Use for thinking-quality rework that does not require user input. This includes research depth issues, feasibility re-assessment, missing edge cases, vague acceptance criteria, and similar structural problems. Fresh context prevents anchoring to the flawed artifact.

**Same conversation**: Use for interactive rework that requires user input. This includes clarifications where user preference determines the answer, ambiguous research scope, and priority trade-offs. Explain the issue to the user, gather their input, and then revise the artifact in the current context.

Fix agents rewrite the full artifact, not section patches. A full rewrite maintains internal coherence across sections that cross-reference each other.

After all fixes complete, return to step 2 (Execute Review) and increment the cycle counter. The re-review evaluates the revised artifact against the same checklist.

#### Fix Agent Prompt Template

```
You are fixing a flagged issue in the {phase} artifact for the {topic} discovery topic.

## Issue
{description of the flagged checklist item and what is wrong}

## Current Artifact
Read cortex/research/{topic}/{artifact} for the current content.

## Phase-Specific Checklist
{paste the relevant checklist from the Checklists section below}

## Instructions
1. Read the current artifact fully
2. Rewrite the ENTIRE artifact to address the flagged issue while maintaining all existing content that is correct
3. Do not patch individual sections — rewrite the full file to maintain internal coherence
4. Write the revised artifact to cortex/research/{topic}/{artifact}
5. Report: what you changed and why. Format: changed [file path] — [one-sentence rationale].

The artifact must still conform to the format defined in the {phase} phase reference.
Do not add content beyond what the phase requires.
```

### 5. Escalation

When the cycle cap is reached (2 cycles completed, issue persists), stop reviewing and escalate to the user. Present:

- What was checked (the flagged checklist items)
- What was tried (fixes dispatched in each cycle)
- What remains unresolved (items still flagged after 2 cycles)

After escalation, the user decides how to proceed. Do not continue reviewing.

## Checklists

### Post-Research Checklist

Evaluate against `cortex/research/{topic}/research.md`:

| # | Item | Criteria |
|---|------|----------|
| R1 | Research questions answered concretely | Each question in the Codebase Analysis and Web Research sections has a specific finding, not a hand-wavy generalization |
| R2 | Feasibility grounded in evidence | Feasibility assessment cites specific codebase patterns, API capabilities, or documented behavior — not just "this should be possible" |
| R3 | Critical unknowns addressed | No critical unknowns are left unacknowledged; if unresolvable, they appear in Open Questions with explanation of why they could not be resolved |
| R4 | Open questions are genuine | Items in Open Questions represent true unknowns that require user input for decomposition choices, or questions that could not be resolved through research (with an explanation of why). Research feeds directly into Decompose — questions that could have been answered through more investigation are not acceptable deferrals. |
| R5 | Dependency verification complete | If external dependencies exist, the Web & Documentation Research section confirms specific capabilities (endpoints, methods, flags) are present and not deprecated |

## Cycle Cap

The orchestrator runs a maximum of 2 review cycles per phase. A cycle is one complete pass through the checklist. The counter resets for each new phase.

- **Cycle 1**: Initial review after artifact is written.
- **Cycle 2**: Re-review after fix dispatch. If issues remain after cycle 2, escalate.

Do not start cycle 3. Escalate with full context per step 5.

## Constraints

| Thought | Reality |
|---------|---------|
| "The artifact looks mostly fine, I'll pass it through" | Evaluate every checklist item individually. Gestalt impressions miss specific gaps. A single unflagged issue becomes the user's problem. |
| "I can fix this issue myself instead of dispatching" | The orchestrator does not edit phase artifacts directly. Dispatching fixes preserves separation of concerns and creates an audit trail via event logging. |
| "This issue is minor, not worth a fix cycle" | Flag it. The fix agent may resolve it quickly. Letting minor issues pass compounds across phases — a weak research finding becomes a poorly-prioritized backlog ticket becomes a failed implementation. |
| "The fix made things worse, I should try a third cycle" | The 2-cycle cap is firm. Escalate to the user. More iteration rounds decrease quality, not increase it. |
