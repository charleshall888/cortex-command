---
schema_version: "1"
uuid: be599732-2f99-43b0-b528-5c2ad1656328
title: "Surface aggregated signal on daytime-pipeline sandbox/EPERM cascade failures"
status: archived
priority: high
type: feature
created: 2026-05-20
updated: 2026-05-25
tags: [overnight-runner, pipeline, observability, sandbox]
discovery_source: cortex/research/harness-friction-triage/research.md
---
## Why

On 2026-05-16 the daytime pipeline ran 5 tasks for feature #209 (lead-refine-4-complexity-value-gate). All 5 hit Bash-sandbox-EPERM on every git commit attempt. Tasks 1-3 emitted exit-reports describing the failure as a per-task issue. Task 4 deferred with an operator question. Task 5 silently produced no exit report. The pipeline then paused on branch staleness — but the data loss had already happened: branch `pipeline/lead-refine-4-complexity-value-gate` is gone, `git fsck --lost-found` found no recoverable dangling commits for the touched files (`skills/refine/SKILL.md`, `skills/lifecycle/SKILL.md`, `tests/test_refine_skill.py`). Five tasks of agent work evaporated.

The failure mode is silent at the pipeline level: each task emits an individual failure (or doesn't), but no aggregated signal fires when the entire run is blocked on the same systemic issue.

Live evidence the broader sandbox problem persists: `cortex/lifecycle/seatbelt-probe.log` shows 10+ `seatbelt_probe` failures with `result: failed` between 12:31-12:32 on 2026-05-20 (today), `softfail_active: false`. Commit `a338437c` excluded `git:*` from sandbox restrictions which may help the specific git-commit failure mode, but the seatbelt-probe layer is still reporting hard failures.

## Role

Detect when N consecutive task agents in a single pipeline session hit the same systemic failure (Bash-sandbox-EPERM, seatbelt-probe-fail, etc.) and surface a single loud aggregated signal — pipeline-aborted with cause — rather than letting each task silently fail. Optionally pause the pipeline before further task dispatch when the threshold trips, so subsequent tasks don't continue against a known-broken environment.

## Integration

Sits inside the daytime/overnight pipeline orchestrator. Reads per-task exit reports (or their absence — the `worker_no_exit_report` event is itself a signal). Emits a new `pipeline_systemic_failure` event with cause and task-count fields. The morning report and operator notifications subscribe to this event.

## Edges

- Breaks if exit-report schema gains a new failure-cause field that the detector can't recognize.
- Threshold tuning matters: too tight produces false alarms, too loose lets cascades complete.
- Companion observability work: `worker_no_exit_report` is currently silent at the pipeline level; the detector should treat it as an actionable signal.

## Touch points

- `cortex_command/overnight/batch_runner.py` or successor module
- Exit-report schema and `worker_no_exit_report` event handling
- `bin/.events-registry.md` (register the new event)
- `cortex/lifecycle/seatbelt-probe.log` (recent failures dated 2026-05-20)
- `cortex/lifecycle/lead-refine-4-complexity-value-gate/exit-reports/` (historical — now cleaned, but the failure pattern was documented in those reports)
- Commit `a338437c` (Pass excludedCommands=['git:*'] to orchestrator + feature-worker sandboxes — partial mitigation already shipped)