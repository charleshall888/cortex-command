# Specification: Prevent agents from writing their own completion evidence

## Problem Statement

Overnight agents can write artifacts (log entries, status fields, marker files) and then check those same artifacts as proof of task completion. This self-sealing pattern produces false positives by construction — the verification always passes because the executing agent controls both the write and the read. One confirmed instance required human intervention to catch (retro 2026-04-02-1629). The general pattern has no systemic guard. This ticket adds plan-authoring conventions, plan review detection, and builder-level guardrails that reduce the likelihood of self-sealing verification appearing in new plans. These are documentation-layer defenses; they do not guarantee prevention on overnight-generated plans (Step 3b), which skip orchestrator review. A separate backlog item (R5) tracks the runtime trust gap.

## Requirements

1. **Plan template prohibition**: The plan phase reference (`skills/lifecycle/references/plan.md`) must include a Prohibited list item and a Constraints table row that explicitly forbid verification steps referencing artifacts the executing task creates for the purpose of satisfying verification. Acceptance criteria: `grep -A1 'Prohibited' skills/lifecycle/references/plan.md | grep -c 'self-sealing'` >= 1 (the term appears within the Prohibited section), AND `grep -B2 -A2 'self-sealing' skills/lifecycle/references/plan.md` shows at least two distinct locations (Prohibited list and Constraints table). Pass if both conditions met.

2. **P7 checklist item in orchestrator review**: The Post-Plan Checklist in `skills/lifecycle/references/orchestrator-review.md` must include a P7 row with a two-step check: (a) a mechanical cross-reference — does any task's Verification field reference a file or log entry that the same task creates in its Files list? (b) a guided judgment — if yes, is the referenced content the task's primary deliverable (benign) or an artifact created solely to satisfy the verification check (harmful self-sealing)? Step (b) is a judgment call, not a mechanical check; the P7 criteria must include operational guidance: "If the task's stated purpose is to create the artifact, the self-check is benign. If the task's purpose is to verify an external condition and the artifact is a side-channel for recording that verification, the self-check is harmful." Acceptance criteria: `grep 'P7.*self-sealing' skills/lifecycle/references/orchestrator-review.md` matches at least one line containing both "P7" and "self-sealing" in a table row. Pass if exit code = 0.

3. **Builder prompt guardrail**: The implement phase reference (`skills/lifecycle/references/implement.md`) must include an instruction telling builders not to write artifacts solely to satisfy their own verification check, and to flag self-sealing verification as a question in their exit report. Acceptance criteria: `grep -c 'self-sealing' skills/lifecycle/references/implement.md` >= 1, appearing in an instruction list item (not a comment or example). Pass if count >= 1.

4. **Overnight plan generation gap closure**: The Step 3b sub-agent prompt in `claude/overnight/prompts/orchestrator-round.md` must inline the self-sealing prohibition so overnight-generated plans inherit the convention even though sub-agents do not read the plan.md reference file. Acceptance criteria: `grep -B2 -A2 'self-sealing' claude/overnight/prompts/orchestrator-round.md` shows the term appearing within the Step 3b plan-generation prompt text. Pass if exit code = 0.

5. **Backlog item for exit report trust model**: A new backlog item must be created to address the `verification_passed` dead code in exit reports — either reading and acting on the field, or removing it from the schema. This is the runtime-layer complement to this ticket's documentation-layer defenses. Acceptance criteria: `grep -rl 'verification_passed' backlog/ | grep -v '025-'` returns at least one file (a backlog item other than this one that discusses the verification_passed field), pass if exit code = 0.

## Non-Requirements

- **No runtime enforcement**: This ticket does not add Python code to the plan parser, batch runner, or overnight pipeline. Enforcement is at the prompt/documentation layer. The overnight Step 3b path is a known accepted risk at this scope — R4 is the only defense on that surface, and it relies on sub-agent compliance with an inlined prohibition.
- **No separate verifier agent**: No new agent type is added for post-task verification. Token cost is disproportionate for a personal tooling project.
- **No provenance tracking infrastructure**: No manifest files, hash chains, or per-file write tracking.
- **No changes to exit report processing**: The `verification_passed` field and `_read_exit_report()` behavior are unchanged. That concern is tracked by the new backlog item (R5).
- **No modification of existing plans**: Existing lifecycle plans are not retroactively audited or rewritten. The convention applies to new plans going forward.

## Edge Cases

- **Benign self-check pattern**: A task creates a deliverable file (e.g., `requirements/observability.md`) and verification confirms the file has correct content (sections, line count). This is NOT self-sealing — the file is the intended deliverable, not manufactured evidence. P7 step (b) distinguishes this using the operational guidance: "If the task's stated purpose is to create the artifact, the self-check is benign."
- **Protocol-mandated state writes**: A task appends a `phase_transition` event to `events.log` as part of lifecycle protocol, and verification checks for that event. This is a boundary case. P7 step (b) guidance applies: the task's purpose is to verify/transition state, and the event is a side-channel recording of that transition. P7 should flag this for human review rather than auto-rejecting, since the judgment is ambiguous.
- **Overnight-generated plans without review**: Plans generated by Step 3b sub-agents skip orchestrator review entirely. R4 (inlined prohibition) is the only defense. If the sub-agent ignores R4, there is no secondary catch before overnight execution. This is an accepted risk at the current scope — the runtime trust gap is tracked by the backlog item (R5).
- **Simple-tier features skipping review**: Simple-tier/low-criticality features may skip orchestrator review. The plan template prohibition (R1) and builder guardrail (R3) are the defenses at this surface; P7 (R2) does not apply.

## Technical Constraints

- All changes are prompt/documentation edits to existing reference files. No new files except the backlog item (R5).
- The plan Prohibited list follows the existing single-line bullet format (plan.md lines 59-65).
- The P7 row follows the existing `| P# | Item | Criteria |` table format (orchestrator-review.md lines 148-157).
- The Step 3b prompt in orchestrator-round.md is a verbatim string passed to sub-agents — changes must be inlined in the prompt text, not as external file references.
- P7 step (b) is a judgment call, not a mechanical check. It is less precise than P1-P6. This is inherent to the classification problem — the benign/harmful boundary depends on task intent, which cannot be resolved syntactically. The operational guidance reduces ambiguity but does not eliminate it.
