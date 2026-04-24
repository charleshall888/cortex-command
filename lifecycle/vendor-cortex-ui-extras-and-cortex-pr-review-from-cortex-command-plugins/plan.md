# Plan: vendor-cortex-ui-extras-and-cortex-pr-review-from-cortex-command-plugins

## Overview

Vendor two plugins from `~/Workspaces/cortex-command-plugins/` into this repo's `plugins/` tree via `rsync -a`, then parameterize the existing dual-source drift machinery (`justfile` build recipe, `.githooks/pre-commit`, drift tests) with two top-level plugin-classification just-variables (`BUILD_OUTPUT_PLUGINS`, `HAND_MAINTAINED_PLUGINS`) plus two internal helper recipes that emit one-name-per-line. Build-output plugins are regenerated + drift-checked; hand-maintained plugins are left alone. The hook also fails closed on unclassified plugin directories, validates `plugin.json name` keys, and short-circuits `just build-plugin` when no top-level sources are staged.

## Tasks

### Task 1: Vendor `plugins/cortex-ui-extras/`

- **Files**:
  - `plugins/cortex-ui-extras/.claude-plugin/plugin.json` (new, enriched)
  - `plugins/cortex-ui-extras/skills/ui-a11y/SKILL.md` (new)
  - `plugins/cortex-ui-extras/skills/ui-brief/SKILL.md` (new)
  - `plugins/cortex-ui-extras/skills/ui-brief/references/design-md-template.md` (new)
  - `plugins/cortex-ui-extras/skills/ui-brief/references/theme-template.md` (new)
  - `plugins/cortex-ui-extras/skills/ui-check/SKILL.md` (new)
  - `plugins/cortex-ui-extras/skills/ui-judge/SKILL.md` (new)
  - `plugins/cortex-ui-extras/skills/ui-lint/SKILL.md` (new)
  - `plugins/cortex-ui-extras/skills/ui-setup/SKILL.md` (new)
- **What**: Copy the entire cortex-ui-extras plugin tree from the sibling repo via `rsync -a --exclude='.DS_Store' --exclude='.git*'`, then overwrite `.claude-plugin/plugin.json` with the enriched three-field shape plus the `"experimental": true` custom key.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Source: `~/Workspaces/cortex-command-plugins/plugins/cortex-ui-extras/` (8 files beneath `.claude-plugin/` and `skills/`, all 644 mode, no executables).
  - Target: `plugins/cortex-ui-extras/`.
  - `rsync -a` preserves mode bits (644 across all files here) and matches the existing `just build-plugin` idiom in `justfile:404-412`.
  - Enriched `plugin.json` body (overwrites the 33-byte name-only source file):
    ```json
    {
      "name": "cortex-ui-extras",
      "description": "Experimental UI design skills (brief, setup, lint, a11y, judge, check) for Claude Code interactive workflows",
      "author": "Charlie Hall <charliemhall@gmail.com>",
      "experimental": true
    }
    ```
  - Claude Code ignores unknown plugin.json keys (per research line 158), so `experimental` is a safe additive field.
- **Verification**: `rsync -rcn --delete --exclude='.DS_Store' --exclude='.git*' ~/Workspaces/cortex-command-plugins/plugins/cortex-ui-extras/ plugins/cortex-ui-extras/ 2>&1 | grep -vE "^(sending|sent |total |$|plugin\.json)" | wc -l` = 0 — pass if count = 0 (only plugin.json differs per the enrichment); AND `jq -e '.name == "cortex-ui-extras" and (.description | length > 0) and (.author | length > 0) and .experimental == true' plugins/cortex-ui-extras/.claude-plugin/plugin.json` — pass if exit 0.
- **Status**: [x] completed

### Task 2: Vendor `plugins/cortex-pr-review/` preserving executable mode

- **Files**:
  - `plugins/cortex-pr-review/.claude-plugin/plugin.json` (new, enriched)
  - `plugins/cortex-pr-review/skills/pr-review/SKILL.md` (new)
  - `plugins/cortex-pr-review/skills/pr-review/references/output-format.md` (new)
  - `plugins/cortex-pr-review/skills/pr-review/references/protocol.md` (new)
  - `plugins/cortex-pr-review/skills/pr-review/references/rubric.md` (new)
  - `plugins/cortex-pr-review/skills/pr-review/scripts/evidence-ground.sh` (new, **755 mode**)
