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

**On-main short-circuit**: if the current branch is `main` or `master`, skip Steps 2–5 (no PR needed for direct-to-main work) and proceed to Step 7 with pr.json absent and no orphan-PR probe needed — treat as first-run path jumping directly to Steps 9–12. The finalization-tail artifact commit (Step 11a) runs on this path; its stage-first guard ensures nothing is double-committed.

### Step 3 — Push Branch and Create PR

Push the branch to the remote, then create a pull request with a summary of the feature. The PR title and body should reflect the feature's purpose and include a link to the lifecycle directory.

**Variant A detection (advisory)**: Before invoking `/cortex-core:pr`, perform a two-signal check to determine whether this lifecycle is running from inside an `interactive/{slug}` worktree:

1. **Signal 1 — lock file**: call `cortex_command/interactive_lock.py:read_lock(feature_slug)`. A non-None return indicates an `interactive.pid` lock file is present for this slug.
2. **Signal 2 — directory corroboration**: run `git rev-parse --show-toplevel` and compare the result against `pwd`. If both resolve to the same path and that path is the `interactive/{slug}` worktree root, the session's CWD is confirmed inside the worktree.

If **both signals are positive** (lock file present and `git rev-parse --show-toplevel` matches the `interactive/{slug}` worktree path), apply the `cd-in-then-out` pattern around `/cortex-core:pr`:

```
(a) save _origin_pwd=$(pwd)
(b) cd into the interactive/{slug} worktree if not already there
(c) invoke /cortex-core:pr
(d) cd "$_origin_pwd" to restore the original working directory
```

If **either signal is absent or contradictory** (lock file missing or invalid, or `git rev-parse --show-toplevel` does not match the worktree path, or the two signals disagree), treat the session as NOT in Variant A and invoke `/cortex-core:pr` from the current cwd without any cd.

The detection is purely advisory — it does not block PR creation. When the `cd-in-then-out` path is taken, the restore in step (d) ensures the Step 8 cd-out hard guard composes correctly (Step 8 will find the session back in the original directory, not the worktree).

### Step 4 — Write `pr.json` Atomically

Resolve the repo identity:

```bash
gh repo view --json nameWithOwner -q .nameWithOwner
```

Write `cortex/lifecycle/{slug}/pr.json` using a tempfile + `os.replace` pattern (per `cortex/requirements/pipeline.md:124-130` atomicity invariant) with the following closed schema:

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

**Atomic write pattern**:

```python
import json, os, tempfile, pathlib

pr_json_path = pathlib.Path(f"cortex/lifecycle/{slug}/pr.json")
payload = {"number": number, "url": url, "head_branch": head_branch,
           "opened_at": opened_at, "repo": repo}
with tempfile.NamedTemporaryFile(
    mode="w", dir=pr_json_path.parent, delete=False, suffix=".tmp"
) as tmp:
    json.dump(payload, tmp, indent=2)
    tmp_path = tmp.name
os.replace(tmp_path, pr_json_path)
```

### Step 5 — Emit `pr_opened` Event

Append a `pr_opened` event to `cortex/lifecycle/{slug}/events.log`:

```json
{"schema_version": 1, "ts": "<ISO8601>", "event": "pr_opened", "feature": "<slug>", "number": <int>, "url": "<string>", "head_branch": "<string>", "repo": "<owner/name>"}
```

### Step 6 — Phase-Exit Pause (Handoff Message)

Exit with the following handoff message and do not proceed further:

> PR open at `<url>`; merge on GitHub, then re-run `/cortex-core:lifecycle complete <slug>` to finalize.

This is the kept phase-exit pause. The user merges the PR on GitHub (or delegates merge to a reviewer), then re-invokes the complete phase to trigger Steps 7–12.

---

## Re-invocation: State-Aware Routing

When `/cortex-core:lifecycle complete <slug>` is invoked again after the phase-exit pause, enter Step 7 to route based on current lifecycle state.

### Step 7 — State-Aware Routing

Evaluate in strict order. Each branch is terminal unless noted otherwise (i.e., continues to Steps 8–12).

**Evaluation order:**

#### Branch 1 — `feature_wontfix` present in events.log

Scan `cortex/lifecycle/{slug}/events.log` for a `feature_wontfix` event. If present, exit with:

> lifecycle was wontfix'd at `<ts>`; nothing to complete (worktree cleanup skipped).

