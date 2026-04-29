# Review: resolve-cortex-commandbacklog-packaged-dispatch-dead-branch-in-bin-cortex-wrappers

## Stage 1: Spec Compliance

### Requirement 1: `cortex_command.backlog` is a real Python subpackage
- **Expected**: Move four modules into `cortex_command/backlog/`; package importable; legacy `backlog/*.py` files gone.
- **Actual**: `python3 -c "import cortex_command.backlog.{update_item,create_item,generate_index,build_epic_map}"` exits 0. The legacy `backlog/{update_item,create_item,generate_index,build_epic_map}.py` files are deleted (4/4 confirmed). `cortex_command/backlog/__init__.py` exists. The implementer's deviation #1 (preserving the existing `__init__.py` to keep `readiness.py` re-exports) is correct — the spec says "Create `cortex_command/backlog/__init__.py`" but the package already existed (with `readiness.py`); the four moved modules sit alongside `readiness.py`. This preserves the existing public re-exports of `is_item_ready`/`partition_ready` that `cortex_command/overnight/backlog.py` and `tests/test_backlog_readiness.py` depend on. Spec acceptance criteria are met regardless of whether `__init__.py` was created from scratch or augmented.
- **Verdict**: PASS

### Requirement 2: `_PROJECT_ROOT` shim is removed from moved modules
- **Expected**: No `sys.path.insert` or `_PROJECT_ROOT =` lines in the four moved modules.
- **Actual**: `grep -nE "sys\.path\.insert|_PROJECT_ROOT\s*=" cortex_command/backlog/*.py` produces no output.
- **Verdict**: PASS

### Requirement 3: Production callers use the packaged import path
- **Expected**: All `from backlog.<mod>` rewritten to `from cortex_command.backlog.<mod>`.
- **Actual**: `grep -rn "from backlog\.\|import backlog\." --include="*.py" cortex_command/ tests/` returns no output. `cortex_command/overnight/outcome_router.py:322-323` uses the packaged path; `cortex_command/overnight/tests/conftest.py:25-28` stubs `sys.modules["cortex_command.backlog.update_item"]`; `tests/test_backlog_worktree_routing.py` and `tests/test_build_epic_map.py` updated. The implementer's deviation #5 (also updating `tests/test_select_overnight_batch.py` to switch from `importlib.util.spec_from_file_location` to `from cortex_command.backlog import generate_index`, and `tests/test_build_epic_map.py` to use `python -m`) is correct — these were filesystem-path imports the spec's plan T2 had not enumerated, and leaving them broken would have failed Requirement 22.
- **Verdict**: PASS

### Requirement 4: `update_item.py` subprocess-launches `generate_index` via `python -m`
- **Expected**: No `generate_index.py` filesystem path lookup; `[sys.executable, "-m", "cortex_command.backlog.generate_index"]` invocation.
- **Actual**: `cortex_command/backlog/update_item.py:417` has the `python -m` invocation. `grep -nE "generate_index\.py" cortex_command/backlog/update_item.py` produces no output. The `_resolve_generate_index` helper has been deleted. The implementer's deviation #2 (also rewriting `create_item.py:134`'s subprocess call to use `python -m`) is correct — `create_item.py` had the same pattern and would have been silently broken post-move; the deviation is an internal-consistency necessity, not scope creep.
- **Verdict**: PASS

### Requirement 5: Four `[project.scripts]` entry points are registered
- **Expected**: All four entry points declared in `pyproject.toml`; each module exposes a `main()` callable with no arguments.
- **Actual**: `pyproject.toml:22-25` declares all four entry points pointing at `cortex_command.backlog.<mod>:main`. Each module has a `def main()` (parameterless except `build_epic_map.main(argv=None)` which still works because `argparse.parse_args(None)` reads `sys.argv`, and the entry-point invocation form `main()` is supported). The `which`-based manual acceptance is post-`uv tool install -e . --reinstall` and outside test scope — the spec correctly notes this. The dispatch test in R15 covers the equivalent without depending on the install.
- **Verdict**: PASS

### Requirement 6: Bash wrappers deleted (canonical + plugin mirrors)
- **Expected**: 8 wrappers gone (4 canonical + 4 plugin mirrors).
- **Actual**: `ls bin/cortex-update-item bin/cortex-create-backlog-item bin/cortex-generate-backlog-index bin/cortex-build-epic-map plugins/cortex-interactive/bin/cortex-update-item plugins/cortex-interactive/bin/cortex-create-backlog-item plugins/cortex-interactive/bin/cortex-generate-backlog-index plugins/cortex-interactive/bin/cortex-build-epic-map 2>&1 | grep -c "No such file"` returns 8.
- **Verdict**: PASS

