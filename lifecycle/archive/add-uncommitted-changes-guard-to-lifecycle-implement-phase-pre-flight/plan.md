# Plan: Add uncommitted-changes guard to lifecycle implement-phase pre-flight

## Overview

All 9 requirements modify a single file: `skills/lifecycle/references/implement.md §1`. The ticket is a prose-only change — no code, no tests, no helpers. The edits add (1) a new `Uncommitted-changes guard` paragraph adjacent to the existing `Worktree-agent context guard` (implement.md:18), mirroring that guard's structural pattern, and (2) a static one-clause caveat on the "Implement in autonomous worktree" option description. The guard runs `git status --porcelain` immediately before the `AskUserQuestion` call; on non-empty output it demotes the current-branch option (strip `(recommended)` suffix if present, prepend a fixed warning to the description) without removing it. On porcelain failure, the guard is inert and surfaces a one-line diagnostic. The guard's prose is phrased abstractly ("the option that keeps the user on the current branch") so #097's rename of "Implement on main" → "Implement on current branch" and flip of `(recommended)` does not require re-editing.

Composition plan: the plan is a single edit landing one paragraph and two option-description changes, split into three tasks for clear verification granularity — one task per acceptance-testable surface (the guard paragraph, the option-2 caveat, the routing-label integrity confirmation). All three tasks target lines 11–26 of the same file. Tasks 1 and 2 are independent text additions; Task 3 is a verification-only task that confirms routing-label substrings are untouched.

## Tasks

### Task 1: Add "Uncommitted-changes guard" paragraph to implement.md §1
- **Files**: `skills/lifecycle/references/implement.md`
- **What**: Insert a new paragraph titled `**Uncommitted-changes guard**:` immediately after the existing `**Worktree-agent context guard**:` paragraph (currently at line 18) and before the `Dispatch by selection:` block (currently at line 20). The paragraph must:
  - State that immediately before the `AskUserQuestion` call, the skill runs `git status --porcelain` (no path filter, no additional flags).
  - State that on non-empty output, the option that keeps the user on the current branch is demoted: (a) prepend the fixed warning `Warning: uncommitted changes in working tree — this will mix them into the commit on main.` as a one-line prefix to that option's description, and (b) strip the `(recommended)` suffix from that option's label if present.
  - State that the option remains selectable and stays at its existing position (no removal, no gating pre-question).
  - State that on `git status --porcelain` non-zero exit (e.g., missing `.git`, corrupt index, bisect/rebase state), the guard does not fire — neither demotion nor warning prefix are applied — a single-line diagnostic `uncommitted-changes guard skipped: git status failed` is surfaced alongside the prompt, and the pre-flight continues normally as a fallback.
  - Refer to the demoted option abstractly (e.g., "the option that keeps the user on the current branch") rather than by its literal label, so #097's rename does not invalidate the prose.
- **Depends on**: none
- **Context**: Mirror the structural pattern of the `Worktree-agent context guard` paragraph at line 18 — bold label (`**Uncommitted-changes guard**:`), single paragraph, check-and-note-alongside-prompt (not a hard block, not a pre-question). The existing guard's opening phrasing is `"Immediately before the AskUserQuestion call, check the current branch with git branch --show-current."` — use the same "Immediately before the AskUserQuestion call" lead-in. The routing block at lines 20–24 matches against canonical label substrings (`"Implement on main"` / `"Implement on current branch"`); do NOT alter those substrings — only the `(recommended)` suffix (currently absent from option 3 but present post-#097) and the description are touched. Detection convention is established by `skills/pr/SKILL.md:9`, `skills/overnight/SKILL.md:168`, and `claude/statusline.sh:156` — `git status --porcelain` with non-empty stdout. Disposition (demote, not block) deliberately diverges from those precedents per spec Requirement 6. The warning text in Requirement 3 is fixed verbatim — no paraphrase.
- **Verification**:
  - `grep -c 'Uncommitted-changes guard' skills/lifecycle/references/implement.md` returns 1 (Requirement 9).
  - `grep -c 'git status --porcelain' skills/lifecycle/references/implement.md` returns at least 1 (Requirement 1).
  - `grep -c 'If non-empty' skills/lifecycle/references/implement.md` returns at least 1 (Requirement 2, conditional trigger).
  - `grep -c 'prefix' skills/lifecycle/references/implement.md` returns at least 1 (Requirement 2, prefix-prepend step).
  - `grep -c '(recommended)' skills/lifecycle/references/implement.md` returns at least 1 (Requirement 2, suffix-strip step — matches existing `(recommended)` on option 1 today as well; Requirement 2 only requires the substring to be documented).
  - `grep -c 'Warning: uncommitted changes in working tree' skills/lifecycle/references/implement.md` returns exactly 1 (Requirement 3, fixed warning text).
  - `grep -c 'uncommitted-changes guard skipped: git status failed' skills/lifecycle/references/implement.md` returns exactly 1 (Requirement 7, fallback diagnostic).
  - `grep -c 'fallback' skills/lifecycle/references/implement.md` returns at least 1 (Requirement 7, fallback continuation prose).
- **Status**: [x] complete — commit 8af5a14

