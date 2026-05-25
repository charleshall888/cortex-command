# Plan: revert-tmpdir-worktree-placement-and-restore

## Overview

Revert `resolve_worktree_root()` branch (c) from `$TMPDIR/cortex-worktrees/<feature>` to `<repo>/.claude/worktrees/<feature>`, delete the dead branch-(b) sentinel machinery and `cortex init` Step 7b registration, drop the now-historical parity-check exceptions, and sweep all code/docs/tests/requirements/config that assert the old TMPDIR placement. Phase 1 is a single atomic code+test commit; Phase 2 is a single atomic docs+config commit.

## Outline

### Phase 1: Core code, tests, and migration (tasks: 1–11)
**Goal**: Make the resolver return the repo-relative path, remove dead code and dead exceptions, add migration helper, fix all test assertions — everything `just test` covers.
**Checkpoint**: `just test` exits 0; `grep -rn "cortex-worktrees" cortex_command/ tests/` = 0 matches; phase 1 committed atomically.

### Phase 2: Docs, config, and requirements sweep (tasks: 12–16)
**Goal**: Update all prose, skill references, docs, requirements, config, hook comments, and superseded lifecycle annotations so no TMPDIR-placement language survives in live documents.
**Checkpoint**: `grep -rn "cortex-worktrees" cortex/requirements/ skills/ docs/ claude/hooks/ cortex/lifecycle.config.md` = 0 matches; phase 2 committed atomically.

## Tasks

### Task 1: Revert resolver branch (c) and delete branch (b) + `_registered_worktree_root()`
- **Files**: `cortex_command/pipeline/worktree.py`
- **What**: Replace the branch-(c) return at line 223 with `(repo_root / ".claude" / "worktrees" / feature).resolve()` where `repo_root` comes from `_repo_root()`. Update module docstring (line 5) and branch-(c) inline comments (lines 178, 217) to reflect repo-relative default and Anthropic-aligned rationale. Delete `_registered_worktree_root()` (lines 119–161) and its call site at line 208 in `resolve_worktree_root()`.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `_repo_root()` already exists (subprocess `git rev-parse --show-toplevel`). Branch-(c) currently: `return Path(os.environ.get("TMPDIR", "/tmp")).resolve() / "cortex-worktrees" / feature`. Branch-(b) call site at line 208: `registered = _registered_worktree_root()` followed by `if registered: return (registered / feature).resolve()`. After deletion, branch flow is: (a) env-var override → (b) gone → (c) repo-relative → (d) cross-repo overnight.
- **Verification**: `grep -c "cortex-worktrees" cortex_command/pipeline/worktree.py` = 0; `grep -c "_registered_worktree_root\|cortex-worktree-root" cortex_command/pipeline/worktree.py` = 0; `just test` exits 0.
- **Status**: [ ] pending

### Task 2: Add `unregister_matching()` to `settings_merge.py`
- **Files**: `cortex_command/init/settings_merge.py`
- **What**: Add a new function `unregister_matching(predicate: str, settings: dict) -> dict` that removes entries containing `predicate` as a substring from both `sandbox.filesystem.allowWrite` and `additionalDirectories` in the settings dict. Returns the modified settings. The existing `unregister()` uses exact-string equality and only covers `allowWrite`; this new function is the migration predicate.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `unregister()` signature at line 208: `def unregister(repo_root, cortex_target_path, home=None)`. The new `unregister_matching` operates on an already-loaded settings dict (not disk I/O) — the caller in `handler.py` owns the load/save cycle. Pattern: filter `[e for e in arr if predicate not in str(e)]` applied to both arrays under `settings["sandbox"]["filesystem"]["allowWrite"]` and `settings["additionalDirectories"]`.
- **Verification**: Unit test: calling `unregister_matching("cortex-worktrees", settings_with_entry)` removes matching entries from both arrays and leaves non-matching entries untouched; `just test` exits 0.
- **Status**: [ ] pending

