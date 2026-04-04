# Review: prevent-agents-from-writing-their-own-completion-evidence

## Stage 1: Spec Compliance

### R1 — Plan template prohibition
**Rating**: PARTIAL

The self-sealing prohibition appears in two distinct locations in `skills/lifecycle/references/plan.md`:
- **Prohibited list** (line 65): "Verification steps that reference artifacts ... this is self-sealing and passes tautologically"
- **Hard Gate / Constraints table** (line 266): `| "The agent can verify by checking the file it just wrote" | Verification that checks an artifact the same task creates solely for verification is self-sealing ... |`

Both the Prohibited list item and the Constraints table row are present and correctly worded. The second acceptance criterion (`grep -B2 -A2` showing two distinct locations) is met.

The first acceptance criterion (`grep -A1 'Prohibited' | grep -c 'self-sealing'` >= 1) returns 0. This is because the self-sealing item is the 7th bullet in the Prohibited list (7 lines after the heading), while `-A1` only captures 1 line after each heading match. This is a deficiency in the spec's grep pattern, not the implementation -- the item is correctly placed in the Prohibited section. Scoring PARTIAL because the mechanical check fails even though the intent is fully satisfied.

Additionally, `plan.md` has two Prohibited lists: the one inside the Plan Agent Prompt Template (lines 58-65, used for competing plans on critical features) and the one in the main Code Budget section (lines 213-218, used for the standard single-plan flow). The self-sealing prohibition was added only to the first list, not the second. Agents using the standard (non-critical) plan flow will not see the self-sealing prohibition in their Prohibited list, only in the Hard Gate table at the bottom. This is an inconsistency that weakens the defense for the most common plan authoring path.

### R2 — P7 checklist item in orchestrator review
**Rating**: PASS

The P7 row at line 158 of `skills/lifecycle/references/orchestrator-review.md` includes:
- (a) Mechanical cross-reference: "cross-reference the Verification field against the Files list: does Verification reference an artifact that the same task creates?"
- (b) Guided judgment with operational guidance: "if the task's stated purpose is to create that artifact (it is the primary deliverable), the self-check is benign. If the task's purpose is to verify an external condition and the artifact is a side-channel for recording that verification, the self-check is harmful -- flag it as self-sealing."

The acceptance criterion (`grep 'P7.*self-sealing'` returning exit code 0) is met. The operational guidance language matches the spec's required text.

### R3 — Builder prompt guardrail
**Rating**: PASS

Line 94 of `skills/lifecycle/references/implement.md` adds item 6 to the Instructions numbered list within the Builder Prompt Template:
> 6. Do not write files or artifacts solely to satisfy your own verification check. If a verification step requires checking something you created in this task for the purpose of satisfying verification (not as the task's primary deliverable), flag it as self-sealing in your exit report rather than self-certifying.

This appears in the numbered instruction list (not a comment or example). `grep -c 'self-sealing'` returns 1. Acceptance criteria met.

### R4 — Overnight plan generation gap closure
**Rating**: PASS

Lines 238-243 of `claude/overnight/prompts/orchestrator-round.md` inline the prohibition within the Step 3b sub-agent prompt:
> Prohibited in verification steps: self-sealing verification -- do not write verification fields that check artifacts the executing task creates solely to satisfy verification (e.g., writing a log entry then checking for it). Verification must reference independently observable state: test output, pre-existing files, or artifacts from prior tasks.

The text is within the Step 3b prompt code block (between "You are generating an implementation plan" and the deferral instruction). `grep -B2 -A2 'self-sealing'` confirms placement. Acceptance criteria met.

### R5 — Backlog item for exit report trust model
**Rating**: PASS

`backlog/036-address-verification-passed-dead-code-in-exit-reports.md` exists and contains:
- Problem description: `verification_passed` field written by builders but never read by `_read_exit_report()`
- Investigation options: read and act on the field, or remove it from the schema
- Context link to ticket 025

`grep -rl 'verification_passed' backlog/ | grep -v '025-'` returns the file. Acceptance criteria met.

## Stage 2: Code Quality

### Naming conventions
Consistent. The P7 row follows the existing `| P# | Item | Criteria |` format. The Prohibited list bullet follows existing single-line format. The builder instruction follows existing numbered-list format. The backlog item follows the standard YAML frontmatter + markdown body convention.

### Error handling
Not applicable -- all changes are documentation/prompt edits with no runtime behavior.

### Test coverage
The plan's verification steps were executed during implementation. The spec's acceptance criteria are met for R2-R5. R1's grep criterion technically fails due to the spec's own `-A1` limitation, but the underlying requirement (self-sealing term in Prohibited section and Constraints table) is satisfied.

### Pattern consistency
One inconsistency noted: the self-sealing prohibition was added to the Prohibited list inside the Plan Agent Prompt Template (for competing plans) but not to the Prohibited list in the Code Budget section (for the standard plan flow). Both lists existed before this change with identical content; now they diverge. This is a minor gap -- the Hard Gate table at the bottom of plan.md covers the standard flow path, but the Prohibited list divergence could confuse agents or future editors.

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

The implementation adds documentation-layer guardrails (plan conventions, review checklist items, builder instructions, prompt inlining) and a backlog item. All changes align with the project philosophy (complexity must earn its place, file-based state, iterative improvement) and the pipeline requirements (session orchestration, feature execution). No new runtime behavior is introduced that would require updating requirements docs.

## Verdict

```json
{
  "verdict": "APPROVED",
  "cycle": 1,
  "issues": [
    "plan.md Prohibited list inconsistency: self-sealing item added to the competing-plans Prohibited list (line 65) but not to the main-flow Code Budget Prohibited list (line 213-218) — both lists should carry the same prohibitions for consistency",
    "R1 acceptance criterion grep pattern (grep -A1) is too narrow for the actual placement (7th bullet) — the spec grep fails despite correct implementation; not blocking but the spec criterion should be corrected if reused"
  ],
  "requirements_drift": "none"
}
```
