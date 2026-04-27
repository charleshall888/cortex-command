# Review: trim-plan-approval-chat-output

## Stage 1: Spec Compliance

### Requirement 1: output-floors.md Approval Surface Floor table — PASS

The Approval Surface Floor table at `claude/reference/output-floors.md` lines 28-32 contains exactly three rows: **Produced**, **Value**, **Trade-offs**. The Veto surface and Scope boundaries rows have been removed. A prose note follows the table at line 34: "Items the user might want to veto and the list of explicit exclusions belong in the plan artifact itself, not in the chat approval summary — the summary surfaces only what the user needs to triage."

Acceptance criteria verification:
- `grep '| \*\*Veto surface\*\* \|'` in output-floors.md = 0 matches
- `grep '| \*\*Scope boundaries\*\* \|'` in output-floors.md = 0 matches

### Requirement 2: plan.md §4 inline bullet list — PASS

`skills/lifecycle/references/plan.md` §4 (User Approval, lines 247-254) lists only Produced and Trade-offs. The Veto surface and Scope boundaries bullets have been removed.

Acceptance criteria verification:
- `grep '- \*\*Veto surface\*\*'` in plan.md = 0 matches
- `grep '- \*\*Scope boundaries\*\*'` in plan.md = 0 matches

Note: The pre-existing discrepancy where Value is absent from plan.md §4 inline list but present in output-floors.md is explicitly called out as out-of-scope in the spec's Non-Requirements section.

### Requirement 3: plan.md §3 artifact template named sections — PASS

The plan artifact template in §3 (Write Plan Artifact) includes `## Veto Surface` at line 164 and `## Scope Boundaries` at line 167, both appearing after `## Verification Strategy` at line 161.

Acceptance criteria verification:
- `grep '## Veto Surface\|## Scope Boundaries'` in plan.md = 2 matches

### Requirement 4: specify.md §4 inline bullet list — PASS

`skills/lifecycle/references/specify.md` §4 (User Approval, lines 154-162) lists only Produced, Value, and Trade-offs. The Veto surface and Scope boundaries bullets have been removed.

Acceptance criteria verification:
- `grep 'Veto surface\|Scope boundaries'` in specify.md = 0 matches (entire file)

## Stage 2: Code Quality

### Naming conventions
Consistent with project patterns. The new `## Veto Surface` and `## Scope Boundaries` sections use the same PascalCase heading style as existing artifact template sections (`## Overview`, `## Tasks`, `## Verification Strategy`).

### Error handling
Not applicable — these are documentation edits to markdown reference files.

### Test coverage
Acceptance criteria are grep-based and all verified directly. No runtime tests apply to reference doc changes.

### Pattern consistency
- The prose note added after the Approval Surface Floor table mirrors the tone and structure of the note following the Phase Transition Floor table ("These fields are the minimum..."), maintaining consistent documentation voice.
- The new artifact template sections include bracketed placeholder descriptions in the same style as other template sections (e.g., `## Verification Strategy`).
- Both `## Veto Surface` and `## Scope Boundaries` are placed after `## Verification Strategy` as specified.

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
