# Research: Fix overnight runner silent crash — signal handling, unregistered events, and batch plan path mismatch

## Codebase Analysis

### Files That Will Change

| File | Lines | Change |
|------|-------|--------|
| `claude/overnight/runner.sh` | 505 | Add SIGHUP to signal trap |
| `claude/overnight/runner.sh` | ~658 | Add worktree fallback check for batch plan |
| `claude/overnight/runner.sh` | 362-375 | Add `{session_dir}` to `fill_prompt()` |
| `claude/overnight/events.py` | 32-70, 72-112 | Register 6 event type constants + add to EVENT_TYPES |
| `claude/overnight/batch_plan.py` | 18-57 | Add absolute path assertion on `output_path` |
| `claude/overnight/prompts/orchestrator-round.md` | 19-21 | Fix misleading HTML comment about `{state_path}` |

### Related Files (consume events, no changes needed)

- `claude/overnight/report.py` — morning report reads events generically (line 162, 412-425)
- `claude/overnight/status.py` — live status display, event-type agnostic (lines 85-139)

### Key Code Locations

**Signal trap** (runner.sh:505):
```bash
trap cleanup SIGINT SIGTERM
```

**cleanup()** (runner.sh:449-503): 7 side effects — kill child PIDs (CLAUDE_PID, BATCH_PID), remove lock file, transition state to "paused" with reason "signal", update active-session pointer, generate partial morning report, notify "session killed", exit 130. Does NOT kill watchdog PIDs (WATCHDOG_PID at line 612, BATCH_WATCHDOG_PID at line 679).

**fill_prompt()** (runner.sh:362-375): Substitutes `{state_path}`, `{plan_path}`, `{events_path}`, `{round_number}`, `{tier}` into the orchestrator prompt template. `{state_path}` resolves to absolute path (via realpath at line 178).

**batch_plan.py generate_batch_plan()** (lines 18-57): `output_path` parameter used directly. When `feature_plan_paths` dict is missing an entry, falls back to relative `Path(f"lifecycle/{name}/plan.md")` — this relative path is intentionally worktree-relative and correct for its context.

**EVENT_TYPES** (events.py:72-112): Tuple of 40 registered event type strings. `log_event()` at line 172 validates against this tuple, raises ValueError for unknown types.

**Unregistered event types in runner.sh** (confirmed by exhaustive grep):

| Event type | Line(s) | Crash risk | Context |
|------------|---------|------------|---------|
| `integration_worktree_missing` | 310, 312 | HIGH — kills startup | Worktree entry missing or path not on disk |
| `orchestrator_no_plan` | 660 | HIGH — kills round loop | Orchestrator didn't produce batch plan |
| `batch_runner_stalled` | 690 | HIGH — kills stall recovery | Batch runner watchdog timeout |
| `artifact_commit_failed` | 949 | Low — notification lost | Git commit of lifecycle artifacts fails |
| `push_failed` | 1067 | Low — notification lost | Pushing integration branch fails |
| `morning_report_commit_failed` | 1194, 1204 | Low — notification lost | Pushing morning report fails |

No additional unregistered types exist. All Python callers use imported constants from events.py (except one style inconsistency at batch_runner.py:1407 using a raw string that matches the registered constant).

### Existing Patterns & Conventions

- **Event type constants**: UPPER_CASE module-level constants (e.g., `ORCHESTRATOR_FAILED = "orchestrator_failed"`)
- **EVENT_TYPES tuple**: All constants listed in a single tuple for membership validation
- **Signal trap**: Named function (`cleanup`) with signal-specific semantics — distinct from normal exit path (lines 1237-1295)
- **Path resolution**: STATE_PATH resolved via `realpath` at line 178; SESSION_DIR derived as `$(dirname "$STATE_PATH")`
- **Worktree awareness**: runner.sh CDs into WORKTREE_PATH (line 583) before spawning agents; prompts receive absolute paths via fill_prompt()

## Web Research

### Signal Handling Best Practices

- The three-signal pattern (`SIGHUP + SIGINT + SIGTERM`) is the established best practice for long-running bash daemons.
- tmux sends SIGHUP to the foreground process group when a pane/session is destroyed or the server dies. Detaching does NOT send any signal.
- `trap cleanup EXIT` catches all exit paths including `set -e` failures, but is inappropriate when cleanup() has semantically different responsibilities than the normal exit path — which is exactly the case here.
- SIGPIPE is a non-issue: bash ignores it by default for builtins; tmux dying sends SIGHUP first.
- SIGQUIT should be left untrapped to preserve core dump capability for debugging.

### Path Validation

- `Path.is_absolute()` is the idiomatic Python check. Use `ValueError` (not `TypeError`) for the assertion — matches events.py's existing error convention.
- `resolve()` converts relative to absolute (masking the bug); `is_absolute()` detects and rejects (surfacing the bug). Validation should use `is_absolute()`.

### Event Registry Patterns

- Allowlist with ValueError on unknown types is the correct pattern for registries where data quality matters.
- Removing the allowlist allows typos to corrupt the events log silently.
- `frozenset` would be O(1) for membership vs O(n) for tuple, but marginal at 46 entries.

## Requirements & Constraints

### From requirements/pipeline.md

