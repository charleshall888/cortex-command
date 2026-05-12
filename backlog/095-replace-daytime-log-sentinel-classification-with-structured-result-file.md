---
schema_version: "1"
uuid: 7e7ecade-3fa3-4d9c-841f-8ed6141c4da8
title: "Replace daytime log-sentinel classification with structured result file"
status: complete
priority: high
type: feature
created: 2026-04-20
updated: 2026-04-21
parent: "93"
tags: [lifecycle, daytime-pipeline, observability, output-contract]
discovery_source: cortex/research/revisit-lifecycle-implement-preflight-options/research.md
areas: [overnight-runner]
complexity: complex
criticality: high
spec: cortex/lifecycle/archive/replace-daytime-log-sentinel-classification-with-structured-result-file/spec.md
session_id: null
lifecycle_phase: implement
---

# Replace daytime log-sentinel classification with structured result file

The current daytime pipeline result surfacing reads the last `"Feature "` line of `daytime.log` and classifies by substring (`merged successfully` / `deferred` / `paused` / `failed`). This is brittle against SIGKILL, OOM, stdout buffering, log rotation, and main-session crash + restart.

## Findings from discovery

Current behavior (`implement.md §1b vii`, `daytime_pipeline.py:322-351`):

- `run_daytime()` prints `"Feature {name} merged successfully."` or similar at the end of normal exit paths. Paths include lines 324, 328, 337, 348, 350.
- `print` is block-buffered on redirected stdout — SIGKILL/OOM/segfault can lose the unflushed sentinel entirely.
- The skill-side `finally` block in `run_daytime` runs *before* the final `print` — so atomicity is already broken.
- Main-session crash during polling + user restart: the subprocess completes, cleans up its PID file, and the skill's next invocation misreads the prior-run's log line as current (no freshness token).

`daytime-state.json` and `events.log` already carry structured state (`features_merged/paused/deferred/failed` with `error` fields), but the classifier ignores them. `bin/overnight-status` (in-repo prior art) reads structured state, not log tails.

## Research Context

See `research/revisit-lifecycle-implement-preflight-options/research.md` DR-2. A log-sentinel variant (`DAYTIME_RESULT {json}`) was considered and rejected: it inherits every failure mode of the current substring-match approach. The structured-file approach uses the same atomic-write primitive (`write-to-tempfile + os.replace`) that `save_state()` already uses.

## Acceptance

- Subprocess writes `lifecycle/{slug}/daytime-result.json` atomically at end-of-run with at least: `outcome` (merged/deferred/paused/failed), `pr_url`, `session_id` (or `start_ts`) as a freshness token, `end_ts`, `tasks_completed`, `commits`, `rework_cycles`, `deferred_files` (list).
- `implement.md §1b vii` reads `daytime-result.json` first; falls back to `daytime-state.json` if the result file is missing; falls back to log tail (current behavior) as last resort.
- Stdout buffering discipline addressed: `flush=True` on critical prints, or `PYTHONUNBUFFERED=1` in the subprocess launch.
- Freshness-token check in the skill: reject a result file whose `session_id`/`start_ts` doesn't match this dispatch's subprocess.

## Out of scope

- Progress rendering during the run (can be addressed separately).
- `bin/daytime-status` CLI (optional — decide in spec).
- Cost/token tracking (reserve the fields but do not populate).
- Any change to the pre-flight in `implement.md §1`.

## Spec-phase decisions

- Exact `daytime-result.json` schema.
- Freshness token format (UUID session_id vs. ISO 8601 start_ts vs. both).
- Whether to build `bin/daytime-status` or render inline in the skill.
