# Plan: fix-test-cascade-from-252-migration

## Overview

Apply canonical Task 11/12/15 patterns from #252's lifecycle file-by-file across eight in-scope test files: `SourceFileLoader('mod', 'bin/cortex-*')` → direct `from cortex_command.X.Y import ...` (preserving module-private symbols the tests consume), and `[sys.executable, str(SCRIPT_PATH), …]` / `[str(SCRIPT_PATH), …]` → `[sys.executable, "-m", "cortex_command.X.Y", …]` as the default, with two documented exceptions in `test_commit_preflight.py` (helper-split: `_invoke_module` + `_invoke_wrapper`) and one constant re-point (`test_git_env_hardening`'s AST-walker, which is not a subprocess callsite). Then widen the `cache_key = (id(tmp_path), case)` → `cache_key = (str(tmp_path), case)` fix across all 7 parity-test files (the original ticket named 1). Finally verify the closeout signal via direct pytest invocation that bypasses `just test`'s `sed`-indent wrapper.

## Outline

### Phase 1: SourceFileLoader + companion subprocess fixes (tasks: 1, 2, 3, 4)
**Goal**: Convert the four files that combine `SourceFileLoader` on `bin/cortex-*` with companion subprocess callsites to direct imports + `-m` invocation, preserving each test's consumed module-private symbols.
**Checkpoint**: `python3 -c "import ast; tree=ast.parse(open('<file>').read()); ..."` confirms no `SourceFileLoader` calls in any of the four files; each file passes when run individually via `.venv/bin/pytest <file>`.

### Phase 2: Subprocess-only fixes with documented exceptions (tasks: 5, 6, 7, 8)
**Goal**: Convert the four files that contain only subprocess callsites (no `SourceFileLoader`), applying default `-m` plus the helper-split / SCRIPT_PATH re-point exceptions in `test_commit_preflight.py`.
**Checkpoint**: All eight in-scope test files (Phase 1 + Phase 2) pass when run individually; `test_shim_records_invocation` still hits the wrapper's `cortex-log-invocation` shim.

### Phase 3: `id(tmp_path)` widening across all 7 parity-test sites (tasks: 9, 10)
**Goal**: Replace `cache_key = (id(tmp_path), case)` with `cache_key = (str(tmp_path), case)` in all seven parity-test files; update the module-level `_result_cache` type annotation per the canonical model.
**Checkpoint**: `grep -rnE "cache_key = \(id\(tmp_path\)" tests/` returns no matches.

### Phase 4: Closeout verification (task: 11)
**Goal**: Verify the closeout signal via direct pytest invocation that bypasses `just test`'s `sed`-indent wrapper.
**Checkpoint**: `just test` exits 0 OR pytest's short test summary shows zero ERROR lines and zero FAILED lines outside `tests/test_log_invocation_perf.py`.

## Tasks

### Task 1: Rewrite tests/test_resolve_backlog_item.py
- **Files**: `tests/test_resolve_backlog_item.py`
- **What**: Replace the `SourceFileLoader` module-load block (~L118–129) with a direct module import. Read the file first to enumerate every attribute the test accesses on the loaded module (research surfaced at least seven: `slugify`, `_item_title`, `_parse_frontmatter`, `_resolve_kebab`, `_resolve_lifecycle_slug`, `_resolve_numeric`, `_resolve_title_phrase`). Choose between (a) `import cortex_command.backlog.resolve_item as resolver` with the existing fixture binding `resolver` to the module, OR (b) explicit `from cortex_command.backlog.resolve_item import slugify, _item_title, _parse_frontmatter, _resolve_kebab, _resolve_lifecycle_slug, _resolve_numeric, _resolve_title_phrase` plus any missing symbols. Approach (a) is closer to Task 15's canonical model and preserves the existing `resolver` fixture name; prefer it unless the file references symbols by bare name. Convert the three subprocess callsites at L154, L720, L777 from `[sys.executable, str(SCRIPT_PATH), *args]` to `[sys.executable, "-m", "cortex_command.backlog.resolve_item", *args]`.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Task 15's canonical model is at `tests/test_complexity_escalator.py` (commit 5f0d16eb) — `import cortex_command.lifecycle.complexity_escalator as _escalator_module` plus a `@pytest.fixture` returning the module. Promoted module is `cortex_command.backlog.resolve_item` with `main()` per pyproject.toml `[project.scripts]`. The `resolver` fixture must continue to expose every module-private symbol the tests consume; enumerate at task-start by grep.
- **Verification**: `.venv/bin/pytest tests/test_resolve_backlog_item.py --tb=short` exits 0 — pass if all collected tests pass and exit code = 0.
- **Status**: [x] completed

