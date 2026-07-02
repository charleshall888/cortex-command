---
schema_version: "1"
uuid: 4fed271e-9fd8-4e86-98b1-3c5efec3800f
title: Add observed-merge auto-close for morning-review already-merged exit
status: complete
priority: medium
type: feature
created: 2026-07-01
updated: 2026-07-02
parent: null
complexity: simple
criticality: high
spec: cortex/lifecycle/add-observed-merge-auto-close-for/spec.md
areas: ['skills']
lifecycle_phase: research
---
## Why
Removing morning-review's pre-merge auto-close (#342) leaves one rare intersection uncovered: when a completed feature's mid-session `status: complete` write throws (`BACKLOG_WRITE_FAILED`) AND its PR is later merged out-of-band, the PR-merge step stops at "PR already merged" before the post-merge closer runs, so the ticket lands on main but is never closed. #342 makes this non-silent (a verify-closure advisory) but deliberately defers the actual auto-close.

## Role
Make the "PR already merged — main is up to date" exit's advisory correct and actionable rather than adding an automatic close: tell the operator that local main is stale here (the post-merge sync is skipped on this exit), name this session's completed-feature tickets to check after fetching, and point to the existing post-merge closer for any still open. Research for this item found an automatic close is not cheaply or safely achievable at this exit, so the durable observed-merge closer, stranded-merged-work reconciliation, and the backlog-id-resolution hardening moved to the follow-up #346.

## Integration
Builds on #342's single-source post-merge closure. The already-merged exit stops with a verify-closure advisory; this item makes that advisory fetch-first and ticket-specific (local is stale on this exit) without adding a close. The actual verify-then-close, gated on a durable remote on-main signal, moved to #346. Must preserve the post-merge closer's idempotence and the merge-is-terminal-event convention (ADR-0004 / project.md).

## Edges
- Local main is stale on this exit (the post-merge sync is skipped), so the advisory must tell the operator to fetch before checking any ticket.
- Advisory only: the exit must not run an automatic close, and must not print the close command literal in a way that regresses the post-merge closure-ordering guard.
- The automatic close, stranded-work reconciliation, and cross-repo / id-resolution concerns are deferred to #346, not addressed here.

## Touch points
- `skills/morning-review/references/walkthrough.md` — the PR-merge exits (the "PR already merged" advisory added by #342) and the post-merge closer that #342 single-sourced closure to.
- `skills/morning-review/SKILL.md` — the post-merge closure breadcrumb #342 left in Step 6.
