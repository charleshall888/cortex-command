# Plan: prep-hooks-and-apikey-for-sharing

## Overview

Rename 12 hook files to the `cortex-` prefix using `git mv`, then cascade updates across all reference sites (settings.json, justfile, docs, tests, skills, claude/ code) in parallel — all before a final verify-and-commit task. Tasks 1 and 2 are serialized (Task 2 depends on Task 1) to avoid git index lock contention from concurrent `git mv` operations. Tasks 3–9 are independent of each other and can run in parallel. Deploy steps (`just deploy-hooks`, `just deploy-config`) are not automated — they must be run by the primary user after the commit.

## Tasks

### Task 1: Rename 5 hook files in hooks/
- **Files**: `hooks/cortex-cleanup-session.sh` (renamed from `cleanup-session.sh`), `hooks/cortex-notify-remote.sh`, `hooks/cortex-notify.sh`, `hooks/cortex-scan-lifecycle.sh`, `hooks/cortex-validate-commit.sh`
- **What**: Use `git mv` to rename each file to its `cortex-` prefixed name, preserving git history.
- **Depends on**: none
- **Complexity**: simple
- **Context**: All 5 files live in `hooks/`. Use `git mv hooks/validate-commit.sh hooks/cortex-validate-commit.sh` (and similarly for each). Do not modify file contents. Reference updates happen in Tasks 3–9.
- **Verification**: `git ls-files hooks/` shows only `cortex-*` prefixed files (no bare `validate-commit.sh`, `cleanup-session.sh`, etc.).
- **Status**: [ ] pending

### Task 2: Rename 7 hook files in claude/hooks/
- **Files**: `claude/hooks/cortex-permission-audit-log.sh`, `claude/hooks/cortex-setup-gpg-sandbox-home.sh`, `claude/hooks/cortex-skill-edit-advisor.sh`, `claude/hooks/cortex-sync-permissions.py`, `claude/hooks/cortex-tool-failure-tracker.sh`, `claude/hooks/cortex-worktree-create.sh`, `claude/hooks/cortex-worktree-remove.sh`
- **What**: Use `git mv` to rename each claude/hooks/ file to its `cortex-` prefixed name.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: All 7 files live in `claude/hooks/`. Apply `git mv claude/hooks/<name> claude/hooks/cortex-<name>` for each. Python file: `git mv claude/hooks/sync-permissions.py claude/hooks/cortex-sync-permissions.py`. Do not modify file contents. Reference updates happen in Tasks 3–9. Serialized after Task 1 to avoid concurrent `.git/index.lock` contention.
- **Verification**: `git ls-files claude/hooks/` shows only `cortex-*` prefixed files.
- **Status**: [ ] pending

### Task 3: Update 11 hook path references in claude/settings.json
- **Files**: `claude/settings.json`
- **What**: Update all `~/.claude/hooks/<name>` path strings in the hooks block to use their new `cortex-*` names. The two `~/.claude/notify.sh` entries (lines 264, 281) are unchanged. The WorktreeCreate/WorktreeRemove inline bash strings (lines 317, 325) each contain `$CWD/claude/hooks/worktree-create.sh` and `worktree-remove.sh` — update only the filename portion inside the bash string.
- **Depends on**: none
- **Complexity**: simple
- **Context**: File: `claude/settings.json`. Updated entries (old → new filename in path):
  - `sync-permissions.py` → `cortex-sync-permissions.py` (line 219)
  - `scan-lifecycle.sh` → `cortex-scan-lifecycle.sh` (line 224)
  - `setup-gpg-sandbox-home.sh` → `cortex-setup-gpg-sandbox-home.sh` (line 229)
  - `cleanup-session.sh` → `cortex-cleanup-session.sh` (line 240)
  - `validate-commit.sh` → `cortex-validate-commit.sh` (line 251)
  - `notify-remote.sh permission` → `cortex-notify-remote.sh permission` (line 268)
  - `permission-audit-log.sh` → `cortex-permission-audit-log.sh` (line 272)
  - `notify-remote.sh complete` → `cortex-notify-remote.sh complete` (line 285)
  - `tool-failure-tracker.sh` → `cortex-tool-failure-tracker.sh` (line 293)
  - `skill-edit-advisor.sh` → `cortex-skill-edit-advisor.sh` (line 302)
  - WorktreeCreate (line 317): `worktree-create.sh` inside the inline bash string → `cortex-worktree-create.sh`
  - WorktreeRemove (line 325): `worktree-remove.sh` inside the inline bash string → `cortex-worktree-remove.sh`
  The inline bash strings at lines 317 and 325 are JSON string values containing a `bash -c '...'` command. Two filenames appear inside: one in the `-f "$CWD/claude/hooks/..."` existence check and one in the `bash "$CWD/claude/hooks/..."` invocation. Both must be updated. Preserve all JSON escaping.
