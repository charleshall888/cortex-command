# Plan: prevent-agents-from-writing-their-own-completion-evidence

## Overview

Add self-sealing verification guards at four documentation/prompt surfaces: plan template Prohibited list and Constraints table, P7 checklist item in orchestrator review, builder prompt guardrail in implement reference, and inlined prohibition in overnight Step 3b prompt. Also create a backlog item for the exit report trust model. All changes are prompt/documentation edits to existing files.

## Tasks

### Task 1: Add self-sealing prohibition to plan template Prohibited list
- **Files**: `skills/lifecycle/references/plan.md`
- **What**: Add a new bullet to the Prohibited list (after line 64) that forbids verification steps referencing artifacts the executing task creates solely to satisfy verification. This is the authoring-time convention.
- **Depends on**: none
- **Complexity**: simple
- **Context**: The Prohibited section is at lines 58-64 of `skills/lifecycle/references/plan.md`. Current items prohibit function bodies, import statements, error handling, complete test code, copy-paste code, and prose-only verification. The new item follows the same single-line bullet format. Example wording: "Verification steps that reference artifacts (files, log entries, status fields) the executing task creates solely for the purpose of satisfying verification — this is self-sealing and passes tautologically."
- **Verification**: `grep -A1 'Prohibited' skills/lifecycle/references/plan.md | grep -c 'self-sealing'` >= 1, pass if count >= 1.
- **Status**: [x] complete

### Task 2: Add self-sealing Constraints table row to plan template
- **Files**: `skills/lifecycle/references/plan.md`
- **What**: Add a new row to the Constraints table (the `| Thought | Reality |` table at lines 259-264) that addresses the "agent can verify by checking what it just wrote" misconception. The row must contain the term "self-sealing".
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: The Constraints table at lines 259-264 has 4 existing rows in `| Thought | Reality |` format. The new row follows the same pattern. Example: `| "The agent can verify by checking the file it just wrote" | Verification that checks an artifact the same task creates solely for verification is self-sealing — it passes tautologically. Use test commands, pre-existing state, or prior-task outputs instead. |`. Task 1 must complete first — both tasks edit the same file and must be serialized to avoid a parallel-write conflict in the overnight pipeline.
- **Verification**: `grep -c 'self-sealing' skills/lifecycle/references/plan.md` >= 2 (one from Prohibited list added by Task 1, one from Constraints table added by this task). Additionally, `grep -B1 'self-sealing.*tautologic' skills/lifecycle/references/plan.md` must show a line containing `|` (confirming placement in the Constraints table row, not just the Prohibited section). Pass if both conditions met.
- **Status**: [x] complete

### Task 3: Add P7 checklist item to orchestrator review
- **Files**: `skills/lifecycle/references/orchestrator-review.md`
- **What**: Add a P7 row to the Post-Plan Checklist table (after P6 at line 157) that performs a two-step check for self-sealing verification: (a) cross-reference Files and Verification fields, (b) guided judgment with operational criteria.
- **Depends on**: none
- **Complexity**: simple
- **Context**: The Post-Plan Checklist table at lines 150-157 of `skills/lifecycle/references/orchestrator-review.md` uses `| # | Item | Criteria |` format. P6 is the last row at line 157. The P7 Criteria text must include the operational guidance from the spec: "If the task's stated purpose is to create the artifact, the self-check is benign. If the task's purpose is to verify an external condition and the artifact is a side-channel for recording that verification, the self-check is harmful — flag it as self-sealing."
- **Verification**: `grep 'P7.*self-sealing' skills/lifecycle/references/orchestrator-review.md` matches at least one line, pass if exit code = 0.
- **Status**: [x] complete

### Task 4: Add builder guardrail to implement reference
- **Files**: `skills/lifecycle/references/implement.md`
- **What**: Add an instruction (item 6) to the builder prompt template's Instructions list (after item 5 at line 93) telling builders not to write artifacts solely to satisfy their own verification check, and to flag self-sealing verification as a question in their exit report. The instruction must appear in the numbered instruction list, not in a comment or example block.
- **Depends on**: none
- **Complexity**: simple
- **Context**: The Instructions list in the builder prompt template at lines 88-96 of `skills/lifecycle/references/implement.md` has 5 items. Item 5 says "Report what you did and any issues encountered." The new item 6 goes after item 5, inside the `## Instructions` numbered list (not inside the code fence template or any example block). Example: "6. Do not write files or artifacts solely to satisfy your own verification check. If a verification step requires checking something you created in this task for the purpose of satisfying verification (not as the task's primary deliverable), flag it as self-sealing in your exit report rather than self-certifying."
- **Verification**: `grep -n 'self-sealing' skills/lifecycle/references/implement.md` shows the match on a line within the Instructions section (between lines 88-97, i.e., after `## Instructions` and before the closing code fence). Pass if at least one match appears in that range.
- **Status**: [x] complete

