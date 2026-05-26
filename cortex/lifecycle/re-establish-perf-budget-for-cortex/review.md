# Review: re-establish-perf-budget-for-cortex

## Stage 1: Spec Compliance

### Requirement 1: Defer top-level Python imports and remove `subprocess`
- **Expected**: `datetime`, `json`, `pathlib` become function-scoped; `subprocess` removed from module entirely. Top-of-module imports reduce to `os`, `sys`.
- **Actual**: Top-of-module imports are `os`, `sys`, and `typing` only. `subprocess` is absent. `datetime` is function-scoped in `_utc_now_iso()`. `pathlib.Path` is function-scoped in `_log_breadcrumb()`, `_resolve_repo_root()`. `json` is function-scoped in `main()` after the early-return guard. The subprocess-absence probe exits 0.
- **Verdict**: PASS

### Requirement 2: Replace `git rev-parse` with pure-Python repo-root walk
- **Expected**: `_resolve_repo_root()` walks `[Path.cwd(), *Path.cwd().parents]` for a `.git` dir or file; `subprocess` call removed.
- **Actual**: `_resolve_repo_root()` (lines 64–91) imports `pathlib.Path` locally, then walks `[cwd, *cwd.parents]` checking both `git_marker.is_dir()` and `git_marker.is_file()`. No `subprocess` anywhere in the module. Parity test passes.
- **Verdict**: PASS

### Requirement 3: Reorder `main()` so `LIFECYCLE_SESSION_ID` check runs before heavy imports
- **Expected**: `LIFECYCLE_SESSION_ID` env-var check is the first executable statement after function entry, before any conditional `import` statement. The `no_session_id` early-return path must not pay for any deferred import that the breadcrumb itself does not use.
- **Actual (rework commit 44a64965)**: Line 108 is `session_id = os.environ.get("LIFECYCLE_SESSION_ID", "")` — first executable statement. Line 110 is `args = list(sys.argv[1:] if argv is None else argv)` — uses only `sys` (always top-level loaded, zero heavy-import cost). Lines 112–114 are `if not session_id: / _log_breadcrumb("no_session_id", "") / return 0` — the early-return guard. Line 116 is `import json` — after the guard. No `from pathlib import Path` appears anywhere in `main()`. The `no_session_id` path pays for zero heavy imports. Both the formal acceptance criterion ("first executable statement is the session-id check") and the normative text ("early-return path must not pay for any deferred import") are satisfied. Cycle-1 finding is fully resolved.
- **Verdict**: PASS

### Requirement 4: Reorder `bin/cortex-log-invocation` branches
- **Expected**: Branch order (a) force-source → (b) pyproject grep → (c) wheel probe → (d) exit-2. Branch (b) uses name-match grep, not file-presence. `bash -n` exits 0.
- **Actual**: Branch (a) force-source at line 13, branch (b) pyproject grep at line 21 using `grep -q '^name = "cortex-command"'` (name-match), branch (c) wheel probe at line 26, branch (d) exit-2 at line 31. `bash -n` exits 0.
- **Verdict**: PASS

### Requirement 5: Preserve `CORTEX_COMMAND_FORCE_SOURCE=1` semantics
- **Expected**: Force-source branch remains first, unchanged in behavior. Covered by existing parity test.
- **Actual**: Branch (a) is unchanged and first. All parity tests pass.
- **Verdict**: PASS

### Requirement 6: Regenerate plugin mirror
- **Expected**: `plugins/cortex-core/bin/cortex-log-invocation` matches `bin/cortex-log-invocation` byte-for-byte.
- **Actual**: `diff bin/cortex-log-invocation plugins/cortex-core/bin/cortex-log-invocation` exits 0. Files are identical.
- **Verdict**: PASS

### Requirement 7: Un-skip `test_log_invocation_fast_path_budget` with calibrated budgets
- **Expected**: `@pytest.mark.skip` removed. Budgets tight enough to detect a ~20ms regression. Spec recommends p50 ≤ 50ms, mean ≤ 60ms, p95 ≤ 80ms as starting point.
- **Actual**: No `@pytest.mark.skip` — only two appropriate `@pytest.mark.skipif` runtime-environment guards (bash shim absent; git absent). Budget constants are P50=50ms, MEAN=55ms, P95=65ms, each tighter than the spec's recommended maximums and giving ≥12ms headroom above the measured floor (~38ms p50/p95), sufficient to detect a ~20ms regression. Test passes on dev hardware.
- **Verdict**: PASS

