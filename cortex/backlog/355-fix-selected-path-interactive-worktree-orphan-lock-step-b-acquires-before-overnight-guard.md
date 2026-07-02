---
schema_version: "1"
uuid: 4cb85bf0-2e94-41e9-aa15-8e1fa416e7e9
title: 'Fix selected-path interactive worktree orphan-lock: Step B acquires before overnight guard'
status: backlog
priority: low
type: bug
created: 2026-07-02
updated: 2026-07-02
---
## Why
The interactive worktree implement flow (skills/lifecycle/references/implement.md) acquires the per-feature lock at Step B on the picker-selected path, before the overnight concurrent guard runs during interactive worktree preflight. When the overnight guard rejects (overnight became live between the acquire and the guard), the acquired lock is never released — release_lock in cortex_command/interactive_lock.py is not invoked anywhere in the skill flow — so the session holds a lock for a worktree it never created. The same session then self-blocks on retry, and concurrent sessions read the lock as LIVE until the owner process dies (stale recovery). Ticket 348 fixed the equivalent ordering on the suppressed branch-mode path (a change local to the interactive worktree preflight, no Step B edit) but carved out the selected-path case, because it requires reordering the Step B acquire relative to the overnight guard — a change to the picker-selected preflight sequence beyond that ticket's trim + dead-check charter.

## Role
The selected path's acquire ordering comes into line with the suppressed path that 348 corrected: the overnight liveness guard precedes the interactive lock acquisition, or the lock is released on the overnight-reject exit. The affordance is unchanged — a live same-slug interactive session still blocks a second one; only the failure path (overnight-reject after acquire) stops orphaning the lock.

## Integration
Step B runs in the branch-selection preflight, and the overnight guard runs later inside interactive worktree creation (after the worktree preconditions), so the two guards are separated by the branch-mode routing. The picker fire-condition and the branch-mode wiring test (tests/test_lifecycle_implement_branch_mode.py) pin the picker-decision surface, not the acquire / overnight-guard ordering, so the change sits below that test's contract. The suppressed-path ordering fix from 348 is the reference pattern.

## Edges
- release_lock exists in cortex_command/interactive_lock.py but is unused in the skill flow; either wiring it on the reject exit or reordering the two guards resolves the orphan — the design choice belongs to this ticket's research.
- Low reachability: the orphan fires only when overnight becomes live between the acquire and the overnight guard on the selected path; the window is narrow.
- Stale recovery clears the orphan once the owner process dies, so the impact is a temporary self-block, not a permanent wedge.

## Touch points
- skills/lifecycle/references/implement.md (§1 Step B and §1a-ii ordering on the selected path)
- cortex_command/interactive_lock.py (release_lock, currently unused in the skill flow)
- plugins/cortex-core mirror (same commit as the implement.md edit)
- tests/test_lifecycle_implement_branch_mode.py (picker-decision contract — verify unaffected)