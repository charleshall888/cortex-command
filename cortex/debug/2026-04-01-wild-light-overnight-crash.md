# Debug Session: Wild-Light Overnight Session Crash
Date: 2026-04-01
Status: Escalated — deletion cause unresolved

## Phase 1 Findings

- **Observed behavior**: Runner launched at 13:37 EDT but crashed immediately; all features remain pending; tmux session exited.
- **Evidence gathered**:
  - `overnight-events.log` has exactly two entries: `session_start` at 12:50 (bootstrap) and `session_start` at 13:37 (manual runner launch). Nothing in between.
  - `overnight-state.json`: phase `executing`, all 8 features `pending`, `current_round: 1`, `worktree_path: /var/folders/.../overnight-worktrees/overnight-2026-04-01-1650`
  - `git worktree list` in wild-light showed the worktree as `prunable` (directory gone, metadata stale)
  - `.runner.lock` contains PID `2505` — written by the manual runner before it crashed
  - Integration branch `overnight/overnight-2026-04-01-1650` still exists in wild-light
  - `git worktree prune` was already run during the first investigation pass, removing stale metadata
- **Crash mechanism (confirmed)**:
  - `runner.sh:543` logs `session_start` (explains the second log entry)
  - `runner.sh:552` runs `cd "$WORKTREE_PATH"` inside `set -euo pipefail`
  - The directory was gone → `cd` failed → script exited immediately
  - No trap handles ERR/EXIT; cleanup trap only handles SIGINT/SIGTERM; worktree removal only runs at natural loop exit (lines 1228–1230). None of these fire on `set -e` exit.
- **Dead-ends**:
  - `plan.py:initialize_overnight_state()` lines 361–363 deletes existing worktree before creating a new one — but only if a second bootstrap runs with the exact same `worktree_path`. Collision-avoidance uses the session *directory* path, not the worktree path, so a same-minute re-run would generate a different session ID and different worktree path. **Not the cause.**
  - `runner.sh` natural-exit cleanup (`git worktree remove --force`) only runs after the main loop completes. **Not the cause.**
  - SIGINT/SIGTERM cleanup trap transitions state to `paused` but does not remove the worktree. **Not the cause.**
  - No cron, hook, or scheduled script in cortex-command was found that cleans up `/tmp` or overnight worktrees. **Not the cause.**

## Phase 2 Findings

- **Deletion cause**: Unknown. The overnight system has no automatic code path that would delete the worktree in the 47-minute window between bootstrap (12:50) and runner launch (13:37).
- **`session_id: "manual"` in second event**: The runner's `log_event` shell helper doesn't pass a `session_id` arg; the events module falls back to `"manual"` (likely from `LIFECYCLE_SESSION_ID` env var being unset in the tmux session). This is a red herring — it doesn't affect the crash.
- **Most likely theories for deletion** (no definitive evidence for any):
  1. User ran a cleanup command (e.g., `rm -rf $TMPDIR/overnight-worktrees/...` or broader `$TMPDIR` cleanup) in the 47-minute window
  2. macOS periodic temp-file cleanup (unusual within 47 min, but possible if launchd ran a cleanup agent)
  3. A previous overnight tmux session that completed naturally and ran `git worktree remove --force` — but its WORKTREE_PATH would have been a different session ID, so this is unlikely

## Current State

Root cause of **crash**: confirmed — `cd "$WORKTREE_PATH"` at `runner.sh:552` failed because the directory was gone.

Root cause of **worktree deletion**: unknown. No code path in the overnight system causes this automatically. Most likely external action (user cleanup or system temp purge).

**Resiliency gap identified**: The runner has no guard for a missing worktree at startup. It silently crashes on `set -e` with no helpful error message and no recovery guidance. A `[[ -d "$WORKTREE_PATH" ]]` check before the `cd` with a clear recovery message would prevent user confusion.

## Recovery steps

The integration branch `overnight/overnight-2026-04-01-1650` still exists in wild-light. To resume:

```bash
# In the wild-light repo:
git worktree add /var/folders/1_/md_bhrsj6l132p60bdg134zh0000gq/T/overnight-worktrees/overnight-2026-04-01-1650 overnight/overnight-2026-04-01-1650

# Then re-launch the runner:
overnight-start /Users/charlie.hall/Workspaces/cortex-command/lifecycle/sessions/overnight-2026-04-01-1650/overnight-state.json 6h
```