### Requirement 7: `install_guard.check_in_flight_install()` moved into `_dispatch_upgrade` only
- **Expected**: Removed from `cortex_command/__init__.py:13-15`; added as first action of `_dispatch_upgrade`; not added to other handlers; `import cortex_command` no longer fires the guard.
- **Actual**: `cortex_command/__init__.py` has only a docstring + `from __future__ import annotations`; no `check_in_flight_install` reference. `cortex_command/cli.py:251-258` shows `_dispatch_upgrade` calling `check_in_flight_install()` as the first statement (after function-local imports for `os`, `subprocess`, `Path`). Global grep confirms the only production-code call site is `cli.py:258`. The latent-bug fix (overnight status no longer fires the guard) is verified by `test_overnight_status_does_not_fire_guard`.
- **Verdict**: PASS

### Requirement 8: `install_guard` carve-outs pruned
- **Expected**: pytest, runner-child, dashboard carve-outs and `_is_dashboard_initiator` removed; module docstring updated; only carve-outs (d) and (e) remain.
- **Actual**: `grep -cE "_is_dashboard_initiator|PYTEST_CURRENT_TEST|CORTEX_RUNNER_CHILD" cortex_command/install_guard.py` = 0. The new docstring at lines 1-38 describes the opt-in-by-callers shape and lists only `CORTEX_ALLOW_INSTALL_DURING_RUN` and the cancel-bypass. The implementer's deviation #3 (collapsing `_check_in_flight_install_core` into `check_in_flight_install` since the only thing distinguishing them was the pytest carve-out) is correct — with the carve-out gone, the indirection has no purpose, and `tests/test_install_inflight_guard.py:42` was correctly updated to import the public function.
- **Verdict**: PASS

### Requirement 9: Audit `python -m cortex_command.<sub>` callsites and document classifications
- **Expected**: Audit document at `requirements/observability.md` under a new "Install-mutation invocations" subsection; each match classified as install-mutation or non.
- **Actual**: `requirements/observability.md` lines 122-146 contain a comprehensive `## Install-mutation invocations` subsection. It documents both the module-form and shell-form audit sweeps, classifies every current match (none are install-mutations), explicitly identifies `_dispatch_upgrade` as the only install-mutation site, and notes the stale-pointer self-heal warning narrowing from the spec's Edge Cases.
- **Verdict**: PASS

### Requirement 10: Audit existing CLI-invoking tests for guard interaction
- **Expected**: With pytest carve-out gone, no test that calls `cortex_command.cli.main()` should produce false-positive `InstallInFlightError`.
- **Actual**: `grep -rn "cortex_command\.cli\.main\|from cortex_command\.cli import main" --include="*.py" cortex_command/ tests/` returns three matches: two are documentation/test code in `test_install_guard_relocation.py`, one is `cortex_command/overnight/cli_handler.py` (production code). The new `test_install_guard_relocation.py` correctly fixtures `_ACTIVE_SESSION_PATH` for both invoking tests (`test_upgrade_fires_guard`, `test_overnight_status_does_not_fire_guard`). The audit pre-conditions from plan T6's context (no test-file invokers in current tree) plus the new tests' explicit fixturing both hold.
- **Verdict**: PASS

### Requirement 11: Parity linter merges `[project.scripts]` symmetrically + self-test fixture
- **Expected**: `gather_deployed()` unions `bin/` files with `[project.scripts]` keys; W005 stays scoped to `bin/`-discovered commands only; new self-test fixture for entry-point orphan W003.
- **Actual**: `bin/cortex-check-parity:189-217` shows `gather_deployed` unioning bin/ contents with `gather_entry_point_names()`. The wired-set construction for E001/E002 at `lint()` works through the same `referenced` dictionary so entry-point references resolve symmetrically. The new self-test case `invalid-entry-point-orphan` at line 946-978 fixtures a synthetic `pyproject.toml` declaring `cortex-orphan-test`, asserts gather_deployed surfaces it AND that `lint()` produces W003. `python3 bin/cortex-check-parity --self-test` exits 0 with all 16 cases passing. `python3 bin/cortex-check-parity` exits 0 against the post-change tree.
- **Verdict**: PASS

