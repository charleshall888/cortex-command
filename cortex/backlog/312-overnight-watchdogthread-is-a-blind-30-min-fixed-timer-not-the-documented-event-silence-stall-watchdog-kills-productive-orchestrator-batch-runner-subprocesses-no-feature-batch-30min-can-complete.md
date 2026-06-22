---
schema_version: "1"
uuid: 0cbb3a1d-3efb-4710-bd62-52e030763bdd
title: Overnight WatchdogThread is a blind 30-min fixed timer (not the documented event-silence/stall watchdog) — kills productive orchestrator/batch_runner subprocesses; no feature batch >30min can complete
status: backlog
priority: high
type: bug
created: 2026-06-22
updated: 2026-06-22
---
**Why:** The overnight runner's `WatchdogThread` (`cortex_command/overnight/runner_primitives.py`) is documented as a "Stall-detection watchdog" and its kill path logs `"event log silence (stall timeout)"`, but the implementation **monitors nothing** — it is a flat fixed-duration timer. `run()` only ever does `elapsed += poll_interval` and calls `_kill_for_stall()` once `elapsed > timeout_seconds` (`STALL_TIMEOUT_SECONDS = 1800.0`, `runner.py:87`). It never reads an event log, file mtime, or any progress/activity signal, and never resets `elapsed`. Result: **every orchestrator and batch_runner subprocess is hard-killed at exactly 30 minutes regardless of how productively it is working** — so any feature (or batch) that legitimately needs >30 min can never complete.

**Evidence** (wild-light run-now session `overnight-2026-06-22-1106`):
- `pipeline-events.log`: feature `re-tune-late-join-probe-for` emitted `dispatch_progress` continuously until **11:40:49** (last content: *"Now I'll make all the edits. Starting with the constants"*) — i.e. actively implementing.
- `overnight-events.log`: `batch_runner_stalled` + `circuit_breaker` + `session_complete` at **11:41:07**; `paused_reason: stall_timeout`.
- Round-1 batch_runner spawned ~11:11 → killed 11:41:07 = **exactly 30:00** = `STALL_TIMEOUT_SECONDS`.
- The healthy worker was killed **18 seconds** after its last progress message — not a stall, a deadline.
- Confirmed identical in installed `2.27.1` AND clone HEAD (`runner_primitives.py::WatchdogThread.run`), so unfixed.

**Corrects #308's premise:** #308 refers to "the 30-minute event-silence watchdog" — but the watchdog is NOT event-silence-based; it monitors no events. The two failure modes share one root defect: (a) it kills productive long batches (this ticket); (b) it cannot detect a genuinely-stopped host because it watches nothing (the out-of-process-liveness gap #308 describes).

**Fix direction:** make `WatchdogThread` reset `elapsed` to 0 whenever the watched activity signal advances — e.g. poll the worker-driven `pipeline-events.log` mtime/size each tick and reset on growth (true "event log silence" per its own docstring). Heartbeats (~5 min) + `dispatch_progress` would then keep a productive batch alive while a genuine 30-min silence still trips. The signal must be one the *worker* writes (`pipeline-events.log`), not the watchdog's own parent (heartbeats die with the host — #308). Merely raising the cap is not the fix; activity-aware reset is.

**Role:** developer running overnight sessions (any path — run-now or scheduled).

**Integration:** `overnight/runner_primitives.py::WatchdogThread`; `overnight/runner.py` orchestrator-watchdog (1506) + batch_runner-watchdog (1717) wiring; `STALL_TIMEOUT_SECONDS`.

**Edges / non-goals:** not the launchd `project_root=/` bug (#311); not a real worker hang (the worker was provably alive at kill time). Do not merely raise the timeout.