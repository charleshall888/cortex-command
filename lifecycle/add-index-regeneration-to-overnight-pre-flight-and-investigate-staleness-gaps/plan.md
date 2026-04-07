# Plan: Add index regeneration to overnight pre-flight and investigate staleness gaps

## Overview

Insert a new pre-selection step in the overnight SKILL.md that regenerates the backlog index before batch selection, with failure gates on both regeneration and auto-commit. Deprecate the redundant `generate-index.sh` shell script and update all documentation references. The main complexity is the step renumbering cascade and internal cross-reference updates within the overnight skill.

## Tasks

### Task 1: Insert index regeneration step and renumber overnight SKILL.md
- **Files**: `skills/overnight/SKILL.md`
- **What**: Insert a new Step 2 ("Pre-selection Index Regeneration") between current Step 1 (Check Existing Session) and current Step 2 (Select Features). The new step instructs the agent to: (1) run `generate-backlog-index` from the project root, (2) halt on non-zero exit, (3) `git add backlog/index.json backlog/index.md`, (4) commit only if staged changes exist with message "Regenerate backlog index", (5) halt on commit failure. Then renumber all subsequent top-level steps (current Step 2→3, 3→4, 4→5, 5→6, 6→7, 7→8) and update all internal cross-references.
- **Depends on**: none
- **Complexity**: complex
- **Context**:
  - Current top-level steps 1-7 at lines 49-220; new step inserts after line ~56 (end of Step 1)
  - Top-level step references to update: line 66 ("step 3" → "step 4"), line 123 ("Step 6" → "Step 7"), line 137 ("Step 4" → "Step 5"), line 140 ("Step 6" → "Step 7"), line 184 ("Step 7" → "Step 8"), line 186 ("Step 4" → "Step 5")
  - Sub-step disambiguation: lines 179, 180, 182 say "step 2" meaning Launch sub-step 2 (`bootstrap_session`). After insertion, "step 2" is ambiguous with new top-level Step 2. Rewrite as "sub-step 2" or "Launch step 2" to disambiguate
  - Step 7 sub-steps (0-8) will become Step 8 sub-steps — renumber the heading ("Step 7: Launch" → "Step 8: Launch") and all sub-step references within it
  - Technical constraint: use `generate-backlog-index` (global CLI name), not `python3 backlog/generate_index.py`
- **Verification**: `grep -cE '(generate-backlog-index|generate_index)' skills/overnight/SKILL.md` ≥ 1 — pass if count ≥ 1. `grep -c 'Step 7: Launch' skills/overnight/SKILL.md` = 0 — pass if the old heading is gone (should now be "Step 8: Launch"). `grep -c '### Step 8: Launch' skills/overnight/SKILL.md` ≥ 1 — pass if the renamed heading exists. `grep -ci 'commit.*fail\|commit.*halt\|halt.*commit' skills/overnight/SKILL.md` ≥ 1 — pass if the commit-failure gate instruction exists in the new step.
- **Status**: [ ] pending

### Task 2: Delete `generate-index.sh`
- **Files**: `skills/backlog/generate-index.sh`
- **What**: Remove the deprecated shell script that only produces `index.md` (not `index.json`). All active call sites already use `generate_index.py` via the `generate-backlog-index` global CLI.
- **Depends on**: none
- **Complexity**: simple
- **Context**: File at `skills/backlog/generate-index.sh`. Already bypassed in all active code paths (`just backlog-index`, skill reindex, `update_item.py`, `create_item.py`).
- **Verification**: `test ! -f skills/backlog/generate-index.sh` — pass if exit code 0 (file does not exist)
- **Status**: [ ] pending

### Task 3: Update `docs/backlog.md` references to `generate-index.sh`
- **Files**: `docs/backlog.md`
- **What**: Replace references to `generate-index.sh` with `generate-backlog-index` (or `generate_index.py` where the project-local path is more appropriate). Two references: line 111 (reindex command description) and line 172 (`update_item.py` side effects).
- **Depends on**: none
- **Complexity**: simple
- **Context**: Line 111: `Runs bash ~/.claude/skills/backlog/generate-index.sh` — replace with `generate-backlog-index`. Line 172: `Regenerates backlog/index.md via generate-index.sh` — update to reference `generate_index.py` and note it produces both `index.json` and `index.md`.
- **Verification**: `grep -c 'generate-index\.sh' docs/backlog.md` = 0 — pass if count is 0
- **Status**: [ ] pending

### Task 4: Update `skills/discovery/references/decompose.md` reference to `generate-index.sh`
- **Files**: `skills/discovery/references/decompose.md`
- **What**: Replace the `generate-index.sh` reference with `generate-backlog-index` at line 98.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Line 98: `Run backlog/generate-index.sh to update the backlog index.` — replace with `Run generate-backlog-index to update the backlog index.`
- **Verification**: `grep -c 'generate-index\.sh' skills/discovery/references/decompose.md` = 0 — pass if count is 0
- **Status**: [ ] pending

### Task 5: Run full test suite and acceptance criteria
- **Files**: (none modified — verification only)
- **What**: Run `just test` to verify no regressions. Then run the acceptance criteria checks from the spec for all 5 requirements.
- **Depends on**: [1, 2, 3, 4]
- **Complexity**: simple
- **Context**: Acceptance criteria checks: (R1) `grep -c 'generate_index\|generate-backlog-index' skills/overnight/SKILL.md` ≥ 1; (R2) verify regeneration + commit + gate instructions exist before uncommitted-files check; (R3) `test ! -f skills/backlog/generate-index.sh` and `grep -r 'generate-index\.sh' docs/ skills/` returns empty; (R4) verify halt instruction on regeneration failure; (R5) `grep -nE 'Step [0-9]|step [0-9]' skills/overnight/SKILL.md` — all references internally consistent.
- **Verification**: `just test` — pass if exit code 0. `grep -r 'generate-index\.sh' docs/ skills/` — pass if no output.
- **Status**: [ ] pending

## Verification Strategy

After all tasks complete, verify the full feature end-to-end:
1. `just test` passes (no regressions)
2. `grep -c 'generate-backlog-index' skills/overnight/SKILL.md` ≥ 1 (regeneration step exists)
3. `test ! -f skills/backlog/generate-index.sh` (deprecated file removed)
4. `grep -r 'generate-index\.sh' docs/ skills/` returns no matches (all references updated)
5. Manual review of `skills/overnight/SKILL.md` confirms: new Step 2 exists with regeneration + auto-commit + failure gates, all step numbers are sequential, all internal cross-references are consistent, sub-step references are disambiguated from top-level steps
