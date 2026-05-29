# Review: resolve-user-project-root-stops-at

## Stage 1: Spec Compliance

### Requirement 1
**Expected**: `_resolve_main_repo_root()` present (grep count = 1); resolver ordering is eager-worktree-detect — (a) env-first, (b) walk for `.git` FILE, parse via `_main_root_from_gitfile`, (b-guard) `cortex/`-existence check, (c) literal `_resolve_user_project_root()` fallback; pure-Python (no subprocess/rev-parse call in body); `commondir` referenced; returned path `.resolve()`-canonicalized.

**Actual**: `grep -c 'def _resolve_main_repo_root'` = 1. Body: (a) `os.environ.get("CORTEX_REPO_ROOT")` → `Path(env_root).resolve()` first; (b) walks CWD upward, on first `.git` that `is_file()` calls `_main_root_from_gitfile`; (b-guard) checks `(candidate / "cortex").is_dir()` before returning `candidate.resolve()`; (c) `return _resolve_user_project_root()`. A `.git` directory breaks the loop without entering (b). `_main_root_from_gitfile` is a pure-Python `commondir`-aware parse; `grep -nE 'subprocess|rev-parse'` returns only docstring mentions, no executable calls.

**Verdict**: PASS

**Notes**: The only `subprocess`/`rev-parse` occurrences are docstring string-literals. The `.git`-is-a-directory break correctly implements the #201 anti-leak boundary.

---

### Requirement 2
**Expected**: `_lock_path` and `_events_log_path` both call `_resolve_main_repo_root()`. `grep -c '_resolve_main_repo_root()'` ≥ 2. Neither calls `_resolve_user_project_root()` directly.

**Actual**: `grep -c '_resolve_main_repo_root()'` = 5. `_lock_path`: `root = _resolve_main_repo_root()`. `_events_log_path`: `root = _resolve_main_repo_root()`. Neither calls `_resolve_user_project_root()` directly.

**Verdict**: PASS

---

### Requirement 3
**Expected**: Req 1's step (c) is a literal `_resolve_user_project_root()` call (not an alias); `grep -c '_resolve_user_project_root'` ≥ 2.

**Actual**: `grep -c '_resolve_user_project_root'` = 5 (import + docstring/comment references + the literal `return _resolve_user_project_root()` fallback). Fallback is a literal call.

**Verdict**: PASS

**Notes**: The #241 R2 grandfather grep (≥ 2) is satisfied deterministically.

---

### Requirement 4
**Expected**: `tests/test_interactive_lock_sandbox.py::test_lock_write_from_worktree_cwd` passes (or skips cleanly) with no fixture/assertion changes; diff confined to docstrings.

**Actual**: In this environment `_sandbox_exec_can_apply()` returns False (nested Seatbelt), so the test skips cleanly — the documented dev behavior. The diff is strictly docstring-only: two docstring sections changed, zero changes to fixture construction, `subprocess.run` argv, or `assert` lines.

**Verdict**: PASS

**Notes**: On vanilla macOS CI (no ambient Seatbelt container) the test runs its subprocess against the installed wheel after merge — the patched code. The docstring-only diff invariance is fully confirmed.

---

### Requirement 5
**Expected**: With `CORTEX_REPO_ROOT` set, `_resolve_main_repo_root()` returns `Path(env).resolve()` without parsing `.git`. Unit test passes under `-k 'env'`.

**Actual**: `test_resolve_main_repo_root_env_first` patches `_main_root_from_gitfile` to raise if called, sets `CORTEX_REPO_ROOT`, asserts the resolver returns `tmp_path.resolve()`. Passes. Body returns immediately on env presence without entering the walk.

**Verdict**: PASS

**Notes**: The sentinel-patch proves env-first by output AND by proving no `.git` parse occurs.

---

### Requirement 6
**Expected**: No-`.git`, `cortex/`-bearing project → resolves via step-(c) walk, no exception.

**Actual**: `test_resolve_main_repo_root_no_git_cortex_fallback` builds a `proj/cortex/` with no `.git`, `chdir`s in, asserts `== proj.resolve()`. Passes.

**Verdict**: PASS

---

### Requirement 7
**Expected**: Hand-built real-worktree-shape fixture (worktree-CWD, co-located `cortex/`, `.git` file → `<main>/.git/worktrees/<id>`, relative `commondir: ../..`): (1) resolver == `<main>`; (2) `_lock_path("probe")` under `<main>/cortex/...`; (3) `acquire_lock` from worktree CWD writes to `<main>` AND `read_lock` from same CWD returns non-`None`.

**Actual**: `test_resolve_main_repo_root_worktree_with_cortex_resolves_to_main` uses `_build_worktree_skeleton(..., with_worktree_cortex=True)`: absolute `gitdir:` pointer, relative `commondir: ../..` (real git shape). All three assertions present and passing. No `git worktree add`.

**Verdict**: PASS

