# Specification: build-daytime-pipeline-module-and-cli

## Problem Statement

The overnight pipeline executes features in batches, but users often need a single feature executed today — not in the next overnight window. Before #075 and #076 extracted `feature_executor` and `outcome_router` from `batch_runner.py`, building a daytime driver would have required duplicating ~700 LOC of orchestration glue. With those modules now extracted, a thin daytime driver (~150 LOC) can invoke the same dispatch, merge, review, and recovery logic that overnight uses, with zero duplication. This ticket builds that driver. Users benefit by being able to execute `python3 -m claude.overnight.daytime_pipeline --feature <slug>` and get a feature merged by end of day, with the same test-gate and auto-revert safety net as overnight.

## Requirements

1. **(M)** **CLI entry point**: Module `claude/overnight/daytime_pipeline.py` is invocable as `python3 -m claude.overnight.daytime_pipeline --feature <slug>`.
   Acceptance: `python3 -m claude.overnight.daytime_pipeline --help` exits 0 and output contains `--feature`.

2. **(M)** **CWD enforcement**: CLI aborts with a clear error if `lifecycle/` directory does not exist in CWD.
   Acceptance: Running from `/tmp` produces exit code 1 and stderr containing "must be run from the repo root" (or equivalent).

3. **(M)** **Feature execution**: Calls `feature_executor.execute_feature(feature, worktree_path, config)` and drives it through to completion, using the plan at `lifecycle/{feature}/plan.md`.
   Acceptance: Interactive/session-dependent — verified via manual acceptance test on a small feature that has a complete plan.md.

4. **(M)** **Per-feature events.log**: All event writes land in the main repo's `lifecycle/{feature}/events.log`, not inside the worktree.
   Acceptance: After a run, `grep -c '"event"' lifecycle/{feature}/events.log` ≥ 1 in the main repo CWD; `ls .claude/worktrees/{feature}/lifecycle/` does not exist (or is absent).

5. **(M)** **Per-feature deferred files (DR-4)**: Deferrals written to `lifecycle/{feature}/deferred/`, not to `deferred/` at repo root. Requires threading a `deferred_dir` keyword argument through **all six** deferral call sites in `feature_executor` (lines 250, 442, 497) and `outcome_router` (lines 633, 893, 957); `write_deferral()` in `deferral.py` already accepts this parameter.
   Acceptance: After a deferred run, `ls lifecycle/{feature}/deferred/` lists at least one `.md` file; `ls deferred/` does not contain the feature's deferral files.

6. **(M)** **Backward-compatible deferral threading**: The `deferred_dir` parameter added to all six call sites uses `DEFAULT_DEFERRED_DIR` as its default — existing overnight call paths are unchanged.
   Acceptance: `just test` exits 0; new behavioral unit tests (added as part of Req 16) cover at least one deferral call site in each of `feature_executor` and `outcome_router` with a custom `deferred_dir` argument.

7. **(M)** **Auto-merge on success with test-gate**: After `execute_feature` returns `status="completed"`, driver calls `outcome_router.apply_feature_result`; on merge success the test gate runs; on gate failure the merge is auto-reverted (same as overnight).
   Acceptance: Interactive/session-dependent — manual acceptance test observes successful merge and test-gate pass; failure path triggers revert.

8. **(M)** **Per-feature state file**: Driver creates `lifecycle/{feature}/daytime-state.json` with all fields required by `load_state()` in `claude/overnight/state.py` — including `session_id`, `plan_ref`, `current_round`, `phase`, `started_at`, `updated_at`, and `features` — with `features[{feature}]` pre-populated as a minimal `OvernightFeatureStatus` (read `state.py` for the exact field set) so that `load_state()` succeeds and the conflict-recovery block in `feature_executor` is not short-circuited by `_fs is None`. The `phase` field must be `"executing"`.
   Acceptance: `python3 -c "from cortex_command.overnight.state import load_state; s=load_state('lifecycle/{feature}/daytime-state.json'); assert s.features.get('{feature}') is not None"` exits 0 after a run is started.

