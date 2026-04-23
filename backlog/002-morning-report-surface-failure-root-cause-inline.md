---
id: 002
title: "Morning report: surface failure root cause inline instead of pointing to log files"
type: chore
status: complete
priority: high
tags: [overnight, morning-report, dx]
created: 2026-04-01
updated: 2026-04-06
session_id: null
lifecycle_phase: research
lifecycle_slug: morning-report-surface-failure-root-cause-inline
complexity: complex
criticality: high
spec: lifecycle/morning-report-surface-failure-root-cause-inline/spec.md
areas: [overnight-runner,report]
---

# Morning report: surface failure root cause inline

## Problem

When a feature fails overnight, the morning report says:

> completed with no new commits — check pipeline-events.log task_output and task_git_state events

This gives no actionable information. The user has to manually trace through events.log, branch history, and git log to find the root cause. In the 2026-04-01 session, this turned out to be a stale backlog item (feature was already merged to main in a prior session).

## Desired Behavior

The report generator should classify common failure modes and surface them inline:

- "Branch already exists with prior commits — feature was already implemented in a prior session"
- "No changes produced — backlog item may already be complete (check git log)"
- "Agent exited without committing — see task output below"
- "Plan generation failed — spec may be insufficient"

## Implementation Notes

The `no_commit_guard` in `batch_runner.py` already knows *why* it paused the feature. That reason should propagate through `overnight-state.json` into the morning report's Failed Features section rather than being flattened to a generic message.

Key files: `cortex_command/overnight/batch_runner.py`, `cortex_command/overnight/report.py`
