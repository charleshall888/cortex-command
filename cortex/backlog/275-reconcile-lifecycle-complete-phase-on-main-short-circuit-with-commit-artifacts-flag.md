---
schema_version: "1"
uuid: b7aaff1c-213c-4074-a0e8-11dea04e8547
title: "Reconcile lifecycle complete-phase on-main short-circuit with commit-artifacts flag"
status: complete
priority: medium
type: bug
created: 2026-06-01
updated: 2026-06-01
complexity: complex
criticality: high
spec: cortex/lifecycle/reconcile-lifecycle-complete-phase-on-main/spec.md
areas: ['lifecycle']
---
**Why:** The lifecycle Complete phase's on-main short-circuit (`skills/lifecycle/references/complete.md`) skips Steps 2-5 when the branch is `main`/`master`, jumping straight to Steps 9-12. Step 2 ("Commit Lifecycle Artifacts") is among the skipped steps, and Steps 9-12 (backlog write-back, index sync, `feature_complete`, summary) never commit the lifecycle dir. So on a trunk-based completion the implement/review/complete artifacts (updated `plan.md`, `events.log` through `feature_complete`, `review.md`, `index.md`, residue) are left uncommitted — even though `commit-artifacts` defaults to `true` and the Refine and Plan phases DO auto-commit their artifacts on main (post-refine-commit + the plan commit). Observed in lifecycle #274 (investigate-critical-review-telemetry-creating-phantom): the orchestrator had to commit the artifacts manually after Steps 9-12. The inconsistency is the crux — earlier phases commit on main, the complete phase does not.

**Role:** Close the inconsistency so trunk-based completions preserve design history the same way the PR flow and the earlier phases already do.

**Integration:** On main, still skip the PR ceremony (Steps 3-6) and worktree cleanup, but run an artifact-commit gated on `commit-artifacts=true`. Likely placement: after Step 11 (`feature_complete`) so the closing event is captured, bundling the lifecycle dir + backlog write-back (item .md status + regenerated `index.json`/`index.md`) into one "Complete lifecycle" commit. Reuse `cortex-read-commit-artifacts` and `/cortex-core:commit`.

**Edges:** Worktree / feature-branch paths already commit via Step 2 — only the on-main path is affected. Respect `commit-artifacts=false`. Avoid double-committing if a prior run already committed. `.session`/`.lock` stay uncommitted.

**Touch-points:** `skills/lifecycle/references/complete.md` (on-main short-circuit, Step 2, Steps 9-12). NOTE: this is a `skills/` edit, so the fix itself must run through a lifecycle.