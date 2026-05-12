# Review: Fix overnight runner silent crash

## Stage 1: Spec Compliance

### A. Signal Handling

**R1 — Add SIGHUP to signal trap**: PASS
- `runner.sh:512` reads `trap cleanup SIGINT SIGTERM SIGHUP` -- exact match to the spec.

**R2 — Kill watchdog PIDs in cleanup()**: PASS
- `runner.sh:458-459` adds kills for `WATCHDOG_PID` and `BATCH_WATCHDOG_PID` with `${...:-}` guard pattern in cleanup().
- Watchdog subshells spawned under `set -m` blocks at lines 619-621 and 696-698, giving each its own PGID.
- Process-group kill via `kill -- -"$PID"` matches the existing CLAUDE_PID/BATCH_PID pattern.
- `grep -c 'WATCHDOG_PID' runner.sh` yields 8 (>= 4 required).

### B. Batch Plan Path Resolution

**R3 — Absolute path assertion in batch_plan.py**: PASS
- `batch_plan.py:46-47` raises `ValueError` with message containing "absolute" when `output_path` is not absolute.
- Guard is at the top of `generate_batch_plan()`, before any file operations.
- Test `test_batch_plan.py::test_relative_output_path_raises_value_error` passes.

**R4 — Worktree fallback check in runner.sh**: PASS
- `runner.sh:668-675` checks `$WORKTREE_PATH/lifecycle/sessions/$SESSION_ID/batch-plan-round-$ROUND.md` when primary path missing.
- Guarded by `[[ -n "$WORKTREE_PATH" ]]` (line 668 uses `&&` with the WORKTREE_PATH check).
- Uses `cp` (not `mv`) as specified.
- Logs a warning on line 673.

**R5 — Add {session_dir} to fill_prompt()**: PASS
- `runner.sh:368` passes `SESSION_DIR="$SESSION_DIR"` to the fill_prompt python block.
- `runner.sh:375` performs `t.replace('{session_dir}', os.environ['SESSION_DIR'])`.
- `orchestrator-round.md:170` uses `Path("{session_dir}") / "overnight-strategy.json"` (was `.parent` derivation).
- `orchestrator-round.md:276` uses `Path("{session_dir}") / "batch-plan-round-{round_number}.md"` (was `.parent` derivation).
- Direct `{state_path}` uses preserved at lines 130 and 286 (for reading/writing state).
- Exactly 2 `Path("{session_dir}")` occurrences in the prompt, 0 `.parent` derivations remain.

**R6 — Fix HTML comment in orchestrator-round.md**: PASS
- `orchestrator-round.md:19-20` reads: `{session_dir} is substituted by runner.sh's fill_prompt() and resolves to an absolute path like /path/to/lifecycle/sessions/{session_id}/`
- Shows absolute path with leading slash. Acceptance criteria met.

### C. Event Type Registration

**R7 — Register 6 event types in events.py**: PASS
- All 6 constants defined at lines 71-76 with correct names and string values.
- All 6 included in `EVENT_TYPES` tuple at lines 118-123.
- Naming follows existing convention (UPPER_CASE constants, lowercase_underscore values).

### D. Testing

**R8 — Regression test for event type sync**: PASS
- `test_events.py::test_all_log_event_calls_registered` scans all `.sh` and `.py` files in `claude/overnight/`.
- Parses `log_event "..."` (bash), `log_event("...")` (python), and `overnight_log_event("...")` (python) patterns.
- Asserts each found literal is in `EVENT_TYPES`.
- Includes sanity check that at least one literal was found.
- Test passes.

**R9 — Make runner.sh REPO_ROOT testable**: PASS
- `runner.sh:26` reads `if [[ -z "${REPO_ROOT:-}" ]]; then` -- exact guard pattern from spec.
- Existing derivation logic preserved inside the guard (lines 27-33).
- No behavioral change in production (REPO_ROOT never pre-set).

**R10 — Integration test for signal handling**: PASS
- `test_runner_signal.py::test_sighup_triggers_cleanup` implements all specified setup steps:
  - (a) `REPO_ROOT=$tmpdir/repo` with `.venv` symlink
  - (b) `HOME=$tmpdir` with no-op `notify.sh`
  - (c) Structurally complete state file with all required fields
  - (d) Mock `claude` binary (`sleep 60`) first in PATH
  - (e) No-op notify.sh at `$tmpdir/.claude/notify.sh`
  - (f) Orchestrator prompt template at correct path
- Polls for `session_start` event before sending SIGHUP.
- Verifies: process exits within 10 seconds, `circuit_breaker` event with `reason: signal`, exit code 130.
- Test passes (verified outside sandbox; sandbox-only TMPDIR restriction causes sandbox failure -- not a code issue).

**R11 — Unit test for absolute path assertion**: PASS
- `test_batch_plan.py::test_relative_output_path_raises_value_error` passes `Path("relative/path")` and asserts `ValueError` with match "absolute".
- Test passes.

## Stage 2: Code Quality

### Naming Conventions
Consistent with project patterns. Event type constants follow the established `UPPER_CASE = "lower_case"` pattern. Variable names (`WATCHDOG_PID`, `BATCH_WATCHDOG_PID`, `SESSION_DIR`) follow existing shell conventions. Test names use descriptive `test_<what_is_tested>` format.

### Error Handling
Appropriate for context. The `${WATCHDOG_PID:-}` guard in cleanup handles the unset-variable edge case. The absolute path assertion raises `ValueError` with a clear message. The worktree fallback is defense-in-depth with proper guards (`[[ -n "$WORKTREE_PATH" ]]`). Kill commands use `2>/dev/null || true` matching existing patterns.

### Test Coverage
All 3 new test files cover the specified scenarios. The regression test (`test_all_log_event_calls_registered`) provides ongoing protection against future event type registration gaps. The signal handling test exercises the real cleanup code path end-to-end. All 63 tests in the suite pass.

### Pattern Consistency
Implementation follows existing project conventions throughout:
- `set -m` / `set +m` blocks for process group isolation match the existing CLAUDE_PID/BATCH_PID pattern.
- `fill_prompt()` substitution uses the same `t.replace('{key}', value)` pattern as existing variables.
- Event constants placement and ordering in `events.py` is consistent.
- Test structure follows existing test file conventions (fixtures, `tmp_path` usage, `pytest.raises`).

## Requirements Drift
**State**: detected
**Findings**:
- The pipeline requirements (`requirements/pipeline.md`) describe graceful degradation ("Budget exhaustion and rate limits pause the session rather than crashing it") and audit trail, but do not explicitly mention signal handling (SIGHUP/SIGTERM/SIGINT) as a graceful degradation trigger. The implementation now treats SIGHUP as a first-class signal that triggers cleanup, state transition to paused, and partial morning report generation -- this behavior is not captured in the requirements.
- The pipeline requirements do not mention the event type registration allowlist (`EVENT_TYPES`) as an architectural constraint, despite it being load-bearing for data quality validation. The spec's non-requirements section explicitly states "Do NOT remove the EVENT_TYPES allowlist -- it provides data quality validation for the events log."
**Update needed**: requirements/pipeline.md

## Verdict

```json
{
  "verdict": "APPROVED",
  "cycle": 1,
  "issues": [],
  "requirements_drift": "detected"
}
```
