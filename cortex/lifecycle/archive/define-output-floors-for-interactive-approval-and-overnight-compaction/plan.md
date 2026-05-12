# Plan: Define output floors for interactive approval and overnight compaction

## Overview

Create a reference document defining minimum content requirements for phase transition summaries and approval surfaces, then wire it into the lifecycle skill via cross-references with inline fallback fields. Update the justfile to deploy the new reference doc and add a conditional loading trigger to Agents.md. Tasks 1-6 are independent and can execute in parallel; Task 7 is the integration checkpoint.

## Tasks

### Task 1: Create the output-floors reference document
- **Files**: `claude/reference/output-floors.md` (new)
- **What**: Create the core reference document with three sections: phase transition floor (Decisions, Scope delta, Blockers, Next checklist), approval surface floor (Produced, Trade-offs, Veto surface, Scope boundaries checklist), and overnight file-based addendum (file artifacts bypass compaction, rationale field convention). Include downstream consumption note referencing #052 and #053. Target ~100-150 lines.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Follow the existing reference doc pattern from `claude/reference/verification-mindset.md` — `audience: agent` frontmatter, action-oriented content, no motivational preamble. The phase transition floor defines four required fields with brief descriptions. The approval surface floor defines four required fields: Produced (one-line summary of the artifact), Trade-offs (alternatives considered and rationale), Veto surface (items the user might disagree with or want to change), Scope boundaries (what is explicitly excluded). The overnight addendum documents that file-based artifacts bypass compaction and defines the `rationale` field convention for events.log orchestrator entries. End with a section noting this doc is the constraint source for tickets #052 and #053. Include a precedence rule: when this doc is loaded alongside inline field names in SKILL.md, the expanded definitions here supersede the inline names.
- **Verification**: `test -f claude/reference/output-floors.md` — pass if exit 0. `grep -c 'audience: agent' claude/reference/output-floors.md` — pass if output = 1. `grep -c 'Decisions\|Scope delta\|Blockers\|Next' claude/reference/output-floors.md` — pass if output >= 4. `grep -c 'Produced\|Trade-offs\|Veto surface\|Scope boundaries' claude/reference/output-floors.md` — pass if output >= 4. `grep -c 'rationale' claude/reference/output-floors.md` — pass if output >= 1.
- **Status**: [x] done

### Task 2: Replace lifecycle SKILL.md phase transition instruction
- **Files**: `skills/lifecycle/SKILL.md`
- **What**: Replace the "briefly summarize what was accomplished and what comes next" instruction at line 273 with a cross-reference to `output-floors.md` that preserves auto-proceed behavior. Include the four phase transition field names inline (Decisions, Scope delta, Blockers, Next) as minimum-viable fallback. Add a precedence note: the reference doc's expanded definitions supersede these inline names when loaded.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Line 273 in `## Phase Transition` section currently reads: "After completing a phase artifact, announce the transition and proceed to the next phase automatically. Between phases, briefly summarize what was accomplished and what comes next." The replacement must preserve the auto-proceed behavior ("announce the transition and proceed to the next phase automatically") while replacing "briefly summarize" with the floor requirements. The next line (275) about `/lifecycle <phase>` jumps should not be modified.
- **Verification**: `grep -c 'output-floors' skills/lifecycle/SKILL.md` — pass if output >= 1. `grep -c 'briefly summarize what was accomplished' skills/lifecycle/SKILL.md` — pass if output = 0. `grep -c 'Decisions' skills/lifecycle/SKILL.md` — pass if output >= 1.
- **Status**: [x] done

### Task 3: Inline approval surface fields in specify.md
- **Files**: `skills/lifecycle/references/specify.md`
- **What**: Add the four approval surface field names with parenthetical definitions to §4 User Approval as minimum-viable fallback. Format as a bulleted list. Note: specify.md §4 does not define what "specification summary" means — the approval surface fields will structure this previously-undefined presentation.
- **Depends on**: none
- **Complexity**: simple
- **Context**: §4 User Approval is at line 154-156: "Present the specification summary and use the AskUserQuestion tool to collect approval — not as plain markdown text. The user must approve before proceeding to Plan. If the user requests changes, revise the spec and re-present." Insert a bulleted list between the presentation instruction and the "if the user requests changes" sentence. Each bullet is a field name with parenthetical definition:
  - **Produced** (one-line summary of the artifact)
  - **Trade-offs** (alternatives considered and rationale for chosen approach)
  - **Veto surface** (items the user might disagree with or want to change)
  - **Scope boundaries** (what is explicitly excluded)
  Add a note: "See `~/.claude/reference/output-floors.md` for expanded definitions when loaded."
