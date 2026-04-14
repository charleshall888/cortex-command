# Plan: build-daytime-pipeline-module-and-cli

## Overview

Thread `deferred_dir` backward-compatibly through six call sites in `feature_executor` and `outcome_router`, then build `daytime_pipeline.py` as a thin async CLI driver (~150 LOC) that constructs a `BatchConfig + OutcomeContext` for single-feature execution, manages a PID file and per-feature state JSON, and delegates to the existing `execute_feature → apply_feature_result → cleanup_worktree` pipeline. Tasks 1 and 2 are independent and can run in parallel; Tasks 3–5 follow sequentially.

## Tasks

### [x] Task 1: Thread deferred_dir through feature_executor.py (3 call sites)

- **Files**: `claude/overnight/feature_executor.py`
- **What**: Add `deferred_dir: Path = DEFAULT_DEFERRED_DIR` to `_handle_failed_task` and `execute_feature`; update the three `write_deferral()` call sites at lines 250, 442, and 497 to pass the new keyword arg; forward the param through the `_handle_failed_task` invocation at line 664. Add `DEFAULT_DEFERRED_DIR` to the existing deferral import block.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Import addition: line 38 imports from `claude.overnight.deferral`; add `DEFAULT_DEFERRED_DIR` to that import
  - `_handle_failed_task` signature (line 180): `async def _handle_failed_task(feature, task, all_tasks, spec_excerpt, retry_result, consecutive_pauses_ref, manager=None, round=0, log_path=..., *, deferred_dir: Path = DEFAULT_DEFERRED_DIR) -> Optional[FeatureResult]`
  - `execute_feature` signature (line 345): add `deferred_dir: Path = DEFAULT_DEFERRED_DIR` as a trailing keyword-only argument
  - `write_deferral(deferral)` at line 250 → `write_deferral(deferral, deferred_dir=deferred_dir)`
  - `write_deferral(_deferral)` at line 442 → `write_deferral(_deferral, deferred_dir=deferred_dir)`
  - `write_deferral(_deferral)` at line 497 → `write_deferral(_deferral, deferred_dir=deferred_dir)`
  - `_handle_failed_task(...)` call at line 664: add `deferred_dir=deferred_dir` as a keyword argument
- **Verification**: `just test` — pass if exit 0, all tests pass (overnight callers use the default, so behavior is unchanged)

---

### [x] Task 2: Thread deferred_dir through outcome_router.py (3 call sites)

- **Files**: `claude/overnight/outcome_router.py`
- **What**: Add `deferred_dir: Path = DEFAULT_DEFERRED_DIR` to `_apply_feature_result` (sync, line 433) and `apply_feature_result` (async, line 760); update the three `write_deferral()` call sites at lines 633, 893, and 957 to pass the new keyword arg; forward the param through all four `_apply_feature_result` internal call sites (lines 784, 797, 978, 984). Add `DEFAULT_DEFERRED_DIR` to the existing deferral import block.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Import: `write_deferral` is imported at line 32; extend to include `DEFAULT_DEFERRED_DIR`
  - `_apply_feature_result` signature (line 433): add `deferred_dir: Path = DEFAULT_DEFERRED_DIR` after `ctx`
  - `apply_feature_result` signature (line 760): add `*, deferred_dir: Path = DEFAULT_DEFERRED_DIR` — keyword-only, after `ctx`
  - `write_deferral(deferral)` at line 633 → `write_deferral(deferral, deferred_dir=deferred_dir)`
  - `write_deferral(deferral)` at line 893 → `write_deferral(deferral, deferred_dir=deferred_dir)`
  - `write_deferral(deferral)` at line 957 → `write_deferral(deferral, deferred_dir=deferred_dir)`
  - `_apply_feature_result(name, result, ctx)` at lines 784, 797, 978, 984 → add `deferred_dir=deferred_dir` kwarg to all four calls
- **Verification**:
  - `just test` — pass if exit 0
  - `grep -c "deferred_dir=deferred_dir" claude/overnight/outcome_router.py` — pass if count ≥ 7 (3 write_deferral + 4 _apply_feature_result)

---

### [x] Task 3: daytime_pipeline.py — startup helpers and BatchConfig factory

