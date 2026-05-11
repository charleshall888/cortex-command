# Phase 4 §5: Team Investigation Before Escalation

This reference expands on Phase 4 §5 of the 4-phase debugging protocol. Read when 3+ fixes have failed.

## Step 1 — Agent Teams availability check

```
Run: printenv CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS
```

- If it prints `1`: Agent Teams is available — proceed to Step 2
- If it prints nothing or fails: Agent Teams unavailable — skip to the Architecture Discussion below

## Step 2 — Spawn 3–5 teammates

Choose team size based on the number of distinct plausible theories at this point (minimum 3). If fewer than 3 distinct theories can be identified, assign the third teammate to "investigate novel angles not covered by the other theories."

## Step 3 — Provide teammate context

Each teammate receives:

- The bug description and reproduction steps
- The complete error output
- The full history of failed fix attempts — what was tried, what failed, and what was learned from each
- Their assigned root cause theory
- Explicit challenge instruction: "Your job is to test your assigned theory AND actively challenge the other teammates' theories with evidence. Try to disprove their hypotheses, not just verify yours."

## Step 4 — Enforce structured output

Each teammate must produce:

- **Root cause assertion**: one clear statement
- **Supporting evidence**: specific findings (file paths, error patterns, code behavior)
- **Rebuttal of strongest competing theory**: with evidence

Format example:

```
Root cause: [assertion] / Evidence: [supporting detail] / Rebuttal: [strongest objection to this hypothesis]
```

Enforce via `TeammateIdle` hook (exit code 2 sends feedback, keeps the teammate working) or by the lead sending direct messages challenging shallow or incomplete outputs.

## Step 5 — Convergence check

After the team completes, review each teammate's structured conclusion:

- **Converged**: all but at most one teammate independently identify the same root cause, and their evidence is non-overlapping. Corroboration (the same finding cited by multiple teammates) does NOT count as independent confirmation — that is non-convergence.
- **Not converged**: no theory achieves the convergence threshold, or the apparent agreement is based on shared evidence rather than independent findings.

## Step 6 — On convergence

Attempt one more targeted fix using the surviving theory. This is a fresh attempt, not counted toward the original 3-attempt limit.

- If this fix succeeds → done
- If this fix fails → proceed to Architecture Discussion below

## Step 7 — On non-convergence

Proceed directly to Architecture Discussion below, including a summary of the competing theories and evidence gathered by the team.

> **Note on overnight/autonomous contexts**: If running autonomously (no human available): skip team investigation and fail the current task directly. The overnight runner's failure gate will surface it to morning review.

---

## Architecture Discussion

(Escalation destination for non-convergence or post-team fix failure.)

**Patterns indicating an architectural problem:**

- Each fix reveals new coupling or a new symptom in a different place
- A proper fix would require "massive refactoring" to implement correctly
- Each fix moves the error rather than eliminating it

**STOP and question fundamentals:**

- Is the component designed correctly for this use case?
- Are we debugging a symptom of a deeper structural mismatch?
- Should this be redesigned rather than incrementally patched?

**Discuss with the user before attempting more fixes.**
