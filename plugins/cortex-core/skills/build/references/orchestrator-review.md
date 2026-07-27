# Orchestrator Phase Review

Quality gate: nothing reaches the user until the artifact passes its checklist or hits the cycle cap.

**Skip** when criticality is `low` AND tier is `simple` — proceed directly to user presentation, logging no orchestrator events. Run for all other combinations. Use the tier and criticality already carried into this context; fall back to `cortex-lifecycle-state --feature {feature}` (defaults `medium`/`simple` when a key is absent) only if they never reached it. On `"corrupted": true`, apply the canonical rule in SKILL.md § Criticality — treat the feature as requiring review.

## 1. Execute

Rate every item in the phase checklist — Post-Specify (`spec.md`) or Post-Plan (`plan.md`) — **pass** or **flag**, individually rather than as a gestalt. Flag anything unsatisfied or materially weak, minor issues included; a flag requires a fix before user presentation. Run in the main conversation; the artifact is already in context, so no subagent.

**Binary-checkable** (checklist items S1 and P4) means one of: (a) a runnable command with observable output and pass/fail; (b) an observable state naming the file path, the string or pattern, and the expected true/false; (c) `Interactive/session-dependent: [one-sentence rationale]` when neither applies.

## 2. Handle the verdict

**Pass** → show a one-line assessment ("Spec clean, criteria measurable") and proceed. **Flag** → cycle 3 or beyond goes to Escalation; otherwise Fix Dispatch.

## 3. Fix dispatch

The orchestrator does not edit phase artifacts directly — dispatching preserves separation of concerns and creates an audit trail.

Rework needing no user input → a **fresh subagent**, which avoids anchoring to the flawed artifact. Brief it with the flagged checklist item and what is wrong, the artifact path to read, and the phase's format requirements. It must **rewrite the entire artifact** to address the flag while preserving all correct existing content — never patch sections — and add nothing beyond what the phase requires. It ends with this envelope and no prose around it:

```
verdict: revised | failed
files_changed: [<path>, ...]
rationale: <≤15 words>
```


Rework needing user input (preference decides) → explain the issue, gather input, revise in place.

After all fixes, increment the cycle counter and return to §1 with the same checklist; relay only the re-review verdict from the envelope.

## 4. Escalation

Max **2 review cycles per phase** (counter resets each phase; never start cycle 3) — more iteration rounds decrease quality, not increase it. At the cap with an issue persisting, stop and present what was checked, what was tried per cycle, and what's unresolved. The user decides; do not continue reviewing.