- **Files**: `claude/overnight/daytime_pipeline.py`
- **What**: Create the module with all startup-layer functions: CWD guard, PID file I/O and liveness check, SIGKILL recovery sequence, and a `build_config` factory that constructs a `BatchConfig` pointing to per-feature paths and writes the initial `daytime-state.json`. No execution logic in this task.
- **Depends on**: none
- **Complexity**: complex
- **Context**:
  - Module path: `claude/overnight/daytime_pipeline.py` — sibling to `feature_executor.py` and `outcome_router.py`
  - `_check_cwd() -> None`: `if not Path("lifecycle").is_dir(): sys.stderr.write("error: must be run from the repo root (lifecycle/ directory not found)\n"); sys.exit(1)`
  - `_pid_path(feature: str) -> Path`: `Path(f"lifecycle/{feature}/daytime.pid")`
  - `_read_pid(pid_path: Path) -> Optional[int]`: reads file; returns int or None on absence/parse error
  - `_is_alive(pid: int) -> bool`: `os.kill(pid, 0)` — return True on success or PermissionError (alive, not owned); return False on OSError with errno.ESRCH (dead)
  - `_write_pid(pid_path: Path) -> None`: ensures the parent directory exists (creating it recursively if needed), then writes the current process's PID as a string to `pid_path`
  - `_worktree_path(feature: str) -> Path`: `Path(".claude") / "worktrees" / feature`
  - `_recover_stale(feature: str, worktree_path: Path) -> None`: aborts any in-progress merge (if `MERGE_HEAD` exists in the worktree), removes all `.lock` files under the worktree, force-removes the worktree via `git worktree remove --force --force`, then prunes the worktree list via `git worktree prune`; all git subprocess calls pass `cwd=worktree_path` (not `-C`); see the SIGKILL recovery sequence in `lifecycle/build-daytime-pipeline-module-and-cli/research.md` for the full rationale and ordering
  - `build_config(feature: str, cwd: Path, session_id: str) -> BatchConfig`:
    - Reads `test_command` from `lifecycle.config.md` if present (key: `test-command:`); defaults to `"just test"`
    - Constructs `BatchConfig(batch_id=1, plan_path=cwd / f"lifecycle/{feature}/plan.md", test_command=test_command, base_branch="main", overnight_state_path=cwd / f"lifecycle/{feature}/daytime-state.json", overnight_events_path=cwd / f"lifecycle/{feature}/events.log", result_dir=cwd / f"lifecycle/{feature}", pipeline_events_path=cwd / f"lifecycle/{feature}/pipeline-events.log")`
    - Then constructs `OvernightState(session_id=session_id, plan_ref=str(config.plan_path), current_round=1, phase="executing", features={feature: OvernightFeatureStatus(status="running", round_assigned=1)})` and calls `save_state(state, config.overnight_state_path)` to write `daytime-state.json`
    - Also calls `(cwd / f"lifecycle/{feature}/deferred").mkdir(parents=True, exist_ok=True)` to pre-create the deferred directory
    - Returns `config`
  - Required imports: `asyncio`, `os`, `subprocess`, `sys`, `time` from stdlib; `Path` from `pathlib`; `Optional` from `typing`; `BatchConfig`, `BatchResult` from `claude.overnight.batch_runner`; `OvernightState`, `OvernightFeatureStatus`, `save_state` from `claude.overnight.state`; `create_worktree`, `cleanup_worktree` from `claude.pipeline.worktree`; `execute_feature` from `claude.overnight.feature_executor`; `apply_feature_result`, `OutcomeContext` from `claude.overnight.outcome_router`; `DEFAULT_DEFERRED_DIR` from `claude.overnight.deferral`
- **Verification**: `python3 -c "from claude.overnight.daytime_pipeline import _check_cwd, _read_pid, _is_alive, _write_pid, _recover_stale, build_config; print('ok')"` — pass if output is `ok` and exit 0

---

### [x] Task 4: daytime_pipeline.py — execution loop + CLI

