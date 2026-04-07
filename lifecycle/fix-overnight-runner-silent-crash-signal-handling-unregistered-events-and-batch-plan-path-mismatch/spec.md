# Specification: Fix overnight runner silent crash

## Problem Statement

Session `overnight-2026-04-07-0008` crashed silently after Round 1 due to three independent bugs converging: SIGHUP not trapped, batch plan written to wrong location, and unregistered event types crashing under `set -e`. The runner died without cleanup, state transition, notification, or morning report — violating the pipeline's graceful degradation and audit trail requirements. This fix restores the overnight runner's reliability as the backbone of autonomous multi-hour development.

## Requirements

### A. Signal Handling

1. **Add SIGHUP to signal trap**: Change `runner.sh:505` from `trap cleanup SIGINT SIGTERM` to `trap cleanup SIGINT SIGTERM SIGHUP`. Acceptance criteria: `grep 'trap cleanup.*SIGHUP' claude/overnight/runner.sh` matches, pass if exit code = 0.

2. **Kill watchdog PIDs in cleanup()**: Add kills for `WATCHDOG_PID` and `BATCH_WATCHDOG_PID` in `cleanup()` (after the existing CLAUDE_PID and BATCH_PID kills at lines 451-452). Spawn watchdog subshells under their own `set -m` block so they get their own PGID, then use process-group kill in cleanup: `kill -- -"$WATCHDOG_PID" 2>/dev/null || true`. This matches the existing CLAUDE_PID/BATCH_PID pattern and eliminates orphaned child processes (`sleep`, `tail`, `python3` children of the watchdog loop). Acceptance criteria: `grep -c 'WATCHDOG_PID' claude/overnight/runner.sh` >= 4 (two spawns at 612/679, two kills in cleanup), pass if count >= 4.

### B. Batch Plan Path Resolution

3. **Absolute path assertion in `batch_plan.py`**: Add a guard at the top of `generate_batch_plan()` (after line 46, before any file operations) that raises `ValueError` if `output_path` is not absolute: `if not output_path.is_absolute(): raise ValueError(f"output_path must be absolute, got: {output_path}")`. Acceptance criteria: `just test` exits 0 with a new test that calls `generate_batch_plan(output_path=Path("relative/path"), ...)` and asserts `ValueError` is raised.

4. **Worktree fallback check in `runner.sh`**: After line 659 (`if [[ ! -f "$BATCH_PLAN_PATH" ]]`), before logging `orchestrator_no_plan`, check `$WORKTREE_PATH/lifecycle/sessions/$SESSION_ID/batch-plan-round-$ROUND.md`. If found, copy (not move) it to `$BATCH_PLAN_PATH` and log a warning. This is a defense-in-depth measure for LLM non-determinism — R5/R6 fix the root cause (prompt clarity), but LLM agents may still construct paths incorrectly despite clear prompting (as happened in the original crash where Round 1 followed the prompt but Round 2 did not). R4 catches the most likely failure mode (batch plan at wrong path) without attempting to rescue other side effects (state writes use the substituted `{state_path}` variable directly and are less susceptible to LLM path confusion). Acceptance criteria: Observable in code — `grep -c 'WORKTREE_PATH.*batch-plan' claude/overnight/runner.sh` >= 1.

5. **Add `{session_dir}` to `fill_prompt()`**: Extend `fill_prompt()` (runner.sh:362-375) to substitute `{session_dir}` with `$SESSION_DIR`. In `orchestrator-round.md`, replace only the two `.parent` derivation occurrences with `Path("{session_dir}")` (note the `Path()` wrapper — `{session_dir}` is substituted as a raw string, so `/` path join requires a Path object):
   - Line 171: `Path("{state_path}").parent / "overnight-strategy.json"` → `Path("{session_dir}") / "overnight-strategy.json"`
   - Line 277: `Path("{state_path}").parent / "batch-plan-round-{round_number}.md"` → `Path("{session_dir}") / "batch-plan-round-{round_number}.md"`
   
   Do NOT replace direct `{state_path}` uses for reading/writing state (e.g., `state_path = Path("{state_path}")` at lines 130, 287). Those must remain as-is. Acceptance criteria: `grep 'session_dir' claude/overnight/runner.sh` matches in fill_prompt AND `grep -c 'Path.*session_dir' claude/overnight/prompts/orchestrator-round.md` = 2, pass if both conditions met.

