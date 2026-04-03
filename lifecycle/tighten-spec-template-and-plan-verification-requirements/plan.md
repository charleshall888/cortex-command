# Plan: tighten-spec-template-and-plan-verification-requirements

## Overview

Three independent text-edit tasks, one per file. All tasks can run in parallel — no shared state or ordering dependencies. Each task updates a single skill reference file to tighten binary-checkability requirements for acceptance criteria (S1) and verification fields (P4).

## Tasks

### Task 1: Update S1 and P4 Criteria in orchestrator-review.md

- **Files**: `skills/lifecycle/references/orchestrator-review.md`
- **What**: Replace the S1 Criteria text and P4 Criteria text in the Post-Specify and Post-Plan checklists to require binary-checkable criteria with the three-part condition.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - File is a markdown table with columns `# | Item | Criteria`. The target rows are S1 (line ~140) and P4 (line ~155).
  - Current S1 Criteria cell: `Every requirement has acceptance criteria that can be objectively evaluated as met or not met — no subjective language like "should be fast" or "user-friendly"`
  - Current P4 Criteria cell: `Each task's Verification field describes concrete steps to confirm success, not vague "verify it works"`
  - New S1 Criteria must: (1) use the phrase "binary-checkable", (2) define three formats — (a) command + observable output + explicit pass/fail criterion (e.g., exit code = 0, grep count ≥ N), (b) observable state naming the specific file path, the specific string/pattern to find, and the expected true/false result, (c) annotation "Interactive/session-dependent: [one-sentence rationale explaining why a command is not possible]" — and (3) state that prose criteria like "confirm the feature works correctly" do not pass even if they avoid subjective language.
  - New P4 Criteria must: (1) define the same three-part condition as S1, (2) include the annotation "Interactive/session-dependent:" as the exception path using the identical format string as S1, (3) state that prose-only Verification fields do not pass.
  - Both criteria must use the identical annotation format string: `Interactive/session-dependent: [one-sentence rationale explaining why a command is not possible]`
  - Markdown table cells cannot span multiple lines. Use semicolons or line-wrapped text to fit the three-part condition within the Criteria cell. The table can be reformatted with a wider Criteria column if needed — but the three-part structure must be present.
- **Verification**:
  - (a) `grep -c 'binary-checkable' skills/lifecycle/references/orchestrator-review.md` returns ≥ 1
  - (b) `grep -c 'Interactive/session-dependent' skills/lifecycle/references/orchestrator-review.md` returns ≥ 2 (one for S1, one for P4)
  - (c) Read the S1 and P4 rows and confirm the three-part condition (a)/(b)/(c) appears in the Criteria cell for both
- **Status**: [x] done

### Task 2: Update Requirements template in specify.md

- **Files**: `skills/lifecycle/references/specify.md`
- **What**: Update the Requirements section template in §3 to show that acceptance criteria must be binary-checkable, with an inline example.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - File is the Specify Phase reference. §3 "Write Specification Artifact" contains the spec template as a markdown code block. Within that block, the Requirements section currently shows:
    ```
    ## Requirements
    1. [Requirement]: [Acceptance criteria]
    ```
  - The `[Acceptance criteria]` placeholder needs a parenthetical that: (1) uses the phrase "binary-checkable", (2) gives at least one concrete example (e.g., `` `just test` exits 0 — pass if exit code = 0 ``, or `` `grep -c 'pattern' file` = N ``), and (3) names the exception annotation format `Interactive/session-dependent: [rationale]`.
  - Example replacement:
    ```
    ## Requirements
    1. [Requirement]: [Acceptance criteria — binary-checkable: (a) command + expected output + pass/fail (e.g., "`just test` exits 0, pass if exit code = 0"), (b) observable state naming specific file and pattern (e.g., "`grep -c 'keyword' path/file` = 1"), or (c) "Interactive/session-dependent: [rationale]" if a command check is not possible]
    ```
  - The goal is for a spec author reading the template to immediately understand the required format without needing to read orchestrator-review.md.
  - Note: this is inside a markdown code block in specify.md. Edit the text within the code fence only — do not change the code fence markers.
