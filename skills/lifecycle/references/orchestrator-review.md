# Orchestrator Phase Review

Quality gate: nothing reaches the user until the artifact passes its checklist or hits the cycle cap.

**Skip** when criticality is `low` AND tier is `simple` — proceed directly to user presentation, logging no orchestrator events. Run for all other combinations. Read both fields with `cortex-lifecycle-state --feature {feature}` (defaults `medium`/`simple` when a key is absent); on `"corrupted": true`, apply the canonical rule in SKILL.md § Criticality — treat the feature as requiring review.

## 1. Execute

Rate every item in the phase checklist — Post-Specify (`spec.md`) or Post-Plan (`plan.md`) — **pass** or **flag**. Flag anything unsatisfied or materially weak; a flag requires a fix before user presentation. Run in the main conversation; the artifact is already in context, so no subagent.

Evaluate every item individually — a gestalt "looks mostly fine" misses specific gaps, and a single unflagged issue becomes the user's problem. Flag minor issues too: the fix agent may resolve one quickly, and letting them pass compounds across phases.

**Binary-checkable** (checklist items S1 and P4) means one of: (a) a runnable command with observable output and pass/fail; (b) an observable state naming the file path, the string or pattern, and the expected true/false; (c) `Interactive/session-dependent: [one-sentence rationale]` when neither applies.

## 2. Handle the verdict

**Pass** → show a one-line assessment ("Spec clean, criteria measurable") and proceed. **Flag** → cycle 3 or beyond goes to Escalation; otherwise Fix Dispatch.

## 3. Fix dispatch

The orchestrator does not edit phase artifacts directly — dispatching preserves separation of concerns and creates an audit trail.

Rework needing no user input → a **fresh subagent**, which avoids anchoring to the flawed artifact:

```bash
model=$(cortex-resolve-model --role orchestrator-fix --criticality "$(cortex-lifecycle-state --feature {feature} --field criticality --raw)")
```

On nonzero exit, halt and escalate. Dispatch with:

```
You are fixing a flagged issue in the {phase} artifact for the {feature} feature.

## Issue
{the flagged checklist item and what is wrong}

## Current Artifact
Read cortex/lifecycle/{feature}/{artifact} for the current content.

## Phase-Specific Checklist
{the relevant checklist}

## Instructions
1. Rewrite the ENTIRE artifact to address the flagged issue, preserving all correct existing content — don't patch sections.
2. Write the revised artifact to cortex/lifecycle/{feature}/{artifact}.
3. End your return with this envelope, no prose before or after it:
   verdict: revised | failed
   files_changed: [<path>, ...]
   rationale: <≤15 words>

The artifact must conform to the {phase} phase reference's format. Do not add content beyond what the phase requires.
```

Rework needing user input (preference decides) → explain the issue, gather input, revise in place.

After all fixes, increment the cycle counter and return to §1 with the same checklist; relay only the re-review verdict from the envelope.

## 4. Escalation

Max **2 review cycles per phase** (counter resets each phase; never start cycle 3) — more iteration rounds decrease quality, not increase it. At the cap with an issue persisting, stop and present what was checked, what was tried per cycle, and what's unresolved. The user decides; do not continue reviewing.
