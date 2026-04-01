# Plan: Fix overnight watchdog to kill entire process group on stall

## Overview

Use bash job control (`set -m`) to give the orchestrator agent and batch_runner their own process groups, change the watchdog kill to target the entire group, and update the cleanup trap to kill child groups on graceful shutdown. All changes are in `runner.sh`.

## Tasks

### Task 1: Wrap spawn sites with `set -m` for process group isolation
- **Files**: `claude/overnight/runner.sh`
- **What**: Add `set -m` before and `set +m` after each of the two background spawn sites (orchestrator at ~line 571 and batch_runner at ~line 627) so each child process becomes its own PGID leader.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Orchestrator spawn is `claude -p "$FILLED_PROMPT" ... & CLAUDE_PID=$!` (~line 571-573). Batch runner spawn is `python3 -m claude.overnight.batch_runner ... & BATCH_PID=$!` (~line 627-634). Add `set -m` immediately before each `&` backgrounding line and `set +m` immediately after capturing `$!` but before the watchdog spawn on the next line (so the watchdog does NOT get its own PGID). Do not enable `set -m` globally — scope it tightly to avoid affecting watchdog subshells and inline Python snippets. Add a comment explaining that `set -m` gives the child its own PGID so the watchdog can kill the entire process group. Also add a comment noting the `$!` == PGID invariant holds for direct `cmd &` but would break with pipelines. Clear each PID variable (`CLAUDE_PID=""`, `BATCH_PID=""`) after successful `wait` at each spawn site to prevent stale PID reuse in the cleanup trap.
- **Verification**: After applying, run `runner.sh` in a test session. Verify with `ps -o pid,pgid,comm` that the orchestrator and batch_runner processes have PGIDs equal to their own PIDs (not runner.sh's PGID).
- **Status**: [x] complete

### Task 2: Change watchdog kill to target the entire process group
- **Files**: `claude/overnight/runner.sh`
- **What**: In `watch_events_log()`, change the kill command from single-PID to process-group kill. Keep the `kill -0` liveness check as single-PID.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: The watchdog function `watch_events_log()` is at ~line 369-427. The kill line is at ~line 423: `kill "$target_pid" 2>/dev/null || true`. Change to `kill -- -"$target_pid" 2>/dev/null || true`. The `--` prevents the negative PID from being parsed as a signal flag. The liveness check `kill -0 "$target_pid"` at ~line 378 must remain single-PID — a negative PID with `kill -0` returns true if any process in the group is alive, giving false positives.
- **Verification**: Trigger a watchdog timeout in a test session. Verify that all child processes (including claude CLI subprocesses) are terminated, not just the direct child. Verify runner.sh itself continues running.
- **Status**: [x] complete

### Task 3: Update cleanup trap to kill child process groups
- **Files**: `claude/overnight/runner.sh`
- **What**: In the `cleanup()` function, add explicit process-group kills for CLAUDE_PID and BATCH_PID before existing cleanup logic, so graceful shutdown (SIGINT/SIGTERM to runner.sh) also terminates children.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: The cleanup function is at ~line 440-490, registered via `trap cleanup SIGINT SIGTERM` at line 490. Currently it transitions state to `paused` and generates a partial morning report, but does not kill child processes. With `set -m`, children are in separate PGIDs and won't receive runner.sh's signals. Add `[[ -n "${BATCH_PID:-}" ]] && kill -- -"$BATCH_PID" 2>/dev/null || true` and the same for `CLAUDE_PID` near the top of `cleanup()`, before state transitions. PID variable clearing after `wait` is handled in Task 1.
- **Verification**: Send SIGTERM to runner.sh during an active batch run. Verify all child processes (batch_runner, claude CLI) are terminated. Verify the morning report is still generated.
- **Status**: [x] complete

## Verification Strategy

1. Start an overnight session and let it reach the batch_runner phase
2. Verify via `ps -o pid,pgid,comm` that batch_runner and its children have a distinct PGID from runner.sh
3. Simulate a stall timeout (or wait for a natural one) and verify no orphaned processes remain
4. Send SIGTERM to runner.sh during active execution and verify clean shutdown with no orphans
5. Verify runner.sh continues to the next round after a watchdog kill (exit codes preserved)
