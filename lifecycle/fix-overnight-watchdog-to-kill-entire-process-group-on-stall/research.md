# Research: Fix overnight watchdog to kill entire process group on stall

## Codebase Analysis

### Files That Will Change

1. **`claude/overnight/runner.sh`** (PRIMARY)
   - Line 423: Watchdog kill logic — `kill "$target_pid" 2>/dev/null || true` → process group kill
   - Lines 571-573: Orchestrator agent spawn — `claude -p ... & CLAUDE_PID=$!`
   - Lines 627-634: Batch runner spawn — `python3 -m ... & BATCH_PID=$!`
   - Lines 440-490: Signal trap/cleanup handler — must be updated to kill child process groups
   - Lines 574, 635: Watchdog subprocess invocation

2. **`claude/overnight/batch_runner.py`** (OPTIONAL, defense-in-depth)
   - Add SIGTERM handler for cooperative subprocess cleanup
   - Existing `global_abort_signal` field in `BatchResult` suggests signal infrastructure exists

### Relevant Existing Patterns

- **Process spawning**: `cmd & PID=$!` followed by `wait $PID; EXIT_CODE=$?`
- **Watchdog**: `watch_events_log()` polls event log every 30s, fires after 1800s silence
- **Stall flag**: Temp file written by watchdog, checked by main loop after `wait` returns
- **Signal trap**: `trap cleanup SIGINT SIGTERM` transitions state to `paused`, generates partial morning report
- **Event logging**: `log_event()` helper wrapping Python's `claude.overnight.events.log_event`
- **No existing `setsid` usage** anywhere in the codebase

### Integration Points

- Exit codes from `wait` drive state transitions and event logging (lines 597-607, 658-661)
- Stall flag file coordinates watchdog→main-loop communication
- Morning report generation depends on state file and events log integrity
- Heartbeat loop in batch_runner.py (every 5 min) prevents false stall timeouts

## Web Research

### Critical Platform Finding: macOS Has No `setsid` CLI

The `setsid(1)` command is part of `util-linux`, a **Linux-only** package. macOS has the `setsid(2)` system call but no shell-level wrapper. The backlog's proposed syntax (`setsid python3 -m claude.overnight.batch_runner ...`) will fail on stock macOS/Darwin.

### `setsid` vs `setpgrp` — Key Distinction

| Method | New Process Group | New Session | Loses Terminal | `$!` Accurate | `wait` Works |
|---|---|---|---|---|---|
| `setsid()` | Yes | Yes | Yes | No (may fork) | Depends |
| `setpgid(0,0)` / `setpgrp` | Yes | No | No | Yes | Yes |
| `set -m` (bash) | Yes (per job) | No | No | Yes | Yes |

