# Complete Phase — First-Run PR Flow

Read only when complete.md routes `first_run`. Opens the PR, then waits for the merge. complete.md handles the re-run and the finish.

## Step 1 — Tests

`test-command` in `cortex/lifecycle.config.md` → run it.
<!-- pause: complete-test-command-ask question -->
Config present without `test-command` → ask whether there are tests to run. No config → skip, noting "No `cortex/lifecycle.config.md` found — skipping test step." Failures → report and stop until fixed. First run only.

## Step 2 — Commit

`cortex-read-commit-artifacts`: `true` (default) → stage `cortex/lifecycle/{slug}/` plus uncommitted source and commit; `false` → source only.

## Step 3 — Push and open the PR

Push, then create a PR whose title and body describe the feature and link the lifecycle directory. Note the number, URL, and branch. For an `interactive/{slug}` worktree (`cortex-interactive-lock inspect {slug}` reports `LIVE` **and** `git rev-parse --show-toplevel` is that root), cd in, run `gh pr create`, and cd back out; otherwise run it from cwd.

## Step 4 — Record it

```bash
cortex-lifecycle-record-pr-opened --feature {slug} --number {pr-number} --url {pr-url} --head-branch {head-branch}
```

Writes `pr.json` atomically (repo identity fixed at creation) and logs the event; `--url`/`--head-branch` save it a `gh pr view` call. `ok` → Step 5. `gh-error` → show `message` and stop; never hand off without a recorded PR.

<!-- pause: complete-merge-wait phase-exit-wait -->
## Step 5 — Phase-exit pause

Exit with this message and do nothing more. The user re-runs by hand; don't poll:

> PR open at `<url>`; merge on GitHub, then re-run `/cortex-core:build complete <slug>` to finalize.
