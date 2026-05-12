# Plan: trim-plan-approval-chat-output

## Overview

Three targeted file edits, all independent. Remove the Veto surface and Scope boundaries table rows from `output-floors.md`, add `## Veto Surface` and `## Scope Boundaries` sections to the plan.md artifact template, remove the corresponding bullet entries from plan.md's and specify.md's approval lists.

## Tasks

### Task 1: Remove Veto surface and Scope boundaries from output-floors.md
- **Files**: `claude/reference/output-floors.md`
- **What**: Delete the Veto surface and Scope boundaries rows from the Approval Surface Floor table. Add a short prose note after the table stating that those fields belong in the plan artifact, not the chat summary. Use phrasing that does not include the exact bold-formatted strings `**Veto surface**` or `**Scope boundaries**`.
- **Depends on**: none
- **Complexity**: simple
- **Context**: The Approval Surface Floor table is around lines 28–36 of the file. Current rows: Produced, Value, Trade-offs, Veto surface, Scope boundaries. After edit: Produced, Value, Trade-offs. The note goes on a new line after the closing `|` of the table, before the next paragraph (`The approval surface floor supplements...`).
- **Verification**: `grep -c '| \*\*Veto surface\*\* \|| | \*\*Scope boundaries\*\* |' claude/reference/output-floors.md` — pass if output = 0
- **Status**: [x] complete

### Task 2: Update plan.md — add artifact sections and remove approval bullets
- **Files**: `skills/lifecycle/references/plan.md`
- **What**: Two edits to the same file: (a) add `## Veto Surface` and `## Scope Boundaries` as named sections in the §3 artifact template, immediately after the `## Verification Strategy` section closing; (b) remove the `- **Veto surface**` and `- **Scope boundaries**` bullet entries from the §4 User Approval bullet list.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - §3 artifact template: the `## Verification Strategy` section is the last section in the plan.md template block (around line 162). Add after it:
    ```
    ## Veto Surface
    [Design choices, scope calls, or constraints the user might want to revisit before implementation begins. "None" if nothing is controversial.]
    
    ## Scope Boundaries
    [What is explicitly excluded from this feature. Maps to the spec's Non-Requirements section.]
    ```
  - §4 User Approval bullet list: currently lists Produced, Trade-offs, Veto surface, Scope boundaries (lines ~244–248). Remove the Veto surface and Scope boundaries lines. The surviving bullets are Produced and Trade-offs.
- **Verification**:
  - `grep -c '- \*\*Veto surface\*\*\|- \*\*Scope boundaries\*\*' skills/lifecycle/references/plan.md` — pass if output = 0
  - `grep -c '## Veto Surface\|## Scope Boundaries' skills/lifecycle/references/plan.md` — pass if output = 2
- **Status**: [x] complete

### Task 3: Remove Veto surface and Scope boundaries from specify.md §4
- **Files**: `skills/lifecycle/references/specify.md`
- **What**: Remove the `- **Veto surface**` and `- **Scope boundaries**` bullet entries from the §4 User Approval bullet list. The surviving bullets are Produced, Value, and Trade-offs.
- **Depends on**: none
- **Complexity**: simple
- **Context**: §4 User Approval bullet list is around lines 157–162. Currently lists Produced, Value, Trade-offs, Veto surface, Scope boundaries. Remove the last two.
- **Verification**: `grep -c 'Veto surface\|Scope boundaries' skills/lifecycle/references/specify.md` — pass if output = 0
- **Status**: [x] complete

## Verification Strategy

After all three tasks complete, run the three acceptance criteria from the spec in sequence:
1. `grep -c '| \*\*Veto surface\*\* \|| | \*\*Scope boundaries\*\* |' claude/reference/output-floors.md` = 0
2. `grep -c '- \*\*Veto surface\*\*\|- \*\*Scope boundaries\*\*' skills/lifecycle/references/plan.md` = 0
3. `grep -c '## Veto Surface\|## Scope Boundaries' skills/lifecycle/references/plan.md` = 2
4. `grep -c 'Veto surface\|Scope boundaries' skills/lifecycle/references/specify.md` = 0

All four must pass before closing the feature.

## Veto Surface
- Task 2 combines two edits to the same file (§3 and §4 of plan.md). Splitting them into separate tasks would add no value — they don't conflict and neither is a prerequisite for the other.
- No Trade-offs section is being added to the plan.md artifact template (only Veto Surface and Scope Boundaries are added). This matches what was asked; Trade-offs stays in chat output only.

## Scope Boundaries
- `specify.md` §3 artifact template is not touched — Non-Requirements and Open Decisions provide equivalent coverage
- `orchestrator-review.md` is not touched
- Historical lifecycle artifacts with grep checks referencing these strings are not touched
- The pre-existing Value discrepancy in `plan.md` §4 is out of scope
