# Orchestrator Phase Review

Quality gate between phase artifact write and user presentation. The orchestrator reviews the artifact against phase-specific checklists, dispatches fixes for flagged issues, and only surfaces the artifact to the user once it passes or the cycle cap is reached.

## Applicability

Before running this protocol, determine whether orchestrator review applies. Read `lifecycle/{feature}/events.log` and find the most recent `lifecycle_start` or `criticality_override` event. Extract `criticality` and `tier` from that event. If no such event exists, default to `criticality: medium`.

**Skip rule**: Skip orchestrator review when criticality is `low` AND tier is `simple`. Proceed directly to user presentation or the next phase.

**Run rule**: Run orchestrator review for all other combinations:

| Criticality | simple | complex |
|-------------|--------|---------|
| low         | skip   | review  |
| medium      | review | review  |
| high        | review | review  |
| critical    | review | review  |

If the review is skipped, do not log any orchestrator events. Proceed as if the protocol were not present.

## Protocol

### 1. Identify Phase and Checklist

Determine which phase just completed and select the corresponding checklist below.

### 2. Execute Review

Evaluate the artifact against every item in the checklist. For each item, assign a verdict:

- **pass**: The item is satisfied. No action needed.
- **flag**: The item is not satisfied or is materially weak. Requires a fix before user presentation.

This review executes in the main conversation context. Do not dispatch a subagent for the review itself — the artifact is already in context.

### 3. Log Review

Append an `orchestrator_review` event to `lifecycle/{feature}/events.log`:

```
{"ts": "<ISO 8601>", "event": "orchestrator_review", "feature": "<name>", "phase": "research|specify|plan", "verdict": "pass|flag", "cycle": <N>, "issues": ["<description of each flagged item>"]}
```

The `verdict` is `pass` if all items passed, `flag` if any item was flagged. The `issues` array is empty on pass.

### 4. Handle Verdict

**On pass**: Show the user a one-line assessment summarizing what was checked and the result. Example formats:

- "Research solid: all 4 questions answered with concrete findings, feasibility grounded in codebase analysis."
- "Spec clean: 6 requirements with measurable criteria, edge cases covered, scope boundaries explicit."
- "Plan well-structured: 8 tasks averaging 10 min each, dependency graph complete, all verification steps actionable."

Then proceed to user presentation or the next phase as normal.

**On flag**: Check the cycle counter. If this is cycle 3 or beyond, go to Escalation (step 6). Otherwise, proceed to Fix Dispatch (step 5).

### 5. Fix Dispatch

For each flagged issue, determine the appropriate fix mode:

**Fresh subagent** (via Task tool): Use for thinking-quality rework that does not require user input. This includes research depth issues, plan restructuring, feasibility re-assessment, missing edge cases, vague acceptance criteria, and similar structural problems. Fresh context prevents anchoring to the flawed artifact.

**Model for fresh subagent fixes**: `sonnet` for low/medium/high criticality, `opus` for critical.

**Same conversation**: Use for interactive rework that requires user input. This includes spec clarifications where user preference determines the answer, ambiguous requirements, and priority trade-offs. Explain the issue to the user, gather their input, and then revise the artifact in the current context.

For each dispatched fix, append an `orchestrator_dispatch_fix` event to `lifecycle/{feature}/events.log`:

```
{"ts": "<ISO 8601>", "event": "orchestrator_dispatch_fix", "feature": "<name>", "phase": "research|specify|plan", "mode": "fresh_subagent|same_context", "issue": "<description of the flagged item>"}
```

Fix agents rewrite the full artifact, not section patches. A full rewrite maintains internal coherence across sections that cross-reference each other.

After all fixes complete, return to step 2 (Execute Review) and increment the cycle counter. The re-review evaluates the revised artifact against the same checklist.

#### Fix Agent Prompt Template

```
You are fixing a flagged issue in the {phase} artifact for the {feature} feature.

## Issue
{description of the flagged checklist item and what is wrong}

## Current Artifact
Read lifecycle/{feature}/{artifact} for the current content.

## Phase-Specific Checklist
{paste the relevant checklist from the Checklists section below}

## Instructions
1. Read the current artifact fully
2. Rewrite the ENTIRE artifact to address the flagged issue while maintaining all existing content that is correct
3. Do not patch individual sections — rewrite the full file to maintain internal coherence
4. Write the revised artifact to lifecycle/{feature}/{artifact}
5. Report what you changed and why

The artifact must still conform to the format defined in the {phase} phase reference.
Do not add content beyond what the phase requires.
```

### 6. Escalation

