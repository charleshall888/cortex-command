---
schema_version: "1"
uuid: a436ae8a-b430-43f6-853d-a2e7c64f504c
title: "Fix overnight watchdog to kill entire process group on stall"
status: complete
priority: high
type: chore
created: 2026-04-01
updated: 2026-04-01
tags: [overnight, reliability, process-management]
complexity: simple
criticality: high
session_id: null
lifecycle_phase: implement
lifecycle_slug: fix-overnight-watchdog-to-kill-entire-process-group-on-stall
spec: lifecycle/fix-overnight-watchdog-to-kill-entire-process-group-on-stall/spec.md
---

# Fix overnight watchdog to kill entire process group on stall

## Problem

When the overnight watchdog fires after 30 minutes of event log silence, it sends
`kill "$target_pid"` (SIGTERM to a single PID) to `batch_runner.py`. This kills
only the Python process — all `claude` CLI subprocesses spawned by the SDK's
`anyio.open_process()` are orphaned and continue running indefinitely.

This was a contributing factor in the 2026-03-31 overnight hang (wild-light
backlog #121): even after the watchdog fired, the stuck `git commit` processes
survived because only `batch_runner.py` was killed, not its children.

## Root Cause

The entire overnight process tree shares one process group (runner.sh's PGID):

```
runner.sh (PGID leader)
  └─ python3 batch_runner.py (same PGID, backgrounded with &)
       └─ claude CLI (same PGID, via anyio.open_process, no start_new_session)
            └─ git commit → pre-commit → uv → lsp_diagnostics.py → Godot
```

- `batch_runner.py` has no signal handler or atexit cleanup for subprocesses
- The SDK's `SubprocessCLITransport.close()` (which sends SIGTERM to claude CLI)
  never fires when the parent is killed abruptly
- Using `kill -9 -$PGID` from the watchdog would kill runner.sh itself (it's the
  PGID leader), so that's not viable either

## Proposed Fix

Launch `batch_runner` with `setsid` so it gets its own PGID:

```bash
setsid python3 -m cortex_command.overnight.batch_runner ... & BATCH_PID=$!
```

Then the watchdog can kill the entire batch process group:

```bash
kill -- -$BATCH_PID   # kills batch_runner + all claude SDK children
```

This kills exactly the batch runner and all its descendants without touching
`runner.sh`.

The same pattern should apply to the orchestrator claude agent in the round loop.

## Affected Files

- `cortex_command/overnight/runner.sh` — watchdog kill logic, process spawning
- Possibly `cortex_command/pipeline/dispatch.py` — could add `start_new_session=True` to
  `anyio.open_process()` as defense-in-depth

## Acceptance Criteria

- After a watchdog timeout, no orphaned `claude` CLI processes remain running
- `runner.sh` itself survives the watchdog kill and can continue to the next round
  or generate the morning report
- The watchdog still functions correctly for the orchestrator agent (round loop)
