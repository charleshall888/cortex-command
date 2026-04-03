# Plan: fix-skill-sub-file-path-bug-across-all-skills

## Overview

Replace all bare relative sub-file path references across 9 SKILL.md files and 7 reference files with portable absolute paths: `${CLAUDE_SKILL_DIR}/references/foo.md` in SKILL.md bodies and `~/.claude/skills/{skill}/references/foo.md` in reference files. All tasks are independent and commit their own changes. Task 10 (verification) runs after all others complete.

## Tasks

### Task 1: Fix lifecycle/SKILL.md table refs

- **Files**: `skills/lifecycle/SKILL.md`
- **What**: Replace 4 relative sub-file refs in the phase-reference table with `${CLAUDE_SKILL_DIR}` paths; simplify display text to filename only.
- **Depends on**: none
- **Complexity**: simple
- **Context**: The table at lines ~268–271 currently reads:
  ```
  | Plan | [references/plan.md](references/plan.md) | ...
  | Implement | [references/implement.md](references/implement.md) | ...
  | Review | [references/review.md](references/review.md) | ...
  | Complete | [references/complete.md](references/complete.md) | ...
  ```
  Update each href to `${CLAUDE_SKILL_DIR}/references/{name}.md` and simplify display text to just the filename (e.g., `[plan.md](...)`).
- **Verification**: `grep -n 'references/' skills/lifecycle/SKILL.md` shows only `${CLAUDE_SKILL_DIR}/references/` occurrences in load instructions. `grep -n '](references/' skills/lifecycle/SKILL.md` returns nothing.
- **Status**: [x] complete

---

### Task 2: Fix refine/SKILL.md cross-skill refs

- **Files**: `skills/refine/SKILL.md`
- **What**: Replace all cross-skill references to lifecycle sub-files with the `${CLAUDE_SKILL_DIR}/../lifecycle/` traversal pattern.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Find all occurrences: `grep -n 'skills/lifecycle/references' skills/refine/SKILL.md`. Each occurrence of `skills/lifecycle/references/clarify.md` → `${CLAUDE_SKILL_DIR}/../lifecycle/references/clarify.md`. Each occurrence of `skills/lifecycle/references/specify.md` → `${CLAUDE_SKILL_DIR}/../lifecycle/references/specify.md`.
- **Verification**: `grep -n 'skills/lifecycle/references' skills/refine/SKILL.md` returns nothing. All cross-skill refs now use `${CLAUDE_SKILL_DIR}/../lifecycle/references/`.
- **Status**: [x] complete

---

### Task 3: Fix discovery/SKILL.md refs

- **Files**: `skills/discovery/SKILL.md`
- **What**: Replace 4 relative sub-file refs (backtick inline and markdown link forms) with `${CLAUDE_SKILL_DIR}` paths.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Find all: `grep -n 'references/' skills/discovery/SKILL.md`. Update each load instruction to use `${CLAUDE_SKILL_DIR}/references/{name}.md`. For markdown links, apply filename-only display text: `[auto-scan.md](${CLAUDE_SKILL_DIR}/references/auto-scan.md)`.
- **Verification**: `grep -n '](references/' skills/discovery/SKILL.md` returns nothing. All load-instruction refs contain `${CLAUDE_SKILL_DIR}`.
- **Status**: [x] complete

---

### Task 4: Fix skill-creator/SKILL.md load instructions

- **Files**: `skills/skill-creator/SKILL.md`
- **What**: Replace bare relative refs at the 6 specific target lines listed below. Make no other changes to this file.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Run `grep -n 'references/' skills/skill-creator/SKILL.md` first to confirm line numbers. Then apply exactly these 6 substitutions and nothing else:
  - The line containing `` read `references/contract-patterns.md` `` → `` read `${CLAUDE_SKILL_DIR}/references/contract-patterns.md` ``
  - The line containing `See references/workflows.md` → `See ${CLAUDE_SKILL_DIR}/references/workflows.md`
  - The line containing `See references/output-patterns.md` → `See ${CLAUDE_SKILL_DIR}/references/output-patterns.md`
  - The line containing `See references/contract-patterns.md` → `See ${CLAUDE_SKILL_DIR}/references/contract-patterns.md`
  - The line containing `See references/orchestrator-patterns.md` → `See ${CLAUDE_SKILL_DIR}/references/orchestrator-patterns.md`
  - The line containing `See references/state-patterns.md` → `See ${CLAUDE_SKILL_DIR}/references/state-patterns.md`

  All other `references/` occurrences in this file are illustrative content — do not change them.
