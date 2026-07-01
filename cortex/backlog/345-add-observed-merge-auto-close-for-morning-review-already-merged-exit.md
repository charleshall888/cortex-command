---
schema_version: "1"
uuid: 4fed271e-9fd8-4e86-98b1-3c5efec3800f
title: Add observed-merge auto-close for morning-review already-merged exit
status: backlog
priority: medium
type: feature
created: 2026-07-01
updated: 2026-07-01
parent: "340"
---
## Why
Removing morning-review's pre-merge auto-close (#342) leaves one rare intersection uncovered: when a completed feature's mid-session `status: complete` write throws (`BACKLOG_WRITE_FAILED`) AND its PR is later merged out-of-band, the PR-merge step stops at "PR already merged" before the post-merge closer runs, so the ticket lands on main but is never closed. #342 makes this non-silent (a verify-closure advisory) but deliberately defers the actual auto-close.

## Role
Add observed-merge auto-close on the "PR already merged — main is up to date" exit: when this session completed features whose tickets are still open and whose work is confirmed present on main, close them. Also address the deferred siblings called out in #342: stranded-merged-work reconciliation (orphaned integration branches, PRs, and worktrees, plus no re-pick backoff) and the cross-repo bare-numeric-close hazard.

## Integration
Builds on #342's single-source post-merge closure. The already-merged exit currently stops with a verify-closure advisory; this ticket makes it verify-then-close for tickets provably on main. Must preserve the post-merge closer's idempotence and the merge-is-terminal-event convention (ADR-0004 / project.md).

## Edges
- Only close tickets whose completed work is confirmed on main (the out-of-band merge landed it) — never close on a merge this review cannot verify.
- Cross-repo bare-numeric-close hazard: a bare numeric slug can resolve to the wrong item across repos — disambiguate before closing.
- Idempotence: re-close on an already-complete ticket must remain a safe no-op.

## Touch points
- `skills/morning-review/references/walkthrough.md` — the PR-merge exits (the "PR already merged" advisory added by #342) and the post-merge closer that #342 single-sourced closure to.
- `skills/morning-review/SKILL.md` — the post-merge closure breadcrumb #342 left in Step 6.
