---
schema_version: "1"
uuid: 4cb85bf0-2e94-41e9-aa15-8e1fa416e7e9
title: 'Fix selected-path interactive worktree orphan-lock: Step B acquires before overnight guard'
status: complete
priority: low
type: bug
created: 2026-07-02
updated: 2026-07-02
lifecycle_phase: complete
lifecycle_slug: fix-selected-path-interactive-worktree-orphan
complexity: complex
criticality: high
spec: cortex/lifecycle/fix-selected-path-interactive-worktree-orphan/spec.md
areas: ['lifecycle']
---
## Why
On the picker-selected path of the interactive worktree implement flow (skills/lifecycle/references/implement.md), Step B acquires the per-feature lock. A Step A overnight check already precedes the acquire, so an overnight run that is live at entry is rejected before any acquire happens. But a second overnight concurrent guard runs later, during interactive worktree preflight; if overnight goes live in the window between the acquire and that second guard, the guard rejects while the acquired lock is never released — release_lock in cortex_command/interactive_lock.py is not invoked anywhere in the skill flow — so the session holds a lock for a worktree it never created. The same session then self-blocks on retry, and concurrent sessions read the lock as LIVE until the owner process dies (stale recovery). Because Step A already guards the common already-live case, this is a narrow TOCTOU race, not a deterministic orphan — the deterministic variant lived on the suppressed branch-mode path (no Step A) and was fixed by ticket 348. The selected-path case was carved out of 348 because reordering the acquire relative to the second guard changes the picker-selected preflight sequence, beyond that ticket's trim + dead-check charter.

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