### Requirement 12: Telemetry helper byte-equivalent to bash shim, fail-open, JSONL
- **Expected**: `cortex_command/backlog/_telemetry.py` mirrors `bin/cortex-log-invocation` byte-for-byte; 5 fail-open categories; called from each module's `main()` first.
- **Actual**: Read both implementations side-by-side:
  - **Field shape**: Both emit `{"ts":"<ISO 8601 Z>","script":"<name>","argv_count":<int>,"session_id":"<id>"}\n`.
  - **Field order**: bash uses `printf '{"ts":"%s","script":"%s","argv_count":%d,"session_id":"%s"}\n'` (lines 60-61). Python builds an ordered dict at lines 112-117 with keys in identical order, serializes via `json.dumps(record, separators=(",", ":"), ensure_ascii=False)` + trailing `"\n"` (line 118). Python 3.7+ guarantees dict insertion order; `separators=(",", ":")` produces no spaces; `ensure_ascii=False` prevents `\uXXXX` escapes; `json.dumps` does not escape `/`. Bytes match.
  - **5 fail-open categories**: bash emits `no_session_id` (line 28), `no_repo_root` (line 34), `session_dir_missing` (line 41), `write_denied` (line 64), `other` (lines 53, also implicit on any `printf` failure). Python emits identical strings at lines 82, 87, 96, 125, 105 (and 128 for outer-`Exception`). Match.
  - **Quote/backslash skip**: bash `case "$script_name$LIFECYCLE_SESSION_ID" in *\"*|*\\*) ... other` (lines 51-56). Python at lines 104-106 mirrors the same skip with category `other`. Match.
  - **All four `main()` calls log_invocation first**: `update_item.py:434`, `create_item.py:146`, `generate_index.py:284`, `build_epic_map.py:200` — verified by `cortex-invocation-report --check-entry-points` exit 0.
  - **Byte-equivalence test**: `cortex_command/backlog/tests/test_telemetry_byte_equivalence.py` is a real subprocess-vs-Python test that creates an isolated git repo, sets `LIFECYCLE_SESSION_ID`, invokes the bash shim and the Python helper with matching argv, and compares output bytes after normalizing only the `ts` field. The test asserts both that the byte sequences match AND the schema is `{ts, script, argv_count, session_id}` with the expected field values. The test passes.
- **Verdict**: PASS

### Requirement 13: Pre-commit gate enforces telemetry-call presence in entry-point modules
- **Expected**: New `--check-entry-points` mode (or `--check-shims` extension) wired into pre-commit Phase 1.6/adjacent.
- **Actual**: `bin/cortex-invocation-report:125-172` defines `_check_entry_points()` as a sibling to `_check_shims()`. It walks the four modules, awk-extracts the first non-blank/non-comment/non-docstring line of each `def main()`, and asserts it begins with `_telemetry.log_invocation(`. `.githooks/pre-commit:117-141` defines a new Phase 1.7 that triggers `--check-entry-points` whenever any of the five entry-point or telemetry modules is staged. Manual run `bash bin/cortex-invocation-report --check-entry-points` exits 0 with "Checked 4 entry-point modules; 0 missing telemetry call."
- **Verdict**: PASS

### Requirement 14: Updated documentation references
- **Expected**: No `bin/cortex-{update-item,create-backlog-item,generate-backlog-index,build-epic-map}` references except in spec, lifecycle artifacts, the originating backlog ticket, and `lifecycle/archive/`.
- **Actual**: Audit grep shows residual matches only in lifecycle artifacts (`lifecycle/ship-dr-5.../research.md`, `lifecycle/extract-dev-epic-map.../research.md`, `lifecycle/extract-dev-epic-map.../review.md`, `lifecycle/extract-dev-epic-map.../plan.md`). All of these are within `lifecycle/<slug>/{research,spec,plan,review,index}.md` which the spec's acceptance criteria explicitly exempt. The `backlog/107-extract-dev-epic-map-parse-into-bin-build-epic-map.md` body was rewritten (T11 deletion of the `bin/cortex-build-epic-map` body reference confirmed). No live documentation paths reference the deleted bash wrappers.
- **Verdict**: PASS

### Requirement 15: Regression test for backlog entry-point dispatch
- **Expected**: `cortex_command/backlog/tests/test_dispatch.py` invokes each `main()` with `--help`, asserts dispatch + telemetry call.
- **Actual**: Test file uses `pytest.mark.parametrize` over the four (module, command-name) pairs, patches `module._telemetry.log_invocation` per-test, asserts `mock_log.call_count == 1` and `mock_log.call_args.args[0] == command_name`. The test does not depend on `uv tool install -e . --reinstall` — it imports modules directly and invokes their callables. Test passes.
- **Verdict**: PASS