- **Files**: `claude/overnight/daytime_pipeline.py`
- **What**: Add async `run_daytime(feature: str) -> int` that orchestrates the full lifecycle (startup checks → PID write → worktree create → execute → route → cleanup), the orphan-prevention background task, and the CLI (`build_parser`, `_run`, `__main__` block).
- **Depends on**: [1, 2, 3]
- **Complexity**: complex
- **Context**:
  - `run_daytime(feature: str) -> int` (async):
    1. `_check_cwd()`
    2. Check `Path(f"lifecycle/{feature}/plan.md").exists()`; if not: stderr "error: plan.md not found at `lifecycle/{feature}/plan.md`"; return 1
    3. `cwd = Path.cwd()`; `pid_path = _pid_path(feature)`
    4. Check `_read_pid(pid_path)`:
       - alive → stderr "error: daytime already running for {feature} (PID {pid})"; return 1
       - dead → `_recover_stale(feature, _worktree_path(feature))` then `pid_path.unlink(missing_ok=True)`
       - None (absent) → continue
    5. `_write_pid(pid_path)` — must happen before worktree creation
    6. `session_id = os.environ.get("LIFECYCLE_SESSION_ID") or f"daytime-{feature}-{int(time.time())}"`
    7. `config = build_config(feature, cwd, session_id)`
    8. `deferred_dir = cwd / f"lifecycle/{feature}/deferred"`
    9. `worktree_info = create_worktree(feature)`
    10. Build `OutcomeContext`:
        ```
        ctx = OutcomeContext(
            batch_result=BatchResult(batch_id=1),
            lock=asyncio.Lock(),
            consecutive_pauses_ref=[0],
            recovery_attempts_map={feature: 0},   # one Sonnet→Opus cycle
            worktree_paths={feature: worktree_info.path},
            worktree_branches={feature: worktree_info.branch},
            repo_path_map={feature: None},
            integration_worktrees={},
            integration_branches={},
            session_id=session_id,
            backlog_ids={feature: None},
            feature_names=[feature],
            config=config,
        )
        ```
    11. Orphan-prevention guard (background asyncio task before execute):
        - `_orphan_task = asyncio.create_task(_orphan_guard(feature, pid_path))` — store the reference so it can be cancelled in finally
        - `_orphan_guard(feature: str, pid_path: Path) -> None` (async): loops indefinitely, sleeping 1 second between iterations; on each wake checks whether the process has been orphaned (parent PID is 1); if orphaned, calls `cleanup_worktree(feature)`, removes `pid_path`, then calls `os._exit(1)` — **must use `os._exit`, not `sys.exit`**: `sys.exit` inside a coroutine raises `SystemExit` only within the task, the main coroutine continues unaffected
    12. Single `try/except/finally` block wrapping both execute and route calls:
        - try body: `result = await execute_feature(feature, worktree_info.path, config, deferred_dir=deferred_dir)` then `await apply_feature_result(feature, result, ctx, deferred_dir=deferred_dir)` — sequential in one try, not nested try statements
        - `except Exception as e`: write `f"error: daytime pipeline failed: {e}"` to stderr; return 1 — catches `raise RuntimeError` paths inside `apply_feature_result` (`_effective_merge_repo_path`, `recover_test_failure`) and prevents silent traceback exits
        - finally: `_orphan_task.cancel()` (suppress pending-task warnings on clean exit); `cleanup_worktree(feature)`; `pid_path.unlink(missing_ok=True)` — **the `finally` block is the sole cleanup owner on CI-deferred paths**: `apply_feature_result` does NOT call `cleanup_worktree` on `ci_pending`/`ci_failing` outcomes; on merge-success paths it is a harmless second-call since `cleanup_worktree` is idempotent
    13. Return code: inspect `ctx.batch_result` — **`features_paused` and `features_deferred` are `list[dict]` with shape `{"name": ..., "error": ...}`, not `list[str]`**; `features_merged` IS `list[str]`:
        - `feature in ctx.batch_result.features_merged` → print "Feature {feature} merged successfully."; return 0
        - `any(d.get("name") == feature for d in ctx.batch_result.features_deferred)` → print path to deferral file from `lifecycle/{feature}/deferred/`; return 1
        - `any(d.get("name") == feature for d in ctx.batch_result.features_paused)` → print "Feature {feature} paused — worktree cleaned; check events.log for details."; return 1
        - otherwise (features_failed or unrecognized) → print error from `ctx.batch_result.features_failed` if present; return 1
  - `build_parser() -> argparse.ArgumentParser`: `prog="python3 -m claude.overnight.daytime_pipeline"`, add `--feature` (required, help="Feature slug to execute (e.g. my-feature)")
  - `_run() -> None`: `args = build_parser().parse_args(); sys.exit(asyncio.run(run_daytime(args.feature)))`
  - `if __name__ == "__main__": _run()`
- **Verification**:
  - `python3 -m claude.overnight.daytime_pipeline --help` — pass if exit 0 and output contains `--feature`
  - From `/tmp`: `python3 -m claude.overnight.daytime_pipeline --feature x 2>&1` — pass if output contains "must be run from the repo root"

---

### [x] Task 5: Unit tests

