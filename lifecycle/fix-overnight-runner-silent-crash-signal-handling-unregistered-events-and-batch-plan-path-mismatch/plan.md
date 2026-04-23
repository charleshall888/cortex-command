# Plan: fix-overnight-runner-silent-crash

## Overview

Build the test infrastructure and validation layer first — event type registration, REPO_ROOT testability guard, and regression test — so the safety net is in place before any production code changes. Then make the production fixes (signal trap, watchdog kills, batch plan path, prompt clarity). Then write the integration and unit tests that verify the fixes end-to-end.

## Tasks

### Task 1: Register 6 event types in events.py
- **Files**: `claude/overnight/events.py`
- **What**: Add 6 module-level string constants at the end of the constants block (after line 70) and append all 6 to the `EVENT_TYPES` tuple (after `SESSION_BUDGET_EXHAUSTED` at line 110).
- **Depends on**: none
- **Complexity**: simple
- **Context**: Constants block runs lines 32-70; `EVENT_TYPES` tuple runs lines 72-112. Naming convention: `UPPER_CASE` constant, `all_lowercase_with_underscores` string value. The 6 types to add: `INTEGRATION_WORKTREE_MISSING`, `ORCHESTRATOR_NO_PLAN`, `BATCH_RUNNER_STALLED`, `ARTIFACT_COMMIT_FAILED`, `PUSH_FAILED`, `MORNING_REPORT_COMMIT_FAILED`. All 6 are already called by string literal in runner.sh (lines 310, 312, 660, 690, 949, 1067, 1194, 1204). Do not change the `log_event()` validation logic at line 172.
- **Verification**: `python3 -c "from cortex_command.overnight.events import EVENT_TYPES; assert 'orchestrator_no_plan' in EVENT_TYPES"` exits 0
- **Status**: [x] complete

### Task 2: Make runner.sh REPO_ROOT testable
- **Files**: `claude/overnight/runner.sh`
- **What**: Wrap the existing REPO_ROOT derivation block (lines 25-31) in `if [[ -z "${REPO_ROOT:-}" ]]; then ... fi` so a caller can pre-set `REPO_ROOT` to redirect all path-derived writes to a tmpdir during integration tests.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Lines 24-31 unconditionally derive REPO_ROOT via `git rev-parse` and `cd`. The guard wraps only lines 25-31 — the `.venv` existence check at line 32 and `source` at line 36 remain outside the guard so they run with the final `REPO_ROOT` value regardless. Production behavior is unchanged: REPO_ROOT is never pre-set in production. The `git -C` in the existing derivation uses the private `_SCRIPT_DIR` variable — do not alter its pattern.
- **Verification**: `grep 'REPO_ROOT:-' claude/overnight/runner.sh` exits 0. `bash -n claude/overnight/runner.sh` exits 0
- **Status**: [x] complete

### Task 3: Add regression test — event type sync across overnight files
- **Files**: `tests/test_events.py`
- **What**: Add a test `test_all_log_event_calls_registered()` that scans all `.sh` and `.py` files under `claude/overnight/` for `log_event` calls with string literal arguments and asserts each literal is present in `EVENT_TYPES`.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: `tests/test_events.py` at line 18 defines `REPO_ROOT = Path(__file__).parent.parent` — reuse it. For `.sh` files, match `log_event "([^"]+)"` (the bash inline string literal pattern). For `.py` files, match `log_event\("([^"]+)"` and `overnight_log_event\("([^"]+)"` where the first argument is a quoted string literal (not an imported constant — constants have no quotes). Collect all matched strings, import `EVENT_TYPES` from `claude.overnight.events`, assert membership.
- **Verification**: `just test` exits 0
- **Status**: [x] complete

### Task 4: Add SIGHUP to signal trap
- **Files**: `claude/overnight/runner.sh`
- **What**: Change line 505 from `trap cleanup SIGINT SIGTERM` to `trap cleanup SIGINT SIGTERM SIGHUP`.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Single-word addition. `cleanup()` at lines 449-503 already handles the full graceful shutdown: kills CLAUDE_PID and BATCH_PID, removes lock file, transitions state to "paused" with reason "signal", generates partial morning report, sends notification, exits 130. Do NOT switch to `trap cleanup EXIT` — cleanup() sets paused state and exits 130, conflicting with normal completion at lines 1237-1295.
- **Verification**: `grep 'trap cleanup.*SIGHUP' claude/overnight/runner.sh` exits 0
- **Status**: [x] complete

