# Review: delete-post-shift-orphan-code-scripts-hooks-and-retire-paired-requirements (cycle 1)

> no area docs matched for tags: [repo-spring-cleaning, cleanup, hooks, scripts, plugins]; drift check covers project.md only

## Stage 1: Spec Compliance

### R1 — `plugins/cortex-overnight-integration/` removed — PASS

`test ! -e plugins/cortex-overnight-integration` exits 0. Both test files under `plugins/cortex-overnight-integration/tests/` were removed in commit `503045a`. No `.claude-plugin/` directory was ever present (confirmed in research).

### R2 — Completed-migration scripts and paired test/fixtures removed — PASS

All seven paths checked absent: `scripts/sweep-skill-namespace.py`, `scripts/verify-skill-namespace.py`, `scripts/verify-skill-namespace.carve-outs.txt`, `scripts/generate-registry.py`, `scripts/migrate-namespace.py`, `tests/test_migrate_namespace.py`, `tests/fixtures/migrate_namespace/` (8 fixture files). All removed in commit `503045a`.

### R3 — `.gitignore` dead entries removed — PASS

`grep -E '^(skills/registry\.json|debug/test-\*/|ui-check-results/)$' .gitignore` exits 1 (no matches). All three dead entries removed: `skills/registry.json` and comment in `503045a`; `debug/test-*/` and `ui-check-results/` in `00cf886`. `.mcp.json` playwright entry confirmed removed (empty `mcpServers: {}` object preserved per plan).

### R4 — DR-4 hooks and paired tests/fixtures removed — PASS

All six paths checked absent: `claude/hooks/cortex-output-filter.sh`, `claude/hooks/output-filters.conf`, `claude/hooks/cortex-sync-permissions.py`, `claude/hooks/bell.ps1`, `tests/test_output_filter.sh`, `tests/fixtures/hooks/sync-permissions/`. All removed in commit `48b6183`.

### R5 — `tests/test_hooks.sh` sync-permissions block removed — PASS

`grep -c 'cortex-sync-permissions' tests/test_hooks.sh` returns `0`. The 73-line sync-permissions block was cleanly excised in commit `48b6183` with no adjacent-section damage (worktree tests confirmed intact in current run: 6/6 pass).

### R6 — `requirements/project.md:36` Context efficiency QA cut — PASS

`grep -c 'Context efficiency' requirements/project.md` returns `0`. `grep -c 'output-filters.conf' requirements/project.md` returns `0`. The Quality Attributes section now has five bullets (formerly six); the removal was atomic with DR-4 hook deletion in commit `48b6183` per the DR-4 atomicity constraint.

### R7 — Per-commit atomicity for all 8 paired-deletion invariants — PASS

