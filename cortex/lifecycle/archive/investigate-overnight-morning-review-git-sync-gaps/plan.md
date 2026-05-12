# Plan: investigate-overnight-morning-review-git-sync-gaps

## Overview

Migrate overnight artifact commits from local `main` to the integration branch worktree, add a post-PR-merge sync step with multi-pass conflict resolution to morning review, and create a shared sync-rebase script with a pattern-based allowlist. Key architectural decisions: redirect `extract_batch_specs()` to write to the worktree path (avoiding a `plan.py` refactor), and copy all backlog files from `$REPO_ROOT` to the worktree before the artifact commit (since `_write_back_to_backlog()` writes to the real repo, not the worktree).

## Tasks

### Task 1: Create sync-allowlist.conf
- **Files**: `claude/overnight/sync-allowlist.conf`
- **What**: Create the shared allowlist file with glob patterns for files safe to auto-resolve with `--theirs` during post-merge rebase.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Patterns must cover the files from runner.sh Phase D artifact commit (lines 986–993): `lifecycle/sessions/*/`, `lifecycle/*/research.md`, `lifecycle/*/spec.md`, `lifecycle/*/plan.md`, `lifecycle/*/agent-activity.jsonl`, `lifecycle/pipeline-events.log`, `backlog/index.md`, `backlog/archive/*`, `backlog/[0-9]*-*.md` (individual item files with overnight status updates). Also include morning report files: `lifecycle/sessions/*/morning-report.md`, `lifecycle/morning-report.md`. Format: one glob per line, `#` for comments.
- **Verification**: `test -f claude/overnight/sync-allowlist.conf` — pass if exit 0; `grep -c '^[^#]' claude/overnight/sync-allowlist.conf` — pass if count ≥ 8 (at least 8 non-comment patterns)
- **Status**: [x] complete

### Task 2: Create git-sync-rebase.sh script
- **Files**: `bin/git-sync-rebase.sh`
- **What**: Create a shell script that performs the full post-merge sync: dirty rebase guard, fetch, rebase with multi-pass allowlist-based conflict resolution, and push. Exit codes: 0 = success, 1 = conflict (aborted, user must resolve), 2 = push failed (rebase succeeded).
- **Depends on**: [1]
- **Complexity**: complex
- **Context**: The script accepts an allowlist file path as its first argument (default: `claude/overnight/sync-allowlist.conf`). Flow: (1) check for `.git/rebase-merge/` or `.git/rebase-apply/` — if present, `git rebase --abort` and warn; (2) `git fetch origin`; (3) check `git rev-list HEAD..origin/main --count` — if 0, skip rebase; (4) `git pull --rebase origin main`; (5) if conflicts, enter multi-pass loop: identify conflicted files via `git diff --name-only --diff-filter=U`, match each against allowlist globs, `git checkout --theirs` + `git add` for matches, count remaining non-allowlist conflicts, if >3 or unresolvable `git rebase --abort` and exit 1, else `git rebase --continue` and re-enter loop if new conflicts; (6) `git push origin main` — exit 2 on failure. Glob matching: use bash `fnmatch`-style pattern matching against each allowlist line. Must not require interactive input (sandbox constraint).
- **Verification**: `test -x bin/git-sync-rebase.sh` — pass if exit 0; `head -1 bin/git-sync-rebase.sh | grep -c '#!/'` — pass if count = 1
- **Status**: [x] complete

### Task 3: Update runner.sh — redirect session artifact copies to worktree
- **Files**: `claude/overnight/runner.sh`
- **What**: Change the session artifact copy block (lines 974–977) to copy batch results and overnight-strategy to `$WORKTREE_PATH/lifecycle/sessions/${SESSION_ID}/` instead of `$REPO_ROOT/lifecycle/sessions/${SESSION_ID}/`.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Current code at lines 974-977: `mkdir -p "$REPO_ROOT/lifecycle/sessions/${SESSION_ID}/"` followed by `cp` commands targeting the same directory. Change `$REPO_ROOT` to `$WORKTREE_PATH` in the `mkdir` and all `cp` targets. The `2>/dev/null || true` on the cp commands is acceptable here — some files may legitimately not exist if no batch results were produced.
- **Verification**: `grep -c 'WORKTREE_PATH.*lifecycle/sessions' claude/overnight/runner.sh` — pass if count ≥ 3 (mkdir + 2 cp lines); `grep -c 'REPO_ROOT.*lifecycle/sessions.*SESSION_ID' claude/overnight/runner.sh` — pass if count = 0 in the copy block (lines 974-977 range)
- **Status**: [x] complete