### Task 3: Delete Step 7b + `_resolve_worktree_base()`, wire migration in `handler.py`
- **Files**: `cortex_command/init/handler.py`
- **What**: Delete the worktree-base registration block (lines 200–211, Step 7b) and `_resolve_worktree_base()` helper (lines 216–234). In the `--update` branch (around lines 157–163), call `unregister_matching("cortex-worktrees", settings)` on the loaded settings before writing back to disk. Load `~/.claude/settings.local.json` (or `home/settings.local.json`), call `unregister_matching`, write back atomically (existing flock pattern from ADR-0003 applies). The `--update` branch already calls `scaffold.scaffold()` and `scaffold.drift_files()` — the migration call goes after those, guarded by `if settings_changed`.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**: `--update` branch in handler starts around line 157. The flock-guarded settings load/save pattern is at `settings_merge.py:load()` + `settings_merge.write_atomic()`. The `unregister()` function call site (line 132, `--unregister` path) shows the pattern.
- **Verification**: `grep -c "_resolve_worktree_base\|cortex-worktrees" cortex_command/init/handler.py` = 0; `just test` exits 0.
- **Status**: [ ] pending

### Task 4: Add `.claude/worktrees/` to scaffold gitignore targets
- **Files**: `cortex_command/init/scaffold.py`
- **What**: Add `.claude/worktrees/` to the `_GITIGNORE_TARGETS` tuple at line 53 so `cortex init` appends the pattern to user repos' `.gitignore`.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `_GITIGNORE_TARGETS = ("cortex/.cortex-init", "cortex/.cortex-init-backup/")` — append `.claude/worktrees/` as a third entry.
- **Verification**: `grep -c "claude/worktrees" cortex_command/init/scaffold.py` ≥ 1; `just test` exits 0.
- **Status**: [ ] pending

### Task 5: Fix seatbelt probe allow-set
- **Files**: `cortex_command/overnight/seatbelt_probe.py`
- **What**: Update `allow_paths` at line 164 so it covers BOTH the repo's `.claude/worktrees/` path (for branch-(c) worktree creation under the spawned claude session) AND retains `$TMPDIR` coverage for probe output files written at lines 156–157. Derive the `.claude/worktrees/` path from `_repo_root()` or the probe's existing `repo_root` variable — do not hardcode.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Current line 164: `allow_paths=[str(tmpdir_resolved)]`. The probe spawns `claude -p` with these paths in the sandbox `allowWrite` allowlist. After the revert, `resolve_worktree_root()` returns `<repo>/.claude/worktrees/<feature>` — outside `$TMPDIR` — so the spawned claude will fail to create the worktree unless `.claude/worktrees/` is in `allow_paths`. `$TMPDIR` must remain because probe result files (`seatbelt-output-*`, `seatbelt-result-*`) are written there.
- **Verification**: Inspect the `allow_paths` construction line (the assignment whose right-hand side flows into the `claude -p` invocation): `awk '/allow_paths\s*=/,/\]/' cortex_command/overnight/seatbelt_probe.py | grep -c "claude/worktrees"` ≥ 1 AND `awk '/allow_paths\s*=/,/\]/' cortex_command/overnight/seatbelt_probe.py | grep -c "tmpdir\|TMPDIR"` ≥ 1 (both the new repo-relative path AND $TMPDIR coverage must appear in the same construction). `just test` exits 0.
- **Status**: [ ] pending

### Task 6: Fix archive rewriter functional exclusion
- **Files**: `bin/cortex-archive-rewrite-paths`, `plugins/cortex-core/bin/cortex-archive-rewrite-paths`
- **What**: Add `.claude` to `EXCLUDED_DIR_NAMES` in both copies of the archive rewriter. After the revert, worktrees are inside the repo tree under `.claude/worktrees/`; without exclusion the rewriter walks into worktree copies of lifecycle docs and mutates them. Update the comment block at lines 62–66 to reflect that worktrees are now repo-relative and the exclusion is needed.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `EXCLUDED_DIR_NAMES = frozenset({".git", ".venv"})` at line 66 (both copies). The filter at line 110: `dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDED_DIR_NAMES)` — matches on individual path component names, so `.claude` covers `.claude/worktrees/` entirely. Both files must stay in sync (dual-source enforcement via pre-commit drift check) — the canonical edit is `bin/cortex-archive-rewrite-paths`; `plugins/cortex-core/bin/cortex-archive-rewrite-paths` regenerates automatically via the pre-commit hook (`just build-plugin`), but verify both for safety.
- **Verification**: `grep -c "\.claude" bin/cortex-archive-rewrite-paths` ≥ 1 in `EXCLUDED_DIR_NAMES` AND `grep -c "\.claude" plugins/cortex-core/bin/cortex-archive-rewrite-paths` ≥ 1 in `EXCLUDED_DIR_NAMES`; `just test` exits 0.
- **Status**: [ ] pending