- **What**: Copy the entire cortex-pr-review tree via `rsync -a --exclude='.DS_Store' --exclude='.git*'` to preserve the 755 mode bit on `evidence-ground.sh`, then overwrite `.claude-plugin/plugin.json` with the enriched three-field shape (no `experimental` key — cortex-pr-review is core, not experimental).
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Source: `~/Workspaces/cortex-command-plugins/plugins/cortex-pr-review/` (6 files; `evidence-ground.sh` is 755, everything else 644).
  - Definition of Done (per spec Non-Requirements): run `shellcheck -S error plugins/cortex-pr-review/skills/pr-review/scripts/evidence-ground.sh` once during implementation and manually read the script; not a standing CI gate.
  - Enriched `plugin.json` body:
    ```json
    {
      "name": "cortex-pr-review",
      "description": "Multi-agent GitHub pull request review pipeline for Claude Code",
      "author": "Charlie Hall <charliemhall@gmail.com>"
    }
    ```
- **Verification**: `rsync -rcn --delete --exclude='.DS_Store' --exclude='.git*' ~/Workspaces/cortex-command-plugins/plugins/cortex-pr-review/ plugins/cortex-pr-review/ 2>&1 | grep -vE "^(sending|sent |total |$|plugin\.json)" | wc -l` = 0 — pass if count = 0; AND `stat -f "%Lp" plugins/cortex-pr-review/skills/pr-review/scripts/evidence-ground.sh` — pass if output is exactly `755`; AND `jq -e '.name == "cortex-pr-review" and (.description | length > 0) and (.author | length > 0) and (.experimental // false) == false' plugins/cortex-pr-review/.claude-plugin/plugin.json` — pass if exit 0.
- **Status**: [x] completed

### Task 3: Declare plugin-policy arrays + list recipes in `justfile`

- **Files**: `justfile`
- **What**: Add two top-level just-variables declaring the plugin-classification policy and two internal helper recipes that emit one plugin name per line on stdout. Downstream consumers (Task 4's `build-plugin` and Task 5's `.githooks/pre-commit`) read the policy either via just interpolation (`{{BUILD_OUTPUT_PLUGINS}}` inside recipe bodies) or via the helper recipes' newline-separated stdout.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Insertion point: immediately before the existing `build-plugin:` recipe at `justfile:404`, under the `# --- Plugin ---` header at `justfile:401`.
  - **Format**: top-level just-variables using the `:=` assignment operator, not bash arrays. `just` does not support file-scoped bash arrays; the cross-recipe-shared classification must be a just-variable. Spec R4's wording "readonly plugin-policy arrays" is satisfied semantically (immutable file-scoped classification lists) via just-variables plus space-separated string values; the word "array" in the spec refers to the conceptual list, not a bash-array data structure. Pattern:
    ```
    BUILD_OUTPUT_PLUGINS := "cortex-interactive cortex-overnight-integration"
    HAND_MAINTAINED_PLUGINS := "cortex-pr-review cortex-ui-extras"
    ```
  - **Helper-recipe output contract (load-bearing)**: both `_list-*` recipes MUST emit exactly one plugin name per line on stdout. Task 5's `mapfile -t` consumer splits on newlines; any change to the separator (space-joined, comma-joined, etc.) silently breaks classification. Implementation: `echo '{{BUILD_OUTPUT_PLUGINS}}' | tr ' ' '\n'` (space → newline) inside each recipe body.
  - Recipe names prefixed with `_` (underscore) mark them as internal (not shown in primary `just --list`) per just convention; the plan does not introduce any other underscore-prefixed recipes today.
  - Both recipes use `#!/usr/bin/env bash` shebangs since the pre-commit hook and tests are bash-only (Technical Constraints, spec line 70).
  - `cortex-overnight-integration` is pre-registered per spec R4 and Follow-ups. See the "Pre-registration coupling" note in Task 4 Context and the Veto Surface section for the scope implications on ticket 121.
