---
feature: delete-post-shift-orphan-code-scripts-hooks-and-retire-paired-requirements
phase: specify
tier: complex
criticality: medium
created: 2026-05-05
parent_backlog: 168-delete-post-shift-orphan-code-scripts-hooks-and-retire-paired-requirements
parent_epic: 165-repo-spring-cleaning-share-readiness-epic
---

> Epic context: this ticket implements DR-4 (junk deletion + paired requirements retirement) and the F-6/F-7/F-8 dispositions from epic [#165 — Repo spring cleaning](backlog/165-repo-spring-cleaning-share-readiness-epic.md). The epic-level audit lives at [research/repo-spring-cleaning/research.md](research/repo-spring-cleaning/research.md). Sibling tickets #166 (docs/README) and #169 (lifecycle/research archive) are out of scope.

# Specification: Delete post-shift orphan code/scripts/hooks and retire paired requirements

## Problem Statement

The cortex-command repo accumulated orphan code, scripts, hooks, configuration-hygiene lines, and stale requirements/test pairings during the distribution shift in tickets #117/#144/#147 (plugin-only deployment plus retirement of `cortex setup`). Round-3 verification at research time confirmed each path has no current consumer; round-3 re-verification at implement time (R16) catches drift between research and implement. Leaving these in tree creates installer-audience noise (per epic #165's share-readiness thesis), spec/code drift at `requirements/project.md:36`, and a parity orphan at `bin/cortex-validate-spec`. This ticket removes them in four per-category commits with paired-deletion invariants enforced within each commit and verified per-commit by R7 (the parameterized atomicity gate).

## Requirements

### R1: `plugins/cortex-overnight-integration/` is removed (entire directory)

Acceptance: `test ! -e plugins/cortex-overnight-integration && echo PASS || echo FAIL` prints `PASS`. Pass condition: exit 0 with `PASS` on stdout.

### R2: Completed-migration scripts and paired test/fixtures are removed

Acceptance: each path absent from working tree.
```
for p in scripts/sweep-skill-namespace.py scripts/verify-skill-namespace.py scripts/verify-skill-namespace.carve-outs.txt scripts/generate-registry.py scripts/migrate-namespace.py tests/test_migrate_namespace.py tests/fixtures/migrate_namespace; do
  [ -e "$p" ] && { echo "FAIL: $p still exists"; exit 1; }
done
echo PASS
```
Pass condition: exit 0 with `PASS` on stdout (no `FAIL` lines).

### R3: `.gitignore` is updated to drop dead entries

Acceptance: `grep -E '^(skills/registry\.json|debug/test-\*/|ui-check-results/)$' .gitignore` returns no matches and exits 1. Pass condition: `grep` exit code = 1 (no match).

### R4: DR-4 hooks and their paired tests/fixtures are removed

Acceptance: each path absent from working tree.
```
for p in claude/hooks/cortex-output-filter.sh claude/hooks/output-filters.conf claude/hooks/cortex-sync-permissions.py claude/hooks/bell.ps1 tests/test_output_filter.sh tests/fixtures/hooks/sync-permissions; do
  [ -e "$p" ] && { echo "FAIL: $p still exists"; exit 1; }
done
echo PASS
```
Pass condition: exit 0 with `PASS` on stdout.

### R5: `tests/test_hooks.sh` sync-permissions block is removed

Acceptance: `grep -c 'cortex-sync-permissions' tests/test_hooks.sh` returns `0`. Pass condition: stdout is exactly `0`.

### R6: `requirements/project.md:36` Context efficiency QA is cut entirely (option b)

Acceptance: `grep -c 'Context efficiency' requirements/project.md` returns `0`. Pass condition: stdout is exactly `0`. Additionally `grep -c 'output-filters.conf' requirements/project.md` returns `0`.

### R7: Per-commit atomicity for ALL paired-deletion invariants

Each of the 8 paired-deletion invariants (see Technical Constraints) MUST be satisfied within a single git SHA — both halves of every pair land in the same commit. Acceptance: a parameterized check that, for each invariant's anchor path, finds the SHA that deleted/edited the anchor on this branch and verifies the partner path(s) appear in that same SHA's diff.

```
MERGE_BASE=$(git merge-base HEAD main)
fail=0
check_pair() {
  local anchor="$1"; shift
  local sha=$(git log --diff-filter=DM --pretty=format:%H "$MERGE_BASE..HEAD" -- "$anchor" | head -1)
  if [ -z "$sha" ]; then echo "FAIL: no commit touched $anchor"; fail=1; return; fi
  for partner in "$@"; do
    if ! git show --stat "$sha" -- "$partner" | grep -q "$partner"; then
      echo "FAIL: $anchor and $partner not in same commit ($sha)"; fail=1
    fi
  done
}
# Invariant 1: validate-spec script ↔ recipe ↔ dual-source mirror
check_pair bin/cortex-validate-spec justfile plugins/cortex-core/bin/cortex-validate-spec
# Invariant 2: migrate-namespace script ↔ test ↔ fixtures
check_pair scripts/migrate-namespace.py tests/test_migrate_namespace.py tests/fixtures/migrate_namespace
# Invariant 3: generate-registry script ↔ .gitignore line
check_pair scripts/generate-registry.py .gitignore
# Invariant 4: sync-permissions hook ↔ test_hooks.sh block ↔ fixtures
check_pair claude/hooks/cortex-sync-permissions.py tests/test_hooks.sh tests/fixtures/hooks/sync-permissions
# Invariant 5: output-filter hook + conf ↔ test_output_filter.sh
check_pair claude/hooks/cortex-output-filter.sh claude/hooks/output-filters.conf tests/test_output_filter.sh
# Invariant 6: DR-4 — output-filter hook + conf ↔ requirements/project.md retirement
check_pair claude/hooks/cortex-output-filter.sh requirements/project.md
# Invariant 7: bell.ps1 ↔ docs/agentic-layer.md
check_pair claude/hooks/bell.ps1 docs/agentic-layer.md
# Invariant 8: sweep/verify scripts (paired test-only via shared category boundary; satisfied by R14 commit 1)
check_pair scripts/sweep-skill-namespace.py scripts/verify-skill-namespace.py scripts/verify-skill-namespace.carve-outs.txt
[ $fail -eq 0 ] && echo PASS || exit 1
```
Pass condition: stdout includes `PASS`. (R7 generalizes the prior DR-4-only atomicity check across all paired-deletion invariants, including the dual-source mirror at invariant 1 surfaced by critical review.)

### R8: `bin/cortex-validate-spec` and `justfile` validate-spec recipe are deleted (D3 = Option B)

Acceptance:
```
test ! -e bin/cortex-validate-spec && \
test ! -e plugins/cortex-core/bin/cortex-validate-spec && \
! grep -qE '^validate-spec:' justfile && \
! grep -qE 'bin/cortex-validate-spec' justfile && \
echo PASS || echo FAIL
```
Pass condition: stdout includes `PASS`. (Updated to also verify the dual-source mirror is removed per CLAUDE.md "canonical source mirrored into the cortex-core plugin's bin/ via dual-source enforcement.")

### R9: `landing-page/` is preserved at repo root (D4 = keep, pending future GitHub Pages work)

Acceptance: `test -d landing-page && test -f landing-page/README.md && echo PASS || echo FAIL` prints `PASS`. Pass condition: stdout includes `PASS`.

### R10: Round-2 config-hygiene cleanups land

Acceptance:
```
grep -c 'lifecycle/morning-report.md' cortex_command/overnight/sync-allowlist.conf  # expect 0
grep -c '"playwright"' .mcp.json                                                     # expect 0
python3 -c "import tomllib; d=tomllib.loads(open('pyproject.toml','rb').read()); print('cortex_command/tests' in d['tool']['pytest']['ini_options']['testpaths'])"  # expect True
```
Pass condition: first two `grep -c` commands print exactly `0`; the python3 invocation prints `True`.

### R11: CHANGELOG `[Unreleased]` `### Removed` entry advises maintainers about user-global hook bindings

Acceptance: a section-bracketed slice of `CHANGELOG.md` between the `## [Unreleased]` header and the next `## [` header MUST contain a `### Removed` subsection that lists ALL FOUR deleted hook script names AND the `~/.claude/settings.json` path AND a maintainer-action verb (`grep` OR `remove` OR `unbind`) AND must NOT contain session-breaking phrasing (`MUST` capitalized, `CRITICAL`, `session-breaking`, `migration` not as part of "no migration").

```
SLICE=$(awk '/^## \[Unreleased\]/{flag=1; next} /^## \[/{flag=0} flag' CHANGELOG.md)
echo "$SLICE" | grep -q '^### Removed' || { echo "FAIL: no ### Removed subsection in [Unreleased]"; exit 1; }
for token in cortex-output-filter output-filters.conf cortex-sync-permissions bell.ps1 '~/.claude/settings.json'; do
  echo "$SLICE" | grep -qF "$token" || { echo "FAIL: missing token: $token"; exit 1; }
done
echo "$SLICE" | grep -qE '\b(grep|remove|unbind)\b' || { echo "FAIL: no maintainer-action verb"; exit 1; }
if echo "$SLICE" | grep -qE '\b(MUST|CRITICAL|session-breaking)\b'; then
  echo "FAIL: session-breaking phrasing found (advisory should be precautionary per Web research warn-and-continue verdict)"; exit 1
fi
echo PASS
```
Pass condition: stdout includes `PASS`. The acceptance gate enforces (a) section bracketing via awk, (b) `### Removed` placement, (c) all four deleted hook names, (d) the user-global settings path, (e) at least one maintainer-action verb, (f) no session-breaking phrasing — collectively binding the precautionary-advisory framing the Web research established.

### R12: `just test` passes after all four commits land

Acceptance: `just test` exits 0 AND `bash tests/test_hooks.sh` exits 0 AND `bash tests/test_output_filter.sh` does NOT exist (no orphan tests). Pass condition: first two exit codes = 0, third path test = false. Verifies no orphaned-test or paired-deletion miss escaped review across both pytest-collected tests and bash hook tests.

### R13: `bin/cortex-check-parity` pre-commit gate passes (no parity orphans introduced)

Acceptance: `bin/cortex-check-parity` exits 0 against final HEAD. Pass condition: exit code = 0. Each commit on the feature branch must additionally have parent linkage (no `--no-verify` bypasses), verified by absence of pre-commit-rejected commits in the branch.

### R14: Implementation lands as 4 per-category commits (D1 = Option B)

Acceptance: the feature branch contains exactly 4 commits between the merge base and HEAD, each scoped to one category:

1. **Commit 1 — Confirmed deletes**: `plugins/cortex-overnight-integration/`, `scripts/{sweep,verify,generate,migrate}-*.py` + carve-outs, `tests/test_migrate_namespace.py` + fixtures, `.gitignore:20` registry.json line, dual-source mirrors auto-regenerated by pre-commit hook (no manual mirror staging).
2. **Commit 2 — DR-4 hooks + paired tests + paired requirements**: `claude/hooks/{cortex-output-filter.sh,output-filters.conf,cortex-sync-permissions.py,bell.ps1}`, `tests/test_output_filter.sh`, `tests/test_hooks.sh` sync-permissions block + `tests/fixtures/hooks/sync-permissions/`, `requirements/project.md:36` retire (cut entirely per D2), `docs/agentic-layer.md:216` bell.ps1 line removal, CHANGELOG `[Unreleased]` `### Removed` advisory entry per R11.
3. **Commit 3 — Investigate-then-decide dispositions**: `bin/cortex-validate-spec` delete, `plugins/cortex-core/bin/cortex-validate-spec` mirror delete (auto-regenerated by pre-commit hook; staged via `git add plugins/cortex-core/bin/cortex-validate-spec` if not auto-staged), `justfile:326-327` validate-spec recipe delete; `landing-page/` left in place per D4.
4. **Commit 4 — Round-2 config hygiene**: `.gitignore:53` debug/test-*/ line, `.gitignore:64` ui-check-results/ line, `.mcp.json` playwright entry, `cortex_command/overnight/sync-allowlist.conf:36` morning-report.md line, `pyproject.toml:40` testpaths add `cortex_command/tests`.

Pass condition: `git log --oneline $(git merge-base HEAD main)..HEAD | wc -l` returns `4`. Each commit message matches the category subject per CLAUDE.md commit conventions.

### R15: Both `just test` AND `bash tests/test_hooks.sh` pass between each commit

Acceptance: at each of the 4 commit boundaries on the feature branch, BOTH `just test` exits 0 AND `bash tests/test_hooks.sh` exits 0. Pass condition: exit code = 0 for both at each boundary. (R12 covers the post-merge end-state; R15 catches paired-deletion invariant misses mid-sequence for both pytest-collected tests AND bash hook tests, closing the gap that `just test` alone leaves over `tests/test_hooks.sh` and `tests/test_output_filter.sh`.)

### R16: Round-3 NOT_FOUND grep re-verification at implement time

Before each delete commit (R14 commits 1, 2, 3), re-run NOT_FOUND grep against the paths to be deleted in that commit. The check guards against drift between research time and implement time (a new consumer added by a parallel ticket, etc.).

```
# Run before commit N; substitute PATHS_FOR_COMMIT_N
PATHS_FOR_COMMIT_N="<space-separated paths to be deleted in this commit>"
fail=0
for p in $PATHS_FOR_COMMIT_N; do
  # exclude historical surfaces (lifecycle/research/retros); search active code/config/docs/tests/justfile
  if grep -rl --include='*.py' --include='*.sh' --include='*.md' --include='*.json' --include='*.toml' --include='justfile' \
       --exclude-dir=lifecycle --exclude-dir=research --exclude-dir=retros --exclude-dir=.git --exclude-dir=node_modules \
       -F "$(basename "$p")" . 2>/dev/null | grep -v "^./$p$" | head -1; then
    echo "FAIL: $p has surviving consumer beyond historical surfaces"; fail=1
  fi
done
[ $fail -eq 0 ] && echo PASS-COMMIT-N || exit 1
```
Pass condition: round-3 grep emits `PASS-COMMIT-N` for each of commits 1-3 (commit 4 is config-hygiene with no path-deletes that need NOT_FOUND verification). Evidence: include the round-3 PASS line in the commit body of each delete commit, e.g. `Round-3-reverified: PASS-COMMIT-1`.

Verifiable post-merge: `git log --format=%B $(git merge-base HEAD main)..HEAD | grep -c 'Round-3-reverified: PASS-COMMIT-' returns 3` (commits 1, 2, 3). Pass condition: stdout is exactly `3`.

If round-3 grep finds an unexpected consumer for any path: halt the affected delete; surface to the user; decide whether to (a) extend scope to delete the consumer too, (b) keep the path and add to `bin/.parity-exceptions.md` for `bin/*` paths, or (c) defer to a separate ticket.

## Non-Requirements

- **No autopatch into user-global `~/.claude/settings.json`.** Per `requirements/project.md:35` defense-in-depth, the maintainer's personal settings are out of sandbox visibility; CHANGELOG advisory is the sole mitigation.
- **No `requirements/pipeline.md:130` cleanup.** Separate work (the #148 N8 leftover) — not in this ticket.
- **No README/docs reorg.** Out of scope per parent epic — child ticket #166.
- **No lifecycle/research archive sweep.** Out of scope per parent epic — child ticket #169.
- **No `docs/agentic-layer.md` skill-table cleanup.** Out of scope (#166 owns docs reorg). The single-line `bell.ps1` reference removal at `docs/agentic-layer.md:216` is the only docs touch in this ticket and only because it's a paired consistency edit with the bell.ps1 hook deletion.
- **No new replacement mechanism for output-filters.conf** (D2 = cut entirely). Context efficiency is no longer a stated QA. If a future ticket reintroduces preprocessing-hook context filtering, it must restore the QA in `requirements/project.md` then.
- **No allowlist entry for `bin/cortex-validate-spec`** (D3 = delete). The script and its recipe are removed; no `bin/.parity-exceptions.md` row is added.
- **No `landing-page/` move or delete** (D4 = keep at root). The directory is preserved for future GitHub Pages presentation work.
- **No CHANGELOG entry framed as session-breaking migration.** R11 enforces precautionary framing via negative-match acceptance; missing-hook behavior is warn-and-continue per Web research §"Risk-surface verdict."

## Edge Cases

- **Round-3 grep finds an unexpected consumer at implement time.** Behavior codified in R16: halt the affected delete, surface to the user, choose between (a) extend scope, (b) allowlist (for `bin/*` only), or (c) defer. Re-verification grep is mandatory and audit-bound via `Round-3-reverified: PASS-COMMIT-N` commit-body trailer.
- **Pre-commit hook rejection on commit 2 or 3 due to parity gate.** If `bin/cortex-check-parity` flags an unexpected orphan at commit time, the commit is blocked. Expected behavior: investigate root cause; do not bypass with `--no-verify`. Either fix the orphan in the same commit or stop and surface to the user.
- **Dual-source mirror not auto-staged.** CLAUDE.md: "Auto-generated mirrors at `plugins/cortex-core/{skills,hooks,bin}/` are regenerated by the pre-commit hook from canonical sources." The mirror regeneration produces an unstaged working-tree change; the pre-commit hook's drift check (Phase 4) will block if the mirror isn't staged. Behavior: after running `just build-plugin` (or letting the hook do it), `git add plugins/cortex-core/bin/cortex-validate-spec` to stage the mirror deletion before committing. R8 verifies the final-state absence; R7 invariant 1 verifies same-SHA atomicity.
- **`tests/test_hooks.sh` sync-permissions block boundary detection.** The block starts at L308 with the `cortex-sync-permissions.py tests` header and runs to the next non-sync-permissions test section. The implementer must read both boundaries before deletion (header line + next section header) to avoid removing adjacent unrelated test cases.
- **`requirements/project.md` line-number shift after L36 cut.** Cutting the entire Context efficiency QA shifts subsequent line numbers. Documents that reference `requirements/project.md:N` for N>36 must be checked for stale anchors as part of commit 2's review. The lifecycle research already verified one such reference exists at `requirements/pipeline.md:130` (separate ticket); no others surfaced.
- **CHANGELOG `[Unreleased]` section absence.** If the `[Unreleased]` section header is missing or moved when commit 2 is being prepared, add it per Keep-a-Changelog convention (matches `CHANGELOG.md:7` style) before adding the `### Removed` entry. Do not skip the entry due to header absence. R11's awk-based section bracket requires the header to exist.
- **Maintainer's user-global `~/.claude/settings.json` actively binds a deleted hook.** Behavior post-merge: Claude Code emits a `<hook name> hook error` transcript line on each affected event firing (warn-and-continue per Web research). The CHANGELOG advisory directs the maintainer to grep their settings file and remove bindings. No automated mitigation.

## Changes to Existing Behavior

- **REMOVED**: `claude/hooks/cortex-output-filter.sh`, `claude/hooks/output-filters.conf`, `claude/hooks/cortex-sync-permissions.py`, `claude/hooks/bell.ps1` — these hooks lose all repo presence. Maintainer-installed wirings in `~/.claude/settings.json` will produce transcript noise (warn-and-continue) until the maintainer removes the bindings.
- **REMOVED**: `bin/cortex-validate-spec` AND its dual-source mirror at `plugins/cortex-core/bin/cortex-validate-spec` AND the `just validate-spec` recipe — `just validate-spec` will fail with "recipe not found" after merge. No documented workflow consumes the recipe.
- **REMOVED**: `requirements/project.md` Context efficiency QA — context-efficiency filtering is no longer a stated project quality attribute. Future preprocessing-hook context-filtering work must reintroduce the QA.
- **REMOVED**: completed-migration scripts (`sweep-skill-namespace.py`, `verify-skill-namespace.py` + carve-outs, `generate-registry.py`, `migrate-namespace.py`) and the paired test (`tests/test_migrate_namespace.py` + fixtures). No callable surface lost; one-shot migration tools.
- **REMOVED**: `plugins/cortex-overnight-integration/` directory — never fully materialized as a plugin (no `.claude-plugin/` dir inside); no marketplace or build reference today.
- **REMOVED**: `.mcp.json` `playwright` MCP server entry — disabled in `.claude/settings.local.json:3` and no in-repo consumer; deleting the entry removes a config orphan without behavior change.
- **REMOVED**: dead `.gitignore` lines (`skills/registry.json`, `debug/test-*/`, `ui-check-results/`) and dead `cortex_command/overnight/sync-allowlist.conf:36` line — config-hygiene only; no behavior change.
- **MODIFIED**: `pyproject.toml:40` testpaths gains explicit `cortex_command/tests` entry. Behavior: pytest collection becomes explicit for that directory rather than implicit.
- **ADDED**: `CHANGELOG.md` `[Unreleased]` section gains a `### Removed` entry listing the deleted hooks (all four) with a precautionary advisory directing maintainers to grep `~/.claude/settings.json` for the deleted hook script names and remove bindings.

## Technical Constraints

- **DR-4 atomicity binding** (parent epic #165 ratified decision): `claude/hooks/cortex-output-filter.sh` + `claude/hooks/output-filters.conf` deletion MUST land in the same commit as the `requirements/project.md` Context efficiency QA retirement. Mixed-state is forbidden by the epic decision.
- **Paired-deletion invariants** (8 invariants — verified per-commit by R7): each pair lands in a single git SHA.
  1. `bin/cortex-validate-spec` ↔ `justfile` validate-spec recipe ↔ `plugins/cortex-core/bin/cortex-validate-spec` (dual-source mirror)
  2. `scripts/migrate-namespace.py` ↔ `tests/test_migrate_namespace.py` ↔ `tests/fixtures/migrate_namespace/`
  3. `scripts/generate-registry.py` ↔ `.gitignore:20` skills/registry.json line
  4. `claude/hooks/cortex-sync-permissions.py` ↔ `tests/test_hooks.sh` sync-permissions block ↔ `tests/fixtures/hooks/sync-permissions/`
  5. `claude/hooks/cortex-output-filter.sh` + `claude/hooks/output-filters.conf` ↔ `tests/test_output_filter.sh`
  6. `claude/hooks/cortex-output-filter.sh` + `claude/hooks/output-filters.conf` ↔ `requirements/project.md` (DR-4 atomicity)
  7. `claude/hooks/bell.ps1` ↔ `docs/agentic-layer.md:216`
  8. `scripts/sweep-skill-namespace.py` ↔ `scripts/verify-skill-namespace.py` + carve-outs (one-shot pair, same R14 commit 1 by category boundary)
- **Parity gate** (`requirements/project.md:27`): `bin/cortex-check-parity` runs as a pre-commit hook. Deleting `bin/cortex-validate-spec` requires deleting the `justfile` recipe in the same commit AND staging the mirror deletion in `plugins/cortex-core/bin/`. Bypassing the gate via `--no-verify` is not permitted.
- **Dual-source mirror enforcement** (CLAUDE.md): `bin/cortex-*` scripts are canonical sources mirrored to `plugins/cortex-core/bin/` by the pre-commit hook. Deletes of canonical sources cause the pre-commit hook's `just build-plugin` step to remove the mirror in the working tree; the implementer must `git add` the mirror deletion before committing.
- **Test coverage scope of `just test`**: `just test` invokes pytest-collected suites only (justfile:389-419 — `test-pipeline`, `test-overnight`, `test-init`, `test-install`, `pytest tests/`, stress test). It does NOT invoke `bash tests/test_hooks.sh` or `bash tests/test_output_filter.sh`. R12 and R15 explicitly add `bash tests/test_hooks.sh` to the gate to cover bash hook tests; R7's parameterized atomicity check covers paired-deletion invariants regardless of test surface.
- **Defense-in-depth** (`requirements/project.md:35`): no automated mutation of `~/.claude/settings.json`. CHANGELOG advisory is the sole user-global mitigation; per Web research, missing-hook behavior is warn-and-continue, so the advisory is precautionary not migration-critical (R11 enforces this framing via negative match).
- **Commit-message conventions** (CLAUDE.md): imperative mood, capitalized, no trailing period, ≤72 char subject; commits go via `/cortex-core:commit` skill. Each delete commit (1, 2, 3) MUST include a `Round-3-reverified: PASS-COMMIT-N` trailer in its body per R16.
- **Keep-a-Changelog format** (CHANGELOG.md:5): the `### Removed` entry matches existing v0.1.0 prose style. R11 enforces section-bracket placement, all-four-hook-name completeness, maintainer-action verb presence, and precautionary-tone via negative match.
- **CLAUDE.md 100-line cap**: not approached; no new policy entries added.

## Open Decisions

(None — all spec-phase user decisions resolved during §2 interview; critical-review fixes applied without requiring further user input.)