### Requirement 8: Delete `test_log_invocation_fast_path_faster_than_slow`
- **Expected**: `grep -c "test_log_invocation_fast_path_faster_than_slow" tests/test_log_invocation_perf.py` = 0.
- **Actual**: Count is 0. Function is absent.
- **Verdict**: PASS

### Requirement 9: Parity test continues passing under extended fixtures
- **Expected**: `tests/test_cortex_log_invocation_parity.py` passes after Req 11 fixture extensions.
- **Actual**: All parity tests pass including the three new edge-case fixtures.
- **Verdict**: PASS

### Requirement 10: Header comment documents branch reorder rationale
- **Expected**: ≥3-line comment block at top of `bin/cortex-log-invocation` with literal substrings `wheel-probe cost` and `double Python boot`.
- **Actual**: Lines 3–9 contain an 8-line comment block. `grep -c 'wheel-probe cost'` = 1 (line 4). `grep -c 'double Python boot'` = 1 (line 7). Both substrings present.
- **Verdict**: PASS

### Requirement 11: Extend parity-test fixtures to bind walk invariants
- **Expected**: Three new test functions matching `test_.*_worktree_file`, `test_.*_env_var_honored`, `test_.*_no_repo_root_breadcrumb`. Each with binding assertions. All pass.
- **Actual**: `test_resolve_repo_root_worktree_file` (line 372), `test_resolve_repo_root_env_var_honored` (line 416), `test_resolve_repo_root_no_repo_root_breadcrumb` (line 477). Each has multiple `assert` statements binding the invariants. All three pass. Name patterns satisfy the acceptance-criteria greps.
- **Verdict**: PASS

### Requirement 12: Add structural ordering test for bash wrapper branches
- **Expected**: `test_bash_branch_order` function present; asserts pyproject-grep line < wheel-probe line.
- **Actual**: `tests/test_log_invocation_branch_order.py` contains `test_bash_branch_order` which reads `bin/cortex-log-invocation`, locates the pyproject anchor (`^name = "cortex-command"`) and wheel anchor (`import cortex_command.log_invocation"`), and asserts `pyproject_idx < wheel_idx`. Test passes.
- **Verdict**: PASS

### Requirement 13: Fix `_p95` percentile-rank computation
- **Expected**: Replace incorrect `int(0.95 * n) - 1` with correct nearest-rank formula using `math.ceil`. `grep -c 'math.ceil'` ≥ 1.
- **Actual**: `_p95` at line 76 is `sorted_samples[min(n - 1, int(math.ceil(0.95 * n)) - 1)]`. `math` imported at line 6. `grep -c 'math.ceil'` = 1.
- **Verdict**: PASS

---

## Requirements Drift

**State**: none
**Findings**: None
**Update needed**: None

---

## Stage 2: Code Quality

- **Req 3 rework correctness**: The `args` assignment at line 110 (between `session_id` and the early-return guard) uses only `sys.argv`, which is always loaded at module import time — zero marginal cost on the `no_session_id` path. The cycle-1 concern was exclusively about `import json` and `from pathlib import Path`; both are gone from the early-return path. The rework is minimal, correct, and introduces no new issues.
- **Naming conventions**: Consistent with project patterns throughout. No deviations observed.
- **Error handling**: Fail-open contract maintained on all paths. `_log_breadcrumb` is itself fail-open (catches `OSError`). No new exception-swallowing introduced.
- **Test coverage**: The structural test `test_log_invocation_main_session_id_check_first` continues to enforce the first-statement property. The deferred-imports test `test_log_invocation_no_top_level_heavy_imports` (via subprocess isolation) provides independent confirmation that no heavy import fires before the guard. Together they adequately bind Req 3 post-rework.
- **Pattern consistency**: Lazy-import pattern consistent with `_utc_now_iso` and `_log_breadcrumb` helpers in the same module. Branch ordering in the bash wrapper and plugin mirror sync follow established project conventions.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 2, "issues": [], "requirements_drift": "none"}
```