When the cycle cap is reached (2 cycles completed, issue persists), stop reviewing and escalate to the user. Present:

- What was checked (the flagged checklist items)
- What was tried (fixes dispatched in each cycle)
- What remains unresolved (items still flagged after 2 cycles)

Append an `orchestrator_escalate` event to `lifecycle/{feature}/events.log`:

```
{"ts": "<ISO 8601>", "event": "orchestrator_escalate", "feature": "<name>", "phase": "research|specify|plan", "reason": "<summary of unresolved issues>", "cycles": <N>}
```

After escalation, the user decides how to proceed. Do not continue reviewing.

## Checklists

### Post-Research Checklist

Evaluate against `lifecycle/{feature}/research.md`:

| # | Item | Criteria |
|---|------|----------|
| R1 | Research questions answered concretely | Each question in the Codebase Analysis and Web Research sections has a specific finding, not a hand-wavy generalization |
| R2 | Feasibility grounded in evidence | Feasibility assessment cites specific codebase patterns, API capabilities, or documented behavior — not just "this should be possible" |
| R3 | Critical unknowns addressed | No critical unknowns are left unacknowledged; if unresolvable, they appear in Open Questions with explanation of why they could not be resolved |
| R4 | Open questions are genuine | Items in Open Questions represent true unknowns that require user input or cannot be resolved through further research, not lazily deferred work |
| R5 | Dependency verification complete | If external dependencies exist, the Dependency Verification section confirms specific capabilities (endpoints, methods, flags) are present and not deprecated |

### Post-Specify Checklist

Evaluate against `lifecycle/{feature}/spec.md`:

| # | Item | Criteria |
|---|------|----------|
| S1 | Measurable acceptance criteria | Every requirement has acceptance criteria that can be objectively evaluated as met or not met — no subjective language like "should be fast" or "user-friendly" |
| S2 | Edge cases identified and handled | Edge Cases section covers failure modes, unexpected inputs, boundary conditions, and concurrent scenarios relevant to the feature |
| S3 | MoSCoW classification justified | Must-have vs should-have vs won't-do distinctions are explicit, and the classification reflects actual priority rather than "everything is must-have" |
| S4 | Non-requirements are explicit boundaries | Non-Requirements section defines concrete scope boundaries, not vague statements like "not in scope for now" |
| S5 | Technical constraints grounded | Technical Constraints section references specific codebase patterns, ADRs, or architectural decisions — not generic best practices |

### Post-Plan Checklist

Evaluate against `lifecycle/{feature}/plan.md`:

| # | Item | Criteria |
|---|------|----------|
| P1 | Task sizing within bounds | Each task targets 5-15 minutes and 1-5 files; tasks outside this range are flagged |
| P2 | Dependency graph complete | Every task has a `**Depends on**` field; no missing edges where one task's output is another's input |
| P3 | Structural context sufficient | Each task's Context field provides enough information (file paths, function signatures, pattern references) for a fresh subagent to execute without reading unrelated files |
| P4 | Verification steps actionable | Each task's Verification field describes concrete steps to confirm success, not vague "verify it works" |
| P5 | Code budget respected | Plan contains prose and structural context only — no function bodies, import statements, or copy-paste-ready code |
| P6 | Files/Verification consistency | Every file implied by Verification is listed in Files; no verification step requires modifying unlisted files |

## Cycle Cap

The orchestrator runs a maximum of 2 review cycles per phase. A cycle is one complete pass through the checklist. The counter resets for each new phase.

- **Cycle 1**: Initial review after artifact is written.
- **Cycle 2**: Re-review after fix dispatch. If issues remain after cycle 2, escalate.

Do not start cycle 3. Escalate with full context per step 6.

## Constraints

| Thought | Reality |
|---------|---------|
| "The artifact looks mostly fine, I'll pass it through" | Evaluate every checklist item individually. Gestalt impressions miss specific gaps. A single unflagged issue becomes the user's problem. |
| "I can fix this issue myself instead of dispatching" | The orchestrator does not edit phase artifacts directly. Dispatching fixes preserves separation of concerns and creates an audit trail via event logging. |
| "This issue is minor, not worth a fix cycle" | Flag it. The fix agent may resolve it quickly. Letting minor issues pass compounds across phases — a vague spec item becomes a broken plan task becomes a failed implementation. |
| "The fix made things worse, I should try a third cycle" | The 2-cycle cap is firm. Escalate to the user. More iteration rounds decrease quality, not increase it. |
| "Criticality is low so I should skip even for complex features" | The skip rule requires BOTH low criticality AND simple complexity. Low-criticality complex features still get reviewed. |
