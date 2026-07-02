# Plan: trim-lifecycle-config-instance-delete-narration

## Overview
Delete the `## Branch Mode` section (candidates s4–s8) from this repo's always-read `cortex/lifecycle.config.md`, consolidate the four branch-mode values into the existing operator note in `docs/overnight-operations.md`, add a one-line frontmatter pointer, and correct ADR-0017's status. Three independent prose edits + one verification run; no code, no asset/template/mirror change.

## Outline

### Phase 1: Trim + consolidate (tasks: 1, 2, 3, 4)
**Goal**: Remove the config body prose, preserve operator discoverability in docs, correct the ADR status, and confirm no test regression.
**Checkpoint**: `## Branch Mode` gone from the config; the four values live in `docs/overnight-operations.md`; ADR-0017 reads `accepted`; the targeted test suite exits 0.

## Tasks

### Task 1: Delete the Branch Mode section and add the frontmatter pointer
- **Files**: cortex/lifecycle.config.md
- **What**: Remove the entire `## Branch Mode` section — the intro (s4), `### Values (closed set)` (s5), `### Carve-outs` (s6), `### Normalization rules` (s7), and `### Edge cases` (s8), i.e. everything from `## Branch Mode` to end-of-file. Add a single YAML `#` comment line immediately above `branch-mode: prompt` in the frontmatter pointing operators to the docs note.
- **Depends on**: none
- **Complexity**: simple
- **Context**: The section is currently the last content in the file (Branch Mode block runs from the `## Branch Mode` heading through `### Edge cases`; `## Review Criteria` sits above it and must survive). The frontmatter closes at the second `---`; the pointer comment must live *inside* the frontmatter, on its own line above `branch-mode: prompt`, e.g. `# branch-mode values + carve-outs: see docs/overnight-operations.md (branch-mode note)`. Parser `cortex_command/lifecycle_config.py:_extract_frontmatter_text`/`read_branch_mode` only reads the frontmatter region, so a `#` comment there is inert. Leave a single trailing newline after `## Review Criteria`'s last bullet.
- **Verification**: `grep -c '^## Branch Mode' cortex/lifecycle.config.md` = 0 AND `grep -cE '### (Values \(closed set\)|Carve-outs|Normalization rules|Edge cases)' cortex/lifecycle.config.md` = 0 AND `grep -c '^## Review Criteria' cortex/lifecycle.config.md` = 1 AND the line above `branch-mode: prompt` starts with `#` and contains `docs/overnight-operations.md` AND `.venv/bin/python -c "import cortex_command.lifecycle_config as m,pathlib; print(m.read_branch_mode(pathlib.Path('.')))"` prints `prompt` — pass if all hold.
- **Status**: [x] complete

### Task 2: Complete the docs branch-mode note with the four values
- **Files**: docs/overnight-operations.md
- **What**: Extend the existing branch-mode "Consumed-but-unscaffolded exception" note (~line 717) with the four-value enumeration and a one-line carve-out summary. Do not restate implement.md §2's full routing prose — just the values and a one-line "picker fires regardless when …".
- **Depends on**: none
- **Complexity**: simple
- **Context**: The note begins `**Consumed-but-unscaffolded exception**: \`branch-mode\` is read by \`read_branch_mode\` …`. Append the value list: `worktree-interactive` (worktree-interactive path), `trunk` (commit on current branch), `feature-branch` (create `feature/{slug}`), `prompt` (picker fires every time = unset). Carve-out line: the picker fires regardless of `branch-mode` on a dirty working tree or when a live interactive worktree session PID exists (`cortex/lifecycle/sessions/{slug}.interactive.pid`). Source of truth for routing remains `skills/lifecycle/references/implement.md` §2 and `cortex_command/lifecycle_implement.py:should_fire_picker`.
- **Verification**: `grep -c 'worktree-interactive' docs/overnight-operations.md` ≥ 1 AND all four tokens `worktree-interactive`, `trunk`, `feature-branch`, `prompt` appear within the branch-mode section — pass if all four present in that section.
- **Status**: [x] complete

### Task 3: Correct ADR-0017 status to accepted
- **Files**: cortex/adr/0017-reconcile-and-gate-lifecycle-config-sources.md
- **What**: Change the frontmatter `status: proposed` to `status: accepted` (its parity gate `tests/test_lifecycle_config_parity.py` is implemented and green). Change only that line; do not add or reorder fields.
- **Depends on**: none
- **Complexity**: simple
- **Context**: The ADR frontmatter currently contains only `status: proposed` between the two `---` delimiters.
- **Verification**: `grep -c '^status: accepted' cortex/adr/0017-reconcile-and-gate-lifecycle-config-sources.md` = 1 AND `grep -c '^status: proposed' cortex/adr/0017-reconcile-and-gate-lifecycle-config-sources.md` = 0 — pass if both hold.
- **Status**: [x] complete

### Task 4: Verify no test regression
- **Files**: none (read-only test run)
- **What**: Run the config, citation, parity, and branch-mode test modules to confirm the edits caused no regression.
- **Depends on**: [1, 2, 3]
- **Complexity**: simple
- **Context**: The relevant modules are `tests/test_lifecycle_config.py` (parser unit tests), `tests/test_lifecycle_config_parity.py` (asset↔template frontmatter parity — unaffected by repo-instance body edits), `tests/test_skill_section_citations.py` (heading citations — pins plan.md/complete.md, not this file), and `tests/test_lifecycle_implement_branch_mode.py` (picker routing — code-owned closed set). Run with the repo venv.
- **Verification**: `.venv/bin/python -m pytest tests/test_lifecycle_config.py tests/test_lifecycle_config_parity.py tests/test_skill_section_citations.py tests/test_lifecycle_implement_branch_mode.py -q` — pass if exit code = 0.
- **Status**: [x] complete

## Risks
- Scope spans three files rather than the ticket's literal one-file Touch points — this is the research-decided cold home for the LAZY_REF blocks, surfaced and approved by the operator at spec time, and conflict-checked clean against all epic #347 siblings. The docs edit is additive (adds a value list), so it cannot be clobbered by a future doc trim.
- A live concurrent lifecycle session for #348 is editing the working tree on `main`. Implementation commits must use explicit pathspecs so #348's changes do not leak into this feature's commit(s).