- **Verification**: `just _list-build-output-plugins | sort -u | tr '\n' ',' | sed 's/,$//'` output equals `cortex-interactive,cortex-overnight-integration` — pass if exact match; AND `just _list-hand-maintained-plugins | sort -u | tr '\n' ',' | sed 's/,$//'` output equals `cortex-pr-review,cortex-ui-extras` — pass if exact match.
- **Status**: [x] completed

### Task 4: Parameterize `just build-plugin` to iterate BUILD_OUTPUT_PLUGINS with directory guard

- **Files**: `justfile`
- **What**: Rewrite the `build-plugin` recipe body to iterate `{{BUILD_OUTPUT_PLUGINS}}`, wrap each iteration with an explicit `[[ -d plugins/$p/.claude-plugin ]] || { echo "build-plugin: skipping $p (not yet materialized)" >&2; continue; }` guard, and keep the existing rsync behavior (skills loop, `bin/cortex-*` glob, `hooks/cortex-validate-commit.sh`) for plugins whose directory exists.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**:
  - Existing recipe body (`justfile:404-412`):
    ```
    build-plugin:
        #!/usr/bin/env bash
        set -euo pipefail
        SKILLS=(commit pr lifecycle backlog requirements research discovery refine retro dev fresh diagnose evolve critical-review)
        for s in "${SKILLS[@]}"; do
            rsync -a --delete "skills/$s/" "plugins/cortex-interactive/skills/$s/"
        done
        rsync -a --delete --include='cortex-*' --exclude='*' bin/ plugins/cortex-interactive/bin/
        rsync -a hooks/cortex-validate-commit.sh plugins/cortex-interactive/hooks/cortex-validate-commit.sh
    ```
  - New shape: outer `for p in {{BUILD_OUTPUT_PLUGINS}}; do` wraps the existing body; inner body targets `plugins/$p/` instead of hardcoded `plugins/cortex-interactive/`. Directory-check guard skips to next iteration. **Critical**: use `{{BUILD_OUTPUT_PLUGINS}}` (just-variable interpolation), not `$BUILD_OUTPUT_PLUGINS` (bash expansion) — the latter is unset inside the recipe's bash environment and would yield a silently-empty loop that passes verification for the wrong reason.
  - `cortex-overnight-integration` is in BUILD_OUTPUT_PLUGINS but its directory won't exist until ticket 121 lands; the guard must emit the skip message to stderr and return exit 0 overall for the `just build-plugin` invocation.
  - **Pre-registration coupling (handoff contract to ticket 121)**: The SKILLS array stays hardcoded to cortex-interactive's skill list. This spec does NOT pre-factor SKILLS per plugin. The directory-existence guard protects ONLY the absent-directory case — the moment ticket 121 creates `plugins/cortex-overnight-integration/.claude-plugin/`, the guard stops firing and `just build-plugin` will rsync cortex-interactive's 15 skills into the new plugin tree, producing an incorrect build. Ticket 121's first materialization commit MUST atomically land one of: (i) per-plugin SKILLS mapping in `build-plugin`, (ii) reclassification of cortex-overnight-integration to `HAND_MAINTAINED_PLUGINS`, or (iii) a pre-flight opt-out inside the build-plugin loop. This obligation is a direct consequence of pre-registration; absent any of (i)/(ii)/(iii), ticket 121's first commit will fail its own pre-commit hook. See the Veto Surface for the pre-registration decision and its alternatives.
- **Verification**: `just build-plugin 2>&1 | grep -q "skipping cortex-overnight-integration"` — pass if exit 0; AND `[ ! -d plugins/cortex-overnight-integration ]` — pass if true (no ghost directory); AND `just build-plugin >/dev/null 2>&1 && git status --porcelain plugins/cortex-interactive/ plugins/cortex-pr-review/ plugins/cortex-ui-extras/ | wc -l` = 0 — pass if output is `0` (idempotent rebuild leaves no diff; hand-maintained plugins untouched).
- **Status**: [x] completed

