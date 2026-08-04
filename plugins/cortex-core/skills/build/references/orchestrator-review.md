# Orchestrator Phase Review

Quality gate: nothing reaches the user before passing review or hitting the cycle cap.

**Skip** when criticality is `low` AND tier is `simple` — go straight to user presentation, logging no orchestrator events; run for every other combination. Use the tier and criticality already in context, falling back to `cortex-lifecycle-state --feature {feature}` (defaults `medium`/`simple` when absent) only if unreached. On `"corrupted": true`, apply SKILL.md § Criticality's canonical rule: treat the feature as requiring review.

## 1. Execute

Rate the artifact against the phase reference's authoring rules. Take each separately, **pass** or **flag**, never as a gestalt; an unreached, unsatisfied, or materially weak rule is a flag, minor issues included. A flag requires a fix before user presentation. Run in the main conversation — the artifact is already in context, so no subagent.

**Binary-checkable** means one of: (a) a runnable command with observable output and pass/fail; (b) an observable state naming the file path, the string or pattern, and the expected true/false; (c) `Interactive/session-dependent: [one-sentence rationale]` when neither applies.

## 2. Handle the verdict

**Pass** → show a one-line assessment (e.g. "Spec clean, criteria measurable") and proceed. **Flag** → Escalation at cycle 3+, else Fix Dispatch.

## 3. Fix dispatch

The orchestrator does not edit phase artifacts directly — dispatching preserves separation of concerns.

Rework needing no user input → a **fresh subagent** takes every repair, avoiding anchoring to the flawed artifact; briefed with the flagged rule, what's wrong, the artifact path, and format requirements. Flags confined to a single requirement get a targeted edit to that requirement; flags spanning more than one, or the artifact's cross-references, get a full rewrite to keep cross-referencing sections coherent. If a targeted edit proves not confinable, it reports `verdict: failed` rather than an inconsistent patch. Ends with this envelope, no prose:

```
verdict: revised | failed
files_changed: [<path>, ...]
changed_beyond_flag: <none | ≤15-word summary>
rationale: <≤15 words>
```

Rework needing user input (preference decides) → explain the issue, gather input, revise in place.

After all fixes, increment the cycle counter and return to §1 with the same rules; relay only the re-review verdict.

## 4. Escalation

Max **2 review cycles per phase** (counter resets each phase; never start cycle 3) — more iteration rounds decrease quality, not increase it. At the cap with an issue persisting, stop and present what was checked, what was tried per cycle, and what's unresolved. The user decides; do not continue reviewing.
