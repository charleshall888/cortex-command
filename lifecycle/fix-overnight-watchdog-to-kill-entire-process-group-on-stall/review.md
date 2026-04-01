# Review: Fix overnight watchdog to kill entire process group on stall

## Stage 1: Spec Compliance

### Requirement 1: Process group isolation

**Rating: PASS**

Both spawn sites (orchestrator at line 576-580, batch_runner at line 637-646) are wrapped with `set -m` before the backgrounding and `set +m` immediately after capturing `$!`. This causes each child to become its own process group leader (PGID == PID). The `set +m` is applied before the watchdog subshell spawn on the next line, so the watchdog does not get its own PGID -- matching the spec's requirement that `set -m` be scoped narrowly. Comments explain both the PGID purpose and the `$! == PGID` invariant for direct `cmd &`.

### Requirement 2: Watchdog group kill

**Rating: PASS**

In `watch_events_log()` at line 423, the kill command is changed from `kill "$target_pid"` to `kill -- -"$target_pid"`. The `--` prevents the negative PID from being parsed as a signal option. The `kill -0` liveness check at line 378 remains single-PID (`kill -0 "$target_pid"`), matching the spec's edge case about false positives from orphaned grandchildren.

### Requirement 3: Cleanup trap update

**Rating: PASS**

The `cleanup()` function at lines 441-443 now explicitly kills both child process groups before any other cleanup logic:

```
[[ -n "${CLAUDE_PID:-}" ]] && kill -- -"$CLAUDE_PID" 2>/dev/null || true
[[ -n "${BATCH_PID:-}" ]] && kill -- -"$BATCH_PID" 2>/dev/null || true
```

This uses `${VAR:-}` to safely handle unset variables, and `2>/dev/null || true` to suppress errors when no process group exists. With `set -m`, children are in separate process groups and would not receive runner.sh's SIGINT/SIGTERM, so these explicit kills are necessary.

### Requirement 4: runner.sh survives

**Rating: PASS**

The watchdog function returns 0 after killing the process group (line 424). The `wait $CLAUDE_PID` / `wait $BATCH_PID` calls capture the exit code into `EXIT_CODE` / `BATCH_EXIT`, and subsequent logic handles non-zero exits (stall detection via the stall flag, error logging). The PID variables are cleared (`CLAUDE_PID=""`, `BATCH_PID=""`) after each `wait` at lines 584 and 650, preventing stale PIDs from being reused in cleanup. Runner.sh continues to the next round or morning report generation.

### Non-Requirements Check

- No changes to `batch_runner.py` -- correct, only `runner.sh` modified.
- No changes to `dispatch.py` -- correct.
- No SIGKILL escalation -- correct, only SIGTERM (default signal for `kill`).
- No runtime PGID assertions -- correct.

### Edge Cases Check

- **`set -m` job status messages**: `set +m` is applied immediately after capturing `$!` and before `wait`, suppressing bash's background job termination notifications to stderr. PASS.
- **Watchdog liveness check**: `kill -0 "$target_pid"` remains single-PID. Only the actual kill is group-scoped. PASS.
- **Pipeline spawn**: Comment on both spawn sites documents that `$! == PGID` only holds for direct `cmd &`, not pipelines. PASS.

### Requirements Compliance

The implementation aligns with project requirements:

- **Graceful partial failure**: Watchdog kills a stalled round, runner.sh continues to next round or generates morning report. This strengthens the existing partial-failure model.
- **Complexity**: Three minimal, well-scoped changes (set -m wrapping, group kill, cleanup trap). No unnecessary abstractions.
- **Maintainability**: Comments explain the why. Changes are localized to the two spawn patterns and one cleanup function.
- **macOS bash 3.2 compatibility**: `set -m` and `kill -- -PID` are POSIX and work on bash 3.2. No `setsid` dependency.

## Stage 2: Code Quality

### Naming Conventions

Consistent with existing patterns. `CLAUDE_PID`, `BATCH_PID`, `WATCHDOG_PID`, `BATCH_WATCHDOG_PID` follow the established `UPPER_SNAKE` convention for module-level variables. PID clearing uses empty string assignment, matching how other variables are handled in the script.

### Error Handling

All `kill` calls use `2>/dev/null || true` to suppress errors when processes are already gone. The `${VAR:-}` pattern in cleanup prevents unbound variable errors under `set -u`. The watchdog's `return 0` after kill ensures runner.sh sees clean watchdog exit. No new failure modes introduced.

### Test Coverage

The plan's verification strategy requires manual testing (start a session, check ps output, simulate stalls, send SIGTERM). These are appropriate for a shell script change to an overnight runner -- there's no automated test harness for process group behavior. The tasks are marked complete, indicating verification was performed.

### Pattern Consistency

The `set -m` / `set +m` wrapping follows the same pattern at both spawn sites. The group kill syntax `kill -- -"$PID"` is used consistently in the watchdog function and cleanup trap. PID clearing after `wait` is applied at both spawn sites symmetrically.

## Verdict

```json
{
  "verdict": "APPROVED",
  "cycle": 1,
  "issues": []
}
```
