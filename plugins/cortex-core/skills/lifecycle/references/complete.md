# Complete Phase

Creates a PR, pauses for merge on GitHub, then finalizes on re-invocation.

## Protocol

### Step 1 — Run Tests

Determine the test path from `cortex/lifecycle.config.md`:
- **`test-command` set** → run it.
- **config without `test-command`** → ask the user if there are tests to run.
- **no config** → skip, noting "No `cortex/lifecycle.config.md` found — skipping test step."

Tests fail → report and halt until resolved. First-run path only — Step 7's routing skips Step 1 on re-invocation.

### Step 2 — Commit Lifecycle Artifacts

Run `cortex-read-commit-artifacts`. `true` (default) → stage `cortex/lifecycle/{slug}/` plus any uncommitted source and commit via `/cortex-core:commit`. `false` → commit only the source.

**On-main short-circuit**: on `main`/`master`, skip Steps 2–5 (no PR for direct-to-main work) and jump to Steps 9–12 with pr.json absent — no orphan-PR probe. Step 11a's artifact commit still runs.

### Step 3 — Push Branch and Create PR

Push the branch, then create a PR whose title and body reflect the feature's purpose and link the lifecycle directory. Capture the returned PR number for Step 4.

**Variant A (advisory, non-blocking)**: if this lifecycle runs from inside an `interactive/{slug}` worktree — both `read_lock(slug)` returns non-None AND `git rev-parse --show-toplevel` is that worktree root — wrap `/cortex-core:pr` in a cd-in-then-out around the worktree. Otherwise invoke `/cortex-core:pr` from the current cwd.

### Step 4 — Record the Opened PR

One call resolves repo identity, atomically writes `cortex/lifecycle/{slug}/pr.json`, and logs the `pr_opened` event (schema_version-first, per the ADR-0020 hand-written exemption — see the verb for the exact shape):

```bash
cortex-lifecycle-record-pr-opened --feature {slug} --number {pr-number}
```

Act on `state`: `ok` → continue to Step 6. `gh-error` → surface `message` and halt — do not proceed to the handoff without a recorded PR. `repo` is resolved at PR-creation and locked so Step 7's `gh pr view --repo <repo>` hits the right repository even if `origin` later changes.

### Step 6 — Phase-Exit Pause (Handoff Message)

Exit with this handoff and go no further:

> PR open at `<url>`; merge on GitHub, then re-run `/cortex-core:lifecycle complete <slug>` to finalize.

Don't poll — manual re-invocation is the gate.

---

## Re-invocation: State-Aware Routing

### Step 7 — State-Aware Routing

The classifier verb reads `events.log` and `pr.json` (querying `gh` only when a PR is in play) and prints one JSON verdict:

```bash
cortex-lifecycle-complete-route <slug>
```

Act on the verdict; do not re-derive it:

- **Terminal** (`message` non-empty, `continue_to: null`): print `message` verbatim and exit — the verb owns the exact recovery/wait text.
- **`continue_to` set** — continue at the named step: `already_complete` → **Step 12** (idempotent short-circuit: no re-cleanup, no duplicate `feature_complete`, no second `pr.json`); `on_main` → **Step 9**; `first_run` → **Steps 1–6**; `merged_clean_ancestor` → **Step 8**.
- **`orphan_ambiguous`** (`continue_to: null`, `candidates` present): multiple orphan PRs match `interactive/<slug>` (slug reuse). Surface the candidates (PR number, state, `mergedAt`), ask which to use, write `pr.json` for it atomically, then re-run `cortex-lifecycle-complete-route <slug>` to classify the chosen PR's state.

---

### Step 8 — Worktree Cleanup

**Hard guard**: if `realpath "$PWD"` is inside the target worktree, exit with `cd out of the worktree before running cleanup; current PWD is the worktree being removed.` — do not auto-cd. The user exits (`ExitWorktree action="keep"` when EnterWorktree state is live, else `cd $(git rev-parse --show-toplevel)`) and re-invokes.

**Prefix check**: cleanup runs only for `interactive/`-prefixed worktrees — check `git worktree list --porcelain` for `.claude/worktrees/interactive-{slug}`. No match → skip silently.

**Gate** — both required, else skip with a warning naming the cause (dirty worktree, or non-ancestor branch not in origin/main): (1) `git status --porcelain --ignored=traditional` inside the worktree is empty; (2) `git merge-base --is-ancestor <branch-head> origin/main` succeeds.

**Call**: `cleanup_worktree(slug, branch=f"interactive/{slug}", force=False)`. No `force=True` — on failure, report and retain the worktree.

### Step 9 — Backlog Write-Back

If a backlog item was identified earlier, mark it complete and clear the session:

```bash
cortex-update-item <slug> --status complete --session-id null
```

No item → skip silently. Exit code 2 → apply the ambiguous-slug handling in backlog-writeback.md (loaded at lifecycle Step 2).

### Step 10 — Backlog Index Sync

After the Step 9 call (success, failure, or skip), resolve the backend with `cortex-read-backlog-backend` (argless). Any value other than `cortex-backlog` → skip with a one-line advisory that index sync is disabled for this repo. On `cortex-backlog` (default), regenerate via the two-tier fallback: module path `python3 -m cortex_command.backlog.generate_index` first, CLI `cortex-generate-backlog-index` second, else a stale-index warning.

### Step 11 — Log `feature_complete`

```bash
cortex-lifecycle-event feature-complete --feature {slug} --tasks-total {N} --rework-cycles {N} --merge-anchor merge
```

Read `{N}` from `cortex-lifecycle-counters --feature {slug}` (JSON `tasks_total`/`rework_cycles`). Simple tier (no review) → `rework_cycles` is `0`. This event closes the feature's log.

**Idempotent-skip guard**: if a `feature_complete` row already exists in the working-tree events.log, skip the verb and continue to Step 11a — a duplicate from a commit-retry corrupts the log. Match on a parsed JSON `event` field, not a substring.

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
