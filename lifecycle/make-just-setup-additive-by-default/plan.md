# Plan: make-just-setup-additive-by-default

## Overview

Each deploy-* recipe becomes independently additive using an inline classify-then-install pattern. A new `setup-force` recipe inlines the current destructive install behavior. `setup` is converted to a bash block that passes a `CONFLICTS_FILE` env var to each deploy-* recipe so conflicts are aggregated into a single pending list at the end (satisfying spec Requirement 3). When deploy-* recipes are invoked directly without `CONFLICTS_FILE`, they print their own pending section (satisfying spec Requirement 7 — independently usable). All seven tasks modify `justfile` and are strictly sequential.

## Tasks

### Task 1: Add `setup-force` recipe
- **Files**: `justfile`
- **What**: Add a new `setup-force` recipe that inlines all current destructive symlink install behavior unconditionally. Repo owner uses this for a clean re-installation.
- **Depends on**: none
- **Complexity**: complex
- **Context**: Position the recipe between `setup` (line 10) and `deploy-bin` (line 26). Bash block with `#!/usr/bin/env bash`, `set -euo pipefail`. Include the worktree guard pattern from `deploy-bin` (lines 29-33 — check that `git rev-parse --git-dir` equals `--git-common-dir`; exit 1 if in worktree). Then inline all targets unconditionally:
  - **bin** (7 file symlinks → `~/.local/bin/`, use `ln -sf`): `$(pwd)/bin/count-tokens`, `$(pwd)/bin/audit-doc`, `$(pwd)/backlog/update_item.py`, `$(pwd)/backlog/create_item.py`, `$(pwd)/backlog/generate_index.py`, `$(pwd)/bin/jcc`, `$(pwd)/bin/overnight-start`
  - **reference** (4 file symlinks → `~/.claude/reference/`, use `ln -sf`): `verification-mindset.md`, `parallel-agents.md`, `context-file-authoring.md`, `claude-skills.md` from `$(pwd)/claude/reference/`
  - **skills** (directory loop, use `ln -sfn`): `for skill in skills/*/SKILL.md; do name=$(basename "$(dirname "$skill")"); ln -sfn "$(pwd)/skills/$name" "$HOME/.claude/skills/$name"; done`
  - **hooks** — 2 loops:
    - Loop 1: `for hook in hooks/*.sh; do [ -f "$hook" ] || continue; name=$(basename "$hook"); if [ "$name" = "cortex-notify.sh" ]; then ln -sf "$(pwd)/$hook" "$HOME/.claude/notify.sh"; else ln -sf "$(pwd)/$hook" "$HOME/.claude/hooks/$name"; fi; done`
    - Loop 2: `for hook in claude/hooks/*; do [ -f "$hook" ] || continue; name=$(basename "$hook"); ln -sf "$(pwd)/$hook" "$HOME/.claude/hooks/$name"; done`
  - **config** (4 file symlinks, use `ln -sf`): `~/.claude/settings.json` ← `$(pwd)/claude/settings.json`; `~/.claude/statusline.sh` ← `$(pwd)/claude/statusline.sh`; `~/.claude/rules/cortex-global.md` ← `$(pwd)/claude/rules/global-agent-rules.md`; `~/.claude/rules/cortex-sandbox.md` ← `$(pwd)/claude/rules/sandbox-behaviors.md`
  - **settings.local.json**: Write `sandbox.filesystem.allowWrite` for this clone. Path: `ALLOW_PATH="$(pwd)/lifecycle/sessions/"`. If file exists and `jq` is available: append `$ALLOW_PATH` to the existing `allowWrite` array and deduplicate — use `jq --arg path "$ALLOW_PATH"` and an expression that reads the existing array (treating null/missing as `[]`), appends the new path, and removes duplicates using `unique`. Write to a `.tmp` file then `mv` atomically. If file exists but `jq` is absent: print the warning "Warning: jq not found — settings.local.json overwritten. Install jq to preserve allowWrite paths from other clones." then overwrite. If file does not exist: create fresh with just `$ALLOW_PATH` in the array.
  - Call `just python-setup` at the end.
  - Add comment at recipe top: `# Note: when adding new symlink targets to any deploy-* recipe, also add them here.`
- **Verification**: `just setup-force` completes without errors on the owner's machine. `just check-symlinks` passes. No classification output printed. `settings.local.json` contains correct `allowWrite` path; re-running does not duplicate the path.
- **Status**: [x] complete

