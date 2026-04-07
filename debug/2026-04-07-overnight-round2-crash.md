# Debug Session: Overnight runner silent crash after Round 1
Date: 2026-04-07
Status: In progress
Session: overnight-2026-04-07-0008

## Phase 1 Findings

### Observed behavior
Overnight session completed Round 1 (2 features merged), logged `round_start` for Round 2 at 00:16:34 UTC, then died silently. tmux session `overnight-runner` dead. No further events. State stuck in `executing`.

### Timeline
- 00:08:47 — Session start event logged
- 00:09:53 — Orchestrator starts Round 1
- 00:14:54 — Round 1 features dispatched (2 parallel agents)
- 00:15:46 — Feature 1 merged (inline style fixes)
- 00:16:32 — Feature 2 merged (accessibility foundations)
- 00:16:33 — Round 1 complete
- 00:16:34 — Round 2 start logged
- 00:19:58 — Last commit: "Generate implementation plans for round 2 features"
- 00:20:00 — **Runner dies silently** — no more events, commits, or debug logs

### Root cause: Three independent failures converged

**Failure A — SIGHUP not trapped (runner.sh:505)**
The tmux server died, sending SIGHUP to the runner. The trap only catches SIGINT/SIGTERM. Runner died without cleanup. The orchestrator Claude process survived as an orphan (separate process group via `set -m`) and completed Round 2 plans before exiting.

**Failure B — Batch plan written to worktree, not main repo**
The Round 2 orchestrator wrote `batch-plan-round-2.md` to a relative path resolving inside the worktree (`/tmp/claude/overnight-worktrees/.../lifecycle/sessions/.../batch-plan-round-2.md`) instead of the main repo session dir. Runner checks only `$SESSION_DIR/batch-plan-round-$ROUND.md` (line 658). Contributing factor: misleading HTML comment in orchestrator-round.md lines 19-21 describes `{state_path}` as a relative path when it's actually absolute.

**Failure C — Unregistered event type crashes under set -e**
Even if A and B hadn't occurred, `log_event "orchestrator_no_plan"` at runner.sh:660 would have crashed the runner — `orchestrator_no_plan` is not in EVENT_TYPES (events.py:72-112), raising ValueError, killed by `set -e`.

### Evidence gathered

**Event log**: Last entry is `round_start` for Round 2. No `batch_assigned`, no `feature_start`.
**Worktree**: Still exists at `$TMPDIR/overnight-worktrees/overnight-2026-04-07-0008/`. Contains `batch-plan-round-2.md` in its own session dir.
**Integration branch**: `overnight/overnight-2026-04-07-0008` has Round 2 plan commit at 427c9f1.
**tmux**: `tmux list-sessions` returns "no server running".
**Lock file**: `.runner.lock` still contains dead PID 62057.
**Debug logs**: 13 logs from Round 1 (20:15-20:16), none after.
**No crash dumps**: No OOM, no signal kills in system logs.

## Phase 2 Findings

### Signal handling gaps (runner.sh)

| Signal | Trapped? | Effect |
|--------|----------|--------|
| SIGINT | Yes (line 505) | cleanup() runs |
| SIGTERM | Yes (line 505) | cleanup() runs |
| SIGHUP | **No** | Runner dies, children orphaned, no cleanup |
| EXIT | **No trap** | set -e deaths exit silently, no cleanup |

cleanup() (lines 449-503) kills children, removes lock, transitions to paused, logs circuit_breaker, generates morning report, sends notification. But it only runs for SIGINT/SIGTERM.

Watchdog PIDs (lines 612, 679) are NOT killed by cleanup() — orphaned on any signal.

### set -e danger zones

Lines 618-665 (post-orchestrator) and 685-862 (post-batch) have `set -e` on. Any python3 inline call or unregistered log_event kills the runner with no cleanup.

### Unregistered event types — 6 total

| Event type | Line | set -e? | Crash? |
|------------|------|---------|--------|
| `integration_worktree_missing` | 310, 312 | YES | YES — kills session at startup |
| `orchestrator_no_plan` | 660 | YES | YES — kills round loop (this crash) |
| `batch_runner_stalled` | 690 | YES | YES — kills stall recovery handler |
| `artifact_commit_failed` | 949 | NO | No, but notification lost |
| `push_failed` | 1067 | In `||` | No, but notification lost |
| `morning_report_commit_failed` | 1194, 1204 | NO | No, but notification lost |

### Batch plan path mismatch

- Prompt template (orchestrator-round.md:278) tells agent to use `Path("{state_path}").parent`
- `{state_path}` is substituted with absolute path by fill_prompt (runner.sh:362-374)
- But misleading HTML comment on lines 19-21 describes it as relative
- Orchestrator cwd is the worktree (runner.sh:583). Relative paths resolve there.
- `generate_batch_plan()` (batch_plan.py:48) has no absolute path assertion
- Runner checks only main repo path (line 658), no worktree fallback
- Round 1 agent followed prompt correctly; Round 2 agent deviated (LLM non-determinism)

## Current State

Root causes identified (3 independent failures). No fixes attempted yet.

### Fixes needed (priority order)

1. **Trap SIGHUP + EXIT** (runner.sh:505) — `trap cleanup EXIT` covers all exit paths
2. **Register 6 missing event types** in events.py EVENT_TYPES
3. **Guard all log_event calls** in bash with `|| true` — logging should never crash the runner
4. **Add `{session_dir}` substitution** to fill_prompt and update prompt template to use it directly
5. **Fix misleading HTML comment** in orchestrator-round.md:19-21
6. **Add absolute path assertion** in batch_plan.py generate_batch_plan()
7. **Add worktree fallback** for batch plan check at runner.sh:658
8. **Kill watchdog PIDs** in cleanup() alongside CLAUDE_PID and BATCH_PID