### Task 7: Fix `complete.md` cleanup prefix check
- **Files**: `skills/lifecycle/references/complete.md`
- **What**: Update the substring match at line 183 in `git worktree list --porcelain` detection from `cortex-worktrees/interactive-{slug}` to `.claude/worktrees/interactive-{slug}`. This is the only code path that detects whether an interactive lifecycle used a worktree and triggers cleanup.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `complete.md:183` currently checks porcelain output for `cortex-worktrees/interactive-{slug}`. After the revert, `create_worktree()` creates the worktree at `<repo>/.claude/worktrees/interactive-{slug}/` (resolved path), so porcelain will emit the resolved `.claude/worktrees/` path. The `.resolve()` requirement means the worktree IS at the resolved path, so the substring `.claude/worktrees/interactive-{slug}` will appear in the porcelain output.
- **Verification**: `grep -c "claude/worktrees/interactive" skills/lifecycle/references/complete.md` ≥ 1; `grep -c "cortex-worktrees/interactive" skills/lifecycle/references/complete.md` = 0.
- **Status**: [ ] pending

### Task 8: Update `tests/test_worktree.py` — delete outdated tests, update assertions and mocking
- **Files**: `tests/test_worktree.py`
- **What**: (a) Delete `TestVerifyR5NegativeProperty` (lines 632–651) — it asserts branch-(c) result is NOT under `<repo>/.claude/`, the opposite of post-revert semantics; (b) delete all branch-(b) sentinel tests (tests patching `_registered_worktree_root` or checking `#cortex-worktree-root` sentinel); (c) revert all remaining branch-(c) path assertions to expect `<repo>/.claude/worktrees/<feature>`; (d) update test mocking so tests that call `resolve_worktree_root()` in non-git contexts patch `_repo_root` rather than `subprocess.run` — branch (c) calls `_repo_root()` directly after the revert.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: `TestVerifyR5NegativeProperty` at line 632 patches `_registered_worktree_root` to `None` and `_repo_root` to `fake_repo`, then asserts `not str(result).startswith(str(fake_repo) + "/.claude/")`. Existing branch-(b) tests look for `cortex-worktree-root` or patch `_registered_worktree_root`. After deletion, `grep -c "_registered_worktree_root\|cortex-worktree-root" tests/test_worktree.py` = 0 is satisfied.
- **Verification**: `grep -c "cortex-worktrees" tests/test_worktree.py` = 0; `grep -c "_registered_worktree_root\|cortex-worktree-root" tests/test_worktree.py` = 0; `just test` exits 0.
- **Status**: [ ] pending

### Task 9: Add `test_mcp_json_propagation_and_deny_invariant`; update `test_worktree_seatbelt.py`
- **Files**: `tests/test_worktree.py`, `tests/test_worktree_seatbelt.py`
- **What**: In `tests/test_worktree.py`, add `test_mcp_json_propagation_and_deny_invariant`: calls `git worktree add .claude/worktrees/probe-test` in a tmp repo, asserts `.mcp.json` is present in the worktree (propagation), and asserts that a direct write to `.mcp.json` is denied (best-effort: use `pytest.raises(PermissionError)` under a `sandbox-exec`-wrapped subprocess if available, or document why the deny half requires a live Claude Code session and omit the runtime assertion while leaving the intent comment). In `tests/test_worktree_seatbelt.py`: update module docstring lines 3–5, replacing `$TMPDIR/cortex-worktrees/<feature>` with `.claude/worktrees/<feature>`. The test bodies import `resolve_worktree_root` and use the returned path dynamically — no body assertions hardcode the old path, so the docstring update is the entire scope for this file.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: `test_worktree_seatbelt.py` module docstring starts at line 1: `"""Seatbelt-active integration tests for both worktree dispatch paths. R10 of restore-worktree-root-env-prefix: prove the new branch-(c) default ($TMPDIR/cortex-worktrees/<feature>)...`. The `.mcp.json` deny is enforced by the Claude Code JS tool layer, not the kernel — `open()` inside pytest will not raise `PermissionError`. Scope the deny assertion to what IS testable in a subprocess (e.g., check `.mcp.json` exists but skip the write-deny half unless `sandbox-exec` is available).
- **Verification**: `grep -c "cortex-worktrees\|TMPDIR/cortex" tests/test_worktree_seatbelt.py` = 0; `just test` exits 0.
- **Status**: [ ] pending

