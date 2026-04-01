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

### Stage 3: Write Verdict

Produce your review as structured output with the following format:

```
## Stage 1: Spec Compliance

### Requirement: {requirement text}
- **Expected**: {what the spec says}
- **Actual**: {what the implementation does}
- **Verdict**: PASS / FAIL / PARTIAL
- **Notes**: {details, especially if FAIL or PARTIAL}

(repeat for each requirement)

## Stage 2: Code Quality

- **Naming conventions**: {assessment}
- **Error handling**: {assessment}
- **Verification coverage**: {assessment}
- **Pattern consistency**: {assessment}
- **Scope discipline**: {assessment}

## Verdict

VERDICT: {APPROVED | CHANGES_REQUESTED | REJECTED}

### Rationale
{1-3 sentences explaining the verdict}

### Issues
{bulleted list of specific issues to address, or "None" if APPROVED}
```

## Verdict Criteria

- **APPROVED**: All spec requirements PASS (PARTIAL is acceptable if minor). Code quality is adequate. No scope creep.
- **CHANGES_REQUESTED**: One or more requirements are PARTIAL with significant gaps, or code quality issues need addressing. The implementation is on the right track but needs specific fixes.
- **REJECTED**: One or more requirements FAIL outright, or the implementation takes a fundamentally wrong approach. Recommend revisiting the plan or spec.

## Review Discipline

- Review what was built against what was specified. Do not suggest enhancements beyond the spec.
- Flag scope creep (work done that the spec did not ask for) as an issue.
- Be specific in issue descriptions — reference exact files and line ranges.
- Do not modify any files. This is a read-only review.