6. **Fix HTML comment in orchestrator-round.md**: Lines 19-21 describe `{state_path}` as resolving to `lifecycle/sessions/{session_id}/overnight-state.json` (relative). Correct to show that `{state_path}` resolves to an absolute path (e.g., `/path/to/lifecycle/sessions/{session_id}/overnight-state.json`). Acceptance criteria: `grep -c 'resolves to.*/' claude/overnight/prompts/orchestrator-round.md` >= 1 (shows absolute path with leading slash).

### C. Event Type Registration

7. **Register 6 event types in `events.py`**: Add 6 module-level constants and include them in the `EVENT_TYPES` tuple:
   - `INTEGRATION_WORKTREE_MISSING = "integration_worktree_missing"`
   - `ORCHESTRATOR_NO_PLAN = "orchestrator_no_plan"`
   - `BATCH_RUNNER_STALLED = "batch_runner_stalled"`
   - `ARTIFACT_COMMIT_FAILED = "artifact_commit_failed"`
   - `PUSH_FAILED = "push_failed"`
   - `MORNING_REPORT_COMMIT_FAILED = "morning_report_commit_failed"`
   
   Acceptance criteria: `just test` exits 0 with a new test that calls `log_event(event_type, ...)` for each of the 6 new types and asserts no ValueError is raised.

### D. Testing

8. **Regression test for event type sync**: Add a test that scans all files in `claude/overnight/` (both `.sh` and `.py`) for `log_event` calls with string literal event type arguments, and asserts each is present in `EVENT_TYPES`. For bash files, parse `log_event "..."` patterns. For Python files, parse `log_event("...")` and `overnight_log_event("...")` patterns where the first argument is a string literal (not an imported constant). Acceptance criteria: `just test` exits 0 with the new test passing.

9. **Make runner.sh REPO_ROOT testable**: Wrap the existing REPO_ROOT derivation (runner.sh:25-31) in a guard so it respects a pre-set value: `if [[ -z "${REPO_ROOT:-}" ]]; then ... fi`. This is a 2-line change that doesn't affect production (REPO_ROOT is never pre-set in production) but enables the integration test to redirect all REPO_ROOT-derived writes to a tmpdir. Acceptance criteria: `grep 'REPO_ROOT:-' claude/overnight/runner.sh` matches, pass if exit code = 0.

10. **Integration test for signal handling**: Write a pytest test that runs the real `runner.sh` with a fully isolated environment and sends SIGHUP. Setup: (a) set `REPO_ROOT=$tmpdir/repo` and symlink `.venv` from the real repo into it so venv activation works, (b) set `HOME=$tmpdir` so `~/.local/share/` and `~/.claude/notify.sh` writes go to temp locations, (c) create a structurally complete state file with all fields `load_state()` requires (`session_id`, `phase: "executing"`, `plan_ref`, `current_round`, `started_at`, `updated_at`, `features` with at least one pending feature), (d) create a mock `claude` binary (`#!/bin/bash\nsleep 60`) first in PATH so the main loop blocks at `wait $CLAUDE_PID`, (e) create a no-op notify.sh at `$tmpdir/.claude/notify.sh`, (f) create the orchestrator prompt template at `$REPO_ROOT/claude/overnight/prompts/orchestrator-round.md`. Run: start `runner.sh --state $tmpdir/state.json --max-rounds 1` as a subprocess. Poll events log for `session_start` event (confirms pre-loop setup complete and trap is registered). Send SIGHUP. Verify: (a) process exits within 10 seconds (not hung), (b) `circuit_breaker` event with `reason: signal` appears in events log, (c) exit code is 130. This tests the real cleanup() code path — no replicas, no repo side effects. Acceptance criteria: `just test` exits 0 with the new test passing.

