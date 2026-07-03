---
schema_version: "1"
uuid: 6eb2c913-9f89-41d4-8404-38ef1d8ecc1e
title: Durable observed-merge closer + stranded-work reconciliation for morning-review
status: backlog
priority: low
type: feature
created: 2026-07-02
updated: 2026-07-02
---
## Why
The morning-review observed-merge advisory (#345) deliberately stops at a fetch-first manual advisory on the "PR already merged" exit, because a correct automatic close there is not cheaply achievable today: the post-merge sync step is skipped on that exit so the local checkout is stale, there is no push path on that exit to update main, and no durable remote signal exists to confirm a completed feature's work and ticket state on main. Research for #345 also surfaced two adjacent robustness gaps that were explicitly deferred: stranded merged work left behind on declined or abandoned integration branches, and an unstated assumption in the post-merge closer that a bare numeric backlog id always matches the current backlog numbering. These are recorded here so they are not lost.

## Role
Build the durable pieces #345 could not. First, a remote-authoritative on-main check — read the ticket's state as it exists on remote main, keyed off the merge commit — plus a push, so the already-merged exit can automatically close a genuinely-stranded completed-feature ticket instead of only advising. Second, stranded-merged-work reconciliation: detect and clean up orphaned integration branches, pull requests, and worktrees from declined or abandoned sessions, and add re-pick backoff so the overnight runner does not repeatedly re-select a feature whose work is stranded. Third, harden the post-merge closer's bare-numeric backlog-id resolution against a mismatched or renumbered backlog, since that assumption affects the existing closer, not only any new one.

## Integration
Builds on #345's fetch-first advisory and #342's single-source post-merge closure. The durable closer should replace the manual advisory only once the remote on-main check is proven reliable, and must preserve the post-merge closer's idempotence and the merge-is-terminal convention. The reconciliation and id-hardening pieces are independently shippable and may be decomposed into separate tickets during refine if they prove large.

## Edges
- Only close a ticket whose completed work is confirmed on remote main, never on a merge that cannot be verified against main.
- Reconciliation cleanup must skip on uncommitted or ambiguous state so it never destroys unrecovered work.
- Harden id resolution so a stale root or a renumbered backlog cannot close the wrong item; a re-close on an already-complete ticket stays a safe no-op.
- Re-pick backoff must not permanently strand a feature that could still legitimately be retried.

## Touch points
- `skills/morning-review/references/walkthrough.md` — the "PR already merged" exit and the post-merge closer (§6b).
- `cortex_command/overnight/outcome_router.py` — the session write-back and the `BACKLOG_WRITE_FAILED` path.
- `cortex_command/backlog/update_item.py`, `cortex_command/backlog/resolve_item.py` — bare-numeric backlog-id resolution.
- `cortex_command/overnight/` — integration branch/worktree lifecycle and re-pick logic.
- `cortex/lifecycle/add-observed-merge-auto-close-for/research.md` — the #345 research establishing why the automatic close was deferred.