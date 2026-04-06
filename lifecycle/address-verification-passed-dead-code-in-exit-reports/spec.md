# Specification: Address verification_passed dead code in exit reports

## Problem Statement

The `verification_passed` and `committed` boolean fields are defined in the overnight builder exit report schema (`claude/pipeline/prompts/implement.md`) and written by every builder agent, but `_read_exit_report()` in `batch_runner.py` extracts only `action`, `reason`, and `question`. No Python code reads either field. This creates a false impression that verification status and commit status are tracked when they are not. Removing the dead fields makes the exit report schema honest and reduces prompt token waste.

## Requirements

1. **Remove `verification_passed` from the exit report schema table**: The row at line 83 of `claude/pipeline/prompts/implement.md` defining `verification_passed` as a required boolean field is deleted. Acceptance criteria: `grep -c 'verification_passed' claude/pipeline/prompts/implement.md` = 0.

2. **Remove `committed` from the exit report schema table**: The row at line 82 of `claude/pipeline/prompts/implement.md` defining `committed` as a required boolean field is deleted. Acceptance criteria: `grep -c 'committed.*boolean' claude/pipeline/prompts/implement.md` = 0.

3. **Remove `verification_passed` from both exit report examples**: The field is removed from the "complete" example (line 95) and the "question" example (line 106). Acceptance criteria: `grep -c 'verification_passed' claude/pipeline/prompts/implement.md` = 0 (covered by R1).

4. **Remove `committed` from both exit report examples**: The field is removed from the "complete" example (line 94) and the "question" example (line 105). Acceptance criteria: `grep -c '"committed"' claude/pipeline/prompts/implement.md` = 0.

5. **No Python code changes**: `_read_exit_report()` in `batch_runner.py` already ignores unknown fields via `data.get()`. No changes to Python source or test files. Acceptance criteria: `git diff --name-only` shows only `claude/pipeline/prompts/implement.md` modified.

6. **Exit report examples remain valid JSON structure**: After removal, both example exit reports contain only the fields that `_read_exit_report()` actually reads (`action`, `reason`, `question`). Acceptance criteria: each example block in the modified file contains exactly the fields appropriate for its action type (complete: `action`, `reason`; question: `action`, `reason`, `question`).

## Non-Requirements

- **Not reading or acting on `verification_passed`**: Research determined that self-reported verification has near-zero trust value. An agent that fabricates `action: "complete"` will also fabricate `verification_passed: true`. Runtime verification is handled externally by the smoke test gate and SHA comparison circuit breaker.
- **Not adding a replacement field**: Ticket 025 (prevent agents from writing their own completion evidence) and ticket 021 (evaluator rubric) address the external verification path. This ticket only removes dead code.
- **Not changing `_read_exit_report()` return type or behavior**: The function already correctly ignores these fields.
- **Not changing `conflict.py`'s separate `_read_exit_report()`**: It uses a completely different exit report schema that never included these fields.

## Edge Cases

- **In-flight overnight sessions**: A builder agent dispatched before the prompt change may still write `verification_passed` and `committed` in its exit report. This is harmless — `_read_exit_report()` uses `data.get()` for known keys only and silently ignores all other fields.
- **Agent hallucination of removed fields**: After removal, agents may still include these fields from training data or cached context. Also harmless for the same reason.
- **Line 39 reference to "committed"**: `implement.md` line 39 contains the phrase "When that task is done and committed" — this is natural language describing the workflow, not a reference to the exit report field. It must not be removed.

## Technical Constraints

- **Single file change**: Only `claude/pipeline/prompts/implement.md` is modified. The change is prompt-only — no Python, no tests, no infrastructure.
- **Architectural decision**: Verification status is validated externally (SHA comparison, test gates, smoke test), not via agent self-report. The `action` field remains the sole behavioral signal from exit reports, complemented by the pipeline's deferral system (`action: "question"`) per `requirements/pipeline.md`.
