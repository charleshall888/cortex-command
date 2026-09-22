# Orchestrator Phase Review

A quality check: an artifact reaches the user only after it passes, or with its open problems named.

**Skip** when criticality is `low` AND tier is `simple` (no events logged); run for every other combination. Use the tier and criticality you already have (`cortex-lifecycle-state --feature {feature}` only if you lack them; defaults `medium`/`simple`). `"corrupted": true` → SKILL.md § Criticality: the feature requires review.

1. **Check** the artifact against the phase reference's authoring rules, each **pass** or **flag** (flag = not covered, not met, or clearly weak). No subagent — you already have the artifact. **Binary-checkable** = (a) a runnable command with pass/fail output; (b) an observable state naming path, pattern, and expected truth; (c) `Interactive/session-dependent: [one-sentence rationale]`.
2. **Pass** → one-line assessment ("Spec clean, criteria measurable") and proceed.
3. **Flag** → fix each in place. A flag that spans several requirements or cross-references gets one consistent rewrite, not a patch. Where the fix depends on a preference, ask first. Re-check only the flagged rules, once. Still flagged → show what was checked and what is unresolved; the user decides. More rounds make it worse.
