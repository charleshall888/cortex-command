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

Read only the reference for what you're doing right now — don't preload all of them.

- **Phase 1 detail**: `${CLAUDE_SKILL_DIR}/references/phase-1-investigation.md`
- **Phase 4 §5** (team investigation): `${CLAUDE_SKILL_DIR}/references/phase-4-team-investigation.md`
- **Debug-session artifact**: `${CLAUDE_SKILL_DIR}/references/debug-session-artifact.md`
- **Supporting techniques**: `${CLAUDE_SKILL_DIR}/references/techniques.md`
- **Common rationalizations**: `${CLAUDE_SKILL_DIR}/references/rationalizations.md`

## The Four Phases

After each phase, write or update the debug session artifact — `In progress` through Phases 1–3, `Resolved` or `Escalated` at Phase 4. See `${CLAUDE_SKILL_DIR}/references/debug-session-artifact.md` for location, format, and timing.

### Phase 1: Root Cause Investigation

1. Read errors fully: file paths, line numbers, exit codes. For hooks, separate the hook script's errors from the wrapped tool's.
2. Reproduce consistently; treat context (sandbox vs. non-sandbox, overnight vs. interactive) as a clue, not noise.
3. Check recent changes — git diff, recent commits, skill or hook redeploys.
4. Gather evidence at component boundaries before proposing fixes. See `${CLAUDE_SKILL_DIR}/references/phase-1-investigation.md` §4 for the boundary checklist.
5. Trace backward to root cause; fix at the source, not the symptom. See `${CLAUDE_SKILL_DIR}/references/techniques.md` (Backward Root-Cause Tracing).
6. Optional: if 2+ plausible theories exist and a human is available, consider a competing-hypotheses team instead of testing sequentially — skip in autonomous contexts. See `${CLAUDE_SKILL_DIR}/references/phase-1-investigation.md` §6.

### Phase 2: Pattern Analysis

1. Find a working example (similar skill, passing hook, healthy lifecycle) and diff it against the broken one, down to frontmatter and structure — no difference is too small to matter.
2. Check dependencies — paths, env vars, permissions, session state, timing assumptions.

### Phase 3: Hypothesis and Testing

1. Form one hypothesis: "I think X is the root cause because Y" — specific file paths, env vars, exact mismatches.
2. Test minimally — smallest possible change, one variable at a time.
3. Verify: worked → Phase 4; didn't → new hypothesis.
4. When you don't know, say so — gather more evidence (back to Phase 1) rather than guessing.

### Phase 4: Implementation

1. State the confirmed root cause and where it is before writing any fix.
2. Implement one change addressing it — no bundled refactoring or "while I'm here" fixes.
3. Verify: test the specific behavior that was failing, then check adjacent behavior.
4. If it doesn't work, stop and count fix attempts. < 3: return to Phase 1. ≥ 3: team investigation before a 4th attempt — see `${CLAUDE_SKILL_DIR}/references/phase-4-team-investigation.md`.

---

## Lifecycle Escalation Boundary

Debug and lifecycle escalation are **different mechanisms**. Debug escalation: fires during implementation after 3 failed fixes on an architecturally-resistant bug, and runs a team investigation then an architecture discussion. Lifecycle escalation: fires at phase transitions (Research→Spec, Spec→Plan) when scope or complexity exceeds the estimate, and prompts the user to escalate to the Complex tier.

`/cortex-core:diagnose` on a failed lifecycle task is a pre-retry step, not a replacement for the lifecycle's own phase gates.

---

## Red Flags — Stop and Follow Process

If you catch yourself thinking any of these, **stop and return to Phase 1**:

- "Quick fix for now, investigate later" / "just try X and see" / "add multiple changes at once and see what happens"
- "It's probably X" or "this might work" — proposed without evidence, or before completing the backward trace
- Each fix reveals a new problem in a different place

**If 3+ fixes failed:** see `${CLAUDE_SKILL_DIR}/references/phase-4-team-investigation.md` before a 4th attempt.

For the catalog of excuses to recognize and rebut, see `${CLAUDE_SKILL_DIR}/references/rationalizations.md`.
