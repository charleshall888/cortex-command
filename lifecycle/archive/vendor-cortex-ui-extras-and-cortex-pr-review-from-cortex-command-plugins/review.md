# Review: vendor-cortex-ui-extras-and-cortex-pr-review-from-cortex-command-plugins

## Stage 1: Spec Compliance

### R1: `plugins/cortex-ui-extras/` vendored verbatim, all six ui-* skills present
- **Expected**: rsync dry-run diff count (excluding plugin.json/README.md enrichment) = 0; all six `ui-{a11y,brief,check,judge,lint,setup}/SKILL.md` present.
- **Actual**: rsync diff count = 0 (verified against `~/Workspaces/cortex-command-plugins/plugins/cortex-ui-extras/`). All six SKILL.md files present. Supporting references (`design-md-template.md`, `theme-template.md`) also vendored under `ui-brief/references/`.
- **Verdict**: PASS
- **Notes**: Plugin contents byte-identical to external repo, modulo enriched plugin.json per R3.

### R2: `plugins/cortex-pr-review/` vendored; `evidence-ground.sh` preserves mode 755
- **Expected**: SKILL.md and scripts/evidence-ground.sh present; `stat -f "%Lp"` outputs exactly `755`.
- **Actual**: Both files present. `stat -f "%Lp" plugins/cortex-pr-review/skills/pr-review/scripts/evidence-ground.sh` outputs `755`.
- **Verdict**: PASS
- **Notes**: rsync diff count against external repo = 0 for pr-review tree as well.

### R3: Both plugin.json files carry required fields; ui-extras carries `experimental: true`
- **Expected**: `jq -e` exits 0 on both shape checks.
- **Actual**:
  - `cortex-ui-extras/.claude-plugin/plugin.json`: name=cortex-ui-extras, description non-empty, author non-empty, experimental=true. jq check passes.
  - `cortex-pr-review/.claude-plugin/plugin.json`: name=cortex-pr-review, description non-empty, author non-empty, no experimental key (defaults to false). jq check passes.
- **Verdict**: PASS
- **Notes**: Description/author text matches the spec's Technical Constraints proposed text exactly.

### R4: justfile declares policy arrays + helper recipes emitting one name per line
- **Expected**: `just _list-build-output-plugins | sort -u` = `cortex-interactive\ncortex-overnight-integration`; `just _list-hand-maintained-plugins | sort -u` = `cortex-pr-review\ncortex-ui-extras`.
- **Actual**: Both commands produce exactly the expected output. Implementation uses two `just` variables (`BUILD_OUTPUT_PLUGINS`, `HAND_MAINTAINED_PLUGINS`) with helper recipes that `echo ... | tr ' ' '\n'`. Variables declared near the other plugin recipes (around line 403).
- **Verdict**: PASS

### R5: `just build-plugin` iterates build-output plugins, explicitly skips absent dirs
- **Expected**: Recipe guards each iteration with directory check; after invocation, no ghost `plugins/cortex-overnight-integration/` dir; stderr contains "skipping cortex-overnight-integration"; exit 0; vendored plugin dirs untouched.
- **Actual**: `just build-plugin` output: `build-plugin: skipping cortex-overnight-integration (not yet materialized)`. Exit 0. `plugins/cortex-overnight-integration/` does not exist. `git status --porcelain plugins/cortex-ui-extras/ plugins/cortex-pr-review/` is empty.
- **Verdict**: PASS
- **Notes**: Guard implemented as `[[ -d plugins/$p/.claude-plugin ]] || { echo "build-plugin: skipping $p (not yet materialized)" >&2; continue; }` — matches spec's suggested form.

### R6: pre-commit fails on build-output drift; passes on hand-maintained edits
- **Expected**: Staged edit to `plugins/cortex-interactive/skills/commit/SKILL.md` → exit 1, stderr mentions path. Staged edit to `plugins/cortex-ui-extras/skills/ui-lint/SKILL.md` → exit 0.
- **Actual**: Covered by test suite subtests C (ui-lint pass-through exits 0), D (pr-review pass-through exits 0), F (direct hand-edit to cortex-interactive/skills/commit/SKILL.md exits 1 with stderr mentioning the path), A (top-level skills drift propagated to plugin exits 1 with plugin path in stderr). All six subtests pass. Hook code (lines 101–114) iterates `BO` array and runs `git diff --quiet -- "plugins/$p/"` per entry.
- **Verdict**: PASS
- **Notes**: Verified via `bash tests/test_drift_enforcement.sh`; exit 0 with 6/6 passes.

