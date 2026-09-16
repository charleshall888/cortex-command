# Complete Phase

Opens a PR, pauses for merge on GitHub, finalizes on re-invocation.

### Step 7 — Routing

```bash
cortex-lifecycle-complete-route <slug>
```

The verb reads `events.log` and `pr.json` (querying `gh` only when a PR is in play) and prints one verdict. Act on it; don't re-derive:

- **Terminal** (`message` non-empty, `continue_to: null`) → print `message` verbatim and exit.
- `first_run` → [complete-first-run.md](${CLAUDE_SKILL_DIR}/references/complete-first-run.md).
- `merged_clean_ancestor` → Step 8.
- `on_main` → Step 9. Direct-to-main work has no PR: no pr.json, no orphan probe; Step 11a still runs.
- `already_complete` → Step 12. Idempotent: no re-cleanup, no duplicate completion event, no second pr.json.
<!-- pause: complete-orphan-pr-pick question -->
- `orphan_ambiguous` (`continue_to: null`, `candidates` present) → several orphan PRs match `interactive/<slug>` from slug reuse. Show number, state, `mergedAt`; ask which; write `pr.json` for it atomically; re-run the router.

### Step 8 — Worktree cleanup

**Hard guard**: `realpath "$PWD"` inside the target worktree → exit with `cd out of the worktree before running cleanup; current PWD is the worktree being removed.` — never auto-cd. The user exits (`ExitWorktree action="keep"` when EnterWorktree state is live, else `cd "$(git rev-parse --git-common-dir)/.."` — `--show-toplevel` returns the worktree itself) and re-invokes.

Only `interactive/`-prefixed worktrees are cleaned — `git worktree list --porcelain` for `.claude/worktrees/interactive-{slug}`; no match → skip silently. Both gates required, else skip with a warning naming the cause (a dirty worktree, or a non-ancestor branch not in origin/main): `git status --porcelain --ignored=traditional` inside the worktree is empty, and `git merge-base --is-ancestor <branch-head> origin/main` succeeds. Then from the main repo: `git worktree remove <path>` (never `--force`), `git worktree prune`, `git branch -d interactive/{slug}`; on failure report and retain.

### Step 9 — Finalize

```bash
cortex-lifecycle-finalize --feature {slug} --backlog-file {backlog-filename}
```

`{backlog-filename}` is the file identified at entry (`""` when none); the verb resolves the backend itself. `finalized` → marked complete, `session_id=null`, index regenerated → Step 11a. `external-backend` → local write-back skipped; make the equivalent update on the tracker best-effort per `backlog.instructions`; the event is still emitted → Step 11a. `error` → surface `message`, halt. Exit 2 → ambiguous slug; backlog-writeback.md's exit-2 rule.

<!-- finalization-commit-step -->
### Step 11a — Commit finalization artifacts

```
cortex-lifecycle-stage-artifacts --phase complete --feature {slug} --commit-subject "Complete {slug}: finalization artifacts"
```

The verb reads `commit-artifacts` itself, owns explicit-path staging, and commits exactly its staged set. Act on `signal`: `config_disabled` → relay `message`; `nothing_staged` → continue to Step 12; `staged` → relay `commit.sha`, or on `commit.state: failed` surface `commit.message` and stop — never imply the artifacts were committed. After a commit off `main`/`master`, advise: `Artifacts committed on <branch> rather than the default branch — move them to main if appropriate.` No automatic switch.
<!-- /finalization-commit-step -->

### Step 12 — Summarize

Feature and description, tasks completed, key files, open or follow-up items. Preserve `cortex/lifecycle/{slug}/` as project history. Emit the summary and exit.
