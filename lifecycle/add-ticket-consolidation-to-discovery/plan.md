# Plan: add-ticket-consolidation-to-discovery

## Overview

Add a consolidation review section to `skills/discovery/references/decompose.md` between the current §2 (Identify Work Items) and §3 (Determine Grouping), renumbering subsequent sections. Single-file edit.

## Tasks

### Task 1: Add consolidation review section and renumber decompose.md
- **Files**: `skills/discovery/references/decompose.md`
- **What**: Insert a new §3 "Consolidation Review" section after current §2 and renumber all subsequent sections (§3→§4, §4→§5, §5→§6, §6→§7, §7→§8, §8→§9). The new section defines two heuristics — (a) same-file overlap among S-sized items and (b) no-standalone-value prerequisites — instructs the agent to combine matching items automatically, and requires documenting consolidation decisions in the Key Design Decisions section of `decomposed.md`.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Current section structure: §1 Load Context, §2 Identify Work Items (line 13, ends ~line 30), §3 Determine Grouping (line 33), §4 Create Backlog Tickets (line 44), §5 Write Decomposition Record (line 57), §6 Update Index (line 81), §7 Commit (line 85), §8 Present Summary (line 89), Constraints (line 97)
  - The new §3 goes between the end of §2 (after line 28 "Present the proposed work items...") and the start of current §3 (line 33 "### 3. Determine Grouping")
  - §2 already captures `size` (S/M/L) and `dependencies` per work item — the consolidation heuristics evaluate these fields
  - The only internal cross-reference to update: Constraints section line 99 references "One epic max" which relates to current §3 — no section-number cross-refs exist within the file
  - `research/{topic}/decomposed.md` template (§5/new §6) already has a "Key Design Decisions" pattern used in `research/generative-ui-harness/decomposed.md` — the consolidation section should reference recording decisions there
  - The agent may also consolidate beyond the two named heuristics if it can provide concrete, verifiable rationale — self-referential reasoning like "same thought process" is explicitly insufficient
- **Verification**: `grep -c "### 3. Consolidation Review" skills/discovery/references/decompose.md` returns 1; `grep -c "### 4. Determine Grouping" skills/discovery/references/decompose.md` returns 1; `grep -c "### 9. Present Summary" skills/discovery/references/decompose.md` returns 1
- **Status**: [x] complete

## Verification Strategy

Run `grep -n "^### " skills/discovery/references/decompose.md` to confirm all 9 sections are present and correctly numbered. Verify the two heuristic names appear: `grep -c "Same-file overlap" skills/discovery/references/decompose.md` and `grep -c "No-standalone-value prerequisite" skills/discovery/references/decompose.md` both return 1.
