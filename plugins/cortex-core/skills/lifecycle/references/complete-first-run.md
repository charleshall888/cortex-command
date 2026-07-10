# Complete Phase — First-Run PR Flow

Read this only on `first_run` routing from complete.md's Step 7, or on a fresh `complete` entry that has not yet opened a PR. It creates a PR, then pauses for merge on GitHub; re-invocation routing and finalization stay in complete.md.

## Protocol

### Step 1 — Run Tests

Determine the test path from `cortex/lifecycle.config.md`:
- **`test-command` set** → run it.
<!-- pause: complete-test-command-ask question -->
- **config without `test-command`** → ask the user if there are tests to run.
- **no config** → skip, noting "No `cortex/lifecycle.config.md` found — skipping test step."

Tests fail → report and halt until resolved. First-run path only — complete.md's Step 7 routing skips this step on re-invocation.

### Step 2 — Commit Lifecycle Artifacts

Run `cortex-read-commit-artifacts`. `true` (default) → stage `cortex/lifecycle/{slug}/` plus any uncommitted source and commit via `/cortex-core:commit`. `false` → commit only the source.

### Step 3 — Push Branch and Create PR

Push the branch, then create a PR whose title and body reflect the feature's purpose and link the lifecycle directory. Capture the returned PR number and URL, and the current branch (already known before the push), for Step 4.

**Variant A (advisory, non-blocking)**: if this lifecycle runs from inside an `interactive/{slug}` worktree — both `read_lock(slug)` returns non-None AND `git rev-parse --show-toplevel` is that worktree root — wrap `/cortex-core:pr` in a cd-in-then-out around the worktree. Otherwise invoke `/cortex-core:pr` from the current cwd.

### Step 4 — Record the Opened PR

One call resolves repo identity, atomically writes `cortex/lifecycle/{slug}/pr.json`, and logs the `pr_opened` event (schema_version-first, per the ADR-0020 hand-written exemption — see the verb for the exact shape). Pass `--url`/`--head-branch` from Step 3 so the verb skips its `gh pr view` fallback:

```bash
cortex-lifecycle-record-pr-opened --feature {slug} --number {pr-number} --url {pr-url} --head-branch {head-branch}
```

Act on `state`: `ok` → continue to Step 6. `gh-error` → surface `message` and halt — do not proceed to the handoff without a recorded PR. `repo` is resolved at PR-creation and locked so complete.md's Step 7 `gh pr view --repo <repo>` hits the right repository even if `origin` later changes.

<!-- pause: complete-merge-wait phase-exit-wait -->
### Step 6 — Phase-Exit Pause (Handoff Message)

Exit with this handoff and go no further:

> PR open at `<url>`; merge on GitHub, then re-run `/cortex-core:lifecycle complete <slug>` to finalize.

Don't poll — manual re-invocation is the gate.
