# Orchestrator Phase Review

Quality gate: nothing reaches the user until the artifact passes review or hits the cycle cap.

**Skip** when criticality is `low` AND tier is `simple` — proceed directly to user presentation, logging no orchestrator events. Run for all other combinations. Use the tier and criticality already carried into this context; fall back to `cortex-lifecycle-state --feature {feature}` (defaults `medium`/`simple` when a key is absent) only if they never reached it. On `"corrupted": true`, apply the canonical rule in SKILL.md § Criticality — treat the feature as requiring review.

## 1. Execute

Rate the artifact against the authoring rules of the phase reference you just executed. Take each separately, **pass** or **flag**, never as a gestalt; a rule the artifact never reaches is a flag, as is anything unsatisfied or materially weak, minor issues included. A flag requires a fix before user presentation. Run in the main conversation; the artifact is already in context, so no subagent.

**Binary-checkable** means one of: (a) a runnable command with observable output and pass/fail; (b) an observable state naming the file path, the string or pattern, and the expected true/false; (c) `Interactive/session-dependent: [one-sentence rationale]` when neither applies.

## 2. Handle the verdict

**Pass** → show a one-line assessment ("Spec clean, criteria measurable") and proceed. **Flag** → cycle 3 or beyond goes to Escalation; otherwise Fix Dispatch.

## 3. Fix dispatch

The orchestrator does not edit phase artifacts directly — dispatching preserves separation of concerns.

Rework needing no user input → route by blast radius, not by who holds the pen: a **fresh subagent** takes every repair, avoiding anchoring to the flawed artifact. Brief it with the flagged rule, what's wrong, the artifact path, and the phase's format requirements. Flags confined to a single requirement get a targeted edit to that requirement's section; flags spanning more than one requirement, or the artifact's cross-references, get a full rewrite — the only way to keep cross-referencing sections coherent, so never patch several sections piecemeal. If a targeted edit proves not confinable once the subagent is inside the artifact, it reports `verdict: failed` on the envelope below rather than forcing an inconsistent patch. It ends with this envelope and no prose around it:

```
verdict: revised | failed
files_changed: [<path>, ...]
changed_beyond_flag: <none | ≤15-word summary>
rationale: <≤15 words>
```


Rework needing user input (preference decides) → explain the issue, gather input, revise in place.

After all fixes, increment the cycle counter and return to §1 with the same rules; relay only the re-review verdict from the envelope.

## 4. Escalation

Max **2 review cycles per phase** (counter resets each phase; never start cycle 3) — more iteration rounds decrease quality, not increase it. At the cap with an issue persisting, stop and present what was checked, what was tried per cycle, and what's unresolved. The user decides; do not continue reviewing.
