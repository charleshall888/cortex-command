# Complete Phase

Creates a PR, pauses for merge on GitHub, then finalizes on re-invocation. Run the Step 7 router first — it classifies the route.

**First-run PR flow** (`first_run`): read complete-first-run.md and follow its Steps 1–6.

**On-main short-circuit**: on `main`/`master` there is no PR for direct-to-main work — Step 7 classifies `on_main` and routes straight to Step 9 (skip the PR flow; pr.json absent, no orphan probe). Step 11a's artifact commit still runs.

## Re-invocation: State-Aware Routing

### Step 7 — State-Aware Routing

The classifier verb reads `events.log` and `pr.json` (querying `gh` only when a PR is in play) and prints one JSON verdict:

```bash
cortex-lifecycle-complete-route <slug>
```

Act on the verdict; do not re-derive it:

- **Terminal** (`message` non-empty, `continue_to: null`): print `message` verbatim and exit — the verb owns the exact recovery/wait text.
- **`continue_to` set** — continue at the named step: `already_complete` → **Step 12** (idempotent short-circuit: no re-cleanup, no duplicate `feature_complete`, no second `pr.json`); `on_main` → **Step 9**; `first_run` → **complete-first-run.md** (Steps 1–6); `merged_clean_ancestor` → **Step 8**.
- **`orphan_ambiguous`** (`continue_to: null`, `candidates` present): multiple orphan PRs match `interactive/<slug>` (slug reuse). Surface the candidates (PR number, state, `mergedAt`), ask which to use, write `pr.json` for it atomically, then re-run `cortex-lifecycle-complete-route <slug>` to classify the chosen PR's state.

---

### Step 8 — Worktree Cleanup

**Hard guard**: if `realpath "$PWD"` is inside the target worktree, exit with `cd out of the worktree before running cleanup; current PWD is the worktree being removed.` — do not auto-cd. The user exits (`ExitWorktree action="keep"` when EnterWorktree state is live, else `cd $(git rev-parse --show-toplevel)`) and re-invokes.

**Prefix check**: cleanup runs only for `interactive/`-prefixed worktrees — check `git worktree list --porcelain` for `.claude/worktrees/interactive-{slug}`. No match → skip silently.

**Gate** — both required, else skip with a warning naming the cause (dirty worktree, or non-ancestor branch not in origin/main): (1) `git status --porcelain --ignored=traditional` inside the worktree is empty; (2) `git merge-base --is-ancestor <branch-head> origin/main` succeeds.

**Call**: `cleanup_worktree(slug, branch=f"interactive/{slug}", force=False)`. No `force=True` — on failure, report and retain the worktree.

### Step 9 — Finalize

Resolve the backend once (`cortex-read-backlog-backend`, argless), then compose the write-back, index regen, and idempotent `feature_complete` emission in one call:

```bash
cortex-lifecycle-finalize --feature {slug} --backend {resolved-backend} --backlog-file {backlog-filename}
```

`{backlog-filename}` is the backlog file identified at lifecycle entry (`""` when no item was identified). Act on the JSON `state`:

- **`finalized`** (`cortex-backlog`/`none`) → the item was marked complete (`session_id=null`, index regenerated best-effort) and `feature_complete` was emitted or idempotently skipped → Step 11a.
- **`external-backend`** → the local write-back was skipped; make the equivalent completion update on the configured tracker best-effort per `backlog.instructions`. The event is still emitted → Step 11a.
- **`error`** → surface `message` and halt.

Exit code 2 → ambiguous backlog slug; apply the exit-2 rule in backlog-writeback.md (loaded at lifecycle Step 2). The verb reads the feature's counters (`tasks_total`/`rework_cycles`) itself.

<!-- finalization-commit-step -->
### Step 11a — Commit Finalization Artifacts

Run `cortex-read-commit-artifacts` (default true when absent).

**`false`**: skip the commit; note inline that lifecycle artifacts and any uncommitted source are left for the operator to commit deliberately.

**`true`**: stage the finalization set, then act on the verb's `signal`:

```
cortex-lifecycle-stage-artifacts --phase complete --feature {slug}
```

The verb owns the explicit-path staging and prints `signal` — the staging outcome, equivalent to `git diff --cached --quiet`:

- `nothing_staged` → skip `/cortex-core:commit` silently and continue to Step 12.
- `staged` → proceed to commit.

A non-zero verb exit is a staging failure: halt before Step 12 rather than commit a partial set.

Invoke `/cortex-core:commit` with an imperative ≤72-char subject. On non-zero exit, surface the error and stop before the Step 12 summary — do not imply the artifacts were committed until the commit succeeds. After a successful commit, if the branch is not `main` or `master`, advise: `Artifacts committed on <branch> rather than the default branch — move them to main if appropriate.` No automatic branch switch.
<!-- /finalization-commit-step -->

### Step 12 — Summarize and Preserve Lifecycle Directory

Brief summary: feature name + description, tasks completed, key files created/modified, any open or follow-up items. Preserve `cortex/lifecycle/{slug}/` as project history. Proceed automatically — emit the summary and exit.
