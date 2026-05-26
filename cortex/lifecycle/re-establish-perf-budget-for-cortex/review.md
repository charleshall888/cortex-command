# Review: re-establish-perf-budget-for-cortex

## Stage 1: Spec Compliance

### Requirement 1: Defer top-level Python imports and remove `subprocess`
- **Expected**: `datetime`, `json`, `pathlib` become function-scoped; `subprocess` removed from module entirely. Acceptance: `python3 -c "import cortex_command.log_invocation; import sys; assert 'subprocess' not in sys.modules"` exits 0.
- **Actual**: Top-of-module imports are now only `os`, `sys`, and `typing`. `subprocess` is absent (`grep -c 'subprocess' cortex_command/log_invocation.py` = 0). `datetime` is function-scoped in `_utc_now_iso()`. `pathlib.Path` is function-scoped in `_log_breadcrumb()`, `_resolve_repo_root()`, and `main()`. `json` is function-scoped in `main()`. The subprocess-absence subprocess check exits 0.
- **Verdict**: PASS

### Requirement 2: Replace `git rev-parse` with pure-Python repo-root walk
- **Expected**: `_resolve_repo_root()` walks `[Path.cwd(), *Path.cwd().parents]` for a `.git` dir or file; `subprocess` call removed.
- **Actual**: Implementation at lines 64–91 walks `[cwd, *cwd.parents]` (where `cwd = Path.cwd()`), checking both `git_marker.is_dir()` and `git_marker.is_file()`. No `subprocess` anywhere in the module. Parity test passes (22/22 tests green).
- **Verdict**: PASS

### Requirement 3: Reorder `main()` so `LIFECYCLE_SESSION_ID` check runs before heavy imports
- **Expected**: `LIFECYCLE_SESSION_ID` env-var check is the first executable statement after function entry, before any conditional `import` statement. The `no_session_id` early-return path must not pay for any deferred import that the breadcrumb itself does not use.
- **Actual**: `session_id = os.environ.get("LIFECYCLE_SESSION_ID", "")` is indeed the first executable statement (line 108). However, `import json` (line 110) and `from pathlib import Path` (line 111) appear on the two lines immediately following that assignment, and the `if not session_id:` early-return check is not until line 115. The no-session-id path therefore pays for both `import json` and `from pathlib import Path` on every call where `LIFECYCLE_SESSION_ID` is unset. `json` is not used by `_log_breadcrumb()` (which does its own `from pathlib import Path` internally). The formal acceptance criterion — "first executable statement is the session-id check" — is satisfied, but the normative text — "early-return path must not pay for any deferred import that the breadcrumb itself does not use" — is violated. The AST structural test (`test_log_invocation_main_session_id_check_first`) only verifies the first-statement property; it does not catch the misplaced deferred imports.
- **Verdict**: PARTIAL
- **Notes**: Fix is straightforward: move the `import json` and `from pathlib import Path` in `main()` to after the `if not session_id: return 0` block (or inline them at their first use sites, as the pattern in `_utc_now_iso` and `_log_breadcrumb` demonstrates). The `from pathlib import Path` import in `main()` is also redundant — every codepath that uses `Path` in `main()` calls through to helpers that import it themselves, or goes through `_resolve_repo_root()` which imports it locally. Only `json` has a direct call site in `main()` (line 153). The no-session-id path currently pays ~30µs per invocation for two unnecessary imports; over the perf budget threshold the delta is below test resolution, but it defeats the stated design intent.

### Requirement 4: Reorder `bin/cortex-log-invocation` branches
- **Expected**: Branch order (a) force-source → (b) pyproject grep → (c) wheel probe → (d) exit-2. Branch (b) uses name-match grep, not file-presence. Acceptance: `bash -n bin/cortex-log-invocation` exits 0.
- **Actual**: Branch order is exactly (a) force-source (line 13), (b) pyproject grep (line 21), (c) wheel probe (line 26), (d) exit-2 (line 31). Branch (b) uses `grep -q '^name = "cortex-command"'` — name-match, not file-presence. `bash -n` exits 0.
- **Verdict**: PASS

### Requirement 5: Preserve `CORTEX_COMMAND_FORCE_SOURCE=1` semantics
- **Expected**: Force-source branch remains first, unchanged in behavior. Covered by existing parity test.
- **Actual**: Branch (a) is unchanged and first. The parity fixture test `force-source` exercises this path and all 22 parity tests pass.
- **Verdict**: PASS

### Requirement 6: Regenerate plugin mirror
- **Expected**: `plugins/cortex-core/bin/cortex-log-invocation` matches `bin/cortex-log-invocation` byte-for-byte. `diff` exits 0.
- **Actual**: `diff bin/cortex-log-invocation plugins/cortex-core/bin/cortex-log-invocation` exits 0. Files are identical.
- **Verdict**: PASS

### Requirement 7: Un-skip `test_log_invocation_fast_path_budget` with calibrated budgets
- **Expected**: `@pytest.mark.skip` removed. Budgets tight enough to detect a ~20ms regression. Spec recommends p50 ≤ 50ms, mean ≤ 60ms, p95 ≤ 80ms as starting point.
- **Actual**: The test has no `@pytest.mark.skip` — only two conditional `@pytest.mark.skipif` guards (bash shim absent; git absent), which are appropriate runtime-environment guards rather than deferrals. Budget constants are P50=50ms, MEAN=55ms, P95=65ms. Measured floor noted in docstring is ~38ms p50, ~40ms p95. All three budgets give ≥15ms headroom above floor, sufficient to detect a ~20ms regression. Test passes on dev hardware.
- **Verdict**: PASS