### Task 2: Rewrite tests/test_load_parent_epic.py
- **Files**: `tests/test_load_parent_epic.py`
- **What**: Replace the `SourceFileLoader` block at ~L423 with `import cortex_command.backlog.load_parent_epic as load_parent_epic_module` (or the equivalent name the existing test code references). At task-start, grep the file for every attribute access on the loaded module and ensure all are preserved. Convert subprocess callsites at L60 and L373 from `[sys.executable, str(SCRIPT_PATH), …]` to `[sys.executable, "-m", "cortex_command.backlog.load_parent_epic", …]`.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Promoted module `cortex_command.backlog.load_parent_epic` with `main()`. Same canonical-model reference as Task 1. The file has both SourceFileLoader (L423) and subprocess (L60, L373) patterns. Check whether the file uses a `_load_script_module` helper or accesses the loaded module by a specific local name before choosing the import alias.
- **Verification**: `.venv/bin/pytest tests/test_load_parent_epic.py --tb=short` exits 0 — pass if exit code = 0.
- **Status**: [x] completed

### Task 3: Rewrite tests/test_superseded_frontmatter_tolerance.py
- **Files**: `tests/test_superseded_frontmatter_tolerance.py`
- **What**: The file has one `_load_module_from_path` helper (~L77–84) containing a single `SourceFileLoader` invocation, invoked twice — once for `LOAD_PARENT_EPIC` (~L128–130) and once for `RESOLVE_BACKLOG_ITEM` (~L209–211). Replace the helper or its two call sites with two direct imports: `import cortex_command.backlog.load_parent_epic as ...` and `import cortex_command.backlog.resolve_item as ...`. Verify the tests' `module._parse_frontmatter(...)` accesses at ~L141 and ~L222 (and any other module-private symbol accesses) are preserved after the rewrite — the direct-import path must expose `_parse_frontmatter` (it does; it's a module-private symbol but importable). Convert subprocess callsites at L108, L171, L187 from `str(SCRIPT_PATH)` form to `[sys.executable, "-m", "cortex_command.backlog.{load_parent_epic|resolve_item}", …]` per which script each callsite originally targeted.
- **Depends on**: none
- **Complexity**: simple
- **Context**: This file exercises both load_parent_epic and resolve_item modules. Read the two `SCRIPT_PATH` constants near the top of the file to determine which subprocess callsite targets which module. Reuse the import shape from Tasks 1 and 2. Module-private symbols (`_parse_frontmatter`) remain accessible after direct import — they are only "private" by convention, not by enforcement.
- **Verification**: `.venv/bin/pytest tests/test_superseded_frontmatter_tolerance.py --tb=short` exits 0 — pass if exit code = 0.
- **Status**: [x] completed