9. **(M)** **Dashboard isolation**: The per-feature state file is at `lifecycle/{feature}/daytime-state.json`, not at `lifecycle/overnight-state.json`. `config.overnight_state_path` points to the per-feature path so the shared overnight state is never touched or read.
   Acceptance: `ls lifecycle/overnight-state.json` is unmodified before and after a daytime run (or is absent if no overnight session has run).

10. **(M)** **Worktree + branch cleanup on all exit paths**: The `pipeline/{feature}` branch and `.claude/worktrees/{feature}/` directory are removed when the driver exits — on success, failure, deferred, and **paused** outcomes. Unlike overnight (which retains worktrees on pause for session re-entry), daytime has no re-entry mechanism; the driver must call `cleanup_worktree` explicitly after `apply_feature_result` returns, regardless of the feature's resulting status. Graceful exits (including Ctrl+C) are handled via `try/finally`; SIGKILL recovery requires Req 11–12 infrastructure.
    Acceptance: After pipeline exits (any path including paused), `git branch --list "pipeline/{feature}"` returns empty output; `ls .claude/worktrees/{feature}` returns non-zero exit code (directory absent). Note: SIGKILL crash scenario is an Interactive/session-dependent acceptance test.

11. **(S)** **PID file lifecycle**: PID file written to `lifecycle/{feature}/daytime.pid` before worktree creation; removed on clean exit.
    Acceptance: During a run, `cat lifecycle/{feature}/daytime.pid` contains a valid integer PID; after clean exit the file is absent.

12. **(S)** **Stale PID recovery**: If `lifecycle/{feature}/daytime.pid` exists and the recorded PID is dead (`os.kill(pid, 0)` raises `OSError`), driver cleans the stale worktree and PID file before starting a fresh run.
    Acceptance: Interactive/session-dependent — create a stale PID file with a dead PID and stale worktree; subsequent invocation proceeds without error.

13. **(S)** **Concurrent same-feature guard**: If `lifecycle/{feature}/daytime.pid` exists and the recorded PID is alive, driver refuses to start with exit code 1 and a message naming the running PID.
    Acceptance: `python3 -m claude.overnight.daytime_pipeline --feature slug` exits 1 and stderr contains "already running" when a live daytime process exists for that feature.

14. **(S)** **macOS orphan prevention**: Subprocess (if applicable) polls `os.getppid() == 1` at 1-second cadence in a background task; on parent death, attempts cleanup and exits within 2 seconds.
    Acceptance: Interactive/session-dependent — kill parent process, verify subprocess exits and worktree is cleaned up within ~5 seconds.

15. **(S)** **SIGKILL recovery**: On startup, if stale worktree exists (MERGE_HEAD present or lock files present), run recovery sequence: `git merge --abort` (if MERGE_HEAD present), remove `*.lock` files, `git worktree remove --force --force`, `git worktree prune`.
    Acceptance: Interactive/session-dependent — manually create worktree with MERGE_HEAD; subsequent invocation recovers and proceeds without error.

16. **(M)** **Unit tests**: Driver logic covered by unit tests that mock `feature_executor.execute_feature` and `outcome_router.apply_feature_result`. Additionally, behavioral tests for the `deferred_dir` threading must cover at least one call site in `feature_executor` and one in `outcome_router` with a custom `deferred_dir` argument (verifying the path is forwarded, not just that the default is unchanged).
    Acceptance: `just test` exits 0; `claude/overnight/tests/test_daytime_pipeline.py` exists and contains at least one test function; `claude/overnight/tests/` contains at least one test verifying `write_deferral` is called with a non-default `deferred_dir` in each modified module.

17. **(M)** **Plan.md required**: Driver checks for `lifecycle/{feature}/plan.md` before starting; if absent, exits 1 with a clear message.
    Acceptance: `python3 -m claude.overnight.daytime_pipeline --feature no-plan-feature` exits 1 and stderr contains "plan.md not found" (or equivalent).

