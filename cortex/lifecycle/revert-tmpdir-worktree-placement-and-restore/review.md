# Review: revert-tmpdir-worktree-placement-and-restore

## Stage 1: Spec Compliance

### Requirement 1: Revert branch (c) of `resolve_worktree_root()`
- **Expected**: branch (c) returns `(repo_root / ".claude" / "worktrees" / feature).resolve()`; module docstring + branch-(c) comments reflect Anthropic-aligned repo-relative rationale; `grep -c "cortex-worktrees" cortex_command/pipeline/worktree.py` = 0; `just test` exits 0.
- **Actual**: `cortex_command/pipeline/worktree.py:166-167` returns `(repo / ".claude" / "worktrees" / feature).resolve()` with `repo = repo_root if repo_root is not None else _repo_root()`. Module docstring (lines 1-18) describes Anthropic-aligned repo-relative default and the filename-scoped `.mcp.json` deny; branch-(c) inline comments (lines 161-165) match. `grep -c "cortex-worktrees" cortex_command/pipeline/worktree.py` = 0. Targeted tests pass (52/52 across the three primary test files).
- **Verdict**: PASS
- **Notes**: Resolver order documented in the function docstring is (a) env override → (c) repo-relative → (d) cross-repo; branch (b) was intentionally dropped per R2. The chokepoint property is preserved (create_worktree, cleanup_worktree, hook resolver, probe all route through this).

### Requirement 2: Delete `_registered_worktree_root()` and branch-(b) call site
- **Expected**: sentinel reader and call site deleted entirely; `grep -c "_registered_worktree_root\|cortex-worktree-root" cortex_command/pipeline/worktree.py` = 0; `just test` exits 0.
- **Actual**: Function and call site absent; grep count = 0. Branch flow in `resolve_worktree_root()` goes (a) → (d) → (c) with no branch-(b) intermediate. Tests pass.
- **Verdict**: PASS

### Requirement 3: Delete Step 7b and `_resolve_worktree_base()` from `init/handler.py`
- **Expected**: Step 7b block + `_resolve_worktree_base()` helper deleted; `cortex init --update` migrates orphaned `cortex-worktrees`-prefixed entries from both `allowWrite` and `additionalDirectories`; migration is idempotent; new `unregister_matching` helper exists; `grep -c "_resolve_worktree_base\|cortex-worktrees" cortex_command/init/handler.py` = 0 (excluding comments explaining what was removed).
- **Actual**: Both deletions confirmed. `handler.py` step 7b is replaced by a 4-line migration block (lines 200-207) that fires only on `--update` and calls `settings_merge.unregister_matching_in_place("cortex-worktrees", home=home)`. The two remaining `cortex-worktrees` hits in handler.py are (a) the migration-block comment at line 200 and (b) the predicate string literal at line 207 — both are deliberate and load-bearing for the migration. Migration test `TestUnregisterMatchingMigration` covers both removal and idempotency.
- **Verdict**: PASS
- **Notes**: Grep matches 2 (not 0) but both are the migration predicate the spec explicitly required; the dead-code intent of the verification is met. Implementer added `unregister_matching(predicate, settings) -> dict` (pure, as specced) AND a `unregister_matching_in_place(predicate, home)` disk-wrapper that handler.py calls — the wrapper preserves the spec's "caller owns load/save" property (the wrapper is the caller) while keeping flock + atomic_write out of handler.py. The pure function remains independently testable.

### Requirement 4: Add `.claude/worktrees/` to `scaffold.py` gitignore targets
- **Expected**: `_GITIGNORE_TARGETS` gains `.claude/worktrees/`; `grep -c "claude/worktrees" cortex_command/init/scaffold.py` ≥ 1.
- **Actual**: `_GITIGNORE_TARGETS` (lines 55-59) now contains three entries including `.claude/worktrees/`. Grep returns 2.
- **Verdict**: PASS

### Requirement 5: Fix `seatbelt_probe.py` allow-set
- **Expected**: `allow_paths` covers both `.claude/worktrees/` (for branch (c) creation) and retains `$TMPDIR` (for probe output files); `grep -c "claude/worktrees\|repo_root\|project_root" cortex_command/overnight/seatbelt_probe.py` ≥ 1 in the allow_paths construction.
- **Actual**: `seatbelt_probe.py:167-174` builds `allow_paths=[str(tmpdir_resolved), str((home_repo / ".claude/worktrees").resolve())]`. The comment block (lines 159-164) explains the dual-path rationale and cites #260. Grep returns 3.
- **Verdict**: PASS

