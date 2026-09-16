# Complete Phase — First-Run PR Flow

Read only on `first_run` routing from complete.md. Opens the PR, then pauses for merge; re-invocation routing and finalization stay in complete.md.

## Step 1 — Tests

`test-command` in `cortex/lifecycle.config.md` → run it.
<!-- pause: complete-test-command-ask question -->
Config present without `test-command` → ask whether there are tests to run. No config → skip, noting "No `cortex/lifecycle.config.md` found — skipping test step." Failures → report and halt until resolved. First run only.

## Step 2 — Commit

`cortex-read-commit-artifacts`: `true` (default) → stage `cortex/lifecycle/{slug}/` plus uncommitted source and commit; `false` → source only.

## Step 3 — Push and open the PR

Push, then create a PR whose title and body reflect the feature and link the lifecycle directory. Capture number, URL, and branch. Inside an `interactive/{slug}` worktree (`cortex-interactive-lock inspect {slug}` reports `LIVE` **and** `git rev-parse --show-toplevel` is that root) wrap `gh pr create` in a cd-in-then-out; otherwise run it from cwd.

## Step 4 — Record it

```bash
cortex-lifecycle-record-pr-opened --feature {slug} --number {pr-number} --url {pr-url} --head-branch {head-branch}
```

Atomically writes `pr.json` (repo identity locked at creation) and logs the event; passing `--url`/`--head-branch` skips its `gh pr view` fallback. `ok` → Step 5. `gh-error` → surface `message`, halt; never hand off without a recorded PR.

<!-- pause: complete-merge-wait phase-exit-wait -->
## Step 5 — Phase-exit pause

Exit with this handoff and go no further — manual re-invocation is the gate, don't poll:

> PR open at `<url>`; merge on GitHub, then re-run `/cortex-core:build complete <slug>` to finalize.