- **Verification**: `grep -c 'Produced\|Trade-offs\|Veto surface\|Scope boundaries' skills/lifecycle/references/specify.md` — pass if output >= 4.
- **Status**: [x] done

### Task 4: Inline approval surface fields in plan.md
- **Files**: `skills/lifecycle/references/plan.md`
- **What**: Add the four approval surface field names with parenthetical definitions to §4 User Approval as minimum-viable fallback. Format as a bulleted list. Note: plan.md §4 already defines its summary as "overview + task list" — the approval surface fields supplement this, adding approval-specific context the user needs to make a go/no-go decision.
- **Depends on**: none
- **Complexity**: simple
- **Context**: §4 User Approval is at line 241-243: "Present the plan summary (overview + task list). The user must approve before implementation begins. If the user requests changes, revise and re-present." Insert a bulleted list between the presentation instruction and the "if the user requests changes" sentence, matching the format from Task 3. Same four fields with same parenthetical definitions. Add the same reference note to `output-floors.md`.
- **Verification**: `grep -c 'Produced\|Trade-offs\|Veto surface\|Scope boundaries' skills/lifecycle/references/plan.md` — pass if output >= 4.
- **Status**: [x] done

### Task 5: Add conditional loading trigger to Agents.md
- **Files**: `claude/Agents.md`
- **What**: Add a row to the conditional loading table for `output-floors.md` with trigger "Writing phase transition summaries, approval surfaces, or editing skill output instructions".
- **Depends on**: none
- **Complexity**: simple
- **Context**: The conditional loading table is at lines 20-24 of `claude/Agents.md`. Current format is: `| Trigger description | \`~/.claude/reference/filename.md\` |`. Add a new row following the same format after the `parallel-agents.md` entry. The table currently has 3 entries.
- **Verification**: `grep -c 'output-floors' claude/Agents.md` — pass if output >= 1.
- **Status**: [x] done

### Task 6: Add symlink to justfile deploy-reference recipe
- **Files**: `justfile`
- **What**: Add `output-floors.md` symlink entries to three locations in the justfile: the `setup-force` recipe, the `deploy-reference` recipe, and the `check-symlinks` recipe.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Each existing reference doc has entries in three justfile locations. Insert each entry after the existing `claude-skills.md` entry in its respective section:
  1. **`setup-force` recipe** (after the `ln -sf ... claude-skills.md` line): Add `ln -sf "$(pwd)/claude/reference/output-floors.md" ~/.claude/reference/output-floors.md`. Uses `~` for the target path (matching existing entries in this recipe).
  2. **`deploy-reference` recipe** (after the `claude-skills.md|` entry in the `pairs=()` array): Add `"$(pwd)/claude/reference/output-floors.md|$HOME/.claude/reference/output-floors.md"`. Uses `$HOME` for the target path (matching existing entries in this array, which runs inside a `#!/usr/bin/env bash` block).
  3. **`check-symlinks` recipe** (after the `check ~/.claude/reference/claude-skills.md` line): Add `check ~/.claude/reference/output-floors.md`. Uses `~` (matching existing entries).
  Note: Lines 40 and 181 document a bidirectional maintenance contract between `setup-force` and `deploy-reference` — both must stay in sync.
- **Verification**: `grep 'output-floors' justfile | grep -c 'ln -sf'` — pass if output >= 1 (setup-force entry). `grep 'output-floors' justfile | grep -c '|'` — pass if output >= 1 (deploy-reference entry). `grep 'output-floors' justfile | grep -c 'check'` — pass if output >= 1 (check-symlinks entry).
- **Status**: [x] done

### Task 7: Deploy and verify end-to-end
- **Files**: none (verification only)
- **What**: Run `just deploy-reference` to deploy the new symlink, then verify all spec acceptance criteria pass.
- **Depends on**: [1, 2, 3, 4, 5, 6]
- **Complexity**: simple
- **Context**: Run `just deploy-reference` (not `just setup` — narrower scope, fewer side effects) to create the symlink. Then verify: `test -L ~/.claude/reference/output-floors.md` (symlink exists), `just check-symlinks` (all symlinks valid), and spot-check the acceptance criteria from the spec.
- **Verification**: `just check-symlinks 2>&1 | grep -c 'FAIL'` — pass if output = 0. `test -L ~/.claude/reference/output-floors.md` — pass if exit 0 (symlink exists).
- **Status**: [x] done

## Verification Strategy

After all tasks complete, verify end-to-end:
1. `just check-symlinks` passes with no FAIL entries
2. All 8 spec acceptance criteria pass (grep counts for field names in reference doc, SKILL.md, specify.md, plan.md, Agents.md)
3. `wc -l claude/reference/output-floors.md` is within the 100-150 line target
4. The reference doc has no prose examples (checklist format only per spec)
