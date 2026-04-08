---
schema_version: "1"
uuid: dbcc91e6-8113-4f08-bdde-9f39e4a9bd7d
title: "Fix overnight runner resume: round restart, status overwrite, and missing round filter"
status: complete
priority: critical
type: bug
tags: [overnight, reliability, runner]
areas: [overnight-runner]
blocked-by: []
created: 2026-04-07
updated: 2026-04-07
session_id: null
lifecycle_phase: complete
lifecycle_slug: fix-overnight-runner-resume-round-restart-status-overwrite-and-missing-round-filter
complexity: complex
criticality: high
---

After fixing #039's crash bugs and resuming session `overnight-2026-04-07-0008`, the runner re-dispatched already-merged Round 1 features, corrupting their status. The resume path doesn't work. Full investigation in `debug/2026-04-07-overnight-round2-crash.md`.

## Bug 1: Runner hardcodes ROUND=1 (runner.sh:519)

On resume, the runner always starts at Round 1 regardless of `state.current_round`. Should read `current_round` from state and start there, skipping completed rounds.

## Bug 2: No round filtering in feature dispatch

The orchestrator prompt (orchestrator-round.md:154,201,207) mentions `round_assigned == current_round` but never implements the filter in code. All pending/paused features get dispatched regardless of their round assignment. The orchestrator should only dispatch features whose `round_assigned` matches the current round.

## Bug 3: map_results overwrites merged status

When re-dispatched features hit the no-commit guard and pause, `map_results.py:98-104` updates the state file, overwriting the `merged` status from the original run. Already-terminal features (merged, failed) should not have their status overwritten by a re-dispatch.

## Bug 4: Negative merged count

`MERGED_BEFORE` (runner.sh:525-530) counted the 2 merged features from the original run. After re-run paused them, `MERGED_AFTER` was 0. Result: `merged_this_round = 0 - 2 = -2`. The arithmetic assumes monotonically increasing merged count, which breaks on resume.
