# Debug Session: setup-merge fails on directory targets
Date: 2026-04-08
Status: Resolved

## Phase 1 Findings
- **Observed behavior**: `just setup` (via `setup-force`) and `/setup-merge` conflict-file
  remediation both silently fail when the symlink target is a real directory (e.g.,
  `~/.claude/skills/devils-advocate`). `ln -sfn` creates a symlink *inside* the directory
  instead of replacing it.
- **Evidence gathered**:
  - `setup-force` justfile:65 — blindly runs `ln -sfn` for all skills, no directory guard
  - `/setup-merge` SKILL.md conflict-file handling — runs `ln {ln_flag}`, same failure
  - `deploy-skills` recipe correctly detects directories as `[conflict]` and defers, but
    the deferred remediation (setup-merge) was also broken
  - `check-symlinks` justfile:715 still listed `settings.json` as a symlink, but
    `setup-merge` manages it as a merged regular file
- **Dead-ends**: None — root cause was clear from the report and code inspection.

## Phase 2 Findings
- **Pattern**: `deploy-skills` already handles this correctly by classifying real directories
  as conflicts and deferring. The bug was in the two code paths that actually attempt the
  `ln` command without a directory guard.

## Current State
Root cause identified: `ln -sfn` cannot atomically replace a real directory.

Fixes applied:
1. `justfile` setup-force skill loop: added `[ -d "$target" ] && [ ! -L "$target" ]` guard
   with `rm -rf` before `ln -sfn`
2. `SKILL.md` conflict-file handling: split into directory vs file sub-paths; directories
   get `rm -rf` then `ln`, files get the existing diff+replace flow
3. `check-symlinks`: removed `settings.json` from symlink inventory (managed by setup-merge
   as a merged regular file, not a symlink)