- **Verification**:
  - (a) `grep -c 'binary-checkable' skills/lifecycle/references/specify.md` returns ≥ 1
  - (b) `grep -c 'Interactive/session-dependent' skills/lifecycle/references/specify.md` returns ≥ 1
  - (c) Read the §3 Requirements section template in specify.md and confirm a parenthetical with "binary-checkable" and at least one example is present on the `[Requirement]: [Acceptance criteria]` line
- **Status**: [x] done

### Task 3: Update Verification template in both plan.md template blocks

- **Files**: `skills/lifecycle/references/plan.md`
- **What**: Update the Verification placeholder text in both the §1b competing-plan agent prompt template and the §3 standard plan template, and extend the §1b "Prohibited:" list to include prose-only Verification fields.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - plan.md has two separate template blocks, each containing `- **Verification**:` lines. Read the file before editing to confirm the exact locations.
  - **§1b block** (lines ~30-90, inside a markdown code fence): The competing-plan agent prompt template. Contains exactly **one** `- **Verification**:` line, currently: `- **Verification**: {what to test and how to confirm success}` (line ~80). This block also contains a "### Prohibited:" list with entries like "Function bodies", "Import statements", etc.
  - **§3 block** (lines ~127-161, inside a separate markdown code fence): The standard plan template. Contains **two** `- **Verification**:` lines — one for the Task 1 example (`{what to test and how to confirm success}`, line ~145) and one for the Task 2 example (`{verification steps}`, line ~154). Both must be updated.
  - **Changes to §1b**:
    - (a) Replace the single Verification placeholder with text showing the three formats: `{(a) command + expected output + pass/fail (e.g., "run \`just test\` — pass if exit 0, all tests pass"), OR (b) specific file/pattern check (e.g., "\`grep -c 'keyword' path/file\` = 1 — pass if count = 1"), OR (c) "Interactive/session-dependent: [one-sentence rationale explaining why no command is possible]"}`.
    - (b) Extend the "### Prohibited:" list by adding one entry at the end of the list: `- Verification fields that consist only of prose descriptions requiring human judgment to evaluate (e.g., "confirm the feature works correctly", "verify the change looks right")`
  - **Changes to §3** (update both Task 1 and Task 2 Verification lines):
    - (a) Replace both Verification placeholders with text matching the three-format pattern above.
    - (b) Add the following note immediately after the closing code fence of the §3 template block (after the ` ``` ` at line ~161), before the "### Task Sizing" subsection:
      > Verification fields that consist only of prose descriptions (e.g., "confirm the feature works correctly") do not pass the P4 checklist. Use format (a), (b), or (c) from the task template above.
  - Important: the §1b and §3 template blocks are separate markdown code fences in the same file. The `### Prohibited:` list is inside the §1b code fence, not the §3 code fence.
- **Verification**:
  - (a) `grep -c 'Interactive/session-dependent' skills/lifecycle/references/plan.md` returns ≥ 2 (one from §1b, one or two from §3)
  - (b) `grep -c 'prose descriptions' skills/lifecycle/references/plan.md` returns ≥ 1 (confirms Prohibited entry is present)
  - (c) Read the §1b template block and confirm: one Verification line updated + Prohibited list extended
  - (d) Read the §3 template block and confirm: both Verification lines updated + note appears immediately after the closing ` ``` ` fence and before "### Task Sizing"
- **Status**: [x] done

## Verification Strategy

After all three tasks complete:

1. (a) `grep -c 'binary-checkable' skills/lifecycle/references/orchestrator-review.md` returns ≥ 1
2. (b) `grep -c 'Interactive/session-dependent' skills/lifecycle/references/orchestrator-review.md` returns ≥ 2
3. (c) `grep -c 'binary-checkable' skills/lifecycle/references/specify.md` returns ≥ 1
4. (d) `grep -c 'Interactive/session-dependent' skills/lifecycle/references/plan.md` returns ≥ 2
5. (e) `grep -c 'Interactive/session-dependent' skills/lifecycle/references/specify.md` returns ≥ 1 (confirms annotation format appears in all three files — combined with (b) and (d), this verifies three-file coverage)
6. (f) `grep -c 'prose descriptions' skills/lifecycle/references/plan.md` returns ≥ 1 (confirms Prohibited entry present in §1b)
7. (g) Run `just test` if available — the changes are documentation-only and should not affect test outcomes. Interactive/session-dependent: just test runs a test suite unrelated to these text changes and cannot confirm annotation consistency — treat as an additional smoke-check only.
