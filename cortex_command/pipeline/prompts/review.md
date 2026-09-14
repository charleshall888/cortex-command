# Feature Review

You are reviewing the **{feature}** implementation against its specification.

## Specification

{spec_excerpt}

## Working Directory

The feature branch is checked out at `{worktree_path}`. Read files from this directory to review the implementation.

## Feature Branch

Branch: `{branch_name}`

Review all commits on this branch. Use `git log main..HEAD` and `git diff main..HEAD` from the worktree to understand the full scope of changes.

## Instructions

This is a read-only review. Do NOT modify any source files.

### Stage 1: Spec Compliance

For each requirement in the specification, verify the implementation matches:
- Read the relevant source files in the worktree
- Check that acceptance criteria are met
- Rate each requirement: **PASS**, **FAIL**, or **PARTIAL**
- Include a brief rationale for each rating

If any requirement is **FAIL**, skip Stage 2 and write the verdict immediately.

### Stage 2: Code Quality

Only perform this stage if all requirements are PASS or PARTIAL (no FAIL):
- **Naming conventions**: consistent with project patterns?
- **Error handling**: appropriate for the context?
- **Verification coverage**: do the implemented verification steps work?
- **Pattern consistency**: follows existing project conventions?
- **Scope discipline**: no changes beyond what the spec requires?

### Requirements Drift

Compare the implementation against stated project requirements.
Note: requirements drift does NOT influence the verdict. This is an observation only.
- If the implementation matches all stated requirements and introduces no new behavior not reflected in them: state = none
- If the implementation introduces behavior not captured in the requirements docs, or changes behavior in a way requirements don't reflect: state = detected; list each drifted item as a bullet

### Stage 3: Write Review

Write your review to `{review_md_path}` on disk using the format below.

The verdict is read by a parser, not a person: it takes the first fenced ```json block in the file and returns ERROR on any other field names or values. The Verdict section therefore contains one fenced JSON code block with exactly these fields:
- `"verdict"`: one of `"APPROVED"`, `"CHANGES_REQUESTED"`, or `"REJECTED"`
- `"cycle"`: `1` (this brief is used only for cycle 1)
- `"issues"`: array of issue strings (empty array if none)
- `"requirements_drift"`: `"none"` or `"detected"`

Other field names (`"overall"`, `"result"`, `"status"`) or values (`"PASS"`, `"FAIL"`, `"APPROVED_WITH_NOTES"`) are parsed as ERROR. Use this structure for `review.md`:

```
# Review: {feature}

## Stage 1: Spec Compliance

### Requirement: {requirement text}
- **Expected**: {what the spec says}
- **Actual**: {what the implementation does}
- **Verdict**: PASS / FAIL / PARTIAL
- **Notes**: {details, especially if FAIL or PARTIAL}

(repeat for each requirement)

## Requirements Drift

**State**: none | detected
**Findings**:
- (one bullet per drifted item, or "None" if state is none)
**Update needed**: (path to requirements file that needs updating, or "None")

## Stage 2: Code Quality
<!-- Only present if Stage 1 has no FAIL verdicts -->

- **Naming conventions**: {assessment}
- **Error handling**: {assessment}
- **Verification coverage**: {assessment}
- **Pattern consistency**: {assessment}
- **Scope discipline**: {assessment}

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
```

The `requirements_drift` value in the verdict JSON matches the Requirements Drift section: `"none"` when State is none, `"detected"` when State is detected.

## Verdict Criteria

- **APPROVED**: All spec requirements PASS (PARTIAL is acceptable if minor). Code quality is adequate. No scope creep.
- **CHANGES_REQUESTED**: One or more requirements are PARTIAL with significant gaps, or code quality issues need addressing. The implementation is on the right track but needs specific fixes.
- **REJECTED**: One or more requirements FAIL outright, or the implementation takes a fundamentally wrong approach. Recommend revisiting the plan or spec.

## Review Discipline

- Review what was built against what was specified. Do not suggest enhancements beyond the spec.
- Flag scope creep (work done that the spec did not ask for) as an issue.
- Be specific in issue descriptions -- reference exact files and line ranges.
