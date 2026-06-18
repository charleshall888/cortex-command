---
schema_version: "1"
uuid: 1f5eb8a9-2152-4bfb-9331-b85af9c0c72d
title: 'Overnight run-now runner left session ''executing'' after orchestrator silently stopped; worker_no_exit_report did not trip the #262 circuit breaker'
status: complete
priority: high
type: bug
created: 2026-06-17
updated: 2026-06-18
complexity: complex
criticality: high
spec: cortex/lifecycle/overnight-run-now-runner-left-session/spec.md
areas: ['overnight-runner']
lifecycle_phase: plan
---
**Why:** In wild-light overnight session `overnight-2026-06-17-1821` (2026-06-17, **run-now** path, cortex-CLI runner), the session was left in `phase: executing` with no live runner, no watchdog fire, and no morning report — the same "left executing / silent stop" failure class as #039/#278, recurring on the cortex-CLI run-now path. Evidence from the session logs:
- `overnight-events.log` last event `19:00:37Z`; `pipeline-events.log` shows worker agents still active until `19:58Z` — the orchestrator/event-logging layer stopped ~58 min before the workers did, and the 30-minute event-silence watchdog never fired (at review time `cortex overnight status` showed "52m since last event, fires at 30m"). An **in-process watchdog cannot fire once its host stops** — it needs an out-of-process liveness check.
- **5× `worker_no_exit_report`** events fired (round 2: `actor-render-batching` tasks 3, 4, 10, 11; `perf-instrumentation` task 1) yet the session did **not** halt. #262 (complete) added `worker_no_exit_report` to `_SESSION_HALT_ERROR_TYPES` (Slice A) precisely to bail loudly on this — so either that halt path regressed, is not reached on the run-now cortex-CLI orchestrator, or `result.error` was not set on the no-exit branch (the Slice A caveat) and the orchestrator check never fired. The breaker that was supposed to catch exactly this did not.
- `runner-stderr.log`: `runner: plan commit failed for session=… rc=1` (round-2 plan commit).
- `runner.pid` records pid/pgid `28888`, but `28888` was already dead immediately after `cortex overnight start` returned `pid=28888` (it is a launcher/detach artifact), so `runner.pid`-based liveness reads "dead" even while the session runs — dead-runner detection is unreliable (relevant to #277's P2 status states).

**Role:** Make the run-now cortex-CLI runner fail loudly and clean up when its orchestrator stops: escalate on `worker_no_exit_report` (honor #262), detect orchestrator death via an out-of-process liveness check rather than an in-process watchdog, transition the session out of `executing` (paused/failed) and write a (partial) morning report, and reap orphaned worker agents.

**Integration:**
- Verify #262 Slice A actually fires on the cortex-CLI run-now orchestrator — confirm `feature_executor` sets `result.error = "worker_no_exit_report"` and the orchestrator halt check consumes it on this path. The 5× no-exit-no-halt here is the regression signal.
- Move the 30-minute event-silence watchdog out-of-process (or have `cortex overnight status` / a launchd guardian check `runner.pid` liveness) so orchestrator death is caught (ties to #001 process-group kill and #277 P2 liveness/status states).
- On orchestrator stop, transition phase off `executing` and emit a partial morning report + reap worker agents — confirm the #039/#278 "left executing" fixes cover the cortex-CLI run-now path, not only `runner.sh`/launchd.
- `runner.pid` should record the live session-leader pid, not the transient launcher, so liveness checks are meaningful.

**Edges:**
- This is the cortex-CLI runner (`cortex overnight start`), not the legacy `runner.sh`/`batch_runner.py` that #039/#001 patched — confirm those fixes were ported.
- Distinct from #277 (scheduled-path `setsid`/launchd silent-kill): this was the **run-now** path, which #277 reported produced a proper `STAT Ss` session leader — yet it still ended silently mid-run.
- A contributing trigger was a wild-light-side pre-commit gate blocking all worker commits (filed in the wild-light backlog) — but the harness response (no halt, no report, orphans, left `executing`) is the defect this ticket tracks.
- Non-goal: the wild-light gate fix; the opaque-failed-task-output capture (companion cortex-command ticket).