11. **Unit test for absolute path assertion**: Add a test for `generate_batch_plan()` that passes a relative `output_path` and asserts `ValueError` is raised with a message containing "absolute". Acceptance criteria: `just test` exits 0 with the new test passing.

## Non-Requirements

- Do NOT switch to `trap cleanup EXIT` — cleanup() has 7 side effects with signal-specific semantics (paused state, partial report, exit 130) that conflict with normal completion (complete state, full report, exit 0).
- Do NOT blanket-guard bash `log_event` calls with `|| true` — the events log is load-bearing (morning report, resume logic, watchdog consume it). Swallowing errors converts crash-visible failures into silently-missing data.
- Do NOT remove the EVENT_TYPES allowlist — it provides data quality validation for the events log.
- Do NOT modify the `feature_plan_paths` relative path fallback at `batch_plan.py:55` — this relative path is intentionally worktree-relative and correct for its context. Only `output_path` needs the absolute assertion.
- The `set -e` blind spot (no signal handler fires on `set -e` exits) is out of scope. File as a follow-up.
- A narrow `ValueError` catch in the bash `log_event` helper is out of scope for this ticket. The regression test (R8) covers the most common introduction vector (runner.sh), but does not cover all call sites — future defense-in-depth via a Python-level ValueError catch may be warranted as a follow-up.

## Edge Cases

- **SIGHUP during cleanup()**: Safe — bash traps are not re-entered by default. Signals received during a handler are held until the handler completes.
- **Watchdog PID variables unset**: The `${WATCHDOG_PID:-}` guard pattern handles this — if the variable is unset (cleanup fires before any round starts), the conditional is falsy and the kill is skipped.
- **Batch plan exists in both locations**: The worktree fallback (R4) only triggers when the primary path (`$SESSION_DIR`) has no file. If both exist, the primary is used.
- **Worktree fallback when `$WORKTREE_PATH` is empty**: Guard the fallback check with `[[ -n "$WORKTREE_PATH" ]]` — non-worktree sessions skip the fallback silently.
- **`generate_batch_plan()` called from tests with tmpdir paths**: `tempfile.TemporaryDirectory()` always returns absolute paths on macOS and Linux. Existing tests are unaffected.
- **`morning_report_commit_failed` logged from within `cd "$TARGET_INTEGRATION_WORKTREE"` subshell** (line 1201-1207): The `log_event` bash function uses `$EVENTS_PATH` which is an absolute path set at session start — logging works regardless of CWD.
- **REPO_ROOT pre-set in production**: The `if [[ -z "${REPO_ROOT:-}" ]]` guard only applies when REPO_ROOT is already set. In production, REPO_ROOT is never pre-set — the guard falls through to the existing derivation logic. No behavioral change.

## Technical Constraints

- **Atomic state writes**: cleanup()'s `save_state()` uses atomic tempfile + `os.replace()` — no partial-write corruption risk (from `requirements/pipeline.md`).
- **Process group semantics**: cleanup() kills process groups via `kill -- -"$PID"` (negative PID). This depends on `set -m` having created separate process groups for child processes. Watchdog subshells must be spawned under `set -m` to get their own PGID, matching the existing pattern for CLAUDE_PID/BATCH_PID. This enables clean process-group kill in cleanup() and eliminates orphaned child processes.
- **Event naming convention**: All-lowercase with underscores. Constants are UPPER_CASE. Must follow existing pattern in events.py.
- **`fill_prompt()` substitution**: Uses simple string replacement (`t.replace('{key}', value)`). Adding `{session_dir}` follows the same pattern as existing variables.

## Open Decisions

None.