### Task 5: Inline self-sealing prohibition in overnight Step 3b prompt
- **Files**: `claude/overnight/prompts/orchestrator-round.md`
- **What**: Add the self-sealing prohibition to the Step 3b sub-agent prompt (lines 226-245) so overnight-generated plans inherit the convention. Insert after the plan format instructions (line 237) and before the deferral instruction (line 239).
- **Depends on**: none
- **Complexity**: simple
- **Context**: The Step 3b prompt at lines 226-245 of `claude/overnight/prompts/orchestrator-round.md` is a verbatim string passed to sub-agents. It currently says "Follow the lifecycle plan phase protocol..." and describes the plan format. The prohibition should be inlined as an additional instruction, e.g.: "Prohibited in verification steps: self-sealing verification — do not write verification fields that check artifacts the executing task creates solely to satisfy verification (e.g., writing a log entry then checking for it). Verification must reference independently observable state: test output, pre-existing files, or artifacts from prior tasks."
- **Verification**: `grep -B2 -A2 'self-sealing' claude/overnight/prompts/orchestrator-round.md` shows the term within the Step 3b prompt text (between the "You are generating an implementation plan" header and the "If the spec is too ambiguous" deferral instruction), pass if exit code = 0.
- **Status**: [x] complete

### Task 6: Create backlog item for exit report trust model
- **Files**: `backlog/` (new file via `create-backlog-item` CLI)
- **What**: Create a new backlog item addressing the `verification_passed` dead code in exit reports. The item should describe the problem (field collected but never read by `_read_exit_report()`), the options to investigate (read and act on it, or remove it), and link back to this ticket (025) as context.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Use the `create-backlog-item` CLI tool to create the item. This handles ID assignment, UUID generation, filename convention (`NNN-slug.md` with zero-padded ID), event logging, and index regeneration. Invoke as: `create-backlog-item --title "Address verification_passed dead code in exit reports" --type chore --priority medium --status backlog --tags "overnight,reliability,verification"`. After the file is created, edit it to add a body section describing: (1) the problem — `verification_passed` is written by builder agents in `claude/pipeline/prompts/implement.md` (lines 81, 93, 104) but `_read_exit_report()` in `batch_runner.py` (lines 404-446) extracts only `action`, `reason`, and `question`; (2) options to investigate — either read the field and pause tasks where action=complete but verification_passed=false (~10 lines of Python), or remove the field from the exit report schema; (3) context link — discovered during ticket 025 research. Use exploratory framing for implementation approaches ("options to investigate" not "proposed fix").
- **Verification**: `grep -rl 'verification_passed' backlog/ | grep -v '025-'` returns at least one file, pass if exit code = 0.
- **Status**: [x] complete

## Verification Strategy

After all tasks are complete, verify the full feature end-to-end using the spec's acceptance criteria:

1. **R1 (plan template)**: `grep -A1 'Prohibited' skills/lifecycle/references/plan.md | grep -c 'self-sealing'` >= 1, AND `grep -B2 -A2 'self-sealing' skills/lifecycle/references/plan.md` shows at least two distinct locations (Prohibited list and Constraints table). Pass if both conditions met.
2. **R2 (orchestrator review)**: `grep 'P7.*self-sealing' skills/lifecycle/references/orchestrator-review.md` matches at least one line containing both "P7" and "self-sealing" in a table row. Pass if exit code = 0.
3. **R3 (builder guardrail)**: `grep -c 'self-sealing' skills/lifecycle/references/implement.md` >= 1, appearing in the Instructions numbered list (not a comment or example). Pass if count >= 1 and placement is within the Instructions section.
4. **R4 (overnight Step 3b)**: `grep -B2 -A2 'self-sealing' claude/overnight/prompts/orchestrator-round.md` shows the term appearing within the Step 3b plan-generation prompt text. Pass if exit code = 0.
5. **R5 (backlog item)**: `grep -rl 'verification_passed' backlog/ | grep -v '025-'` returns at least one file. Pass if exit code = 0.
6. **Regression**: Run `just test` to confirm no existing tests are broken by the documentation changes.