### Requirement 8: Delete `test_log_invocation_fast_path_faster_than_slow`
- **Expected**: `grep -c "test_log_invocation_fast_path_faster_than_slow" tests/test_log_invocation_perf.py` = 0.
- **Actual**: Count is 0. Function is absent.
- **Verdict**: PASS

### Requirement 9: Parity test continues passing under extended fixtures
- **Expected**: `tests/test_cortex_log_invocation_parity.py` passes after Req 11 fixture extensions.
- **Actual**: All 22 parity tests pass (16 existing parametrized + 3 new edge-case + 3 new parity edge fixtures totalling 22 collected tests, all green).
- **Verdict**: PASS

### Requirement 10: Header comment documents branch reorder rationale
- **Expected**: ≥3-line comment block at top of `bin/cortex-log-invocation` containing literal substrings `wheel-probe cost` and `double Python boot`. `grep -c` ≥ 1 for each.
- **Actual**: Lines 3–9 contain an 8-line comment block explaining the branch ordering rationale. `grep -c 'wheel-probe cost' bin/cortex-log-invocation` = 1 (line 4). `grep -c 'double Python boot' bin/cortex-log-invocation` = 1 (line 7). Both substrings present.
- **Verdict**: PASS

### Requirement 11: Extend parity-test fixtures to bind walk invariants
- **Expected**: Three new test functions: `test_.*_worktree_file`, `test_.*_env_var_honored`, `test_.*_no_repo_root_breadcrumb`. Each with an `assert` binding the invariant. All three pass.
- **Actual**: `test_resolve_repo_root_worktree_file` (line 372), `test_resolve_repo_root_env_var_honored` (line 416), `test_resolve_repo_root_no_repo_root_breadcrumb` (line 477). Each has multiple `assert` statements binding the stated invariants. All three pass. Name patterns satisfy the acceptance-criteria greps (`_worktree_file`, `_env_var_honored`, `_no_repo_root_breadcrumb` present as substrings).
- **Verdict**: PASS

### Requirement 12: Add structural ordering test for bash wrapper branches
- **Expected**: `test_bash_branch_order` function in `tests/test_log_invocation_branch_order.py` or `tests/test_log_invocation_perf.py`. Test asserts pyproject-grep line < wheel-probe line.
- **Actual**: `tests/test_log_invocation_branch_order.py` contains `test_bash_branch_order` which reads `bin/cortex-log-invocation`, finds the pyproject anchor (`^name = "cortex-command"`) and wheel anchor (`import cortex_command.log_invocation"`), and asserts `pyproject_idx < wheel_idx`. Test passes.
- **Verdict**: PASS

### Requirement 13: Fix `_p95` percentile-rank computation
- **Expected**: Replace `int(0.95 * n) - 1` with a correct nearest-rank formula using `math.ceil`. `grep -c 'math.ceil' tests/test_log_invocation_perf.py` ≥ 1.
- **Actual**: `_p95` implementation at line 76 is `sorted_samples[min(n - 1, int(math.ceil(0.95 * n)) - 1)]`. `math` is imported at line 6. `grep -c 'math.ceil'` = 1.
- **Verdict**: PASS

---

## Requirements Drift

**State**: none
**Findings**:
- None
**Update needed**: None

---

## Stage 2: Code Quality

- **Naming conventions**: Consistent with project patterns. Helper functions use `_` prefix for private scope. Test function names match the `test_<subject>_<invariant>` convention used elsewhere in the suite. Constants are UPPER_SNAKE_CASE. No deviations observed.
- **Error handling**: Fail-open contract maintained. `_log_breadcrumb` is itself fail-open (catches `OSError`, returns silently). `_resolve_repo_root()` returns `None` on failure and the caller handles it. No new exception-swallowing introduced.
- **Test coverage**: 22 targeted tests pass across parity, imports discipline, branch ordering, and perf budget. The three new fixture variants (`worktree_file`, `env_var_honored`, `no_repo_root_breadcrumb`) each contain multiple binding assertions rather than mere function-name presence. The `_p95` fix and `test_log_invocation_fast_path_budget` un-skip are confirmed active. One gap noted: the `test_log_invocation_main_session_id_check_first` AST test checks only the first-statement property, not the relative ordering of deferred imports vs. the early-return guard — the partial compliance on Req 3 is therefore not caught by the structural test.
- **Pattern consistency**: Lazy-import pattern follows the established convention in `cortex_command/interactive_lock.py` and `cortex_command/cli.py`. Branch ordering in the bash wrapper follows the existing force-source / working-tree / wheel / exit-2 structure. Plugin mirror sync matches the dual-source enforcement pattern documented in CLAUDE.md.

## Verdict

```json
{"verdict": "CHANGES_REQUESTED", "cycle": 1, "issues": ["Req 3 PARTIAL: import json and from pathlib import Path in main() appear before the if not session_id early-return (lines 110-111 before line 115). The no_session_id path unnecessarily pays for both imports on every call where LIFECYCLE_SESSION_ID is unset, violating the spec's normative text: 'early-return path must not pay for any deferred import that the breadcrumb itself does not use'. Fix: move the import json and from pathlib import Path statements to after the if not session_id: return 0 block, or inline them at first use."], "requirements_drift": "none"}
```
