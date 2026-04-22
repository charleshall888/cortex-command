# Review: add-uncommitted-changes-guard-to-lifecycle-implement-phase-pre-flight

## Stage 1: Spec Compliance

### Requirement 1: Porcelain detection runs before the pre-flight AskUserQuestion
- **Expected**: Immediately before the `AskUserQuestion` call in §1, run `git status --porcelain` (no path filter, no additional flags). Grep witness: `git status --porcelain` ≥ 1; relative ordering confirmed by structural read.
- **Actual**: Line 20 (`**Uncommitted-changes guard**`) explicitly says "Immediately before the `AskUserQuestion` call, run `git status --porcelain` (no path filter, no additional flags)." `grep -c 'git status --porcelain'` = 5 (includes guard paragraph + existing refs). The guard paragraph sits at line 20, which is before the `Dispatch by selection:` block at line 22 and precedes the `AskUserQuestion` semantically (the prompt is described at line 11 and the guard's lead-in explicitly says "Immediately before the AskUserQuestion call").
- **Verdict**: PASS
- **Notes**: Identical lead-in pattern to the adjacent Worktree-agent context guard.

### Requirement 2: Non-empty porcelain output demotes the "Implement on current branch" option
- **Expected**: `If non-empty` ≥ 1 AND `prefix` ≥ 1 AND `(recommended)` ≥ 1.
- **Actual**: `grep -c 'If non-empty'` = 1; `grep -c 'prefix'` = 2; `grep -c '(recommended)'` = 1. All three conditions witnessed on line 20: conditional trigger ("If non-empty output is returned"), prefix-prepend step ("prepend the fixed warning ... as a one-line prefix"), suffix-strip step ("strip the `(recommended)` suffix from that option's label if present").
- **Verdict**: PASS

### Requirement 3: Warning text is fixed
- **Expected**: `grep -c 'Warning: uncommitted changes in working tree'` = 1.
- **Actual**: `grep -c 'Warning: uncommitted changes in working tree'` = 1. The exact prose `Warning: uncommitted changes in working tree — this will mix them into the commit on main.` appears verbatim on line 20.
- **Verdict**: PASS

### Requirement 4: Autonomous worktree option gets a dirt-behavior caveat
- **Expected**: `grep -c 'uncommitted changes remain on main'` = 1.
- **Actual**: `grep -c 'uncommitted changes remain on main'` = 1. The clause "note that uncommitted changes remain on main and do not travel to the worktree" is integrated into line 14's description of the autonomous worktree option — static, present regardless of porcelain state.
- **Verdict**: PASS

### Requirement 5: Forward-compatible phrasing
- **Expected**: Guard prose refers to the demoted option abstractly so #097's rename does not invalidate the guard text.
- **Actual**: Line 20 uses "the option that keeps the user on the current branch" rather than a literal label. Structural read confirms no dependency on the current literal labels ("Implement on main") for the guard's trigger or action text.
- **Verdict**: PASS

### Requirement 6: Selection remains unblocked
- **Expected**: Guard does not remove the option or add a gating pre-question.
- **Actual**: Line 20 explicitly states "The option remains selectable and stays at its existing position — no removal, no gating pre-question." Structural read of lines 11–28 confirms: four option bullets still present at positions 1–4; no early-exit, abort, or pre-AskUserQuestion halt wired to the dirty-tree condition; routing block at lines 22–26 unchanged.
- **Verdict**: PASS

### Requirement 7: Porcelain-failure fallback
- **Expected**: `grep -c 'uncommitted-changes guard skipped: git status failed'` = 1 AND `grep -c 'fallback'` ≥ 1.
- **Actual**: `grep -c 'uncommitted-changes guard skipped: git status failed'` = 1; `grep -c 'fallback'` = 3. Both witnessed on line 20 with explicit fallback continuation prose.
- **Verdict**: PASS

### Requirement 8: Option routing is not disturbed
- **Expected**: `grep -cE '"Implement on main"|"Implement on current branch"'` ≥ 1; routing labels at lines 22–26 unchanged.
- **Actual**: `grep -c '"Implement on main"'` matches on line 25; `grep -c '"Implement in autonomous worktree"'` = 2 (label + routing); `grep -c '"Implement in worktree"'` = 1; `grep -c '"Create feature branch"'` = 1. Routing block at lines 22–26 structurally unchanged — same four `If the user selects …` branches, same canonical substrings.
- **Verdict**: PASS

### Requirement 9: Guard is documented alongside the existing Worktree-agent context guard
- **Expected**: `grep -c 'Uncommitted-changes guard'` = 1; adjacency to Worktree-agent context guard confirmed structurally.
- **Actual**: `grep -c 'Uncommitted-changes guard'` = 1. The new guard paragraph sits at line 20, immediately after the `Worktree-agent context guard` paragraph at line 18 (with a single blank line between them on line 19). Same structural pattern: bold label, single paragraph, check-and-note-alongside-prompt.
- **Verdict**: PASS

## Requirements Drift

**State**: none
**Findings**:
- None
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: `**Uncommitted-changes guard**:` label mirrors the adjacent `**Worktree-agent context guard**:` label (hyphenated compound modifier + "guard" suffix + colon). Consistent.
- **Error handling**: Fallback on `git status --porcelain` non-zero exit is documented correctly: guard does not fire, single-line diagnostic is surfaced alongside the prompt (not as a separate halt), and pre-flight continues. Enumerated trigger scenarios (missing `.git`, corrupt index, bisect/rebase state) match the spec's Edge Cases section.
- **Test coverage**: Plan's Verification Strategy executed — all 14 grep assertions (Tasks 1, 2, and 3) match the expected counts; structural read of lines 11–28 confirms adjacency, relative ordering, abstract phrasing, absence of halt, and intact routing block. No test suite updates required per spec Technical Constraints. Symlink still in place at `~/.claude/skills/lifecycle/references/implement.md`.
- **Pattern consistency**: The new paragraph mirrors the existing context guard's structure — same `Immediately before the AskUserQuestion call` lead-in, single paragraph, bold label, conditional with alongside-prompt note rather than a hard block. No new code path, no script, no structural element added.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