- **Files**: `claude/overnight/tests/test_daytime_pipeline.py`
- **What**: Write unit tests covering startup guards (CWD check, plan check, live PID guard, stale PID recovery), success/deferred/paused routing, and two behavioral deferred_dir threading tests (one for `feature_executor`, one for `outcome_router`) verifying the custom path is forwarded to `write_deferral`.
- **Depends on**: [1, 2, 4]
- **Complexity**: complex
- **Context**:
  - Use `unittest.IsolatedAsyncioTestCase` for async tests; mirror the `_make_ctx` factory pattern from `claude/overnight/tests/test_outcome_router.py`
  - CWD guard test: `monkeypatch` or `tmp_path` — run `run_daytime("feat")` from a directory without `lifecycle/`; assert returns 1 and stderr contains "must be run from the repo root"
  - Plan check test: create `lifecycle/feat/` directory in tmp_path but no `plan.md`; assert returns 1 and stderr contains "plan.md not found"
  - Live PID guard: write `lifecycle/feat/daytime.pid` with the current process's PID (guaranteed alive); assert `run_daytime("feat")` returns 1 and stderr contains "already running"
  - Stale PID recovery: write `lifecycle/feat/daytime.pid` with PID 99999 (guaranteed dead); patch `_recover_stale`, `create_worktree`, `execute_feature`, `apply_feature_result`; assert `run_daytime` proceeds past PID check (calls `_recover_stale` once)
  - Success routing: mock `execute_feature` returning `FeatureResult(name="feat", status="completed")`; mock `apply_feature_result` as `AsyncMock` that appends to `ctx.batch_result.features_merged`; assert `run_daytime` returns 0
  - Deferred_dir behavioral test for `feature_executor` (Req 6): patch `claude.overnight.feature_executor.write_deferral` as `MagicMock(return_value=Path("/custom/feat-q001.md"))`; call `execute_feature("feat", ..., deferred_dir=Path("/custom"))` with mocked brain that returns DEFER action; assert `write_deferral` was called with `deferred_dir=Path("/custom")`
  - Deferred_dir behavioral test for `outcome_router` (Req 6): patch `claude.overnight.outcome_router.write_deferral` as `MagicMock(...)`; call `apply_feature_result("feat", result_with_ci_error, ctx, deferred_dir=Path("/custom"))` where result triggers a CI-blocking deferral; assert `write_deferral` was called with `deferred_dir=Path("/custom")`
- **Verification**: `just test` — pass if exit 0; `grep -c "def test_" claude/overnight/tests/test_daytime_pipeline.py` — pass if count ≥ 7

---

## Verification Strategy

After all tasks complete, run the full acceptance sequence:
1. `just test` — exit 0, all tests pass, including `test_daytime_pipeline.py`
2. `python3 -m claude.overnight.daytime_pipeline --help` — exit 0, output contains `--feature`
3. From `/tmp`: `python3 -m claude.overnight.daytime_pipeline --feature x` — exit 1, stderr "must be run from the repo root"
4. From repo root with a feature that has no `plan.md`: exit 1, stderr "plan.md not found"
5. Interactive acceptance test (manual): run against a small feature with a complete `plan.md`; verify `lifecycle/{feature}/daytime-state.json` exists after startup; verify `lifecycle/{feature}/deferred/` exists; verify branch is cleaned up after completion

## Veto Surface

- **`build_config` reads `lifecycle.config.md` for `test_command`**: simpler to hardcode `"just test"` (it's in every project's config), but reading the config file is more portable. If the user prefers hardcoding, remove the `lifecycle.config.md` parse and use `"just test"` directly.
- **Return code on deferred**: returns 1. Could return 2 to distinguish deferred from failure. Kept at 1 to match the shell convention "non-zero = not fully successful."
- **`recovery_attempts_map={feature: 0}`**: one Sonnet→Opus recovery cycle — matches overnight defaults per user decision. Change to `{feature: 1}` for fail-fast if preference changes.
- **Backlog write-backs**: `apply_feature_result` writes back to `backlog/NNN-{feature}.md` on all outcomes (merged → `status: complete`, paused → `status: in_progress`, deferred → `status: backlog`). This is intentional for daytime (spec §Technical Constraints says it is correct). Key side-effect: a daytime defer demotes the item from `refined` to `backlog`, requiring `/refine` before overnight can pick it up again. If suppression is desired, the mechanism would need a flag added to `OutcomeContext` or `_write_back_to_backlog` — scope-boundary risk since that touches overnight-shared code.

## Scope Boundaries

- No changes to `batch_runner.py`, `orchestrator.py`, or any existing overnight session behavior
- No skill pre-flight integration (`#079`)
- No morning report changes
- No dashboard UI integration (`daytime-state.json` is not the shared overnight state)
- Multi-feature batch is overnight-only; daytime is always single-feature
- Cross-repo features not supported in V1 (`repo_path=None` throughout)
- No concurrent overnight + daytime guard — documented limitation; user controls scheduling
- Daytime resume/re-entry not supported; worktree always cleaned on exit
