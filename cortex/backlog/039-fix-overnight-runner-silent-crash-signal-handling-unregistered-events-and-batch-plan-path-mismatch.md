---
schema_version: "1"
uuid: 4f9c2260-9a67-4fa9-954e-45ef1bf4d2e1
title: "Fix overnight runner silent crash: signal handling, unregistered events, and batch plan path mismatch"
status: complete
priority: critical
type: bug
tags: [overnight, reliability, runner]
areas: [overnight-runner]
blocked-by: []
created: 2026-04-07
updated: 2026-04-07
session_id: null
lifecycle_phase: review
lifecycle_slug: fix-overnight-runner-silent-crash-signal-handling-unregistered-events-and-batch-plan-path-mismatch
complexity: complex
criticality: critical
spec: cortex/lifecycle/archive/fix-overnight-runner-silent-crash-signal-handling-unregistered-events-and-batch-plan-path-mismatch/spec.md
---

Session `overnight-2026-04-07-0008` crashed silently after Round 1 completed. Three independent failures converged. Full investigation in `debug/2026-04-07-overnight-round2-crash.md`.

## Failure A: SIGHUP not trapped (runner.sh:505)

Trap only catches SIGINT/SIGTERM. tmux dying sends SIGHUP, runner dies without cleanup — no state transition to paused, no notification, no morning report, lock file left behind. Children survive as orphans (separate process group via `set -m`).

**Fix:** Add SIGHUP to the existing signal trap: `trap cleanup SIGINT SIGTERM SIGHUP`. Do NOT switch to `trap cleanup EXIT` — cleanup() and the normal exit path have overlapping-but-different responsibilities (paused vs. complete state, partial vs. full morning report), and making cleanup() safely idempotent across all 7 side effects is complex and error-prone. Adding SIGHUP to the existing trap is the minimal correct fix.

## Failure B: Batch plan written to worktree instead of main repo

Round 2 orchestrator wrote `batch-plan-round-2.md` to a relative path resolving in the worktree. Runner only checks `$SESSION_DIR` (main repo). Round 1 agent followed the prompt correctly; Round 2 didn't (LLM non-determinism).

**Fixes (priority order — mechanical guardrails first, prompt improvements second):**
1. Add absolute path assertion in `batch_plan.py` `generate_batch_plan()` — this is the only deterministic fix. Any caller passing a relative path fails immediately with a clear error.
2. Add worktree fallback check in runner.sh:658 — if batch plan not found at `$SESSION_DIR`, check `$WORKTREE_PATH/lifecycle/sessions/$SESSION_ID/` and move it with a warning.
3. Add `{session_dir}` variable to `fill_prompt` and update prompt to use it directly — reduces the derivation step the LLM can get wrong, but is probabilistic, not deterministic.
4. Fix or remove misleading HTML comment in orchestrator-round.md:19-21 that describes `{state_path}` as relative when it's actually absolute.

## Failure C: 6 unregistered event types crash under set -e

`log_event "orchestrator_no_plan"` at runner.sh:660 raises ValueError (not in EVENT_TYPES), killed by `set -e`. 3 of 6 unregistered types crash the runner; the other 3 lose notifications silently. The stall recovery handler itself crashes from this bug.

| Event type | Line | Crash risk |
|------------|------|------------|
| `integration_worktree_missing` | 310, 312 | HIGH — kills startup |
| `orchestrator_no_plan` | 660 | HIGH — kills round loop |
| `batch_runner_stalled` | 690 | HIGH — kills stall recovery |
| `artifact_commit_failed` | 949 | Low — notification lost |
| `push_failed` | 1067 | Low — notification lost |
| `morning_report_commit_failed` | 1194, 1204 | Low — notification lost |

**Fix:** Register all 6 event types in events.py EVENT_TYPES. Do NOT blanket-guard bash log_event calls with `|| true` — the events log is load-bearing (consumed by morning report, resume logic, watchdog). Swallowing all Python errors converts crash-visible failures into silently-missing-data, which is the exact class of problem this ticket is about. If a narrower guard is desired, catch only ValueError in the Python code rather than suppressing the entire invocation.
