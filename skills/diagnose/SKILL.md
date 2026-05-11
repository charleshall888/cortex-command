---
name: diagnose
description: >
  Systematic 4-phase debugging for skills, hooks, lifecycle, and overnight runner issues.
  Use when: "fix this bug", "why is this failing", "make this test pass", "skill not working",
  "hook not running", "diagnose this", or unexpected agentic-layer behavior.
  Finds root cause, fixes, and verifies.
---

# Systematic Debugging

## Rule

ALWAYS find root cause before attempting fixes. No fixes without completing Phase 1.

## References

Detailed procedures, examples, and templates are extracted to references. Read on demand when the phase you are in points to one:

| Topic | Reference |
|-------|-----------|
| Phase 1 detail (boundary instrumentation, competing-hypotheses team) | [phase-1-investigation.md](${CLAUDE_SKILL_DIR}/references/phase-1-investigation.md) |
| Phase 4 §5 (team investigation + architecture discussion) | [phase-4-team-investigation.md](${CLAUDE_SKILL_DIR}/references/phase-4-team-investigation.md) |
| Debug-session artifact (location, format, write timing) | [debug-session-artifact.md](${CLAUDE_SKILL_DIR}/references/debug-session-artifact.md) |
| Supporting techniques (backward tracing, defense-in-depth, condition waits) | [techniques.md](${CLAUDE_SKILL_DIR}/references/techniques.md) |
| Common rationalizations | [rationalizations.md](${CLAUDE_SKILL_DIR}/references/rationalizations.md) |

Read **only** the reference for what you are currently doing. Do not preload all references.

## The Four Phases

### Phase 1: Root Cause Investigation

**BEFORE attempting ANY fix:**

1. **Read error messages carefully.** Don't skip warnings; note file paths, line numbers, exit codes. For hook failures, distinguish errors from the hook script vs. errors from the tool it wraps.
2. **Reproduce consistently.** Identify exact trigger steps. Context-specific failures (sandbox vs. non-sandbox, overnight vs. interactive) are clues, not noise.
3. **Check recent changes.** Git diff, recent commits. New skills, frontmatter edits, justfile changes, hook redeploys.
4. **Gather evidence at component boundaries.** Add diagnostic instrumentation before proposing fixes; identify the failing component from evidence, not guesswork. See `${CLAUDE_SKILL_DIR}/references/phase-1-investigation.md` for boundary checklist and instrumentation patterns.
5. **Trace backward to root cause.** Where does the bad value or wrong behavior originate? Fix at the source, not the symptom. See `${CLAUDE_SKILL_DIR}/references/techniques.md` (Backward Root-Cause Tracing).
6. **Optional: competing-hypotheses team.** If 2+ distinct plausible theories already exist and a human is available, consider spawning a parallel team rather than testing sequentially. Skip entirely in autonomous contexts. Procedure: `${CLAUDE_SKILL_DIR}/references/phase-1-investigation.md` §6.

> After this phase, write or update the debug session artifact. See `${CLAUDE_SKILL_DIR}/references/debug-session-artifact.md`.

### Phase 2: Pattern Analysis

**Find the pattern before fixing:**

1. **Find working examples.** Locate a similar working component (working skill, passing hook, healthy lifecycle).
2. **Compare against the reference.** Read the reference implementation completely — don't skim. Frontmatter and structure end-to-end.
3. **Identify differences.** List every difference between working and broken, however small. Don't assume "that can't matter."
4. **Understand dependencies.** What does this component need? Paths, env vars, permissions, session state, assumptions about when it runs.

> After this phase, update the debug session artifact.

### Phase 3: Hypothesis and Testing

**Scientific method:**

1. **Form a single hypothesis.** State clearly: "I think X is the root cause because Y." Be specific about file paths, env vars, exact mismatches.
2. **Test minimally.** SMALLEST possible change to test the hypothesis. One variable at a time.
3. **Verify before continuing.** Worked → Phase 4. Didn't work → new hypothesis. Don't pile fixes on top of fixes.
4. **When you don't know, say so.** Don't pretend. Gather more evidence (back to Phase 1).

> After this phase, update the debug session artifact.

### Phase 4: Implementation

**Fix the root cause, not the symptom:**

1. **Confirm the root cause.** State what it is and where it is before writing any fix.
2. **Implement a single fix.** Address the root cause — one change at a time. No "while I'm here" improvements. No bundled refactoring.
3. **Verify the fix.** Test the specific behavior that was failing. Check adjacent behaviors still work.
4. **If the fix doesn't work, STOP.** Count fix attempts so far.
   - If < 3: return to Phase 1 and re-analyze.
   - **If ≥ 3: stop and attempt team investigation before escalating.** See `${CLAUDE_SKILL_DIR}/references/phase-4-team-investigation.md`. Do NOT attempt Fix #4 without completing the team investigation protocol or an architectural discussion.

> After this phase completes, update the debug session artifact (Resolved or Escalated). See `${CLAUDE_SKILL_DIR}/references/debug-session-artifact.md`.

---

## Lifecycle Escalation Boundary

Debug skill escalation and lifecycle escalation are **different mechanisms** covering different concerns:

| | Debug escalation | Lifecycle escalation |
|---|---|---|
| **When** | During implementation, after 3 failed fix attempts | At phase transitions (Research→Spec, Spec→Plan) |
| **Signal** | A bug resists fixes and shows architectural patterns | Feature scope/complexity exceeds original estimate |
| **Action** | Team investigation first; architecture discussion if team doesn't converge | User is prompted to escalate to Complex tier |
| **Phase** | Implement (post-build debugging) | Research/Specify (pre-build design) |

Invoking `/cortex-core:diagnose` when a lifecycle task fails is a structured pre-retry step — it does not replace or short-circuit the lifecycle's own phase gates.

---

## Red Flags — Stop and Follow Process

If you catch yourself thinking any of these, **stop and return to Phase 1**:

- "Quick fix for now, investigate later"
- "Just try changing X and see if it works"
- "Add multiple changes, run and see"
- "It's probably X, let me fix that" (without evidence)
- "I don't fully understand but this might work"
- Proposing a solution before completing the backward trace
- "One more fix attempt" (when you've already tried 2+)
- Each fix reveals a new problem in a different place

**If 3+ fixes failed:** team investigation first, then architecture discussion if the team doesn't converge. See `${CLAUDE_SKILL_DIR}/references/phase-4-team-investigation.md`.

For the catalog of excuses to recognize and rebut, see `${CLAUDE_SKILL_DIR}/references/rationalizations.md`.
