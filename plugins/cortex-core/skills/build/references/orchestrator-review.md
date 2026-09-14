# Orchestrator Phase Review

Quality gate: nothing reaches the user before passing review or being surfaced as unresolved.

**Skip** when criticality is `low` AND tier is `simple` — go straight to user presentation, logging no orchestrator events; run for every other combination. Use the tier and criticality already in context, falling back to `cortex-lifecycle-state --feature {feature}` (defaults `medium`/`simple` when absent) only if unreached. On `"corrupted": true`, apply SKILL.md § Criticality's canonical rule: treat the feature as requiring review.

## 1. Execute

Check the artifact against the phase reference's authoring rules, each separately, **pass** or **flag**; an unreached, unsatisfied, or materially weak rule is a flag. Run in the main conversation — the artifact is already in context, so no subagent.

**Binary-checkable** means one of: (a) a runnable command with observable output and pass/fail; (b) an observable state naming the file path, the string or pattern, and the expected true/false; (c) `Interactive/session-dependent: [one-sentence rationale]` when neither applies.

## 2. Handle the verdict

**Pass** → show a one-line assessment (e.g. "Spec clean, criteria measurable") and proceed. **Flag** → §3.

## 3. Fix

Fix each flag in place. A flag spanning several requirements or the artifact's cross-references gets a coherent rewrite of the affected sections, not a patch; where a preference decides the fix, explain the issue and gather input first. Re-check only the flagged rules, once. If a flag still stands, present what was checked and what is unresolved and let the user decide — further iteration rounds decrease quality.
