---
feature: delete-post-shift-orphan-code-scripts-hooks-and-retire-paired-requirements
phase: plan
tier: complex
criticality: medium
created: 2026-05-05
parent_backlog: 168-delete-post-shift-orphan-code-scripts-hooks-and-retire-paired-requirements
parent_epic: 165-repo-spring-cleaning-share-readiness-epic
---

# Plan: delete-post-shift-orphan-code-scripts-hooks-and-retire-paired-requirements

## Overview

Land the four-category cleanup (R14) as exactly four per-category commits on a feature branch off `main`, with paired-deletion atomicity preserved within each commit (R7's eight invariants), round-3 NOT_FOUND re-verification recorded in each delete commit's body (R16), and `just test` + `bash tests/test_hooks.sh` both green at every commit boundary (R15). The pre-commit parity gate (`bin/cortex-check-parity`) runs unaided per commit; the dual-source mirror at `plugins/cortex-core/bin/cortex-validate-spec` is staged in commit 3.

## Round-3 Grep Template (refined per critical review)

Tasks 2, 3, 4 each invoke this refined template instead of inheriting spec R16's literal form. The refinement extends spec R16's exclusions to make the gate runnable against a working tree containing same-commit paired-deletion partners (per critical review O1) and out-of-scope sibling-ticket references (per critical review O2):

```bash
# Per-commit substitutions (set by the calling task)
PATHS_TO_VERIFY="<basenames being deleted in this commit — anchor of the grep>"
COMMIT_DELETE_SET="<paths being deleted in this commit, space-separated>"
COMMIT_EDIT_SET="<paths being modified-not-deleted in this commit, space-separated>"

fail=0
for p in $PATHS_TO_VERIFY; do
  matches=$(grep -rl --include='*.py' --include='*.sh' --include='*.md' --include='*.json' --include='*.toml' --include='*.conf' --include='justfile' --include='.gitignore' \
       --exclude-dir=lifecycle --exclude-dir=research --exclude-dir=retros --exclude-dir=backlog --exclude-dir=.git --exclude-dir=node_modules \
       -F "$(basename "$p")" . 2>/dev/null | grep -v "^\./$p$" || true)
  for m in $matches; do
    rel="${m#./}"
    skip=0
    for d in $COMMIT_DELETE_SET; do [ "$rel" = "$d" ] && skip=1 && break; done
    [ $skip -eq 1 ] && continue
    for e in $COMMIT_EDIT_SET; do [ "$rel" = "$e" ] && skip=1 && break; done
    [ $skip -eq 1 ] && continue
    echo "FAIL: $p has surviving consumer at $rel beyond historical surfaces"
    fail=1
  done
done
[ $fail -eq 0 ] && echo "PASS-COMMIT-N" || exit 1
```

Differences from spec R16's literal template (each justified):

- **Adds `--exclude-dir=backlog`**: backlog items describe past/future work narratively (epic #165, ticket #168 itself enumerate the deleted paths in their bodies); they are not active code/config consumers. Without this exclusion, every round-3 grep returns 5–10 backlog matches, drowning the actual signal.
- **Adds `--include='*.conf'` and `--include='.gitignore'`**: spec R16's include list omitted extensionless and `.conf` files, leaving real consumers (`output-filters.conf`, `sync-allowlist.conf`, `.gitignore`) invisible to the grep. The wider include surface improves drift detection.
- **Adds same-commit `COMMIT_DELETE_SET` and `COMMIT_EDIT_SET` exclusions**: R7's atomicity invariants require the canonical script and its consumer test/fixture/docs paths to land in the same SHA. At pre-stage grep time, the consumer files still exist in tree; without these exclusions, every paired-deletion invariant trips its own round-3 gate (e.g., `cortex-sync-permissions` matches `tests/test_hooks.sh` which is being edited in the same commit). The exclusions are precisely scoped — only paths in the current commit's delete-or-edit set are skipped — so cross-commit drift remains visible.

The trailer text is unchanged: `Round-3-reverified: PASS-COMMIT-N`. The implementer pastes the literal `PASS-COMMIT-N` line emitted by the refined template into the commit body trailer.

## Tasks

### Task 1: Pre-commit lifecycle 168 artifacts to main, then create feature branch
- **Files**: (committed on `main` before branching, NOT on the feature branch)
  - `lifecycle/delete-post-shift-orphan-code-scripts-hooks-and-retire-paired-requirements/research.md`
  - `lifecycle/delete-post-shift-orphan-code-scripts-hooks-and-retire-paired-requirements/spec.md`
  - `lifecycle/delete-post-shift-orphan-code-scripts-hooks-and-retire-paired-requirements/plan.md`
  - `lifecycle/delete-post-shift-orphan-code-scripts-hooks-and-retire-paired-requirements/events.log`
  - `lifecycle/delete-post-shift-orphan-code-scripts-hooks-and-retire-paired-requirements/index.md`
  - `lifecycle/delete-post-shift-orphan-code-scripts-hooks-and-retire-paired-requirements/critical-review-residue.json`
  - `backlog/168-delete-post-shift-orphan-code-scripts-hooks-and-retire-paired-requirements.md` (frontmatter changes from this lifecycle's start: `status`, `lifecycle_phase`, `lifecycle_slug`, `session_id`, `complexity`, `criticality`, `spec` fields)
  - `backlog/168-delete-post-shift-orphan-code-scripts-hooks-and-retire-paired-requirements.events.jsonl` (lifecycle event log entries)
- **What**: Commit lifecycle 168's 6 artifact files plus the matching `backlog/168-*.md` frontmatter and `backlog/168-*.events.jsonl` changes onto `main` via `/cortex-core:commit` BEFORE branching. After this commit lands on main, branch off main; the lifecycle artifacts are then inherited via merge-base on the feature branch (NOT "riding on" the branch). The feature branch's `merge-base..HEAD` range is empty post-Task-1 — Task 2's commit becomes the FIRST commit on the branch and counts as commit 1 of R14's mandated four. R14's `git log --oneline $(git merge-base HEAD main)..HEAD | wc -l = 4` then holds because lifecycle artifacts are merge-base-side, not in the branch's diff.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Working tree at planning time contains 10 modified/untracked items per `git status --short`: this lifecycle's 6 artifact files + `backlog/168-*.md` (frontmatter) + `backlog/168-*.events.jsonl` are THIS lifecycle's pre-commit set. The remaining items (`backlog/064-*.md`, `backlog/166-*.md`, `backlog/169-*.md`, `backlog/index.json`, `backlog/index.md`, `lifecycle/fix-archive-predicate-and-sweep-lifecycle-and-research-dirs/`, `lifecycle/rewrite-readme-migrate-content-to-docs-setupmd-reorganize-docs-and-fix-stale-paths/`, `research/vertical-planning/`) are NOT this lifecycle's responsibility — they belong to sibling tickets (#064 separate work; #166 README rewrite; #169 lifecycle archive; vertical-planning is separate research). Use scope-bounded `git add <explicit-paths>` (NEVER `git add .` and NEVER `git add -A`) to commit ONLY the 8 paths listed under Files. Sibling-ticket files remain as working-tree state on `main` and on the new feature branch — this is fine; subsequent task commits also use scope-bounded `git add` so sibling state never travels onto category commits. The aggregate files `backlog/index.json` and `backlog/index.md` are intentionally NOT in this task's commit set — those reflect aggregate state across multiple in-flight tickets and should be regenerated via `just backlog-index` and committed in a coordinated cross-lifecycle step (not this lifecycle's domain). After the lifecycle-scaffold commit lands on `main`, create the feature branch via `git checkout -b cleanup-orphan-code-and-retire-paired-requirements` (≤63 char, kebab-case). The pre-commit hook runs on the lifecycle-scaffold commit; the hook's parity check skips since no `bin/cortex-*` paths are touched, and the dual-source drift loop (Phase 4) is a no-op since canonical bin/hooks/skills are unchanged. Branch creation does not trigger the hook.
- **Verification**:
  ```
  [ "$(git rev-parse --abbrev-ref HEAD)" = "cleanup-orphan-code-and-retire-paired-requirements" ] && \
  [ "$(git rev-list --count main..HEAD)" -eq 0 ] && \
  test -e lifecycle/delete-post-shift-orphan-code-scripts-hooks-and-retire-paired-requirements/plan.md && \
  test -e lifecycle/delete-post-shift-orphan-code-scripts-hooks-and-retire-paired-requirements/critical-review-residue.json && \
  git log --format=%s -1 main | grep -qE '(lifecycle|scaffold|critical|168)' && \
  echo PASS
  ```
  Pass if stdout includes `PASS` (branch is checked out, zero commits delta to main, lifecycle artifacts present in merge-base via main's tip, and main's tip commit subject mentions this lifecycle).
- **Status**: [ ] pending

### Task 2: Commit 1 — Confirmed deletes (R1, R2, R3, R7-inv-2/3/8, R14-c1, R15, R16)
- **Files**:
  - `plugins/cortex-overnight-integration/` (delete entire directory tree)
  - `scripts/sweep-skill-namespace.py` (delete)
  - `scripts/verify-skill-namespace.py` (delete)
  - `scripts/verify-skill-namespace.carve-outs.txt` (delete)
  - `scripts/generate-registry.py` (delete)
  - `scripts/migrate-namespace.py` (delete)
  - `tests/test_migrate_namespace.py` (delete)
  - `tests/fixtures/migrate_namespace/` (delete entire directory tree, 8 files)
  - `.gitignore` (edit: remove the `# Auto-generated skill registry` comment + the `skills/registry.json` line; surrounding context per research §"Files to delete" lines 19–21)
- **What**: Land the confirmed-orphan completed-migration scripts, the rename-leftover plugin directory, and the paired test+fixtures+`.gitignore` line in one atomic commit. Round-3 (refined template) re-verifies each path has zero active consumers immediately before the commit; the `Round-3-reverified: PASS-COMMIT-1` trailer captures the result.
- **Depends on**: [1]
- **Complexity**: complex
- **Context**: Round-3 invocation for this commit:
  - `PATHS_TO_VERIFY="plugins/cortex-overnight-integration scripts/sweep-skill-namespace.py scripts/verify-skill-namespace.py scripts/verify-skill-namespace.carve-outs.txt scripts/generate-registry.py scripts/migrate-namespace.py tests/test_migrate_namespace.py tests/fixtures/migrate_namespace"`
  - `COMMIT_DELETE_SET="plugins/cortex-overnight-integration scripts/sweep-skill-namespace.py scripts/verify-skill-namespace.py scripts/verify-skill-namespace.carve-outs.txt scripts/generate-registry.py scripts/migrate-namespace.py tests/test_migrate_namespace.py tests/fixtures/migrate_namespace"`
  - `COMMIT_EDIT_SET=".gitignore"`
  Run from repo root before staging; expected output `PASS-COMMIT-1`. Commit message subject ≤72 chars, imperative, capitalized, no trailing period (CLAUDE.md). Commit body MUST include the literal `Round-3-reverified: PASS-COMMIT-1` trailer per R16 (paste the line emitted by the refined template). Use `/cortex-core:commit` to author the commit. Pre-commit hook will run `bin/cortex-check-parity` (commit must pass without `--no-verify`). The dual-source mirrors at `plugins/cortex-core/{skills,hooks,bin}/` and `plugins/cortex-overnight/hooks/` are unaffected by this commit's paths — the `build-plugin` recipe at `justfile:472–504` enumerates HOOKS arrays per plugin (cortex-core: `cortex-validate-commit.sh`, `cortex-worktree-create.sh`, `cortex-worktree-remove.sh` at `justfile:481`; cortex-overnight: `cortex-cleanup-session.sh`, `cortex-scan-lifecycle.sh`, `cortex-tool-failure-tracker.sh`, `cortex-permission-audit-log.sh` at `justfile:487`); none of this commit's 9 paths appear in any HOOKS or BIN array, so `just build-plugin` (run by pre-commit Phase 2) produces no working-tree drift. R7 invariants 2, 3, 8 are satisfied as natural consequences of this category boundary (script ↔ paired test/fixtures, generate-registry ↔ `.gitignore`, sweep+verify pair). After the commit lands, R15 boundary check runs `just test` and `bash tests/test_hooks.sh`.
- **Verification**: After commit, run:
  ```
  R3=$(git log --format=%B -1 | grep -c 'Round-3-reverified: PASS-COMMIT-1'); \
  for p in plugins/cortex-overnight-integration scripts/sweep-skill-namespace.py scripts/verify-skill-namespace.py scripts/verify-skill-namespace.carve-outs.txt scripts/generate-registry.py scripts/migrate-namespace.py tests/test_migrate_namespace.py tests/fixtures/migrate_namespace; do [ -e "$p" ] && { echo "FAIL:$p"; exit 1; }; done; \
  GI=$(grep -cE '^skills/registry\.json$' .gitignore); \
  just test >/dev/null 2>&1; T1=$?; \
  bash tests/test_hooks.sh >/dev/null 2>&1; T2=$?; \
  [ $R3 -eq 1 ] && [ $GI -eq 0 ] && [ $T1 -eq 0 ] && [ $T2 -eq 0 ] && echo PASS-COMMIT-1
  ```
  Pass if stdout includes `PASS-COMMIT-1`.
- **Status**: [ ] pending

### Task 3: Commit 2 — DR-4 hooks + paired tests + paired requirements + CHANGELOG (R4, R5, R6, R7-inv-4/5/6/7, R11, R14-c2, R15, R16)
- **Files**:
  - `claude/hooks/cortex-output-filter.sh` (delete)
  - `claude/hooks/output-filters.conf` (delete)
  - `claude/hooks/cortex-sync-permissions.py` (delete)
  - `claude/hooks/bell.ps1` (delete)
  - `tests/test_output_filter.sh` (delete)
  - `tests/test_hooks.sh` (edit: remove the `cortex-sync-permissions.py tests` block bracketed by the `---` header at L307 and the next `---` header at L383, inclusive of the block contents but exclusive of the next section's `---` opener; per planning-time grep, the block runs L307–382 — read both boundary headers before deleting to avoid removing the `Summary` section at L383)
  - `tests/fixtures/hooks/sync-permissions/` (delete entire directory, 2 fixture JSON files)
  - `requirements/project.md` (edit: cut the entire L36 `Context efficiency` bullet — D2 = option (b), per spec R6; verify subsequent line numbers shift cleanly and no other doc anchors `requirements/project.md:N` for N>36 break — per spec edge case `requirements/project.md` line-number shift after L36 cut, the only known cross-reference is `requirements/pipeline.md:130` which is out of scope for this ticket)
  - `docs/agentic-layer.md` (edit: remove the L216 `bell.ps1` table row only — paired consistency edit, the only docs touch in this ticket per spec Non-Requirements; L209 `cortex-sync-permissions.py` row, L212 `cortex-output-filter.sh` row, L255 output-filter prose, and L264 sync-permissions prose are out of scope per spec Non-Requirements ("No `docs/agentic-layer.md` skill-table cleanup") and remain as known surviving descriptive references owned by sibling ticket #166)
  - `CHANGELOG.md` (edit: add `### Removed` subsection under `## [Unreleased]` per Keep-a-Changelog convention — see Context for the required prose tokens)
- **What**: Land the DR-4 atomic retirement (hooks + `requirements/project.md:36`) plus paired tests and the precautionary CHANGELOG advisory in a single commit so all four R7 invariants (4, 5, 6, 7) close in one SHA. Round-3 (refined template) re-verifies the four hook paths plus the paired test and fixture paths immediately before the commit; trailer captures `PASS-COMMIT-2`.
- **Depends on**: [2]
- **Complexity**: complex
- **Context**: CHANGELOG `[Unreleased]` `### Removed` entry MUST contain ALL FOUR deleted hook script names (`cortex-output-filter`, `output-filters.conf`, `cortex-sync-permissions`, `bell.ps1`) AND the literal token `~/.claude/settings.json` AND at least one maintainer-action verb from `{grep, remove, unbind}` AND must NOT contain the tokens `MUST` (capitalized), `CRITICAL`, or `session-breaking` (R11 negative-match — Web research established missing-hook behavior is warn-and-continue, so framing is precautionary not migration-critical). Recommended exact prose template per research §Tradeoffs Decision 5: "Removed: \`claude/hooks/cortex-output-filter.sh\`, \`claude/hooks/output-filters.conf\`, \`claude/hooks/cortex-sync-permissions.py\`, \`claude/hooks/bell.ps1\`. Maintainers who installed these via the retired \`cortex setup\` flow should grep \`~/.claude/settings.json\` for these script names and remove the bindings; cortex no longer deploys them." If the `## [Unreleased]` header is absent at commit-prep time, add it per Keep-a-Changelog convention before adding the `### Removed` subsection (per spec edge case "CHANGELOG `[Unreleased]` section absence"). For the `tests/test_hooks.sh` block edit, identify the boundary headers via `grep -n '^# -\{30,\}' tests/test_hooks.sh` — at planning time these are L307 (block opener) and L383 (Summary opener); delete L307–382 inclusive (header + 4 test cases + final `fi`) as a SINGLE Edit operation (one `old_string` matching the entire block, one `new_string` empty) to avoid line-number drift mid-edit. Pre-deletion sanity check: `grep -nE 'SYNC_HOOK|SYNC_FIXTURE_DIR|SYNC_TMPDIR' tests/test_hooks.sh` — all matches must fall within L307–382 (helper variables are scoped to the deleted block; if any match outside, the deletion would orphan a reference and break R15). For `requirements/project.md` line 36, cut the entire bullet (D2 = option b — Context efficiency QA dropped without replacement; future preprocessing-hook work must reintroduce the QA per spec Non-Requirements). For `docs/agentic-layer.md` line 216, remove the single table row containing `bell.ps1`; do NOT touch other rows. Mirror coverage: per `justfile:472–504`'s `build-plugin` recipe, the HOOKS arrays at `justfile:481` (cortex-core: `cortex-validate-commit.sh`, `cortex-worktree-create.sh`, `cortex-worktree-remove.sh`) and `justfile:487` (cortex-overnight: `cortex-cleanup-session.sh`, `cortex-scan-lifecycle.sh`, `cortex-tool-failure-tracker.sh`, `cortex-permission-audit-log.sh`) do NOT include any of the four DR-4 hooks; therefore neither `plugins/cortex-core/hooks/` nor `plugins/cortex-overnight/hooks/` mirrors any DR-4 hook, and `just build-plugin` (run by pre-commit Phase 2 due to commit `54d5edb`'s broadened `claude/hooks/cortex-` trigger) produces zero drift on this commit. No mirror staging needed. Round-3 invocation for this commit:
  - `PATHS_TO_VERIFY="claude/hooks/cortex-output-filter.sh claude/hooks/output-filters.conf claude/hooks/cortex-sync-permissions.py claude/hooks/bell.ps1 tests/test_output_filter.sh tests/fixtures/hooks/sync-permissions"`
  - `COMMIT_DELETE_SET="claude/hooks/cortex-output-filter.sh claude/hooks/output-filters.conf claude/hooks/cortex-sync-permissions.py claude/hooks/bell.ps1 tests/test_output_filter.sh tests/fixtures/hooks/sync-permissions"`
  - `COMMIT_EDIT_SET="tests/test_hooks.sh requirements/project.md docs/agentic-layer.md CHANGELOG.md"`
  Expected `PASS-COMMIT-2`. Commit body trailer `Round-3-reverified: PASS-COMMIT-2` (literal line emitted by the template, pasted in). Commit subject ≤72 chars.
- **Verification**: After commit, run:
  ```
  R3=$(git log --format=%B -1 | grep -c 'Round-3-reverified: PASS-COMMIT-2'); \
  for p in claude/hooks/cortex-output-filter.sh claude/hooks/output-filters.conf claude/hooks/cortex-sync-permissions.py claude/hooks/bell.ps1 tests/test_output_filter.sh tests/fixtures/hooks/sync-permissions plugins/cortex-core/hooks/cortex-output-filter.sh plugins/cortex-core/hooks/output-filters.conf plugins/cortex-core/hooks/cortex-sync-permissions.py plugins/cortex-core/hooks/bell.ps1 plugins/cortex-overnight/hooks/cortex-output-filter.sh plugins/cortex-overnight/hooks/cortex-sync-permissions.py; do [ -e "$p" ] && { echo "FAIL:$p"; exit 1; }; done; \
  SP=$(grep -c 'cortex-sync-permissions' tests/test_hooks.sh); \
  CE=$(grep -c 'Context efficiency' requirements/project.md); \
  OF=$(grep -c 'output-filters.conf' requirements/project.md); \
  BP216=$(awk 'NR==216' docs/agentic-layer.md | grep -c 'bell\.ps1'); \
  SLICE=$(awk '/^## \[Unreleased\]/{f=1;next} /^## \[/{f=0} f' CHANGELOG.md); \
  CL_R=$(echo "$SLICE" | grep -c '^### Removed'); \
  CL_TOK_PASS=1; for tok in cortex-output-filter cortex-sync-permissions output-filters.conf bell.ps1 '~/.claude/settings.json'; do echo "$SLICE" | grep -qF "$tok" || CL_TOK_PASS=0; done; \
  CL_VERB=$(echo "$SLICE" | grep -cE '\b(grep|remove|unbind)\b'); \
  CL_BAD=$(echo "$SLICE" | grep -cE '\b(MUST|CRITICAL|session-breaking)\b'); \
  just test >/dev/null 2>&1; T1=$?; \
  bash tests/test_hooks.sh >/dev/null 2>&1; T2=$?; \
  [ $R3 -eq 1 ] && [ $SP -eq 0 ] && [ $CE -eq 0 ] && [ $OF -eq 0 ] && [ $BP216 -eq 0 ] && [ $CL_R -ge 1 ] && [ $CL_TOK_PASS -eq 1 ] && [ $CL_VERB -ge 1 ] && [ $CL_BAD -eq 0 ] && [ $T1 -eq 0 ] && [ $T2 -eq 0 ] && echo PASS-COMMIT-2
  ```
  Pass if stdout includes `PASS-COMMIT-2`. The verification combines: R16 trailer presence (`R3=1`); paired-deletion absence at canonical paths (the loop over canonical hook paths) AND at both mirror destinations `plugins/cortex-core/hooks/` AND `plugins/cortex-overnight/hooks/` (belt-and-suspenders mirror-absence check per critical review B-class concern); `tests/test_hooks.sh` block removed (`SP=0`); `requirements/project.md` Context-efficiency bullet cut entirely (`CE=0`, `OF=0`); `docs/agentic-layer.md` L216 specifically no longer mentions `bell.ps1` (`BP216=0` — narrow check that does NOT fail on surviving L209/L212/L255/L264 references which are out-of-scope); CHANGELOG `### Removed` subsection present (`CL_R≥1`); all 5 R11 tokens present via per-token loop matching spec R11 verbatim (`CL_TOK_PASS=1` — replaces the broken alternation grep per critical review O3); maintainer-action verb present; no session-breaking phrasing; both test surfaces green.
- **Status**: [ ] pending

### Task 4: Commit 3 — Investigate-then-decide: validate-spec deletion + dual-source mirror (R8, R7-inv-1, R14-c3, R15, R16)
- **Files**:
  - `bin/cortex-validate-spec` (delete — canonical source)
  - `plugins/cortex-core/bin/cortex-validate-spec` (delete — dual-source mirror; `git add` after pre-commit auto-regenerates the mirror as deleted in working tree)
  - `justfile` (edit: delete the `validate-spec` recipe at L326–327 — recipe header + body line)
- **What**: Implement D3 = Option B (delete script + recipe + mirror in one commit). The R7 invariant 1 (script ↔ recipe ↔ mirror tri-pair) closes in this single SHA. `landing-page/` is preserved per D4 = keep — no edits in this commit.
- **Depends on**: [3]
- **Complexity**: simple
- **Context**: Per CLAUDE.md "Auto-generated mirrors at `plugins/cortex-core/{skills,hooks,bin}/` are regenerated by the pre-commit hook from canonical sources" — when `bin/cortex-validate-spec` is deleted, `just build-plugin` (run by pre-commit) will mirror the deletion into `plugins/cortex-core/bin/cortex-validate-spec` as a working-tree change. The implementer must explicitly `git add plugins/cortex-core/bin/cortex-validate-spec` to stage the mirror deletion before committing — otherwise the pre-commit hook's drift check (Phase 4) blocks. The justfile recipe spans exactly L326–327 (`validate-spec *args:` header at L326, body `python3 bin/cortex-validate-spec {{args}}` at L327) per planning-time `grep -n 'validate-spec' justfile`. Ensure no blank line before/after is orphaned. Round-3 invocation for this commit:
  - `PATHS_TO_VERIFY="bin/cortex-validate-spec"`
  - `COMMIT_DELETE_SET="bin/cortex-validate-spec plugins/cortex-core/bin/cortex-validate-spec"`
  - `COMMIT_EDIT_SET="justfile"`
  Expected `PASS-COMMIT-3`. Commit body trailer `Round-3-reverified: PASS-COMMIT-3`. Commit subject ≤72 chars.
- **Verification**: After commit, run:
  ```
  R3=$(git log --format=%B -1 | grep -c 'Round-3-reverified: PASS-COMMIT-3'); \
  test ! -e bin/cortex-validate-spec && \
  test ! -e plugins/cortex-core/bin/cortex-validate-spec && \
  ! grep -qE '^validate-spec:' justfile && \
  ! grep -qE 'bin/cortex-validate-spec' justfile && \
  test -d landing-page && \
  just test >/dev/null 2>&1 && \
  bash tests/test_hooks.sh >/dev/null 2>&1 && \
  [ $R3 -eq 1 ] && \
  echo PASS-COMMIT-3
  ```
  Pass if stdout includes `PASS-COMMIT-3`.
- **Status**: [ ] pending

### Task 5: Commit 4 — Round-2 config hygiene (R10, R3, R14-c4, R15)
- **Files**:
  - `.gitignore` (edit: delete the `debug/test-*/` line and the `ui-check-results/` line; remove dead surrounding comments if the comment becomes orphaned by the deletion)
  - `.mcp.json` (edit: remove the `playwright` MCP server entry; if `mcpServers` becomes empty, leave the empty object `{}` rather than dropping the key — preserves schema shape for future entries)
  - `cortex_command/overnight/sync-allowlist.conf` (edit: delete the L36 `lifecycle/morning-report.md` line)
  - `pyproject.toml` (edit: add `"cortex_command/tests"` to the `[tool.pytest.ini_options].testpaths` array at L40 — append after the existing 6 entries, preserving array formatting; D6 = Option A operator-pick recommended)
- **What**: Land config-hygiene-only edits with no path-deletes, so R16 round-3 grep does NOT apply (this commit has no delete trailer). R7 atomicity has no invariants in this commit (all deletions/edits are independent config lines). Commit lands the final R10 acceptance.
- **Depends on**: [4]
- **Complexity**: simple
- **Context**: For `.mcp.json`, parse the JSON, remove the `playwright` key under `mcpServers`, write back with stable key ordering. For `pyproject.toml`, the testpaths array currently has 6 entries; append `"cortex_command/tests"` as the 7th. Match the existing array's quoting and indentation. Commit subject ≤72 chars, no Round-3-reverified trailer (this is the config-hygiene commit, not a delete commit).
- **Verification**: After commit, run:
  ```
  GI1=$(grep -c '^debug/test-\*/' .gitignore); \
  GI2=$(grep -c '^ui-check-results/' .gitignore); \
  PW=$(grep -c '"playwright"' .mcp.json); \
  SA=$(grep -c 'lifecycle/morning-report.md' cortex_command/overnight/sync-allowlist.conf); \
  TP=$(python3 -c "import tomllib; d=tomllib.loads(open('pyproject.toml','rb').read()); print('cortex_command/tests' in d['tool']['pytest']['ini_options']['testpaths'])"); \
  just test >/dev/null 2>&1; T1=$?; \
  bash tests/test_hooks.sh >/dev/null 2>&1; T2=$?; \
  [ $GI1 -eq 0 ] && [ $GI2 -eq 0 ] && [ $PW -eq 0 ] && [ $SA -eq 0 ] && [ "$TP" = "True" ] && [ $T1 -eq 0 ] && [ $T2 -eq 0 ] && echo PASS-COMMIT-4
  ```
  Pass if stdout includes `PASS-COMMIT-4`.
- **Status**: [ ] pending

### Task 6: End-to-end branch verification (R7, R12, R13, R14, R16)
- **Files**: none (read-only verification)
- **What**: Run the full spec-level acceptance suite against final HEAD: R7 (parameterized 8-invariant atomicity sweep across the merge-base..HEAD range), R12 (`just test` + `tests/test_hooks.sh` final state), R13 (`bin/cortex-check-parity` parity gate), R14 (exactly 4 commits between merge base and HEAD), R16 (commit-body trailer count).
- **Depends on**: [5]
- **Complexity**: simple
- **Context**: This task runs the spec's R7 atomicity sweep verbatim (8 `check_pair` invocations covering invariants 1–8). The R13 gate (`bin/cortex-check-parity`) must exit 0 against final HEAD. The R14 commit count is checked via `git log --oneline $(git merge-base HEAD main)..HEAD | wc -l = 4` — this passes because Task 1's lifecycle scaffold commit is on `main`, not on the feature branch's diff. The R16 trailer count is checked via `git log --format=%B $(git merge-base HEAD main)..HEAD | grep -c 'Round-3-reverified: PASS-COMMIT-' = 3` (commits 1–3 carry trailers; commit 4 does not).
- **Verification**:
  ```
  MERGE_BASE=$(git merge-base HEAD main); \
  CC=$(git log --oneline "$MERGE_BASE..HEAD" | wc -l | tr -d ' '); \
  TR=$(git log --format=%B "$MERGE_BASE..HEAD" | grep -c 'Round-3-reverified: PASS-COMMIT-'); \
  bash -c '
    fail=0; MERGE_BASE='"$MERGE_BASE"';
    check_pair() { local anchor="$1"; shift; local sha=$(git log --diff-filter=DM --pretty=format:%H "$MERGE_BASE..HEAD" -- "$anchor" | head -1); [ -z "$sha" ] && { echo "FAIL:no-commit:$anchor"; fail=1; return; }; for partner in "$@"; do git show --stat "$sha" -- "$partner" | grep -q "$partner" || { echo "FAIL:$anchor!=$partner"; fail=1; }; done; };
    check_pair bin/cortex-validate-spec justfile plugins/cortex-core/bin/cortex-validate-spec;
    check_pair scripts/migrate-namespace.py tests/test_migrate_namespace.py tests/fixtures/migrate_namespace;
    check_pair scripts/generate-registry.py .gitignore;
    check_pair claude/hooks/cortex-sync-permissions.py tests/test_hooks.sh tests/fixtures/hooks/sync-permissions;
    check_pair claude/hooks/cortex-output-filter.sh claude/hooks/output-filters.conf tests/test_output_filter.sh;
    check_pair claude/hooks/cortex-output-filter.sh requirements/project.md;
    check_pair claude/hooks/bell.ps1 docs/agentic-layer.md;
    check_pair scripts/sweep-skill-namespace.py scripts/verify-skill-namespace.py scripts/verify-skill-namespace.carve-outs.txt;
    exit $fail
  '; R7=$?; \
  just test >/dev/null 2>&1; T1=$?; \
  bash tests/test_hooks.sh >/dev/null 2>&1; T2=$?; \
  bin/cortex-check-parity >/dev/null 2>&1; PG=$?; \
  [ $CC -eq 4 ] && [ $TR -eq 3 ] && [ $R7 -eq 0 ] && [ $T1 -eq 0 ] && [ $T2 -eq 0 ] && [ $PG -eq 0 ] && echo PASS-FINAL
  ```
  Pass if stdout includes `PASS-FINAL`.
- **Status**: [ ] pending

## Verification Strategy

End-to-end verification runs in two layers:

1. **Per-commit boundary checks** (Tasks 2–5 each include their own R15 + per-commit acceptance gates) — catches paired-deletion misses mid-sequence rather than at the end. Tasks 2 and 3 also include belt-and-suspenders mirror-absence checks under `plugins/cortex-core/hooks/` and `plugins/cortex-overnight/hooks/` to surface unexpected drift even if the pre-commit Phase 4 loop catches it first.
2. **Final spec-acceptance sweep** (Task 6) — runs R7's parameterized 8-invariant atomicity sweep, R12 (final test pass), R13 (`bin/cortex-check-parity` gate), R14 (exactly 4 commits between merge base and HEAD), and R16 (3 `Round-3-reverified: PASS-COMMIT-N` trailers in commits 1–3).

Tasks 2–5 each touch >5 files, exceeding the planning sizing guideline of 1–5 files per task. This is a deliberate consequence of R7's eight paired-deletion invariants, which require multi-file atomicity within each commit's SHA. Splitting any of Tasks 2–5 into sub-tasks would either (a) split a paired-deletion invariant across commits (forbidden by R7), or (b) require a multi-task → single-commit coordination pattern that exceeds the legibility benefit for these per-category boundaries.

The round-3 grep template (above) is a refinement of spec R16's literal form with three justified extensions: `--exclude-dir=backlog` (backlog items describe work narratively), broader `--include` patterns (to detect drift in `.conf`/`.gitignore` files), and same-commit DELETE_SET/EDIT_SET exclusions (so paired-deletion partners don't trigger false positives). The trailer text `Round-3-reverified: PASS-COMMIT-N` is unchanged from spec R16; the implementer pastes the literal `PASS-COMMIT-N` line emitted by the refined template into commit bodies.

## Veto Surface

- **D2 = option (b) for `requirements/project.md:36`**: cut the Context efficiency QA entirely (no replacement mechanism named). Spec already resolved this. If the user prefers preserve-and-reword (option a) at plan-review time, Task 3's `requirements/project.md` edit changes shape (option a: reword to drop `output-filters.conf` mention but keep the QA outcome sentence), AND spec R6's acceptance gate (`grep -c 'Context efficiency' requirements/project.md returns 0`) must be amended in lockstep. Spec amendment required for option a/c.
- **D3 = Option B for `bin/cortex-validate-spec`** (delete script + recipe + mirror). Alternative: D3 = Option A (keep + add `bin/.parity-exceptions.md` row with `maintainer-only-tool` rationale ≥30 chars). If user prefers Option A at plan-review, Task 4 inverts: instead of three deletes, the task adds one row to `bin/.parity-exceptions.md` and leaves all three paths in place. R7 invariant 1 dissolves under Option A.
- **D4 = keep `landing-page/` at root** (per spec). Spec resolved.
- **D6 = Option A `pyproject.toml` testpaths edit** (add `cortex_command/tests`). Spec marked operator-pick recommended Option A; non-controversial. If user prefers Option B (leave implicit), drop the `pyproject.toml` edit from Task 5.
- **CHANGELOG advisory placement (Decision 5 = Option A)**: spec resolved as `[Unreleased]` `### Removed` subsection. If user prefers Option B/C, Task 3's CHANGELOG edit changes shape and R11's acceptance gate must be relaxed accordingly.
- **Commit ordering**: spec sequences commit 1 (confirmed-deletes) → commit 2 (DR-4) → commit 3 (validate-spec) → commit 4 (config-hygiene). If user prefers a different per-category ordering, the task ordering shifts but R7/R14/R16 acceptance gates are ordering-independent.
- **Branch name**: `cleanup-orphan-code-and-retire-paired-requirements` (Task 1). User may prefer a different convention (e.g., `cleanup/168-orphan-deletion`); zero impact on acceptance gates.
- **Trailer literal `Round-3-reverified: PASS-COMMIT-N`**: spec mandates this exact trailer text. If user prefers different trailer wording, R16's `grep -c 'Round-3-reverified: PASS-COMMIT-'` acceptance gate must update in lockstep.
- **Round-3 grep template refinement**: this plan extends spec R16's literal template with `--exclude-dir=backlog`, broader `--include` patterns, and same-commit DELETE_SET/EDIT_SET exclusions (per critical review O1 + O2). If user prefers a stricter literal-spec-R16 grep (no refinement), the trailer cannot be authored truthfully against the actual pre-stage tree (commits 1–3 each contain same-commit paired-deletion partners) — so spec R16 itself would need amendment to acknowledge same-commit-partner exclusions. The plan's refinement preserves R16's drift-detection intent while making the gate runnable.
- **Scope of `docs/agentic-layer.md` edits in commit 2**: plan touches L216 only (bell.ps1 row, paired with bell.ps1 hook deletion). L209 (`cortex-sync-permissions.py` row), L212 (`cortex-output-filter.sh` row), L255 (output-filter prose), L264 (sync-permissions prose) are out of scope per spec Non-Requirements ("No `docs/agentic-layer.md` skill-table cleanup"). These references survive after this lifecycle and are owned by sibling ticket #166. If user prefers to widen scope and clean L209/L212/L255/L264 in this lifecycle, Task 3 absorbs four additional row/prose edits, R7 invariants do not change, and #166's docs scope shrinks correspondingly.

## Scope Boundaries

Per spec Non-Requirements section:

- No autopatch into user-global `~/.claude/settings.json`.
- No `requirements/pipeline.md:130` cleanup (separate work — #148 N8 leftover).
- No README/docs reorg (#166 owns).
- No lifecycle/research archive sweep (#169 owns).
- No `docs/agentic-layer.md` skill-table cleanup (#166 owns); only the single-line `bell.ps1` row removal at L216 is in scope, as a paired consistency edit with the bell.ps1 hook deletion. The surviving descriptive references at L209/L212/L255/L264 are explicitly NOT this lifecycle's responsibility.
- No new replacement mechanism for `output-filters.conf` (D2 = cut entirely).
- No allowlist entry for `bin/cortex-validate-spec` (D3 = delete).
- No `landing-page/` move or delete (D4 = keep at root).
- No CHANGELOG entry framed as session-breaking migration (R11 negative-match enforces precautionary framing).
- No commits to sibling-ticket files in working tree (`backlog/064-*.md`, `backlog/166-*.md`, `backlog/169-*.md`, aggregate `backlog/index.{json,md}`, `lifecycle/fix-archive-*/`, `lifecycle/rewrite-readme-*/`, `research/vertical-planning/`) — these belong to other tickets and remain as untouched working-tree state across this lifecycle's branch.
