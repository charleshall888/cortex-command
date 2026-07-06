# Phase 1: Root Cause Investigation — Detailed Procedure

Expands SKILL.md Phase 1 (steps 1–3, 5 summarized there); this ref owns §4 (boundary evidence) and §6 (competing-hypotheses team).

### 4. Gather Evidence at Component Boundaries

For multi-component systems (overnight runner → task agent → skill → hook), instrument each boundary — log input/output and verify paths, permissions, and env vars at each layer. Run once to see where it breaks, then investigate only that component.

Common boundaries to check:

- Skill trigger: does the description match the invocation phrase?
- Hook execution: is the script executable? Is its path in the settings.json allowlist? Is events.log writable?
- Lifecycle state: is events.log valid JSON (one object per line)? Does plan.md match the expected checkbox format?
- Overnight runner: did it exit silently? Is the task agent waiting on stdin?

### 6. Optional: Competing-Hypotheses Team (Phase 1 Early Trigger)

If root cause is unclear and 2+ theories have emerged, consider a team to investigate in parallel rather than testing sequentially in Phase 3. **Skip this offer entirely when running autonomously** (overnight / no human available).

Offer explicitly and wait for confirmation before spawning:

> "Multiple competing theories are present. Spawn a competing-hypotheses team now to investigate in parallel, or continue with sequential hypothesis testing?"

If declined, continue to Phase 2 normally.

Team mechanics (availability check, spawn size, teammate context, structured output, convergence check) are identical to Phase 4 — see phase-4-team-investigation.md, Steps 1–5. Two differences here:

- Teammates have no fix-attempt history — they work from the error output and initial investigation only.
- On the outcome you proceed to Phase 2, not a fix: **converged** → Phase 2 with the surviving theory as the leading hypothesis; **not converged** → Phase 2 with all theories noted for sequential investigation.