### Task 2: Refactor `deploy-bin` with classify-then-install
- **Files**: `justfile` (lines 26-41)
- **What**: Replace 7 unconditional `ln -sf` calls with classify-then-install loop. Each target is classified and printed. Conflicts are collected; post-install behavior depends on `CONFLICTS_FILE` env var.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Keep the bash block structure, worktree guard, and `mkdir -p ~/.local/bin`. Add comment `# Note: also update setup-force when adding new targets here.` Replace the 7 `ln -sf` lines with a classify-then-install section. Declare `conflicts=()` array. For each of the 7 targets (same source→target pairs as Task 1 Context):
  - If `! -e "$target" && ! -L "$target"`: print `[new]      $target` → install with `ln -sf "$source" "$target"`
  - If `-L "$target" && [ "$(readlink "$target")" = "$source" ]`: print `[update]   $target` → re-install with `ln -sf "$source" "$target"`
  - If `! -e "$target" && -L "$target"`: print `[conflict] $target — broken symlink` → append `"$target (broken symlink)"` to conflicts
  - If `-L "$target" && [ "$(readlink "$target")" != "$source" ]`: print `[conflict] $target — symlink to $(readlink "$target")` → append `"$target (symlink to $(readlink "$target"))"` to conflicts
  - Else (regular file): print `[conflict] $target — regular file` → append `"$target (regular file)"` to conflicts
  After all targets, if `${#conflicts[@]} -gt 0`:
  - If `${CONFLICTS_FILE:-}` is set: append each conflict entry to `$CONFLICTS_FILE` (one per line). Do NOT print the pending section here.
  - If `CONFLICTS_FILE` is not set (standalone invocation): print the pending section: `N conflict(s) skipped. Open Claude in the cortex-command directory and run: /setup-merge to resolve...` with the list.
- **Verification**: On owner's machine all 7 targets show `[update]`, no conflict section. Fresh machine shows 7 `[new]`. A regular file at one target path shows `[conflict]`; with `CONFLICTS_FILE` set, the conflict is written to the file (not printed as a section); without `CONFLICTS_FILE`, the pending section prints.
- **Status**: [x] complete

### Task 3: Refactor `deploy-reference` — add shebang + classify-then-install
- **Files**: `justfile` (lines 44-49)
- **What**: Add bash shebang + `set -euo pipefail`; convert 4 `ln -sf` calls to classify-then-install with `CONFLICTS_FILE` support.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**: Currently no shebang — plain `just` recipe. Add `#!/usr/bin/env bash` as the first line of the recipe body, then `set -euo pipefail`. Keep `mkdir -p ~/.claude/reference`. Add comment. 4 targets (same pairs as Task 1 Context). Same classify-then-install pattern and `CONFLICTS_FILE` conditional as Task 2.
- **Verification**: `just deploy-reference` on owner's machine shows 4 `[update]` lines, no errors. `just check-symlinks` still passes for reference targets.
- **Status**: [x] complete

### Task 4: Refactor `deploy-skills` with directory symlink classify-then-install
- **Files**: `justfile` (lines 52-59)
- **What**: Add classify-then-install to the directory symlink loop. Install uses `ln -sfn`; expected source path is the directory (not SKILL.md).
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: The loop variable `skill` iterates over `skills/*/SKILL.md` files (used to enumerate names), but the symlink target and source comparison use the parent directory path: `source="$(pwd)/skills/$name"` and `target="$HOME/.claude/skills/$name"`. Classification uses `readlink "$target"` compared to `source` — NOT to the SKILL.md path. Install command: `ln -sfn "$source" "$target"` (directory symlinks require `-n`). Declare `conflicts=()`. After loop, apply same `CONFLICTS_FILE` conditional as Task 2. Add comment `# Note: also update setup-force when adding new targets here.`
- **Verification**: `just deploy-skills` on owner's machine shows `[update]` for all 31+ skills, no conflicts. No directory corruption from using `ln -sfn` correctly.
- **Status**: [x] complete

### Task 5: Refactor `deploy-hooks` with classify-then-install
- **Files**: `justfile` (lines 62-82)
- **What**: Add classify-then-install to both hook loops; collect conflicts across both loops; apply `CONFLICTS_FILE` conditional after both loops complete.
- **Depends on**: [4]
- **Complexity**: simple
- **Context**: Declare a single `conflicts=()` array at the top of the recipe. Both loops append to the same array.
  - Loop 1 (`hooks/*.sh`): apply `[ -f "$hook" ]` guard. Special case: `cortex-notify.sh` → `target="$HOME/.claude/notify.sh"`, `source="$(pwd)/$hook"`. Other hooks: `target="$HOME/.claude/hooks/$name"`. All use `ln -sf`.
  - Loop 2 (`claude/hooks/*`): `target="$HOME/.claude/hooks/$name"`, `source="$(pwd)/$hook"`. All use `ln -sf`.
  After both loops: apply same `CONFLICTS_FILE` conditional as Task 2.
- **Verification**: `just deploy-hooks` on owner's machine shows all `[update]` lines, no conflicts. `cortex-notify.sh` shows `[update] ~/.claude/notify.sh`.
- **Status**: [x] complete