### Task 5: Rewrite `.githooks/pre-commit` with policy-aware drift scope + fail-closed + name validation + short-circuit

- **Files**: `.githooks/pre-commit`
- **What**: Replace the hook's single-plugin logic with four policy-aware behaviors: (a) short-circuit `just build-plugin` when no top-level source paths are staged, (b) iterate `just _list-build-output-plugins` for per-plugin `git diff --quiet` drift checks, (c) fail-closed when any `plugins/*/.claude-plugin/plugin.json` is not classified in either policy array, (d) validate each `plugins/*/.claude-plugin/plugin.json` has a non-empty `name` via `jq -e`.
- **Depends on**: [3]
- **Complexity**: complex
- **Context**:
  - Replace `.githooks/pre-commit:14-37` entirely. Existing unconditional build+single-diff is insufficient; new shape has four phases.
  - **Phase 1 — Name validation and classification guard** (runs first, no dependency on build output):
    - Shell-glob `plugins/*/.claude-plugin/plugin.json`. For each match, read the enclosing plugin dir name. Run `jq -e '.name | length > 0' "$pj" >/dev/null 2>&1` — fail if exit non-zero, printing the plugin.json path and `name` keyword on stderr.
    - Load classification via `mapfile -t BO < <(just _list-build-output-plugins)` and `mapfile -t HM < <(just _list-hand-maintained-plugins)`. For each discovered plugin dir, check membership in either array; if in neither, print the plugin name and `"not classified (BUILD_OUTPUT_PLUGINS or HAND_MAINTAINED_PLUGINS)"` on stderr and exit 1.
    - Directories under `plugins/` without `.claude-plugin/plugin.json` are silently skipped (per spec R7 edge case).
  - **Phase 2 — Short-circuit decision** (narrowed from spec R9 prose — see "Short-circuit correctness" note below):
    - `staged=$(git diff --cached --name-only --diff-filter=ACMR)`.
    - Default `BUILD_NEEDED=0`.
    - Set `BUILD_NEEDED=1` if any staged path matches a top-level source path: `echo "$staged" | grep -qE '^(skills/|bin/cortex-|hooks/cortex-validate-commit\.sh$)'`.
    - Also set `BUILD_NEEDED=1` if any staged path matches a build-output plugin tree: `while read -r p; do echo "$staged" | grep -qE "^plugins/$p/" && { BUILD_NEEDED=1; break; }; done < <(just _list-build-output-plugins)`.
    - **Short-circuit correctness**: spec R9's prose says "short-circuits `just build-plugin` when no top-level source paths are staged" — as written, this leaks: a contributor who stages only a direct hand-edit to `plugins/cortex-interactive/skills/commit/SKILL.md` (no top-level source) would skip the build, and Phase 4's `git diff --quiet` (working-vs-index) would pass trivially because the working tree and index both contain the hand-edit. R6's acceptance ("hand-edit to plugins/cortex-interactive/... fails the commit") would silently regress. Phase 2 therefore expands the short-circuit trigger to also detect staged paths under any `BUILD_OUTPUT_PLUGINS` tree, closing the hole while preserving R9's intent (docs-only/backlog-only commits still skip the build). Spec R9 prose should be amended post-implementation to match; R9's acceptance test (backlog-only commit) still passes unchanged under the narrowed trigger.
  - **Phase 3 — Conditional build**: when `BUILD_NEEDED=1`, run `just build-plugin >/dev/null 2>&1` (preserve existing error-reporting path: fail fast, re-run with stderr visible on failure). When `BUILD_NEEDED=0`, skip the build entirely.
  - **Phase 4 — Drift loop**: for each `p` in `$BO`, run `git diff --quiet plugins/$p/` — if non-zero, accumulate drifted plugin name and `git diff --name-only plugins/$p/` lines; at end, if any drift found, print the consolidated message and exit 1. Note: this is working-tree-vs-index semantics, which is load-bearing — Phase 3's build rewrites the working tree from canonical sources, so a staged hand-edit in the index creates the working-vs-index delta that this diff detects. Phase 2's narrowing ensures Phase 3 always runs when the delta could be created.
  - Shebang stays `#!/bin/bash` (spec Technical Constraint, line 70). `set -euo pipefail` retained.
  - Exit 0 only after all four phases pass.
  - Consumers: the hook invokes `just _list-*` sub-recipes (justfile parsed twice per hook run — ~200ms overhead). Spec R9 short-circuit mitigates for non-source commits; further optimization is a follow-up per spec Edge Cases.