### Task 10: Update `test_settings_merge.py` and `test_hooks.sh`; add migration integration test
- **Files**: `cortex_command/init/tests/test_settings_merge.py`, `tests/test_hooks.sh`
- **What**: In `test_settings_merge.py`: (a) delete the three `test_worktree_base_*` integration tests (lines ~1067–1156) and the comment at line 954 referencing `$TMPDIR/cortex-worktrees/<feature>`; (b) add `TestUnregisterMatchingMigration` with two tests: `test_update_removes_cortex_worktrees_entries` (creates a settings file with `cortex-worktrees`-prefixed paths in both `allowWrite` and `additionalDirectories`, calls `init_main(["--update", ...])`, asserts both entries are gone) and `test_update_idempotent_on_clean_settings` (runs `--update` twice on a file without the entries, asserts settings unchanged). In `test_hooks.sh`: verify no literal `cortex-worktrees` strings exist — the hook tests use a mock resolver (`$WT_TMPDIR/mock-worktrees/` indirection) so no line edits are needed; confirm with grep and document.
- **Depends on**: [2, 3]
- **Complexity**: simple
- **Context**: The three `test_worktree_base_*` tests start around line 1067 and call `init_main()`. `TestUnregisterMatchingMigration` follows the `TestInitMergeSettings` pattern. The `--update` flag path in `handler.py` (post-Task 3) calls `unregister_matching("cortex-worktrees", settings)`.
- **Verification**: `grep -c "cortex-worktrees\|test_worktree_base" cortex_command/init/tests/test_settings_merge.py` = 0; `grep -c "cortex-worktrees" tests/test_hooks.sh` = 0; `just test` exits 0.
- **Status**: [ ] pending

### Task 11: Sweep remaining test files with hardcoded `cortex-worktrees` paths
- **Files**: `tests/test_implement_option2_worktree_creation.py`, `tests/test_hooks_resolver_parity.sh`, `tests/test_archive_rewrite_paths.py`
- **What**: (a) `tests/test_implement_option2_worktree_creation.py`: update the module docstring at line 4 and the test method docstring at line 72 to describe `<repo>/.claude/worktrees/interactive-test-fixture/`; rewrite `expected_path` at lines 82 and 183 from `isolated_tmpdir / "cortex-worktrees" / "interactive-test-fixture"` to compute via `_repo_root() / ".claude" / "worktrees" / "interactive-test-fixture"` (use the same `_repo_root()` helper the production code uses, or call `subprocess.run(['git','rev-parse','--show-toplevel'])`). The fixture `isolated_tmpdir` may no longer be the right base — review the fixture and adjust setup so the test runs against the repo-relative path that `resolve_worktree_root()` actually returns. (b) `tests/test_hooks_resolver_parity.sh`: update lines 31, 33, 34 — replace `$PARITY_TMPDIR/cortex-worktrees/$FEATURE` with the repo-relative path that `resolve_worktree_root` returns under test conditions (or substitute the mock-resolver path the script uses for `WT_TMPDIR` setup). (c) `tests/test_archive_rewrite_paths.py:235`: update the comment from `$TMPDIR/cortex-worktrees/{feature}/` to `<repo>/.claude/worktrees/{feature}/`.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: `test_implement_option2_worktree_creation.py` asserts the path materialization for the interactive worktree creation flow. The hardcoded `cortex-worktrees` paths at lines 82 and 183 are real assertions — they will fail after Task 1 lands because `resolve_worktree_root()` will return `.claude/worktrees/` paths. The fixture and its computed `expected_path` must both update. `test_hooks_resolver_parity.sh` is a bash harness that creates and cleans up a worktree; the cleanup-path strings at lines 31/33/34 will silently no-op (no directory to clean) after revert. `test_archive_rewrite_paths.py:235` is a comment only.
- **Verification**: `grep -c "cortex-worktrees" tests/test_implement_option2_worktree_creation.py tests/test_hooks_resolver_parity.sh tests/test_archive_rewrite_paths.py` = 0; `just test` exits 0.
- **Status**: [ ] pending

