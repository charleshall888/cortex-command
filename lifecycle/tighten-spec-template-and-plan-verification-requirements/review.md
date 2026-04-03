# Review: tighten-spec-template-and-plan-verification-requirements

## Stage 1: Spec Compliance

### R1 — S1 Criteria tightened in orchestrator-review.md
**Rating**: PASS

The S1 Criteria cell (line 140) contains:
- The phrase "binary-checkable" (grep count = 2, requirement >= 1)
- The three-part condition: (a) runnable command with observable output and explicit pass/fail, (b) observable state naming specific file path, string/pattern, and expected result, (c) "Interactive/session-dependent: [one-sentence rationale]"
- Explicit statement that prose criteria do not pass even if they avoid subjective language

All acceptance criteria met.

### R2 — S1 exception path consistent with P4
**Rating**: PASS

The phrase "Interactive/session-dependent:" appears in both the S1 row (line 140) and the P4 row (line 155) of orchestrator-review.md. Both use the identical annotation format: `Interactive/session-dependent: [one-sentence rationale explaining why a command is not possible]`. grep count = 2, requirement >= 2.

All acceptance criteria met.

### R3 — P4 Criteria tightened in orchestrator-review.md
**Rating**: PASS

The P4 Criteria cell (line 155) contains:
- The same three-part condition as S1: (a) runnable command + output + pass/fail, (b) observable state with specific file/pattern/result, (c) "Interactive/session-dependent" annotation
- Explicit statement that prose-only Verification fields do not pass, with examples: "verify it works" and "confirm the section was added"

All acceptance criteria met.

### R4 — specify.md Requirements template updated
**Rating**: PASS

The Requirements section template in specify.md section 3 (line 118) now reads:
```
1. [Requirement]: [Acceptance criteria -- binary-checkable: (a) command + expected output + pass/fail (e.g., "`just test` exits 0, pass if exit code = 0"), (b) observable state naming specific file and pattern (e.g., "`grep -c 'keyword' path/file` = 1"), or (c) "Interactive/session-dependent: [rationale]" if a command check is not possible]
```

Contains "binary-checkable" (grep count = 1, requirement >= 1), concrete examples, and the exception annotation format.

All acceptance criteria met.

### R5 — plan.md both templates updated
**Rating**: PARTIAL

**What passes**:
- `grep -c 'Interactive/session-dependent' plan.md` = 3 (requirement >= 2). The annotation appears in both the section 1b competing-plan template (line 81) and the section 3 standard template (lines 146, 155).
- `grep -c 'prose descriptions' plan.md` = 2 (requirement >= 1). Appears in the section 1b Prohibited list (line 64) and as a blockquote note after the section 3 template (line 164).
- The section 1b Prohibited list is genuinely extended with a new entry: "Verification fields that consist only of prose descriptions requiring human judgment to evaluate."
- The section 3 template has an equivalent structural note as a blockquote after the code fence.

**What is borderline**:
- The spec's detailed AC states: `grep -c 'Prohibited' plan.md` should return >= current count + 1. The pre-existing count was 2 (one "Prohibited:" header in section 1b, one in section 3 Code Budget). The current count is still 2 because the new entry extends the existing list without adding a new line containing the word "Prohibited." The list extension is substantively correct -- the new prohibition entry is properly co-located under the section 1b "### Prohibited:" heading. The grep-count metric is a proxy that does not capture list-item additions under an existing heading. The intent of R5 (prohibiting prose-only Verification fields) is fully met; only the specific grep counter does not increment.

## Stage 2: Code Quality

### Naming Conventions
Consistent. S1 was renamed from "Acceptance criteria are objectively evaluable" to "Binary-checkable acceptance criteria." P4 was renamed from "Verification steps are actionable" to "Binary-checkable verification steps." Both names accurately reflect the tightened criteria and follow the checklist's existing naming pattern.

### Error Handling
Not applicable -- these are documentation/template changes with no runtime behavior.

### Test Coverage
The plan's verification steps (grep-based checks) all pass:
- `grep -c 'binary-checkable' orchestrator-review.md` = 2
- `grep -c 'Interactive/session-dependent' orchestrator-review.md` = 2
- `grep -c 'binary-checkable' specify.md` = 1
- `grep -c 'Interactive/session-dependent' plan.md` = 3
- `grep -c 'prose descriptions' plan.md` = 2

### Pattern Consistency
The implementation follows existing conventions:
- Checklist table format preserved (pipe-delimited markdown table cells)
- Template code fence structure maintained in both plan.md and specify.md
- The section 1b Prohibited list extension follows the same bullet format as existing entries
- The section 3 blockquote note is structurally appropriate -- it sits outside the code fence and before the next subsection, making it visible to plan authors without cluttering the template itself
- The annotation format "Interactive/session-dependent: [rationale]" is consistent across all three files, ensuring authors see the same format at write time (specify.md, plan.md) and review time (orchestrator-review.md)

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

The implementation tightens acceptance criteria quality within the existing lifecycle template/review system. It does not introduce new behavior outside the scope of the three changed files. The project requirement that "success criteria are verifiable by an agent with zero prior context" (requirements/project.md) is directly served by this change. The pipeline requirement that plan.md verification steps serve as "executable criteria for feature workers" (requirements/pipeline.md) is also directly served. No new capabilities, interfaces, or behaviors are introduced that are not already reflected in existing requirements.

## Verdict

```json
{
  "verdict": "APPROVED",
  "cycle": 1,
  "issues": [],
  "requirements_drift": "none"
}
```

All five requirements are substantively met. R5's grep-count proxy for `Prohibited` does not increment (2 before, 2 after) because the new prohibition is a list item under the existing heading, not a new heading. The prohibition content is correctly placed and functional. This is a metric artifact, not a substantive gap, and does not warrant requesting changes.