## Non-Requirements

- Skill pre-flight integration — that is #079
- Changes to `batch_runner.py`, `orchestrator.py`, or any overnight session behavior — zero regression expectation
- Morning report changes
- Dashboard UI integration — daytime-state.json is intentionally not the shared overnight state file
- Multi-feature batch — overnight only; daytime is always single-feature
- Cross-repo features — V1 supports default repo only (`repo_path=None`)
- Interactive merge approval — driver auto-merges on success (same as overnight); users can interrupt with Ctrl+C before the merge step if they wish to review first
- `--recover` explicit flag — stale detection and recovery are automatic on startup
- Model or budget customization — V1 uses overnight defaults; agent tool allowlist is `["Read", "Write", "Edit", "Bash", "Glob", "Grep"]`
- Concurrent overnight + daytime protection — user controls scheduling; document as a known limitation
- **Concurrent same-feature daytime runs** — not supported until Req 11–13 ship; users must not launch two daytime instances for the same feature simultaneously; no system guard exists until Req 13 is implemented
- Daytime resume/re-entry for paused features — daytime always cleans up the worktree on exit regardless of pause status; there is no overnight-style session that can resume a paused daytime feature

## Edge Cases

- **No plan.md**: Driver exits 1 before worktree creation with "plan.md not found at lifecycle/{feature}/plan.md" message.
- **All plan tasks already checked (`[x]`)**: `execute_feature` returns `status="completed"` with no tasks run; driver proceeds to apply_feature_result → merge.
- **Stale PID, no worktree**: PID file points to dead PID; worktree does not exist. Recovery clears PID file and continues normally.
- **Stale PID, worktree present with MERGE_HEAD**: Full SIGKILL recovery sequence runs before new worktree creation.
- **Stale PID, worktree present with index.lock but no MERGE_HEAD**: Remove lock files, `git worktree remove --force --force`, continue.
- **Live PID for same feature**: Driver refuses to start (see Requirement 13).
- **Multiple concurrent daytime runs for different features**: Each has own per-feature state file, PID file, and worktree — no collision. Merge serialization is user-supervised.
- **Test gate failure after merge**: `apply_feature_result` auto-reverts via `git revert -m 1 --no-ff HEAD`; driver then calls `cleanup_worktree`; exits non-zero.
- **Deferred feature**: `execute_feature` returns `status="deferred"`; `apply_feature_result` writes deferral to `lifecycle/{feature}/deferred/`; driver calls `cleanup_worktree`; exits 0 with a clear message naming the deferral file.
- **Conflict in merge → feature paused**: `apply_feature_result` dispatches repair agent (Sonnet → Opus escalation); if repair fails, feature status is `paused`; driver calls `cleanup_worktree` explicitly (daytime has no re-entry path, unlike overnight); exits non-zero with a message naming the paused state and any deferral files written.
- **API rate limit or budget exhaustion**: `execute_feature` returns with appropriate error status; driver calls `cleanup_worktree`; exits non-zero and logs the reason.
- **Driver process killed (Ctrl+C) before merge**: `finally` block runs cleanup_worktree; PID file removed; branch deleted.
- **Driver process SIGKILLed during worktree creation**: Next invocation finds stale PID + existing worktree and runs recovery sequence (Req 12/15).
- **`lifecycle/{feature}/` directory does not exist**: Driver creates it (and the `deferred/` subdirectory) before starting; also writes `daytime-state.json` and `daytime.pid` there.

## Changes to Existing Behavior

- MODIFIED: `claude/overnight/feature_executor.py` — all three deferral call sites (lines 250, 442, 497) now accept `deferred_dir: Path = DEFAULT_DEFERRED_DIR`; all existing overnight call paths use the default, behavior unchanged.
- MODIFIED: `claude/overnight/outcome_router.py` — all three deferral call sites (lines 633, 893, 957) now accept `deferred_dir: Path = DEFAULT_DEFERRED_DIR`; all existing overnight call paths use the default, behavior unchanged.
- ADDED: `claude/overnight/daytime_pipeline.py` — new CLI module invocable as `python3 -m claude.overnight.daytime_pipeline`.
- ADDED: `claude/overnight/tests/test_daytime_pipeline.py` — unit tests for daytime driver logic and behavioral deferral threading tests.

