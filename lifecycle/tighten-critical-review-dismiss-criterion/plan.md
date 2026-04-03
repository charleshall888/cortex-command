# Plan: tighten-critical-review-dismiss-criterion

## Overview

One surgical sentence appended to the Dismiss definition in CR's Step 4. No structural changes.

## Tasks

### Task 1: Add anchor check to Dismiss definition

- **Files**: `skills/critical-review/SKILL.md`
- **What**: Append the anchor check sentence to the Dismiss paragraph in Step 4.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Target: Step 4, Dismiss definition, currently: "the objection is already addressed in the artifact, misreads the stated constraints, or would expand scope in a direction clearly outside the requirements. State the dismissal reason briefly."
  - Append: "**Anchor check**: if your dismissal reason cannot be pointed to in the artifact text and lives only in your memory of the conversation, treat it as Ask instead — that is anchoring, not a legitimate dismissal."
- **Verification**: Read `skills/critical-review/SKILL.md`. Confirm the Dismiss definition contains the anchor check sentence, and the existing three conditions are unchanged.
- **Status**: [x] complete (commit e2c8540)

## Verification Strategy

`grep "Anchor check" skills/critical-review/SKILL.md` — confirms sentence is present.