- **Verification**: The 6 target lines now contain `${CLAUDE_SKILL_DIR}/references/`. Run `grep -n 'references/' skills/skill-creator/SKILL.md` and confirm the total count of `references/` occurrences is unchanged (same number as before, just with the 6 target lines updated).
- **Status**: [x] complete

---

### Task 5: Fix remaining SKILL.md files (5 files)

- **Files**: `skills/requirements/SKILL.md`, `skills/pr-review/SKILL.md`, `skills/morning-review/SKILL.md`, `skills/backlog/SKILL.md`, `skills/ui-brief/SKILL.md`
- **What**: Replace all bare relative sub-file refs in these 5 SKILL.md files with `${CLAUDE_SKILL_DIR}/references/…`.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Each file, what to find, and the fix (use grep to confirm line numbers first):
  - `requirements/SKILL.md`: `` `references/gather.md` `` (×2) → `` `${CLAUDE_SKILL_DIR}/references/gather.md` ``
  - `pr-review/SKILL.md`: `` `references/protocol.md` `` (×2) → `` `${CLAUDE_SKILL_DIR}/references/protocol.md` ``
  - `morning-review/SKILL.md`: `` `references/walkthrough.md` `` (×3) → `` `${CLAUDE_SKILL_DIR}/references/walkthrough.md` ``
  - `backlog/SKILL.md`: `` `references/schema.md` `` (×1) → `` `${CLAUDE_SKILL_DIR}/references/schema.md` ``
  - `ui-brief/SKILL.md`: `` `references/design-md-template.md` `` and `` `references/theme-template.md` `` → same pattern
- **Verification**: `grep -rn '](references/' skills/requirements/SKILL.md skills/pr-review/SKILL.md skills/morning-review/SKILL.md skills/backlog/SKILL.md skills/ui-brief/SKILL.md` returns nothing. All load instructions in these files contain `${CLAUDE_SKILL_DIR}`.
- **Status**: [x] complete

---

### Task 6: Fix lifecycle reference files (4 files)

- **Files**: `skills/lifecycle/references/clarify.md`, `skills/lifecycle/references/specify.md`, `skills/lifecycle/references/research.md`, `skills/lifecycle/references/plan.md`
- **What**: Replace bare relative sub-file refs with absolute tilde paths. `${CLAUDE_SKILL_DIR}` is not substituted in reference files — use `~/.claude/skills/lifecycle/references/` prefix instead.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Exact substitutions (verify line numbers with grep first):
  - `clarify.md`: `` `skills/lifecycle/references/clarify-critic.md` `` → `` `~/.claude/skills/lifecycle/references/clarify-critic.md` ``
  - `specify.md`: `` `references/orchestrator-review.md` `` → `` `~/.claude/skills/lifecycle/references/orchestrator-review.md` ``
  - `research.md`: `` `references/orchestrator-review.md` `` → `` `~/.claude/skills/lifecycle/references/orchestrator-review.md` ``
  - `plan.md`: `` `references/orchestrator-review.md` `` → `` `~/.claude/skills/lifecycle/references/orchestrator-review.md` ``
- **Verification**: `grep -rn 'references/orchestrator-review\|references/clarify-critic' skills/lifecycle/references/clarify.md skills/lifecycle/references/specify.md skills/lifecycle/references/research.md skills/lifecycle/references/plan.md` — every match contains `~/.claude/skills/lifecycle/references/`.
- **Status**: [x] complete

---

### Task 7: Fix discovery and skill-creator reference files (3 files)