### Task 4: Update runner.sh — Phase D artifact commit to worktree
- **Files**: `claude/overnight/runner.sh`
- **What**: Change the Phase D artifact commit subshell (lines 984–1000) to: (a) add a pre-commit step that copies ALL backlog files from `$REPO_ROOT/backlog/` to `$WORKTREE_PATH/backlog/` (individual item files with status updates, archive, and index); (b) change `cd "$REPO_ROOT"` to `cd "$WORKTREE_PATH"`; (c) expand `git add` to include `backlog/` (all backlog files, not just index.md and archive).
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: `_write_back_to_backlog()` in `batch_runner.py` (line 1146) writes individual item status updates (e.g., `status: complete`) to `$REPO_ROOT/backlog/NNN-*.md` via `_PROJECT_ROOT` (line 1071). These files never reach the worktree automatically. The `backlog/index.md` in `$REPO_ROOT` may also be stale (index regeneration uses CWD-relative paths, and CWD is the worktree during batch execution). Therefore: copy the entire `$REPO_ROOT/backlog/` directory to `$WORKTREE_PATH/backlog/` before the artifact commit. Use `cp -r "$REPO_ROOT/backlog/"* "$WORKTREE_PATH/backlog/"` to bring all item changes, then `git add backlog/` to capture everything. The `lifecycle/*/research.md`, `spec.md`, `plan.md`, `agent-activity.jsonl` already exist in the worktree (arrived via feature branch merges). `lifecycle/sessions/${SESSION_ID}/` exists in the worktree after Task 3's copy. Verify that `lifecycle/pipeline-events.log` is written to the worktree CWD during batch execution — if it resolves to a different path, add an explicit copy.
- **Verification**: `grep -c 'cd.*WORKTREE_PATH' claude/overnight/runner.sh` — pass if count ≥ 2 (the original line 595 + the new Phase D subshell); `grep 'cp.*REPO_ROOT.*backlog.*WORKTREE_PATH' claude/overnight/runner.sh` — pass if matches exist
- **Status**: [x] complete

