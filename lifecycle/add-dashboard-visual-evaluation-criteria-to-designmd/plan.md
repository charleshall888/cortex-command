# Plan: Add dashboard visual evaluation criteria to DESIGN.md

## Overview

Append a `## Visual Evaluation Criteria` section to `claude/dashboard/DESIGN.md` after the existing `## Pattern Examples` section (currently the last section). The section contains a four-row criteria table and a brief usage paragraph. No existing content is modified.

## Tasks

### Task 1: Append Visual Evaluation Criteria section to DESIGN.md

- **Files**: `claude/dashboard/DESIGN.md`
- **What**: Append the following content after line 93 (end of `## Pattern Examples` section):

  ```markdown

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
- **Context**: DESIGN.md is 93 lines; the new section is purely additive. The file header confirms re-running `/ui-brief` will not overwrite edits. The section heading `## Visual Evaluation Criteria` must remain stable — tickets 029 and 031 reference it by name.
- **Verification**:
  - `grep -c '## Visual Evaluation Criteria' claude/dashboard/DESIGN.md` returns 1
  - `grep -Ec 'Information clarity|Consistency|Operational usefulness|Purposefulness' claude/dashboard/DESIGN.md` returns 4
  - `grep -c 'Playwright' claude/dashboard/DESIGN.md` returns >= 1
- **Status**: pending

## Verification Strategy

Run all three acceptance-criteria grep commands from the spec against the modified file:

```sh
grep -c '## Visual Evaluation Criteria' claude/dashboard/DESIGN.md        # must be 1
grep -Ec 'Information clarity|Consistency|Operational usefulness|Purposefulness' claude/dashboard/DESIGN.md  # must be 4
grep -c 'Playwright' claude/dashboard/DESIGN.md                            # must be >= 1
```

Then read the end of `claude/dashboard/DESIGN.md` to confirm style matches the rest of the file: `##` heading, table for structured data, terse prose, no verbose explanations.