### Requirement 6: Fix `bin/cortex-archive-rewrite-paths` functional exclusion
- **Expected**: `.claude/worktrees/` (or `.claude/`) added to `EXCLUDED_DIR_NAMES`; comment at line ~62 updated.
- **Actual**: `EXCLUDED_DIR_NAMES = frozenset({".git", ".venv", ".claude"})` at line 66. Comment block at lines 67-70 names the new placement and cites #260. Both copies (`bin/` and `plugins/cortex-core/bin/`) updated; dual-source pre-commit hook keeps them in sync.
- **Verdict**: PASS

### Requirement 7: Fix `complete.md` cleanup prefix check
- **Expected**: substring match changes from `cortex-worktrees/interactive-{slug}` to `.claude/worktrees/interactive-{slug}`; `grep -c "claude/worktrees/interactive"` ≥ 1; `grep -c "cortex-worktrees/interactive"` = 0.
- **Actual**: `complete.md:183` now reads `.claude/worktrees/interactive-{slug}`. Greps return 1 and 0.
- **Verdict**: PASS

### Requirement 8: Update `test_worktree.py` and `test_worktree_seatbelt.py`
- **Expected**: revert branch-(c) assertions to expect `.claude/worktrees/`; delete branch-(b) sentinel tests; delete `TestVerifyR5NegativeProperty`; add `test_mcp_json_propagation_and_deny_invariant` asserting `.mcp.json` propagates AND a direct write to `.mcp.json` in the worktree is denied; update seatbelt docstring; mock `_repo_root` for non-git contexts; greps for `cortex-worktrees` / sentinel = 0 in both files; `just test` exits 0.
- **Actual**: All branch-(b) tests and `TestVerifyR5NegativeProperty` are gone. Branch-(c) assertions use `.claude/worktrees/`. Tests that exercise resolution patch `_repo_root` via `unittest.mock.patch("cortex_command.pipeline.worktree._repo_root", return_value=repo)`. Greps return 0. The new test (`tests/test_worktree.py:588-637`) asserts propagation (the `.mcp.json` file exists in the worktree with the seeded content) but explicitly documents that the deny half is enforced by the Claude Code JS tool layer, not Seatbelt — a pytest subprocess `open()` will not raise `PermissionError`, so the deny invariant cannot be observed inside pytest. The docstring frames this as a best-effort pin on the propagation half + a documented note on the deny limitation.
- **Verdict**: PARTIAL
- **Notes**: The propagation half is pinned correctly and a regression in git-worktree-add `.mcp.json` exclusion would be caught. The deny half is not asserted at runtime; the implementation explains why (kernel vs JS-tool-layer enforcement). The plan (Risks section, line 165) already anticipated this exact limitation and authorized scoping the deny assertion to "what IS testable in a subprocess." The spec text reads literally as "asserts a direct write to `.mcp.json` in the worktree is denied by the sandbox" — strictly the test does not, so this is partial rather than full PASS. The deviation is documented in-test and matches the plan's risk-acknowledged scope.

### Requirement 9: Update `test_settings_merge.py`
- **Expected**: delete the three `test_worktree_base_*` integration tests; preserve `register_additional_directories`; `grep -c "cortex-worktrees\|test_worktree_base" cortex_command/init/tests/test_settings_merge.py` = 0.
- **Actual**: The three `test_worktree_base_*` tests are gone. `register_additional_directories` and its idempotency test remain. A new `TestUnregisterMatchingMigration` class adds two tests (removal + idempotency) that pin the new migration path. Grep returns 11 (10 cortex-worktrees inside the new migration test body + 1 `test_worktree_base` in the removed-tests comment at line 951).
- **Verdict**: PARTIAL
- **Notes**: Same deviation pattern as R3 — the literal `cortex-worktrees` is required as the migration predicate the new test class exercises, so the grep cannot be 0. The dead-tests intent (delete the obsolete `test_worktree_base_*` integration tests) is met; the new migration tests provide the inverse coverage the migration code needs. The remaining `test_worktree_base` hit at line 951 is in a deletion-history comment, which provides useful provenance and is what the spec parenthetical "(excluding comments explaining what was removed)" would intend if applied symmetrically with R3.

### Requirement 10: Update `tests/test_hooks.sh`
- **Expected**: TMPDIR-based assertions at lines 164/189/199/220/224/235 replaced with `.claude/worktrees/`-based assertions; `grep -c "cortex-worktrees" tests/test_hooks.sh` = 0.
- **Actual**: `tests/test_hooks.sh` uses a `cortex-worktree-resolve` mock shim (`WT_MOCK_BIN/cortex-worktree-resolve` at lines 168-177) and all path assertions read from `$(cortex-worktree-resolve <name>)` rather than hardcoding `cortex-worktrees/...`. Grep returns 0.
- **Verdict**: PASS