`setsid` creates a full new session (overkill). `setpgrp`/`set -m` creates only a new process group (exactly what's needed).

### Portable Alternatives

1. **`set -m` (bash job control)**: Each backgrounded process gets its own PGID automatically. Zero dependencies, works on macOS bash 3.2.
2. **`perl -e 'setpgrp(0,0); exec @ARGV'` wrapper**: Portable, no fork indirection, `$!` correct.
3. **Python `os.setpgid(0,0)` inline wrapper**: Python already a dependency.

### Process Group Kill Semantics

- `kill -- -$PGID` atomically signals all processes in the group
- `wait $PID` works on direct children regardless of PGID
- `kill 0` kills the current process group (avoid in scripts — kills the parent)

## Requirements & Constraints

### Acceptance Criteria (from backlog)

1. After a watchdog timeout, no orphaned `claude` CLI processes remain running
2. `runner.sh` itself survives the watchdog kill and can continue to the next round or generate the morning report
3. The watchdog still functions correctly for the orchestrator agent (round loop)

### Architectural Constraints

- Two watchdog instances: one for orchestrator (300s timeout), one for batch_runner (1800s timeout)
- State transitions to `paused` with `paused_reason: 'stall_timeout'` must be preserved
- Event logging (STALL_TIMEOUT events) must occur before killing
- Morning report generation depends on intact state and events files
- No existing tests for watchdog/process group behavior

## Tradeoffs & Alternatives

### Recommended: `set -m` (bash job control)

**Pros**: Zero dependencies, works on stock macOS bash 3.2, minimal code change (~6-8 lines), correct POSIX semantics, `wait` and exit codes unaffected, only creates new process group (not full session).

**Cons**: Prints job termination messages to stderr (cosmetic), affects all `&`-backgrounded processes if enabled globally (scope narrowly with `set -m` / `set +m` around spawn sites).

### Fallback: Python `setpgid(0,0)` Wrapper

```bash
python3 -c "import os,sys; os.setpgid(0,0); os.execvp(sys.argv[1], sys.argv[1:])" \
    python3 -m claude.overnight.batch_runner ... & BATCH_PID=$!
```

Clean, explicit, portable. Slightly more verbose.

### Rejected Approaches

- **`setsid` CLI** (backlog's proposal): Not available on macOS
- **`pkill -P` tree-walk**: Race conditions, only kills direct children, fragile
- **Cgroups**: macOS incompatible
- **SDK `start_new_session=True`**: Not exposed by SDK, AND contradicts process-group kill (see Adversarial Review)

## Adversarial Review

### Critical Findings

1. **Cleanup trap must be updated (HIGH)**: With `set -m`, child processes are in their own PGIDs and won't receive signals sent to runner.sh. The `cleanup()` trap at line 440 must explicitly `kill -- -$BATCH_PID` and `kill -- -$CLAUDE_PID`, or every graceful shutdown will orphan running agents.

2. **`start_new_session=True` contradicts process-group kill (HIGH)**: If `dispatch.py` adds `start_new_session=True` to `anyio.open_process()`, each `claude` CLI subprocess escapes the batch_runner's process group. `kill -- -$BATCH_PID` would kill batch_runner but leave claude CLI running — the exact bug we're fixing. This "defense-in-depth" option is actually harmful.

3. **No SIGKILL escalation**: If a process ignores SIGTERM, the group stays alive. Watchdog should send SIGTERM, sleep briefly, then SIGKILL.

4. **`asyncio.run()` does NOT propagate SIGTERM to child processes**: When batch_runner.py receives SIGTERM, Python's default handler raises SystemExit. `asyncio.run()` cancels tasks but does NOT signal subprocess children. This confirms the process-group kill is necessary — Python-level cleanup alone is insufficient.

### Assumptions to Validate

- `$! == PGID` holds when using direct `cmd &` but breaks with pipelines (`cmd | tee log &`). Current code uses direct spawn — document this constraint.
- Future SDK versions might add `start_new_session=True` internally, silently breaking the fix.

### Recommended Mitigations

1. Update `cleanup()` trap to kill child process groups explicitly
2. Do NOT add `start_new_session=True` to dispatch.py — it contradicts the mechanism
3. Add SIGKILL escalation in watchdog (SIGTERM → 3s sleep → SIGKILL)
4. Scope `set -m` narrowly around spawn sites
5. Add Python SIGTERM handler in batch_runner.py as defense-in-depth (cooperative, not `start_new_session`)
6. Document the `$! == PGID` invariant with a comment

## Open Questions

- Should `set -m` be scoped narrowly (`set -m; cmd & PID=$!; set +m`) or enabled globally? Global is simpler but affects all background processes including watchdog subshells and inline Python snippets.
- Should the SIGKILL escalation timeout be 3 seconds or configurable? The watchdog already waited 30 minutes — a brief grace period seems sufficient.
- How to guard against future SDK versions adding `start_new_session=True` internally? A runtime PGID assertion (`ps -o pgid= -p $CHILD_PID` == `$BATCH_PID`) could detect this.
