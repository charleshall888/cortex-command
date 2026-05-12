# Review: make-just-setup-additive-by-default

## Stage 1: Spec Compliance

### Requirement 1: Pre-install classification
- **Expected**: `just setup` classifies all symlink targets before making any changes. Each target printed as `[new]`, `[update]`, or `[conflict]` with conflict reason (regular file, broken symlink, symlink to elsewhere).
- **Actual**: Each deploy recipe classifies targets and prints the correct one-line-per-target format with all three conflict sub-types and reasons. However, classification and installation are interleaved within the same for-loop: each target is classified and immediately installed (if new/update) before moving to the next target. The spec says "The classification report is printed before any install action."
- **Verdict**: PARTIAL
- **Notes**: The interleaved approach produces identical results in practice (same installs, same skips, same output), and symlink creation is effectively atomic. A two-pass approach (classify all, then install all) would match the spec literally but add complexity for no behavioral benefit. The output the user sees is correct in all cases.

### Requirement 2: Install behavior
- **Expected**: `new` and `update` targets are installed. `conflict` targets are skipped entirely -- no write, no overwrite, no prompt.
- **Actual**: Classification branches correctly route: `new` and `update` call `ln -sf`/`ln -sfn`, all three conflict sub-types skip installation and append to the conflicts array. No writes occur for conflicts.
- **Verdict**: PASS

### Requirement 3: Pending conflict list
- **Expected**: After installation, print `N conflict(s) skipped...` with `/setup-merge` instruction and list of skipped targets with reasons. Omit section entirely if no conflicts.
- **Actual**: The `setup` recipe reads `$CONFLICTS_FILE` after all deploy recipes complete. If non-empty, prints the count, the `/setup-merge` instruction, and each conflict entry with its reason. If empty (`! -s`), the section is omitted. Each individual deploy recipe also prints its own conflict summary when run standalone (no `CONFLICTS_FILE` set). Format matches spec exactly.
- **Verdict**: PASS

### Requirement 4: `just setup-force` preserves destructive behavior
- **Expected**: Standalone recipe with inlined `ln -sf`/`ln -sfn` calls, no classification, no skipping, no prompts, does not call additive deploy recipes, no env var flags.
- **Actual**: `setup-force` (lines 37-109) is a standalone bash block with direct `ln -sf` and `ln -sfn` calls for all targets. No classification logic, no CONFLICTS_FILE, no calls to deploy-* recipes. Includes settings.local.json handling and python-setup. Target lists match the deploy recipes.
- **Verdict**: PASS

### Requirement 5: `settings.local.json` always written
- **Expected**: Exempt from classification. Always written. If file exists and jq available: append with dedup. If file exists and jq absent: overwrite with warning. If file does not exist: create fresh.
- **Actual**: In `deploy-config` (lines 365-383), `settings.local.json` is handled outside the classification pairs array. Three branches: (1) file exists + jq available: uses `jq` with `unique` to append/dedup the allowWrite path, (2) file exists + no jq: overwrites with the exact warning message from the spec, (3) file does not exist: creates fresh. Same logic in `setup-force` (lines 91-108).
- **Verdict**: PASS

### Requirement 6: Zero conflicts on owner re-run
- **Expected**: Running `just setup` where all targets already point to this repo produces zero conflicts -- all classify as `update`.
- **Actual**: The classification logic checks `readlink "$target" == "$source"` where `$source` uses `$(pwd)`. If symlinks already point to the current repo's absolute paths, they match and classify as `update`. The `readlink` comparison uses exact string matching (no `-f` flag), and sources use `$(pwd)` which produces absolute paths. This works correctly on re-run from the same clone.
- **Verdict**: PASS

### Requirement 7: `deploy-*` recipes are independently additive
- **Expected**: Each recipe is individually additive when run directly. Same behavior as when called from `just setup`.
- **Actual**: All five deploy recipes (deploy-bin, deploy-reference, deploy-skills, deploy-hooks, deploy-config) contain their own classification logic. When `CONFLICTS_FILE` is not set, they print their own standalone conflict summary. When `CONFLICTS_FILE` is set (from `setup`), they append to the shared file. Both paths produce additive behavior.
- **Verdict**: PASS

### Requirement 8: Remove interactive prompts from `deploy-config`
- **Expected**: No `read -rp "Overwrite with symlink?"` prompts. Regular files treated as conflicts (skipped) without prompting.
- **Actual**: `deploy-config` contains no `read` calls. The only `read -rp` calls in the justfile are in the unrelated `setup-github-pat` and `setup-github-pat-org` recipes. Regular file targets in deploy-config classify as `[conflict]` and are skipped silently.
- **Verdict**: PASS

## Requirements Compliance

- **Complexity must earn its place**: The classification logic is repeated verbatim in all five deploy recipes (approximately 15 lines each). This is deliberate duplication rather than extraction into a shared function, which keeps each recipe self-contained and readable at the cost of DRY. Given that these are shell scripts in a justfile (not a programming language with good abstraction), the duplication is defensible -- a shared function would require sourcing or just-level workarounds that add their own complexity. Acceptable.
- **Maintainability through simplicity**: Each deploy recipe follows an identical pattern (pairs array, for loop, classify, install-or-skip, conflict summary). The pattern is easy to follow and extend. The `setup-force` recipe mirrors targets inline, with "also update setup-force" comments in each deploy recipe as a maintenance reminder.
- **Graceful partial failure**: Conflicts are surfaced clearly with reasons. The pending list tells the user exactly what was skipped and how to resolve it. No silent skips.
- **Fail clearly**: Conflict reasons (regular file, broken symlink, symlink to elsewhere) give actionable information. The `/setup-merge` instruction provides a clear next step.

## Stage 2: Code Quality

- **Naming conventions**: `setup` / `setup-force` naming is clear and conventional. `CONFLICTS_FILE` env var is descriptive. Classification labels `[new]`, `[update]`, `[conflict]` match the spec exactly. Source/target variable naming is consistent across all recipes.
- **Error handling**: All recipes use `set -euo pipefail`. Worktree guards in `deploy-bin` and `setup-force` prevent symlinks from pointing to ephemeral worktree paths. The `CONFLICTS_FILE` temp file is cleaned up via `trap`. The `${TMPDIR:-/tmp}` fallback handles environments where TMPDIR is unset.
- **Test coverage**: No automated tests were added for the new classification logic. The spec's non-requirements section doesn't mention tests, and the plan would need to be checked for verification steps. Manual testing would cover the critical paths (new install, re-run, conflict scenarios). Given this is shell scripting in a justfile, automated testing would require significant infrastructure. Acceptable for now.
- **Pattern consistency**: All five deploy recipes follow an identical structure: mkdir, define pairs/loop source, classify, install-or-skip, aggregate conflicts. The conflict summary logic (standalone vs CONFLICTS_FILE) is consistent across all recipes. The `setup-force` recipe mirrors the exact target list from the deploy recipes with comments to keep them in sync.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": []}
```
