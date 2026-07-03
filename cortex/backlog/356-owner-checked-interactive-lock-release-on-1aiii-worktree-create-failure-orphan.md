---
schema_version: "1"
uuid: adc22833-5cd8-41d6-ac04-a504dbd57c84
title: Owner-checked interactive-lock release on 1a.iii worktree-create-failure orphan
status: complete
priority: low
type: bug
created: 2026-07-02
updated: 2026-07-03
---
## Why
The interactive-worktree implement flow acquires the per-feature lock, then creates the git worktree in a later step. If the worktree create aborts (create failure, `worktree_escapes_repo` containment rejection, or any non-zero exit), the flow exits with the lock still held — orphaning it on **both** entry modes (picker-`selected` and branch-mode-`suppressed`, unified post-#355). This is pre-existing and was **not** fixed by #348 or #355: both closed the *overnight-guard-reject* orphan by moving the acquire behind the overnight guard, but the worktree-create-failure orphan sits *after* the acquire, so no acquire reorder can reach it. Residual is a self-block on retry until stale recovery reclaims the lock — the same hazard class #355 closed for the guard-reject path.

## Role
Close the last orphan window on the interactive-worktree acquire path: on any worktree-create abort, release the lock the flow already acquired, so a failed create never leaves a held lock. The affordance is unchanged — a live same-slug interactive session still blocks a second one; only the failure exit stops orphaning.

## Integration
The release must be **owner-checked**. `release_lock(feature_slug)` in `cortex_command/interactive_lock.py` (verified) unlinks the lock file unconditionally — it takes no owner argument and does not compare the on-disk lock's owner session to the caller before removing it. Because `acquire_lock` is a non-atomic read-then-replace with no exclusive-create flag, two same-slug `selected` sessions can both pass the acquire (it is git's worktree-path exclusivity, not the lock, that prevents the double worktree — see the #355 Edge Cases); a naive release-on-abort would then delete the *winner's* live lock. So this ticket needs an owner-checked release (compare owner session id, or a release-if-owner subcommand) before wiring the release into the worktree-create failure exit — a genuine design task, which is why it was deferred out of #355 rather than folded in.

## Edges
- Scope covers both entry modes symmetrically — post-#355 the acquire is unconditional, so a worktree-create abort on `selected` and `suppressed` leaks identically and the fix must cover both.
- The shipping `cortex-interactive-lock release {slug}` subcommand has no owner check today; adding the owner-checked variant is in scope.
- Do NOT weaken `acquire_lock`'s non-atomicity here — that is a separate concern #355 explicitly left unchanged; the owner check is precisely what makes the release safe under the existing double-pass.
- Low reachability: fires only when a worktree create fails after a successful acquire; stale recovery bounds the impact to a temporary self-block, not a permanent wedge.

## Touch points
- `skills/lifecycle/references/implement.md` §1a.iii (+ the byte-identical cortex-core mirror) — the worktree-create failure exit gains a release-on-abort for the lock acquired at §1a.ii.
- `cortex_command/interactive_lock.py` — add an owner-checked release path (an owner check on `release_lock`, or a new release-if-owner subcommand on `cortex-interactive-lock`).
- Parent context: #355 (selected-path guard-then-acquire reorder) and #348 (suppressed-path precedent).

## Resolution
Implemented directly (commit `c0d0abd9`), not through the lifecycle gate — the change was small and the one open design question (owner-check identity) resolved to the conservative `session_id`-only match. `release_lock_if_owner` / the `release-if-owner` subcommand unlink only when this session's `CLAUDE_CODE_SESSION_ID` owns the on-disk lock; §1a.iii's create-failure exit now calls it before exiting. The env-absent case is intentionally not cleaned up here — it degrades to the pre-existing stale-recovery-bounded behavior rather than risk deleting a co-passer's live lock. The pid+start_time fallback the ticket floated was dropped as unnecessary for that reason.