### Task 12: Update requirements and lifecycle config files
- **Files**: `cortex/requirements/multi-agent.md`, `cortex/requirements/pipeline.md`, `cortex/lifecycle.config.md`
- **What**: In `multi-agent.md`: replace `$TMPDIR/cortex-worktrees/{feature}/` with `<repo>/.claude/worktrees/{feature}/` at lines 30 and 77; rewrite the line-77 rationale from "Seatbelt mandatory deny blocks `git worktree add`" to "Anthropic-aligned repo-relative default; project trust covers the path; no per-shell registration needed"; annotate the `restore-worktree-root-env-prefix/` reference as "superseded by #260". In `pipeline.md`: update lines 165–167 to clarify the `.mcp.json` deny is filename-scoped (blocks agent writes to `.mcp.json`) and does NOT block `git worktree add` creating the worktree directory or checking out other files. In `cortex/lifecycle.config.md`: update line 35 — replace `$TMPDIR/cortex-worktrees/` with `.claude/worktrees/` in the `worktree-interactive` mode description.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `multi-agent.md:30` — "Outputs: Git worktree at `$TMPDIR/cortex-worktrees/{feature}/`". `multi-agent.md:77` — starts "Worktrees for the default repo are created at `$TMPDIR/cortex-worktrees/{feature}/`; ... Rationale: the Seatbelt mandatory deny on .mcp.json ... blocks `git worktree add`". `pipeline.md` lines 165–167 contain language asserting the deny "blocks `git worktree add`". `cortex/lifecycle.config.md:35` describes `worktree-interactive` mode: "creates a feature branch and a `$TMPDIR/cortex-worktrees/` worktree".
- **Verification**: `grep -c "TMPDIR/cortex-worktrees" cortex/requirements/multi-agent.md` = 0; `grep -c "blocks.*git worktree add\|git worktree add.*block" cortex/requirements/pipeline.md` = 0; `grep -c "filename-scoped\|file-scoped" cortex/requirements/pipeline.md` ≥ 1; `grep -c "cortex-worktrees" cortex/lifecycle.config.md` = 0.
- **Status**: [ ] pending

### Task 13: Update skill references (implement.md, parallel-execution.md, overnight/SKILL.md)
- **Files**: `skills/lifecycle/references/parallel-execution.md`, `skills/lifecycle/references/implement.md`, `skills/overnight/SKILL.md`
- **What**: In `parallel-execution.md`: update lines 14 and 17 — replace `$TMPDIR/cortex-worktrees/{feature}/` with `<repo>/.claude/worktrees/{feature}/` and rewrite the rationale (`.mcp.json` deny is file-scoped; `git worktree add` into `.claude/worktrees/` succeeds). In `implement.md`: update worktree path references at lines 128 and 256 from `$TMPDIR/cortex-worktrees/` to `.claude/worktrees/`; rewrite the pre-flight check at lines 132–182 to verify the worktree path is inside the project root (not check for `additionalDirectories` registration, which no longer exists). In `overnight/SKILL.md`: update line 133 — replace `$TMPDIR/cortex-worktrees/{feature}/` with `<repo>/.claude/worktrees/{feature}/` and rewrite the deny-blocks-git-worktree rationale.
- **Depends on**: none
- **Complexity**: simple
- **Context**: All three files have multiple references to `cortex-worktrees`. The `implement.md` pre-flight check currently verifies `settings.local.json` contains `TMPDIR/cortex-worktrees/` in `allowWrite`/`additionalDirectories`; after this ticket that registration no longer exists. The new pre-flight check verifies `$(cortex-worktree-resolve interactive-{slug})` is inside the repo root (use `cortex-worktree-resolve` to compute the expected path, then verify it starts with `git rev-parse --show-toplevel`). The plugin mirrors at `plugins/cortex-core/skills/lifecycle/references/` regenerate via the pre-commit hook (`just build-plugin`) — only edit the canonical sources.
- **Verification**: `grep -rn "cortex-worktrees" skills/` = 0 matches.
- **Status**: [ ] pending