### Task 5: Redirect batch spec extraction to worktree
- **Files**: `skills/overnight/SKILL.md`
- **What**: Change the batch spec extraction instruction (current Step 4, item 4) to call `extract_batch_specs(state, worktree_path)` with the worktree path instead of the repo root. Commit the extracted specs in the worktree context (on the integration branch) instead of on main.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `initialize_overnight_state()` in `claude/overnight/plan.py` creates both the `OvernightState` object AND the worktree atomically — they cannot be separated without a significant refactor. Instead of reordering extraction before worktree creation, redirect the extraction to write directly to the worktree. `extract_batch_specs(state: OvernightState, project_root: Path) -> list[Path]` already accepts `project_root` as a parameter — pass the worktree path (available from the state's `worktree_path` field or from `overnight-state.json`). After extraction, `git add` and `/commit` must run in the worktree context (not the repo root). Update the SKILL.md instruction to: (1) read the worktree path from the initialized state; (2) call `extract_batch_specs(state, Path(worktree_path))`; (3) `cd` to the worktree for the `git add` + `/commit` step. Note: the returned file paths will be relative to the worktree, not the repo root.
- **Verification**: Interactive/session-dependent: the change is in a SKILL.md instruction file — verification requires running `/overnight` and confirming batch specs are committed on the integration branch, not main.
- **Status**: [x] complete

### Task 6: Add post-merge sync to morning review walkthrough
- **Files**: `skills/morning-review/references/walkthrough.md`
- **What**: Add a Section 6a after the existing PR merge (Section 6, item 5 "On success") that performs the post-merge sync by calling `git-sync-rebase.sh` and handling its exit codes.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**: Insert after walkthrough.md line 306 (end of worktree removal block). New Section 6a: "Post-merge sync". Protocol: (1) run `git-sync-rebase.sh claude/overnight/sync-allowlist.conf`; (2) exit 0: report "Local main synced and pushed — fully up to date."; (3) exit 1: report "Sync encountered unresolvable conflicts. Local main is diverged — resolve manually with `git pull --rebase origin main`."; (4) exit 2: report "Rebase succeeded but push failed. Run `git push origin main` when network is available.". Update the success message on line 301 from "Merged — main is now up to date. Remote branch deleted." to just "Merged. Remote branch deleted." (the "up to date" message moves to the sync step's success path).
- **Verification**: `grep -c 'git-sync-rebase' skills/morning-review/references/walkthrough.md` — pass if count ≥ 1; `grep -c 'Post-merge sync' skills/morning-review/references/walkthrough.md` — pass if count ≥ 1
- **Status**: [x] complete

### Task 7: Update morning review SKILL.md
- **Files**: `skills/morning-review/SKILL.md`
- **What**: Add a brief reference to the new post-merge sync step after Step 6, noting that the walkthrough's Section 6a handles local/remote sync after PR merge including a push to origin.
- **Depends on**: [6]
- **Complexity**: simple
- **Context**: Current Step 6 (SKILL.md line 123-125) references the walkthrough for the full protocol. This task adds a note that Step 6 now includes a post-merge sync and push, so agents scanning the SKILL.md (without reading the walkthrough) know about the new behavior.
- **Verification**: `grep -c 'sync\|push' skills/morning-review/SKILL.md` — pass if count ≥ 1 (new reference to sync/push behavior)
- **Status**: [x] complete

### Task 8: Add edge cases to morning review walkthrough
- **Files**: `skills/morning-review/references/walkthrough.md`
- **What**: Add new edge case rows to the walkthrough's Edge Cases table for: sync script not found, dirty rebase state detected and cleaned, push failure after successful rebase, all conflicts auto-resolved by allowlist.
- **Depends on**: [6]
- **Complexity**: simple
- **Context**: The Edge Cases table starts at walkthrough.md line 315. Add rows: `| git-sync-rebase.sh not found | Report missing script, skip sync, note "run just deploy-bin to install" |`, `| Dirty .git/rebase-merge/ detected | Script auto-aborts stale rebase, warns user, proceeds with sync |`, `| Push fails after rebase | Report error, note local main is clean but not pushed |`, `| All conflicts auto-resolved | Report "N files auto-resolved via allowlist" |`.
- **Verification**: `grep -c 'sync-rebase\|rebase-merge\|Push fails\|auto-resolved' skills/morning-review/references/walkthrough.md` — pass if count ≥ 4
- **Status**: [x] complete

### Task 9: Deploy git-sync-rebase.sh and add allow rule
- **Files**: `bin/git-sync-rebase.sh`, `justfile`, `claude/settings.json`
- **What**: Add the script pair to the justfile's `deploy-bin` recipe (which uses an explicit pairs array, not a glob), make the script executable, add `Bash(git-sync-rebase.sh *)` to the settings.json allow list, and run `just deploy-bin` to deploy.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**: The justfile's `deploy-bin` recipe (around line 130) uses a hardcoded `pairs` array. Add the entry `"$(pwd)/bin/git-sync-rebase.sh|$HOME/.local/bin/git-sync-rebase.sh"` to the array. In `claude/settings.json`, add `"Bash(git-sync-rebase.sh *)"` to the `allow` array under `permissions` to ensure the script runs without prompts in non-sandboxed contexts. Run `chmod +x bin/git-sync-rebase.sh` and `just deploy-bin` to deploy.
- **Verification**: `test -x ~/.local/bin/git-sync-rebase.sh` — pass if exit 0 (script deployed and executable); `grep -c 'git-sync-rebase' justfile` — pass if count ≥ 1; `grep -c 'git-sync-rebase' claude/settings.json` — pass if count ≥ 1
- **Status**: [x] complete

## Verification Strategy

End-to-end verification requires running a full overnight session followed by morning review:

1. Run `/overnight` — confirm no artifact commits on local `main` (only morning report), integration branch contains artifacts including backlog status updates.
2. Run `/morning-review` — confirm PR merge succeeds, post-merge sync runs, local main is synced and pushed (`git rev-list HEAD..origin/main --count` = 0 and `git rev-list origin/main..HEAD --count` = 0).
3. Verify `backlog/` changes (individual item status updates, index, archive) are in the merged PR (not stranded on local main).

Interactive/session-dependent: full E2E verification requires an overnight session. Individual tasks have unit-level verification steps.
