---
schema_version: "1"
uuid: 29604a81-71cb-4b3f-9eef-9699ffdcee57
title: Fix feature_complete emission-ordering strand on Step-11a commit failure
status: backlog
priority: low
type: bug
created: 2026-06-29
updated: 2026-06-29
parent: 336
complexity: complex
criticality: medium
areas: ['lifecycle']
---
## Why

The lifecycle Complete phase emits `feature_complete` at Step 11 (`skills/lifecycle/references/complete.md`) **before** the Step-11a finalization commit. If that commit fails (pre-commit hook rejection, index lock, working-tree conflict) the phase halts — but `feature_complete` is already in the working-tree `events.log`. On re-invocation, `complete-route`'s Branch 2 short-circuits on the working-tree `feature_complete` to Step 12, so the finalization commit is **never retried**: the lifecycle artifacts stay uncommitted and the operator must commit them by hand. Rare (needs a commit failure) and manually recoverable, but a real correctness wart in the canonical multi-step Complete contract.

Split out of #331 (the complete.md offload) after critical review proved #331's spec-prescribed fix — "emit `feature_complete` only after a successful Step-11a commit" — is **itself buggy**: `events.log` is part of Step 11a's staged set, so emitting after the commit leaves the terminal row permanently uncommitted (a dirty working-tree line after *every* completion). The correct fix is a genuine design effort, not a one-line relocation, so it earns its own ticket. #331 migrates the `feature_complete` emission to the `cortex-lifecycle-event` verb **at today's ordering** (row stays committed, no regression); this ticket fixes the ordering correctness on top of that.

## Role

Make `feature_complete` presence iff the finalization commit landed (or there was nothing to commit), so a failed Step-11a commit leaves a recoverable, retry-able state rather than a Branch-2 strand — without leaving an uncommitted terminal row on the success path.

## Integration

Builds on #331 (which lands `complete-route` + the verb-based `feature_complete` emission). The structurally-correct fix lives in the **`complete-route` verb's Branch 2**: short-circuit (`already_complete` → Step 12) only when `feature_complete` is **committed** (present in `HEAD`'s `events.log`); when present in the working tree but not committed, route to finalization-retry instead. Pair with **idempotent emission** (emit `feature_complete` only if not already present) so the retry re-commits the existing row without duplicating it. Evaluate against the two-commit and emit-then-rollback alternatives — both have residual failure windows or fragile mutation, documented in #331's plan critical-review.

## Edges

- Worktree-interactive path: a failed Step-11a commit leaves a dirty tree → re-invocation currently routes Branch 4d (`merged_dirty`, "resolve first", terminal), so recovery there is via user-resolve-then-retry, not a clean auto-rerun — the fix must reconcile with 4d.
- on-main / trunk path: `on_main` → Step 9 re-runs 9–12 cleanly on retry.
- Must not duplicate `feature_complete` rows (metrics hard-indexes the corpus); emission must be idempotent.
- Must not regress the success path (today's committed-row behavior) — no permanently-dirty working tree.
- Keep `complete-route`'s golden route table coherent if Branch 2 gains a committed-vs-uncommitted distinction.

## Touch-points

- `cortex_command/lifecycle/complete_route.py` (Branch 2 committed-state check + new/extended route) + its golden-route-table test
- `skills/lifecycle/references/complete.md` (Step 11 idempotent-emission guard; Step 11a halt-path framing) (+ mirror)
- `tests/` (round-trip + commit-failure-recovery behavioral test — must be discriminating, not the self-sealing prose-only test #331's review flagged)