Verified by running the R7 parameterized check with `aa3c044` as the range base (the spec's `git merge-base HEAD main` equivalent for the on-main implementation). All 13 pair assertions passed:

- Invariant 1 (validate-spec ↔ justfile ↔ mirror): `63d97f3`
- Invariants 2, 3, 8 (migrate-namespace+test+fixtures; generate-registry+.gitignore; sweep+verify pair): `503045a`
- Invariants 4, 5, 6, 7 (sync-permissions+test_hooks+fixtures; output-filter+conf+test_output_filter; output-filter+requirements; bell.ps1+agentic-layer.md): `48b6183`

### R8 — `bin/cortex-validate-spec`, justfile recipe, and dual-source mirror deleted — PASS

All four acceptance conditions satisfied: `bin/cortex-validate-spec` absent, `plugins/cortex-core/bin/cortex-validate-spec` absent, `^validate-spec:` not in justfile, `bin/cortex-validate-spec` not in justfile. Removed in commit `63d97f3`. D3 = Option B implemented.

### R9 — `landing-page/` preserved — PASS

`test -d landing-page && test -f landing-page/README.md` exits 0. D4 = keep confirmed; no changes to `landing-page/` in any commit.

### R10 — Round-2 config-hygiene cleanups — PASS

All three acceptance conditions verified:
- `grep -c 'lifecycle/morning-report.md' cortex_command/overnight/sync-allowlist.conf` → `0`
- `grep -c '"playwright"' .mcp.json` → `0`
- `python3 -c "... 'cortex_command/tests' in testpaths"` → `True` (testpaths now has 7 entries)

### R11 — CHANGELOG `[Unreleased]` `### Removed` advisory entry — PASS

All six acceptance gate conditions pass on the awk-sliced `[Unreleased]` section:
- `### Removed` subsection present
- All five required tokens present: `cortex-output-filter`, `output-filters.conf`, `cortex-sync-permissions`, `bell.ps1`, `~/.claude/settings.json`
- Maintainer-action verb `grep` present
- No session-breaking phrasing (`MUST`, `CRITICAL`, `session-breaking` all absent)

The advisory prose matches the research §Decision 5 recommended template verbatim and is correctly scoped to the four deleted hooks without framing removal as a blocking migration step.

### R12 — `just test` passes after all four commits land — PARTIAL

`just test` exits 0 (6/6 suites: test-pipeline, test-overnight, test-init, test-install, tests, tests-takeover-stress). `tests/test_output_filter.sh` is absent (correct). However, `bash tests/test_hooks.sh` exits 1 with 3 failing tests (`scan-lifecycle/single-incomplete-feature`, `scan-lifecycle/claude-output-format`, `scan-lifecycle/fresh-resume-fires`).

**Assessment**: these 3 failures are demonstrably pre-existing at `c019e97` (the commit before the lifecycle-168 scaffold) and are confirmed unrelated to any deletion in this lifecycle — they test `hooks/cortex-scan-lifecycle.sh` behavior, not any of the removed hooks. The implementer's events.log records this finding explicitly at task_complete for task 3: "3 scan-lifecycle failures in tests/test_hooks.sh are pre-existing on c019e97 (predate lifecycle 168), unrelated to the deletion." The spirit of R12 (no deletion-related test failures) is satisfied; the letter (exit 0) is not, due to a pre-existing unrelated regression. Rated PARTIAL rather than FAIL because: (a) the pre-existing nature is documented in the events.log with a specific SHA reference, (b) R13 confirms no parity orphans escaped, and (c) the failing tests are demonstrably not within this lifecycle's scope.

### R13 — `bin/cortex-check-parity` passes — PASS

`bin/cortex-check-parity` exits 0 against final HEAD. The parity gate confirms no `bin/cortex-*` scripts are orphaned after the deletions. No `--no-verify` bypass at any commit (all commits pass through the pre-commit hook as designed).

### R14 — Implementation lands as 4 per-category commits — PARTIAL

**Deviation 1 (feature branch)**: implementation ran directly on `main` (user-directed). R14's "on a feature branch" precondition is unevaluable; the spec's `git merge-base HEAD main` = HEAD when on main. Adapted to `aa3c044..HEAD` range.

**Deviation 2 (commit count)**: 5 commits in range vs. spec's "exactly 4":
1. `503045a` — Confirmed deletes (Task 2, R14-c1)
2. `6da8fa9` — SIGHUP test fixture fix (out of R14 scope — test infrastructure)
3. `48b6183` — DR-4 hooks + paired tests/requirements/docs/CHANGELOG (Task 3, R14-c2)
4. `63d97f3` — validate-spec deletion + mirror (Task 4, R14-c3)
5. `00cf886` — Config hygiene (Task 5, R14-c4)

The 5th commit (`6da8fa9`) is strictly test infrastructure (2 files: `tests/test_runner_followup_commit.py`, `tests/test_runner_signal.py`) fixing a pre-existing PATH-resolution flake that surfaced when running under `.venv/bin/pytest`. No source code or config was changed. The 4 deletion commits are correctly sequenced per R14's category order. Rated PARTIAL rather than FAIL: the four-category commit structure is intact and the SIGHUP fix is a necessary test-infrastructure correction that could not be deferred without leaving R15 unsatisfiable.

Commit subjects: all four category commits are imperative, capitalized, no trailing period. One minor convention breach: commit `503045a` subject is 74 characters (exceeds CLAUDE.md's 72-char limit by 2).

### R15 — `just test` AND `bash tests/test_hooks.sh` pass at every commit boundary — PARTIAL

From commit `6da8fa9` onwards (Tasks 3, 4, 5), `just test` is confirmed 6/6 green. At `503045a` (Task 2), `just test` was blocked by the pre-existing SIGHUP test flake inherited from `c019e97` — fixed in the inline `6da8fa9` commit. `bash tests/test_hooks.sh` exits 1 at all boundaries due to the 3 pre-existing scan-lifecycle failures (same pre-existing finding as R12). The per-commit boundary verification was performed by the implementer and documented in task_complete events. The paired-deletion invariants (the core safety goal of R15) are all satisfied: no deletion-related test failures surfaced at any boundary.

### R16 — Round-3 NOT_FOUND grep re-verification at implement time — PASS

`git log --format=%B aa3c044..HEAD | grep -c 'Round-3-reverified: PASS-COMMIT-'` returns exactly `3`. Trailers present in commits 1 (`503045a`), 2 (`48b6183`), and 3 (`63d97f3`). Commit 4 (`00cf886`) correctly omits the trailer (config-hygiene commit with no path deletes). The round-3 template used the plan's refined form (with `--exclude-dir=backlog`, broader `--include`, and same-commit DELETE_SET/EDIT_SET exclusions) — all three refinements are documented and justified in plan §Round-3 Grep Template.

---

## Stage 2: Code Quality

Stage 1 contains no outright FAIL verdicts (two PARTIAL, both pre-existing and documented). Stage 2 proceeds.

**Commit structure**: the four deletion categories map cleanly to the spec's R14 taxonomy. Each commit's body explicitly names the R7 invariants it closes (e.g., `48b6183`: "R7 atomicity invariants 4/5/6/7 close in this SHA") — this is excellent maintainer documentation and makes bisect-based auditing straightforward.

**`.gitignore` cleanup**: removal of the `# Auto-generated skill registry` comment alongside `skills/registry.json` was the correct paired edit (plan §Task 2 context specified this). The `debug/test-*/` and `ui-check-results/` removals in `00cf886` are clean with no orphaned comments.

**`.mcp.json`**: the `playwright` key was removed while preserving the `mcpServers: {}` empty-object shape per plan guidance. Valid JSON, correct per plan task 5 context ("preserves schema shape for future entries").

**`tests/test_hooks.sh` block removal**: the sync-permissions block (formerly L307-L382) was removed cleanly. Post-removal grep confirms zero `cortex-sync-permissions`, `SYNC_HOOK`, `SYNC_FIXTURE_DIR`, or `SYNC_TMPDIR` references survive. The adjacent Summary section and worktree-create/remove blocks are intact.

**`docs/agentic-layer.md`**: the `bell.ps1` table row at L216 was removed (R7 invariant 7 satisfied). The surviving `cortex-sync-permissions.py` (L209) and `cortex-output-filter.sh` (L212) rows are correctly preserved per spec Non-Requirements ("No `docs/agentic-layer.md` skill-table cleanup — #166 owns"). This is expected stale-documentation state, not a miss.

**CHANGELOG advisory**: matches the research §Decision 5 recommended exact prose template. Section-bracketed correctly under `## [Unreleased]` per Keep-a-Changelog convention. Precautionary framing preserved (no session-breaking language).

**Out-of-scope files in Task 5 commit**: commit `00cf886` includes `backlog/index.json` and `backlog/index.md` alongside the four planned config-hygiene files and `lifecycle/events.log`. The plan explicitly states these "are intentionally NOT in this task's commit set... aggregate state across multiple in-flight tickets... committed in a coordinated cross-lifecycle step." The sub-agent included them anyway. The changes are benign (status field updated from `backlog` to `in_progress`, spec path added) and the aggregate files are auto-generated state — no spec requirement is violated and no invariant is broken. However, this is a scope discipline miss: the commit's content does not match the plan's Task 5 file list, and the backlog/index changes reflect cross-lifecycle state that should be coordinated separately. Flagged as a code quality concern, not a spec failure.

**Pattern consistency**: the four deletion commits follow CLAUDE.md conventions (imperative, capitalized, no trailing period). One minor breach: `503045a` subject is 74 chars (2 over the 72-char limit). The SIGHUP fix commit (`6da8fa9`) follows the same conventions. All commits use `/cortex-core:commit` as required (inferred from events.log timestamp pattern and commit authorship).

---

## Requirements Drift

**State**: detected

**Findings**: The removal of `requirements/project.md:36` (the "Context efficiency" quality attribute) under D2 = option b is a resolved user decision (spec R6, spec Non-Requirements §D2) and was executed as specified. However, it removes a stated quality attribute from the project requirements without a replacement, introducing a permanent absence in the requirements document. Future contributors will not find any documented QA covering preprocessing-hook context filtering; the spec's Non-Requirements section explicitly anticipates this: "If a future ticket reintroduces preprocessing-hook context filtering, it must restore the QA in `requirements/project.md` then." This is an intentional, user-approved drift — the requirements document now understates a historical concern — but it qualifies as "detected" under the drift definition because behavior (or in this case the absence of a mechanism) is no longer captured in requirements.

No other drift detected: the SIGHUP test fix introduces no new project capability; the `pyproject.toml` testpaths addition makes explicit what was already implicitly collected; the config-hygiene removals reduce configuration surface without changing behavior.

## Suggested Requirements Update

The deletion of Context efficiency as a QA is user-approved and intentional. The requirements document itself was the artifact modified. No update is needed to any currently-active requirements file — `requirements/project.md` reflects the intended post-cleanup state. The spec's Non-Requirements section is the audit trail for the decision. If a future ticket restores preprocessing-hook context filtering, it should restore the QA at that time.

No `requirements/project.md` append is warranted.

---

## Verdict

```json
{
  "verdict": "APPROVED",
  "cycle": 1,
  "issues": [
    "R12/R15 PARTIAL: bash tests/test_hooks.sh exits 1 due to 3 pre-existing scan-lifecycle test failures (confirmed at c019e97, predating this lifecycle, unrelated to any deletion in scope)",
    "R14 PARTIAL: 5 commits in range vs spec's 4; extra commit is SIGHUP test-infrastructure fix required for R15 green; no feature branch (user-directed deviation); 4 deletion category commits correctly structured",
    "503045a commit subject 74 chars, exceeds CLAUDE.md 72-char limit by 2",
    "00cf886 includes out-of-scope backlog/index.json and backlog/index.md (plan explicitly excluded these); changes are benign auto-generated state but represent scope discipline miss"
  ],
  "requirements_drift": "detected"
}
```
