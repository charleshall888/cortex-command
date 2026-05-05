---
name: diagnose
description: >
  Systematic 4-phase debugging for skills, hooks, lifecycle, and overnight runner issues.
  Use when: "debug this", "fix this bug", "why is this failing", "investigate this error",
  "make this test pass", "why isn't this triggering", "skill not working", "hook not running",
  "lifecycle bug", "overnight runner stall", "diagnose this", "diagnose",
  or any unexpected behavior in the agentic layer
  components. Finds root cause, fixes, and verifies with a structured loop.
---

# Systematic Debugging

## Rule

ALWAYS find root cause before attempting fixes. No fixes without completing Phase 1.

## The Four Phases

### Phase 1: Root Cause Investigation

**BEFORE attempting ANY fix:**

1. **Read Error Messages Carefully**
   - Don't skip past errors or warnings — they often contain the exact solution
   - Read stderr completely; note file paths, line numbers, exit codes
   - For hook failures: check whether the error is from the hook script itself or from the
     tool it wraps

2. **Reproduce Consistently**
   - Can you trigger it reliably? What are the exact steps?
   - If it only fails in one context (sandbox vs. non-sandbox, overnight vs. interactive),
     that context is the clue — not an annoyance

3. **Check Recent Changes**
   - What changed that could cause this? Git diff, recent commits
   - New skills added? Frontmatter edited? justfile recipe changed? Hook re-deployed?

4. **Gather Evidence at Component Boundaries**

   **When the system has multiple components (e.g., overnight runner → task agent → skill →
   hook):**

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
   - Hook execution: is the script executable? Is the path in the settings.json allowlist?
     Is events.log writable?
   - Lifecycle state: is events.log valid JSON (one object per line)? Does plan.md have
     expected checkbox format?
   - Overnight runner: did the bash runner exit silently? Is the task agent waiting on stdin?

5. **Trace Backward to Root Cause**

   See **Backward Tracing** technique below.

   Quick version: where does the bad value or wrong behavior originate? Trace backward
   through callers until you find the source. Fix at the source, not the symptom.

6. **Optional: Competing-Hypotheses Team (Phase 1 Early Trigger)**

   If root cause is genuinely unclear and 2+ distinct plausible theories have already emerged
   from the error output and initial investigation, consider spawning a competing-hypotheses
   team to investigate in parallel rather than testing theories sequentially in Phase 3.

   **Skip this offer entirely when running autonomously (overnight/no human available).**

   **Availability check:**
   ```
   Run: printenv CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS
   ```
   - If it prints `1`: Agent Teams is available, proceed with the offer
   - If it prints nothing or fails: Agent Teams unavailable — continue to Phase 2 normally

   **If available and 2+ theories exist**, present an explicit offer:

   > "Multiple competing theories are present. Spawn a competing-hypotheses team now to
   > investigate in parallel, or continue with sequential hypothesis testing?"

   Wait for confirmation before spawning. If declined, continue to Phase 2 normally.

   **If confirmed — spawn the team (3–5 teammates):**

   Choose team size based on the number of distinct plausible theories (minimum 3). Each
   teammate receives:
   - The bug description and reproduction steps
   - The complete error output
   - Their assigned root cause theory
   - Instruction: "Investigate evidence supporting your assigned theory AND actively gather
     evidence that would disprove the competing theories."

   Note: there is no fix attempt history at this stage — teammates work from error output and
   initial investigation only.

   **Convergence check:** After the team completes, review each teammate's structured
   conclusion (root cause assertion, supporting evidence, rebuttal of competing theories).
   - **Converged**: If all but at most one teammate independently identify the same root cause
     with non-overlapping evidence, declare convergence and proceed to Phase 2 with the
     surviving theory as the leading hypothesis.
   - **Not converged**: If no theory achieves majority support, or if the apparent majority is
     based on the same evidence (corroboration, not independent confirmation), continue to
     Phase 2 with all theories noted for sequential investigation.

> After this phase completes, write or update the debug session artifact. See **Debug Session Artifact** section.

### Phase 2: Pattern Analysis

**Find the pattern before fixing:**

1. **Find Working Examples**
   - Locate a similar working component (working skill, passing hook, healthy lifecycle)
   - What works that's similar to what's broken?

2. **Compare Against the Reference**
   - Read the reference implementation completely — don't skim
   - For skills: read a working skill's frontmatter and structure end-to-end
   - For hooks: read a working hook script top to bottom