### Task 14: Update operational docs (`pipeline.md`, `sdk.md`)
- **Files**: `docs/internals/pipeline.md`, `docs/internals/sdk.md`
- **What**: Update worktree-placement text at cited lines: `docs/internals/pipeline.md` line 32 (table entry for `worktree_resolve_cli.py` — update `$TMPDIR/cortex-worktrees/<name>/` to `.claude/worktrees/<name>/`) and line 141 (update path reference); `docs/internals/sdk.md` lines 29, 144, and 160 — replace TMPDIR-placement language and update the deny-blocks-git-worktree rationale.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `docs/internals/pipeline.md:32` — table row for `worktree_resolve_cli.py` names `$TMPDIR/cortex-worktrees/<name>/`. `docs/internals/sdk.md:29` — "Key constraint: worktree isolation is mandatory in sandbox. The Seatbelt mandatory deny... blocks `git worktree add` from checking out `.mcp.json` into any path under the repo `.claude/` scope." This rationale needs rewriting.
- **Verification**: `grep -rn "cortex-worktrees" docs/` = 0 matches.
- **Status**: [ ] pending

### Task 15: Drop dead parity-check exceptions; update hook comment
- **Files**: `cortex_command/parity_check.py`, `claude/hooks/cortex-worktree-create.sh`
- **What**: In `cortex_command/parity_check.py`: delete BOTH exception entries `"cortex-worktrees"` (lines 67–72: comment block + entry) and `"cortex-worktree-root"` (lines 71–75: comment block + entry). After this ticket, neither string has live references in the codebase, so the exceptions are dead config — keeping them as historical tombstones adds maintenance debt and tempts future contributors to re-introduce the path. In `claude/hooks/cortex-worktree-create.sh` at lines 39–42: add a short comment naming `.claude/worktrees/` as the new default for grep-discoverability.
- **Depends on**: [1, 8, 11, 12, 13, 14] — all live references must already be removed before dropping the exceptions, or the parity check will fail
- **Complexity**: simple
- **Context**: `cortex_command/parity_check.py:67–75` holds the two exception entries with descriptive comments. The exceptions exist because the parity linter (`bin/cortex-check-parity` → `cortex_command.parity_check`) flags tokens matching `cortex-*` that appear in skills/docs/tests but lack a corresponding `bin/cortex-*` deployable. With both strings expunged from live code per Tasks 1, 8, 11, 12, 13, 14, the linter no longer encounters them and the exceptions become unreachable.
- **Verification**: `grep -c "cortex-worktrees\|cortex-worktree-root" cortex_command/parity_check.py` = 0; `grep -c "claude/worktrees" claude/hooks/cortex-worktree-create.sh` ≥ 1; `cortex-check-parity` exits 0 (the parity check itself must pass without the exceptions); `just test` exits 0.
- **Status**: [ ] pending