### R7: pre-commit fails-closed on unclassified plugin directories
- **Expected**: New `plugins/cortex-unclassified/.claude-plugin/plugin.json` staged → exit 1, stderr matches classification regex.
- **Actual**: Covered by subtest E in the test suite — hook exits 1 and stderr matches `cortex-unclassified.*(not classified|unclassified|BUILD_OUTPUT_PLUGINS|HAND_MAINTAINED_PLUGINS)`. Actual stderr message: `pre-commit: plugin 'cortex-unclassified' not classified (BUILD_OUTPUT_PLUGINS or HAND_MAINTAINED_PLUGINS).`
- **Verdict**: PASS
- **Notes**: Hook Phase 1 enumerates `plugins/*/.claude-plugin/plugin.json` via glob (shopt -s nullglob) and requires each plugin dir to appear in BO or HM array; otherwise exits 1.

### R8: pre-commit validates non-empty `name` key on every plugin.json
- **Expected**: Staged blanked `name` in `plugins/cortex-ui-extras/.claude-plugin/plugin.json` → exit 1, stderr mentions plugin.json path and "name".
- **Actual**: Manually seeded `.name = ""` via jq, staged, ran hook. Exit 1; stderr: `pre-commit: plugins/cortex-ui-extras/.claude-plugin/plugin.json missing non-empty 'name' field.` Both "plugins/cortex-ui-extras/.claude-plugin/plugin.json" and "name" appear in stderr. Working tree restored via `git restore --staged` + file-copy backup.
- **Verdict**: PASS
- **Notes**: Hook Phase 1 runs `jq -e '.name | length > 0'` per plugin.json. Validation fires regardless of classification (correct per spec).

### R9: pre-commit short-circuits `just build-plugin` for non-source commits
- **Expected**: With only a backlog file staged, capture `git diff --stat plugins/cortex-interactive/` before/after hook; both byte-identical; hook exits 0.
- **Actual**: Staged `backlog/index.json` only, captured before/after diff-stat of `plugins/cortex-interactive/` — outputs byte-identical. Hook exit 0. Restored staging area.
- **Verdict**: PASS
- **Notes**: Hook Phase 2 (lines 68–83) inspects `git diff --cached --name-only --diff-filter=ACMR` and sets BUILD_NEEDED=1 only if matching `^(skills/|bin/cortex-|hooks/cortex-validate-commit\.sh$)` or any staged path is under a build-output plugin tree. Phase 4 drift loop runs regardless, but with no staged changes under any build-output plugin it's a no-op.

### R10: `tests/test_drift_enforcement.sh` gains subtests C/D/E; A/B/F still pass
- **Expected**: Test script exits 0 with at least 5 distinct subtests; stash-based cleanup, not unconditional `git restore`.
- **Actual**: Six subtests (A/B/C/D/E/F) all pass. Test output:
  ```
  Drift enforcement tests: 6/6 passed
  ```
  Cleanup uses `git stash push -u -- <tracked paths>` upfront (guarding pre-existing dirty state on the specific tracked paths the subtests mutate) + `git stash pop` in EXIT trap + `rm -rf plugins/cortex-unclassified/` for subtest E's untracked file. Per-subtest restoration uses `git restore --staged` + `git checkout --` for tracked files; subtest E additionally `rm -rf`s the unclassified dir.
- **Verdict**: PASS
- **Notes**: Test exceeds spec (F adds direct build-output-plugin hand-edit coverage beyond the required A/B/C/D/E). Cleanup mechanism matches spec (`git stash push -u` + secondary `rm -rf` trap).

