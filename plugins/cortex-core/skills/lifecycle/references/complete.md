# Complete Phase

Multi-step phase: creates a PR, pauses for merge on GitHub, then finalizes on re-invocation.

## Protocol

### Step 1 — Run Tests

Check for `cortex/lifecycle.config.md` and determine the test path:

- **Config exists with `test-command`**: Run the specified command.
- **Config exists without `test-command`**: Ask the user if there are tests to run.
- **No config exists**: Skip the test step. Note to the user: "No `cortex/lifecycle.config.md` found — skipping test step."

If tests fail, report the failures and do not proceed until they are resolved. First-run path only (state-aware routing in Step 7 skips Step 1 on re-invocation).

### Step 2 — Commit Lifecycle Artifacts

Run `cortex-read-commit-artifacts` to read the `commit-artifacts` flag from project config. If stdout is `true` (the default), stage `cortex/lifecycle/{slug}/` artifacts alongside any uncommitted source changes, then use `/cortex-core:commit` to create the commit. If stdout is `false`, exclude lifecycle artifacts from staging (commit only the uncommitted source changes via `/cortex-core:commit`).

**On-main short-circuit**: if the current branch is `main` or `master`, skip Steps 2–5 (no PR needed for direct-to-main work) and proceed to Step 7 with pr.json absent and no orphan-PR probe needed — treat as first-run path jumping directly to Steps 9–12. The finalization-tail artifact commit (Step 11a) runs on this path.

### Step 3 — Push Branch and Create PR

Push the branch to the remote, then create a pull request with a summary of the feature. The PR title and body should reflect the feature's purpose and include a link to the lifecycle directory.

**Variant A detection (advisory)**: Before invoking `/cortex-core:pr`, perform a two-signal check to determine whether this lifecycle is running from inside an `interactive/{slug}` worktree:

1. **Signal 1 — lock file**: call `cortex_command/interactive_lock.py:read_lock(feature_slug)`. A non-None return indicates an `interactive.pid` lock file is present for this slug.
2. **Signal 2 — directory corroboration**: run `git rev-parse --show-toplevel` and compare the result against `pwd`. If both resolve to the same path and that path is the `interactive/{slug}` worktree root, the session's CWD is confirmed inside the worktree.

If **both signals are positive** (lock file present and `git rev-parse --show-toplevel` matches the `interactive/{slug}` worktree path), apply the `cd-in-then-out` pattern around `/cortex-core:pr`: save `_origin_pwd=$(pwd)`, cd into the worktree, invoke `/cortex-core:pr`, then restore with `cd "$_origin_pwd"`.

If **either signal is absent or contradictory**, treat the session as NOT in Variant A and invoke `/cortex-core:pr` from the current cwd without any cd.

The detection is purely advisory — it does not block PR creation.

### Step 4 — Write `pr.json` Atomically

Resolve the repo identity:

```bash
gh repo view --json nameWithOwner -q .nameWithOwner
```

