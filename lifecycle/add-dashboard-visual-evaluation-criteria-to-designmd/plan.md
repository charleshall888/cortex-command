# Plan: Add dashboard visual evaluation criteria to DESIGN.md

## Overview

Append a `## Visual Evaluation Criteria` section to `claude/dashboard/DESIGN.md` after the existing `## Pattern Examples` section (currently ending at line 93). The new section contains a four-row criteria table (Information clarity, Consistency, Operational usefulness, Purposefulness) with Weight and What-to-evaluate columns, followed by a 2-4 sentence usage guidance paragraph referencing Playwright MCP. No existing content is modified.

## Tasks

### Task 1: Append Visual Evaluation Criteria section to DESIGN.md
- **Files**: `claude/dashboard/DESIGN.md`
- **What**: After line 93 (the final line of `## Pattern Examples`), append a blank line followed by a `## Visual Evaluation Criteria` heading, an introductory sentence, a markdown table with four rows (Information clarity/High, Consistency/High, Operational usefulness/Medium, Purposefulness/Low), and a usage guidance paragraph. The table columns are: Criterion, Weight, What to evaluate. Each row's evaluation description is adapted from the spec requirements. The usage paragraph mentions Playwright MCP (ticket 029), dashboard PR review, and feature spec acceptance criteria. It notes that evaluation reliability varies by criterion — consistency is most mechanically verifiable, purposefulness requires the most judgment.
- **Depends on**: none
- **Context**: The spec requires terse, directive prose matching DESIGN.md's existing style. `##` heading level. Table for structured reference data. The section name `## Visual Evaluation Criteria` must remain stable — downstream tickets 029 and 031 reference it. Content for each criterion row comes from spec requirement 2 and the research draft in research.md.
- **Verification**: `grep -c '## Visual Evaluation Criteria' claude/dashboard/DESIGN.md` outputs `1`; `grep -Ec 'Information clarity|Consistency|Operational usefulness|Purposefulness' claude/dashboard/DESIGN.md` outputs `4`; `grep -c 'Playwright' claude/dashboard/DESIGN.md` outputs at least `1`
- **Status**: [x] not started

### Task 2: Verify no existing content was modified
- **Files**: `claude/dashboard/DESIGN.md`
- **What**: Confirm that lines 1-93 of the file are unchanged from their pre-edit state. The spec explicitly requires additive-only changes.
- **Depends on**: [1]
- **Context**: The spec non-requirements state "No changes to existing DESIGN.md sections — additive only." A git diff restricted to the first 93 lines must show no deletions or modifications.
- **Verification**: `git diff claude/dashboard/DESIGN.md | grep -c '^-[^-]'` outputs `0` (no removed lines from existing content)
- **Status**: [x] not started

## Verification Strategy

After all tasks complete, run the spec's acceptance criteria:
1. `grep -c '## Visual Evaluation Criteria' claude/dashboard/DESIGN.md` -- must output `1`
2. `grep -Ec 'Information clarity|Consistency|Operational usefulness|Purposefulness' claude/dashboard/DESIGN.md` -- must output `4`
3. `grep -c 'Playwright' claude/dashboard/DESIGN.md` -- must output at least `1`
4. `git diff claude/dashboard/DESIGN.md | grep -c '^-[^-]'` -- must output `0` (no existing lines removed)
5. Visual review: the new section uses `##` heading, a markdown table, terse directive prose, and appears after `## Pattern Examples`
