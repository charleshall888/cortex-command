# Phase 4 §5: Team Investigation Before Escalation

Expands Phase 4 §5. Read when 3+ fixes have failed.

## Step 1 — Agent Teams availability check

Run `printenv CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`. Prints `1` → available, proceed to Step 2. Prints nothing or fails → unavailable, skip to Architecture Discussion below.

## Step 2 — Spawn 3–5 teammates

Team size follows the number of distinct plausible theories (minimum 3); if fewer exist, assign the extra teammate(s) to investigate novel angles the others don't cover.

## Step 3 — Provide teammate context

Give each teammate the full picture (bug description, reproduction steps, error output, fix-attempt history — tried, failed, learned) plus their assigned theory, with an explicit instruction to challenge the other teammates' theories with evidence, not just verify their own.

## Step 4 — Enforce structured output

Each teammate must produce a root cause assertion (one statement), supporting evidence (file paths, error patterns, code behavior), and a rebuttal of the strongest competing theory:

```
Root cause: [assertion] / Evidence: [supporting detail] / Rebuttal: [strongest objection to this hypothesis]
```

Enforce via the `TeammateIdle` hook (exit code 2 keeps the teammate working) or by messaging weak outputs directly.

## Step 5 — Convergence check

- **Converged**: all but at most one teammate independently reach the same root cause, with non-overlapping evidence. Shared evidence cited by multiple teammates does not count as independent confirmation.
- **Not converged**: no theory meets that threshold, or the agreement rests on shared rather than independent evidence.

## Step 6 — Outcome

- **Converged**: attempt one more targeted fix with the surviving theory (a fresh attempt, uncounted toward the 3-attempt limit). Success → done; failure → Architecture Discussion below.
- **Not converged**: proceed directly to Architecture Discussion below, with a summary of the competing theories and evidence gathered.

> **Note on overnight/autonomous contexts**: skip team investigation and fail the task directly — the overnight runner's failure gate surfaces it to morning review.

---

## Architecture Discussion

**Patterns indicating an architectural problem:**

- Each fix reveals new coupling or moves the error to a different place
- A proper fix would require massive refactoring

Then stop: is the component correctly designed for this use case, or are you patching a deeper structural mismatch? **Discuss with the user before attempting more fixes.**