- **Verification**: `bash -n .githooks/pre-commit` — pass if exit 0 (syntax check); AND `git stash push -u >/dev/null 2>&1; .githooks/pre-commit >/dev/null 2>&1; rc=$?; git stash pop >/dev/null 2>&1 || true; [ "$rc" -eq 0 ]` — pass if true (hook exits 0 on a clean working tree with no staged changes, exercising phases 1/2/4 without seeding drift); AND full-scenario behavioral verification runs in Task 6 against seeded drift across subtests A-E.
- **Status**: [x] completed — with 2 flagged deviations: (1) `mapfile` replaced with `while IFS= read -r` loop because macOS `/bin/bash` is 3.2 and lacks `mapfile` (shebang `#!/bin/bash` is a hard spec constraint; bash 4+ not installed). (2) Phase 4 drift loop guards unmaterialized plugin directories (`cortex-overnight-integration` is pre-registered in BUILD_OUTPUT_PLUGINS but has no directory yet) via `[ ! -d "plugins/$p" ]` + `git ls-files --error-unmatch` skip; without this, `git diff --quiet plugins/cortex-overnight-integration/` errors and the clean-tree exit-0 verification is unreachable.

### Task 6: Extend `tests/test_drift_enforcement.sh` with subtests C, D, E and swap cleanup to `git stash push -u`