- **Verification**: `grep -c 'hooks/validate-commit\|hooks/cleanup-session\|hooks/scan-lifecycle\|hooks/notify-remote\|hooks/permission-audit-log\|hooks/tool-failure-tracker\|hooks/skill-edit-advisor\|hooks/sync-permissions\|hooks/setup-gpg-sandbox-home\|hooks/worktree-create\|hooks/worktree-remove' claude/settings.json` returns 0. `python3 -c "import json; json.load(open('claude/settings.json'))"` exits 0.
- **Status**: [ ] pending

### Task 4: Update justfile — 4 changes
- **Files**: `justfile`
- **What**: Apply 4 changes to the justfile: (a) update the `deploy-hooks` special-case check, (b) update the `validate-commit` recipe, (c) update the `check-symlinks` recipe, and (d) add the apiKeyHelper symlink step to `deploy-config`.
- **Depends on**: none
- **Complexity**: simple
- **Context**: File: `justfile`. Four changes:
  1. `deploy-hooks` recipe (around line 72): change `if [ "$name" = "notify.sh" ]` → `if [ "$name" = "cortex-notify.sh" ]`. The ln target stays `"$HOME/.claude/notify.sh"` — do not change the destination.
  2. `validate-commit` recipe (around line 420): change `bash hooks/validate-commit.sh` → `bash hooks/cortex-validate-commit.sh`.
  3. `check-symlinks` recipe (around lines 448–455): update all 8 `~/.claude/hooks/<name>` entries to their `cortex-*` names. Remove the entry for `~/.claude/hooks/setup-github-pat.sh` entirely.
  4. `deploy-config` recipe (around line 85): add `~/.claude/get-api-key.sh` to the for-loop target list. Add the case arm: `*get-api-key.sh) ln -sf "$(pwd)/claude/get-api-key.sh" "$target" ;;`. The new target goes through the same regular-file guard as the existing targets (the guard fires only when the target is a non-symlink regular file — adding to the loop automatically includes it).
- **Verification**: `just validate-commit msg="Test: valid message"` exits 0. `grep setup-github-pat justfile` returns nothing. `grep 'cortex-notify\.sh' justfile` matches the updated deploy-hooks check.
- **Status**: [ ] pending

### Task 5: Create claude/get-api-key.sh stub
- **Files**: `claude/get-api-key.sh` (new file)
- **What**: Create the apiKeyHelper stub script. The stub delegates to `~/.claude/get-api-key-local.sh` if it exists; otherwise exits 0 with no output. Mark the file executable.
- **Depends on**: none
- **Complexity**: simple
- **Context**: New file: `claude/get-api-key.sh`. Shell script with shebang `#!/usr/bin/env bash`. Logic: if `$HOME/.claude/get-api-key-local.sh` exists and is executable, `exec "$HOME/.claude/get-api-key-local.sh" "$@"`; otherwise exit 0 with no output. After writing: `chmod +x claude/get-api-key.sh`. Must be executable before staging.
- **Verification**: `ls -la claude/get-api-key.sh` shows executable bit set. `output=$(bash claude/get-api-key.sh); echo "exit=$? output='$output'"` prints `exit=0 output=''` when no local override exists. `bash -n claude/get-api-key.sh` exits 0.
- **Status**: [ ] pending

