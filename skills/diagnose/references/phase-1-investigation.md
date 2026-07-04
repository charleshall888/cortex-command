# Phase 1: Root Cause Investigation — Detailed Procedure

Expands SKILL.md Phase 1. Steps 1–3 and 5 are summarized there; this ref owns §4 (boundary evidence) and §6 (competing-hypotheses team).

### 4. Gather Evidence at Component Boundaries

When the system has multiple components (e.g., overnight runner → task agent → skill → hook), instrument each boundary before proposing fixes: log the input entering and the output exiting each component, and verify paths, permissions, and env vars at each layer. Run once to gather evidence showing where it breaks, then analyze that evidence to identify the failing component before investigating it.

Common boundaries to check:

- Skill trigger: does the description match the invocation phrase?
- Hook execution: is the script executable? Is the path in the settings.json allowlist? Is events.log writable?
- Lifecycle state: is events.log valid JSON (one object per line)? Does plan.md have expected checkbox format?
- Overnight runner: did the runner exit silently? Is the task agent waiting on stdin?

### 6. Optional: Competing-Hypotheses Team (Phase 1 Early Trigger)

If root cause is genuinely unclear and 2+ distinct plausible theories have already emerged from the error output and initial investigation, consider spawning a team to investigate in parallel rather than testing theories sequentially in Phase 3. **Skip this offer entirely when running autonomously** (overnight / no human available).

Present an explicit offer and wait for confirmation before spawning:

> "Multiple competing theories are present. Spawn a competing-hypotheses team now to investigate in parallel, or continue with sequential hypothesis testing?"

If declined, continue to Phase 2 normally.

Team mechanics — the availability check, spawn size, teammate context, structured output, and convergence check — are identical to Phase 4; see the phase-4-team-investigation.md reference, Steps 1–5. Two differences at this stage:

- Teammates have no fix-attempt history — they work from the error output and initial investigation only.
- On the outcome you proceed to Phase 2, not a fix: **converged** → Phase 2 with the surviving theory as the leading hypothesis; **not converged** → Phase 2 with all theories noted for sequential investigation.