### Task 6: Refactor `deploy-config` — remove prompts, classify, fix jq dedup
- **Files**: `justfile` (lines 85-130)
- **What**: Remove interactive `read -rp` prompts; add classify-then-install for 4 config symlink targets; fix `settings.local.json` jq to append-with-dedup; add jq-absent warning; apply `CONFLICTS_FILE` conditional.
- **Depends on**: [5]
- **Complexity**: complex
- **Context**: Remove the two `for` loops with `read -rp` prompts (lines 91-103 and 105-117). Replace with a single classify-then-install section for all 4 targets:
  - `~/.claude/settings.json` ← `$(pwd)/claude/settings.json`
  - `~/.claude/statusline.sh` ← `$(pwd)/claude/statusline.sh`
  - `~/.claude/rules/cortex-global.md` ← `$(pwd)/claude/rules/global-agent-rules.md`
  - `~/.claude/rules/cortex-sandbox.md` ← `$(pwd)/claude/rules/sandbox-behaviors.md`
  All use `ln -sf`. Same classify-then-install pattern and `CONFLICTS_FILE` conditional as Task 2.
  `settings.local.json` section (lines 119-130): change jq expression so it appends `$path` to the existing `allowWrite` array with deduplication, following the same approach described in Task 1 Context. Use `jq --arg path "$ALLOW_PATH"` (preserving existing `--arg` pattern from line 124). Add the warning for jq-absent: print "Warning: jq not found — settings.local.json overwritten. Install jq to preserve allowWrite paths from other clones." before overwriting. Add comment `# Note: also update setup-force when adding new targets here.`
- **Verification**: 4 `[update]` lines on owner's machine, no conflicts, no prompts. settings.local.json append doesn't duplicate paths. `CONFLICTS_FILE` mechanism works: conflicts written to file, not printed as a section.
- **Status**: [x] complete

### Task 7: Convert `setup` recipe to bash block with CONFLICTS_FILE aggregation
- **Files**: `justfile` (lines 10-22)
- **What**: Convert the `setup` recipe to a bash block that creates a temp `CONFLICTS_FILE`, passes it to each deploy-* recipe, then reads it to print one aggregate pending conflict list at the end.
- **Depends on**: [6]
- **Complexity**: simple
- **Context**: The current `setup` recipe has no shebang — it's a plain `just` recipe calling other recipes. Convert to `#!/usr/bin/env bash`, `set -euo pipefail`. Logic:
  1. Create temp file: `CONFLICTS_FILE=$(mktemp)`. Trap cleanup: `trap "rm -f \"$CONFLICTS_FILE\"" EXIT`.
  2. Call each deploy recipe with env var prefix: `CONFLICTS_FILE="$CONFLICTS_FILE" just deploy-bin`, `CONFLICTS_FILE="$CONFLICTS_FILE" just deploy-reference`, etc. through all 5 deploy-* recipes.
  3. Call `just python-setup` (not passed CONFLICTS_FILE — not needed).
  4. After all deploy recipes: if `$CONFLICTS_FILE` is non-empty (`-s` check): read it, count lines, print the aggregate pending section in spec Requirement 3 format: `N conflict(s) skipped. Open Claude in the cortex-command directory and run:\n  /setup-merge\nto resolve the following targets:\n  - <each line from CONFLICTS_FILE>`.
  5. If no conflicts: omit the pending section entirely (print nothing extra).
  6. Keep existing success message: `echo "Setup complete. Add the following to your shell profile..."` etc.
  Each deploy-* recipe already suppresses its own pending section when `CONFLICTS_FILE` is set (Tasks 2-6). This task adds the `setup`-side aggregation.
- **Verification**: `just setup` on owner's machine: all `[update]` lines, no conflict section, "Setup complete" message at end. With one conflicting target: exactly one pending section with total count at the bottom, one `/setup-merge` instruction. Direct recipe invocation (`just deploy-bin` without CONFLICTS_FILE) still prints per-recipe pending section.
- **Status**: [x] complete

## Verification Strategy

After all tasks complete:
1. Run `just setup` on the owner's machine — all targets show `[update]`, no conflict section, `settings.local.json` path not duplicated.
2. Run `just check-symlinks` — all symlinks intact.
3. Run `just setup-force` — completes without errors; all targets re-created unconditionally.
4. Run `just verify-setup` — all checks pass.
5. Manually validate aggregate pending list: create a regular file at `~/.local/bin/count-tokens`, run `just setup`, verify that `deploy-bin` prints `[conflict]` for that target but the pending section appears ONLY at the end of `just setup` (not also inside `deploy-bin` output), with the correct "1 conflict(s) skipped" format and one `/setup-merge` instruction.
