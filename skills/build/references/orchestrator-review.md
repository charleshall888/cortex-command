# Orchestrator Phase Review

Quality gate: nothing reaches the user before passing review or being surfaced as unresolved.

**Skip** when criticality is `low` AND tier is `simple` (no events logged); run for every other combination. Use the tier and criticality in context (`cortex-lifecycle-state --feature {feature}` only if unreached; defaults `medium`/`simple`). `"corrupted": true` → SKILL.md § Criticality: the feature requires review.

1. **Check** the artifact against the phase reference's authoring rules, each **pass** or **flag** (unreached, unsatisfied, or materially weak = flag). Inline — the artifact is already in context; no subagent. **Binary-checkable** = (a) a runnable command with pass/fail output; (b) an observable state naming path, pattern, and expected truth; (c) `Interactive/session-dependent: [one-sentence rationale]`.
2. **Pass** → one-line assessment ("Spec clean, criteria measurable") and proceed.
3. **Flag** → fix each in place. A flag spanning several requirements or cross-references gets a coherent rewrite, not a patch; where a preference decides the fix, ask first. Re-check only the flagged rules, once. Still standing → present what was checked and what is unresolved; the user decides — further rounds decrease quality.