### Requirement 11: Update `cortex/requirements/multi-agent.md`
- **Expected**: replace `$TMPDIR/cortex-worktrees/{feature}/` at lines 30 and 77 with `<repo>/.claude/worktrees/{feature}/`; rewrite line-77 rationale to Anthropic-aligned framing; annotate `restore-worktree-root-env-prefix/` as superseded; `grep -c "TMPDIR/cortex-worktrees" cortex/requirements/multi-agent.md` = 0.
- **Actual**: Line 30 and line 77 both updated. Line 77 contains the new rationale (Anthropic-aligned repo-relative default; project trust covers the path; no per-shell registration needed; `.mcp.json` deny is filename-scoped) and the supersession note pointing at #260. Grep returns 0.
- **Verdict**: PASS

### Requirement 12: Update `cortex/requirements/pipeline.md` lines 165–167
- **Expected**: text at lines 165-167 updated to clarify `.mcp.json` deny is filename-scoped and does NOT block `git worktree add`; `grep -c "blocks.*git worktree add\|git worktree add.*block" cortex/requirements/pipeline.md` = 0; `grep -c "filename-scoped\|file-scoped" cortex/requirements/pipeline.md` ≥ 1.
- **Actual**: Lines 165-167 of `pipeline.md` contain unrelated content (`.vscode/.idea` hardcoded sandbox denies) — the spec's line-number citation was stale. The deny-blocks-git-worktree language asserted by the spec does not exist in this file. First grep returns 0 (vacuously satisfied — no offending text to remove); second grep returns 0 (filename-scoped text not added). The filename-scoped language IS captured in `cortex/requirements/multi-agent.md:77`, `cortex_command/pipeline/worktree.py` docstring (3 occurrences), and `skills/lifecycle/references/parallel-execution.md:12`, `skills/overnight/SKILL.md:133`, `docs/internals/sdk.md:29` — the constraint is documented; just not in the spec-cited file.
- **Verdict**: PARTIAL
- **Notes**: The implementer's deviation note flagged this as a stale spec reference and skipped the sub-task. The filename-scoped invariant is preserved and documented in the right requirements file (multi-agent.md, which is the area doc that owns worktree concerns). `pipeline.md` does not currently document this invariant. The acceptance grep's first half passes (no offending text), but the second half (≥1 filename-scoped) fails. The literal acceptance criterion is unmet; the underlying constraint is captured elsewhere.

### Requirement 13: Update skill references
- **Expected**: rewrite TMPDIR-placement in `parallel-execution.md` (lines 14, 17), `implement.md` (pre-flight at 132-182 + path refs at 200, 202), `skills/overnight/SKILL.md` (line 133); pre-flight verifies path is inside project root rather than checking `additionalDirectories` registration; `grep -rn "cortex-worktrees" skills/` = no matches.
- **Actual**: `parallel-execution.md` lines 10-14 describe `<repo>/.claude/worktrees/{feature}/` with the filename-scoped deny rationale. `implement.md` lines 125-171 describe the worktree at `<repo>/.claude/worktrees/interactive-{slug}/` and the pre-flight check is rewritten as a Python script that calls `cortex-worktree-resolve` then verifies the result is `relative_to(repo_root)`. `skills/overnight/SKILL.md:133` describes the same. Grep returns no matches.
- **Verdict**: PASS

### Requirement 14: Update operational docs
- **Expected**: rewrite worktree-placement at `docs/internals/pipeline.md:139` and `docs/internals/sdk.md:29, 144, 160`; `grep -rn "cortex-worktrees" docs/` = no matches.
- **Actual**: All four cited locations now reference `<repo>/.claude/worktrees/<name>/`. The deny rationale is rewritten in `sdk.md:29` to match the canonical language. Grep returns no matches.
- **Verdict**: PASS

