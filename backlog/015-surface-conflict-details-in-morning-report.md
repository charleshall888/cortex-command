---
schema_version: "1"
uuid: c4d5e6f7-a8b9-0123-cdef-456789012345
id: 015
title: "Surface conflict details inline in morning report"
type: chore
status: complete
priority: high
parent: 014
tags: [overnight, merge-conflicts, morning-report]
created: 2026-04-03
updated: 2026-04-03
discovery_source: cortex/research/overnight-merge-conflict-prevention/research.md
session_id: null
lifecycle_phase: research
lifecycle_slug: surface-conflict-details-inline-in-morning-report
complexity: simple
criticality: medium
spec: cortex/lifecycle/archive/surface-conflict-details-inline-in-morning-report/spec.md
---

# Surface conflict details inline in morning report

## Context from discovery

When a feature is paused due to a merge conflict, the morning report currently shows the paused feature with a generic error string and a pointer to the log. The user must manually trace `overnight-events.log` to find the root cause.

The data needed is already present: `batch_runner.py:_apply_feature_result()` writes a `merge_conflict_classified` event with `details.conflicted_files` (list) and `details.conflict_summary` (human-readable string) to the event log. `collect_report_data()` in `report.py` already loads all events into `data.events`. The `_render_failed_features()` function already iterates `data.events` to count retries — the data is in memory, just not extracted.

Key files: `cortex_command/overnight/report.py`, `cortex_command/overnight/batch_runner.py`

## Findings

- `OvernightFeatureStatus` has no `conflict_summary` or `conflicted_files` fields — only `error`, `recovery_attempts`, `recovery_depth`. No state schema change is needed.
- The join between event data and the state feature dict is by feature name string. The event's `feature` field (written at `batch_runner.py:1356`) must match the key in `data.state.features` exactly. Implementation must verify this normalization before shipping, or the fix silently produces no output.
- Backlog 002 is adjacent (surfaces no-commit failure root causes). These may be combined or tracked separately.