- **Session orchestration**: Forward-only phase transitions; paused sessions resume to the phase they paused from. Signal-induced termination must transition to "paused", not crash silently.
- **Failure handling**: Fail-forward model — one feature's failure does not block others. The signal trap is the outermost safety net for this contract.
- **Audit trail**: `lifecycle/pipeline-events.log` provides append-only JSONL record. All operational events must be loggable without crashing.
- **Atomic state writes**: All session state uses tempfile + `os.replace()`. cleanup() already follows this pattern.

### From requirements/multi-agent.md

- **Worktree isolation**: Reliable path resolution across process boundaries. Paths passed between runner.sh and spawned agents must be absolute or worktree-aware.

### From requirements/observability.md

- **Dashboard and statusline**: Read from events.log and overnight-state.json. Malformed or missing event types cause downstream parsing failures or missing dashboard data.

### Scope Boundaries

- The backlog item scopes exactly three failures with specific fixes. The debug file (cited as context) contains additional recommendations (e.g., watchdog PID cleanup, EXIT trap) that are explicitly out of scope.

## Tradeoffs & Alternatives

### Failure A: Signal Trap

| Approach | Verdict | Reasoning |
|----------|---------|-----------|
| Add SIGHUP to existing trap | **Correct** | Minimal, explicit, handles the root cause. cleanup() semantics preserved. |
| `trap cleanup EXIT` | Rejected | cleanup() sets state to "paused", exits 130, generates partial report — all wrong for normal completion. Normal exit has distinct code at lines 1237-1295. |
| nohup/setsid wrapper | Rejected | Changes invocation pattern. Doesn't catch explicit SIGHUP from process managers. Runner still vulnerable when invoked directly. |

### Failure B: Batch Plan Path

| Fix | Priority | Type | Rationale |
|-----|----------|------|-----------|
| B1: Absolute path assertion in `batch_plan.py` | 1 | Deterministic guardrail | Only fix that makes the bug impossible. All existing callers already pass absolute paths — safe to add. |
| B2: Worktree fallback in runner.sh | 2 | Pragmatic recovery | Safety net for agent confusion. Should use `cp` not `mv` to preserve worktree git history. |
| B3: Add `{session_dir}` to fill_prompt | 3 | Prompt clarity | Reduces LLM derivation steps. Probabilistic, not deterministic. |
| B4: Fix HTML comment in orchestrator-round.md | 4 | Documentation | Removes misleading claim that `{state_path}` is relative. |

All 4 are complementary. B1 is mandatory; B2-B4 add defense-in-depth.

### Failure C: Event Registration

| Approach | Verdict | Reasoning |
|----------|---------|-----------|
| Register all 6 in EVENT_TYPES | **Correct** | Types are actively used, not typos. Registration is 6 one-line additions. |
| Remove allowlist entirely | Rejected | Events log is load-bearing (morning report, resume logic, watchdog). Typos would corrupt data silently. |
| Auto-discover from usage | Rejected | Adds build complexity. Doesn't catch typos. Fragile to refactoring. |
| Blanket `\|\| true` guards | Rejected | Converts crash-visible failures into silently-missing data — the exact problem being fixed. |
| Narrow ValueError catch in Python | Not for this ticket | Band-aid. Still doesn't log the event. Better as defense-in-depth follow-up. |

## Adversarial Review

### Failure Modes and Edge Cases

1. **Watchdog orphan processes**: cleanup() kills CLAUDE_PID and BATCH_PID but NOT WATCHDOG_PID or BATCH_WATCHDOG_PID. On signal, watchdog subshells survive as orphans for up to 30 seconds (one poll interval) before detecting the dead target PID and exiting. During this window, a watchdog could write a spurious `stall_timeout` event. Out of ticket scope but a real gap.

2. **`set -e` blind spot**: When `set -e` kills the runner (e.g., from a future inline Python failure outside `set +e` regions), no signal handler fires. The process exits silently with no cleanup. Fix C prevents the specific `set -e` crash from unregistered events, but other `set -e` failures remain unmitigated. A minimal EXIT trap (lock file removal + notification only, without state transition or morning report) could address this — out of ticket scope.

3. **Worktree fallback should copy, not move**: If B2 moves the batch plan from the worktree to `$SESSION_DIR`, it removes the LLM's committed artifact from the worktree's git history. Use `cp` to preserve the worktree commit history.

4. **Regression prevention gap**: After registering the 6 types, any future event type added to runner.sh but not to EVENT_TYPES will cause the same silent crash. No automated check exists to prevent regression.

### Assumptions Validated

- **Signal re-entrance is safe**: Bash traps are not re-entered by default — signals received during a handler are held until the handler completes. cleanup() is safe from re-entrance.
- **Absolute path assertion won't break callers**: All existing callers of `generate_batch_plan()` pass absolute `output_path` values (confirmed via code inspection and test analysis).
- **No concurrency risk in worktree fallback**: Lock file at lines 322-332 prevents concurrent runner processes. Round loop is sequential.

### Recommended Mitigations (Out of Ticket Scope)

1. Add watchdog PID cleanup to cleanup() — prevents orphaned watchdog processes
2. Add regression test: parse runner.sh for `log_event "..."` strings and assert they're all in EVENT_TYPES
3. Consider narrow ValueError catch in bash log_event helper as defense-in-depth
4. File follow-up for minimal EXIT trap to address `set -e` blind spot

## Open Questions

None. All three failures have clear, well-validated fixes. The adversarial review surfaced edge cases (watchdog orphans, set -e blind spot, regression testing) that are explicitly out of ticket scope and should be filed as follow-up items.