### Task 5: Spawn watchdogs under set -m and add watchdog PID kills to cleanup()
- **Files**: `claude/overnight/runner.sh`
- **What**: Wrap watchdog subshell spawns at lines 612 and 679 in their own `set -m` / `set +m` blocks so they get their own PGID. Then add conditional process-group kills for `WATCHDOG_PID` and `BATCH_WATCHDOG_PID` in `cleanup()`, after the existing CLAUDE_PID and BATCH_PID kills at lines 451-452.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Currently watchdog spawns at line 612 (`( watch_events_log ... ) & WATCHDOG_PID=$!`) and line 679 (`( watch_events_log ... ) & BATCH_WATCHDOG_PID=$!`) happen after `set +m` (lines 611, 678), so they inherit the runner's PGID. The fix: wrap each spawn in its own `set -m` / `set +m` block — e.g., at line 612: `set -m; ( watch_events_log "$EVENTS_PATH" 1800 $CLAUDE_PID ) & WATCHDOG_PID=$!; set +m`. This gives the watchdog its own PGID (equal to its PID), matching the CLAUDE_PID/BATCH_PID pattern. In cleanup(), add `[[ -n "${WATCHDOG_PID:-}" ]] && kill -- -"$WATCHDOG_PID" 2>/dev/null || true` (process-group kill with negative PID). This kills the watchdog subshell AND all its children (`sleep`, `tail`, `python3`) — no orphans. The `${WATCHDOG_PID:-}` guard handles cleanup firing before any round starts. Update the normal-path kills at lines 616/683 to also use process-group kill for consistency: `kill -- -$WATCHDOG_PID 2>/dev/null || true`.
- **Verification**: `grep -c 'WATCHDOG_PID' claude/overnight/runner.sh` returns >= 4. `bash -n claude/overnight/runner.sh` exits 0
- **Status**: [x] complete

### Task 6: Add absolute path assertion in batch_plan.py
- **Files**: `claude/overnight/batch_plan.py`
- **What**: Add a `ValueError` guard at the top of `generate_batch_plan()` body (before line 46) that rejects non-absolute `output_path` values.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `generate_batch_plan()` is at lines 18-57; `output_path.parent.mkdir(parents=True, exist_ok=True)` is the first file operation at line 46. Use `output_path.is_absolute()` (not `resolve()` — resolving would mask the bug). The relative `plan_path` fallback at line 55 is intentionally worktree-relative — do not add an assertion there. All existing callers pass absolute paths.
- **Verification**: `python3 -c "from pathlib import Path; from cortex_command.overnight.batch_plan import generate_batch_plan; generate_batch_plan([], None, Path('relative/path'))"` — pass if exit code != 0 (ValueError raised)
- **Status**: [x] complete

### Task 7: Add worktree fallback check in runner.sh
- **Files**: `claude/overnight/runner.sh`
- **What**: Inside the `if [[ ! -f "$BATCH_PLAN_PATH" ]]` block at line 659, before `log_event "orchestrator_no_plan"`, add a secondary check for the batch plan at the worktree path and copy it to `$SESSION_DIR` if found.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Current structure at lines 658-662: `BATCH_PLAN_PATH="$SESSION_DIR/batch-plan-round-$ROUND.md"` / `if [[ ! -f "$BATCH_PLAN_PATH" ]]; then` / `log_event "orchestrator_no_plan"` / `echo "...skipping"` / `else` (batch_runner block). Insert a nested conditional inside the outer `if` block. Guard with `[[ -n "$WORKTREE_PATH" ]]`. Fallback path: `$WORKTREE_PATH/lifecycle/sessions/$SESSION_ID/batch-plan-round-$ROUND.md`. Use `cp` (not `mv`) to preserve worktree git history. Restructure control flow so a successful copy falls through to the `else` (batch_runner invocation). Only log `orchestrator_no_plan` when both paths miss.
- **Verification**: `grep -c 'WORKTREE_PATH.*batch-plan' claude/overnight/runner.sh` returns >= 1
- **Status**: [x] complete

### Task 8: Add {session_dir} to fill_prompt() and fix orchestrator-round.md
- **Files**: `claude/overnight/runner.sh`, `claude/overnight/prompts/orchestrator-round.md`
- **What**: Extend `fill_prompt()` to substitute `{session_dir}` with `$SESSION_DIR`. Replace the two `.parent` derivation occurrences in orchestrator-round.md with `Path("{session_dir}")`. Fix the HTML comment at lines 19-21.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `fill_prompt()` uses inline Python with env var injection and `t.replace('{key}', value)` substitution. Add `SESSION_DIR="$SESSION_DIR"` to the env var prefix and `t = t.replace('{session_dir}', os.environ['SESSION_DIR'])` to the substitution chain. In orchestrator-round.md: change line 171 from `Path("{state_path}").parent / "overnight-strategy.json"` to `Path("{session_dir}") / "overnight-strategy.json"`. Change line 277 from `Path("{state_path}").parent / "batch-plan-round-{round_number}.md"` to `Path("{session_dir}") / "batch-plan-round-{round_number}.md"`. Do NOT change `{state_path}` uses at lines 130 and 287. For the HTML comment at lines 19-21, correct to show absolute path and reference `{session_dir}`.
- **Verification**: `grep 'session_dir' claude/overnight/runner.sh` matches in fill_prompt. `grep -c 'Path.*session_dir' claude/overnight/prompts/orchestrator-round.md` returns 2. `grep -c 'resolves to.*/' claude/overnight/prompts/orchestrator-round.md` returns >= 1
- **Status**: [x] complete