Takes precedence over all pr.json and PR-state checks, including the case where a PR was already created.

#### Branch 2 — `feature_complete` already in events.log

Scan events.log for a `feature_complete` event. If present, short-circuit to the summary in Step 12. No duplicate event, no re-cleanup, no second `pr.json` write.

#### Branch 3 — `pr.json` absent (orphan-PR probe)

Check whether `cortex/lifecycle/{slug}/pr.json` exists.

If absent, probe for an orphan PR (the case where Step 3 created a PR but Step 4 crashed before writing pr.json):

```bash
gh pr list --head "interactive/{slug}" --state all --json number,state,mergedAt --limit 5
```

- **Zero matches**: run first-run path (Steps 1–6). Step 1 tests re-run; if no orphan, PR creation is fresh.
- **Exactly one match**: retroactively reconstruct `pr.json` from the response, write it atomically (same pattern as Step 4), then proceed to Branch 4 (query PR state).
- **Multiple matches (slug-reuse)**: surface the candidates with PR numbers, states, and `mergedAt` timestamps; ask the user which to use (interactive recovery path). On selection, write pr.json and proceed to Branch 4.

#### Branch 4 — Query PR state via `gh pr view`

Read `cortex/lifecycle/{slug}/pr.json` and query:

```bash
gh pr view <number> --json state,mergedAt --repo <repo>
```

Route on the result:

**4a — Auth/network error**: `gh auth status` exits non-zero, or `gh pr view` exits non-zero with output matching network/auth error patterns. Exit with:

> PR state unknown; gh unauthenticated or network error; retry later. (Worktree retained.)

**4b — PR not found**: `gh pr view` exits non-zero with output matching "Could not resolve to a PullRequest" or "GraphQL: not found". Exit with:

> PR `<number>` referenced in pr.json was not found on GitHub. The PR may have been deleted. Run `git worktree remove <path>` manually if appropriate, or restore the PR. (Worktree retained.)

**4c — `state=OPEN`**: Exit with:

> PR open at `<url>`; merge first.

**4d — `state=MERGED` (`mergedAt != null`) + dirty worktree**: Check `git status --porcelain` inside the worktree. If non-empty, exit with:

> uncommitted changes at `<path>`; resolve first.

**4e — `state=MERGED` + clean worktree + branch is local ancestor of `origin/main`**: Branch head passes `git merge-base --is-ancestor <branch-head> origin/main`. Continue to Steps 8–12.

**4f — `state=MERGED` + clean worktree + branch NOT local ancestor of `origin/main`**: Exit with:

> branch head is not in origin/main (possible squash with non-ancestor commit or fork-merge); refusing cleanup until verified. Run `git worktree remove <path>` manually to override.

**4g — `state=CLOSED` (`mergedAt == null`, closed without merge)**: Exit with:

> PR `<url>` was closed without merging. Either reopen and merge, run `git worktree remove <path>` manually to abandon, or invoke `/cortex-core:lifecycle wontfix <slug>` if appropriate. (Worktree retained.)

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

If no backlog item was found, skip silently. If `cortex-update-item` exits with code 2, the slug was ambiguous: present the candidate list on stderr to the user and ask them to re-invoke with a disambiguated slug.

### Step 10 — Backlog Index Sync

After the `cortex-update-item` call (regardless of whether it succeeded, failed, or was skipped), regenerate the backlog index using this fallback chain:

1. If `cortex-update-item` was not found (`command -v cortex-update-item` failed), emit: `"WARNING: cortex-update-item not found — backlog item status may not be updated."`
2. Attempt index regeneration in order:
   - Run `test -f cortex_command/backlog/generate_index.py` — if it exists, run `python3 cortex_command/backlog/generate_index.py` and emit: `"Index regenerated via cortex_command/backlog/generate_index.py"`
   - Else run `command -v cortex-generate-backlog-index` — if found on PATH, run `cortex-generate-backlog-index` and emit: `"Index regenerated via cortex-generate-backlog-index"`
   - Else emit: `"WARNING: Could not regenerate backlog index — no generate_index.py script found. Index may be stale."`

Each fallback is a separate Bash tool call using `test -f` or `command -v` to check availability before running.

### Step 11 — Log `feature_complete`

Append a `feature_complete` event to `cortex/lifecycle/{slug}/events.log`:

