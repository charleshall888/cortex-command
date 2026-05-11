# Phase 1: Root Cause Investigation — Detailed Procedure

This reference expands on Phase 1 of the 4-phase debugging protocol. Read this when entering Phase 1 of a debug session.

## Steps

### 1. Read Error Messages Carefully

- Don't skip past errors or warnings — they often contain the exact solution
- Read stderr completely; note file paths, line numbers, exit codes
- For hook failures: check whether the error is from the hook script itself or from the tool it wraps

### 2. Reproduce Consistently

- Can you trigger it reliably? What are the exact steps?
- If it only fails in one context (sandbox vs. non-sandbox, overnight vs. interactive), that context is the clue — not an annoyance

### 3. Check Recent Changes

- What changed that could cause this? Git diff, recent commits
- New skills added? Frontmatter edited? justfile recipe changed? Hook re-deployed?

### 4. Gather Evidence at Component Boundaries

When the system has multiple components (e.g., overnight runner → task agent → skill → hook):

Add diagnostic instrumentation before proposing fixes:

```
For EACH component boundary:
  - Log what input enters the component (echo to stderr, set -x in scripts)
  - Log what output exits the component
  - Verify file paths, permissions, env variables at each layer

Run once to gather evidence showing WHERE it breaks.
THEN analyze evidence to identify the failing component.
THEN investigate that specific component.
```

Common boundaries to check:

- Skill trigger: does the description match the invocation phrase?
- Hook execution: is the script executable? Is the path in the settings.json allowlist? Is events.log writable?
- Lifecycle state: is events.log valid JSON (one object per line)? Does plan.md have expected checkbox format?
- Overnight runner: did the runner exit silently? Is the task agent waiting on stdin?

### 5. Trace Backward to Root Cause

See `${CLAUDE_SKILL_DIR}/references/techniques.md` (Backward Root-Cause Tracing).

Quick version: where does the bad value or wrong behavior originate? Trace backward through callers until you find the source. Fix at the source, not the symptom.

### 6. Optional: Competing-Hypotheses Team (Phase 1 Early Trigger)

If root cause is genuinely unclear and 2+ distinct plausible theories have already emerged from the error output and initial investigation, consider spawning a competing-hypotheses team to investigate in parallel rather than testing theories sequentially in Phase 3.

**Skip this offer entirely when running autonomously (overnight/no human available).**

**Availability check:**

```
Run: printenv CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS
```

- If it prints `1`: Agent Teams is available, proceed with the offer
- If it prints nothing or fails: Agent Teams unavailable — continue to Phase 2 normally

**If available and 2+ theories exist**, present an explicit offer:

> "Multiple competing theories are present. Spawn a competing-hypotheses team now to investigate in parallel, or continue with sequential hypothesis testing?"

Wait for confirmation before spawning. If declined, continue to Phase 2 normally.

**If confirmed — spawn the team (3–5 teammates):**

Choose team size based on the number of distinct plausible theories (minimum 3). Each teammate receives:

- The bug description and reproduction steps
- The complete error output
- Their assigned root cause theory
- Instruction: "Investigate evidence supporting your assigned theory AND actively gather evidence that would disprove the competing theories."

Note: there is no fix attempt history at this stage — teammates work from error output and initial investigation only.

**Convergence check:** After the team completes, review each teammate's structured conclusion (root cause assertion, supporting evidence, rebuttal of competing theories).

- **Converged**: If all but at most one teammate independently identify the same root cause with non-overlapping evidence, declare convergence and proceed to Phase 2 with the surviving theory as the leading hypothesis.
- **Not converged**: If no theory achieves majority support, or if the apparent majority is based on the same evidence (corroboration, not independent confirmation), continue to Phase 2 with all theories noted for sequential investigation.