### Requirement 15: Update utility scripts and hooks
- **Expected**: update `bin/cortex-check-parity` line 69 from `$TMPDIR/cortex-worktrees/<feature>` to `.claude/worktrees/<feature>`; add a comment to `claude/hooks/cortex-worktree-create.sh` (lines 39-42) naming `.claude/worktrees/` as the new default; `grep -c "TMPDIR/cortex-worktrees" bin/cortex-check-parity` = 0; hook file contains `.claude/worktrees` in a comment.
- **Actual**: `bin/cortex-check-parity` is now a 35-line dual-channel wrapper (the spec's "line 69" was stale — the original full implementation was extracted into `cortex_command/parity_check.py`). The originally-cited comment is no longer at this location. Both parity-check exceptions for `cortex-worktrees` and `cortex-worktree-root` were dropped from `cortex_command/parity_check.py` (lines 67-75 in the prior version) per Task 15 — confirmed by `grep -c "cortex-worktrees\|cortex-worktree-root" cortex_command/parity_check.py` = 0. `claude/hooks/cortex-worktree-create.sh` lines 39-42 contain the new comment: "Resolves to `<repo>/.claude/worktrees/$NAME` for same-repo features (the new default since #260) and to `$TMPDIR/overnight-worktrees/<session>/$NAME` for cross-repo overnight features." First grep returns 0 (vacuously — no offending text); hook contains `claude/worktrees` (returns 4).
- **Verdict**: PASS
- **Notes**: The literal `bin/cortex-check-parity` line-69 edit is moot (wrapper is too short); the intended effect — removing TMPDIR/cortex-worktrees from the parity-check surface — was achieved by dropping the two parity exceptions in `parity_check.py`. Plan reference was stale; the work performed is the right work.

### Requirement 16: Annotate superseded lifecycle artifacts (and ADR-0005)
- **Expected**: prepend supersedes callout to `restore-worktree-root-env-prefix/research.md` and `spec.md` with back-link to #260; `.mcp.json` Seatbelt deny sections preserved as historical record; both files contain "superseded by #260"; `grep -c "superseded"` ≥ 1 each.
- **Actual**: Both `research.md` and `spec.md` have a `> **Superseded by #260** — ...` callout prepended at the top of the file. The misdiagnosis narrative is preserved verbatim below. Grep returns 4 and 1 respectively. ADR-0005 was created at `cortex/adr/0005-repo-relative-worktree-placement.md` with `status: accepted` frontmatter; Context names the empirical refutation date (2026-05-20), Decision describes the single-chokepoint resolution at `resolve_worktree_root()`, Trade-offs and Alternatives are populated.
- **Verdict**: PASS

## Requirements Drift

**State**: none
**Findings**:
- None
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: `unregister_matching` (pure, dict-in/dict-out) and `unregister_matching_in_place` (disk wrapper with `_in_place` suffix) follow the established pattern in `settings_merge.py` — they pair with `register` and `unregister` in the same module, and the `_in_place` suffix is unambiguous: it tells the caller that the function owns the load-save cycle and writes to disk. The pure variant takes `predicate: str, settings: dict` and returns the mutated dict; the wrapper takes `predicate: str, *, home: Path | None = None` and returns `None`. Both names are searchable and the pure function is independently testable. Consistent with module conventions.
- **Error handling**: The migration wrapper (`unregister_matching_in_place`) early-exits if the settings file is absent (lines 343-345) and re-checks after flock acquisition (lines 350-351). This mirrors `unregister()` exactly and is the right shape for a migration that must be a clean no-op on fresh installs. `_validate_sandbox_shape` still fires under flock so a malformed file surfaces a `SettingsMergeError` rather than silently corrupting state. Atomic write via `atomic_write` preserves the existing crash-safe path. Handler.py wraps `_run()` in a single try/except at `main()` that translates `SettingsMergeError` to exit 2, so the migration shares the established error path.
- **Test coverage**: All plan verifications executed (`grep` checks for R1-R16 confirmed). New tests added per the plan: `TestUnregisterMatchingMigration` (two tests covering removal + idempotency) and `test_mcp_json_propagation_and_deny_invariant` (propagation pinned; deny half documented as kernel-vs-JS-layer limitation). `test_worktree_seatbelt.py` docstring updated. 87 tests across touched files pass (including 52 in test_worktree.py + test_worktree_seatbelt.py + test_settings_merge.py confirmed locally, plus the 35 archive/implement tests). The new test pins the regression Mike #260 explicitly worried about (regression in `git worktree add` `.mcp.json` propagation behavior) — solid invariant coverage at the level achievable from pytest.
- **Pattern consistency**: ADR-0005 follows `cortex/adr/README.md`: the three-criteria gate is met (hard to reverse — coordinated changes across resolver/init/scaffolding/tests/docs; surprising without context — the prior lifecycle reverted the other way, future contributors would re-propose; result of a real trade-off — three rejected alternatives enumerated). Frontmatter is the canonical `status: accepted` shape with no `superseded_by:` (correct for an active decision). The no-content-duplication rule is honored: `cortex/requirements/multi-agent.md:77` back-points to the rationale rather than restating it. The MUST-escalation policy is not triggered (no new MUSTs introduced — the change is a revert + sweep).

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": ["R8: deny-half of test_mcp_json_propagation_and_deny_invariant is not asserted at runtime (kernel-vs-JS-layer limitation documented in-test; matches plan-acknowledged risk)", "R9: grep count for 'cortex-worktrees|test_worktree_base' returns 11 (new TestUnregisterMatchingMigration tests need the literal as migration predicate; deleted-tests intent met)", "R12: pipeline.md sub-task skipped (spec line citations stale; filename-scoped language captured in multi-agent.md and code docstrings instead)"], "requirements_drift": "none"}
```