Write `cortex/lifecycle/{slug}/pr.json` using a tempfile + `os.replace` pattern (per `cortex/requirements/pipeline.md:124-130` atomicity invariant; create the tempfile in pr.json's parent directory — os.replace is atomic only within a single filesystem) with the following closed schema:

```json
{
  "number": <int>,
  "url": "<string>",
  "head_branch": "<string>",
  "opened_at": "<ISO8601 string>",
  "repo": "<owner/name>"
}
```

The `repo` field is resolved at PR-creation time and locked so Step 7's `gh pr view --repo <repo>` queries the correct repository even if `origin` changes between invocations.

### Step 5 — Emit `pr_opened` Event

Append a `pr_opened` event to `cortex/lifecycle/{slug}/events.log`:

```json
{"schema_version": 1, "ts": "<ISO8601>", "event": "pr_opened", "feature": "<slug>", "number": <int>, "url": "<string>", "head_branch": "<string>", "repo": "<owner/name>"}
```

### Step 6 — Phase-Exit Pause (Handoff Message)

Exit with the following handoff message and do not proceed further:

> PR open at `<url>`; merge on GitHub, then re-run `/cortex-core:lifecycle complete <slug>` to finalize.

Do not poll — manual re-invocation is the gate.

---

## Re-invocation: State-Aware Routing

When `/cortex-core:lifecycle complete <slug>` is invoked again after the phase-exit pause, enter Step 7 to route based on current lifecycle state.

### Step 7 — State-Aware Routing

Run the classifier verb to resolve the route from current lifecycle state. It reads `events.log` and `pr.json` (and queries `gh` only when a PR is in play), applies the strict-order, first-match-wins state machine — `feature_wontfix` precedes every PR-state check, and an already-logged `feature_complete` short-circuits ahead of them — and prints one JSON verdict:

```bash
cortex-lifecycle-complete-route <slug>
```

Act on the verdict; do not re-derive the routing yourself:

- **Terminal route** (`message` non-empty, `continue_to: null`): print `message` verbatim and exit. The verb owns the exact recovery/wait text for the wontfix, PR-state, and not-found dead-ends — surface it and stop.
- **`continue_to` set** — continue at the named step without re-running the verb:
  - `already_complete` → **Step 12** (idempotent short-circuit: no re-cleanup, no duplicate `feature_complete`, no second `pr.json`).
  - `on_main` → **Step 9** (direct-to-main work has no PR; Step 2's on-main short-circuit already routed here).
  - `first_run` → **Steps 1–6** (no PR exists yet; run the first-run path).
  - `merged_clean_ancestor` → **Step 8** (merged and verified present in `origin/main`; proceed to worktree cleanup).
- **`orphan_ambiguous`** (non-terminal, `continue_to: null`, `candidates` present): multiple orphan PRs match `interactive/<slug>` (slug reuse). Surface the candidates — their PR numbers, states, and `mergedAt` timestamps — and ask the user which to use. On selection, write `pr.json` for the chosen PR atomically (tempfile + `os.replace`), then re-run `cortex-lifecycle-complete-route <slug>` — `pr.json` is now present, so the re-run classifies the chosen PR's state and routes on it.

---

### Step 8 — Worktree Cleanup

**Hard guard**: before running cleanup, compare `realpath "$PWD"` with the worktree path. If the session is running from inside the target worktree, exit with:

> cd out of the worktree before running cleanup; current PWD is the worktree being removed.

Do not auto-cd. The user must exit the worktree and re-invoke. Two exit paths are available: `ExitWorktree action="keep"` is preferred when EnterWorktree session state is live (it clears the keep/remove prompt at session end), and `cd $(git rev-parse --show-toplevel)` works in both same-session and cross-session contexts (but defers the keep/remove prompt to session end when state is live).

**Prefix check**: cleanup runs only for `interactive/`-prefixed worktrees. Detect whether the feature was developed in an `interactive/{slug}` worktree by checking `git worktree list --porcelain` for a path matching `.claude/worktrees/interactive-{slug}` (or the resolved worktree root). If no `interactive/`-prefix worktree is found for this feature (Option 1 or Option 3 features), skip cleanup silently.

**Cleanup gate**: before calling the cleanup primitive, verify:

1. `git status --porcelain --ignored=traditional` inside the worktree is empty (dirty → skip with warning).
2. `git merge-base --is-ancestor <branch-head> origin/main` succeeds (non-ancestor → skip with warning).

**Cleanup call** (interactive prefix only):

```python
cleanup_worktree(slug, branch=f"interactive/{slug}", force=False)
```

No `force=True`. If cleanup fails, report the error and retain the worktree — do not retry with force.

### Step 9 — Backlog Write-Back

If a matching backlog item was identified earlier in the lifecycle, mark it complete and clear the session:

```bash
cortex-update-item <slug> --status complete --session-id null
```

If no backlog item was found, skip silently. If `cortex-update-item` exits with code 2, apply the canonical ambiguous-slug handling in backlog-writeback.md (loaded at lifecycle Step 2).

### Step 10 — Backlog Index Sync

After the `cortex-update-item` call (regardless of whether it succeeded, failed, or was skipped), resolve the active backlog backend with `cortex-read-backlog-backend` (argless; it prints the resolved backend and exits 0) before regenerating anything. On any value other than `cortex-backlog` (`none` OR an external tracker), skip the index regeneration with a one-line advisory that index sync is disabled for this repo — there is no index to regenerate under this backend. (Step 9's write-back is already backend-gated via backlog-writeback.md; this closes the same gap for Step 10, which previously ran unconditionally.)

On the `cortex-backlog` arm (the default), regenerate the backlog index using this fallback chain:

1. If `cortex-update-item` was not found (`command -v cortex-update-item` failed), emit: `"WARNING: cortex-update-item not found — backlog item status may not be updated."`
2. Attempt index regeneration in order:
   - Run `test -f cortex_command/backlog/generate_index.py` — if it exists, run `python3 -m cortex_command.backlog.generate_index` and emit: `"Index regenerated via cortex_command/backlog/generate_index.py"`
   - Else run `command -v cortex-generate-backlog-index` — if found on PATH, run `cortex-generate-backlog-index` and emit: `"Index regenerated via cortex-generate-backlog-index"`
   - Else emit: `"WARNING: Could not regenerate backlog index — no generate_index.py script found. Index may be stale."`

### Step 11 — Log `feature_complete`

Append a `feature_complete` event to `cortex/lifecycle/{slug}/events.log`:

```json
{"ts": "<ISO8601>", "event": "feature_complete", "feature": "<slug>", "tasks_total": <N>, "rework_cycles": <N>, "merge_anchor": "merge"}
```

Read `tasks_total` and `rework_cycles` by running `cortex-lifecycle-counters --feature {slug}` and parsing the JSON output. If no review phase occurred (simple tier), `rework_cycles` will be `0`.

This event closes the event log for the feature.

<!-- finalization-commit-step -->
### Step 11a — Commit Finalization Artifacts

Run `cortex-read-commit-artifacts` to read the `commit-artifacts` flag from project config (default true when absent).

**Flag is `false`**: skip the commit entirely. Note inline that lifecycle artifacts and any uncommitted source are left in the working tree for the operator to commit deliberately.

**Flag is `true`**: stage the finalization artifact set with the verb, then act on its `signal`:

```
cortex-lifecycle-stage-artifacts --phase complete --feature {slug}
```

The verb owns the explicit-path staging discipline — it stages the lifecycle artifacts, the review-drift requirements file (by the exact path review.md recorded), and the narrowed backlog write-back (the resolved ticket file plus the backlog index), all by enumerated paths, never a directory glob or `-u` sweep — and prints `{"signal": "staged"|"nothing_staged", "staged_paths": [...]}`.

**Stage-first idempotent guard**: the verb's `signal` is the staging outcome (equivalent to `git diff --cached --quiet`):

- `nothing_staged` (the index already matches HEAD — `git diff --cached --quiet` would exit 0): nothing new to commit — skip `/cortex-core:commit` silently and continue to Step 12 (common on the worktree path post-merge).
- `staged`: something is staged — proceed to commit.

A non-zero verb exit is a staging failure: halt before Step 12 rather than committing a partial set.

Invoke `/cortex-core:commit` with an imperative ≤72-char subject, for example:

```
Complete {slug}: lifecycle artifacts and backlog write-back
```

If `/cortex-core:commit` exits non-zero, surface the error and stop before the Step 12 summary — a summary implying the artifacts were committed should not be emitted until the commit succeeds.

After a successful commit, if the current branch is not `main` or `master`, surface a one-line advisory:

> Artifacts committed on `<branch>` rather than the default branch — move them to `main` if appropriate.

No automatic branch switch.
<!-- /finalization-commit-step -->

### Step 12 — Summarize and Preserve Lifecycle Directory

Provide a brief summary of what was built:
- Feature name and description
- Number of tasks completed
- Key files created or modified
- Any open items or follow-up work identified during implementation or review

The `cortex/lifecycle/{slug}/` directory is preserved as project history. Do not delete or archive the directory.

Proceed automatically — do not ask the user for confirmation. The lifecycle is now complete; emit the summary and exit without further prompts.