- **Files**: `tests/test_drift_enforcement.sh`
- **What**: Add four subtests (C: hand-maintained edit to `plugins/cortex-ui-extras/skills/ui-lint/SKILL.md`, D: hand-maintained edit to `plugins/cortex-pr-review/skills/pr-review/SKILL.md`, E: unclassified plugin dir creation via `plugins/cortex-unclassified/.claude-plugin/plugin.json`, F: direct hand-edit to build-output plugin tree at `plugins/cortex-interactive/skills/commit/SKILL.md` with no top-level source edit), update existing subtests A/B to stage their seeds before running the hook, and replace the unconditional `git restore` cleanup with `git stash push -u -- <paths>` + `git stash pop`, plus a `rm -rf plugins/cortex-unclassified/` secondary cleanup in the trap.
- **Depends on**: [1, 2, 5]
- **Complexity**: complex
- **Context**:
  - Existing test file structure (`tests/test_drift_enforcement.sh:1-112`): two subtests (A/B) with shared `restore_all()` in trap; each subtest seeds drift, runs hook, asserts exit + stderr content, then runs `git restore` + rebuild. Today's tests do NOT stage — they rely on the original hook always rebuilding. With R9's short-circuit in place, subtests must `git add` their seeded paths so Phase 2 sees staged state (otherwise `BUILD_NEEDED=0` regardless of seed, Phase 3 skips the build, and the drift loop passes trivially).
  - **Update subtest A**: after the `printf >> skills/commit/SKILL.md` seed, add `git add skills/commit/SKILL.md` before invoking the hook. Expected behavior: Phase 2 sets `BUILD_NEEDED=1` (top-level source staged); Phase 3 rebuilds; Phase 4 diff detects working-tree (rebuilt from edited top-level) ≠ index (old plugin tree) → exit 1. Cleanup must unstage: `git restore --staged skills/commit/SKILL.md` in addition to the existing `git checkout -- skills/commit/SKILL.md`.
  - **Update subtest B**: after the `printf >> hooks/cortex-validate-commit.sh` seed, add `git add hooks/cortex-validate-commit.sh` before invoking the hook. Same expected behavior as A. Same unstage in cleanup.
  - **Subtest C** (hand-maintained pass-through): seed an append-only no-op comment (`\n<!-- drift-test-marker -->\n`) in `plugins/cortex-ui-extras/skills/ui-lint/SKILL.md`, then `git add plugins/cortex-ui-extras/skills/ui-lint/SKILL.md`. Run hook. Expected: Phase 2 sees a path under HAND_MAINTAINED (not BUILD_OUTPUT), so `BUILD_NEEDED=0`; Phase 3 skips; Phase 4 iterates BUILD_OUTPUT only (no hand-maintained drift check), no drift found. Hook exit 0. Cleanup: unstage + checkout.
  - **Subtest D** mirrors C: seed + `git add plugins/cortex-pr-review/skills/pr-review/SKILL.md`. Assert exit 0. Cleanup: unstage + checkout.
  - **Subtest F** (direct hand-edit to build-output plugin — exercises the R9 narrowing fix): seed in `plugins/cortex-interactive/skills/commit/SKILL.md` (append no-op comment), then `git add plugins/cortex-interactive/skills/commit/SKILL.md`. Critically, do NOT stage the corresponding top-level source. Run hook. Expected: Phase 2's build-output-plugin-path check fires (`plugins/cortex-interactive/...` matches) → `BUILD_NEEDED=1`; Phase 3 rebuilds → working-tree `plugins/cortex-interactive/skills/commit/SKILL.md` is regenerated from the unchanged top-level source, differing from the staged hand-edit in the index; Phase 4 detects drift → exit 1. This subtest ONLY passes under the narrowed R9 — under spec R9's original prose (top-level-only filter), `BUILD_NEEDED=0`, Phase 3 skips, Phase 4 passes trivially, hook exits 0, and subtest F reports failure. Cleanup: `git restore --staged plugins/cortex-interactive/skills/commit/SKILL.md` + `git checkout -- plugins/cortex-interactive/skills/commit/SKILL.md` + `just build-plugin` (to reset any working-tree regeneration).
  - **Subtest E** (unclassified guard): create `plugins/cortex-unclassified/.claude-plugin/` and write `{"name":"cortex-unclassified"}` to its `plugin.json`, then `git add plugins/cortex-unclassified/.claude-plugin/plugin.json`. Run hook. Assert exit 1 AND `stderr | grep -qE "cortex-unclassified.*(not classified|unclassified|BUILD_OUTPUT_PLUGINS|HAND_MAINTAINED_PLUGINS)"`. **Staging is required**: the hook's Phase 1 fail-closed guard enumerates `plugins/*/.claude-plugin/plugin.json` globs and classifies against staged+committed state.
  - **Cleanup rewrite**: existing `restore_all()` runs unconditional `git restore` which can wipe uncommitted work. Swap to a scoped-stash + explicit-residue pattern:
    - **Top of script** (only existing tracked paths — `plugins/cortex-unclassified/` is NOT listed because it doesn't exist at script start; listing a nonexistent pathspec alongside dirty paths causes `git stash push -u` to exit 1 fatal and save no stash): `git stash push -u -- "$SKILL_SRC" "$HOOK_SRC" plugins/cortex-ui-extras/skills/ui-lint/SKILL.md plugins/cortex-pr-review/skills/pr-review/SKILL.md plugins/cortex-interactive/skills/commit/SKILL.md 2>/dev/null || true`. Purpose: capture any pre-existing dirty state on the tracked paths the subtests mutate (including subtest F's build-output plugin path).
    - **After each subtest**:
      - For subtests A, B, C, D, F (tracked files that were staged): `git restore --staged <seeded-path>` (unstage) THEN `git checkout -- <seeded-path>` (restore working tree) followed by `just build-plugin >/dev/null 2>&1 || true` (reset any working-tree regeneration).
      - For subtest E (staged-but-untracked-from-HEAD file): `git restore --staged plugins/cortex-unclassified/ 2>/dev/null || true` (unstage) THEN `rm -rf plugins/cortex-unclassified/` (remove working tree). `git checkout --` does not work on untracked-from-HEAD paths (errors "pathspec did not match"); `restore --staged` + `rm -rf` is the correct inverse.
    - **EXIT trap** (ordering is load-bearing — subtest E residue must be gone before `stash pop` runs, otherwise pop refuses and the pre-existing-state stash is abandoned):
      1. `rm -rf plugins/cortex-unclassified/ 2>/dev/null || true` (belt-and-braces for subtest E residue if it crashed mid-run)
      2. `git restore --staged plugins/cortex-unclassified/ 2>/dev/null || true` (belt-and-braces unstage)
      3. `git stash pop 2>/dev/null || true` (restore pre-existing dirty state)
  - Dependency on Task 1/2 (vendored hand-maintained plugins must exist) and Task 5 (hook must implement the fail-closed + hand-maintained-pass behaviors the tests assert, AND the narrowed R9 short-circuit that subtest F exercises).
  - Keep subtests A and B — they continue to pass against the parameterized hook because `cortex-interactive` stays in `BUILD_OUTPUT_PLUGINS` — but both now stage their top-level source edits before running the hook.
