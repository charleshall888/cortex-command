# Complete Phase

Creates a PR, pauses for merge on GitHub, then finalizes on re-invocation.

### Step 7 — State-Aware Routing

```bash
cortex-lifecycle-complete-route <slug>
```

The verb reads `events.log` and `pr.json` (querying `gh` only when a PR is in play) and prints one JSON verdict. Act on it; do not re-derive it:

- **Terminal** (`message` non-empty, `continue_to: null`) → print `message` verbatim and exit; the verb owns the exact recovery or wait text.
- **`first_run`** → [complete-first-run.md](${CLAUDE_SKILL_DIR}/references/complete-first-run.md), Steps 1–6.
- **`merged_clean_ancestor`** → Step 8 below.
- **`on_main`** → Step 9. On `main`/`master` there is no PR for direct-to-main work: skip the PR flow entirely, no pr.json, no orphan probe. Step 11a still runs.
- **`already_complete`** → Step 12. Idempotent short-circuit: no re-cleanup, no duplicate completion event, no second pr.json.
<!-- pause: complete-orphan-pr-pick question -->
- **`orphan_ambiguous`** (`continue_to: null`, `candidates` present) → multiple orphan PRs match `interactive/<slug>` from slug reuse. Surface the candidates (PR number, state, `mergedAt`), ask which to use, write `pr.json` for it atomically, then re-run the router to classify the chosen PR's state.

### Step 8 — Worktree Cleanup

**Hard guard**: if `realpath "$PWD"` is inside the target worktree, exit with `cd out of the worktree before running cleanup; current PWD is the worktree being removed.` — do not auto-cd. The user exits (`ExitWorktree action="keep"` when EnterWorktree state is live, else `cd $(git rev-parse --show-toplevel)`) and re-invokes.

Cleanup runs only for `interactive/`-prefixed worktrees — check `git worktree list --porcelain` for `.claude/worktrees/interactive-{slug}`; no match → skip silently.

Both gates required, else skip with a warning naming the cause (a dirty worktree, or a non-ancestor branch not in origin/main): `git status --porcelain --ignored=traditional` inside the worktree is empty, and `git merge-base --is-ancestor <branch-head> origin/main` succeeds. Then `cleanup_worktree(slug, branch=f"interactive/{slug}", force=False)` — never `force=True`; on failure report and retain the worktree.

### Step 9 — Finalize

Resolve the backend once (`cortex-read-backlog-backend`, argless), then compose the write-back, index regen, and idempotent completion emission in one call:

```bash
cortex-lifecycle-finalize --feature {slug} --backend {resolved-backend} --backlog-file {backlog-filename}
```

`{backlog-filename}` is the file identified at lifecycle entry (`""` when none). Act on `state`: **`finalized`** → the item was marked complete (`session_id=null`, index regenerated best-effort) → Step 11a. **`external-backend`** → the local write-back was skipped; make the equivalent completion update on the configured tracker best-effort per `backlog.instructions`; the event is still emitted → Step 11a. **`error`** → surface `message` and halt. **Exit 2** → ambiguous backlog slug; apply backlog-writeback.md's exit-2 rule. The verb reads the feature's counters itself.

<!-- finalization-commit-step -->
### Step 11a — Commit Finalization Artifacts

```
cortex-lifecycle-stage-artifacts --phase complete --feature {slug}
```

The verb reads `commit-artifacts` itself (default true when absent) and owns the explicit-path staging. Act on `signal` — what this verb staged, not the shared index: **`config_disabled`** → relay its `message` and skip the commit. **`nothing_staged`** → skip `/cortex-core:commit` silently and continue to Step 12. **`staged`** → commit. A non-zero exit is a staging failure: halt rather than commit a partial set.

Invoke `/cortex-core:commit` with an imperative ≤72-char subject. On non-zero exit, surface the error and stop — do not imply the artifacts were committed. After a successful commit, if the branch is not `main` or `master`, advise: `Artifacts committed on <branch> rather than the default branch — move them to main if appropriate.` No automatic branch switch.
<!-- /finalization-commit-step -->

### Step 12 — Summarize

Feature name and description, tasks completed, key files created or modified, any open or follow-up items. Preserve `cortex/lifecycle/{slug}/` as project history. Emit the summary and exit.
