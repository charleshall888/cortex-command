# Complete Phase

Opens a PR, waits for the merge on GitHub, and finishes when re-run.

### Step 7 — Routing

```bash
cortex-lifecycle-complete-route <slug>
```

It reads `events.log` and `pr.json` (and asks `gh` only when there is a PR) and prints one verdict. Act on it; don't re-derive it:

- **End** (`message` non-empty, `continue_to: null`) → print `message` exactly and exit.
- `first_run` → [complete-first-run.md](${CLAUDE_SKILL_DIR}/references/complete-first-run.md).
- `merged_clean_ancestor` → Step 8.
- `on_main` → Step 9. Work done on main has no PR and no pr.json; Step 11a still runs.
- `already_complete` → Step 12. Do not clean up again, log a second completion event, or write a second pr.json.
<!-- pause: complete-orphan-pr-pick question -->
- `orphan_ambiguous` (`continue_to: null`, `candidates` present) → the slug was reused, so several PRs match `interactive/<slug>`. Show each number, state, and `mergedAt`. Ask which one, write `pr.json` for it atomically, and re-run the command.

### Step 8 — Worktree cleanup

**Hard guard**: if `realpath "$PWD"` is inside the worktree to remove, exit with `cd out of the worktree before running cleanup; current PWD is the worktree being removed.` Never cd for the user. The user leaves and re-runs: `ExitWorktree action="keep"` when EnterWorktree state is live, else `cd "$(git rev-parse --git-common-dir)/.."` (`--show-toplevel` returns the worktree itself).

Clean only `interactive/` worktrees: look in `git worktree list --porcelain` for `.claude/worktrees/interactive-{slug}`; no match → skip silently. Two checks must both pass: `git status --porcelain --ignored=traditional` inside the worktree is empty, and `git merge-base --is-ancestor <branch-head> origin/main` succeeds. Otherwise skip with a warning that names the cause (a dirty worktree, or a non-ancestor branch not in origin/main). Then from the main repo: `git worktree remove <path>` (never `--force`), `git worktree prune`, `git branch -d interactive/{slug}`; on failure, report it and keep the worktree.

### Step 9 — Finalize

```bash
cortex-lifecycle-finalize --feature {slug} --backlog-file {backlog-filename}
```

`{backlog-filename}` is the file found at entry (`""` when none); the command finds the backend itself. `finalized` → marked complete, `session_id=null`, index rebuilt → Step 11a. `external-backend` → no local update was made; try to make the same update on the tracker per `backlog.instructions`; the event is still logged → Step 11a. `error` → show `message` and stop. Exit 2 → ambiguous slug; backlog-writeback.md's exit-2 rule.

<!-- finalization-commit-step -->
### Step 11a — Commit finalization artifacts

```
cortex-lifecycle-stage-artifacts --phase complete --feature {slug} --commit-subject "Complete {slug}: finalization artifacts"
```

The command reads `commit-artifacts` itself, stages by exact path, and commits only what it staged. Act on `signal`: `config_disabled` → show `message`; `nothing_staged` → Step 12; `staged` → show `commit.sha`, or on `commit.state: failed` show `commit.message` and stop. Never imply the artifacts were committed. After a commit on a branch other than `main`/`master`, advise: `Artifacts committed on <branch> rather than the default branch — move them to main if appropriate.` Do not switch branches.
<!-- /finalization-commit-step -->

### Step 12 — Summarize

Feature and description, tasks completed, key files, open or follow-up items. Keep `cortex/lifecycle/{slug}/` as project history. Print the summary and exit.
