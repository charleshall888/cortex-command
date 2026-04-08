# Plan: Add dashboard visual evaluation criteria to DESIGN.md

## Overview

Append a `## Visual Evaluation Criteria` section to `claude/dashboard/DESIGN.md` after the existing `## Pattern Examples` section (the last section, ending at line 93). The section contains a four-row criteria table and a brief usage paragraph. No existing content is modified.

**Current state of DESIGN.md:** 93 lines. The string `## Visual Evaluation Criteria` does NOT appear anywhere in the file. This section must be created.

**Required end state:** DESIGN.md is longer than 93 lines and contains the new section with all four criteria and a Playwright reference. A commit must be produced.

## Tasks

### Task 1: Append Visual Evaluation Criteria section to DESIGN.md

- **Files**: `claude/dashboard/DESIGN.md`
- **What**: Edit `claude/dashboard/DESIGN.md` to append the following block after the last line (line 93). Use the Edit tool, matching on the last line of the file as `old_string` and appending the new content as `new_string`.

  The exact content to append (after the existing last line):

  ```
  
  ## Visual Evaluation Criteria
  
  Use these criteria when evaluating dashboard UI — via Playwright MCP, PR review, or as acceptance criteria in dashboard feature specs.
  
  | Criterion | Weight | What to evaluate |
  |-----------|--------|-----------------|
  | Information clarity | High | Status hierarchy visually distinct via color and size differentiation; feature phases scannable across cards; session info prominent in session panel |
  | Consistency | High | Design tokens used throughout; badge color meanings stable across panels; no forbidden patterns visible; spacing follows token scale |
  | Operational usefulness | Medium | Alerts prominent and not buried; swim-lane legible with no overlapping labels; no visible layout shift after HTMX refresh; session history presents completed features with outcome and duration |
  | Purposefulness | Low | Reads as purpose-built monitoring tool, not generic admin panel — relevant primarily for large visual changes |
  
  All four criteria can be assessed by Claude via Playwright MCP (ticket 029) using interactive navigation and screenshots, and serve as review criteria for dashboard PRs or acceptance criteria in dashboard feature specs. Evaluation reliability varies: consistency is the most mechanically verifiable, while purposefulness requires the most judgment.
  ```

- **Depends on**: none
- **Context**: DESIGN.md is 93 lines. The last line (line 93) is an empty line following the final bullet in `## Pattern Examples`. The file header confirms re-running `/ui-brief` will not overwrite edits. The heading `## Visual Evaluation Criteria` must remain stable — tickets 029 and 031 reference it by name.
- **Verification** (run after editing, before committing):
  - `grep -c '## Visual Evaluation Criteria' claude/dashboard/DESIGN.md` returns `1`
  - `grep -Ec 'Information clarity|Consistency|Operational usefulness|Purposefulness' claude/dashboard/DESIGN.md` returns `4`
  - `grep -c 'Playwright' claude/dashboard/DESIGN.md` returns `1` or greater
  - `wc -l < claude/dashboard/DESIGN.md` returns a value greater than `93`
- **Status**: pending

### Task 2: Commit the change

- **Files**: `claude/dashboard/DESIGN.md`
- **What**: Stage and commit `claude/dashboard/DESIGN.md` with a clear imperative commit message, e.g. `Add Visual Evaluation Criteria section to dashboard DESIGN.md`. Use the `/commit` skill.
- **Depends on**: Task 1
- **Context**: The commit is required — the prior run produced no commits, which caused this pipeline to be paused. The file edit in Task 1 is the only change; commit it before finishing.
- **Verification**: `git log --oneline -1` shows a commit message referencing the Visual Evaluation Criteria section. `git diff HEAD~1 claude/dashboard/DESIGN.md` shows added lines for the new section.
- **Status**: pending

## Verification Strategy

After Tasks 1 and 2 complete, run these commands from the repo root:

```sh
grep -c '## Visual Evaluation Criteria' claude/dashboard/DESIGN.md        # must be 1
grep -Ec 'Information clarity|Consistency|Operational usefulness|Purposefulness' claude/dashboard/DESIGN.md  # must be 4
grep -c 'Playwright' claude/dashboard/DESIGN.md                            # must be >= 1
wc -l < claude/dashboard/DESIGN.md                                         # must be > 93
git log --oneline -1                                                        # must show a commit for this change
```

All five checks must pass. Then read the end of `claude/dashboard/DESIGN.md` to confirm style matches the rest of the file: `##` heading, table for structured data, terse prose, no verbose explanations.