- **Files**: `skills/discovery/references/research.md`, `skills/skill-creator/references/orchestrator-patterns.md`, `skills/skill-creator/references/workflows.md`
- **What**: Replace bare relative sub-file refs with absolute tilde paths.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Exact substitutions:
  - `discovery/references/research.md` line ~124: `` `references/orchestrator-review.md` `` → `` `~/.claude/skills/discovery/references/orchestrator-review.md` ``
  - `skill-creator/references/orchestrator-patterns.md` line ~64: `` `references/state-patterns.md` `` → `` `~/.claude/skills/skill-creator/references/state-patterns.md` ``
  - `skill-creator/references/workflows.md` line ~127: `[references/output-patterns.md](references/output-patterns.md)` → `[output-patterns.md](~/.claude/skills/skill-creator/references/output-patterns.md)`
- **Verification**: `grep -rn 'references/orchestrator-review\|references/state-patterns\|](references/' skills/discovery/references/research.md skills/skill-creator/references/orchestrator-patterns.md skills/skill-creator/references/workflows.md` returns nothing without a tilde-path prefix.
- **Status**: [x] complete

---

### Task 8: Add convention to claude/reference/claude-skills.md

- **Files**: `claude/reference/claude-skills.md`
- **What**: Add a new row to the "Common Mistakes" table documenting the sub-file path convention.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Find the "Common Mistakes" table. Add a new row (may need to split across rows if the table is narrow) covering:
  - Mistake: relative (`references/foo.md`) or repo-relative (`skills/X/references/foo.md`) sub-file path
  - Fix: `${CLAUDE_SKILL_DIR}/references/foo.md` in SKILL.md body; `~/.claude/skills/{skill}/references/foo.md` in reference files
  - Include in the fix column or as a note row: paths resolve against CWD; `${CLAUDE_SKILL_DIR}` only works in SKILL.md body (not frontmatter hooks, not reference files); cross-skill pattern: `${CLAUDE_SKILL_DIR}/../other-skill/references/foo.md` (personal skills only); `!cat` injection as fallback.
- **Verification**: `grep -n 'CLAUDE_SKILL_DIR' claude/reference/claude-skills.md` shows the new entry. The entry is visible in the Common Mistakes table.
- **Status**: [x] complete

---

### Task 9: Add convention to claude/reference/context-file-authoring.md

- **Files**: `claude/reference/context-file-authoring.md`
- **What**: Add a brief "Skill Sub-File Paths" section with rule, reason, and pointer to claude-skills.md.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Add before the "Red Flags" section. Content:
  - **Rule**: Use `${CLAUDE_SKILL_DIR}/references/foo.md` in SKILL.md; `~/.claude/skills/{skill}/references/foo.md` in reference files. Not relative paths, not repo-relative paths.
  - **Reason**: Claude Code resolves bare paths against the project CWD — not the skill directory.
  - **Pointer**: "See `claude/reference/claude-skills.md` Common Mistakes for cross-skill pattern and `!cat` injection alternative."
- **Verification**: Read `claude/reference/context-file-authoring.md` and confirm the section is present with rule, reason, and pointer.
- **Status**: [ ] pending

---

### Task 10: Post-implementation verification

- **Files**: none
- **What**: Confirm all fixes landed correctly. Verification only — no file changes, no commit.
- **Depends on**: [1, 2, 3, 4, 5, 6, 7, 8, 9]
- **Complexity**: trivial
- **Context**: First, confirm working directory is the repo root: `ls skills/lifecycle/SKILL.md` must succeed. If it fails, stop — wrong directory.

  Then run all four checks. A grep that errors (non-zero exit, no files found) is a failure, not a pass:

  1. `grep -rn '](references/' skills/*/SKILL.md` — must return zero output
  2. `grep -rn 'read \`[^$~]' skills/*/SKILL.md` — must return zero output (any matches must be investigated and confirmed as illustrative before proceeding)
  3. `grep -rn 'references/' skills/*/SKILL.md` — every match must contain `${CLAUDE_SKILL_DIR}/references/` or be confirmed illustrative content
  4. `grep -rn 'references/' skills/*/references/*.md` — every match must contain `~/.claude/skills/` (the tilde-path fix) or be confirmed illustrative/structural content not intended as a file-load instruction

  If any check fails, identify which task's files need fixing and reopen that task.
- **Verification**: All four checks produce expected output. Document results briefly before closing.
- **Status**: [x] complete

## Verification Strategy

Tasks 1–9 each commit their own changes independently. Task 10 runs verification after all commits land. If Task 10 finds any remaining bare paths, the relevant task is reopened and re-run before Task 10 is retried.