### Requirement 16: Regression test that `import cortex_command` does not fire the guard
- **Expected**: A test under `cortex_command/tests/test_install_guard_relocation.py` proving `import cortex_command` succeeds with a faked-live active-session pointer.
- **Actual**: `test_import_does_not_fire_guard` at line 104 stages a live in-flight pointer via `_setup_live_inflight`, then opens `cortex_command.__file__` and asserts `"check_in_flight_install" not in init_text`. This is a structural assertion (the import-time fire is impossible if the call site doesn't exist in `__init__.py`). It is the strongest version of the test the constraint allows — re-importing `cortex_command` in a single-process test cannot exercise `__init__.py` a second time. Test passes.
- **Verdict**: PASS

### Requirement 17: Regression tests for `cortex upgrade` firing guard + `cortex overnight status` not firing guard
- **Expected**: `test_upgrade_fires_guard` proves the guard fires from `_dispatch_upgrade`; `test_overnight_status_does_not_fire_guard` proves the latent-bug fix.
- **Actual**: Both tests in `test_install_guard_relocation.py`. `test_upgrade_fires_guard` (line 135) stages a live pointer, sets argv to `["cortex", "upgrade"]`, stubs `subprocess.run` defensively, calls `cli.main(["upgrade"])`, and asserts `SystemExit(1)` AND that `subprocess.run` was never called (proving the guard fired BEFORE any install work). `test_overnight_status_does_not_fire_guard` (line 163) stages the same pointer, stubs `_dispatch_overnight_status`, calls `cli.main(["overnight", "status"])`, and asserts no exception + `rc == 0`. Both pass.
- **Verdict**: PASS

### Requirement 18: `testpaths` includes the new backlog tests directory
- **Expected**: `cortex_command/backlog/tests` added to `[tool.pytest.ini_options].testpaths`.
- **Actual**: `pyproject.toml:31` includes `"cortex_command/backlog/tests"` as the 6th element.
- **Verdict**: PASS

### Requirement 19: Implementation procedure — pre-stage `just build-plugin` before initial commit
- **Expected**: Documented procedural step.
- **Actual**: spec narrative includes `just build-plugin` in Implementation Procedure step 3. The fact that the commit succeeded with all 8 wrapper deletions co-staged is empirical proof the procedure was followed.
- **Verdict**: PASS

### Requirement 20: Implementation procedure — `uv tool install -e . --reinstall` after pyproject.toml edit
- **Expected**: Documented procedural step.
- **Actual**: Documented in spec Implementation Procedure step 2 and Technical Constraints. Reinstall affects the developer's local entry-point binaries only; the commit itself is independent of reinstall execution.
- **Verdict**: PASS

### Requirement 21: All file-level changes co-stage in one commit
- **Expected**: Single commit containing the move + import updates + pyproject + linter + telemetry + carve-out pruning + plugin-mirror deletions + new tests + doc updates + audit doc.
- **Actual**: `git log -1 --stat 3cdb2b6` shows 38 files changed, 991 insertions(+), 580 deletions(-) in a single commit. Every requirement's file change is present: 4 file moves (rename detected by git), 5 import-site updates, `pyproject.toml`, `bin/cortex-check-parity`, `bin/cortex-invocation-report`, `cortex_command/install_guard.py`, `cortex_command/__init__.py`, `cortex_command/cli.py`, 8 plugin-mirror deletions, 4 new test files, `requirements/observability.md`, `bin/.parity-exceptions.md`, `.githooks/pre-commit`, `backlog/107-...md`. Commit message describes all four bullet points.
- **Verdict**: PASS

### Requirement 22: All existing tests pass and pre-commit hooks pass
- **Expected**: `just test` exits 0; `.githooks/pre-commit` exits 0.
- **Actual**: `just test` reports "Test suite: 5/5 passed" (test-pipeline, test-overnight, test-init, test-install, tests). The commit was created cleanly (commit 3cdb2b6 is on `main`), implying the pre-commit gate passed at commit time.
- **Verdict**: PASS

### Edge Case: Stale-pointer self-heal warning narrowing
- **Expected**: Warning emits only from `_dispatch_upgrade`, never from `import cortex_command`.
- **Actual**: The warning code at `install_guard.py:191-198, 211-218` only runs inside `check_in_flight_install`, which now is only called from `_dispatch_upgrade`. The narrowing is documented in `requirements/observability.md` lines 146-147.
- **Verdict**: PASS

### Edge Case: `cortex overnight status` no longer fails (latent-bug fix)
- **Expected**: Read-only inspection during in-flight session no longer fires `InstallInFlightError`.
- **Actual**: Verified by `test_overnight_status_does_not_fire_guard`.
- **Verdict**: PASS

### Edge Case: `_telemetry.py` write failure
- **Expected**: Helper's fail-open guarantees the entry-point command still succeeds even if telemetry write fails.
- **Actual**: Code review of `_telemetry.py:79-129` confirms every code path is wrapped in `try/except Exception` plus a final outer `try/except Exception` that swallows everything. Breadcrumbs are best-effort. Test `test_dispatch.py` verifies `--help` invocations succeed under telemetry mock; the byte-equivalence test verifies the success path.
- **Verdict**: PASS

### Non-Requirement #1: Other 11 `bin/cortex-*` wrappers untouched — confirmed (commit only touches the four named).
### Non-Requirement #6: Allowlist schema not extended — confirmed (`bin/.parity-exceptions.md` keeps existing 5-column schema). Implementer's deviation #4 (adding a row for `cortex-batch-runner` with category `library-internal`) uses the existing schema and existing categories. The spec's Non-Requirement #6 only forbids extending the schema, not using the existing mechanism. The added rationale ("Entry-point binary spawned by cortex_command/overnight/runner.py via subprocess.Popen — wiring is in Python source, which is outside the scan-glob surface") is specific, ≥30 chars, and accurate (`runner.py:165` spawns `cortex-batch-runner` via subprocess and SCAN_GLOBS does not include `*.py` outside `tests/`). The deviation is correct — not adding the row would have left a W003 pre-existing false-positive in the linter against `cortex-batch-runner` (a maintainer-only path), which Requirement 22 would have failed.
### Non-Requirement #7: Two telemetry implementations remain physically separate — confirmed (`bin/cortex-log-invocation` is bash; `cortex_command/backlog/_telemetry.py` is Python; byte-equivalence is asserted, not enforced via shared code).

## Requirements Drift

**State**: none
**Findings**:
- None
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: Consistent. The `_telemetry` module follows the `_private` underscore-prefix convention for an internal helper. The four entry-point modules follow `def main() -> int` + `if __name__ == "__main__": sys.exit(main())` consistent with the rest of the codebase (`cortex_command.cli`, `cortex_command.overnight.batch_runner`). Breadcrumb category strings (`no_session_id`, `no_repo_root`, etc.) match the bash shim verbatim. Test naming follows project pattern (`test_<feature>_<scenario>`).
- **Error handling**: Appropriate. `_telemetry.log_invocation` has the correct fail-open contract — every code path is in try/except with breadcrumb categorization, plus a final outer `try/except Exception` swallow. The 5 categories match the bash shim semantically. The carve-out pruning in `install_guard.py` is clean — the docstring explains exactly what stays and what's removed. The byte-equivalence test creates an isolated git repo so failures in the bash shim are diagnosable. The `_check_entry_points` bash awk routine handles docstrings + comments + blank lines correctly (verified by reading the awk script).
- **Test coverage**: Sufficient. 4 dispatch tests + 1 byte-equivalence test + 3 install-guard relocation tests = 8 new tests across 3 files. The dispatch test asserts the load-bearing claim (each `main()` calls `log_invocation` with the right command name), the byte-equivalence test asserts the load-bearing claim (Python output bytes match bash output bytes), and the install-guard tests assert the three structural claims (import doesn't fire / upgrade does fire / overnight status doesn't fire). The parity linter's new `invalid-entry-point-orphan` self-test case covers Requirement 11's regression surface. The `--check-entry-points` pre-commit gate prevents future regressions of the telemetry-call-first invariant. One small gap: there is no test that the Python helper's breadcrumb output matches the bash shim's breadcrumb output byte-for-byte (only the JSONL output is byte-compared) — but this is below the spec's bar and breadcrumb output is best-effort by design.
- **Pattern consistency**: Strong. `def main() -> int` returning the exit code with `sys.exit(main())` at module bottom matches `cortex_command/cli.py` and `cortex_command/overnight/batch_runner.py`. The `from __future__ import annotations` opener is consistent with the codebase. Test fixtures use `pytest.MonkeyPatch` and `tmp_path` per project convention. The `_setup_live_inflight` helper in `test_install_guard_relocation.py` is structurally similar to the existing `live_inflight` fixture in `tests/test_install_inflight_guard.py:120-200`. The audit document in `requirements/observability.md` follows the same subsection-with-audit-grep pattern as the existing "Runtime Adoption Telemetry" subsection. Implementer's four deviations are all defensible: #1 preserves an existing public API surface; #2 keeps internal consistency; #3 simplifies a now-pointless indirection; #4 uses the existing allowlist mechanism for an existing W003 false-positive that the entry-point set-union exposed.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
