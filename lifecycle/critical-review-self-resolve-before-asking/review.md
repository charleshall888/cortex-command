# Review: critical-review-self-resolve-before-asking

## Stage 1: Spec Compliance

### Requirement 1: Self-resolution instruction in Step 4

**Rating: PASS**

The paragraph is inserted at line 187 of `skills/critical-review/SKILL.md`, between the Ask definition (line 185, ending "Hold these for the end.") and the "After classifying all objections:" block (line 189). Placement is exactly as specified.

Content check against R1 sub-requirements:

- **Specific investigation steps**: Present. "Re-read the relevant artifact sections, check related codebase files, and consult any project context loaded in Step 2a."
- **Bounded scope**: Present. "a brief check, not an exhaustive search" and the fallback "if the answer isn't evident... classify as Ask" is captured via "Uncertainty still defaults to Ask."
- **Tighter evidence boundary**: Present. "supported by verifiable evidence -- a specific file path, explicit artifact text, or documented project context" and "Do not resolve based on inferences from general principles."
- **Anchor check**: Present. Verbatim: "if your resolution relies on conclusions from your prior work on this artifact rather than new evidence found during the check, treat it as Ask -- that is anchoring, not resolution."
- **Preserved burden of proof**: The sentence "Uncertainty still defaults to Ask" preserves the default. The Apply bar at line 195 is unchanged (verified by grep: exact phrase "Apply when and only when the fix is unambiguous" appears exactly once).

AC verification: `grep -c 'Anchor check'` returns 2 (Dismiss + self-resolution). `grep -c 'brief check'` returns 1. `grep -c 'verifiable evidence'` returns 1. All pass.

### Requirement 2: Clarify-critic parallel update

**Rating: PASS**

Three changes verified in `skills/lifecycle/references/clarify-critic.md`:

**(a) Sync comment update (line 60)**: Updated to include "including the self-resolution step". Matches plan verbatim.

**(b) Self-resolution paragraph (line 68)**: Inserted between Ask definition (line 66) and Apply bar (line 70). Adaptations verified:

- **Context difference**: "Re-read the source material and confidence assessment" (not "relevant artifact sections"). "consult any requirements context loaded in clarify S2" (not "project context loaded in Step 2a"). Correct adaptation.
- **Apply semantics**: "reclassify: as Apply (revising the affected confidence dimension accordingly)" -- correctly reframes Apply in terms of confidence dimension revision.
- **Merge order**: Self-resolution runs after classification and before the Ask-to-Q&A Merge Rule. Trailing sentence "Surviving Ask items flow into the Ask-to-Q&A Merge Rule as before" confirms this.
- **Disposition counts**: Event logging note at line 99 states "Disposition counts reflect post-self-resolution values" with explicit explanation of count adjustments.

**(c) Event logging note (line 99)**: Present. Specifies that `applied_fixes` includes fixes from both initial Apply dispositions and self-resolution reclassifications.

AC verification: `grep -c 'self-resolution\|anchor check'` returns 3 (>= 1). Pass.

## Stage 2: Code Quality

### Naming conventions

Consistent. "Self-resolution" terminology matches the spec and is used consistently across both files. The anchor check pattern mirrors the existing Dismiss anchor check in SKILL.md.

### Error handling

N/A -- these are prose instruction changes, not executable code. The instructions degrade gracefully: if self-resolution finds nothing, the objection remains Ask. If the orchestrator's resolution relies on anchoring, the anchor check catches it.

### Test coverage

Plan verification steps all pass:
- `grep -c 'Anchor check' SKILL.md` = 2 (expected 2)
- `grep -c 'brief check' SKILL.md` = 1 (expected >= 1)
- `grep -c 'verifiable evidence' SKILL.md` = 1 (expected >= 1)
- `grep -c 'self-resolution' clarify-critic.md` = 3 (expected >= 3)
- `grep -c 'Anchor check' clarify-critic.md` = 1 (expected >= 1)
- `grep -c 'verifiable evidence' clarify-critic.md` = 1 (expected >= 1)
- Apply bar unchanged in both files (grep count = 1 each)

### Pattern consistency

The self-resolution paragraph follows the same structural pattern as other disposition instructions in Step 4: bold lead phrase, instruction body, anchor check at the end. The clarify-critic adaptation follows the established pattern of reproducing critical-review's framework with context-appropriate substitutions, as documented in the sync comment.

### Non-requirements verified

- No fresh agent dispatch: self-resolution is inline, as specified.
- No formal rubric: criteria are embedded in the paragraph.
- No event logging in critical-review: confirmed, only clarify-critic's event logging was updated.
- Apply and Dismiss definitions unchanged in both files: confirmed by diff (only additions, no modifications to existing text).
- Steps 2c and 2d unchanged: confirmed (diff shows changes only in Step 4 area of SKILL.md).

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Verdict

```json
{
  "verdict": "APPROVED",
  "cycle": 1,
  "issues": [],
  "requirements_drift": "none"
}
```