### Task 6: Update hook references in docs/
- **Files**: `docs/agentic-layer.md`, `docs/setup.md`, `docs/sdk.md`
- **What**: Update all old hook filenames to their `cortex-*` names in three documentation files.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - `docs/agentic-layer.md`: structured list at lines 214–226 (11 entries) and prose references at lines 270–275. Update all occurrences of old hook names.
  - `docs/setup.md`: 4 references including manual `ln -sf` examples at lines 199–200 (update both source and destination filenames in the example commands) and a table at lines 292–293.
  - `docs/sdk.md`: 3 references to worktree hooks at lines 96, 103, 111.
- **Verification**: `grep -rn 'validate-commit\.sh\|cleanup-session\.sh\|scan-lifecycle\.sh\|notify-remote\.sh\|permission-audit-log\.sh\|tool-failure-tracker\.sh\|skill-edit-advisor\.sh\|sync-permissions\.py\|setup-gpg-sandbox-home\.sh\|worktree-create\.sh\|worktree-remove\.sh' docs/` returns no matches.
- **Status**: [ ] pending

### Task 7: Update hook references in tests/
- **Files**: `tests/test_skill_behavior.sh`, `tests/test_hook_commit.sh`, `tests/test_hooks.sh`, `tests/test_tool_failure_tracker.sh`, `tests/lifecycle_phase.py`
- **What**: Update old hook path strings in all test files to use the new `cortex-*` names.
- **Depends on**: none
- **Complexity**: simple
- **Context**: All test files reference hooks via `$REPO_ROOT/hooks/<name>` or `$REPO_ROOT/claude/hooks/<name>` patterns. Replace the filename component only. Specific locations:
  - `test_skill_behavior.sh:17`: `HOOK="$REPO_ROOT/hooks/validate-commit.sh"` → `cortex-validate-commit.sh`
  - `test_hook_commit.sh:16`: same pattern
  - `test_hooks.sh` lines 10, 97, 185, 204, 301, 330: update each hook filename
  - `test_tool_failure_tracker.sh:19`: `HOOK="$REPO_ROOT/claude/hooks/tool-failure-tracker.sh"` → `cortex-tool-failure-tracker.sh`
  - `lifecycle_phase.py:5`: comment referencing `hooks/scan-lifecycle.sh` → `hooks/cortex-scan-lifecycle.sh`
- **Verification**: `grep -rn 'validate-commit\.sh\|cleanup-session\.sh\|scan-lifecycle\.sh\|notify-remote\.sh\|permission-audit-log\.sh\|tool-failure-tracker\.sh\|skill-edit-advisor\.sh\|sync-permissions\.py\|setup-gpg-sandbox-home\.sh\|worktree-create\.sh\|worktree-remove\.sh' tests/` returns no matches.
- **Status**: [ ] pending

### Task 8: Update hook references in skills/ prose
- **Files**: `skills/lifecycle/SKILL.md`, `skills/lifecycle/references/implement.md`
- **What**: Update two prose references to `worktree-create.sh` to use the new `cortex-worktree-create.sh` name.
- **Depends on**: none
- **Complexity**: trivial
- **Context**:
  - `skills/lifecycle/SKILL.md:373`: update `worktree-create.sh` → `cortex-worktree-create.sh`
  - `skills/lifecycle/references/implement.md:56`: same update
- **Verification**: `grep -rn 'worktree-create\.sh\|worktree-remove\.sh' skills/` returns no matches (or only `cortex-*` references).
- **Status**: [ ] pending