3. **Identify Differences**
   - List every difference between working and broken, however small
   - Don't assume "that can't matter" — frontmatter typos and missing
     executable bits are common root causes

4. **Understand Dependencies**
   - What does this component need? File paths, environment variables, permissions, session
     state? What assumptions does it make about when it runs?

> After this phase completes, write or update the debug session artifact. See **Debug Session Artifact** section.

### Phase 3: Hypothesis and Testing

**Scientific method:**

1. **Form a Single Hypothesis**
   - State clearly: "I think X is the root cause because Y"
   - Be specific: "The session writes are failing because the entry in
     `sandbox.filesystem.allowWrite` uses `~/Workspaces/myrepo/lifecycle/sessions/`
     but the sandbox allowlist expects an absolute path (e.g.
     `/Users/me/Workspaces/myrepo/lifecycle/sessions/`)"

2. **Test Minimally**
   - Make the SMALLEST possible change to test the hypothesis
   - One variable at a time — don't fix multiple things at once

3. **Verify Before Continuing**
   - Did it work? Yes → Phase 4
   - Didn't work? Form a NEW hypothesis — don't add more fixes on top

4. **When You Don't Know**
   - Say "I don't understand X"
   - Don't pretend to know. Gather more evidence (back to Phase 1)

> After this phase completes, write or update the debug session artifact. See **Debug Session Artifact** section.

### Phase 4: Implementation

**Fix the root cause, not the symptom:**

1. **Confirm the Root Cause**
   - State what it is and where it is before writing any fix

2. **Implement a Single Fix**
   - Address the root cause identified — one change at a time
   - No "while I'm here" improvements
   - No bundled refactoring

3. **Verify the Fix**
   - Test the specific behavior that was failing
   - Check that adjacent behaviors still work (e.g., if you edited settings.json, verify
     other hooks still load)

4. **If the Fix Doesn't Work**
   - STOP
   - Count: how many fix attempts so far?
   - If < 3: return to Phase 1 and re-analyze with new information
   - **If ≥ 3: stop and attempt team investigation before escalating — see §5**
   - DO NOT attempt Fix #4 without completing the team investigation protocol or
     an architectural discussion

5. **If 3+ Fixes Failed: Team Investigation Before Escalation**

   **Step 1 — Agent Teams availability check:**
   ```
   Run: printenv CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS
   ```
   - If it prints `1`: Agent Teams is available — proceed to Step 2
   - If it prints nothing or fails: Agent Teams unavailable — skip to the Architecture
     Discussion below

   **Step 2 — Spawn 3–5 teammates.** Choose team size based on the number of distinct
   plausible theories at this point (minimum 3). If fewer than 3 distinct theories can be
   identified, assign the third teammate to "investigate novel angles not covered by the
   other theories."

   **Step 3 — Provide teammate context.** Each teammate receives:
   - The bug description and reproduction steps
   - The complete error output
   - The full history of failed fix attempts — what was tried, what failed, and what was
     learned from each
   - Their assigned root cause theory
   - Explicit challenge instruction: "Your job is to test your assigned theory AND actively
     challenge the other teammates' theories with evidence. Try to disprove their hypotheses,
     not just verify yours."

   **Step 4 — Enforce structured output.** Each teammate must produce:
   - **Root cause assertion**: one clear statement
   - **Supporting evidence**: specific findings (file paths, error patterns, code behavior)
   - **Rebuttal of strongest competing theory**: with evidence

   Format example:
   ```
   Root cause: [assertion] / Evidence: [supporting detail] / Rebuttal: [strongest objection to this hypothesis]
   ```

   Enforce via `TeammateIdle` hook (exit code 2 sends feedback, keeps the teammate working)
   or by the lead sending direct messages challenging shallow or incomplete outputs.

   **Step 5 — Convergence check.** After the team completes, review each teammate's
   structured conclusion:
   - **Converged**: all but at most one teammate independently identify the same root cause,
     and their evidence is non-overlapping. Corroboration (the same finding cited by multiple
     teammates) does NOT count as independent confirmation — that is non-convergence.
   - **Not converged**: no theory achieves the convergence threshold, or the apparent
     agreement is based on shared evidence rather than independent findings.

   **Step 6 — On convergence**: attempt one more targeted fix using the surviving theory.
   This is a fresh attempt, not counted toward the original 3-attempt limit.
   - If this fix succeeds → done
   - If this fix fails → proceed to Architecture Discussion below

   **Step 7 — On non-convergence**: proceed directly to Architecture Discussion below,
   including a summary of the competing theories and evidence gathered by the team.

   > **Note on overnight/autonomous contexts**: If running autonomously (no human available):
   > skip team investigation and fail the current task directly. The overnight runner's
   > failure gate will surface it to morning review.

   ---

   **Architecture Discussion** (escalation destination for non-convergence or post-team fix
   failure)

   **Patterns indicating an architectural problem:**
   - Each fix reveals new coupling or a new symptom in a different place
   - A proper fix would require "massive refactoring" to implement correctly
   - Each fix moves the error rather than eliminating it

   **STOP and question fundamentals:**
   - Is the component designed correctly for this use case?
   - Are we debugging a symptom of a deeper structural mismatch?
   - Should this be redesigned rather than incrementally patched?

   **Discuss with the user before attempting more fixes.**

