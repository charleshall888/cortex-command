---
schema_version: "1"
uuid: d5e6f7a8-b9c0-1234-def0-567890123456
id: 016
title: "Add recovery guidance to morning report for conflicted features"
type: chore
status: complete
priority: high
parent: 014
tags: [overnight, merge-conflicts, morning-report, dx]
created: 2026-04-03
updated: 2026-04-03
discovery_source: cortex/research/overnight-merge-conflict-prevention/research.md
session_id: null
lifecycle_phase: complete
lifecycle_slug: add-recovery-guidance-to-morning-report-for-conflicted-features
complexity: simple
criticality: medium
spec: cortex/lifecycle/archive/add-recovery-guidance-to-morning-report-for-conflicted-features/spec.md
---

# Add recovery guidance to morning report for conflicted features

## Context from discovery

After a merge conflict, the git state is actually recoverable: feature branches (`pipeline/{feature}`) are intact with all commits preserved, and the base branch is cleanly aborted (`git merge --abort` runs in `conflict.py`'s finally block). But no guidance appears anywhere the user sees in the morning.

The user must independently figure out the branch names, the conflict files, and what to do next. This creates friction and delays recovery.

## Findings

For each feature paused due to a conflict, the morning report should include a recovery block. Suggested content:

- Branch name: `pipeline/{feature}`
- Conflicted files (available from event log — see ticket 015)
- Suggested next action: one of "re-enqueue for next overnight session", "resolve manually and re-enqueue", or contextually appropriate guidance based on conflict classification

Key files: `cortex_command/overnight/report.py`

## Notes

- This ticket depends on the event log join work in 015 (conflicted files are needed for recovery guidance)
- Keep the recovery block minimal — this is a formatting concern, not a new workflow