### Task 16: Annotate superseded lifecycle artifacts (R16) and add ADR-0005
- **Files**: `cortex/lifecycle/restore-worktree-root-env-prefix/research.md`, `cortex/lifecycle/restore-worktree-root-env-prefix/spec.md`, `cortex/adr/0005-repo-relative-worktree-placement.md`
- **What**: Prepend a `> **Superseded by #260** — this lifecycle's empirical premise (Seatbelt deny blocks \`git worktree add\` into \`.claude/\`) was refuted on 2026-05-20. The \`.mcp.json\` deny mechanism sections are preserved as a historical misdiagnosis record.` callout to both files. Write `cortex/adr/0005-repo-relative-worktree-placement.md` using the Proposed ADR from the spec verbatim, with the frontmatter shape `status: accepted` per `cortex/adr/README.md`. (ADR-0005 is cited in spec but not yet created; `cortex/adr/` currently has 0001–0004.)
- **Depends on**: none
- **Complexity**: simple
- **Context**: The Proposed ADR in `spec.md` under `## Proposed ADR` has the full content for `0005-repo-relative-worktree-placement`. The supersedes callout must appear at the top of both files (before any existing headings). `cortex/adr/README.md` has the three-criteria gate for ADR creation — confirm ADR-0005 meets it (load-bearing decision: yes — worktree placement is consulted by sandbox, scaffolding, and lifecycle cleanup; actively contested before this ticket: yes — the prior lifecycle moved it the other way; reversal risk non-trivial: yes — requires coordinated changes across resolver, init, tests, and docs).
- **Verification**: `grep -c "superseded\|Superseded" cortex/lifecycle/restore-worktree-root-env-prefix/research.md` ≥ 1; `grep -c "superseded\|Superseded" cortex/lifecycle/restore-worktree-root-env-prefix/spec.md` ≥ 1; `test -f cortex/adr/0005-repo-relative-worktree-placement.md` exits 0; `head -5 cortex/adr/0005-repo-relative-worktree-placement.md | grep -c "^status: accepted$"` = 1.
- **Status**: [ ] pending

## Risks

- **`test_mcp_json_propagation_and_deny_invariant` deny assertion**: The `.mcp.json` deny is enforced by the Claude Code JS layer, not the kernel. Inside a pytest subprocess the `open()` call will not raise `PermissionError`. The test should document this limitation and scope the deny assertion to the mechanism that IS testable (filesystem path existence, not sandbox enforce). The invariant itself is preserved by the non-Requirement "any change to `.mcp.json` sandbox deny is prohibited" — the test pins `.mcp.json` propagation and a best-effort deny check.
- **Dual-source bin/**: both `bin/cortex-archive-rewrite-paths` and `plugins/cortex-core/bin/cortex-archive-rewrite-paths` must be updated identically in Task 6. The pre-commit hook regenerates `plugins/cortex-core/bin/` from `bin/` via `just build-plugin`, so editing the canonical `bin/` copy is sufficient — but verify both for safety.
- **`cortex init --update` call path**: Task 3 wires `unregister_matching` into the `--update` branch. Verify the settings load/save is flock-guarded (ADR-0003) — the existing flock pattern from `init_main` should already wrap the `--update` branch.
- **Task 15 dependency chain**: Dropping the parity-check exceptions requires that Tasks 1, 8, 11, 12, 13, 14 have already removed every live `cortex-worktrees` reference in code, tests, docs, and skills. If any sweep is incomplete, the parity linter will fail closed. The dependency annotation enforces ordering — do not parallelize Task 15 ahead of its prerequisites.
- **Test fixture path resolution in Task 11**: `tests/test_implement_option2_worktree_creation.py` currently uses `isolated_tmpdir` as the base for the expected path. After the revert, the fixture must compute the expected path from the repo root (the same way `resolve_worktree_root` does) — if the fixture's setup creates a fake repo at `isolated_tmpdir` and chdirs into it, the repo-root resolution should work; otherwise the fixture setup needs adjustment.

## Acceptance

`grep -rn "cortex-worktrees" cortex_command/ skills/ docs/ cortex/requirements/ cortex/lifecycle.config.md tests/ claude/hooks/` = 0 matches; `python3 -c "from cortex_command.pipeline.worktree import resolve_worktree_root; import subprocess; r=subprocess.run(['git','rev-parse','--show-toplevel'],capture_output=True,text=True); print(resolve_worktree_root('probe'))"` prints a path under `.claude/worktrees/`; `just test` exits 0; `cortex init --update` on a settings file with a `cortex-worktrees`-prefixed entry removes it; `cortex-check-parity` exits 0 with both dead exception entries removed.