> After this phase completes, write or update the debug session artifact. See **Debug Session Artifact** section.

---

## Debug Session Artifact

### Location

Determine where to write the artifact using this priority:

1. **Explicit feature argument** (e.g., `/cortex-core:diagnose my-feature`): write to
   `lifecycle/{feature}/debug-session.md` if the directory exists. If not, warn verbally
   and fall back to step 3.
2. **Active session scan**: check `lifecycle/*/` for a `.session` file whose content matches
   `$LIFECYCLE_SESSION_ID`. If found, write to `lifecycle/{feature}/debug-session.md`.
3. **Fallback**: write to `debug/{date}-{slug}.md` where `{date}` is ISO date (YYYY-MM-DD)
   and `{slug}` is a short kebab-case description of what is being debugged (use `diagnose`
   if no slug is available). Create the `debug/` directory if absent.

> **Note**: `$LIFECYCLE_SESSION_ID` propagation into overnight sub-agent sessions is
> unverified. In autonomous/overnight context, pass the feature name explicitly
> (e.g., `/cortex-core:diagnose my-feature`) for reliable lifecycle-coupled artifact placement.

### Format

```markdown
# Debug Session: {context}
Date: YYYY-MM-DD
Status: In progress | Resolved | Escalated — investigation incomplete

## Phase N Findings
- **Observed behavior**: ...
- **Evidence gathered**: ...
- **Tests performed**: ...
- **Outcomes**: ...
- **Dead-ends**: ... (call out explicitly)

## Current State
Root cause identified: X. Fix applied: Y.
— or —
Best current theory: X. Not yet tried: Y.

## Prior Attempts
(Move prior content here if the file previously existed; current investigation stays on top.)
```

### Write Timing

- **Phase 1**: create the file with Phase 1 Findings + Current State. Status: `In progress`.
- **Phases 2–3**: update file — add Phase N Findings, update Current State. Status: `In progress`.
- **Phase 4 success**: add Phase 4 Findings, update Current State. Status: `Resolved`.
- **Autonomous escalation** (Phase 4 §5 skipped, no human available): write current findings
  with status `Escalated — investigation incomplete` before failing the task. This write is
  mandatory — do not exit without it.

---

## Lifecycle Escalation Boundary

Debug skill escalation and lifecycle escalation are **different mechanisms** covering
different concerns:

| | Debug escalation | Lifecycle escalation |
|---|---|---|
| **When** | During implementation, after 3 failed fix attempts | At phase transitions (Research→Spec, Spec→Plan) |
| **Signal** | A bug resists fixes and shows architectural patterns | Feature scope/complexity exceeds original estimate |
| **Action** | Team investigation first (§5); architecture discussion if team doesn't converge | User is prompted to escalate to Complex tier |
| **Phase** | Implement (post-build debugging) | Research/Specify (pre-build design) |

Invoking `/cortex-core:diagnose` when a lifecycle task fails is a structured pre-retry step — it does not
replace or short-circuit the lifecycle's own phase gates.

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

**If 3+ fixes failed:** team investigation first (Phase 4 §5), then architecture discussion if the team doesn't converge.

---

## Common Rationalizations

| Excuse | Reality |
|--------|---------|
| "Issue is simple, don't need process" | Simple issues have root causes too. Phase 1 is fast for simple bugs. |
| "Emergency, no time for process" | Systematic debugging is faster than guess-and-check. |
| "Just try this first, then investigate" | First fix sets the pattern. Do it right from the start. |
| "Multiple fixes at once saves time" | Can't isolate what worked. Causes new bugs. |
| "I see the problem, let me fix it" | Seeing symptoms ≠ understanding root cause. |
| "One more fix attempt" (after 2+ failures) | 3+ failures = run team investigation (Phase 4 §5) if Agent Teams available, then architecture discussion. Do not add a 4th fix without completing §5. |

