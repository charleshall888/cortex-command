# Debug Session: Overnight runner silent crash and resume failure
Date: 2026-04-07
Status: In progress

## Phase 1 Findings (Crash — resolved via #039)

### Observed behavior
Session completed Round 1 (2 features merged), logged `round_start` for Round 2, then died silently. Three independent failures converged: SIGHUP not trapped, batch plan written to worktree, unregistered event types crash under set -e. Full details in ticket #039.

## Phase 1 Findings (Resume failure — current investigation)

### Observed behavior
After fixing #039 and resuming the session, the runner:
1. Started at Round 1 instead of Round 2
2. Re-dispatched the two already-merged features
3. Both features paused with "no changes produced" (no-commit guard)
4. `map_results` overwrote their `merged` status with `paused`
5. `merged_this_round` became -2 (negative count)
6. Round 2 orchestrator also failed (exit_code 1)

### Root causes

**Bug 1: Runner hardcodes ROUND=1 (runner.sh:519)**
On resume, the runner always starts at Round 1 regardless of `state.current_round`. It should read the current round from state and skip completed rounds.

**Bug 2: No round filtering in feature dispatch**
The orchestrator prompt (orchestrator-round.md:154,201,207) mentions `round_assigned == current_round` but never implements the filter. All pending/paused features get dispatched regardless of round assignment.

**Bug 3: map_results overwrites merged status**
When re-dispatched features pause, `map_results.py:98-104` updates the state, overwriting the `merged` status from the original run. This is data loss.

**Bug 4: Negative merged count**
`MERGED_BEFORE` (line 525-530) counted the 2 merged features from the original run. After re-run paused them, `MERGED_AFTER` was 0. `merged_this_round = 0 - 2 = -2`.

### Evidence
- Event log: `round_start` for Round 1 (not 2) at 22:02:31
- Event log: `batch_assigned` re-dispatched Round 1 features at 22:02:35
- Event log: `feature_paused` with no-commit guard at 22:02:35
- Event log: `merged_this_round: -2, merged_total: 0`
- State file: features show `paused` instead of `merged`
- runner.sh:519: `ROUND=1` hardcoded
- Integration branch still has all Round 1 commits intact

## Current State

Root causes identified (4 bugs in resume path). No fixes attempted yet. These should be added to ticket #039 or a new ticket.
