# Plan: Address verification_passed dead code in exit reports

## Overview

Remove the dead `verification_passed` and `committed` fields from the overnight builder exit report schema and examples in `claude/pipeline/prompts/implement.md`. Single-file, prompt-only change — no Python or test modifications.

## Tasks

### Task 1: Remove dead fields from exit report schema and examples
- **Files**: `claude/pipeline/prompts/implement.md`
- **What**: Delete the `committed` and `verification_passed` rows from the exit report schema table, and delete the corresponding key-value lines from both the "complete" and "question" example JSON blocks.
- **Depends on**: none
- **Complexity**: simple
- **Context**: The exit report schema table starts at line 79 of `claude/pipeline/prompts/implement.md`. The two rows to remove are at lines 82 (`committed`) and 83 (`verification_passed`). The "complete" example block contains `"committed": true` at line 94 and `"verification_passed": true` at line 95. The "question" example block contains `"committed": false` at line 105 and `"verification_passed": false` at line 106. Line 39 contains the phrase "done and committed" in natural language — this is NOT a reference to the exit report field and must be left unchanged. After removal, the schema table should have 3 rows (action, reason, question) and each example should contain only the fields that `_read_exit_report()` in `batch_runner.py` actually reads.
- **Verification**: `grep -c 'verification_passed' claude/pipeline/prompts/implement.md` = 0 — pass if count = 0. `grep -c '"committed"' claude/pipeline/prompts/implement.md` = 0 — pass if count = 0.
- **Status**: [x] done

## Verification Strategy

Run the two grep checks from Task 1 to confirm both fields are fully removed. Then visually confirm the exit report schema table has exactly 3 field rows (action, reason, question) and both example blocks contain only the fields appropriate for their action type. No test suite changes needed — `_read_exit_report()` never read these fields.
