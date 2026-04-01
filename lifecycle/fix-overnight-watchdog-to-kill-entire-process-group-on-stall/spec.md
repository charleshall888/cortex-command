# Specification: Fix overnight watchdog to kill entire process group on stall

## Problem Statement

When the overnight watchdog fires after 30 minutes of event log silence, it sends SIGTERM to a single PID (`batch_runner.py`). All `claude` CLI subprocesses spawned by the SDK are orphaned and continue running indefinitely. The same applies to the orchestrator agent. This was a contributing factor in the 2026-03-31 overnight hang.

## Requirements

1. **Process group isolation**: Both the orchestrator agent and batch_runner must run in their own process groups, so `kill` can target the entire group. Use `set -m` (bash job control) scoped around each spawn site. Acceptance: `ps -o pgid= -p $CHILD_PID` differs from runner.sh's PGID.

2. **Watchdog group kill**: The watchdog's kill command must target the entire process group (`kill -- -$target_pid`) instead of a single PID. Acceptance: after watchdog timeout, no orphaned `claude` CLI processes remain.

3. **Cleanup trap update**: The `cleanup()` signal handler must explicitly kill child process groups (`kill -- -$CLAUDE_PID`, `kill -- -$BATCH_PID`) so that graceful shutdown (SIGINT/SIGTERM to runner.sh) also terminates children. Acceptance: `runner.sh` graceful shutdown leaves no orphaned processes.

4. **runner.sh survives**: runner.sh must continue running after the watchdog kills a child process group, able to proceed to the next round or generate the morning report. Acceptance: runner.sh exit code is unaffected by child group kills.

## Non-Requirements

- No changes to `batch_runner.py` (no Python signal handlers)
- No changes to `dispatch.py` (no `start_new_session` — it would break process group kill)
- No SIGKILL escalation after SIGTERM
- No runtime PGID assertions

## Edge Cases

- **`set -m` job status messages**: Bash prints termination notifications to stderr. Suppress with `set +m` immediately after capturing `$!`, before `wait`.
- **Watchdog liveness check**: The `kill -0 "$target_pid"` check must stay single-PID. Only the actual kill changes to group kill. A `kill -0 -- -$PGID` would return true if any process in the group is alive, giving false positives from orphaned grandchildren.
- **Watchdog fires before child starts**: 30-minute timeout makes this impossible in practice; no special handling needed.
- **Pipeline spawn**: If a future change wraps the spawn in a pipeline (`cmd | tee &`), `$!` may not equal PGID. Current code uses direct `cmd &` — document this assumption with a comment.

## Technical Constraints

- Must work on macOS bash 3.2 (no `setsid` CLI available)
- `set -m` must be scoped narrowly (`set -m` / `set +m` around each spawn) to avoid affecting watchdog subshells and other background processes
- Exit code semantics from `wait $PID` must be preserved