### R11: README documents four plugins with core/extras framing + experimental marker
- **Expected**: grep returns 4 distinct plugin names; ≥1 line co-locates "experimental" with "cortex-ui-extras"; README contains core/extras/optional language in plugin section.
- **Actual**:
  - `grep -oE "cortex-(interactive|overnight-integration|ui-extras|pr-review)" README.md | sort -u | wc -l` = 4
  - `grep -iE "experimental.*cortex-ui-extras|cortex-ui-extras.*experimental" README.md` → `| cortex-ui-extras | extras | Experimental — UI design skills |`
  - Plugin roster table at lines 92–101 explicitly splits plugins into `core` and `extras` tiers. "core and extras tiers" introductory sentence is present.
- **Verdict**: PASS
- **Notes**: `### Plugin roster` subsection heading (line 92) plus a markdown table with Tier column. `### Limited / custom installation` subsection follows as encouraged.

## Requirements Drift

**State**: none
**Findings**:
- None. `requirements/project.md` describes the cortex-command system at a philosophical/architectural level and does not speak to per-plugin vendoring details. This ticket's concerns (plugin classification, drift enforcement, vendoring mechanics) are lifecycle-internal and do not require updates to project requirements.
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: Consistent. Array names (`BUILD_OUTPUT_PLUGINS`, `HAND_MAINTAINED_PLUGINS`) are descriptive and match spec wording. Helper recipes use the `_list-*` underscore prefix idiom already used elsewhere in the justfile for private/helper recipes. Hook phase comments delineate four phases clearly.
- **Error handling**: Appropriate. `set -euo pipefail` in both the hook and the test script. Phase 1 fails closed on missing-name and unclassified-plugin. Phase 3 rebuilds silently and surfaces stderr on failure by re-running `just build-plugin >&2` before exiting. Phase 4 accumulates drift output into a single report buffer rather than exiting on the first drift — better UX. The `git ls-files --error-unmatch` + disk check double-guard in Phase 4 is defensive but correct: silently skips plugins that are both absent on disk AND absent from the index (true no-op case).
- **Test coverage**: Strong. Six drift-enforcement subtests covering build-output drift (A, B, F), hand-maintained pass-through (C, D), and unclassified-plugin fail-closed (E). Subtest F is above-and-beyond — tests direct hand-edit of a build-output plugin tree, which is the specific attack surface Phase 4's drift loop defends against even when Phase 3 successfully rebuilds. Stash-based cleanup correctly scopes to tracked pathspecs that the subtests mutate, avoiding the `git stash push -u` "no local changes" trap. EXIT trap ordering is load-bearing and documented in-line.
- **Pattern consistency**: Follows existing project conventions. `#!/bin/bash` shebang matches other hooks. `just` variables near the Plugin section. `README.md` table format for the plugin roster mirrors other tables in the README. Uses `jq -e` for JSON validation (the project's established pattern; see other recipes in justfile).
- **Task 5 deviations assessment**:
  1. **`mapfile` → `while IFS= read -r` loop**: Appropriate engineering call, not a spec violation. The spec's Technical Constraints fix `#!/bin/bash` as a hard constraint. macOS ships `/bin/bash` = 3.2.57, which lacks `mapfile` (verified: `mapfile: command not found`). The spec's literal body text suggesting `mapfile -t BO < <(just _list-build-output-plugins)` was incompatible with its own shebang constraint. The read-loop substitution is semantically equivalent (reads each non-empty line into the array), preserves the binding shebang, and is the standard bash-3.2-compatible idiom. The inline comment at lines 27–29 documents the rationale. This is the right call.
  2. **Phase 4 guard for unmaterialized plugin directories**: Appropriate and consistent with spec philosophy, not a violation. `BUILD_OUTPUT_PLUGINS` pre-registers `cortex-overnight-integration` per R4/R5 (ticket 121 owns materialization). Without the guard, a bare `git diff --quiet -- "plugins/cortex-overnight-integration/"` returns 0 silently (verified), but the guard makes the "skip absent plugin dir" behavior explicit, matching the R5 philosophy ("absent directories are skipped explicitly, not inferred"). The guard's double-check (disk OR index) correctly distinguishes "not yet materialized" (skip) from "all files deleted" (still check drift via index). R6's behavior is fully preserved for every materialized build-output plugin.

Both deviations are transparently documented in `events.log` and in in-line comments. Neither represents a spec violation; both are the correct response to a spec instruction whose literal form conflicted with a separate spec-level constraint.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