**Notes**: `commondir` is relative per critical-review concern R2-3. The structural guard covers all three spec-required assertions including writer/reader convergence.

---

### Requirement 8
**Expected**: `-k resolve_main_repo_root` collects ≥ 5 distinct-behavior cases, all passing.

**Actual**: 7 cases collected, all passing: collision (Req 7/8b), env-first (8c), no-git fallback (8d), synthetic-direct no-commondir (8a), malformed-gitdir fallback (8e), worktree-pointer no-cortex → raises (8e), bfail-degrades-to-local (Objection 1). Each a distinct branch.

**Verdict**: PASS

**Notes**: 7 > 5; no near-duplicates. Req 8b covered by the collision case as the plan states.

---

### Requirement 9
**Expected**: Three false-claim tokens absent (spec.md `resolves up to the main repo` = 0; sandbox.py `upward-walks` = 0; sandbox.py `ultimately resolving the main-repo root` = 0); sandbox.py names `_resolve_main_repo_root` ≥ 1.

**Actual**: Greps return 0, 0, 0, 2 respectively. The #241 spec now reads that `_resolve_user_project_root()` does **not** ascend; main anchoring comes from `interactive_lock._resolve_main_repo_root()` (#271). Both sandbox-test docstrings name `_resolve_main_repo_root`. Diff is docstring-only.

**Verdict**: PASS

---

### Requirement 10
**Expected**: Module docstring states the acquire/read/inspect/force-release main-root guarantee, why the resolver is separate, names the structural-guard test, notes `scan_live_locks`' `CORTEX_REPO_ROOT` env-pin. `grep -c 'main repo root'` ≥ 1.

**Actual**: `grep -c 'main repo root'` = 3. Module docstring: (a) acquire/read/inspect/force-release converge on the main repo root via `_resolve_main_repo_root()`; (b) why separate from `common._resolve_user_project_root`; (c) names `test_resolve_main_repo_root_worktree_with_cortex_resolves_to_main` as the structural guard; (d) `scan_live_locks` is the deliberate exception via the overnight env-pin. Both symbols named.

**Verdict**: PASS

---

### Requirement 11
**Expected**: `just test` exits 0.

**Actual**: From inside the worktree under the Claude command-sandbox, `test_interactive_lock.py` = 17 passed, sandbox test skips cleanly. A literal `just test` exit-0 cannot be obtained from inside a worktree due to three execution-context artifacts (confirmed in plan Task 5): `test_runner_pr_gating.py` (sandbox blocks `git write-tree`), `test_worktree_seatbelt.py` (`.git` is a file in a worktree), `test_handler_ensure.py`/`test_init_ensure.py` (`cortex init --ensure` F9 worktree-refusal) — all in files this feature does not touch. All resolver-adjacent tests pass green, including `test_common_utils.py::test_resolve_user_project_root_git_file_boundary_terminates_walk`.

**Verdict**: PASS (with worktree-context caveat as documented in plan Task 5; canonical run on primary checkout post-merge)

---

## Requirements Drift

**State**: none
**Findings**:
- None
**Update needed**: None

The implementation is purely additive to `interactive_lock.py` and its tests, plus two corrective docstring edits. No change to `common.py`, no new architectural constraint, no new status vocabulary, no new ADR trigger. project.md constraints (pure-Python resolver, no subprocess, file-based state per ADR-0001, Path-segment joining, module boundaries) are respected.

## Stage 2: Code Quality

- **Naming conventions**: Consistent. `_main_root_from_gitfile` follows the module's underscore-private helper convention; `_resolve_main_repo_root` mirrors `common._resolve_user_project_root` in naming and `() -> Path` signature.
- **Error handling**: Follows the module's defensive posture — `OSError` caught on file reads returning `None` (not raising); the `Optional[Path]` return signals the None-on-failure contract; the caller's `if candidate is not None and (candidate / "cortex").is_dir()` guard is idiomatic.
- **Test coverage**: All plan verification steps met. The `gitdir:`/`commondir` parse math is correct across all exercised shapes (real-worktree relative `commondir`, synthetic-direct no-commondir, malformed/empty, OSError). No self-sealing tests: `env_first` patches `_main_root_from_gitfile` to assert non-invocation; the collision guard fails on any walk-first impl; `bfail_inside_worktree_degrades_to_local` pins the documented degradation. One minor coverage note: the relative-`gitdir:` branch (`if not git_dir.is_absolute()`) is correct but not directly fixture-exercised (the helper uses an absolute `gitdir:`); this does not affect any requirement's acceptance criterion.
- **Pattern consistency**: Matches existing module/test conventions (tmp_path + monkeypatch fixtures, `il.` prefix, defensive parsing). `git_dir.resolve()` is correctly applied before the `commondir` lookup so the relative `commondir` anchors against canonical `$GIT_DIR`. Symlinks are not special-cased; the submodule case is eliminated by the (b-guard) per the spec's edge-case note.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