```json
{"ts": "<ISO8601>", "event": "feature_complete", "feature": "<slug>", "tasks_total": <N>, "rework_cycles": <N>, "merge_anchor": "merge"}
```

Read `tasks_total` and `rework_cycles` by running `cortex-lifecycle-counters --feature {slug}` and parsing the JSON output. If no review phase occurred (simple tier), `rework_cycles` will be `0`.

The `merge_anchor: "merge"` field identifies this event as post-restructure regime (distinct from pre-restructure events which emit `merge_anchor: "review"` or omit the field). Readers tolerate the field's absence on legacy events (default to `"review"`).

This event closes the event log for the feature.

<!-- finalization-commit-step -->
### Step 11a — Commit Finalization Artifacts

Run `cortex-read-commit-artifacts` to read the `commit-artifacts` flag from project config. The binstub prints `true` or `false` on stdout; when the file or field is absent, treat the result as `true`.

**Flag is `false`**: skip the commit entirely. Note inline that lifecycle artifacts and any uncommitted source are left in the working tree for the operator to commit deliberately.

**Flag is `true`**: stage the artifact set below and proceed to the stage-first guard.

Stage the lifecycle dir by enumerated paths (those present on disk):

```
git add -- cortex/lifecycle/{slug}/research.md \
            cortex/lifecycle/{slug}/spec.md \
            cortex/lifecycle/{slug}/plan.md \
            cortex/lifecycle/{slug}/review.md \
            cortex/lifecycle/{slug}/index.md \
            cortex/lifecycle/{slug}/events.log
```

Stage by enumerated paths only — a directory-scoped add on the lifecycle dir would sweep in un-gitignored residue such as `critical-review-residue.json` and `learnings/*`.

Stage the backlog write-back with a directory-scoped add, which captures the resolved item `.md`, the regenerated `index.json`/`index.md`, and any sibling/parent `.md` files rewritten by `cortex-update-item`'s terminal-status cascade:

```
git add cortex/backlog/
```

The gitignored `cortex/backlog/*.events.jsonl` sidecar is excluded automatically.

**Stage-first idempotent guard**: after staging, run:

```
git diff --cached --quiet
```

- Exit 0 (nothing staged): nothing new to commit — skip `/cortex-core:commit` silently and continue to Step 12. This covers the worktree-interactive post-merge path, where the lifecycle artifacts are already on `main` via the merge and the targeted `git add` stages nothing.
- Exit 1 (something staged): proceed to commit.

Invoke `/cortex-core:commit` with an imperative ≤72-char subject, for example:

```
Complete {slug}: lifecycle artifacts and backlog write-back
```

If `/cortex-core:commit` exits non-zero, surface the error and stop before the Step 12 summary — a summary implying the artifacts were committed should not be emitted until the commit succeeds. The operator resolves the underlying failure and re-invokes; Branch 2 of Step 7 (`feature_complete` present) will short-circuit to Step 12 on retry, leaving the stage-first guard to no-op.

After a successful commit, if the current branch is not `main` or `master`, surface a one-line advisory:

> Artifacts committed on `<branch>` rather than the default branch — move them to `main` if appropriate.

This covers the feature-branch (no-worktree) flow, where the finalization tail runs on `feature/{slug}` after merge. No automatic branch switch — branch normalization is deferred.
<!-- /finalization-commit-step -->

### Step 12 — Summarize and Preserve Lifecycle Directory

Provide a brief summary of what was built:
- Feature name and description
- Number of tasks completed
- Key files created or modified
- Any open items or follow-up work identified during implementation or review

The `cortex/lifecycle/{slug}/` directory is preserved as project history. It contains the research, specification (if applicable), plan, implementation events, and the `pr.json` handoff artifact. Do not delete or archive the directory.

Proceed automatically — do not ask the user for confirmation. The lifecycle is now complete; emit the summary and exit without further prompts.

## Constraints

| Thought | Reality |
|---------|---------|
| "Let me clean up the lifecycle directory" | The lifecycle directory is project documentation. Preserve it for future reference. |
| "I'll force-remove the worktree to be safe" | `cleanup_worktree()` never receives `force=True` from the interactive path. Retain on dirty or non-ancestor. |
| "I'll create the PR again on re-invocation" | On re-invocation, read `pr.json` first. Never create a duplicate PR. |
| "I'll poll GitHub at every SessionStart" | Manual re-invocation is the gate. No automated polling. |
