---
schema_version: "1"
uuid: 8e3f7a21-5c9b-4d62-8e1a-6f2b4c9e7d33
title: "Operator gate: #088 baseline measurement window is complete"
status: backlog
priority: medium
type: task
created: 2026-04-21
updated: 2026-04-21
parent: "82"
tags: [opus-4-7-harness-adaptation, operator-gate]
blocked-by: []
areas: [pipeline]
---

# Operator gate: #088 baseline measurement window is complete

## Purpose

This is a **marker ticket** that exists solely to block `/overnight` auto-selection of #088 until the operator has finished the multi-day measurement window described in #088's Task 6.

`#088`'s plan (`lifecycle/collect-47-baseline-rounds-and-snapshot-the-aggregated-data/plan.md`) includes Task 6 — "Measurement window — user runs ≥2 clean overnight rounds" — which is operator-driven and multi-day. The overnight pipeline's `select_overnight_batch()` and `_is_eligible_for_overnight()` cannot distinguish operator-gated tasks from agent-executable ones; a worker that picks up #088 during the measurement window would either self-forge a `sha-round-*.txt` file (producing a corrupt baseline) or land Commit A on the session integration branch instead of `main` (mechanically violating spec R14). Listing this marker in #088's `blocked-by` forces the existing blocker gate (`claude/overnight/backlog.py:504-512`) to mark #088 ineligible until this ticket is flipped to a terminal status.

## Clearance criterion

Flip this ticket to `status: complete` when **all** of the following are true:

1. Commit A (pipeline instrumentation per #088 Task 5) has landed on `main`.
2. ≥ 2 clean rounds have completed per #088's Requirement 6 (zero `api_rate_limit` errors AND `SESSION_COMPLETE` event present AND no watchdog kill).
3. ≥ 2 corresponding `sha-round-{session_id}.txt` files exist in `lifecycle/collect-47-baseline-rounds-and-snapshot-the-aggregated-data/`.
4. Each clean round's recorded SHA is a descendant of Commit A (spot-check: `git merge-base --is-ancestor <commit-A-sha> $(cat sha-round-{session_id}.txt)` exits 0).

Once these four conditions are satisfied, the operator runs:

```
update-item 099-operator-gate-088-measurement-window-complete status=complete
```

This unblocks #088 so the snapshot-composition phase (Tasks 7–10) can proceed.

## Do not dispatch this ticket overnight

This ticket has no agent-executable work. It is a status marker that the operator toggles manually. Do not assign an `in_progress` or `refined` status to it.