### Task 9: Unit test for absolute path assertion
- **Files**: `tests/test_batch_plan.py` (new) or append to existing test file
- **What**: Add a test that calls `generate_batch_plan()` with a relative `output_path` and asserts `ValueError` is raised with a message containing "absolute".
- **Depends on**: [6]
- **Complexity**: simple
- **Context**: Check whether `tests/test_select_overnight_batch.py` already imports `generate_batch_plan`. If so, add the test there. Otherwise create `tests/test_batch_plan.py`. Use `pytest.raises(ValueError, match="absolute")`. Minimum args: `features=[]`, `test_command=None`, `output_path=Path("relative/path")`. No tmpdir required — assertion fires before any file I/O.
- **Verification**: `just test` exits 0
- **Status**: [x] complete

### Task 10: Integration test for SIGHUP signal handling
- **Files**: `tests/test_runner_signal.py` (new)
- **What**: Write a pytest test that starts real `runner.sh` in a fully isolated environment, sends SIGHUP, and asserts cleanup() ran correctly.
- **Depends on**: [1, 2, 4, 5]
- **Complexity**: complex
- **Context**: Setup: (a) `REPO_ROOT=$tmpdir/repo` with `.venv` symlinked from the real repo so venv activation works. (b) `HOME=$tmpdir` so `~/.claude/notify.sh` and `~/.local/share/` writes go to temp locations — create a no-op executable at `$tmpdir/.claude/notify.sh`. (c) Structurally complete state JSON with all fields `load_state()` requires: `session_id`, `phase: "executing"`, `plan_ref: ""`, `current_round: 1`, `started_at: "<ISO timestamp>"`, `updated_at: "<ISO timestamp>"`, `features: {"test-feature": {"status": "pending"}}`. Feature entries use `OvernightFeatureStatus(**dict)` — the minimal valid entry is `{"status": "pending"}` (all other fields default). Do NOT add extra keys (e.g., `name`, `slug`) — `**dict` raises TypeError on unexpected keys. The `integration_branch` field defaults to `"main"` if omitted; set it to a dummy value to suppress git warnings from the worktree auto-recovery block. (d) Mock `claude` binary (`#!/bin/bash\nsleep 60`) injected first in PATH so main loop blocks at `wait $CLAUDE_PID`. (e) Minimal orchestrator prompt template at `$REPO_ROOT/claude/overnight/prompts/orchestrator-round.md`. (f) Writable events log path. (g) `PYTHONPATH` pointing to the real repo root so `claude.overnight.*` imports resolve. Note: Python module-level `_LIFECYCLE_ROOT` (state.py, events.py) resolves to the real repo via `__file__`, not the tmpdir. This means `collect_report_data()` in cleanup() may read from real-repo paths — but report generation is guarded with `|| true`, and the test's assertions don't depend on report content. (h) Stderr may contain "Terminated: 15" messages from process-group kills — do not assert on clean stderr. Run `runner.sh --state $tmpdir/state.json --max-rounds 1` as subprocess. Poll events log for `session_start` event. Send SIGHUP. Assert: process exits within 10 seconds, `circuit_breaker` event with `reason: signal` in events log, exit code 130. Use `process.kill()` in teardown as safety net.
- **Verification**: `just test` exits 0
- **Status**: [x] complete

## Verification Strategy

After all tasks complete:

1. `just test` exits 0 — all existing tests and new tests pass (regression scan, unit test, integration test).
2. Acceptance criterion checks:
   - `grep 'trap cleanup.*SIGHUP' claude/overnight/runner.sh` exits 0
   - `grep -c 'WATCHDOG_PID' claude/overnight/runner.sh` returns >= 4
   - `grep 'REPO_ROOT:-' claude/overnight/runner.sh` exits 0
   - `grep -c 'WORKTREE_PATH.*batch-plan' claude/overnight/runner.sh` returns >= 1
   - `grep 'session_dir' claude/overnight/runner.sh` matches in fill_prompt
   - `grep -c 'Path.*session_dir' claude/overnight/prompts/orchestrator-round.md` returns 2
   - `grep -c 'resolves to.*/' claude/overnight/prompts/orchestrator-round.md` returns >= 1
3. `bash -n claude/overnight/runner.sh` exits 0
4. `python3 -c "from cortex_command.overnight.events import INTEGRATION_WORKTREE_MISSING, ORCHESTRATOR_NO_PLAN, BATCH_RUNNER_STALLED, ARTIFACT_COMMIT_FAILED, PUSH_FAILED, MORNING_REPORT_COMMIT_FAILED"` exits 0