- **Verification**: `bash tests/test_drift_enforcement.sh 2>&1 | tee /tmp/drift.log; exit_code=${PIPESTATUS[0]}; [ "$exit_code" -eq 0 ] && grep -c "^\[PASS\]" /tmp/drift.log` — pass if the grep prints `6` or more (six distinct subtest passes A, B, C, D, E, F) AND the script exit code was 0.
- **Status**: [x] completed

### Task 7: Update `README.md` with four-plugin roster, core/extras framing, and experimental marker

- **Files**: `README.md`
- **What**: Rewrite the "Optional plugins" section (currently `README.md:92-106`) to reflect the in-repo four-plugin roster: `cortex-interactive`, `cortex-overnight-integration` (core), `cortex-ui-extras` (extras, marked experimental), `cortex-pr-review` (extras). Remove references to the companion repo's role for ui-extras/pr-review; leave the companion-repo mention for android-dev-extras intact.
- **Depends on**: [1, 2]
- **Complexity**: simple
- **Context**:
  - Current relevant block is `README.md:92-110` — three subsections ("Optional plugins", companion marketplace add + enabledPlugins snippet, "Limited / custom installation").
  - New structure must satisfy spec R11 acceptance in three ways simultaneously: (i) four distinct plugin names present via `grep -oE "cortex-(interactive|overnight-integration|ui-extras|pr-review)" README.md | sort -u | wc -l` = 4, (ii) experimental marker co-located with `cortex-ui-extras` via `grep -iE "experimental.*cortex-ui-extras|cortex-ui-extras.*experimental" README.md | wc -l` ≥ 1, (iii) core/extras framing via `grep -iE "core|extras|optional" README.md` producing matches within the plugin section.
  - Simplest satisfying shape: a short table with columns "Plugin | Tier | Notes" listing all four, with ui-extras's Notes cell containing "Experimental".
  - Keep the `claude /plugin install` syntax examples; update the marketplace URL reference only if the in-repo plugins now come from this repo's marketplace (ticket 122's scope — for now, the marketplace URL in the README still points to `cortex-command-plugins` because ticket 144 does not publish this repo's marketplace manifest). Per spec Non-Requirements, this ticket does not publish the marketplace; a prose note can say "in-repo plugins ship via this repo's marketplace once ticket 122 lands".
  - `cortex-overnight-integration` is not yet built (ticket 121) — list it as "shipping in ticket 121" or similar so the roster is accurate-forward, or omit it from the README table and mention it separately. Recommended: include in the table with a "shipping in 121" footnote, since the spec explicitly says README documents the "four shippable plugins" (R11 text).
- **Verification**: `grep -oE "cortex-(interactive|overnight-integration|ui-extras|pr-review)" README.md | sort -u | wc -l | tr -d ' '` = 4 — pass if output is `4`; AND `grep -iE "experimental.*cortex-ui-extras|cortex-ui-extras.*experimental" README.md | wc -l | tr -d ' '` ≥ 1 — pass if output is `1` or greater; AND `grep -iE "core|extras|optional" README.md | wc -l | tr -d ' '` ≥ 1 — pass if output is `1` or greater.
- **Status**: [x] completed

## Verification Strategy

End-to-end verification after all tasks complete:

1. **Structural**: `ls plugins/` shows `cortex-interactive`, `cortex-pr-review`, `cortex-ui-extras` (three directories); each has `.claude-plugin/plugin.json` passing its Task-1/2/existing `jq -e` check. `cortex-overnight-integration` does NOT exist as a directory.
2. **Build-output invariant**: `just build-plugin` exits 0, emits the "skipping cortex-overnight-integration" message, and leaves `git status --porcelain` empty (idempotent rebuild, no drift).
3. **Drift enforcement**: `bash tests/test_drift_enforcement.sh` exits 0 with five subtest passes (A-E).
4. **Hook short-circuit** (under the narrowed R9): a commit touching only `backlog/` or `docs/` runs the hook with `BUILD_NEEDED=0` (Phase 2's top-level filter AND build-output-plugin filter both miss) — `git diff --stat plugins/` before and after hook invocation is byte-identical. Additionally, subtest F proves that a staged direct hand-edit to a build-output plugin tree now fires `BUILD_NEEDED=1` and is caught by Phase 4.
5. **Fail-closed guard**: the subtest E verification in (3) exercises this path; additionally, manually staging a malformed `plugins/foo/.claude-plugin/plugin.json` during review can confirm the jq name-validation path.
6. **Documentation**: `grep -c "cortex-ui-extras\|cortex-pr-review" README.md` reports a sensible count and `grep -i experimental README.md` surfaces the ui-extras marker.

## Veto Surface

- **`cortex-overnight-integration` pre-registration in BUILD_OUTPUT_PLUGINS.** Spec resolves this in favor of pre-registration (R4). Task 4 now documents the handoff obligation to ticket 121: if 121 stays build-output, it must atomically land per-plugin SKILLS, HAND_MAINTAINED reclassification, or a pre-flight opt-out. If 121 reclassifies to hand-maintained, it's a two-line edit and no SKILLS refactor is needed. If the user prefers to leave 121 unregistered, Task 3's `BUILD_OUTPUT_PLUGINS` value shrinks to `"cortex-interactive"` and spec R4 acceptance updates.
- **Enriched `plugin.json` over name-only vendor.** The vendored plugins gain `description` + `author` fields not present in the sibling repo. If the user prefers a strict verbatim vendor (33-byte plugin.json files), Tasks 1/2's plugin.json overwrites disappear and R3's acceptance changes. Spec already fixed the proposed text (Technical Constraints, line 73-75); confirming once more.
- **Internal helper recipe naming.** `_list-build-output-plugins` uses the `_`-prefix convention. If the user prefers a different convention (e.g., `just-list-build-output-plugins` or a single `just plugin-policy <tier>` parameterized recipe), Task 3's recipe signatures and Task 5's hook calls change.
- **README framing choice.** Task 7 recommends a table but could also be a prose paragraph + sub-bullet list. The grep-based acceptance tests permit either; the choice affects reader ergonomics only.

## Scope Boundaries

Per spec Non-Requirements:

- **No marketplace manifest update** (ticket 122 owns `.claude-plugin/marketplace.json`).
- **No android-dev-extras vendoring** — stays in `cortex-command-plugins`.
- **No `cortex-command-plugins` retirement** — it keeps android-dev-extras.
- **No `cortex-overnight-integration` plugin directory creation** (ticket 121). The name is pre-registered in `BUILD_OUTPUT_PLUGINS` but no files are created under `plugins/cortex-overnight-integration/`.
- **No user migration guide** (ticket 124).
- **No git history preservation** of vendored plugins (no `git subtree add`). Raw copy; `git log --follow` terminates at the vendor commit.
- **No SKILL.md rewrite** of `evidence-ground.sh` invocation to `bash scripts/...` prefix. Vendor as-is, preserving 755 mode; file follow-up if a future install path drops modes.
- **No shellcheck CI step.** One-shot shellcheck of `evidence-ground.sh` at vendor time is implementation hygiene in Task 2's DoD, not a standing gate.
- **No external-repo deletion commit** in this ticket's diff. Follow-up in `cortex-command-plugins` once this lands and ticket 122's manifest references the in-repo copies.