## Technical Constraints

- **Module location**: `claude/overnight/daytime_pipeline.py` — `claude/lifecycle/` does not exist as a Python package. CLI invocation is `python3 -m claude.overnight.daytime_pipeline`, replacing the backlog item's stated `python3 -m claude.lifecycle.daytime_pipeline`.
- **CWD must equal repo root**: All path construction in `feature_executor` and `outcome_router` uses bare relative `Path(f"lifecycle/{feature}/...")` — no absolute-base derivation. The CWD enforcement check (Requirement 2) is the only guard.
- **`escalations_path` is hardcoded relative** in `feature_executor` and `outcome_router` (`Path("lifecycle/escalations.jsonl")`): this is a pre-existing constraint; CWD enforcement is the mitigation.
- **deferral.py already supports `deferred_dir`**: `write_deferral(question, deferred_dir=DEFAULT_DEFERRED_DIR)` accepts the parameter; only the six call sites in `feature_executor` and `outcome_router` need to thread it through.
- **`config.overnight_state_path`** must point to `lifecycle/{feature}/daytime-state.json` (not the shared overnight state) so the dashboard is not confused and concurrent per-feature runs don't collide.
- **`config.overnight_events_path`** must be an absolute path derived from `Path.cwd() / f"lifecycle/{feature}/events.log"` at startup. Subprocess CWD (the worktree) differs from main repo CWD.
- **OutcomeContext construction for single-feature**: `consecutive_pauses_ref=[0]`, `integration_worktrees={}`, `integration_branches={}`, `feature_names=[feature]`, `repo_path_map={feature: None}`, `recovery_attempts_map={feature: 0}`. Two behavior notes:
  - **Circuit-breaker is structurally inert in daytime**: threshold is 3 consecutive pauses; a single-feature run can reach at most 1 — the circuit-breaker branch in `apply_feature_result` will never fire. This is expected and intentional.
  - **One recovery cycle allowed**: `recovery_attempts_map={feature: 0}` permits exactly one complete Sonnet→Opus escalation per the inherited outcome routing logic. If daytime wants zero recovery cycles (fail-fast), set `recovery_attempts_map={feature: 1}` instead; the spec allows either; implementation decides based on user preference.
- **Asyncio subprocess pattern**: Use `asyncio.create_subprocess_exec` with `communicate()` (not `await proc.wait()` + `stdout=PIPE`). Use `start_new_session=True` to enable `os.killpg` on the process group.
- **`git -C <path>` is prohibited** by sandbox rules; use `cwd=` parameter in subprocess calls.
- **`preexec_fn` is thread-unsafe** in multi-threaded parents; orphan prevention uses polling (`os.getppid() == 1`) instead of `prctl(PR_SET_PDEATHSIG)`, which is also Linux-only.
- **Worktree naming**: `pipeline/{feature}` branch with collision detection (`-2`, `-3` suffixes) — reuses existing `create_worktree()` in `claude/pipeline/worktree.py`. No new hook changes required.
- **Worktree cleanup ownership**: The daytime driver is responsible for calling `cleanup_worktree` after `apply_feature_result` returns, on all outcome paths including paused. This differs from overnight where paused worktrees are retained for session re-entry. The difference must be implemented in the driver, not in `outcome_router`.
- **`_backlog_dir` global in outcome_router**: Not called by the daytime driver; backlog write-backs default to the repo's own `backlog/` directory, which is correct for daytime use.

## Resolved Decisions

- **Recovery cycle count**: `recovery_attempts_map={feature: 0}` — one Sonnet→Opus recovery cycle, matching overnight defaults. Rationale: consistency; user is not always watching and a single repair attempt is worth the latency.