### Task 2: Add static dirt-behavior caveat to "Implement in autonomous worktree" option description
- **Files**: `skills/lifecycle/references/implement.md`
- **What**: Modify the description of the "Implement in autonomous worktree" option (currently at line 14) to include the one-clause prose note `uncommitted changes remain on main and do not travel to the worktree`. This note is static — present regardless of the porcelain result — because option 2's dirt-stranding behavior is a permanent property, not a conditional. Integrate the clause into the existing description prose; do not add a new line or structural element.
- **Depends on**: none
- **Context**: Line 14's current description starts with `**Implement in autonomous worktree** — dispatch to the daytime pipeline...`. Option routing at line 22 matches against `Implement in autonomous worktree` — do NOT alter that label substring, only extend the description. The caveat should read naturally within the existing em-dash prose (e.g., append as an additional clause near the "When to pick" sentence or integrate into the mechanism description). This is independent of the guard in Task 1: the caveat is always present; the Task 1 guard only fires on dirty porcelain.
- **Verification**:
  - `grep -c 'uncommitted changes remain on main' skills/lifecycle/references/implement.md` returns exactly 1 (Requirement 4).
  - `grep -c 'Implement in autonomous worktree' skills/lifecycle/references/implement.md` returns at least 2 (option label on line 14 plus routing block on line 22 — both unchanged).
- **Status**: [x] complete — commit 3d6c20c

### Task 3: Confirm routing labels and option-removal safety remain intact
- **Files**: `skills/lifecycle/references/implement.md`
- **What**: Verification-only task (no edits). Confirm that after Tasks 1 and 2 land, the canonical routing-match substrings at lines 20–24 (`"Implement on main"`, `"Implement in autonomous worktree"`, `"Implement in worktree"`, `"Create feature branch"`) are still present and unchanged; that the four option bullets at lines 13–16 still exist; and that no early-exit / abort / pre-question flow has been added around the dirty-tree condition.
- **Depends on**: [1, 2]
- **Context**: Requirement 6 forbids any gating pre-question or removal; Requirement 8 forbids any change to the canonical routing label substrings. This task exists as a verification gate to catch a zealous implementer who mirrored warning prose into a label (which would break routing's prose match) or who added a pre-AskUserQuestion halt. Both issues would silently break dispatch without any single grep in Tasks 1 or 2 catching them.
- **Verification**:
  - `grep -cE '"Implement on main"|"Implement on current branch"' skills/lifecycle/references/implement.md` returns at least 1 (Requirement 8).
  - `grep -c '"Implement in autonomous worktree"' skills/lifecycle/references/implement.md` returns at least 1 (routing label intact).
  - `grep -c '"Implement in worktree"' skills/lifecycle/references/implement.md` returns at least 1 (routing label intact).
  - `grep -c '"Create feature branch"' skills/lifecycle/references/implement.md` returns at least 1 (routing label intact).
  - Read lines 11–26 of `skills/lifecycle/references/implement.md` and visually confirm: (a) four option bullets are present in positions 1–4; (b) the new Uncommitted-changes guard paragraph sits adjacent to the Worktree-agent context guard (not inside it, not before the option list); (c) no new AskUserQuestion call, no `exit /lifecycle`, no halt/abort/early-return prose appears tied to the dirty-tree condition; (d) the `Dispatch by selection:` routing block at lines 20–24 is structurally unchanged — same four `If the user selects ...` branches, same canonical substrings.
- **Status**: [x] complete — verification-only, all 14 grep assertions pass and structural read of lines 11–28 confirms (a)-(d)

## Verification Strategy

The acceptance evidence is grep-based plus a small interactive read of §1 for structural assertions that grep cannot make (relative ordering, adjacency, absence-of-halt).

1. Run the grep assertions from Tasks 1, 2, and 3 against `skills/lifecycle/references/implement.md`. All listed counts must match (exactly-N where specified, ≥-N otherwise).
2. Read lines 11–26 of `skills/lifecycle/references/implement.md` and confirm:
   - The `Uncommitted-changes guard` paragraph appears immediately adjacent to the `Worktree-agent context guard` paragraph (Requirement 9, structural adjacency).
   - The `git status --porcelain` call is described as running before the `AskUserQuestion` call (Requirement 1, relative ordering).
   - The guard prose refers to the demoted option abstractly (e.g., "the option that keeps the user on the current branch" or the canonical label) — not in a way that bakes in language #097's rename would invalidate (Requirement 5, forward-compat phrasing).
   - No early-exit, abort, or pre-AskUserQuestion question has been added around the dirty-tree condition (Requirement 6, selection remains unblocked).
   - The four option bullets remain at positions 1–4 (Requirement 8, option routing not disturbed).
3. Symlink propagation: confirm `~/.claude/skills/lifecycle/references/implement.md` is a symlink pointing to the repo copy (`ls -la ~/.claude/skills/lifecycle/references/implement.md`) — edits propagate automatically on next `/lifecycle` invocation. This is a pre-existing repo property, not something this ticket creates; verification confirms it still holds.
4. No test suite exercises the §1 pre-flight prompt flow (per spec Technical Constraints — "No tests to update"). Runtime verification of the guard firing end-to-end requires an interactive `/lifecycle implement` session on `main` with a dirty tree, which is out of scope for this ticket's acceptance and is independently observable by the operator during the next real invocation.