### Task 4: Rewrite tests/test_variant_a_writer_sites_baseline.py
- **Files**: `tests/test_variant_a_writer_sites_baseline.py`
- **What**: Replace the `SourceFileLoader` block at L56–62 (loads `bin/cortex-complexity-escalator`) with `import cortex_command.lifecycle.complexity_escalator as _escalator_module` plus the preserved `@pytest.fixture(scope="module") def escalator_module(): return _escalator_module` shape (Task 15's canonical model — keep the fixture). The file uses the constant name `ESCALATOR_SCRIPT` (not `SCRIPT_PATH`). The three subprocess callsites at ~L292/L293, L322/L324, L355/L357 are currently `[str(ESCALATOR_SCRIPT), feature, …]` — wrapper-direct invocations with no `sys.executable`. Convert them to `[sys.executable, "-m", "cortex_command.lifecycle.complexity_escalator", feature, …]`. The argv shape changes (drops the wrapper-direct invocation, adds `sys.executable + "-m"`); this is intentional — `-m` invocation bypasses the wrapper's branch-selection cascade and runs the canonical module directly.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Direct mirror of Task 15's fix at `tests/test_complexity_escalator.py`. Same promoted module. The wrapper-direct argv shape (`[str(ESCALATOR_SCRIPT), …]` instead of `[sys.executable, str(ESCALATOR_SCRIPT), …]`) is the pre-#252 invocation idiom — the wrapper's shebang (`#!/usr/bin/env bash`) handles the runtime. After conversion to `-m`, `sys.executable` is the Python that runs the test.
- **Verification**: `.venv/bin/pytest tests/test_variant_a_writer_sites_baseline.py --tb=short` exits 0 — pass if exit code = 0.
- **Status**: [x] completed

### Task 5: Rewrite tests/test_check_prescriptive_prose.py
- **Files**: `tests/test_check_prescriptive_prose.py`
- **What**: Convert the two subprocess callsites at L47 and L56 from `[sys.executable, str(SCRIPT_PATH), "--staged"|"--root", …]` to `[sys.executable, "-m", "cortex_command.lint.prescriptive_prose", "--staged"|"--root", …]`. No SourceFileLoader in this file.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Promoted module is `cortex_command.lint.prescriptive_prose` with `main()`. Subprocess-only file; smallest rewrite of the eight.
- **Verification**: `.venv/bin/pytest tests/test_check_prescriptive_prose.py --tb=short` exits 0 — pass if exit code = 0.
- **Status**: [x] completed

### Task 6: Rewrite tests/test_commit_preflight.py with helper-split + SCRIPT_PATH re-point
- **Files**: `tests/test_commit_preflight.py`
- **What**: Two distinct edits:
  - **Helper-split (Requirement 2b)**: The file currently has one shared `_invoke` helper at ~L93–109 containing one `[sys.executable, str(SCRIPT_PATH), …]` callsite consumed by five test functions (`test_normal_repo_emits_valid_json` ~L136, `test_bare_repo_exits_3` ~L157, `test_empty_repo_emits_empty_repo_note` ~L171, `test_binary_diff_no_crash` ~L218, `test_shim_records_invocation` ~L278). Split into two helpers:
    - `_invoke_module(*args, **kwargs)` — uses `[sys.executable, "-m", "cortex_command.commit.preflight", *args]`. Used by the four behavior tests.
    - `_invoke_wrapper(*args, **kwargs)` — uses `[str(SCRIPT_PATH), *args]` (no `sys.executable`; bash wrapper handles the runtime). Used ONLY by `test_shim_records_invocation` because the wrapper's `cortex-log-invocation` shim at wrapper lines 12–14 is what writes the JSONL record the test asserts. Amend the helper's docstring or the calling test's docstring to document the wrapper-shim dependency.
    - Update each consuming test function to call the appropriate helper.
  - **SCRIPT_PATH re-point for `test_git_env_hardening` (Requirement 2c)**: This test at ~L391–478 does `source = SCRIPT_PATH.read_text(encoding="utf-8")` (~L406) and `tree = ast.parse(source, filename=str(SCRIPT_PATH))` (~L407). It is an AST walker, NOT a subprocess callsite. After #252, `SCRIPT_PATH` = bash wrapper that crashes `ast.parse`. Define a local constant `_PYTHON_SCRIPT_PATH = REPO_ROOT / "cortex_command" / "commit" / "preflight.py"` near the test (or as a function-scoped variable) and use it in the `read_text()` + `ast.parse()` calls. The AST walker's assertion logic continues against the canonical Python source. If the assertions reference bash-specific constructs (unlikely — the canonical was Python before #252), adjust the walker to match the Python equivalent.
- **Depends on**: none
- **Complexity**: complex
- **Context**: Promoted module is `cortex_command.commit.preflight` with `main()`. The wrapper `bin/cortex-commit-preflight` is a 34-line bash script with the `cortex-log-invocation` shim at lines 12–14 — the shim is wrapper-only (research verified: `grep -rn 'cortex-log-invocation\|log_invocation' cortex_command/commit/` returns nothing). The AST-walker test reads `SCRIPT_PATH.read_text()` and crashes on `set -euo pipefail` from the bash wrapper. The canonical Python source it should audit is `cortex_command/commit/preflight.py`.
- **Verification**: `.venv/bin/pytest tests/test_commit_preflight.py --tb=short` exits 0 with all five subprocess-dependent tests AND `test_git_env_hardening` passing — pass if exit code = 0.
- **Status**: [x] completed

### Task 7: Rewrite tests/test_clarify_critic_alignment_integration.py
- **Files**: `tests/test_clarify_critic_alignment_integration.py`
- **What**: Convert the subprocess callsite at L98–103 from `[sys.executable, str(SCRIPT_PATH), slug, …]` to `[sys.executable, "-m", "cortex_command.backlog.load_parent_epic", slug, …]`. No SourceFileLoader in this file.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Promoted module is `cortex_command.backlog.load_parent_epic`. Single subprocess callsite; simplest rewrite.
- **Verification**: `.venv/bin/pytest tests/test_clarify_critic_alignment_integration.py --tb=short` exits 0 — pass if exit code = 0.
- **Status**: [x] completed

### Task 8: Repair tests/test_cortex_morning_review_gc_demo_worktrees.py via -m conversion
- **Files**: `tests/test_cortex_morning_review_gc_demo_worktrees.py`
- **What**: Convert the subprocess callsite at L134 from `[str(SCRIPT_PATH), active_session_id]` (with the stripped env `{"TMPDIR": str(tmp_tmpdir), "PATH": os.environ["PATH"]}`) to `[sys.executable, "-m", "cortex_command.overnight.gc_demo_worktrees", active_session_id]`. Keep the explicit `env=` parameter (the test's hermeticity intent is to isolate from user TMPDIR pollution); `-m` invocation bypasses the wrapper's CLI-discovery cascade entirely, so the stripped env no longer causes the wrapper to fail with "cortex-command CLI not found". Update the test file's top-level docstring or the `_run_gc` helper's docstring to reflect that invocation goes directly through the canonical module rather than the bash wrapper.
- **Depends on**: none
- **Complexity**: simple
- **Context**: The canonical module is `cortex_command.overnight.gc_demo_worktrees` (NOT `cortex_command.morning_review.gc_demo_worktrees` — pyproject.toml `[project.scripts]:49` maps `cortex-morning-review-gc-demo-worktrees = "cortex_command.overnight.gc_demo_worktrees:main"`, and the file exists at `cortex_command/overnight/gc_demo_worktrees.py` with `main()` and `__main__`). The wrapper itself execs `python3 -m cortex_command.overnight.gc_demo_worktrees`. The test's six assertions are purely behavioral (returncode, worktree presence/absence, tagged-stderr line prefixes/order) — none depend on bash-wrapper-specific behavior, so `-m` conversion preserves all test assertions identically.
- **Verification**: `.venv/bin/pytest tests/test_cortex_morning_review_gc_demo_worktrees.py --tb=short` exits 0 — pass if all 6 currently-failing tests now pass.
- **Status**: [x] completed

### Task 9: Replace id(tmp_path) cache keys in 4 parity files (auto_bump_version, backlog_ready, complexity_escalator, lifecycle_counters)
- **Files**: `tests/test_cortex_auto_bump_version_parity.py`, `tests/test_cortex_backlog_ready_parity.py`, `tests/test_cortex_complexity_escalator_parity.py`, `tests/test_cortex_lifecycle_counters_parity.py`
- **What**: In each file, locate the `cache_key = (id(tmp_path), case)` line (approx L230, L190, L168, L168 respectively) and replace with `cache_key = (str(tmp_path), case)`. Update the module-level `_result_cache` type annotation if it currently reads `dict[tuple[int, str], …]` to `dict[tuple[str, str], …]` per the canonical model at `tests/test_cortex_commit_preflight_parity.py:317`. If a callsite uses the alternative `f"{tmp_path!s}::{case}"` composite (also canonical), that is equally acceptable.
- **Depends on**: none
- **Complexity**: simple
- **Context**: The canonical already-fixed template is at `tests/test_cortex_commit_preflight_parity.py:317` (note the inline comment "(avoids id(tmp_path) cache collision)"). All four files in this task carry the identical pattern with a module-level `_result_cache` dict and three test functions sharing one memoized subprocess invocation.
- **Verification**: `grep -nE "cache_key = \(id\(tmp_path\)" tests/test_cortex_auto_bump_version_parity.py tests/test_cortex_backlog_ready_parity.py tests/test_cortex_complexity_escalator_parity.py tests/test_cortex_lifecycle_counters_parity.py` returns no matches, pass if exit code = 1.
- **Status**: [x] completed

### Task 10: Replace id(tmp_path) cache keys in 3 parity files (lifecycle_state, load_parent_epic, log_invocation)
- **Files**: `tests/test_cortex_lifecycle_state_parity.py`, `tests/test_cortex_load_parent_epic_parity.py`, `tests/test_cortex_log_invocation_parity.py`
- **What**: Same replacement as Task 9 — `cache_key = (id(tmp_path), case)` → `cache_key = (str(tmp_path), case)` at approx L156, L171, L370 respectively. Update the module-level cache type annotation in each file accordingly.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Same canonical template as Task 9 (`tests/test_cortex_commit_preflight_parity.py:317`). These three files complete the 7-site widening surfaced by critical review.
- **Verification**: `grep -nE "cache_key = \(id\(tmp_path\)" tests/test_cortex_lifecycle_state_parity.py tests/test_cortex_load_parent_epic_parity.py tests/test_cortex_log_invocation_parity.py` returns no matches, pass if exit code = 1. The combined Task 9 + 10 closeout `grep -rnE "cache_key = \(id\(tmp_path\)" tests/` also returns no matches.
- **Status**: [x] completed

### Task 11: Closeout verification — direct pytest invocation
- **Files**: (no file modifications; verification only)
- **What**: Run `just test` from the repo root and capture its exit code. If exit code = 0, closeout passes. If exit code ≠ 0, the failure surface must be exactly `tests/test_log_invocation_perf.py` (the documented pre-existing unrelated failure). Verify this via DIRECT pytest invocation (NOT via `just test`'s `sed`-prefixed output): run `.venv/bin/pytest tests/ --tb=no -q --no-header` and confirm zero `ERROR ` lines and zero `FAILED ` lines outside `tests/test_log_invocation_perf.py` in the short test summary. If additional failures surface (i.e., previously masked by ImportErrors and now revealed), surface them in the closeout commit message and route to Review per Requirement 4 — do NOT silently allowlist them.
- **Depends on**: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
- **Complexity**: simple
- **Context**: Requirement 4 is the binding closeout contract. The Implement phase's final task; no further file modifications, only verification. The closeout commit body should include the `just test` exit code, the failure set (if non-empty), and a brief note on any unmasked secondary failures for Review's attention. Direct pytest invocation bypasses the `just test` recipe's `echo "$output" | sed 's/^/       /'` indent (justfile L474–503), which would otherwise prevent `^FAILED ` line-anchor greps from matching.
- **Verification**: `just test` exits 0 OR (`just test` exits non-zero AND `.venv/bin/pytest tests/ --tb=no -q --no-header 2>&1 | grep -E "^(ERROR|FAILED) " | grep -v "tests/test_log_invocation_perf\.py" | wc -l` equals 0) — pass if either branch holds.
- **Status**: [ ] pending

## Risks

- **Task 1, 2, 3 module-private symbol enumeration**: The tests consume module-private symbols (underscore-prefixed). Each task instructs the implementer to grep the file for module attribute accesses and ensure all are preserved after direct import. If a symbol is missed, the test fails with `AttributeError` on first invocation — `pytest --tb=short` exit code surfaces this immediately. Mitigation: each task's `What` directive explicitly says to enumerate before rewriting.
- **Task 6's helper-split scope**: `test_commit_preflight.py` requires creating `_invoke_module` AND `_invoke_wrapper` AND updating five test functions' callsites. This is the most invasive task. The argument list `_invoke_module` accepts must match `_invoke_wrapper`'s so test functions are interchangeable — except `test_shim_records_invocation` which explicitly uses `_invoke_wrapper`. If the implementer accidentally routes a behavior test through `_invoke_wrapper`, that test's exit-code assertions may differ from module invocation (the wrapper's branch-selection logic can produce different stderr); mitigation: each test function's call points to its helper by name, and the verification is `pytest <file>` which catches semantic divergence.
- **Task 11 closeout secondary blast radius**: Tasks 1–10 may unmask additional failing tests previously hidden by ImportErrors at module load. Requirement 4 requires surfacing those at Review, not silently allowlisting. The verification regex distinguishes `ERROR ` (collection-time) from `FAILED ` (assertion-time) so the implementer can categorize surprises. If the volume is large, Review may decide to split out a follow-up backlog item rather than expanding this ticket's scope.
- **Plan-time vs Implement-time path drift**: This plan was authored against current `HEAD = 1fe5f29e`. If main advances substantially between plan approval and Implement, line numbers in the task `What` fields may drift. Each task uses `~L<N>` notation to signal approximate location; the implementer should grep for the canonical-shape pattern (e.g., `SourceFileLoader`, `cache_key = (id(tmp_path)`, `subprocess.run([sys.executable, str(SCRIPT_PATH)`) rather than going strictly by line number.

## Acceptance

`just test` exits 0 OR `.venv/bin/pytest tests/ --tb=no -q --no-header 2>&1 | grep -E "^(ERROR|FAILED) " | grep -v "tests/test_log_invocation_perf\.py" | wc -l` equals 0. All 8 in-scope test files (Tasks 1–8) pass when run individually via direct pytest invocation. The repo-wide grep `grep -rnE "cache_key = \(id\(tmp_path\)" tests/` returns no matches. No production-side files modified outside `cortex_command/dashboard/tests/` and the auto-regenerated plugin mirrors under `plugins/*/(skills|hooks|bin)/`.
