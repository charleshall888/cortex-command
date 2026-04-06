# Plan: critical-review-self-resolve-before-asking

## Overview
Add a self-resolution paragraph to critical-review Step 4 (between the Ask definition and post-classification flow) with an anchor check, then add an adapted version to clarify-critic's Disposition Framework. Both changes are prose edits to existing markdown files.

## Tasks

### Task 1: Add self-resolution paragraph to critical-review SKILL.md
- **Files**: `skills/critical-review/SKILL.md`
- **What**: Insert a self-resolution paragraph between the Ask definition (line 185, ending "Hold these for the end.") and the "After classifying all objections:" block (line 187).
- **Depends on**: none
- **Complexity**: simple
- **Context**: Insert the following paragraph as a new block between the Ask definition and the post-classification flow. It must appear BEFORE "After classifying all objections:" and AFTER the Ask definition paragraph. Do not modify any existing text — this is a pure insertion.

  The paragraph to insert (verbatim):

  > **Before classifying as Ask, attempt self-resolution.** For each objection you are considering classifying as Ask, do a brief check — not an exhaustive search. Re-read the relevant artifact sections, check related codebase files, and consult any project context loaded in Step 2a. If the answer is supported by verifiable evidence — a specific file path, explicit artifact text, or documented project context — resolve it yourself and classify as Apply or Dismiss instead. Do not resolve based on inferences from general principles or reasoning you already held before investigating. **Anchor check**: if your resolution relies on conclusions from your prior work on this artifact rather than new evidence found during the check, treat it as Ask — that is anchoring, not resolution. Uncertainty still defaults to Ask.

  The existing Apply bar on line 193 must remain verbatim and unchanged. The self-resolution paragraph operates alongside the Apply bar (which governs all dispositions), not as a replacement.
- **Verification**: `grep -c 'Anchor check' skills/critical-review/SKILL.md` — pass if count = 2 (one in Dismiss, one in self-resolution). `grep -c 'brief check' skills/critical-review/SKILL.md` — pass if count ≥ 1. `grep -c 'verifiable evidence' skills/critical-review/SKILL.md` — pass if count ≥ 1.
- **Status**: [ ] pending

### Task 2: Add adapted self-resolution to clarify-critic
- **Files**: `skills/lifecycle/references/clarify-critic.md`
- **What**: Insert an adapted self-resolution paragraph into the Disposition Framework section between the Ask definition (line 66) and the Apply bar (line 68). Update the sync comment on line 60. Add an event logging note about post-self-resolution disposition counts.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Three changes to this file:

  **(a) Update line 60** from:
  "(Apply/Dismiss/Ask framework below matches `/critical-review` Step 4 — reproduced here to avoid silent drift.)"
  to:
  "(Apply/Dismiss/Ask framework below — including the self-resolution step — matches `/critical-review` Step 4 — reproduced here to avoid silent drift.)"

  **(b) Insert the following adapted paragraph** between the Ask definition (line 66, ending "Hold these for the consolidated Q&A in §4.") and the Apply bar (line 68):

  > **Before classifying as Ask, attempt self-resolution.** For each objection you are considering classifying as Ask, do a brief check — not an exhaustive search. Re-read the source material and confidence assessment, and consult any requirements context loaded in clarify §2. If the answer is supported by verifiable evidence — explicit text in the source material, a requirements constraint, or a documented project convention — resolve it and reclassify: as Apply (revising the affected confidence dimension accordingly) or as Dismiss. Do not resolve based on inferences from general principles or reasoning you already held before investigating. **Anchor check**: if your resolution relies on conclusions from your prior work on this assessment rather than new evidence found during the check, treat it as Ask — that is anchoring, not resolution. Uncertainty still defaults to Ask. Surviving Ask items flow into the Ask-to-Q&A Merge Rule as before.

  Key adaptations from critical-review's version: (1) "re-read relevant artifact sections" → "re-read the source material and confidence assessment"; (2) "check related codebase files" → omitted (the orchestrator in clarify works from source material + requirements, not codebase files); (3) "classify as Apply" → "reclassify as Apply (revising the affected confidence dimension accordingly)"; (4) trailing sentence clarifies merge-rule flow.

  **(c) Add a note to the Event Logging section** (after line 95, the `applied_fixes` clarification). Insert:
  "Disposition counts reflect post-self-resolution values. If self-resolution reclassifies an Ask item as Apply, the logged `apply` count increases and `ask` count decreases accordingly. The `applied_fixes` array includes fixes from both initial Apply dispositions and self-resolution reclassifications."

  The existing Apply bar on line 68 must remain unchanged.
- **Verification**: `grep -c 'self-resolution' skills/lifecycle/references/clarify-critic.md` — pass if count ≥ 3 (sync comment, paragraph, event logging note). `grep -c 'Anchor check' skills/lifecycle/references/clarify-critic.md` — pass if count ≥ 1. `grep -c 'verifiable evidence' skills/lifecycle/references/clarify-critic.md` — pass if count ≥ 1.
- **Status**: [ ] pending

### Task 3: Run tests and verify no regressions
- **Files**: none (read-only verification)
- **What**: Run the test suite and verify that Apply bar text in both files is unchanged.
- **Depends on**: [1, 2]
- **Complexity**: trivial
- **Context**: `just test` runs the full test suite. The Apply bar in SKILL.md (line ~195 after insertion) must still contain the exact text: "Apply when and only when the fix is unambiguous and confidence is high." The Apply bar in clarify-critic.md (line ~70 after insertion) must still contain: "Apply when and only when the fix is unambiguous and confidence is high."
- **Verification**: `just test` — pass if exit code = 0. `grep -c 'Apply when and only when the fix is unambiguous' skills/critical-review/SKILL.md` — pass if count = 1. `grep -c 'Apply when and only when the fix is unambiguous' skills/lifecycle/references/clarify-critic.md` — pass if count = 1.
- **Status**: [ ] pending

## Verification Strategy
After all tasks complete: (1) `just test` exits 0, (2) both files contain "Anchor check" in the self-resolution paragraph (grep count = 2 in SKILL.md, ≥ 1 in clarify-critic.md), (3) both files contain "verifiable evidence" (grep count ≥ 1 each), (4) Apply bar text unchanged in both files (grep confirms exact phrase present once per file).
