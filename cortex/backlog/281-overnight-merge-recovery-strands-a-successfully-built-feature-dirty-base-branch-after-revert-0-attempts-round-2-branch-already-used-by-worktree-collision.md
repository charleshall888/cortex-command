---
schema_version: "1"
uuid: 9486d024-5a83-4382-874c-6c3f4448bfdc
title: "Overnight merge-recovery strands a successfully-built feature: 'dirty base branch after revert' (0 attempts) + round-2 'branch already used by worktree' collision"
status: complete
priority: high
type: bug
created: 2026-06-02
updated: 2026-06-03
complexity: complex
criticality: high
spec: cortex/lifecycle/overnight-merge-recovery-strands-a-successfully/spec.md
areas: ['overnight-runner']
lifecycle_phase: plan
---
**Why:** In overnight session `overnight-2026-06-02-1312` (2026-06-02), feature 025 (`build-the-grinder-agnostic-knowledge-layer`) implemented its **full spec correctly** — 12 clean commits, +520/-24 across 12 files (notation contract, DF64V quick-ref + deep-dive companion, per-grinder template, CLAUDE.md index entry, and the de-Setting of 6 shared knowledge files) on `pipeline/build-the-grinder-agnostic-knowledge-layer`. But it **never merged**, and the session reported `0/3` and opened a `[ZERO PROGRESS]` PR. The merge layer failed in two stages:

1. **Round 1 — dirty-base precheck hard-pause.** `pipeline/merge_recovery.py::attempt_merge_recovery` runs a dirty-base check (`git status --porcelain --untracked-files=no` at the repo root from `git rev-parse --show-toplevel`) as step 1 ("ensure the repo root is clean after the revert"). It found the base dirty and returned `paused=True, attempts=0, error="dirty base branch after revert"` — it never entered the flaky-guard or repair cycle. A revert preceded the check and left the base dirty; the precheck then aborts.
2. **Round 2 — worktree/branch collision on retry.** The runner re-dispatched the paused 025, which tried to `git checkout overnight/overnight-2026-06-02-1312` but it was `already used by worktree at /tmp/.../overnight-worktrees/overnight-2026-06-02-1312` (the long-lived integration worktree owns the integration branch). → `feature_paused` again → two zero-progress rounds → `circuit_breaker (stall)` → `session_complete 0/3`.

Net: a feature that built perfectly is **stranded**; its work survives only on the pipeline branch (recoverable by hand), while the automation reports total failure. This is **downstream of #278** (now fixed) — with dispatch fixed, features actually build, which exposes this merge-layer defect.

**Role:** A successfully-built feature must be able to merge (or at least surface as "built, merge-blocked, recoverable on branch X" rather than a stall + zero-progress PR). The dirty-base precheck and the retry path conspire to permanently strand built work.

**Integration (fixes):**
- **Dirty-base precheck.** Determine *why* the base is dirty after the revert. Candidates: (a) the revert/merge ran against the wrong tree — the check uses `git rev-parse --show-toplevel` from whatever cwd, which may resolve to the main repo root rather than the integration worktree; (b) the revert genuinely left uncommitted changes; (c) ignored/symlinked files reading as dirty. Either deterministically clean the base (`reset --hard` to the pre-merge ref) before the precheck, or scope the cleanliness check to the integration worktree explicitly. Pausing with `attempts=0` on a built feature is the wrong default.
- **Retry / worktree-branch collision.** When re-dispatching a paused feature, do not try to check out the integration branch the integration worktree already holds. The dispatch/worktree resolver must detect "branch checked out elsewhere" and reuse that worktree, use a detached checkout, or skip re-dispatch of an already-built-but-merge-blocked feature. This collision is structural: the integration worktree owns `overnight/<id>` for the whole session, so any path that checks out that branch in another worktree collides — audit all such call sites.
- **Reporting.** The morning report/status must distinguish "built but merge-blocked (recoverable on `pipeline/<feature>`)" from "never built", and not open a `[ZERO PROGRESS]` PR when a feature branch has a complete implementation.

**Edges:**
- 025's complete implementation lived on `pipeline/build-the-grinder-agnostic-knowledge-layer` (12 commits); a manual PR recovers it. The automation should surface this, not bury it as 0/3.
- Only reachable after #278's fix (dispatch no longer crashes → features build → merge path exercised). Likely latent for any feature that hits the revert/merge-recovery path.
- Repro: force a post-merge test failure (or whatever triggers the pre-recovery revert) with the integration worktree active; the dirty-base precheck pause + round-2 checkout collision reproduce the stall.
- Sibling-blocked features compound it: 026/027 are `blocked-by: 025`, so 025 stranded → whole session 0/3.

**Touch-points:**
- `cortex_command/pipeline/merge_recovery.py` (dirty-base precheck ~L246–261; `repo_root`/`repo_path` resolution; the `attempts=0` pause).
- `cortex_command/pipeline/merge.py` (`merge_feature` — the revert-on-failure that leaves the base dirty).
- `cortex_command/pipeline/worktree.py` + `cortex_command/overnight/outcome_router.py` (re-dispatch of paused features; integration-branch-already-checked-out-in-worktree collision).
- `cortex_command/overnight/runner.py` (round-2 retry of paused features; circuit-breaker treating built-but-unmerged as zero progress).
- `cortex_command/overnight/report.py` / status rendering + the `[ZERO PROGRESS]` PR creation path.