---

## Supporting Techniques

### Backward Root-Cause Tracing

Bugs often manifest far from their source. Your instinct is to fix where the error appears —
that treats a symptom.

**Core principle**: Trace backward through the execution path until you find the original
trigger, then fix at the source.

**The tracing process:**

1. Observe the symptom (e.g., "commit fails with GPG error")
2. Find the immediate cause (e.g., `git commit` exits non-zero; GNUPGHOME not set)
3. Ask: what called this? What provided the environment? (e.g., the commit skill ran, but
   the SessionStart hook that sets up GNUPGHOME didn't complete)
4. Keep tracing up: what caused the hook to not complete? (e.g., the extra socket path
   wasn't found because TMPDIR changed)
5. Fix at the source (the socket path logic in the hook) — not at the symptom (suppressing
   the GPG error in the commit skill)

**Adding diagnostic instrumentation** when you can't trace manually:
```bash
# In a hook script: trace execution
set -x  # prints every command as it runs

# At a key decision point: log the state
echo "DEBUG: GNUPGHOME=$GNUPGHOME, socket exists=$(test -S $GNUPGHOME/S.gpg-agent && echo yes || echo no)" >&2

# For skill invocation: add an explicit trace to the description trigger
# (temporarily add the invocation phrase you're testing to verify it triggers)
```

**Never fix just where the error appears.** Trace back to find the original trigger.

---

### Defense-in-Depth Validation

When you fix a bug caused by bad state, adding validation at one place feels sufficient —
but that check can be bypassed by different code paths or edge cases.

**Core principle**: Validate at every layer data passes through. Make the bug structurally
impossible.

**The four layers:**

1. **Entry point**: reject invalid input at the boundary
   ```bash
   # In a hook script: verify required env vars are set before using them
   if [ -z "$GNUPGHOME" ]; then
     echo "ERROR: GNUPGHOME not set" >&2; exit 1
   fi
   ```

2. **Business logic**: ensure data makes sense for this operation
   ```bash
   # In a lifecycle script: verify events.log is valid before appending
   if ! python3 -c "import json; [json.loads(l) for l in open('events.log')]" 2>/dev/null; then
     echo "ERROR: events.log is malformed" >&2; exit 1
   fi
   ```

3. **Environment guards**: prevent dangerous operations in specific contexts
   ```bash
   # Before destructive operations: verify you're not in the wrong directory
   if [ "$(pwd)" != "$EXPECTED_ROOT" ]; then
     echo "ERROR: wrong working directory" >&2; exit 1
   fi
   ```

4. **Debug instrumentation**: capture context for forensics
   ```bash
   # Log state at each boundary for post-mortem if something still goes wrong
   echo "DEBUG: entering hook, session=$LIFECYCLE_SESSION_ID, feature=$1" >&2
   ```

Don't stop at one validation point. Add checks at every layer.

---

### Condition-Based Waiting

Arbitrary sleeps guess at timing. This creates races where scripts pass on fast machines
but fail under load or when the system is busy.

**Core principle**: wait for the actual condition you care about, not a guess about how long
it takes.

**Shell-native pattern:**
```bash
wait_for() {
  local description="$1"
  local condition="$2"      # a bash test expression
  local timeout="${3:-30}"  # seconds
  local elapsed=0
  while ! eval "$condition" 2>/dev/null; do
    if [ "$elapsed" -ge "$timeout" ]; then
      echo "Timeout after ${timeout}s waiting for: $description" >&2
      return 1
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done
}

# Usage examples:
wait_for "events.log to appear"       '[ -s lifecycle/my-feature/events.log ]'
wait_for "task-done flag"             '[ -f /tmp/task-done.flag ]'       30
wait_for "GPG agent socket"           '[ -S "$GNUPGHOME/S.gpg-agent" ]'  10
wait_for "overnight runner to finish" 'grep -q feature_complete lifecycle/my-feature/events.log' 120
```

**Don't use when:**
- Testing actual timing behavior (a debounce or rate-limit mechanism)
- If using an arbitrary sleep, document WHY with a comment

**Common mistakes:**
- No timeout: loop forever if condition never met — always include a timeout with a clear error
- Stale state: evaluate the condition fresh inside the loop, not a cached value