### Task 9: Update hook references in claude/ directory files
- **Files**: `claude/dashboard/alerts.py`, `claude/overnight/runner.sh`, `claude/overnight/report.py`, `claude/statusline.sh`
- **What**: Update hook references in four files in the `claude/` directory. The `alerts.py` change is a live runtime path; the others are comments/docstrings.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - `claude/dashboard/alerts.py:112`: runtime path — `notify_remote_sh = root / "hooks" / "notify-remote.sh"` → `root / "hooks" / "cortex-notify-remote.sh"`. This is a `pathlib.Path` construction; change only the filename string.
  - `claude/overnight/runner.sh:794`: comment mentioning `setup-gpg-sandbox-home.sh` → `cortex-setup-gpg-sandbox-home.sh`
  - `claude/overnight/report.py:204`: docstring mentioning `tool-failure-tracker.sh` → `cortex-tool-failure-tracker.sh`
  - `claude/statusline.sh:377`: comment mentioning `scan-lifecycle.sh` → `cortex-scan-lifecycle.sh`
- **Verification**: `grep -rn 'validate-commit\.sh\|cleanup-session\.sh\|scan-lifecycle\.sh\|notify-remote\.sh\|permission-audit-log\.sh\|tool-failure-tracker\.sh\|skill-edit-advisor\.sh\|sync-permissions\.py\|setup-gpg-sandbox-home\.sh\|worktree-create\.sh\|worktree-remove\.sh' claude/` (excluding `claude/settings.json` and `claude/hooks/`) returns no matches.
- **Status**: [ ] pending

### Task 10: Verify and commit atomically
- **Files**: none
- **What**: Confirm all reference updates pass the AC grep, run the test suite against repo-relative hook paths, and create a single commit containing all changes from Tasks 1–9.
- **Depends on**: [1, 2, 3, 4, 5, 6, 7, 8, 9]
- **Complexity**: simple
- **Context**: Sequence:
  1. Run Req 4 AC grep: `grep -rn 'validate-commit\.sh\|cleanup-session\.sh\|scan-lifecycle\.sh\|notify-remote\.sh\|permission-audit-log\.sh\|tool-failure-tracker\.sh\|skill-edit-advisor\.sh\|sync-permissions\.py\|setup-gpg-sandbox-home\.sh\|worktree-create\.sh\|worktree-remove\.sh' docs/ tests/ skills/ claude/` (exclude `claude/settings.json` and `claude/hooks/`). Must return zero matches.
  2. Check JSON: `python3 -c "import json; json.load(open('claude/settings.json'))"` exits 0.
  3. Run test suite: `just test` — tests reference hook scripts via `$REPO_ROOT/hooks/cortex-*` paths (repo-relative, no deploy needed).
  4. Use `/commit` skill to create a single commit with subject: `Rename hook files to cortex-* prefix and add apiKeyHelper stub`.
  
  **Post-commit human steps (not automated)**: After the commit is created, the primary user must run these manually:
  - `just deploy-hooks` — deploys renamed symlinks; confirm `~/.claude/notify.sh` → `hooks/cortex-notify.sh` and `~/.claude/hooks/cortex-validate-commit.sh` etc. exist. Run immediately after pulling — do not start a new Claude Code session before this step (see `notify.sh` transition window).
  - `just deploy-config` — deploys `claude/get-api-key.sh` stub to `~/.claude/get-api-key.sh`.
  - `just check-symlinks` — verify all hook symlinks exist with new names.
  - Interactive startup verification (Req 9): open a new Claude Code session and confirm no startup error related to `apiKeyHelper`.
- **Verification**: AC grep returns zero matches. `python3 -c "import json; json.load(open('claude/settings.json'))"` exits 0. `just test` passes. Single commit in `git log --oneline -1`.
- **Status**: [ ] pending

## Verification Strategy

After Task 10 creates the commit, the primary user completes post-commit steps manually:

1. `just deploy-hooks` (run before any new Claude Code session — notify.sh transition window)
2. `just deploy-config`
3. `just check-symlinks` — all hook entries report present
4. `just test` — passes (also confirms deploy-hooks correctly wired the hooks)
5. `ls -la ~/.claude/notify.sh` — shows symlink to `hooks/cortex-notify.sh`
6. `ls -la ~/.claude/get-api-key.sh` — shows symlink to repo stub
7. `output=$(bash claude/get-api-key.sh); echo "exit=$? output='$output'"` — prints `exit=0 output=''`
8. Interactive startup verification (Req 9): open new Claude Code session, confirm no `apiKeyHelper` startup error
